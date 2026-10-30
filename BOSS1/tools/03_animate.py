"""Step 3 - Animazioni (v2).

La v1 ruotava le ossa in assi locali "alla cieca": il risultato erano pose in
cui il bacino si inclinava di lato e le braccia si attorcigliavano. Qui ogni
rotazione e' espressa in **assi mondo** (X = fianco, Y = profondita', Z = alto)
e convertita nello spazio locale dell'osso:

    Q_locale = M_rest^-1 * R_mondo * M_rest        (M_rest = matrice di riposo)

Cosi' "ruota il braccio di -30 gradi su X" significa sempre "porta la mano
avanti", qualunque sia il roll dell'osso. Le pose usano quaternioni (niente
gimbal lock, ed e' quello che esportano glTF e FBX) con continuita' di segno
tra un keyframe e l'altro.

Set di animazioni (30 fps):

  * `Idle`   120f  loop: respiro, oscillazione del peso, artigli, coda, aureola
  * `Walk`    40f  loop: andatura da knuckle-walker, in place (root motion a
                   carico del motore), doppio bob, contro-rotazione del busto
  * `Roar`    84f  carica, si alza, mascelle aperte, artigli aperti, tremore
  * `Attack`  54f  fendente destro con caricamento, impatto e recupero
  * `Death`   96f  colpo, gambe che cedono, crollo sul fianco, mascella inerte

Output: /home/user/work/stage3.blend
"""
import bpy
import math
import os
import sys
from mathutils import Matrix, Euler

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common import WORK

SRC = os.path.join(WORK, "stage2.blend")
OUT = os.path.join(WORK, "stage3.blend")
FPS = 30

bpy.ops.wm.open_mainfile(filepath=SRC)
sc = bpy.context.scene
sc.render.fps = FPS
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm

for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'

REST = {pb.name: pb.bone.matrix_local.to_3x3() for pb in arm.pose.bones}


def q_world(bone, rx=0.0, ry=0.0, rz=0.0):
    """Rotazione (gradi) attorno agli assi mondo, riportata nello spazio osso."""
    M = REST[bone]
    R = Euler((math.radians(rx), math.radians(ry), math.radians(rz)), 'XYZ').to_matrix()
    return (M.inverted() @ R @ M).to_quaternion()


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
    # Ogni azione deve definire la rotazione di *tutte* le ossa: i canali non
    # keyati in una clip si portano dietro la posa lasciata dalla clip
    # precedente (era il bug della v1: il root ruotato della Death inclinava
    # anche l'Idle).
    for pb in arm.pose.bones:
        pb.keyframe_insert("rotation_quaternion", frame=0)
    return act


def key(bone, frame, rot=None, loc=None):
    """rot = (rx, ry, rz) in gradi su assi mondo; loc in unita' osso."""
    pb = arm.pose.bones[bone]
    if rot is not None:
        pb.rotation_quaternion = q_world(bone, *rot)
        pb.keyframe_insert("rotation_quaternion", frame=frame)
    if loc is not None:
        pb.location = loc
        pb.keyframe_insert("location", frame=frame)


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
    # continuita' quaternioni: per ogni osso, se q(k) . q(k-1) < 0 si nega q(k)
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


SIDES = ("L", "R")

# -------------------------------------------------------------------- IDLE --
act = new_action("Idle")
N = 120
# respiro: petto che si gonfia (X negativo = petto in alto) + spalle
for f, a in ((0, 0.0), (30, -2.4), (60, -0.4), (90, 1.6), (120, 0.0)):
    key("chest", f, rot=(a, 0, 0))
    key("spine", f, rot=(a * 0.6, 0, 0))
    key("neck", f, rot=(-a * 0.5, 0, 0))
# peso che si sposta da un lato all'altro (rollio su Y) + bob verticale
for f, roll, dz in ((0, 0.0, 0.0), (30, 1.8, -0.004), (60, 0.0, 0.0),
                    (90, -1.8, -0.004), (120, 0.0, 0.0)):
    key("root", f, loc=(roll * 0.004, 0, dz))
    key("hips", f, rot=(0, roll, roll * 0.6))
    key("thigh.L", f, rot=(0, -roll * 0.5, 0))
    key("thigh.R", f, rot=(0, -roll * 0.5, 0))
