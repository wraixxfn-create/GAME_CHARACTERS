"""Step 3 - Animazioni (riscritte).

La versione precedente aveva due errori sistematici:

1. **Segno delle rotazioni ambiguo.** La convenzione "rx positivo = avanti"
   vale solo per le ossa che puntano in su (spina): per quelle che puntano in
   giu' (gambe, braccia, gonna, capelli) lo stesso segno manda la punta
   *all'indietro*. Risultato: ginocchia che si piegavano in avanti (passo
   dell'oca), braccia del `Cast` che spingevano dietro la schiena, falcata a
   rovescio.
2. **Rotazioni dei genitori non composte.** La conversione mondo->osso usava
   solo la matrice di rest della singola osso (`M_rest^-1 R M_rest`), ignorando
   la posa dei genitori. Appena un antenato ruota molto (il `root` della
   `Death`, -80 gradi), gli angoli "in assi mondo" dei figli non valgono piu':
   le gambe finivano piegate sopra la testa e il corpo restava sospeso in aria.

Qui le pose si definiscono con **angoli anatomici** (avanti/indietro,
flessione, abduzione) convertiti in assi del *character frame* con i segni
giusti per ogni gruppo di ossa, e la conversione nei canali di posa compone
esattamente la catena:

    D_eff(b) = Delta_b @ D_eff(parent)                        (character frame)
    B(b)     = Rest(b)^-1 @ D_eff(parent)^-1 @ D_eff(b) @ Rest(b)

con `parent = None` per il root. Quando i genitori sono a riposo si riduce alla
formula classica; quando ruotano (Death) gli angoli dei figli restano veri.

Le cinque clip a 30 fps (durate invariate rispetto alla v1):

  * `Idle`  120f  loop: respiro (2 cicli), trasferimento di peso, testa che si
                   guarda intorno, braccia rilassate, ciocche e falde in ritardo
  * `Walk`   36f  loop: ciclo del passo umano in place, ginocchia che si
                   piegano all'indietro, heel-toe roll, braccia in opposizione
  * `Run`    24f  loop: falcata lunga, fase di volo, busto in avanti, gomiti ~90
  * `Cast`   72f  incantesimo: raccolta bassa, apertura larga, SPINTA dei palmi
                   in avanti (davvero in avanti), passo, rientro
  * `Death`  90f  colpo, ginocchia che cedono, caduta all'indietro APPOGGIATA
                   al pavimento, assestamento

I cicli campionano funzioni di fase continue: primo e ultimo frame identici
per costruzione. Lo script stampa un report numerico di sanita' (contatti dei
piedi, direzione del ginocchio, grounding della caduta) e lo salva in
`$ELFO1_WORK/anim_report.json` per lo step di QA.

Output: $ELFO1_WORK/stage3.blend
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
bpy.context.view_layer.objects.active = arm
for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'

# --------------------------------------------------------------- catena -----
# rest in armature space (la mesh non e' trasformata: character frame = mondo)
REST = {pb.name: pb.bone.matrix_local.to_3x3().copy() for pb in arm.pose.bones}
PARENT = {b[0]: b[1] for b in BONES}
ALL_BONES = [b[0] for b in BONES]                 # gia' in ordine gerarchico
SIDES = (("L", 1.0), ("R", -1.0))

X = Vector((1.0, 0.0, 0.0))
Y = Vector((0.0, 1.0, 0.0))
Z = Vector((0.0, 0.0, 1.0))


def A(axis, deg):
    """Quaternione: rotazione di `deg` gradi attorno all'asse (char frame)."""
    if abs(deg) < 1e-9:
        return Quaternion()
    return Quaternion(axis, math.radians(deg))


# ---------------------------------------------------- primitive semantiche --
# Ogni primitiva torna un quaternione del character frame. Convenzioni (tutte
# verificate numericamente sulla posa di rest):
#
#   spina/anca/collo/testa (puntano in su, +Z):
#     pitch > 0 = si piega in AVANTI; roll > 0 = fianco sinistro giu';
#     yaw   > 0 = gira a SINISTRA.
#   arti (puntano in giu', -Z):
#     swing > 0 = punta in AVANTI;            raise_ > 0 = abduzione (su);
#     knee  > 0 = FLESSIONE (tallone INDIETRO); elbow > 0 = mano in avanti;
#     pitch caviglia > 0 = punta del piede in giu'; punta > 0 = piega in su.
#   gonna/capelli (puntano in giu'):
#     flap > 0 = la falda va INDIETRO; spread > 0 = si apre di lato.

def sp(pitch=0.0, roll=0.0, yaw=0.0):
    """Spina/anca/collo/testa."""
    return A(Z, yaw) @ A(Y, roll) @ A(X, pitch)


