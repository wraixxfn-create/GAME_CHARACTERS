"""Step 6 - Render di presentazione (v2).

Genera in `BOSS1/preview/`:

  * `hero_roar.png`    - posa del ruggito, luce da boss fight (3/4 fronte)
  * `hero_idle.png`    - tre quarti posteriore, rim light freddo
  * `hero_head.png`    - primo piano: si vede la densita' extra su testa e
                         aureola ottenuta con la decimation adattiva
  * `turnaround.png`   - 4 viste affiancate (fronte / lato / retro / lato)
  * `anim_idle.gif`, `anim_walk.gif`, `anim_roar.gif`, `anim_attack.gif`,
    `anim_death.gif`

Uso:  python3 06_preview.py [file.blend] [cartella_output] [--gif|--no-gif]
"""
import bpy
import math
import mathutils
import os
import sys
import numpy as np

args = [a for a in sys.argv[1:] if not a.startswith("--")]
BLEND = args[0] if len(args) > 0 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "BOSS1.blend")
OUTDIR = args[1] if len(args) > 1 else os.path.dirname(BLEND) + "/preview"
DO_GIF = "--no-gif" not in sys.argv
DO_STILLS = "--gif-only" not in sys.argv
TURN_ONLY = "--turnaround-only" in sys.argv
os.makedirs(OUTDIR, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
ob = next(o for o in bpy.data.objects if o.type == 'MESH')

# --------------------------------------------------------------- scenario ----
for o in list(bpy.data.objects):
    if o.type in {'CAMERA', 'LIGHT'} or o.name.startswith("ground"):
        bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
ground = bpy.context.object
ground.name = "ground"
gm = bpy.data.materials.new("Ground")
gm.use_nodes = True
p = gm.node_tree.nodes["Principled BSDF"]
p.inputs["Base Color"].default_value = (0.028, 0.030, 0.034, 1)
p.inputs["Roughness"].default_value = 0.62
ground.data.materials.append(gm)


def world(color=(0.010, 0.012, 0.016)):
    w = sc.world or bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (*color, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0


def clear_lights():
    for o in list(bpy.data.objects):
        if o.type == 'LIGHT':
            bpy.data.objects.remove(o, do_unlink=True)


def lights(center, scale=1.0, mult=1.0):
    """Key calda, fill freddo, rim posteriore, luce dal basso rosso brace."""
    s = scale
    cfg = [("Key", (1.6, -2.2, 1.9), 780, 3.4, (1.00, 0.94, 0.86)),
           ("Fill", (-2.6, -1.9, 0.9), 240, 4.2, (0.42, 0.60, 1.00)),
           ("Rim", (-0.6, 2.4, 1.7), 1150, 2.4, (0.55, 0.72, 1.00)),
           ("Bounce", (0.0, -0.9, -0.6), 80, 1.8, (1.00, 0.36, 0.12))]
    for name, D, energy, size, col in cfg:
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy * s * s * mult
        ld.size = size * s
        ld.color = col
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = center + mathutils.Vector(D) * s
        lo.rotation_euler = (center - lo.location).to_track_quat('-Z', 'Y').to_euler()


def bbox():
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    m = ev.to_mesh()
    c = np.empty(len(m.vertices) * 3)
    m.vertices.foreach_get("co", c)
    c = c.reshape(-1, 3)
    mn, mx = c.min(0), c.max(0)
    ev.to_mesh_clear()
    return mathutils.Vector((mn + mx) / 2), mathutils.Vector(mx - mn)


def camera(center, size, azimuth=30.0, elevation=0.30, zoom=1.0, lens=70):
    camd = bpy.data.cameras.new("Cam")
    camd.lens = lens
    cam = bpy.data.objects.new("Cam", camd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    a = math.radians(azimuth)
    dist = max(size) * 2.75 / zoom
    cam.location = center + mathutils.Vector(
        (math.sin(a) * dist * 0.62, -math.cos(a) * dist, size[2] * elevation))
    target = center + mathutils.Vector((0, 0, size[2] * 0.02))
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    for o in list(bpy.data.objects):
        if o.type == 'CAMERA' and o is not cam:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    return cam


def pose(action, frame):
    if action:
        arm.animation_data.action = bpy.data.actions[action]
        if hasattr(arm.animation_data, 'action_slot') and arm.animation_data.action.slots:
            arm.animation_data.action_slot = arm.animation_data.action.slots[0]
    sc.frame_set(frame)


def render(path, res=900, aspect=1.0, samples=64):
    bpy.context.view_layer.update()
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 5
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.render.resolution_x = res
    sc.render.resolution_y = int(res * aspect)
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = path
    bpy.context.view_layer.update()
    bpy.ops.render.render(write_still=True)
    print("RENDER", path)


# ------------------------------------------------------------ still images --
def render_turnaround():
    pose("BOSS1_Idle", 1)
    c, s = bbox()
    world((0.016, 0.018, 0.024))
    ground.hide_render = True      # fondo pulito: e' una tavola di viste
    clear_lights()
    for name, D, energy, lsize, col in (
            ("Key", (1.4, -2.0, 1.6), 760, 3.4, (1.00, 0.95, 0.88)),
            ("Fill", (-2.4, -1.8, 0.9), 300, 4.2, (0.45, 0.62, 1.00)),
            ("Top", (0.0, 0.4, 3.0), 420, 3.0, (0.80, 0.84, 1.00))):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = lsize
        ld.color = col
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = c + mathutils.Vector(D)
        lo.rotation_euler = (c - lo.location).to_track_quat('-Z', 'Y').to_euler()
    dist = max(s) * 2.75
    paths = []
    for name, ang in (("front", 0), ("left", 90), ("back", 180), ("right", 270)):
        a = math.radians(ang)
        camd = bpy.data.cameras.new("Cam"); camd.lens = 60
        cam = bpy.data.objects.new("Cam", camd); sc.collection.objects.link(cam)
        sc.camera = cam
        cam.location = c + mathutils.Vector((math.sin(a) * dist, -math.cos(a) * dist,
                                             s.z * 0.10))
        cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
        for o in list(bpy.data.objects):
            if o.type == 'CAMERA' and o is not cam:
                bpy.data.objects.remove(o, do_unlink=True)
        bpy.context.view_layer.update()
        pth = os.path.join("/tmp", f"turn_{name}.png")
        render(pth, 520, 1.30, 40)
        paths.append(pth)
    from PIL import Image
    ims = [Image.open(x) for x in paths]
    W = sum(i.width for i in ims)
    H = max(i.height for i in ims)
    sheet = Image.new("RGB", (W, H), (12, 13, 16))
    x = 0
    for im in ims:
        sheet.paste(im, (x, 0))
        x += im.width
    sheet.save(os.path.join(OUTDIR, "turnaround.png"))
    print("SHEET", os.path.join(OUTDIR, "turnaround.png"))
    for x in paths:
        os.remove(x)
    ground.hide_render = False


def render_stills():
    # 1) hero: ruggito, 3/4 fronte
    pose("BOSS1_Roar", 34)
    c, s = bbox()
    world(); clear_lights(); lights(c, 1.0, 1.0)
    camera(c, s, azimuth=-35, elevation=0.10, zoom=0.95)
    render(os.path.join(OUTDIR, "hero_roar.png"), 1000, 1.0, 96)

    # 2) hero: idle, tre quarti posteriore con rim light freddo
    pose("BOSS1_Idle", 30)
    c, s = bbox()
    world((0.008, 0.010, 0.015)); clear_lights(); lights(c, 1.0, 0.8)
    camera(c, s, azimuth=30, elevation=0.14, zoom=0.95)
    render(os.path.join(OUTDIR, "hero_idle.png"), 1000, 1.0, 96)

    # 3) primo piano: si vede la densita' extra su testa, aureola e artigli
    pose("BOSS1_Roar", 30)
    c, s = bbox()
    head = c + mathutils.Vector((0.0, -s.y * 0.34, s.z * 0.26))
    world((0.008, 0.010, 0.014)); clear_lights(); lights(head, 0.55, 1.15)
    camd = bpy.data.cameras.new("Cam"); camd.lens = 85
    cam = bpy.data.objects.new("Cam", camd); sc.collection.objects.link(cam); sc.camera = cam
    cam.location = head + mathutils.Vector((0.75, -2.15, -0.30))
    cam.rotation_euler = (head - cam.location).to_track_quat('-Z', 'Y').to_euler()
    for o in list(bpy.data.objects):
        if o.type == 'CAMERA' and o is not cam:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    render(os.path.join(OUTDIR, "hero_head.png"), 950, 1.0, 96)

    # 4) turnaround (inquadratura fissa, 4 viste)
    render_turnaround()


# ------------------------------------------------------------------- GIF -----
# (nome, azione, passo dei frame)  - tutte a 30 fps
CLIPS = [("idle", "BOSS1_Idle", 5),
         ("walk", "BOSS1_Walk", 3),
         ("roar", "BOSS1_Roar", 4),
         ("attack", "BOSS1_Attack", 3),
         ("death", "BOSS1_Death", 4)]


def render_gifs():
    from PIL import Image
    for name, action, step in CLIPS:
        act = bpy.data.actions[action]
        f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
        frames = list(range(f0, f1 + 1, step))
        pose(action, f0)
        c, s = bbox()
        world((0.010, 0.012, 0.016)); clear_lights(); lights(c, 1.0, 0.95)
        camera(c, s, azimuth=32, elevation=0.20, zoom=1.0, lens=62)
        tmp = []
        for i, f in enumerate(frames):
            pose(action, f)
            pth = os.path.join("/tmp", f"gif_{name}_{i:03d}.png")
            render(pth, 360, 0.86, 24)
            tmp.append(pth)
        ims = [Image.open(x).convert("RGB") for x in tmp]
        out = os.path.join(OUTDIR, f"anim_{name}.gif")
        ims[0].save(out, save_all=True, append_images=ims[1:],
                    duration=int(1000 * step / 30), loop=0, optimize=True)
        print("GIF", out, len(ims), "frame")
        for x in tmp:
            os.remove(x)


if TURN_ONLY:
    render_turnaround()
elif DO_STILLS:
    render_stills()
if DO_GIF and not TURN_ONLY:
    render_gifs()

print("[preview] fatto")
