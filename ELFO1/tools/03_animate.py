"""Step 3 - Animazioni (v3: gambe con IK e contatto reale col pavimento).

La v2 aveva corretto i segni delle rotazioni e la composizione della catena, ma
restava un errore di fondo: le gambe erano **cinematiche dirette**. Con una
coscia che oscilla di +-30 gradi e il bacino che si abbassa di 1,6 cm, il piede
non puo' restare a terra: il personaggio galleggia (fino a +17 cm nella `Run`)
e affonda (fino a -8 cm nella `Cast`). Il ginocchio inoltre si muoveva con una
curva arbitraria, non con la geometria della gamba.

Qui ogni gamba e' risolta con **IK a due ossa** su un bersaglio di caviglia
espresso in coordinate mondo:

    H = testa del femore (dopo la posa di bacino/spina/root)
    A = bersaglio di caviglia (y, z decisi dal passo)
    K = H + dir*a + polo*h,   a = (l1^2 - l2^2 + d^2) / 2d

Il polo del ginocchio e' "avanti" nel frame del bacino, quindi il ginocchio si
piega sempre nella direzione giusta, anche quando il root ruota (Death). Le
rotazioni delle ossa si ricavano dalla direzione desiderata:

    D_eff = rotazione minima che porta la direzione di rest su quella voluta
    B(b)  = Rest(b)^-1 @ D_eff(parent)^-1 @ D_eff(b) @ Rest(b)

Il bacino e' calcolato perché la gamba d'appoggio arrivi al suolo: se il piede e'
avanti di `dy`, l'anca deve stare a `z_ankle + sqrt(L^2 - dy^2)`, quindi il
bacino scende di 5-6 cm ai doppi appoggi e risale al passaggio: il classico
"bob" del passo, che prima mancava. Il run ha una fase di volo vera.

Ultimo passaggio, **verifica sul modello**: per ogni frame si valuta la mesh in
posa e si sposta il `root` in verticale finché il punto piu' basso non tocca il
pavimento (nei frame di volo si controlla solo che non affondi). Il contatto
non e' piu' dedotto dalle ossa: e' misurato sulla superficie.

Clip a 30 fps:

  * `Idle`  120f loop: respiro, trasferimento di peso, testa che si guarda
                   intorno, braccia lungo i fianchi (non piu' in A-pose),
                   ciocche e falde in ritardo.
  * `Walk`   36f loop: appoggio di tallone, rullata, stacco di punta, braccia in
                   opposizione, piede piantato a terra in ogni frame.
  * `Run`    24f loop: falcata, appoggio di avampiede, fase di volo, busto in
                   avanti, gomiti a ~90, braccia che accompagnano.
  * `Cast`   72f     : raccolta, apertura, carica, SPINTA dei palmi in avanti
                   con passo, rientro.
  * `Death`  90f     : colpo, ginocchia che cedono, caduta all'indietro con il
                   corpo che si appoggia al pavimento, assestamento.

Output: $ELFO1_WORK/stage3.blend e $ELFO1_WORK/anim_report.json
"""
import bpy
import json
import math
import os
import sys
from mathutils import Quaternion, Vector

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common import WORK
from skeleton import BONES

SRC = os.path.join(WORK, "stage2.blend")
OUT = os.path.join(WORK, "stage3.blend")
REPORT_JSON = os.path.join(WORK, "anim_report.json")
FPS = 30
TAU = 2.0 * math.pi

bpy.ops.wm.open_mainfile(filepath=SRC)
sc = bpy.context.scene
sc.render.fps = FPS
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
body = next(o for o in bpy.data.objects if o.type == 'MESH')
bpy.context.view_layer.objects.active = arm
for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'

# --------------------------------------------------------------- catena -----
REST = {pb.name: pb.bone.matrix_local.to_3x3().copy() for pb in arm.pose.bones}
REST_HEAD = {pb.name: pb.bone.head_local.copy() for pb in arm.pose.bones}
REST_TAIL = {pb.name: pb.bone.tail_local.copy() for pb in arm.pose.bones}
PARENT = {b[0]: b[1] for b in BONES}
ALL_BONES = [b[0] for b in BONES]                 # gia' in ordine gerarchico
SIDES = (("L", 1.0), ("R", -1.0))

# ossa delle gambe: risolte da IK, non dalla posa "semantica"
LEG_BONES = {"thigh.L", "thigh.R", "shin.L", "shin.R",
             "foot.L", "foot.R", "toe.L", "toe.R"}

X = Vector((1.0, 0.0, 0.0))
Y = Vector((0.0, 1.0, 0.0))
Z = Vector((0.0, 0.0, 1.0))

# misure della gamba (unita' del sorgente: il modello e' alto 1,0)
L_THIGH = (REST_TAIL["thigh.L"] - REST_HEAD["thigh.L"]).length
L_SHIN = (REST_TAIL["shin.L"] - REST_HEAD["shin.L"]).length
L_LEG = L_THIGH + L_SHIN
# lunghezza "comoda": la gamba resta leggermente flessa anche a fine falcata
L_STAND = L_LEG - 0.022
HIP_Z = REST_HEAD["thigh.L"].z
ANKLE_Z = REST_HEAD["foot.L"].z
HIP_X = REST_HEAD["thigh.L"].x
ANKLE_X = 0.125                                   # appoggio piu' stretto del rest
print(f"[rig] gamba: coscia {L_THIGH:.3f} stinco {L_SHIN:.3f} "
      f"anca z={HIP_Z:.3f} caviglia z={ANKLE_Z:.3f}")


# ------------------------------------------------------------- primitive ----
def A(axis, deg):
    """Quaternione: rotazione di `deg` gradi attorno all'asse (char frame)."""
    if abs(deg) < 1e-9:
        return Quaternion()
    return Quaternion(axis, math.radians(deg))


def fwd(deg):
    return A(X, -deg)


def abduct(deg, sign):
    return A(Y, -sign * deg)


def twist(deg, bone, sign=1.0):
    if abs(deg) < 1e-9:
        return Quaternion()
    return Quaternion(REST[bone] @ Y, math.radians(sign * deg))


def sp(pitch=0.0, roll=0.0, yaw=0.0):
    """Spina/anca/collo/testa (ossa che puntano in su)."""
    return A(Z, yaw) @ A(Y, roll) @ A(X, pitch)


def smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def cyclic(p, knots):
    """Interpolazione cosinusoidale periodica su nodi (fase, valore)."""
    ph = p % 1.0
    n = len(knots)
    for i in range(n):
        p0, v0 = knots[i]
        p1, v1 = knots[(i + 1) % n]
        hi = p1 if p1 > p0 else p1 + 1.0
        hp = ph if ph >= p0 else ph + 1.0
        if p0 <= hp <= hi:
            t = (hp - p0) / max(hi - p0, 1e-9)
            return v0 + (v1 - v0) * (0.5 - 0.5 * math.cos(math.pi * t))
    return knots[0][1]


# -------------------------------------------------------------- pose --------
class Pose:
    """Accumula i delta di ogni osso nel character frame.

    Le gambe non passano di qui: vengono risolte da `solve_leg()` con bersagli
    di caviglia in coordinate mondo. `legs_fk` resta disponibile per la `Death`,
    dove il corpo ruota con il root e le gambe devono seguirlo.
    """

    def __init__(self):
        self.d = {}

    def add(self, name, q):
        self.d[name] = (q @ self.d[name]) if name in self.d else q.copy()

    def bone(self, name, pitch=0.0, roll=0.0, yaw=0.0):
        self.add(name, sp(pitch, roll, yaw))

    def arm(self, side, swing=0.0, adduct=22.0, elbow=10.0, wrist=0.0,
            grip=8.0, thumb=4.0, twist_deg=0.0, lift=0.0):
        """Un braccio.

        `swing`  > 0 = braccio in AVANTI.
        `adduct` > 0 = braccio verso il fianco (la posa di rest e' una A-pose a
                       ~38 gradi; 24 gradi lo portano a ~14, una posa naturale).
        `elbow`  > 0 = flessione del gomito (mano in avanti).
        """
        sign = 1.0 if side == "L" else -1.0
        self.add(f"clavicle.{side}",
                 fwd(swing * 0.10) @ abduct(-adduct * 0.10 + lift * 0.25, sign))
        self.add(f"upperarm.{side}",
                 fwd(swing) @ abduct(-adduct + lift, sign)
                 @ twist(twist_deg, f"upperarm.{side}", sign))
        self.add(f"forearm.{side}",
                 A(X, -elbow) @ twist(twist_deg * 0.4, f"forearm.{side}", sign))
        self.add(f"hand.{side}", A(X, wrist))
        self.add(f"fingers.{side}", A(X, grip))
        self.add(f"thumb.{side}", A(Z, sign * thumb * 0.6) @ A(X, thumb * 0.5))

    def arms(self, **kw):
        self.arm("L", **kw)
        self.arm("R", **kw)

    def legs_fk(self, swing_l=0.0, swing_r=0.0, knee_l=0.0, knee_r=0.0,
                ankle_l=0.0, ankle_r=0.0, splay=2.0, toe_l=0.0, toe_r=0.0):
        for side, sign, sw, kn, an, to in (("L", 1.0, swing_l, knee_l, ankle_l, toe_l),
                                           ("R", -1.0, swing_r, knee_r, ankle_r, toe_r)):
            self.add(f"thigh.{side}", fwd(sw) @ abduct(splay, sign))
            self.add(f"shin.{side}", A(X, kn))
            self.add(f"foot.{side}", A(X, an))
            self.add(f"toe.{side}", A(X, -to))

    def hair(self, sway=0.0, side=0.0, lag=1.0):
        """sway > 0 = ciocche all'indietro; side > 0 = verso il fianco sinistro."""
        self.add("hair_crest", A(X, sway * 0.5))
        self.add("hair_back_01", A(X, sway * 0.4) @ A(Z, side * 0.3))
        self.add("hair_back_02", A(X, sway * 0.85 * lag) @ A(Z, side * 0.6))
        self.add("hair_back_03", A(X, sway * 1.25 * lag) @ A(Z, side * 0.9))
        for sd, sign in SIDES:
            self.add(f"hair_side_01.{sd}", A(X, sway * 0.35) @ abduct(side, sign))
            self.add(f"hair_side_02.{sd}", A(X, sway * 0.8 * lag) @ abduct(side * 1.4, sign))

    def skirt(self, front=0.0, back=0.0, side=0.0, spread=0.0):
        """front/back > 0 = la falda si alza/fluttua verso l'esterno;
        spread > 0 = le falde laterali si aprono."""
        self.add("skirt_front_01", A(X, -front))
        self.add("skirt_front_02", A(X, -front * 1.6))
        self.add("skirt_back_01", A(X, back))
        self.add("skirt_back_02", A(X, back * 1.6))
        for sd, sign in SIDES:
            self.add(f"skirt_01.{sd}", A(X, side * 0.4) @ abduct(spread, sign))
            self.add(f"skirt_02.{sd}", A(X, side * 0.8) @ abduct(spread * 1.5, sign))


# ------------------------------------------------------- applica la posa ----
_prev_q = {}


def _set_rot(pb, q, keep_sign=True):
    if keep_sign:
        prev = _prev_q.get(pb.name)
        if prev is not None and prev.dot(q) < 0.0:
            q = Quaternion((-q.w, -q.x, -q.y, -q.z))
    pb.rotation_quaternion = q
    _prev_q[pb.name] = q.copy()


def _eff_q(name):
    """Rotazione effettiva (mondo) applicata all'osso nella posa corrente."""
    m = arm.pose.bones[name].matrix.to_3x3() @ REST[name].inverted()
    return m.to_quaternion()


def apply_upper(pose, root_loc=(0.0, 0.0, 0.0), root_delta=None, fk_legs=False):
    """Scrive le rotazioni di tutto il corpo tranne le gambe e aggiorna la
    scena, cosi' le teste del femore sono nella posizione vera per l'IK.
    Con `fk_legs=True` risolve anche le gambe in cinematica diretta (Death)."""
    eff = {}
    for name in ALL_BONES:
        if name in LEG_BONES and not fk_legs:
            continue
        parent = PARENT[name]
        base = eff[parent] if parent else Quaternion()
        dq = pose.d.get(name)
        if name == "root" and root_delta is not None:
            dq = root_delta
        eff[name] = (dq @ base) if dq is not None else base.copy()
        m = REST[name]
        if parent:
            q = (m.inverted() @ eff[parent].to_matrix().inverted()
                 @ eff[name].to_matrix() @ m).to_quaternion()
        else:
            q = (m.inverted() @ eff[name].to_matrix() @ m).to_quaternion()
        _set_rot(arm.pose.bones[name], q)
    rp = arm.pose.bones["root"]
    rp.location = REST["root"].inverted() @ Vector(root_loc)
    bpy.context.view_layer.update()