def fwd(deg):
    return A(X, -deg)


def abduct(deg, sign):
    """> 0 solleva lateralmente il segmento (.L verso +X, .R verso -X)."""
    return A(Y, -sign * deg)


def twist(deg, bone, sign=1.0):
    """Rotazione assiale attorno all'osso a riposo."""
    if abs(deg) < 1e-9:
        return Quaternion()
    axis = REST[bone] @ Y
    return Quaternion(axis, math.radians(sign * deg))


# ------------------------------------------------------------ pose builder --
class Pose:
    """Accumula i delta di ogni osso nel character frame."""

    def __init__(self):
        self.d = {}

    def add(self, name, q):
        self.d[name] = (q @ self.d[name]) if name in self.d else q.copy()

    def bone(self, name, pitch=0.0, roll=0.0, yaw=0.0):
        self.add(name, sp(pitch, roll, yaw))

    def arm(self, side, swing=0.0, raise_=-10.0, elbow_deg=8.0, wrist=0.0,
            grip=0.0, thumb=0.0, twist_deg=0.0):
        """Un braccio. raise_ = gradi di abduzione DALLA A-pose (negativo =
        braccio piu' aderente al fianco, positivo = si solleva di lato)."""
        sign = 1.0 if side == "L" else -1.0
        self.add(f"clavicle.{side}", fwd(swing * 0.12) @ abduct(raise_ * 0.08, sign))
        self.add(f"upperarm.{side}", fwd(swing) @ abduct(raise_, sign)
                 @ twist(twist_deg, f"upperarm.{side}", sign))
        self.add(f"forearm.{side}", fwd(elbow_deg) * 0 + A(X, -elbow_deg)
                 @ twist(twist_deg * 0.5, f"forearm.{side}", sign))
        self.add(f"hand.{side}", A(X, wrist))
        self.add(f"fingers.{side}", A(X, grip))
        self.add(f"thumb.{side}", A(Z, sign * thumb * 0.6) @ A(X, thumb * 0.5))

    def arms(self, **kw):
        self.arm("L", **kw)
        self.arm("R", **kw)

    def legs(self, swing_l=0.0, swing_r=0.0, knee_l=0.0, knee_r=0.0,
             ankle_l=0.0, ankle_r=0.0, splay=2.0, toe_l=0.0, toe_r=0.0):
        for side, sign, sw, kn, an, to in (("L", 1.0, swing_l, knee_l, ankle_l, toe_l),
                                           ("R", -1.0, swing_r, knee_r, ankle_r, toe_r)):
            self.add(f"thigh.{side}", fwd(sw) @ abduct(splay, sign))
            self.add(f"shin.{side}", A(X, kn))                   # tallone indietro
            self.add(f"foot.{side}", A(X, an))                   # > 0 punta in giu'
            self.add(f"toe.{side}", A(X, -to))                   # > 0 piega in su

    def hair(self, sway=0.0, side=0.0, lag=1.0):
        """sway > 0 = ciocche all'indietro; side > 0 = verso il fianco sx."""
        self.add("hair_crest", A(X, sway * 0.5))
        self.add("hair_back_01", A(X, sway * 0.4) @ A(Z, side * 0.3))
        self.add("hair_back_02", A(X, sway * 0.85 * lag) @ A(Z, side * 0.6))
        self.add("hair_back_03", A(X, sway * 1.25 * lag) @ A(Z, side * 0.9))
        for sd, sign in SIDES:
            self.add(f"hair_side_01.{sd}", A(X, sway * 0.35) @ abduct(side, sign))
            self.add(f"hair_side_02.{sd}", A(X, sway * 0.8 * lag) @ abduct(side * 1.4, sign))

    def skirt(self, front=0.0, back=0.0, side=0.0, spread=0.0):
        """front/back > 0 = la falda si solleva/fluttua all'infuori;
        spread > 0 = le falde laterali si aprono."""
        self.add("skirt_front_01", A(X, -front))          # davanti: su = tip avanti
        self.add("skirt_front_02", A(X, -front * 1.6))
        self.add("skirt_back_01", A(X, back))             # dietro: su = tip indietro
        self.add("skirt_back_02", A(X, back * 1.6))
        for sd, sign in SIDES:
            self.add(f"skirt_01.{sd}", A(X, side * 0.4) @ abduct(spread, sign))
            self.add(f"skirt_02.{sd}", A(X, side * 0.8) @ abduct(spread * 1.5, sign))


def cyclic(p, knots):
    """Interpolazione cosinusoidale su nodi (fase, valore), periodica in [0,1):
    il loop si chiude liscio per costruzione."""
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