# testa: micro rotazioni + mascella che "respira"
for f, rx, rz, jaw in ((0, 0, 0, 3), (30, -3, 5, 7), (60, 1, 0, 3),
                       (90, -2, -5, 6), (120, 0, 0, 3)):
    key("head", f, rot=(rx, 0, rz))
    key("jaw", f, rot=(jaw, 0, 0))
# aureola: ondeggio lento, sfasato tra base e punta
for f, a in ((0, 0), (40, 3.2), (80, -2.6), (120, 0)):
    key("halo_base", f, rot=(0, a * 0.5, 0))
    key("halo_mid", f, rot=(0, -a, 0))
    key("halo_tip", f, rot=(0, a * 1.6, 0))
# coda: pendolo
for f, a in ((0, 0), (30, -4), (60, 0), (90, 4), (120, 0)):
    key("tail_01", f, rot=(0, 0, a))
    key("tail_02", f, rot=(0, 0, a * 1.8))
# braccia: micro flessione, artigli che si aprono e chiudono
for f, a in ((0, 0), (30, -2.6), (60, 0), (90, 2.0), (120, 0)):
    for s in SIDES:
        key(f"upperarm.{s}", f, rot=(a, 0, 0))
        key(f"forearm.{s}", f, rot=(-a * 1.3, 0, 0))
        key(f"hand.{s}", f, rot=(a * 0.7, 0, 0))
for f, a in ((0, 4), (30, 12), (60, 4), (90, 9), (120, 4)):
    for s in SIDES:
        for c in ("a", "b", "c"):
            key(f"claw_{c}.{s}", f, rot=(a, 0, 0))
# gambe: compensazione del rollio
for f, a in ((0, 0), (30, 1.4), (60, 0), (90, -1.4), (120, 0)):
    for s in SIDES:
        key(f"shin.{s}", f, rot=(-a * 1.5, 0, 0))
        key(f"foot.{s}", f, rot=(a, 0, 0))
n = polish(act)
print(f"[anim] Idle: {n} curve, {N + 1} frame (loop)")

# -------------------------------------------------------------------- WALK --
# ciclo di 40 frame: 0-20 appoggio sinistro, 20-40 appoggio destro.
# Le braccia sono arti portanti: mano sinistra avanti quando la destra e' dietro.
act = new_action("Walk")
CYC = 40
for f, phase in ((0, 0.0), (10, 0.25), (20, 0.5), (30, 0.75), (40, 1.0)):
    # oscillazione verticale: due "pompaggi" per ciclo
    key("root", f, loc=(0.010 * math.sin(phase * 2 * math.pi),
                        0,
                        -0.012 * abs(math.sin(phase * 2 * math.pi)) - 0.004))
    key("hips", f, rot=(2.0, 3.5 * math.sin(phase * 2 * math.pi),
                        6.0 * math.sin(phase * 2 * math.pi)))
    key("spine", f, rot=(-1.5, -1.5 * math.sin(phase * 2 * math.pi), -4.0 * math.sin(phase * 2 * math.pi)))
    key("chest", f, rot=(-2.0, -1.0 * math.sin(phase * 2 * math.pi),
                         5.0 * math.sin(phase * 2 * math.pi)))
    key("neck", f, rot=(1.0, 0, -2.0 * math.sin(phase * 2 * math.pi)))
    key("head", f, rot=(1.5, 0, -3.0 * math.sin(phase * 2 * math.pi)))
    key("jaw", f, rot=(4 + 3 * abs(math.sin(phase * 2 * math.pi)), 0, 0))
    key("tail_01", f, rot=(0, 0, 8 * math.sin(phase * 2 * math.pi)))
    key("tail_02", f, rot=(0, 0, 14 * math.sin(phase * 2 * math.pi + 0.6)))
    key("halo_base", f, rot=(0, 2.0 * math.sin(phase * 2 * math.pi + 0.8), 0))
    key("halo_mid", f, rot=(0, -2.5 * math.sin(phase * 2 * math.pi + 0.8), 0))