def solve_leg(side, target, foot_pitch=0.0, toe_pitch=0.0):
    """IK a due ossa: posiziona la caviglia su `target` (mondo) con il ginocchio
    in avanti. Ritorna l'errore di reach (0 se il bersaglio e' raggiungibile)."""
    th, sh, ft, to = (f"thigh.{side}", f"shin.{side}", f"foot.{side}", f"toe.{side}")
    pb = arm.pose.bones
    H = pb[th].head.copy()
    A_t = Vector(target)
    d = A_t - H
    dist = d.length
    if dist < 1e-5:
        d = Vector((0.0, 0.0, -1.0))
        dist = 1e-5
    reach = min(dist, L_LEG - 0.004)
    dirv = d.normalized()

    # polo del ginocchio: "avanti" nel frame del bacino (segue la rotazione del
    # corpo: nella Death il corpo e' coricato e le ginocchia guardano in su)
    hips_q = _eff_q("hips")
    pole = hips_q @ Vector((0.0, -1.0, 0.0))
    pole = pole - dirv * pole.dot(dirv)
    if pole.length < 1e-5:
        pole = Vector((0.0, 0.0, 1.0)) - dirv * dirv.z
    pole.normalize()

    a = (L_THIGH * L_THIGH - L_SHIN * L_SHIN + reach * reach) / (2.0 * reach)
    h = math.sqrt(max(L_THIGH * L_THIGH - a * a, 0.0))
    K = H + dirv * a + pole * h
    ankle = H + dirv * reach

    rest_th = (REST_TAIL[th] - REST_HEAD[th]).normalized()
    rest_sh = (REST_TAIL[sh] - REST_HEAD[sh]).normalized()
    q_th = rest_th.rotation_difference((K - H).normalized())
    q_sh = rest_sh.rotation_difference((ankle - K).normalized())
    q_ft = A(X, foot_pitch)
    q_to = A(X, foot_pitch + toe_pitch)

    hips_eff = _eff_q("hips")
    for name, eff_parent, eff_self in ((th, hips_eff, q_th),
                                       (sh, q_th, q_sh),
                                       (ft, q_sh, q_ft),
                                       (to, q_ft, q_to)):
        m = REST[name]
        q = (m.inverted() @ eff_parent.to_matrix().inverted()
             @ eff_self.to_matrix() @ m).to_quaternion()
        _set_rot(arm.pose.bones[name], q)
    bpy.context.view_layer.update()
    return max(0.0, dist - (L_LEG - 0.004))


def mesh_min_z():
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    m = ev.to_mesh()
    z = min(v.co.z for v in m.vertices)
    ev.to_mesh_clear()
    return z


def shift_root(dz):
    if abs(dz) < 1e-9:
        return
    rp = arm.pose.bones["root"]
    rp.location = Vector(rp.location) + REST["root"].inverted() @ Vector((0.0, 0.0, dz))
    bpy.context.view_layer.update()


def new_action(name):
    if arm.animation_data is None:
        arm.animation_data_create()
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    arm.animation_data.action = act
    _prev_q.clear()
    for pb in arm.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    return act


def key_all(frame):
    for pb in arm.pose.bones:
        pb.keyframe_insert("rotation_quaternion", frame=frame)
    arm.pose.bones["root"].keyframe_insert("location", frame=frame)


def all_fcurves(act):
    """Compatibile con le action 'layered' di Blender 4.4+/5.x e con le vecchie."""
    if hasattr(act, "fcurves") and len(getattr(act, "fcurves", [])):
        return list(act.fcurves)
    curves = []
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                curves.extend(cb.fcurves)
    return curves


def polish(act):
    curves = all_fcurves(act)
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
    return len(curves)


def build_frame(frame, pose, feet, root_loc=(0.0, 0.0, 0.0), root_delta=None,
                ground="plant", clearance=0.0, fk_legs=False):
    """Applica la posa, risolve le gambe, appoggia il personaggio e keya tutto.

    `feet`: {side: (target_mondo, pitch_caviglia, pitch punta)}
    `ground`: 'plant' = il punto piu' basso tocca il pavimento,
              'air'   = nessun contatto garantito (solo niente penetrazione),
              'none'  = nessuna correzione.
    """
    apply_upper(pose, root_loc, root_delta, fk_legs=fk_legs)
    for side, (target, pitch, toe) in feet.items():
        solve_leg(side, target, pitch, toe)
    if ground != "none":
        z = mesh_min_z()
        if ground == "plant":
            shift_root(clearance - z)
        elif z < clearance:
            shift_root(clearance - z)
    key_all(frame)


# ================================================================== IDLE ====
N_IDLE = 120
IDLE_FEET_L = (ANKLE_X, 0.010, ANKLE_Z)
IDLE_FEET_R = (-ANKLE_X, -0.010, ANKLE_Z)


def idle_pose(p):
    br = math.sin(TAU * 2.0 * p)                # respiro: 2 cicli
    sw = math.sin(TAU * p)                      # peso L->R->L: 1 ciclo
    lag = math.sin(TAU * p - 0.6)               # testa/capelli in ritardo
    pose = Pose()
    pose.bone("hips", pitch=1.2 + 0.5 * br, roll=1.4 * sw, yaw=1.0 * sw)
    pose.bone("spine_01", pitch=0.8 * br, roll=-0.7 * sw, yaw=-0.7 * sw)
    pose.bone("spine_02", pitch=1.3 * br, roll=-0.6 * sw, yaw=-0.6 * sw)
    pose.bone("chest", pitch=2.0 * br, roll=-1.0 * sw, yaw=-0.8 * sw)
    pose.bone("neck", pitch=-1.0 * br, yaw=1.5 * lag)
    pose.bone("head", pitch=-0.7 * br + 0.6, yaw=3.6 * lag, roll=0.6 * lag)
    for side, ph in (("L", 0.0), ("R", math.pi)):
        pose.arm(side, swing=3.0 + 1.0 * br,
                 adduct=25.0 - 1.5 * br, elbow=11.0 + 2.0 * br,
                 wrist=-4.0, grip=12.0, thumb=5.0)
    pose.hair(sway=1.5 + 1.8 * lag, side=1.0 * lag)
    pose.skirt(front=1.0 * br, back=0.8 * br, side=1.2 * lag, spread=0.8 * lag)
    root = (0.008 * sw, 0.0, 0.0)
    return pose, root


act = new_action("Idle")
for f in range(0, N_IDLE + 1):
    po, ro = idle_pose(f / N_IDLE)
    build_frame(f, po,
                {"L": (IDLE_FEET_L, 0.0, 0.0), "R": (IDLE_FEET_R, 0.0, 0.0)},
                root_loc=ro)
