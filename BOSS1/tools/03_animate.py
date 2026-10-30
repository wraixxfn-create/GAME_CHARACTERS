"""Step 3 - Animazioni.

Crea tre azioni sul rig, tutte pensate per un boss da videogioco:
  * Idle    - 120 frame, loop perfetto (respiro, oscillazione del peso, artigli)
  * Roar    - 72 frame, ruggito/aggro (carica, apertura mascelle, aureola che fiammeggia)
  * Attack  - 60 frame, fendente con l'artiglio destro

Le azioni sono marcate con fake user cosi' non si perdono nel salvataggio e
vengono esportate tutte da glTF (animation mode = Actions).

Output: /home/user/work/stage3.blend
"""
import bpy
import math
import os
import sys
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
    pb.rotation_mode = 'XYZ'


def key(bone, frame, rot=None, loc=None, scale=None):
    """Inserisce keyframe di rotazione (gradi) / posizione / scala."""
    pb = arm.pose.bones[bone]
    if rot is not None:
        pb.rotation_euler = [math.radians(a) for a in rot]
        pb.keyframe_insert("rotation_euler", frame=frame)
    if loc is not None:
        pb.location = loc
        pb.keyframe_insert("location", frame=frame)
    if scale is not None:
        pb.scale = scale
        pb.keyframe_insert("scale", frame=frame)


def new_action(name):
    if arm.animation_data is None:
        arm.animation_data_create()
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    arm.animation_data.action = act
    # azzera la posa
    for pb in arm.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    return act


def all_fcurves(act):
    """Compatibile con le action 'layered' di Blender 4.4+/5.x e con le vecchie."""
    if hasattr(act, "fcurves"):
        return list(act.fcurves)
    curves = []
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                curves.extend(cb.fcurves)
    return curves


def smooth(act, interp='BEZIER'):
    for fc in all_fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = interp
            kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
    return len(all_fcurves(act))


# ------------------------------------------------------------------- IDLE ---
act = new_action("Idle")
N = 120
# respiro: petto e spina dorsale
for f, a in ((0, 0), (30, 2.2), (60, 0), (90, -1.4), (120, 0)):
    key("chest", f, rot=(a, 0, 0))
    key("spine", f, rot=(a * 0.7, 0, 0))
# oscillazione del peso (root/hips)
for f, y in ((0, 0), (30, 0.012), (60, 0), (90, -0.012), (120, 0)):
    key("root", f, loc=(y * 0.4, 0, -abs(y) * 0.5))
    key("hips", f, rot=(0, 0, y * 160))
# testa: micro rotazioni e mascella che "respira"
for f, rx, rz, jaw in ((0, 0, 0, 2), (30, -3, 4, 5), (60, 1, 0, 2),
                       (90, -2, -4, 4), (120, 0, 0, 2)):
    key("head", f, rot=(rx, 0, rz))
    key("neck", f, rot=(rx * 0.4, 0, rz * 0.5))
    key("jaw", f, rot=(-jaw, 0, 0))
# aureola: ondeggio lento
for f, a in ((0, 0), (40, 3), (80, -2.5), (120, 0)):
    key("halo_mid", f, rot=(0, a, 0))
    key("halo_tip", f, rot=(0, a * 1.4, 0))
# braccia: micro flessione e artigli che si stringono
for f, a in ((0, 0), (30, 2.5), (60, 0), (90, -2), (120, 0)):
    for s in ("L", "R"):
        key(f"upperarm.{s}", f, rot=(a, 0, 0))
        key(f"forearm.{s}", f, rot=(-a * 1.6, 0, 0))
        key(f"hand.{s}", f, rot=(a * 0.8, 0, 0))
for f, a in ((0, 0), (30, -6), (60, 0), (90, -4), (120, 0)):
    for s in ("L", "R"):
        for c in ("a", "b", "c"):
            key(f"claw_{c}.{s}", f, rot=(-a * 0.5, 0, 0))
# gambe: micro compensazione
for f, a in ((0, 0), (30, 1.5), (60, 0), (90, -1.2), (120, 0)):
    for s in ("L", "R"):
        key(f"thigh.{s}", f, rot=(a, 0, 0))
        key(f"shin.{s}", f, rot=(-a, 0, 0))
n = smooth(act)
print(f"[anim] Idle: {n} curve, {N} frame")

