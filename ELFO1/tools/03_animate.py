"""Step 3 - Animazioni.

Ogni rotazione e' espressa in **assi mondo** (X = beccheggio: positivo = in
avanti, Y = rollio, Z = imbardata: positivo = il personaggio gira a destra) e
convertita nello spazio della singola osso:

    Q_locale = M_rest^-1 * R_mondo * M_rest

Cosi' "abbassa il braccio di 15 gradi" vuol dire la stessa cosa per la spalla
sinistra e per la destra, qualunque sia il roll delle ossa. Le pose usano
quaternioni (quello che esportano glTF e FBX) con continuita' di segno tra i
keyframe.

Le cinque clip a 30 fps:

  * `Idle`  120f  loop: respiro (2 cicli), trasferimento di peso, testa che si
                   guarda intorno, ciocche e gonnellone in ritardo
  * `Walk`   36f  loop: passo umano in place, doppio bob, contro-rotazione del
                   busto, braccia in opposizione, falde che seguono
  * `Run`    24f  loop: falcata lunga, busto inclinato in avanti, braccia a 90
                   gradi che pompano, appoggio piu' corto
  * `Cast`   72f  incantesimo: raccolta dell'energia, apertura delle braccia,
                   spinta dei palmi in avanti, rientro
  * `Death`  90f  colpo, ginocchia che cedono, caduta all'indietro sul fianco,
                   assestamento

I cicli sono generati campionando una funzione di fase, quindi il primo e
l'ultimo frame coincidono per costruzione: il loop e' chiuso senza aggiustamenti
a mano.

Output: $ELFO1_WORK/stage3.blend
"""
import bpy
import math
import os
import sys
from mathutils import Euler, Matrix, Vector

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common import WORK
from skeleton import DEFORM

SRC = os.path.join(WORK, "stage2.blend")
OUT = os.path.join(WORK, "stage3.blend")
FPS = 30
TAU = 2.0 * math.pi

bpy.ops.wm.open_mainfile(filepath=SRC)
sc = bpy.context.scene
sc.render.fps = FPS
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm

for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'

REST = {pb.name: pb.bone.matrix_local.to_3x3() for pb in arm.pose.bones}
ALL_BONES = [b.name for b in arm.pose.bones]
SIDES = (("L", 1.0), ("R", -1.0))


def q_world(bone, rx=0.0, ry=0.0, rz=0.0):
    """Rotazione (gradi) attorno agli assi mondo, riportata nello spazio osso."""
    M = REST[bone]
    R = Euler((math.radians(rx), math.radians(ry), math.radians(rz)), 'XYZ').to_matrix()
    return (M.inverted() @ R @ M).to_quaternion()


def loc_world(bone, dx=0.0, dy=0.0, dz=0.0):
    """Traslazione in unita' mondo -> location locale della posa."""
    return REST[bone].inverted() @ Vector((dx, dy, dz))


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


def apply_pose(pose, frame, root_loc=(0.0, 0.0, 0.0)):
    """`pose`: {osso: (rx, ry, rz)} in gradi su assi mondo.

    Ogni frame chiave definisce **tutte** le ossa: nessun canale resta in
    eredita' dalla clip precedente (era il bug classico della v1 di BOSS1).
    """
    for name in ALL_BONES:
        pb = arm.pose.bones[name]
        rx, ry, rz = pose.get(name, (0.0, 0.0, 0.0))
        pb.rotation_quaternion = q_world(name, rx, ry, rz)
        pb.keyframe_insert("rotation_quaternion", frame=frame)
    pb = arm.pose.bones["root"]
    pb.location = loc_world("root", *root_loc)
    pb.keyframe_insert("location", frame=frame)


def drop_to_ground(frame, clearance=0.0):
    """Misura il punto piu' basso della mesh in posa e sposta il root di
    conseguenza: la caduta si appoggia al pavimento senza interruttori a mano.
    """
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    body = next(o for o in bpy.data.objects if o.type == 'MESH')
    ev = body.evaluated_get(dg)
    m = ev.to_mesh()
    zmin = min(v.co.z for v in m.vertices)
    ev.to_mesh_clear()
    pb = arm.pose.bones["root"]
    pb.location = pb.location + loc_world("root", 0.0, 0.0, -zmin + clearance)
    pb.keyframe_insert("location", frame=frame)
    return zmin


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