# ------------------------------------------------------------- risoluzione --
def resolve_and_key(pose, frame, root_loc=(0.0, 0.0, 0.0), root_delta=None):
    """Converte i delta del character frame nei canali di posa e keya tutto."""
    eff = {}
    for name in ALL_BONES:
        parent = PARENT[name]
        base = eff[parent] if parent else Quaternion()
        dq = pose.d.get(name)
        if name == "root" and root_delta is not None:
            dq = root_delta
        eff[name] = (dq @ base) if dq is not None else base.copy()
    for name in ALL_BONES:
        pb = arm.pose.bones[name]
        parent = PARENT[name]
        m = REST[name]
        if parent:
            q = (m.inverted() @ eff[parent].to_matrix().inverted()
                 @ eff[name].to_matrix() @ m).to_quaternion()
        else:
            q = (m.inverted() @ eff[name].to_matrix() @ m).to_quaternion()
        # continuita' di segno col frame precedente (niente salti di slerp)
        prev = pb.rotation_quaternion
        if sum(a * b for a, b in zip(prev, q)) < 0:
            q.negate()
        pb.rotation_quaternion = q
        pb.keyframe_insert("rotation_quaternion", frame=frame)
    rp = arm.pose.bones["root"]
    rp.location = REST["root"].inverted() @ Vector(root_loc)
    rp.keyframe_insert("location", frame=frame)


def new_action(name):
    if arm.animation_data is None:
        arm.animation_data_create()
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    arm.animation_data.action = act
    for pb in arm.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    return act


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
    """Bezier auto-clamped + continuita' di segno dei quaternioni."""
    curves = all_fcurves(act)
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
    by_bone = {}
    for fc in curves:
        if "rotation_quaternion" in fc.data_path:
            by_bone.setdefault(fc.data_path, {})[fc.array_index] = fc
    for path, comps in by_bone.items():
        if len(comps) != 4:
            continue
        n = len(comps[0].keyframe_points)
        prev = [comps[i].keyframe_points[0].co[1] for i in range(4)]
        for k in range(1, n):
            cur = [comps[i].keyframe_points[k].co[1] for i in range(4)]
            if sum(a * b for a, b in zip(prev, cur)) < 0:
                for i in range(4):
                    kp = comps[i].keyframe_points[k]
                    kp.co[1] = -kp.co[1]
                    kp.handle_left[1] = -kp.handle_left[1]
                    kp.handle_right[1] = -kp.handle_right[1]
                cur = [-c for c in cur]
            prev = cur
    return len(curves)


def evaluated_zmin():
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    body = next(o for o in bpy.data.objects if o.type == 'MESH')
    ev = body.evaluated_get(dg)
    m = ev.to_mesh()
    zmin = min(v.co.z for v in m.vertices)
    ev.to_mesh_clear()
    return zmin


def drop_to_ground(frame, clearance=0.005):
    """Appoggia la caduta al pavimento misurando il punto piu' basso della mesh
    in posa e abbassando il root di conseguenza (riscrivendo il keyframe)."""
    zmin = evaluated_zmin()
    rp = arm.pose.bones["root"]
    rp.location = Vector(rp.location) + REST["root"].inverted() @ Vector((0.0, 0.0, -zmin + clearance))
    rp.keyframe_insert("location", frame=frame)
    return zmin


def tip(name):
    return tuple(round(v, 4) for v in arm.pose.bones[name].tail)


report = {"foot_contact_walk": [], "foot_contact_run": [],
          "knee_direction_ok": None, "cast_push_forward_ok": None,
          "death_grounded": [], "death_head_rest_z": None}

# -------------------------------------------------------------------- IDLE --
def idle_pose(p):
    br = math.sin(TAU * 2.0 * p)                 # respiro: 2 cicli
    sw = math.sin(TAU * p)                       # peso L->R->L: 1 ciclo
    lag = math.sin(TAU * p - 0.6)                # testa/capelli in ritardo
    pose = Pose()
    pose.bone("hips", pitch=1.0 + 0.6 * br, roll=1.6 * sw, yaw=1.2 * sw)
    pose.bone("spine_01", pitch=0.8 * br, roll=-0.8 * sw, yaw=-0.8 * sw)
    pose.bone("spine_02", pitch=1.4 * br, roll=-0.6 * sw, yaw=-0.6 * sw)
    pose.bone("chest", pitch=2.2 * br, roll=-1.0 * sw, yaw=-0.8 * sw)
    pose.bone("neck", pitch=-1.0 * br, yaw=1.4 * lag)
    pose.bone("head", pitch=-0.8 * br + 0.8, yaw=3.2 * lag, roll=0.6 * lag)
    pose.arms(swing=4.0 + 1.2 * br, raise_=-12.0 + 1.5 * br,
              elbow_deg=12.0 + 2.5 * br, wrist=-4.0, grip=10.0, thumb=6.0)
    pose.legs(swing_l=-1.5, swing_r=1.5, knee_l=3.0 + 1.0 * sw, knee_r=3.0 - 1.0 * sw,
              ankle_l=2.0, ankle_r=0.0, splay=2.0)
    pose.hair(sway=1.5 + 1.8 * lag, side=1.0 * lag)
    pose.skirt(front=1.0 * br, back=0.8 * br, side=1.2 * lag, spread=0.8 * lag)
    root = (0.004 * sw, 0.0, -0.0035 * abs(sw) - 0.002 * (br - 1.0))
    return pose, root