print(f"[anim] Idle: {polish(act)} curve, {N_IDLE} frame (loop)")

# ================================================================== WALK ====
N_WALK = 36
WALK_B = 0.185                      # semi-falcata (m)
WALK_DUTY = 0.62                    # frazione di ciclo in appoggio
WALK_ANKLE = [(0.00, -8.0), (0.08, -3.0), (0.16, 0.0), (0.34, 0.0),
              (0.46, 8.0), (0.56, 20.0), (0.62, 27.0), (0.70, 18.0),
              (0.80, 5.0), (0.90, -3.0)]
WALK_LIFT = 0.085


def leg_cycle(p, B, duty, pitch_knots, lift, x):
    """Bersaglio di caviglia e pitch del piede per una gamba, dato il fase.

    In appoggio la caviglia scorre indietro a velocita' costante (e' l'in-place:
    il root non trasla); in oscillazione torna avanti con un arco che la solleva.
    """
    p = p % 1.0
    pitch = cyclic(p, pitch_knots)
    if p < duty:
        t = p / duty
        y = -B + 2.0 * B * t
        z = ANKLE_Z + max(0.0, -pitch) * 0.0012
    else:
        t = (p - duty) / (1.0 - duty)
        y = B * math.cos(math.pi * t)
        z = ANKLE_Z + lift * math.sin(math.pi * t) ** 0.85
    return (x, y, z), pitch


def walk_root_z(p):
    """Altezza del bacino che lascia la gamba d'appoggio in grado di arrivare a
    terra: e' questo che crea il bob (prima era un numero a caso da 1,6 cm)."""
    cands = []
    for side, off in (("L", 0.0), ("R", 0.5)):
        pp = (p + off) % 1.0
        if pp < WALK_DUTY:
            t = pp / WALK_DUTY
            y = -WALK_B + 2.0 * WALK_B * t
            dy = y - 0.0
            dx = HIP_X - ANKLE_X
            reach = math.sqrt(max(L_STAND ** 2 - dx * dx - dy * dy, 0.25 * L_STAND ** 2))
            cands.append(ANKLE_Z + reach)
    return (min(cands) if cands else HIP_Z) - HIP_Z


def walk_pose(p):
    a = TAU * p
    rl, pl = leg_cycle(p, WALK_B, WALK_DUTY, WALK_ANKLE, WALK_LIFT, ANKLE_X)
    rr, pr = leg_cycle(p + 0.5, WALK_B, WALK_DUTY, WALK_ANKLE, WALK_LIFT, -ANKLE_X)
    # braccia in opposizione: la sinistra segue il piede destro
    sw_l = 21.0 * (-rr[1] / WALK_B)
    sw_r = 21.0 * (-rl[1] / WALK_B)
    pose = Pose()
    pose.bone("hips", pitch=2.6, roll=-4.2 * math.cos(a), yaw=-5.0 * math.cos(a))
    pose.bone("spine_01", pitch=1.0, roll=1.2 * math.cos(a), yaw=1.6 * math.cos(a))
    pose.bone("spine_02", pitch=1.4, roll=1.8 * math.cos(a), yaw=2.8 * math.cos(a))
    pose.bone("chest", pitch=1.8, roll=2.2 * math.cos(a), yaw=4.0 * math.cos(a))
    pose.bone("neck", pitch=-1.6, yaw=0.6 * math.cos(a))
    pose.bone("head", pitch=-2.2, yaw=1.0 * math.cos(a))
    for side, sw in (("L", sw_l), ("R", sw_r)):
        pose.arm(side, swing=sw, adduct=24.0 + 1.5 * math.cos(a + (0 if side == "L" else math.pi)),
                 elbow=16.0 + 14.0 * (0.5 - 0.5 * math.cos(a + (0 if side == "L" else math.pi))),
                 wrist=-4.0, grip=8.0, thumb=3.0)
    # gonna trascinata dalle gambe: la falda davanti sale quando un piede va
    # avanti, quella dietro quando va indietro, le laterali accompagnano il bacino
    front = 1.0 + 5.5 * max(0.0, -min(rl[1], rr[1]) / WALK_B)
    back = 0.8 + 4.5 * max(0.0, max(rl[1], rr[1]) / WALK_B)
    pose.skirt(front=front, back=back, side=1.2 * math.sin(a - 0.5), spread=1.0)
    pose.hair(sway=2.5 + 2.2 * math.cos(a - 0.9), side=1.8 * math.sin(a - 0.6))
    root = (0.010 * math.cos(a), 0.0, walk_root_z(p))
    feet = {"L": (rl, pl, 0.0), "R": (rr, pr, 0.0)}
    return pose, root, feet


act = new_action("Walk")
walk_report = []
for f in range(0, N_WALK + 1):
    po, ro, fe = walk_pose((f % N_WALK) / N_WALK)
    build_frame(f, po, fe, root_loc=ro)
    walk_report.append(round(mesh_min_z(), 5))
print(f"[anim] Walk: {polish(act)} curve, {N_WALK} frame (loop, in place)")

# =================================================================== RUN ====
N_RUN = 24
RUN_B = 0.245
RUN_DUTY = 0.33
RUN_ANKLE = [(0.00, -4.0), (0.08, 2.0), (0.18, 12.0), (0.33, 30.0),
             (0.44, 22.0), (0.60, 4.0), (0.82, -6.0)]
RUN_LIFT = 0.24
# il bacino sale nel volo e scende all'appoggio (2 contatti per ciclo)
RUN_ROOT = [(0.000, -0.062), (0.160, -0.018), (0.330, -0.055),
            (0.415, 0.055), (0.500, -0.062), (0.660, -0.018),
            (0.830, -0.055), (0.915, 0.055)]