def arms(pose, pitch=0.0, adduct=14.0, twist=0.0, elbow=8.0, wrist=0.0,
         finger=0.0, thumb=0.0, spread=0.0):
    """Riempie entrambe le braccia.

    adduct > 0 avvicina il braccio al corpo (dalla posa A verso il basso),
    spread > 0 apre il gomito verso l'esterno, finger > 0 chiude la presa.
    """
    for side, sign in SIDES:
        pose[f"clavicle.{side}"] = (pitch * 0.15, 0.0, -sign * spread * 0.12)
        pose[f"upperarm.{side}"] = (pitch, sign * adduct, sign * twist)
        pose[f"forearm.{side}"] = (elbow, 0.0, sign * spread * 0.5)
        pose[f"hand.{side}"] = (wrist, 0.0, 0.0)
        pose[f"fingers.{side}"] = (finger, 0.0, 0.0)
        pose[f"thumb.{side}"] = (thumb, 0.0, sign * thumb * 0.4)
    return pose


def legs(pose, swing_l=0.0, swing_r=0.0, knee_l=0.0, knee_r=0.0,
         ankle_l=0.0, ankle_r=0.0, splay=1.5):
    for side, sign, sw, kn, an in (("L", 1.0, swing_l, knee_l, ankle_l),
                                   ("R", -1.0, swing_r, knee_r, ankle_r)):
        pose[f"thigh.{side}"] = (sw, 0.0, sign * splay)
        pose[f"shin.{side}"] = (-kn, 0.0, 0.0)
        pose[f"foot.{side}"] = (an, 0.0, 0.0)
        pose[f"toe.{side}"] = (max(0.0, an) * 0.5, 0.0, 0.0)
    return pose


def hair(pose, rx=0.0, ry=0.0, rz=0.0, lag=1.0):
    """Ondeggio delle ciocche: ogni segmento amplifica il precedente."""
    pose["hair_crest"] = (rx * 0.6, ry * 0.4, rz * 0.4)
    pose["hair_back_01"] = (rx * 0.5, ry * 0.5, rz * 0.5)
    pose["hair_back_02"] = (rx * 0.9 * lag, ry * 0.8, rz * 0.8)
    pose["hair_back_03"] = (rx * 1.3 * lag, ry * 1.1, rz * 1.0)
    for side, sign in SIDES:
        pose[f"hair_side_01.{side}"] = (rx * 0.5, ry * 0.6, sign * rz * 0.6)
        pose[f"hair_side_02.{side}"] = (rx * 1.0 * lag, ry * 1.0, sign * rz * 0.9)
    return pose


def skirt(pose, front=0.0, back=0.0, side=0.0, twist=0.0):
    pose["skirt_front_01"] = (front, 0.0, twist * 0.5)
    pose["skirt_front_02"] = (front * 1.5, 0.0, twist)
    pose["skirt_back_01"] = (back, 0.0, -twist * 0.5)
    pose["skirt_back_02"] = (back * 1.5, 0.0, -twist)
    for s, sign in SIDES:
        pose[f"skirt_01.{s}"] = (side, sign * side * 0.3, 0.0)
        pose[f"skirt_02.{s}"] = (side * 1.5, sign * side * 0.4, 0.0)
    return pose


# -------------------------------------------------------------------- IDLE --
def idle_pose(p):
    """p in [0,1). Respiro a 2 cicli, peso a 1 ciclo, micro-movimenti testa."""
    br = math.sin(TAU * 2.0 * p)                 # respiro
    sw = math.sin(TAU * p)                       # trasferimento di peso
    sw2 = math.sin(TAU * p - 0.55)
    hl = math.sin(TAU * p - 1.1)
    pose = {}
    pose["hips"] = (0.5 * br, 1.3 * sw, 0.9 * sw)
    pose["spine_01"] = (0.4 * br, -0.5 * sw, -0.4 * sw)
    pose["spine_02"] = (-1.1 * br, -0.4 * sw, -0.5 * sw)
    pose["chest"] = (-1.7 * br, 0.0, 0.6 * sw)
    pose["neck"] = (0.9 * br, 0.0, -0.9 * sw2)
    pose["head"] = (1.0 * br + 0.6, 0.0, -2.2 * sw2)
    arms(pose, pitch=2.0 + 1.2 * br, adduct=13.0, elbow=10.0 + 2.0 * br,
         wrist=-3.0, finger=4.0 + 3.0 * br, thumb=3.0, spread=3.0)
    legs(pose, swing_l=-1.0, swing_r=1.0, knee_l=2.0 + 0.8 * sw, knee_r=2.0 - 0.8 * sw,
         ankle_l=-1.0, ankle_r=1.0, splay=1.2)
    hair(pose, rx=1.2 * hl, ry=2.4 * sw2, rz=1.6 * hl)
    skirt(pose, front=-1.2 * hl, back=1.0 * hl, side=1.2 * sw2, twist=1.4 * sw2)
    root = (0.005 * sw, 0.0, -0.004 * abs(sw) - 0.002 * br)
    return pose, root