# ------------------------------------------------------------------- ROAR ---
act = new_action("Roar")
# 0 carica (si abbassa, testa giu') -> 22 ruggito (testa su, bocca aperta)
key("root", 0, loc=(0, 0, 0)); key("root", 16, loc=(0, 0, -0.05)); key("root", 30, loc=(0, 0, 0.02)); key("root", 72, loc=(0, 0, 0))
for f, rx in ((0, 0), (16, 12), (30, -14), (50, -10), (72, 0)):
    key("chest", f, rot=(rx, 0, 0))
    key("spine", f, rot=(rx * 0.7, 0, 0))
    key("hips", f, rot=(rx * 0.3, 0, 0))
for f, rx in ((0, 0), (16, 22), (30, -26), (50, -18), (72, 0)):
    key("head", f, rot=(rx, 0, 0))
    key("neck", f, rot=(rx * 0.5, 0, 0))
for f, jaw in ((0, -3), (16, -8), (26, -48), (52, -42), (72, -3)):
    key("jaw", f, rot=(jaw, 0, 0))
for f, a in ((0, 0), (16, -6), (30, 10), (50, 6), (72, 0)):
    for s, sign in (("L", 1), ("R", -1)):
        key(f"upperarm.{s}", f, rot=(a, 0, sign * -a * 0.8))
        key(f"forearm.{s}", f, rot=(-a * 1.2, 0, 0))
for f, a in ((0, 0), (16, -14), (30, 18), (50, 10), (72, 0)):
    for s in ("L", "R"):
        for c in ("a", "b", "c"):
            key(f"claw_{c}.{s}", f, rot=(a * 0.6, 0, 0))
for f, a in ((0, 0), (16, 0), (30, 7), (50, 4), (72, 0)):
    key("halo_mid", f, rot=(0, a, 0))
    key("halo_tip", f, rot=(0, a * 2, 0))
for f, a in ((0, 0), (16, 4), (30, -4), (72, 0)):
    for s in ("L", "R"):
        key(f"thigh.{s}", f, rot=(a, 0, 0))
        key(f"shin.{s}", f, rot=(-a * 1.5, 0, 0))
n = smooth(act)
print(f"[anim] Roar: {n} curve")

# ----------------------------------------------------------------- ATTACK ---
act = new_action("Attack")
# 0 neutro -> 12 arretra il braccio destro -> 26 colpo in avanti/incrociato -> 60 rientro
key("root", 0, loc=(0, 0, 0))
key("root", 12, loc=(0, 0.03, 0.01))
key("root", 26, loc=(0, -0.05, -0.01))
key("root", 60, loc=(0, 0, 0))
for f, rz in ((0, 0), (12, -14), (26, 16), (40, 6), (60, 0)):
    key("chest", f, rot=(0, 0, rz))
    key("spine", f, rot=(0, 0, rz * 0.6))
    key("hips", f, rot=(0, 0, rz * 0.35))
for f, rx, rz in ((0, 0, 0), (12, 8, -16), (26, -6, 14), (40, 2, 6), (60, 0, 0)):
    key("head", f, rot=(rx, 0, rz))
    key("neck", f, rot=(rx * 0.5, 0, rz * 0.5))
for f, jaw in ((0, -2), (12, -6), (22, -26), (34, -10), (60, -2)):
    key("jaw", f, rot=(jaw, 0, 0))
# braccio destro che sferra
for f, rx, rz in ((0, 0, 0), (12, -34, -18), (26, 26, 22), (40, 8, 6), (60, 0, 0)):
    key("upperarm.R", f, rot=(rx, 0, rz))
    key("forearm.R", f, rot=(-rx * 0.9, 0, -rz * 0.5))
    key("hand.R", f, rot=(rx * 0.4, 0, rz * 0.6))
# braccio sinistro: controbilanciamento
for f, rx, rz in ((0, 0, 0), (12, 12, 8), (26, -14, -12), (40, -4, -4), (60, 0, 0)):
    key("upperarm.L", f, rot=(rx, 0, rz))
    key("forearm.L", f, rot=(-rx * 0.8, 0, 0))
for f, a in ((0, 0), (10, -18), (24, 14), (40, 4), (60, 0)):
    for c in ("a", "b", "c"):
        key(f"claw_{c}.R", f, rot=(a, 0, 0))
for f, a in ((0, 0), (12, 3), (26, -4), (60, 0)):
    for s in ("L", "R"):
        key(f"thigh.{s}", f, rot=(a, 0, 0))
        key(f"shin.{s}", f, rot=(-a * 1.4, 0, 0))
n = smooth(act)
print(f"[anim] Attack: {n} curve")

# NLA: tutte le azioni in tracce separate, cosi' restano visibili e esportabili
arm.animation_data.action = bpy.data.actions["Idle"]
for a in bpy.data.actions:
    a.use_fake_user = True

sc.frame_start = 1
sc.frame_end = 120
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED stage3.blend", [a.name for a in bpy.data.actions])
