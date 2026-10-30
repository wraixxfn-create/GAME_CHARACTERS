"""Step 6 - Render di presentazione (facoltativo).

Genera in BOSS1/preview/:
  * hero_roar.png    - posa del ruggito, luce da boss fight
  * hero_idle.png    - vista frontale con rim light freddo
  * turnaround.png   - 4 viste (fronte/fianco/retro/fianco) affiancate

Uso:  python3 06_preview.py [file.blend] [cartella_output]
"""
import bpy
import math
import mathutils
import os
import sys

BLEND = sys.argv[1] if len(sys.argv) > 1 else \
    "/home/user/GAME_CHARACTERS/BOSS1/BOSS1.blend"
OUTDIR = sys.argv[2] if len(sys.argv) > 2 else \
    "/home/user/GAME_CHARACTERS/BOSS1/preview"
os.makedirs(OUTDIR, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
CENTER = mathutils.Vector((0, -0.02, 0.45))


def cleanup():
    for o in list(bpy.data.objects):
        if o.type in {'CAMERA', 'LIGHT'}:
            bpy.data.objects.remove(o, do_unlink=True)


def world(color):
    w = sc.world or bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (*color, 1)


def lights(mult=1.0):
    cfg = [("Key", (1.5, -2.0, 1.6), 150, 1.4, (1.00, 0.95, 0.88)),
           ("Fill", (-2.3, -1.4, 0.5), 26, 2.0, (0.45, 0.62, 1.00)),
           ("Rim", (-0.7, 2.2, 1.5), 260, 1.1, (0.62, 0.74, 1.00)),
           ("Under", (0.2, -0.6, -0.4), 12, 1.0, (1.00, 0.45, 0.20))]
    for name, loc, energy, size, col in cfg:
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy * mult
        ld.size = size
        ld.color = col
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = CENTER + mathutils.Vector(loc)
        lo.rotation_euler = (CENTER - lo.location).to_track_quat('-Z', 'Y').to_euler()


def camera(loc, lens=70):
    camd = bpy.data.cameras.new("Cam")
    camd.lens = lens
    cam = bpy.data.objects.new("Cam", camd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = CENTER + mathutils.Vector(loc)
    cam.rotation_euler = (CENTER - cam.location).to_track_quat('-Z', 'Y').to_euler()
    return cam


def pose(action, frame):
    arm.animation_data.action = bpy.data.actions[action]
    if hasattr(arm.animation_data, 'action_slot') and \
            arm.animation_data.action.slots:
        arm.animation_data.action_slot = arm.animation_data.action.slots[0]
    sc.frame_set(frame)


def render(path, res=1000, samples=96, aspect=1.0):
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x = res
    sc.render.resolution_y = int(res * aspect)
    sc.view_settings.view_transform = 'AgX'
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("RENDER", path)


# 1) hero: ruggito
cleanup(); world((0.008, 0.010, 0.014)); lights(1.0)
camera((-1.25, -1.85, 0.62))
pose("BOSS1_Roar", 34)
render(os.path.join(OUTDIR, "hero_roar.png"), 1100, 110)

# 2) hero: idle, controluce freddo
cleanup(); world((0.008, 0.010, 0.014)); lights(0.85)
camera((1.35, -1.75, 0.75))
pose("BOSS1_Idle", 30)
render(os.path.join(OUTDIR, "hero_idle.png"), 1100, 110)

# 3) turnaround 4 viste
cleanup(); world((0.02, 0.022, 0.028)); lights(0.9)
pose("BOSS1_Idle", 1)
paths = []
for name, ang in (("front", 0), ("left", 90), ("back", 180), ("right", 270)):
    a = math.radians(ang)
    camera((math.sin(a) * 2.45, -math.cos(a) * 2.45, 0.18), 52)
    p = os.path.join("/tmp", f"turn_{name}.png")
    render(p, 560, 40, aspect=1.26)
    paths.append(p)

try:
    from PIL import Image
    ims = [Image.open(p) for p in paths]
    W = sum(i.width for i in ims)
    H = max(i.height for i in ims)
    sheet = Image.new("RGB", (W, H))
    x = 0
    for i in ims:
        sheet.paste(i, (x, 0))
        x += i.width
    sheet.save(os.path.join(OUTDIR, "turnaround.png"))
    print("SHEET", os.path.join(OUTDIR, "turnaround.png"))
    for p in paths:
        os.remove(p)
except ImportError:
    print("PIL non disponibile: turnaround non affiancato")