N_IDLE, STEP_IDLE = 120, 4
act = new_action("Idle")
for f in range(0, N_IDLE + 1, STEP_IDLE):
    pose, root = idle_pose((f % N_IDLE) / N_IDLE)
    apply_pose(pose, f, root)
n = polish(act)
print(f"[anim] Idle: {n} curve, {N_IDLE} frame (loop)")


# -------------------------------------------------------------------- WALK --
def walk_pose(p):
    """Ciclo di passo: 0 = appoggio sinistro, 0.5 = appoggio destro."""
    a = TAU * p
    bob = -0.016 * abs(math.sin(2 * a)) - 0.004
    lat = 0.010 * math.sin(a)
    # gambe: sinusoide di falcata + ginocchio che si piega solo in oscillazione
    sw_l = -22.0 * math.sin(a)
    sw_r = -22.0 * math.sin(a + math.pi)
    kn_l = 6.0 + 42.0 * max(0.0, math.sin(a + 1.2))
    kn_r = 6.0 + 42.0 * max(0.0, math.sin(a + math.pi + 1.2))
    pose = {}
    pose["hips"] = (1.5, 3.0 * math.sin(a + 0.3), -5.0 * math.sin(a))
    pose["spine_01"] = (0.5, -1.0 * math.sin(a + 0.3), 2.5 * math.sin(a))
    pose["spine_02"] = (1.5, -1.5 * math.sin(a + 0.3), 4.0 * math.sin(a))
    pose["chest"] = (2.0, -1.0 * math.sin(a + 0.3), 5.0 * math.sin(a))
    pose["neck"] = (-1.0, 0.0, -2.0 * math.sin(a))
    pose["head"] = (-2.0, 0.0, -3.0 * math.sin(a) + 1.0)
    # braccia in opposizione alle gambe
    pose["upperarm.L"] = (-26.0 * math.sin(a + math.pi), 13.0, 0.0)
    pose["upperarm.R"] = (-26.0 * math.sin(a), -13.0, 0.0)
    for side, sign, ph in (("L", 1.0, a + math.pi), ("R", -1.0, a)):
        pose[f"clavicle.{side}"] = (0.0, 0.0, -2.0 * math.sin(ph) * sign)
        pose[f"forearm.{side}"] = (14.0 + 10.0 * max(0.0, math.sin(ph)), 0.0, 0.0)
        pose[f"hand.{side}"] = (-4.0, 0.0, 0.0)
        pose[f"fingers.{side}"] = (8.0, 0.0, 0.0)
        pose[f"thumb.{side}"] = (4.0, 0.0, sign * 2.0)
    legs(pose, swing_l=sw_l, swing_r=sw_r, knee_l=kn_l, knee_r=kn_r,
         ankle_l=8.0 * math.sin(a + 0.8) - 4.0, ankle_r=8.0 * math.sin(a + math.pi + 0.8) - 4.0,
         splay=1.6)
    hair(pose, rx=-2.0 + 2.0 * math.sin(2 * a - 0.7), ry=3.0 * math.sin(a - 0.9),
         rz=-2.5 * math.sin(a - 0.9))
    skirt(pose, front=-3.0 - 5.0 * max(0.0, math.sin(a)), back=2.0 + 3.0 * max(0.0, -math.sin(a)),
          side=2.5 * math.sin(a - 0.6), twist=-3.0 * math.sin(a))
    return pose, (lat, 0.0, bob)


N_WALK, STEP_WALK = 36, 3
act = new_action("Walk")
for f in range(0, N_WALK + 1, STEP_WALK):
    pose, root = walk_pose((f % N_WALK) / N_WALK)
    apply_pose(pose, f, root)