act = new_action("Idle")
N_IDLE, STEP_IDLE = 120, 4
for f in range(0, N_IDLE + 1, STEP_IDLE):
    po, ro = idle_pose((f % N_IDLE) / N_IDLE)
    resolve_and_key(po, f, ro)
print(f"[anim] Idle: {polish(act)} curve, {N_IDLE} frame (loop)")

# -------------------------------------------------------------------- WALK --
WALK_ANKLE = [(0.00, -9.0), (0.14, 4.0), (0.40, 2.0), (0.50, 26.0),
              (0.60, -4.0), (0.85, -8.0)]        # heel strike -> piatto -> spinta
WALK_TOE = [(0.00, 0.0), (0.40, 2.0), (0.50, 22.0), (0.62, 3.0), (0.85, 0.0)]


def walk_pose(p):
    """Ciclo del passo. p=0: appoggio tallone sinistro, p=0.5: appoggio destro."""
    a = TAU * p
    swing_l = 30.0 * math.cos(a)
    swing_r = -30.0 * math.cos(a)
    # ginocchio: quasi esteso all'appoggio, piccolo bump in caricamento,
    # flessione ampia (fino a ~62 gradi) solo in oscillazione
    kn_l = 7.0 + 8.0 * max(0.0, math.sin(2 * a)) + 58.0 * max(0.0, math.sin(a - math.pi)) ** 1.4
    kn_r = 7.0 + 8.0 * max(0.0, math.sin(2 * a + math.pi)) + 58.0 * max(0.0, math.sin(a)) ** 1.4

    pose = Pose()
    pose.bone("hips", pitch=2.5, roll=-4.0 * math.cos(a), yaw=-5.0 * math.cos(a))
    pose.bone("spine_01", pitch=1.0, roll=1.0 * math.cos(a), yaw=1.5 * math.cos(a))
    pose.bone("spine_02", pitch=1.5, roll=1.5 * math.cos(a), yaw=2.5 * math.cos(a))
    pose.bone("chest", pitch=2.0, roll=2.0 * math.cos(a), yaw=3.5 * math.cos(a))
    pose.bone("neck", pitch=-1.5, yaw=0.8 * math.cos(a))
    pose.bone("head", pitch=-2.0, yaw=1.2 * math.cos(a))
    # braccia in OPPOposizione alle gambe
    for side, ph in (("L", a), ("R", a + math.pi)):
        pose.arm(side, swing=-24.0 * math.cos(ph), raise_=-8.0,
                 elbow_deg=14.0 + 15.0 * (0.5 - 0.5 * math.cos(ph)),
                 wrist=-4.0, grip=6.0, thumb=3.0)
    pose.legs(swing_l=swing_l, swing_r=swing_r, knee_l=kn_l, knee_r=kn_r,
              ankle_l=cyclic(p, WALK_ANKLE), ankle_r=cyclic(p + 0.5, WALK_ANKLE),
              toe_l=cyclic(p, WALK_TOE), toe_r=cyclic(p + 0.5, WALK_TOE), splay=1.6)
    pose.hair(sway=3.0 + 2.5 * math.cos(a - 0.8), side=2.0 * math.sin(a - 0.6))
    pose.skirt(front=2.5 + 3.0 * max(0.0, math.cos(a)),
               back=2.0 + 2.5 * max(0.0, -math.cos(a)),
               side=2.0 * math.sin(a - 0.5), spread=1.5)
    bob = -0.016 * (0.5 + 0.5 * math.cos(2 * a))             # giu' ai doppi appoggi
    return pose, (0.0045 * math.cos(a - 0.2), 0.0, bob)


act = new_action("Walk")
N_WALK, STEP_WALK = 36, 3
for f in range(0, N_WALK + 1, STEP_WALK):
    po, ro = walk_pose((f % N_WALK) / N_WALK)
    resolve_and_key(po, f, ro)
print(f"[anim] Walk: {polish(act)} curve, {N_WALK} frame (loop, in place)")