# arti: sinistra in fase, destra in opposizione (0.5 di sfasamento)
for side, off in (("L", 0.0), ("R", 0.5)):
    for i in range(5):
        f = 10 * i
        ph = (i * 0.25 + off) % 1.0
        s = math.sin(ph * 2 * math.pi)
        c = math.cos(ph * 2 * math.pi)
        # braccio: avanti (s<0 -> spinta indietro) e sollevamento in volo
        key(f"clavicle.{side}", f, rot=(0, 0, -4.0 * s))
        key(f"upperarm.{side}", f, rot=(-18.0 * s, 0, 2.0 * s))
        key(f"forearm.{side}", f, rot=(12.0 + 10.0 * max(0.0, s), 0, 0))
        key(f"hand.{side}", f, rot=(-8.0 * s - 4.0, 0, 0))
        for cl in ("a", "b", "c"):
            key(f"claw_{cl}.{side}", f, rot=(8.0 - 6.0 * max(0.0, -s), 0, 0))
        # gamba: mezzo ciclo dopo il braccio omologo (andatura a due tempi)
        lg = math.sin((ph + 0.5) % 1.0 * 2 * math.pi)
        key(f"thigh.{side}", f, rot=(-16.0 * lg, 0, 0))
        key(f"shin.{side}", f, rot=(10.0 + 14.0 * max(0.0, -lg), 0, 0))
        key(f"foot.{side}", f, rot=(-6.0 * lg + 4.0, 0, 0))
        key(f"toe.{side}", f, rot=(6.0 * max(0.0, lg), 0, 0))
n = polish(act)
print(f"[anim] Walk: {n} curve, {CYC + 1} frame (loop, in place)")

# -------------------------------------------------------------------- ROAR --
act = new_action("Roar")
# 0-18: si carica (testa bassa, spalle chiuse) / 18-40:esplode / 40-64: tiene
# il ruggito con tremore / 64-84: rientra
key("root", 0, loc=(0, 0, 0))
key("root", 18, loc=(0, 0.010, -0.045))
key("root", 34, loc=(0, -0.015, 0.030))
key("root", 48, loc=(0, -0.015, 0.026))
key("root", 70, loc=(0, 0, 0.004))
key("root", 84, loc=(0, 0, 0))
for f, rx, rz in ((0, 0, 0), (18, 14, 0), (34, -22, 0), (48, -20, 2),
                  (70, -6, 0), (84, 0, 0)):
    key("hips", f, rot=(rx * 0.25, 0, rz * 0.2))
    key("spine", f, rot=(rx * 0.5, 0, rz * 0.5))
    key("chest", f, rot=(rx * 0.9, 0, rz))
for f, rx in ((0, 0), (18, 16), (34, -10), (48, -9), (70, -4), (84, 0)):
    key("neck", f, rot=(rx * 0.55, 0, 0))
    key("head", f, rot=(rx, 0, 0))
# mascella: chiusa in carica, spalancata nel ruggito, tremore, si richiude
for f, jaw in ((0, 2), (18, -6), (28, 46), (40, 40), (46, 44), (52, 38),
               (58, 43), (66, 20), (84, 2)):
    key("jaw", f, rot=(jaw, 0, 0))
# braccia: chiuse -> spalancate e protese
for s in SIDES:
    for f, rx, rz in ((0, 0, 0), (18, 10, 6), (34, -26, -14), (48, -24, -12),
                      (70, -6, -3), (84, 0, 0)):
        key(f"clavicle.{s}", f, rot=(0, 0, rz * 0.4))
        key(f"upperarm.{s}", f, rot=(rx, 0, rz if s == "L" else -rz))
        key(f"forearm.{s}", f, rot=(-rx * 0.7, 0, 0))
        key(f"hand.{s}", f, rot=(rx * 0.3 - 6, 0, 0))
    for f, a in ((0, 4), (18, 2), (34, 26), (48, 22), (70, 8), (84, 4)):
        for c in ("a", "b", "c"):
            key(f"claw_{c}.{s}", f, rot=(a, 0, 0))
    for f, a in ((0, 0), (18, 5), (34, -6), (48, -5), (84, 0)):
        key(f"thigh.{s}", f, rot=(a, 0, 0))
        key(f"shin.{s}", f, rot=(-a * 1.6, 0, 0))