n = polish(act)
print(f"[anim] Walk: {n} curve, {N_WALK} frame (loop, in place)")


# --------------------------------------------------------------------- RUN --
def run_pose(p):
    a = TAU * p
    bob = -0.035 * abs(math.sin(2 * a)) + 0.012
    pose = {}
    pose["hips"] = (6.0, 4.0 * math.sin(a + 0.3), -8.0 * math.sin(a))
    pose["spine_01"] = (4.0, -1.5 * math.sin(a + 0.3), 4.0 * math.sin(a))
    pose["spine_02"] = (5.0, -2.0 * math.sin(a + 0.3), 7.0 * math.sin(a))
    pose["chest"] = (6.0, -1.5 * math.sin(a + 0.3), 9.0 * math.sin(a))
    pose["neck"] = (-8.0, 0.0, -3.0 * math.sin(a))
    pose["head"] = (-10.0, 0.0, -4.0 * math.sin(a))
    # braccia piegate a ~90 gradi che pompano
    for side, sign, ph in (("L", 1.0, a + math.pi), ("R", -1.0, a)):
        pose[f"clavicle.{side}"] = (2.0, 0.0, -4.0 * math.sin(ph) * sign)
        pose[f"upperarm.{side}"] = (-45.0 * math.sin(ph) - 6.0, sign * 6.0, sign * -4.0)
        pose[f"forearm.{side}"] = (85.0 + 18.0 * math.sin(ph), 0.0, 0.0)
        pose[f"hand.{side}"] = (-6.0, 0.0, 0.0)
        pose[f"fingers.{side}"] = (28.0, 0.0, 0.0)
        pose[f"thumb.{side}"] = (14.0, 0.0, sign * 6.0)
    sw_l = -40.0 * math.sin(a)
    sw_r = -40.0 * math.sin(a + math.pi)
    kn_l = 12.0 + 78.0 * max(0.0, math.sin(a + 1.35))
    kn_r = 12.0 + 78.0 * max(0.0, math.sin(a + math.pi + 1.35))
    legs(pose, swing_l=sw_l, swing_r=sw_r, knee_l=kn_l, knee_r=kn_r,
         ankle_l=14.0 * math.sin(a + 0.9) - 6.0,
         ankle_r=14.0 * math.sin(a + math.pi + 0.9) - 6.0, splay=1.8)
    hair(pose, rx=-6.0 + 3.0 * math.sin(2 * a - 0.7), ry=4.5 * math.sin(a - 0.9),
         rz=-4.0 * math.sin(a - 0.9), lag=1.25)
    skirt(pose, front=-8.0 - 8.0 * max(0.0, math.sin(a)),
          back=5.0 + 6.0 * max(0.0, -math.sin(a)),
          side=4.0 * math.sin(a - 0.6), twist=-5.0 * math.sin(a))
    return pose, (0.008 * math.sin(a), 0.012, bob)


N_RUN, STEP_RUN = 24, 2
act = new_action("Run")
for f in range(0, N_RUN + 1, STEP_RUN):
    pose, root = run_pose((f % N_RUN) / N_RUN)
    apply_pose(pose, f, root)
n = polish(act)
print(f"[anim] Run: {n} curve, {N_RUN} frame (loop, in place)")