def run_pose(p):
    a = TAU * p
    rl, pl = leg_cycle(p, RUN_B, RUN_DUTY, RUN_ANKLE, RUN_LIFT, ANKLE_X - 0.01)
    rr, pr = leg_cycle(p + 0.5, RUN_B, RUN_DUTY, RUN_ANKLE, RUN_LIFT, -ANKLE_X + 0.01)
    root_z = cyclic(p, RUN_ROOT)
    # in volo il piede accompagna il corpo: alza il bersaglio insieme al bacino
    if (p % 1.0) >= RUN_DUTY:
        rl = (rl[0], rl[1], rl[2] + max(0.0, root_z))
    if ((p + 0.5) % 1.0) >= RUN_DUTY:
        rr = (rr[0], rr[1], rr[2] + max(0.0, root_z))
    sw_l = 40.0 * (-rr[1] / RUN_B)
    sw_r = 40.0 * (-rl[1] / RUN_B)
    pose = Pose()
    pose.bone("hips", pitch=7.0, roll=-3.5 * math.cos(a), yaw=-6.0 * math.cos(a))
    pose.bone("spine_01", pitch=4.0, roll=1.2 * math.cos(a), yaw=2.5 * math.cos(a))
    pose.bone("spine_02", pitch=4.0, roll=1.8 * math.cos(a), yaw=4.5 * math.cos(a))
    pose.bone("chest", pitch=5.0, roll=2.2 * math.cos(a), yaw=6.5 * math.cos(a))
    pose.bone("neck", pitch=-11.0, yaw=1.0 * math.cos(a))
    pose.bone("head", pitch=-9.0, yaw=1.2 * math.cos(a))
    for side, sw in (("L", sw_l), ("R", sw_r)):
        ph = a + (0.0 if side == "L" else math.pi)
        pose.arm(side, swing=sw, adduct=23.0, elbow=74.0 + 14.0 * (0.5 - 0.5 * math.cos(ph)),
                 wrist=-6.0, grip=26.0, thumb=10.0, twist_deg=-4.0)
    front = 3.0 + 7.0 * max(0.0, -min(rl[1], rr[1]) / RUN_B)
    back = 4.0 + 7.0 * max(0.0, max(rl[1], rr[1]) / RUN_B)
    pose.skirt(front=front, back=back, side=1.8 * math.sin(a - 0.6), spread=1.4)
    pose.hair(sway=9.0 + 4.0 * math.cos(a - 0.9), side=2.2 * math.sin(a - 0.7), lag=1.25)
    root = (0.006 * math.cos(a), 0.0, root_z)
    feet = {"L": (rl, pl, 0.0), "R": (rr, pr, 0.0)}
    return pose, root, feet


act = new_action("Run")
run_report = []
for f in range(0, N_RUN + 1):
    p = (f % N_RUN) / N_RUN
    po, ro, fe = run_pose(p)
    in_flight = (p % 1.0) >= RUN_DUTY and ((p + 0.5) % 1.0) >= RUN_DUTY
    build_frame(f, po, fe, root_loc=ro, ground="air" if in_flight else "plant")
    run_report.append(round(mesh_min_z(), 5))
print(f"[anim] Run: {polish(act)} curve, {N_RUN} frame (loop, in place, volo)")

# ================================================================== CAST ====
# pose chiave: (frame, specifica). Le caviglie sono in coordinate mondo.
CAST_KEYS = [
    (0, dict(root=(0.0, 0.0), hips=dict(pitch=1.2), spine_01=dict(),
             spine_02=dict(), chest=dict(), neck=dict(), head=dict(pitch=0.6),
             arm=dict(swing=3, adduct=25, elbow=11, wrist=-4, grip=12, thumb=5),
             feet=dict(L=(ANKLE_X, 0.010, ANKLE_Z, 0.0),
                       R=(-ANKLE_X, -0.010, ANKLE_Z, 0.0)),
             hair=dict(sway=1.5), skirt=dict(front=0.5))),
    (12, dict(root=(0.0, -0.010), hips=dict(pitch=10), spine_01=dict(pitch=6),
              spine_02=dict(pitch=7), chest=dict(pitch=10), neck=dict(pitch=-3),
              head=dict(pitch=-2, yaw=2),
              arm=dict(swing=26, adduct=22, elbow=52, wrist=-16, grip=30, thumb=8),
              feet=dict(L=(ANKLE_X, 0.020, ANKLE_Z, 0.0),
                        R=(-ANKLE_X, 0.010, ANKLE_Z, 0.0)),
              hair=dict(sway=-3), skirt=dict(front=-4))),
    (22, dict(root=(0.0, -0.020), hips=dict(pitch=17), spine_01=dict(pitch=9),
              spine_02=dict(pitch=10), chest=dict(pitch=15), neck=dict(pitch=-6),
              head=dict(pitch=-4, yaw=1),
              arm=dict(swing=42, adduct=18, elbow=72, wrist=-24, grip=40, thumb=12),
              feet=dict(L=(ANKLE_X, 0.030, ANKLE_Z, 0.0),
                        R=(-ANKLE_X, 0.020, ANKLE_Z, 0.0)),
              hair=dict(sway=-6), skirt=dict(front=-7))),
    (34, dict(root=(0.0, 0.004), hips=dict(pitch=-5), spine_01=dict(pitch=-5),
              spine_02=dict(pitch=-7), chest=dict(pitch=-11), neck=dict(pitch=5),
              head=dict(pitch=9),
              arm=dict(swing=6, adduct=-38, elbow=24, wrist=-20, grip=-4,
                       thumb=6, lift=8),
              feet=dict(L=(ANKLE_X, 0.020, ANKLE_Z, 0.0),
                        R=(-ANKLE_X, 0.020, ANKLE_Z, 0.0)),
              hair=dict(sway=8), skirt=dict(front=5))),
    (42, dict(root=(0.0, 0.010), hips=dict(pitch=-8), spine_01=dict(pitch=-6),
              spine_02=dict(pitch=-8), chest=dict(pitch=-13), neck=dict(pitch=6),
              head=dict(pitch=11),
              arm=dict(swing=-18, adduct=-44, elbow=20, wrist=-24, grip=4,
                       thumb=8, lift=10),
              feet=dict(L=(ANKLE_X, 0.020, ANKLE_Z, 0.0),
                        R=(-ANKLE_X, 0.030, ANKLE_Z, 0.0)),
              hair=dict(sway=11), skirt=dict(front=7))),
    (46, dict(root=(0.0, -0.020), hips=dict(pitch=2), spine_01=dict(pitch=0),
              spine_02=dict(pitch=0), chest=dict(pitch=-2), neck=dict(pitch=2),
              head=dict(pitch=4),
              arm=dict(swing=24, adduct=-20, elbow=30, wrist=-16, grip=10,
                       thumb=8, lift=4),
              feet=dict(L=(ANKLE_X, 0.020, ANKLE_Z, 0.0),
                        R=(-ANKLE_X, -0.050, 0.185, -6.0)),
              hair=dict(sway=6), skirt=dict(front=4))),
    (52, dict(root=(0.0, -0.055), hips=dict(pitch=13), spine_01=dict(pitch=7),
              spine_02=dict(pitch=9), chest=dict(pitch=14), neck=dict(pitch=-3),
              head=dict(pitch=-2),
              arm=dict(swing=76, adduct=6, elbow=6, wrist=20, grip=-8,
                       thumb=-4, lift=0, twist_deg=-10),
              feet=dict(L=(ANKLE_X, 0.020, ANKLE_Z, 0.0),
                        R=(-ANKLE_X, -0.185, ANKLE_Z, 2.0)),
              hair=dict(sway=-9), skirt=dict(front=-9, back=7))),
    (60, dict(root=(0.0, -0.040), hips=dict(pitch=8), spine_01=dict(pitch=4),
              spine_02=dict(pitch=5), chest=dict(pitch=8), neck=dict(pitch=-1),
              head=dict(pitch=1),
              arm=dict(swing=48, adduct=10, elbow=16, wrist=8, grip=6, thumb=2),
              feet=dict(L=(ANKLE_X, 0.020, ANKLE_Z, 0.0),
                        R=(-ANKLE_X, -0.150, ANKLE_Z, 0.0)),
              hair=dict(sway=-2), skirt=dict(front=-4))),
    (66, dict(root=(0.0, -0.015), hips=dict(pitch=4), spine_01=dict(pitch=2),
              spine_02=dict(pitch=2), chest=dict(pitch=3), neck=dict(),
              head=dict(pitch=0.5),
              arm=dict(swing=18, adduct=20, elbow=16, wrist=-2, grip=10, thumb=4),
              feet=dict(L=(ANKLE_X, 0.010, ANKLE_Z, 0.0),
                        R=(-ANKLE_X, -0.060, 0.175, -5.0)),
              hair=dict(sway=2), skirt=dict(front=-1))),
    (72, dict(root=(0.0, 0.0), hips=dict(pitch=1.2), spine_01=dict(),
              spine_02=dict(), chest=dict(), neck=dict(), head=dict(pitch=0.6),
              arm=dict(swing=3, adduct=25, elbow=11, wrist=-4, grip=12, thumb=5),
              feet=dict(L=(ANKLE_X, 0.010, ANKLE_Z, 0.0),
                        R=(-ANKLE_X, -0.010, ANKLE_Z, 0.0)),
              hair=dict(sway=1.5), skirt=dict(front=0.5))),
]