# --------------------------------------------------------------------- RUN --
RUN_ANKLE = [(0.00, -6.0), (0.20, 0.0), (0.42, 30.0), (0.60, -8.0), (0.85, -4.0)]
RUN_TOE = [(0.00, 2.0), (0.30, 6.0), (0.45, 26.0), (0.62, 5.0), (0.85, 2.0)]


def run_pose(p):
    """Corsa: falcata +-36 gradi, ginocchio fino a ~90 in recupero, fase di
    volo (bob positivo a meta' appoggio), busto in avanti, gomiti a ~90 gradi."""
    a = TAU * p
    swing_l = 38.0 * math.cos(a)
    swing_r = -38.0 * math.cos(a)
    kn_l = 18.0 + 9.0 * max(0.0, math.sin(2 * a)) + 80.0 * max(0.0, math.sin(a - math.pi)) ** 1.5
    kn_r = 18.0 + 9.0 * max(0.0, math.sin(2 * a + math.pi)) + 80.0 * max(0.0, math.sin(a)) ** 1.5
    lean = 18.0
    pose = Pose()
    pose.bone("hips", pitch=lean * 0.4, roll=-4.0 * math.cos(a), yaw=-6.0 * math.cos(a))
    pose.bone("spine_01", pitch=lean * 0.25, roll=1.5 * math.cos(a), yaw=2.5 * math.cos(a))
    pose.bone("spine_02", pitch=lean * 0.25, roll=2.0 * math.cos(a), yaw=4.5 * math.cos(a))
    pose.bone("chest", pitch=lean * 0.30, roll=2.5 * math.cos(a), yaw=6.0 * math.cos(a))
    pose.bone("neck", pitch=-lean * 0.75, yaw=1.0 * math.cos(a))
    pose.bone("head", pitch=-lean * 0.55, yaw=1.5 * math.cos(a))
    for side, ph in (("L", a), ("R", a + math.pi)):
        pose.arm(side, swing=-48.0 * math.cos(ph) - 10.0, raise_=2.0,
                 elbow_deg=85.0 + 20.0 * (0.5 - 0.5 * math.cos(ph)),
                 wrist=-6.0, grip=30.0, thumb=12.0)
    pose.legs(swing_l=swing_l, swing_r=swing_r, knee_l=kn_l, knee_r=kn_r,
              ankle_l=cyclic(p, RUN_ANKLE), ankle_r=cyclic(p + 0.5, RUN_ANKLE),
              toe_l=cyclic(p, RUN_TOE), toe_r=cyclic(p + 0.5, RUN_TOE), splay=1.4)
    pose.hair(sway=9.0 + 4.5 * math.cos(a - 0.9), side=2.5 * math.sin(a - 0.7), lag=1.3)
    pose.skirt(front=5.0 + 5.0 * max(0.0, math.cos(a)),
               back=8.0 + 5.0 * max(0.0, -math.cos(a)),
               side=4.0 * math.sin(a - 0.6), spread=2.0)
    bob = -0.004 + 0.018 * (0.5 - 0.5 * math.cos(2 * a - 0.9))   # giu' in appoggio, su in volo
    return pose, (0.003 * math.cos(a), 0.0, bob)


act = new_action("Run")
N_RUN, STEP_RUN = 24, 2
for f in range(0, N_RUN + 1, STEP_RUN):
    po, ro = run_pose((f % N_RUN) / N_RUN)
    resolve_and_key(po, f, ro)
print(f"[anim] Run: {polish(act)} curve, {N_RUN} frame (loop, in place)")

# -------------------------------------------------------------------- CAST --
# 0-14 raccolta (busto chino, mani basse davanti), 14-30 apertura (braccia
# larghe in alto, petto fuori), 30-40 carica indietro, 40-50 SPINTA dei palmi
# in avanti con passo, 50-72 rientro all'idle.
def cast_build(spec):
    p = Pose()
    p.bone("hips", **spec["hips"])
    p.bone("spine_01", **spec["spine_01"])
    p.bone("spine_02", **spec["spine_02"])
    p.bone("chest", **spec["chest"])
    p.bone("neck", **spec["neck"])
    p.bone("head", **spec["head"])
    for side in ("L", "R"):
        p.arm(side, **spec["arm"])
    p.legs(**spec["legs"])
    p.hair(**spec["hair"])
    p.skirt(**spec["skirt"])
    return p