# -------------------------------------------------------------------- CAST --
# 0-16 raccolta (busto chino, mani verso il basso al centro)
# 16-34 apertura (braccia larghe, petto in fuori, testa in alto)
# 34-48 spinta (palmi in avanti, busto in avanti, ginocchia flesse)
# 48-72 rientro all'idle
act = new_action("Cast")
CAST = [
    # frame, pose-builder
    (0, dict(hips=(1.0, 0, 0), spine_02=(0, 0, 0), chest=(0, 0, 0), neck=(0, 0, 0),
             head=(0, 0, 0), arms=dict(pitch=2, adduct=13, elbow=10, finger=6),
             legs=dict(swing_l=-1, swing_r=1, knee_l=3, knee_r=3), root=(0, 0, 0),
             hair=dict(rx=0), skirt=dict(front=0))),
    (16, dict(hips=(12, 0, -4), spine_02=(11, 0, -5), chest=(12, 0, -3), neck=(2, 0, 3),
              head=(4, 0, 4), arms=dict(pitch=34, adduct=22, elbow=68, wrist=-22,
                                        finger=42, thumb=26, spread=-8),
              legs=dict(swing_l=-8, swing_r=-8, knee_l=20, knee_r=20, ankle_l=8, ankle_r=8),
              root=(0, 0.004, -0.030), hair=dict(rx=7), skirt=dict(front=-7))),
    (34, dict(hips=(-5, 0, 2), spine_02=(-7, 0, 3), chest=(-11, 0, 2), neck=(-7, 0, 0),
              head=(-11, 0, 0), arms=dict(pitch=-12, adduct=-16, elbow=18, wrist=-28,
                                          finger=6, thumb=4, spread=18),
              legs=dict(swing_l=-2, swing_r=-2, knee_l=4, knee_r=4, ankle_l=0, ankle_r=0),
              root=(0, -0.006, 0.012), hair=dict(rx=-9), skirt=dict(front=5))),
    (48, dict(hips=(9, 0, 3), spine_02=(10, 0, 4), chest=(13, 0, 6), neck=(1, 0, -2),
              head=(5, 0, -3), arms=dict(pitch=68, adduct=6, elbow=8, wrist=26,
                                         finger=-10, thumb=-8, spread=0),
              legs=dict(swing_l=-10, swing_r=10, knee_l=16, knee_r=6, ankle_l=6, ankle_r=2),
              root=(0, -0.020, -0.012), hair=dict(rx=10), skirt=dict(front=-9))),
    (60, dict(hips=(4, 0, 1), spine_02=(4, 0, 2), chest=(5, 0, 2), neck=(0, 0, 0),
              head=(2, 0, 0), arms=dict(pitch=28, adduct=10, elbow=26, wrist=4,
                                        finger=8, thumb=6, spread=2),
              legs=dict(swing_l=-3, swing_r=3, knee_l=6, knee_r=3, ankle_l=2, ankle_r=1),
              root=(0, -0.006, -0.004), hair=dict(rx=3), skirt=dict(front=-3))),
    (72, dict(hips=(0.5, 0, 0), spine_02=(0, 0, 0), chest=(0, 0, 0), neck=(0, 0, 0),
              head=(0.6, 0, 0), arms=dict(pitch=2, adduct=13, elbow=10, wrist=-3,
                                          finger=6, thumb=3, spread=3),
              legs=dict(swing_l=-1, swing_r=1, knee_l=2, knee_r=2, ankle_l=-1, ankle_r=1),
              root=(0, 0, 0), hair=dict(rx=0), skirt=dict(front=0))),
]
for f, spec in CAST:
    pose = {k: v for k, v in spec.items()
            if k not in ("arms", "legs", "hair", "skirt", "root")}
    arms(pose, **spec["arms"])
    legs(pose, **spec["legs"])
    hair(pose, **spec["hair"])
    skirt(pose, **spec["skirt"])
    apply_pose(pose, f, spec["root"])
n = polish(act)
print(f"[anim] Cast: {n} curve, 72 frame")