# aureola: si "accende" e vibra
for f, a in ((0, 0), (18, -2), (30, 9), (38, 7), (46, 9), (54, 6), (84, 0)):
    key("halo_base", f, rot=(0, a * 0.4, 0))
    key("halo_mid", f, rot=(0, -a * 0.8, 0))
    key("halo_tip", f, rot=(0, a * 1.5, 0))
for f, a in ((0, 0), (18, 6), (34, -12), (48, -10), (84, 0)):
    key("tail_01", f, rot=(0, 0, a))
    key("tail_02", f, rot=(0, 0, a * 1.5))
n = polish(act)
print(f"[anim] Roar: {n} curve, 84 frame")

# ------------------------------------------------------------------ ATTACK --
act = new_action("Attack")
# 0-14 carica (busto che ruota a sinistra, braccio destro indietro)
# 14-26 fendente (busto che ruota a destra, braccio che spazza in avanti)
# 26-34 impatto/assestamento, 34-54 rientro
for f, z, y, dz in ((0, 0, 0, 0), (14, -20, 0.020, -0.012),
                    (26, 24, -0.045, 0.004), (32, 18, -0.038, -0.004),
                    (42, 8, -0.012, 0), (54, 0, 0, 0)):
    key("root", f, loc=(0, y, dz))
    key("hips", f, rot=(0, 0, z * 0.30))
    key("spine", f, rot=(0, 0, z * 0.55))
    key("chest", f, rot=(2.0, 0, z))
for f, rx, rz in ((0, 0, 0), (14, 6, -12), (26, -10, 18), (32, -6, 14),
                  (42, -2, 5), (54, 0, 0)):
    key("neck", f, rot=(rx * 0.4, 0, rz * 0.5))
    key("head", f, rot=(rx, 0, rz))
for f, jaw in ((0, 3), (12, 16), (22, 34), (30, 20), (54, 3)):
    key("jaw", f, rot=(jaw, 0, 0))

# braccio destro che sferra: spalla indietro -> avanti, gomito che si apre
for f, rx, ry in ((0, 0, 0), (14, 34, 18), (22, -34, -26), (26, -46, -30),
                  (34, -24, -14), (54, 0, 0)):
    key("clavicle.R", f, rot=(0, 0, ry * 0.35))
    key("upperarm.R", f, rot=(rx, ry * 0.3, ry))
    key("forearm.R", f, rot=(max(0.0, -rx) * 0.8 + 10, 0, 0))
    key("hand.R", f, rot=(rx * 0.3 - 8, 0, ry * 0.5))
for f, a in ((0, 6), (14, 24), (22, 4), (28, 30), (34, 18), (54, 6)):
    for c in ("a", "b", "c"):
        key(f"claw_{c}.R", f, rot=(a, 0, 0))
# braccio sinistro: contrappeso (si porta indietro mentre il destro colpisce)
for f, rx, ry in ((0, 0, 0), (14, -18, -12), (26, 26, 20), (34, 14, 10), (54, 0, 0)):
    key("clavicle.L", f, rot=(0, 0, -ry * 0.3))
    key("upperarm.L", f, rot=(rx, 0, -ry))
    key("forearm.L", f, rot=(max(0.0, rx) * 0.6 + 8, 0, 0))
    key("hand.L", f, rot=(-6, 0, 0))
# gambe: piega in carica, spinta in avanti al colpo
for s, sign in (("L", 1), ("R", -1)):
    for f, a in ((0, 0), (14, 8), (26, -10), (34, -5), (54, 0)):
        key(f"thigh.{s}", f, rot=(a, 0, sign * a * 0.4))
        key(f"shin.{s}", f, rot=(-a * 1.6, 0, 0))
        key(f"foot.{s}", f, rot=(a * 0.8, 0, 0))
for f, a in ((0, 0), (14, 10), (26, 24), (34, 16), (54, 0)):
    key("halo_base", f, rot=(0, a * 0.4, 0))
    key("halo_tip", f, rot=(0, -a, 0))
    key("tail_01", f, rot=(0, 0, -a * 0.6))
n = polish(act)
print(f"[anim] Attack: {n} curve, 54 frame")