CAST = [
    (0, dict(root=(0, 0, 0),
             hips=dict(pitch=1), spine_01=dict(pitch=0), spine_02=dict(pitch=0),
             chest=dict(pitch=0), neck=dict(pitch=0), head=dict(pitch=1),
             arm=dict(swing=4, raise_=-12, elbow_deg=12, grip=10, wrist=-4),
             legs=dict(swing_l=-1.5, swing_r=1.5, knee_l=3, knee_r=3, ankle_l=2),
             hair=dict(sway=1.5), skirt=dict(front=0))),
    (14, dict(root=(0, 0.010, -0.040),
              hips=dict(pitch=13, yaw=-2), spine_01=dict(pitch=7), spine_02=dict(pitch=8),
              chest=dict(pitch=10), neck=dict(pitch=-4), head=dict(pitch=-2, yaw=3),
              arm=dict(swing=38, raise_=-6, elbow_deg=64, grip=34, wrist=-18, thumb=10),
              legs=dict(swing_l=-6, swing_r=-6, knee_l=22, knee_r=20, ankle_l=6, ankle_r=6),
              hair=dict(sway=-4), skirt=dict(front=-6))),
    (30, dict(root=(0, -0.006, 0.012),
              hips=dict(pitch=-6, yaw=2), spine_01=dict(pitch=-5), spine_02=dict(pitch=-7),
              chest=dict(pitch=-11), neck=dict(pitch=4), head=dict(pitch=8),
              arm=dict(swing=-6, raise_=78, elbow_deg=24, grip=-6, wrist=-28, twist_deg=14),
              legs=dict(swing_l=-2, swing_r=-2, knee_l=4, knee_r=4, ankle_l=-6, ankle_r=-6),
              hair=dict(sway=8), skirt=dict(front=4))),
    (40, dict(root=(0, 0.010, -0.015),
              hips=dict(pitch=-4, yaw=-3), spine_01=dict(pitch=-4), spine_02=dict(pitch=-6),
              chest=dict(pitch=-10), neck=dict(pitch=2), head=dict(pitch=6),
              arm=dict(swing=-48, raise_=14, elbow_deg=48, grip=22, wrist=-12, twist_deg=-8),
              legs=dict(swing_l=4, swing_r=-6, knee_l=10, knee_r=14, ankle_l=0, ankle_r=4),
              hair=dict(sway=10), skirt=dict(front=3))),
    (50, dict(root=(0, -0.045, -0.035),
              hips=dict(pitch=11, yaw=3), spine_01=dict(pitch=6), spine_02=dict(pitch=8),
              chest=dict(pitch=13), neck=dict(pitch=-2), head=dict(pitch=-3),
              arm=dict(swing=70, raise_=10, elbow_deg=10, grip=-8, wrist=26, twist_deg=-12),
              legs=dict(swing_l=14, swing_r=-10, knee_l=18, knee_r=26,
                        ankle_l=10, ankle_r=16, toe_r=14),
              hair=dict(sway=-7), skirt=dict(front=-8, back=6))),
    (62, dict(root=(0, -0.012, -0.008),
              hips=dict(pitch=5, yaw=1), spine_01=dict(pitch=3), spine_02=dict(pitch=4),
              chest=dict(pitch=6), neck=dict(pitch=0), head=dict(pitch=1),
              arm=dict(swing=26, raise_=-4, elbow_deg=22, grip=6, wrist=4),
              legs=dict(swing_l=4, swing_r=-3, knee_l=8, knee_r=6, ankle_l=4, ankle_r=2),
              hair=dict(sway=4), skirt=dict(front=-3))),
    (72, dict(root=(0, 0, 0),
              hips=dict(pitch=1), spine_01=dict(pitch=0), spine_02=dict(pitch=0),
              chest=dict(pitch=0), neck=dict(pitch=0), head=dict(pitch=1),
              arm=dict(swing=4, raise_=-12, elbow_deg=12, grip=10, wrist=-4),
              legs=dict(swing_l=-1.5, swing_r=1.5, knee_l=3, knee_r=3, ankle_l=2),
              hair=dict(sway=1.5), skirt=dict(front=0))),
]

act = new_action("Cast")
for f, spec in CAST:
    resolve_and_key(cast_build(spec), f, spec["root"])
print(f"[anim] Cast: {polish(act)} curve, 72 frame")

# ------------------------------------------------------------------- DEATH --
# 0-10 colpo (testa e petto all'indietro), 10-18 ginocchia che cedono,
# 18-52 caduta all'indietro APPOGGIATA al suolo, 52-90 assestamento.
# Le rotazioni degli arti sono nel character frame (pre-root): la rotazione del
# root compone la caduta senza deformare la posa relativa del corpo.
def death_build(spec):
    p = Pose()
    p.bone("hips", **spec["hips"])
    p.bone("spine_01", **spec["spine_01"])
    p.bone("spine_02", **spec["spine_02"])
    p.bone("chest", **spec["chest"])
    p.bone("neck", **spec["neck"])
    p.bone("head", **spec["head"])
    for side in ("L", "R"):
        p.arm(side, **spec["arm"])
    p.legs(**spec["legs"])
    p.hair(**spec["hair"])
    p.skirt(**spec["skirt"])
    return p