def blend(a, b, t):
    if isinstance(a, dict):
        return {k: blend(a[k], b[k], t) for k in a}
    if isinstance(a, (tuple, list)):
        return tuple(blend(x, y, t) for x, y in zip(a, b))
    if isinstance(a, (int, float)):
        return a + (b - a) * t
    return b if t >= 0.5 else a


ARM_DEFAULTS = dict(swing=0.0, adduct=22.0, elbow=10.0, wrist=0.0,
                    grip=8.0, thumb=4.0, twist_deg=0.0, lift=0.0)
TORSO_DEFAULTS = {n: dict(pitch=0.0, roll=0.0, yaw=0.0)
                  for n in ("hips", "spine_01", "spine_02", "chest", "neck", "head")}
HAIR_DEFAULTS = dict(sway=0.0, side=0.0, lag=1.0)
SKIRT_DEFAULTS = dict(front=0.0, back=0.0, side=0.0, spread=0.0)
LEGS_DEFAULTS = dict(swing_l=0.0, swing_r=0.0, knee_l=0.0, knee_r=0.0,
                     ankle_l=0.0, ankle_r=0.0, splay=2.0, toe_l=0.0, toe_r=0.0)


def normalise_keys(keys):
    out = []
    for f, k in keys:
        k = dict(k)
        k["arm"] = {**ARM_DEFAULTS, **k.get("arm", {})}
        for n, d in TORSO_DEFAULTS.items():
            k[n] = {**d, **k.get(n, {})}
        k["hair"] = {**HAIR_DEFAULTS, **k.get("hair", {})}
        k["skirt"] = {**SKIRT_DEFAULTS, **k.get("skirt", {})}
        if "legs" in k:
            k["legs"] = {**LEGS_DEFAULTS, **k["legs"]}
        if "feet" in k:
            k["feet"] = {s: tuple(v) for s, v in k["feet"].items()}
        out.append((f, k))
    return out


def sample_keys(keys, frame):
    for i in range(len(keys) - 1):
        f0, k0 = keys[i]
        f1, k1 = keys[i + 1]
        if f0 <= frame <= f1:
            t = smoothstep((frame - f0) / max(f1 - f0, 1))
            return blend(k0, k1, t)
    return keys[-1][1]


CAST_KEYS = normalise_keys(CAST_KEYS)


def cast_pose(spec):
    pose = Pose()
    for name in ("hips", "spine_01", "spine_02", "chest", "neck", "head"):
        pose.bone(name, **spec[name])
    for side in ("L", "R"):
        pose.arm(side, **spec["arm"])
    pose.hair(**spec["hair"])
    pose.skirt(**spec["skirt"])
    feet = {}
    for side in ("L", "R"):
        x, y, z, pitch = spec["feet"][side]
        feet[side] = ((x, y, z), pitch, 0.0)
    return pose, spec["root"], feet


act = new_action("Cast")
for f in range(0, 73):
    po, ro_spec, fe = cast_pose(sample_keys(CAST_KEYS, f))
    build_frame(f, po, fe, root_loc=(ro_spec[0], ro_spec[1], 0.0))
print(f"[anim] Cast: {polish(act)} curve, 72 frame")