# ------------------------------------------------------------------- DEATH --
act = new_action("Death")
# 0-12 colpo: testa indietro, petto che si apre
# 12-40 gambe che cedono, corpo che crolla in avanti e a sinistra
# 40-70 impatto al suolo + rimbalzo, 70-96 assestamento finale
# il root ruota di ~75 gradi su Y: il corpo cade su un fianco, con il peso
# che si appoggia a terra (translanamento calcolato per non affondare)
for f, roll, pitch, loc in ((0, 0, 0, (0, 0, 0)),
                            (12, -4, 4, (0, 0.020, -0.010)),
                            (30, 22, 10, (-0.020, -0.010, -0.020)),
                            (44, 62, 14, (-0.045, -0.060, 0.012)),
                            (52, 76, 12, (-0.050, -0.080, 0.006)),
                            (62, 72, 13, (-0.050, -0.078, 0.008)),
                            (96, 73, 13, (-0.050, -0.078, 0.008))):
    key("root", f, rot=(pitch, roll, 0), loc=loc)
# il corpo ruota su se stesso mentre cade (rotazione sul fianco)
for f, rx, ry in ((0, 0, 0), (12, 6, 0), (30, 12, 6), (44, 16, 10),
                  (52, 12, 8), (62, 13, 9), (96, 13, 9)):
    key("hips", f, rot=(rx * 0.5, ry * 0.4, 0))
    key("spine", f, rot=(rx * 0.5, ry * 0.5, 0))
    key("chest", f, rot=(rx * 0.6, ry * 0.4, 0))
for f, rx in ((0, 0), (12, -16), (30, 14), (44, 26), (52, 20), (62, 22), (96, 22)):
    key("neck", f, rot=(rx * 0.5, 0, 0))
    key("head", f, rot=(rx, 0, 0))
for f, jaw in ((0, 2), (10, 26), (30, 30), (46, 38), (56, 30), (96, 26)):
    key("jaw", f, rot=(jaw, 0, 0))
# braccia: si aprono e si trascinano a terra
for s, sign in (("L", 1), ("R", -1)):
    for f, rx, ry in ((0, 0, 0), (12, -10, 0), (30, -28, sign * 12),
                      (44, -54, sign * 26), (56, -48, sign * 24), (96, -50, sign * 25)):
        key(f"upperarm.{s}", f, rot=(rx, 0, ry))
        key(f"forearm.{s}", f, rot=(28 + abs(rx) * 0.3, 0, 0))
        key(f"hand.{s}", f, rot=(-10, 0, 0))
        for cl in ("a", "b", "c"):
            key(f"claw_{cl}.{s}", f, rot=(-6, 0, 0))
    for f, a in ((0, 0), (12, -6), (30, 20), (44, 34), (52, 26), (96, 28)):
        key(f"thigh.{s}", f, rot=(a, 0, sign * a * 0.5))
        key(f"shin.{s}", f, rot=(-a * 1.5, 0, 0))
        key(f"foot.{s}", f, rot=(a * 0.6, 0, 0))
        key(f"toe.{s}", f, rot=(a * 0.4, 0, 0))
# aureola e coda che si afflosciano
for f, a in ((0, 0), (12, -4), (30, 6), (46, 14), (60, 10), (96, 11)):
    key("halo_base", f, rot=(0, a * 0.5, 0))
    key("halo_mid", f, rot=(0, -a, 0))
    key("halo_tip", f, rot=(0, -a * 1.4, 0))
for f, a in ((0, 0), (12, -6), (30, 10), (46, 18), (96, 16)):
    key("tail_01", f, rot=(a, 0, 0))
    key("tail_02", f, rot=(a * 1.3, 0, 0))
n = polish(act)
print(f"[anim] Death: {n} curve, 96 frame")

# ------------------------------------------------------------------- setup --
# posa a riposo prima di salvare (niente valori "avanzati" dalle clip)
for pb in arm.pose.bones:
    pb.rotation_quaternion = (1, 0, 0, 0)
    pb.location = (0, 0, 0)
    pb.scale = (1, 1, 1)
arm.animation_data.action = bpy.data.actions["Idle"]
for a in bpy.data.actions:
    a.use_fake_user = True
sc.frame_start = 1
sc.frame_end = 120
print("[anim] azioni:", [a.name for a in bpy.data.actions])
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED stage3.blend")