DEATH = [
    (0, dict(root=(0, 0, 0), rootrot=0,
             hips=dict(pitch=1), spine_01=dict(pitch=0), spine_02=dict(pitch=0),
             chest=dict(pitch=0), neck=dict(pitch=0), head=dict(pitch=1),
             arm=dict(swing=4, raise_=-12, elbow_deg=12, grip=10),
             legs=dict(swing_l=-1.5, swing_r=1.5, knee_l=3, knee_r=3, ankle_l=2),
             hair=dict(sway=1.5), skirt=dict(front=0))),
    (10, dict(root=(0, 0.030, 0.005), rootrot=0,
              hips=dict(pitch=-7), spine_01=dict(pitch=-6), spine_02=dict(pitch=-9),
              chest=dict(pitch=-13), neck=dict(pitch=-8), head=dict(pitch=-14, yaw=5),
              arm=dict(swing=-24, raise_=20, elbow_deg=26, grip=-6, wrist=-14),
              legs=dict(swing_l=3, swing_r=3, knee_l=8, knee_r=8, ankle_l=4),
              hair=dict(sway=6), skirt=dict(front=-4, back=4))),
    (18, dict(root=(0, 0.015, -0.020), rootrot=0,
              hips=dict(pitch=9), spine_01=dict(pitch=6), spine_02=dict(pitch=8),
              chest=dict(pitch=11), neck=dict(pitch=3), head=dict(pitch=6),
              arm=dict(swing=16, raise_=-5, elbow_deg=30, grip=6),
              legs=dict(swing_l=-14, swing_r=-10, knee_l=46, knee_r=38, ankle_l=-4, ankle_r=0),
              hair=dict(sway=-6), skirt=dict(front=6))),
    (28, dict(root=(0, 0.070, -0.150), rootrot=28,
              hips=dict(pitch=-6, yaw=3), spine_01=dict(pitch=-2), spine_02=dict(pitch=0),
              chest=dict(pitch=4), neck=dict(pitch=6), head=dict(pitch=12),
              arm=dict(swing=-8, raise_=30, elbow_deg=40, grip=10),
              legs=dict(swing_l=18, swing_r=12, knee_l=64, knee_r=52, ankle_l=6, ankle_r=2),
              hair=dict(sway=10), skirt=dict(front=8, back=6, spread=3))),
    (40, dict(root=(0, 0.150, -0.320), rootrot=62,
              hips=dict(pitch=-4), spine_01=dict(pitch=0), spine_02=dict(pitch=2),
              chest=dict(pitch=5), neck=dict(pitch=3), head=dict(pitch=8),
              arm=dict(swing=4, raise_=6, elbow_deg=30, grip=14),
              legs=dict(swing_l=24, swing_r=16, knee_l=40, knee_r=32, ankle_l=7, ankle_r=4),
              hair=dict(sway=14), skirt=dict(front=6, back=5, spread=5))),
    (52, dict(root=(0, 0.200, -0.400), rootrot=82,
              hips=dict(pitch=0), spine_01=dict(pitch=1), spine_02=dict(pitch=1),
              chest=dict(pitch=2), neck=dict(pitch=0), head=dict(pitch=2, yaw=-3),
              arm=dict(swing=0, raise_=-4, elbow_deg=20, grip=15),
              legs=dict(swing_l=12, swing_r=8, knee_l=14, knee_r=12, ankle_l=0, ankle_r=0),
              hair=dict(sway=16, side=5), skirt=dict(front=-1, back=1, spread=5))),
    (64, dict(root=(0, 0.200, -0.400), rootrot=84,
              hips=dict(pitch=0), spine_01=dict(pitch=0), spine_02=dict(pitch=1),
              chest=dict(pitch=1), neck=dict(pitch=0), head=dict(pitch=1, yaw=-4),
              arm=dict(swing=-6, raise_=-12, elbow_deg=12, grip=12, wrist=0),
              legs=dict(swing_l=6.5, swing_r=5, knee_l=9, knee_r=7.5, ankle_l=-2, ankle_r=-2),
              hair=dict(sway=14, side=4), skirt=dict(front=-2, back=0, spread=4))),
    (90, dict(root=(0, 0.200, -0.405), rootrot=84.5,
              hips=dict(pitch=0), spine_01=dict(pitch=0), spine_02=dict(pitch=1),
              chest=dict(pitch=1), neck=dict(pitch=0), head=dict(pitch=1, yaw=-4),
              arm=dict(swing=-7, raise_=-13, elbow_deg=12, grip=11, wrist=0),
              legs=dict(swing_l=6, swing_r=4.5, knee_l=8, knee_r=7, ankle_l=-2.5, ankle_r=-2.5),
              hair=dict(sway=14, side=4), skirt=dict(front=-3, back=0, spread=4))),
]