# ------------------------------------------------------------------- DEATH --
# 0-10 colpo (testa indietro, petto che si apre), 10-34 gambe che cedono e
# busto che si rovescia, 34-58 caduta all'indietro (root ruotato di -78 gradi
# su X con traslazione calcolata per appoggiare il bacino a terra), 58-90
# assestamento con un piccolo rimbalzo
DEATH = [
    (0, dict(root=(0, 0, 0), rootrot=(0, 0, 0), hips=(0, 0, 0), spine_02=(0, 0, 0),
             chest=(0, 0, 0), neck=(0, 0, 0), head=(0, 0, 0),
             arms=dict(pitch=2, adduct=13, elbow=10, finger=6),
             legs=dict(swing_l=-1, swing_r=1, knee_l=3, knee_r=3), hair=dict(rx=0),
             skirt=dict(front=0))),
    (10, dict(root=(0, 0.030, 0.004), rootrot=(0, 0, 0), hips=(-6, 0, 0),
              spine_02=(-10, 0, 0), chest=(-14, 0, 0), neck=(-12, 0, 0), head=(-18, 0, 6),
              arms=dict(pitch=-26, adduct=-10, elbow=18, finger=-14, thumb=-10, spread=12),
              legs=dict(swing_l=4, swing_r=4, knee_l=8, knee_r=8), hair=dict(rx=-11),
              skirt=dict(front=6))),
    (24, dict(root=(0, 0.060, -0.060), rootrot=(-8, 0, 0), hips=(-10, 0, 4),
              spine_02=(-6, 0, 6), chest=(-2, 0, 8), neck=(4, 0, -4), head=(10, 0, -8),
              arms=dict(pitch=6, adduct=-16, elbow=34, finger=-4, thumb=-2, spread=8),
              legs=dict(swing_l=-26, swing_r=-18, knee_l=52, knee_r=40, ankle_l=16, ankle_r=12),
              hair=dict(rx=-6), skirt=dict(front=-10))),
    (36, dict(root=(0, 0.115, -0.175), rootrot=(-42, 0, 0), hips=(-8, 0, 6),
              spine_02=(2, 0, 8), chest=(6, 0, 10), neck=(8, 0, -6), head=(16, 0, -10),
              arms=dict(pitch=16, adduct=-30, elbow=46, finger=4, thumb=4, spread=14),
              legs=dict(swing_l=-40, swing_r=-28, knee_l=70, knee_r=54, ankle_l=18, ankle_r=14),
              hair=dict(rx=-16), skirt=dict(front=-16))),
    (48, dict(root=(0, 0.180, -0.300), rootrot=(-74, 0, 0), hips=(-4, 0, 4),
              spine_02=(4, 0, 6), chest=(8, 0, 8), neck=(6, 0, -4), head=(12, 0, -12),
              arms=dict(pitch=24, adduct=-38, elbow=54, finger=10, thumb=8, spread=18),
              legs=dict(swing_l=-52, swing_r=-36, knee_l=84, knee_r=64, ankle_l=20, ankle_r=16),
              hair=dict(rx=-24), skirt=dict(front=-20))),
    (58, dict(root=(0, 0.205, -0.345), rootrot=(-84, 0, 0), hips=(0, 0, 2),
              spine_02=(6, 0, 4), chest=(10, 0, 6), neck=(4, 0, -2), head=(8, 0, -14),
              arms=dict(pitch=30, adduct=-44, elbow=58, finger=14, thumb=10, spread=22),
              legs=dict(swing_l=-58, swing_r=-40, knee_l=90, knee_r=68, ankle_l=22, ankle_r=18),
              hair=dict(rx=-28), skirt=dict(front=-24))),
    (68, dict(root=(0, 0.200, -0.330), rootrot=(-80, 0, 0), hips=(2, 0, 1),
              spine_02=(4, 0, 3), chest=(8, 0, 4), neck=(2, 0, -1), head=(4, 0, -15),
              arms=dict(pitch=28, adduct=-46, elbow=54, finger=12, thumb=8, spread=22),
              legs=dict(swing_l=-54, swing_r=-38, knee_l=86, knee_r=66, ankle_l=20, ankle_r=16),
              hair=dict(rx=-24), skirt=dict(front=-22))),
    (90, dict(root=(0, 0.200, -0.334), rootrot=(-82, 0, 0), hips=(1, 0, 1),
              spine_02=(5, 0, 3), chest=(9, 0, 4), neck=(3, 0, -1), head=(6, 0, -15),
              arms=dict(pitch=29, adduct=-45, elbow=56, finger=12, thumb=8, spread=22),
              legs=dict(swing_l=-56, swing_r=-39, knee_l=88, knee_r=67, ankle_l=21, ankle_r=17),
              hair=dict(rx=-26), skirt=dict(front=-23))),
]
act = new_action("Death")
for f, spec in DEATH:
    pose = {k: v for k, v in spec.items()
            if k not in ("arms", "legs", "hair", "skirt", "root", "rootrot")}
    arms(pose, **spec["arms"])
    legs(pose, **spec["legs"])
    hair(pose, **spec["hair"])
    skirt(pose, **spec["skirt"])
    rx, ry, rz = spec["rootrot"]
    pose["root"] = (rx, ry, rz)
    apply_pose(pose, f, spec["root"])
    if f >= 24:                      # da qui in poi il corpo tocca il suolo
        dz = drop_to_ground(f, clearance=0.004)
n = polish(act)
print(f"[anim] Death: {n} curve, 90 frame (appoggiata a terra)")

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