# ================================================================= DEATH ====
# Caduta con ginocchia che cedono: il root ruota all'indietro e scende, le
# gambe si piegano (FK, perche' seguono il corpo), il contatto e' misurato.
DEATH_KEYS = [
    (0, dict(root=(0.0, 0.0, 0.0), rot=0.0,
             hips=dict(pitch=1.2), spine_01=dict(), spine_02=dict(), chest=dict(),
             neck=dict(), head=dict(pitch=0.6),
             arm=dict(swing=3, adduct=25, elbow=11, grip=12, wrist=-4),
             feet=dict(L=(ANKLE_X, 0.010, ANKLE_Z, 0.0),
                       R=(-ANKLE_X, -0.010, ANKLE_Z, 0.0)),
             hair=dict(sway=1.5), skirt=dict(front=0.5))),
    # colpo: la testa parte all'indietro, le ginocchia si ammorbidiscono
    (6, dict(root=(0.0, 0.005, -0.010), rot=-4.0,
             hips=dict(pitch=-3), spine_01=dict(pitch=-4), spine_02=dict(pitch=-7),
             chest=dict(pitch=-11), neck=dict(pitch=-7), head=dict(pitch=-15, yaw=4),
             arm=dict(swing=-16, adduct=10, elbow=22, grip=-2, wrist=-12),
             feet=dict(L=(ANKLE_X, 0.015, ANKLE_Z, 0.0),
                       R=(-ANKLE_X, -0.005, ANKLE_Z, 0.0)),
             hair=dict(sway=7), skirt=dict(front=-4, back=3))),
    # le ginocchia cedono: il bacino scende, i piedi restano piantati
    (13, dict(root=(0.0, 0.030, -0.075), rot=-2.0,
              hips=dict(pitch=6), spine_01=dict(pitch=5), spine_02=dict(pitch=7),
              chest=dict(pitch=9), neck=dict(pitch=2), head=dict(pitch=4),
              arm=dict(swing=12, adduct=16, elbow=26, grip=2, wrist=-8),
              feet=dict(L=(ANKLE_X, 0.020, ANKLE_Z, 0.0),
                        R=(-ANKLE_X, 0.000, ANKLE_Z, 0.0)),
              hair=dict(sway=-4), skirt=dict(front=4))),
    # il bacino va indietro e giu': la persona si siede sulle gambe
    (22, dict(root=(0.0, 0.110, -0.185), rot=-2.0,
              hips=dict(pitch=-6), spine_01=dict(pitch=2), spine_02=dict(pitch=4),
              chest=dict(pitch=6), neck=dict(pitch=4), head=dict(pitch=8),
              arm=dict(swing=6, adduct=6, elbow=34, grip=6, wrist=-8),
              feet=dict(L=(ANKLE_X, 0.035, ANKLE_Z, 2.0),
                        R=(-ANKLE_X, 0.015, ANKLE_Z, 0.0)),
              hair=dict(sway=9), skirt=dict(front=6, back=4, spread=3))),
    # il bacino tocca il pavimento, il busto comincia a coricarsi
    (32, dict(root=(0.0, 0.190, -0.305), rot=-6.0,
              hips=dict(pitch=-34), spine_01=dict(pitch=10), spine_02=dict(pitch=14),
              chest=dict(pitch=16), neck=dict(pitch=2), head=dict(pitch=6),
              arm=dict(swing=10, adduct=-2, elbow=40, grip=8, wrist=-6),
              feet=dict(L=(ANKLE_X, 0.060, ANKLE_Z, 4.0),
                        R=(-ANKLE_X, 0.040, ANKLE_Z, 2.0)),
              hair=dict(sway=12), skirt=dict(front=6, back=3, spread=4))),
    # disteso: la schiena si appoggia, le gambe si piegano, le braccia cadono
    (43, dict(root=(0.0, 0.250, -0.355), rot=-4.0,
              hips=dict(pitch=-66), spine_01=dict(pitch=6), spine_02=dict(pitch=8),
              chest=dict(pitch=6), neck=dict(pitch=-2), head=dict(pitch=-4, yaw=-2),
              arm=dict(swing=2, adduct=-10, elbow=26, grip=12, wrist=-2),
              feet=dict(L=(ANKLE_X + 0.02, 0.080, 0.095, 8.0),
                        R=(-ANKLE_X - 0.02, 0.060, 0.090, 6.0)),
              hair=dict(sway=15, side=4), skirt=dict(front=0, back=1, spread=5))),
    (54, dict(root=(0.0, 0.275, -0.365), rot=-1.0,
              hips=dict(pitch=-84), spine_01=dict(pitch=0), spine_02=dict(pitch=1),
              chest=dict(pitch=2), neck=dict(pitch=-3), head=dict(pitch=-6, yaw=-4),
              arm=dict(swing=-4, adduct=-16, elbow=18, grip=10, wrist=0),
              feet=dict(L=(ANKLE_X + 0.02, 0.090, 0.085, 6.0),
                        R=(-ANKLE_X - 0.02, 0.070, 0.080, 4.0)),
              hair=dict(sway=13, side=3), skirt=dict(front=-2, back=0, spread=4))),
    (66, dict(root=(0.0, 0.280, -0.368), rot=-0.6,
              hips=dict(pitch=-86), spine_01=dict(pitch=0), spine_02=dict(pitch=0),
              chest=dict(pitch=1), neck=dict(pitch=-3), head=dict(pitch=-5, yaw=-4),
              arm=dict(swing=-5, adduct=-19, elbow=14, grip=9, wrist=0),
              feet=dict(L=(ANKLE_X + 0.02, 0.095, 0.080, 5.0),
                        R=(-ANKLE_X - 0.02, 0.075, 0.075, 3.0)),
              hair=dict(sway=12, side=3), skirt=dict(front=-3, back=-1, spread=4))),
    (90, dict(root=(0.0, 0.280, -0.368), rot=-0.5,
              hips=dict(pitch=-86.3), spine_01=dict(pitch=0), spine_02=dict(pitch=0),
              chest=dict(pitch=1), neck=dict(pitch=-3), head=dict(pitch=-5, yaw=-4),
              arm=dict(swing=-5.5, adduct=-19.5, elbow=13, grip=9, wrist=0),
              feet=dict(L=(ANKLE_X + 0.02, 0.096, 0.079, 5.0),
                        R=(-ANKLE_X - 0.02, 0.076, 0.074, 3.0)),
              hair=dict(sway=12, side=3), skirt=dict(front=-3, back=-1, spread=4))),
]


DEATH_KEYS = normalise_keys(DEATH_KEYS)


def death_pose(spec):
    pose = Pose()
    for name in ("hips", "spine_01", "spine_02", "chest", "neck", "head"):
        pose.bone(name, **spec[name])
    for side in ("L", "R"):
        pose.arm(side, **spec["arm"])
    pose.hair(**spec["hair"])
    pose.skirt(**spec["skirt"])
    feet = {}
    for side in ("L", "R"):
        x, y, z, pitch = spec["feet"][side]
        feet[side] = ((x, y, z), pitch, 0.0)
    return pose, spec["root"], spec["rot"], feet


act = new_action("Death")
death_report = []
for f in range(0, 91):
    spec = sample_keys(DEATH_KEYS, f)
    po, ro, rot, fe = death_pose(spec)
    root_delta = A(X, -rot)      # il root punta in su: RX(-) ribalta all'indietro
    build_frame(f, po, fe, root_loc=ro, root_delta=root_delta, ground="plant")
    death_report.append(round(mesh_min_z(), 5))
print(f"[anim] Death: {polish(act)} curve, 90 frame (a terra)")