act = new_action("Death")
for f, spec in DEATH:
    root_delta = A(X, -spec["rootrot"])     # il root punta in su: RX(-) ribalta all'indietro
    resolve_and_key(death_build(spec), f, spec["root"], root_delta=root_delta)
    if f >= 28:                             # da qui il corpo tocca il suolo
        zmin = drop_to_ground(f, clearance=0.005)
        report["death_grounded"].append((f, round(zmin, 5)))
print(f"[anim] Death: {polish(act)} curve, 90 frame (appoggiata a terra)")

# ------------------------------------------------------------ autoverifica --
def check_pose_sanity():
    ok = True

    def set_action(name):
        arm.animation_data.action = bpy.data.actions[name]
        if hasattr(arm.animation_data, 'action_slot') and arm.animation_data.action.slots:
            arm.animation_data.action_slot = arm.animation_data.action.slots[0]

    # 1) direzione del ginocchio: flessione 45 -> il tallone va INDIETRO
    scratch = new_action("__sanity__")
    tp = Pose()
    tp.legs(swing_l=20, knee_l=45)
    resolve_and_key(tp, 0)
    bpy.context.view_layer.update()
    knee_y = arm.pose.bones["shin.L"].head.y
    heel_y = arm.pose.bones["toe.L"].head.y
    good = heel_y > knee_y - 0.05
    report["knee_direction_ok"] = bool(good)
    print(f"[check] ginocchio 45: punta piede y={heel_y:+.3f} vs ginocchio y={knee_y:+.3f} "
          f"-> {'OK' if good else 'ERR'}")
    ok &= good
    bpy.data.actions.remove(scratch)
    for pb in arm.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)

    # 2) contatto dei piedi: si misura la PUNTA del piede (il vero punto di
    #    contatto, non la caviglia). Nel walk ogni frame ha un piede a terra,
    #    nel run almeno la meta' (c'e' la fase di volo).
    for clip, n, key, thresh, quota in (("Walk", N_WALK, "foot_contact_walk", 0.055, 1.0),
                                        ("Run", N_RUN, "foot_contact_run", 0.060, 0.5)):
        set_action(clip)
        nfr = 12
        vals = []
        for i in range(nfr):
            sc.frame_set(int(i * n / (nfr - 1)))
            bpy.context.view_layer.update()
            vals.append(min(arm.pose.bones["toe.L"].tail.z, arm.pose.bones["toe.R"].tail.z,
                            arm.pose.bones["foot.L"].tail.z, arm.pose.bones["foot.R"].tail.z))
        report[key] = [round(v, 4) for v in vals]
        inside = sum(v < thresh for v in vals) / len(vals)
        good = inside >= quota
        print(f"[check] {clip}: frame con un piede a terra: {inside:.0%} "
              f"(soglia {thresh}) -> {'OK' if good else 'ERR'}")
        ok &= good

    # 3) cast: al frame 50 la mano spinge DAVANTI al petto
    set_action("Cast")
    sc.frame_set(50)
    bpy.context.view_layer.update()
    hand_y = min(arm.pose.bones["fingers.L"].head.y, arm.pose.bones["fingers.R"].head.y)
    chest_y = arm.pose.bones["chest"].head.y
    good = hand_y < chest_y - 0.20
    report["cast_push_forward_ok"] = bool(good)
    print(f"[check] Cast f50: mani y={hand_y:+.3f} vs petto y={chest_y:+.3f} "
          f"-> {'OK' if good else 'ERR'}")
    ok &= good

    # 4) death: a riposo la testa e' bassa e la mesh appoggia a terra
    set_action("Death")
    sc.frame_set(90)
    bpy.context.view_layer.update()
    head_z = arm.pose.bones["head"].tail.z
    zmin = evaluated_zmin()
    report["death_head_rest_z"] = round(head_z, 4)
    good = head_z < 0.22 and abs(zmin) < 0.03
    print(f"[check] Death f90: testa z={head_z:.3f}, mesh min z={zmin:+.3f} "
          f"-> {'OK' if good else 'ERR'}")
    ok &= good

    set_action("Idle")
    sc.frame_set(0)
    return ok


ok = check_pose_sanity()
os.makedirs(WORK, exist_ok=True)
json.dump(report, open(REPORT_JSON, "w"), indent=1)
print(f"[anim] autoverifica: {'OK' if ok else 'ERRORI'} -> {REPORT_JSON}")

# ------------------------------------------------------------------- setup --
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