# ============================================================ autoverifica ==
report = {
    "walk_min_z": walk_report,
    "run_min_z": run_report,
    "death_min_z": death_report,
    "idle_min_z": [],
    "cast_min_z": [],
}


def set_action(name, frame=0):
    arm.animation_data.action = bpy.data.actions[name]
    if hasattr(arm.animation_data, 'action_slot') and arm.animation_data.action.slots:
        arm.animation_data.action_slot = arm.animation_data.action.slots[0]
    sc.frame_set(frame)
    bpy.context.view_layer.update()


ok = True

# 1) contatto: la mesh deve toccare il pavimento in ogni frame di Walk e Idle
set_action("Walk")
mins = []
for f in range(0, N_WALK + 1):
    sc.frame_set(f)
    mins.append(mesh_min_z())
report["walk_min_z_check"] = [round(v, 5) for v in mins]
contact_walk = sum(abs(v) < 0.004 for v in mins) / len(mins)
report["walk_contact"] = round(contact_walk, 4)
print(f"[check] Walk: contatto mesh-pavimento {contact_walk:.0%} dei frame "
      f"(z min {min(mins):+.4f} / max {max(mins):+.4f})")
ok &= contact_walk >= 0.99

# 2) Run: appoggio nei frame di stance, volo senza affondare
set_action("Run")
mins = []
for f in range(0, N_RUN + 1):
    sc.frame_set(f)
    mins.append(mesh_min_z())
report["run_min_z_check"] = [round(v, 5) for v in mins]
stance = [mins[f] for f in range(len(mins)) if (f % N_RUN) / N_RUN < RUN_DUTY
          or ((f % N_RUN) / N_RUN + 0.5) % 1.0 < RUN_DUTY]
report["run_stance_contact"] = round(sum(abs(v) < 0.006 for v in stance) / max(len(stance), 1), 4)
report["run_flight_lift"] = round(max(mins), 4)
run_ok = report["run_stance_contact"] >= 0.75 and max(mins) > 0.02 and min(mins) > -0.006
print(f"[check] Run: contatto in appoggio {report['run_stance_contact']:.0%}, "
      f"volo max {max(mins):+.3f} -> {'OK' if run_ok else 'ERR'}")
ok &= run_ok

# 3) Idle e Cast: nessun affossamento
for clip, n in (("Idle", N_IDLE), ("Cast", 72)):
    set_action(clip)
    vals = []
    for f in range(0, n + 1):
        sc.frame_set(f)
        vals.append(mesh_min_z())
    report["idle_min_z" if clip == "Idle" else "cast_min_z"] = [round(v, 5) for v in vals]
    bad = sum(v < -0.004 for v in vals)
    print(f"[check] {clip}: frame sotto il pavimento {bad}/{len(vals)} "
          f"(z min {min(vals):+.4f})")
    ok &= bad == 0

# 4) ginocchio: con la caviglia davanti, il ginocchio sta davanti alla linea
#    anca-caviglia (niente ginocchia rovesce)
arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.rotation_quaternion = (1, 0, 0, 0)
    pb.location = (0, 0, 0)
p = Pose()
apply_upper(p, (0.0, 0.0, 0.0))
solve_leg("L", (ANKLE_X, -0.18, ANKLE_Z), 0.0, 0.0)
hip = arm.pose.bones["thigh.L"].head
knee = arm.pose.bones["shin.L"].head
ankle = arm.pose.bones["foot.L"].head
line_y = hip.y + (ankle.y - hip.y) * ((knee.z - hip.z) / (ankle.z - hip.z))
knee_ok = knee.y < line_y + 1e-4
report["knee_direction_ok"] = bool(knee_ok)
print(f"[check] ginocchio IK: y ginocchio {knee.y:+.3f} vs linea {line_y:+.3f} "
      f"-> {'OK' if knee_ok else 'ERR'}")
ok &= knee_ok

# 5) Cast: al frame della spinta le mani sono davanti al petto
set_action("Cast", 52)
hand_y = min(arm.pose.bones["fingers.L"].head.y, arm.pose.bones["fingers.R"].head.y)
chest_y = arm.pose.bones["chest"].head.y
cast_ok = hand_y < chest_y - 0.18
report["cast_push_forward_ok"] = bool(cast_ok)
report["cast_hand_y"] = round(hand_y, 4)
report["cast_chest_y"] = round(chest_y, 4)
print(f"[check] Cast f52: mani y={hand_y:+.3f} vs petto y={chest_y:+.3f} "
      f"-> {'OK' if cast_ok else 'ERR'}")
ok &= cast_ok

# 6) braccia: in Idle le mani non stanno larghe come in A-pose
set_action("Idle", 30)
hand_x = max(abs(arm.pose.bones["hand.L"].head.x), abs(arm.pose.bones["hand.R"].head.x))
report["idle_hand_x"] = round(hand_x, 4)
arm_ok = hand_x < 0.30
print(f"[check] Idle: mano x={hand_x:.3f} (A-pose sarebbe ~0.44) "
      f"-> {'OK' if arm_ok else 'ERR'}")
ok &= arm_ok

# 7) Death: posa finale appoggiata, testa in basso
set_action("Death", 90)
head_z = arm.pose.bones["head"].tail.z
zmin = mesh_min_z()
death_ok = head_z < 0.30 and abs(zmin) < 0.01
report["death_head_rest_z"] = round(head_z, 4)
report["death_final_min_z"] = round(zmin, 5)
print(f"[check] Death f90: testa z={head_z:.3f}, mesh min z={zmin:+.3f} "
      f"-> {'OK' if death_ok else 'ERR'}")
ok &= death_ok

report["ok"] = bool(ok)
os.makedirs(WORK, exist_ok=True)
json.dump(report, open(REPORT_JSON, "w"), indent=1)
print(f"[anim] autoverifica: {'OK' if ok else 'ERRORI'} -> {REPORT_JSON}")

# --------------------------------------------------------------- setup ------
for pb in arm.pose.bones:
    pb.rotation_quaternion = (1, 0, 0, 0)
    pb.location = (0, 0, 0)
    pb.scale = (1, 1, 1)
arm.animation_data.action = bpy.data.actions["Idle"]
if hasattr(arm.animation_data, 'action_slot') and arm.animation_data.action.slots:
    arm.animation_data.action_slot = arm.animation_data.action.slots[0]
for a in bpy.data.actions:
    a.use_fake_user = True
sc.frame_start = 1
sc.frame_end = 120
print("[anim] azioni:", [a.name for a in bpy.data.actions])
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED stage3.blend")
if not ok:
    raise SystemExit("[anim] autoverifica FALLITA")
