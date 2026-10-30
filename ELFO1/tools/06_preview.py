"""Step 6 - Render di presentazione.

Genera in `ELFO1/preview/`:

  * `hero_cast.png`     - posa dell'incantesimo, luce fredda + rim caldo
  * `hero_idle.png`     - tre quarti, rune accese
  * `hero_head.png`     - primo piano: viso, orecchie a punta, rune
  * `turnaround.png`    - 4 viste affiancate su fondo neutro
  * `detail_compare.png`- sorgente 339k contro LOD0 55k, stesso primo piano
  * `anim_*.gif`        - idle, walk, run, cast, death a 30 fps

Nei render la normale viene ribaltata sulle facce posteriori (nodo
`Geometry/Backfacing`): il gonnellone e le ciocche sono fogli aperti e senza
questo accorgimento la fodera interna si vedrebbe nera. E' una modifica **solo
di anteprima**: il materiale esportato resta glTF-safe.

Uso:  python3 06_preview.py [file.blend] [cartella_output] [--no-gif|--gif-only|--stills-only]
"""
import bpy
import math
import mathutils
import os
import sys
import numpy as np

args = [a for a in sys.argv[1:] if not a.startswith("--")]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND = args[0] if len(args) > 0 else os.path.join(HERE, "ELFO1.blend")
OUTDIR = args[1] if len(args) > 1 else os.path.join(HERE, "preview")
DO_GIF = "--no-gif" not in sys.argv and "--stills-only" not in sys.argv
DO_STILLS = "--gif-only" not in sys.argv
ONLY_TURN = "--turnaround-only" in sys.argv
ONLY_HEAD = "--head-only" in sys.argv
os.makedirs(OUTDIR, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
ob = next(o for o in bpy.data.objects if o.type == 'MESH')
S = ob.dimensions.z / 1.0            # modello gia' in metri


# ------------------------------------------------- normale double-sided ------
# NOTA: qui *non* si ribalta la normale sulle facce posteriori. Cycles lo fa
# gia' da solo quando la faccia e' vista da dietro; farlo una seconda volta
# mandava la normale dentro il materiale e la fodera interna del gonnellone
# diventava nera (le "macchie" nere della v2). Il materiale e' double-sided
# per il motore, ma nei render non serve nessun nodo extra.

# --------------------------------------------------------------- scenario ----
for o in list(bpy.data.objects):
    if o.type in {'CAMERA', 'LIGHT'} or o.name.startswith("ground"):
        bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
ground = bpy.context.object
ground.name = "ground"
gm = bpy.data.materials.new("Ground")
gm.use_nodes = True
p = gm.node_tree.nodes["Principled BSDF"]
p.inputs["Base Color"].default_value = (0.022, 0.024, 0.028, 1)
p.inputs["Roughness"].default_value = 0.55
ground.data.materials.append(gm)


def world(color=(0.010, 0.012, 0.018)):
    w = sc.world or bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (*color, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0


def clear_lights():
    for o in list(bpy.data.objects):
        if o.type == 'LIGHT':
            bpy.data.objects.remove(o, do_unlink=True)


def add_light(name, loc, energy, size, color, target):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.size = size
    ld.color = color
    lo = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = (mathutils.Vector(target) - lo.location).to_track_quat('-Z', 'Y').to_euler()
    return lo


def lights(center, mult=1.0, warm=1.0):
    """Chiave calda frontale, fill freddo, rim lunare dietro, rim basso ambra."""
    s = max(S, 0.5)
    cfg = [("Key", (1.7, -2.4, 1.9), 250 * mult, 2.6, (1.00, 0.93, 0.84)),
           ("Fill", (-2.6, -1.9, 1.0), 95 * mult, 3.6, (0.42, 0.58, 1.00)),
           ("Rim", (-0.7, 2.6, 1.9), 460 * mult, 1.8, (0.55, 0.75, 1.00)),
           ("Bounce", (0.2, -1.1, -0.4), 45 * warm, 1.8, (1.00, 0.42, 0.14))]
    for name, D, energy, size, col in cfg:
        add_light(name, mathutils.Vector(center) + mathutils.Vector(D) * s,
                  energy * s * s, size * s, col, center)


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


def camera(center, size, azimuth=32.0, elevation=0.28, zoom=1.0, lens=72,
           res=(1000, 1000), margin=1.12):
    """Inquadra il soggetto **per intero** a prescindere dal formato.

    La versione precedente calcolava la distanza da `max(size)` senza tenere
    conto del rapporto d'aspetto: con i GIF 340x265 il campo verticale era piu'
    stretto e la testa e i piedi finivano fuori quadro. Qui si usa la sfera che
    contiene il soggetto e il FOV *piu' stretto* fra orizzontale e verticale.
    """
    camd = bpy.data.cameras.new("Cam")
    camd.lens = lens
    camd.sensor_fit = 'AUTO'
    camd.sensor_width = 36.0
    cam = bpy.data.objects.new("Cam", camd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    aspect = res[0] / res[1]
    if aspect >= 1.0:
        fov_x = 2 * math.atan(36.0 / (2 * lens))
        fov_y = 2 * math.atan((36.0 / aspect) / (2 * lens))
    else:
        fov_y = 2 * math.atan(36.0 / (2 * lens))
        fov_x = 2 * math.atan((36.0 * aspect) / (2 * lens))
    radius = 0.5 * math.sqrt(size.x ** 2 + size.y ** 2 + size.z ** 2)
    dist = radius / math.tan(min(fov_x, fov_y) / 2) * margin / zoom
    a = math.radians(azimuth)
    elev = max(0.0, elevation)
    target = center
    cam.location = target + mathutils.Vector(
        (math.sin(a) * dist * 0.86, -math.cos(a) * dist,
         dist * 0.16 * elev))
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


def render(path, res=900, aspect=1.0, samples=72):
    bpy.context.view_layer.update()
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 6
    sc.render.resolution_x = res
    sc.render.resolution_y = int(res * aspect)
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    sc.view_settings.exposure = -0.15
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = path
    bpy.context.view_layer.update()
    bpy.ops.render.render(write_still=True)
    print("RENDER", path)


# ------------------------------------------------------------ still images ---
def render_stills():
    # 1) incantesimo, 3/4
    pose("ELFO1_Cast", 49)
    c, s = bbox()
    world((0.010, 0.013, 0.020))
    clear_lights()
    lights(c, 1.0)
    camera(c, s, azimuth=-38, elevation=0.12, zoom=0.94, res=(1000, 1000))
    render(os.path.join(OUTDIR, "hero_cast.png"), 1000, 1.0, 96)

    # 2) idle, tre quarti con rim freddo
    pose("ELFO1_Idle", 30)
    c, s = bbox()
    world((0.008, 0.010, 0.016))
    clear_lights()
    lights(c, 0.85)
    camera(c, s, azimuth=34, elevation=0.13, zoom=0.94, res=(1000, 1000))
    render(os.path.join(OUTDIR, "hero_idle.png"), 1000, 1.0, 96)

    # 3) primo piano del viso: inquadratura agganciata all'osso della testa
    pose("ELFO1_Idle", 30)
    c, s = bbox()
    pb = arm.pose.bones["head"]
    head = arm.matrix_world @ (pb.head + (pb.tail - pb.head) * 0.55)
    world((0.008, 0.010, 0.015))
    ground.hide_render = True              # niente linea d'orizzonte dietro il collo
    clear_lights()
    for name, D, energy, size, col in (
            ("Key", (0.42, -0.75, 0.30), 26, 0.55, (1.00, 0.92, 0.82)),
            ("Fill", (-0.60, -0.55, 0.05), 9, 0.85, (0.45, 0.60, 1.00)),
            ("Rim", (-0.25, 0.70, 0.40), 22, 0.45, (0.60, 0.78, 1.00))):
        add_light(name, head + mathutils.Vector(D) * S, energy, size * S, col, head)
    camd = bpy.data.cameras.new("Cam")
    camd.lens = 105
    cam = bpy.data.objects.new("Cam", camd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = head + mathutils.Vector((0.62, -1.28, 0.02))
    cam.rotation_euler = (head - cam.location).to_track_quat('-Z', 'Y').to_euler()
    for o in list(bpy.data.objects):
        if o.type == 'CAMERA' and o is not cam:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    render(os.path.join(OUTDIR, "hero_head.png"), 950, 1.0, 110)
    ground.hide_render = False


def render_head_only():
    """Solo il ritratto: utile per ritoccare l'inquadratura senza rifare tutto."""
    pose("ELFO1_Idle", 30)
    c, s = bbox()
    pb = arm.pose.bones["head"]
    head = arm.matrix_world @ (pb.head + (pb.tail - pb.head) * 0.55)
    world((0.008, 0.010, 0.015))
    ground.hide_render = True              # niente linea d'orizzonte dietro il collo
    clear_lights()
    for name, D, energy, size, col in (
            ("Key", (0.42, -0.75, 0.30), 26, 0.55, (1.00, 0.92, 0.82)),
            ("Fill", (-0.60, -0.55, 0.05), 9, 0.85, (0.45, 0.60, 1.00)),
            ("Rim", (-0.25, 0.70, 0.40), 22, 0.45, (0.60, 0.78, 1.00))):
        add_light(name, head + mathutils.Vector(D) * S, energy, size * S, col, head)
    camd = bpy.data.cameras.new("Cam")
    camd.lens = 105
    cam = bpy.data.objects.new("Cam", camd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = head + mathutils.Vector((0.62, -1.28, 0.02))
    cam.rotation_euler = (head - cam.location).to_track_quat('-Z', 'Y').to_euler()
    for o in list(bpy.data.objects):
        if o.type == 'CAMERA' and o is not cam:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    render(os.path.join(OUTDIR, "hero_head.png"), 950, 1.0, 110)
    ground.hide_render = False


def render_turnaround():
    pose("ELFO1_Idle", 1)
    c, s = bbox()
    world((0.016, 0.018, 0.024))
    ground.hide_render = True
    clear_lights()
    for name, D, energy, size, col in (
            ("Key", (1.5, -2.1, 1.7), 300, 2.6, (1.00, 0.95, 0.88)),
            ("Fill", (-2.4, -1.8, 0.9), 120, 3.6, (0.45, 0.62, 1.00)),
            ("Top", (0.0, 0.4, 3.2), 180, 3.0, (0.80, 0.84, 1.00))):
        add_light(name, c + mathutils.Vector(D) * max(S, 0.5), energy * max(S, 0.5) ** 2,
                  size, col, c)
    dist = max(s) * 2.4
    paths = []
    for name, ang in (("front", 0), ("left", 90), ("back", 180), ("right", 270)):
        a = math.radians(ang)
        # le luci girano con la camera: altrimenti nelle viste da dietro il
        # personaggio resta controluce e il gonnellone diventa un blocco nero
        clear_lights()
        ca, sa = math.cos(a), math.sin(a)
        for lname, D, energy, size, col in (
                ("Key", (1.5, -2.1, 1.7), 300, 2.6, (1.00, 0.95, 0.88)),
                ("Fill", (-2.4, -1.8, 0.9), 120, 3.6, (0.45, 0.62, 1.00)),
                ("Top", (0.0, 0.4, 3.2), 180, 3.0, (0.80, 0.84, 1.00))):
            Dr = (D[0] * ca - D[1] * sa, D[0] * sa + D[1] * ca, D[2])
            add_light(lname, c + mathutils.Vector(Dr) * max(S, 0.5),
                      energy * max(S, 0.5) ** 2, size, col, c)
        camd = bpy.data.cameras.new("Cam")
        camd.lens = 62
        cam = bpy.data.objects.new("Cam", camd)
        sc.collection.objects.link(cam)
        sc.camera = cam
        cam.location = c + mathutils.Vector((math.sin(a) * dist, -math.cos(a) * dist,
                                             s.z * 0.10))
        cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
        for o in list(bpy.data.objects):
            if o.type == 'CAMERA' and o is not cam:
                bpy.data.objects.remove(o, do_unlink=True)
        bpy.context.view_layer.update()
        pth = os.path.join("/tmp", f"turn_{name}.png")
        render(pth, 520, 1.30, 44)
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


def render_detail_compare():
    """Sorgente 339k contro LOD0 55k, stesso primo piano sul viso.

    Riapre i due .blend (il file sorgente e quello finale), quindi va eseguita
    per ultima: azzera la scena in memoria.
    """
    from PIL import Image
    src = os.path.join(HERE, "ImageToStl.com_elf+character+3d+model(1).blend")
    if not os.path.exists(src):
        print("SKIP detail_compare: sorgente assente")
        return
    shots = []
    for tag, blend in (("src", src), ("lod", BLEND)):
        bpy.ops.wm.open_mainfile(filepath=blend)
        s_sc = bpy.context.scene
        s_ob = next(o for o in bpy.data.objects if o.type == 'MESH')
        for o in bpy.data.objects:
            if o.parent:
                mw = o.matrix_world.copy()
                o.parent = None
                o.matrix_world = mw
        for o in list(bpy.data.objects):
            if o.type not in {'MESH', 'ARMATURE'}:
                bpy.data.objects.remove(o, do_unlink=True)
        bpy.context.view_layer.objects.active = s_ob
        s_ob.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

        height = s_ob.dimensions.z
        head = mathutils.Vector((0.0, -0.015 * height, 0.885 * height))
        s_sc.render.engine = 'CYCLES'
        s_sc.cycles.device = 'CPU'
        s_sc.cycles.samples = 96
        s_sc.cycles.use_denoising = True
        w = s_sc.world or bpy.data.worlds.new("W")
        s_sc.world = w
        w.use_nodes = True
        w.node_tree.nodes["Background"].inputs[0].default_value = (0.010, 0.012, 0.016, 1)
        for name, D, energy, size, col in (
                ("Key", (0.9, -1.6, 0.55), 60, 1.0, (1.00, 0.92, 0.82)),
                ("Fill", (-1.2, -1.1, 0.15), 22, 1.6, (0.45, 0.60, 1.00))):
            ld = bpy.data.lights.new(name, 'AREA')
            ld.energy = energy * height * height
            ld.size = size * height
            ld.color = col
            lo = bpy.data.objects.new(name, ld)
            s_sc.collection.objects.link(lo)
            lo.location = head + mathutils.Vector(D) * height
            lo.rotation_euler = (head - lo.location).to_track_quat('-Z', 'Y').to_euler()
        camd = bpy.data.cameras.new("Cam")
        camd.lens = 105
        cam = bpy.data.objects.new("Cam", camd)
        s_sc.collection.objects.link(cam)
        s_sc.camera = cam
        cam.location = head + mathutils.Vector((0.26, -0.72, -0.01)) * height
        cam.rotation_euler = (head - cam.location).to_track_quat('-Z', 'Y').to_euler()
        s_sc.render.resolution_x = 640
        s_sc.render.resolution_y = 640
        s_sc.view_settings.view_transform = 'AgX'
        s_sc.view_settings.exposure = -0.35
        pth = os.path.join("/tmp", f"cmp_{tag}.png")
        s_sc.render.filepath = pth
        bpy.ops.render.render(write_still=True)
        shots.append(pth)
        print("RENDER", pth)
    ims = [Image.open(p) for p in shots]
    W = sum(i.width for i in ims)
    sheet = Image.new("RGB", (W, max(i.height for i in ims)), (12, 13, 16))
    x = 0
    for im in ims:
        sheet.paste(im, (x, 0))
        x += im.width
    sheet.save(os.path.join(OUTDIR, "detail_compare.png"))
    print("SHEET detail_compare.png")
    for p in shots:
        os.remove(p)


# ------------------------------------------------------------------- GIF -----
# (nome, azione, step frame, azimut camera): walk/run quasi di lato, dove la
# falcata si legge; idle/cast/death a tre quarti
CLIPS = [("idle", "ELFO1_Idle", 5, 34),
         ("walk", "ELFO1_Walk", 3, 64),
         ("run", "ELFO1_Run", 2, 64),
         ("cast", "ELFO1_Cast", 4, 36),
         ("death", "ELFO1_Death", 4, 42)]


def render_gifs(only=None):
    from PIL import Image
    for name, action, step, az in CLIPS:
        if only and name not in only:
            continue
        act = bpy.data.actions[action]
        f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
        frames = list(range(f0, f1 + 1, step))
        # bbox che contiene tutta la clip: la camera non deve tagliare nulla
        mn = mathutils.Vector((1e9, 1e9, 1e9))
        mx = mathutils.Vector((-1e9, -1e9, -1e9))
        for f in frames:
            pose(action, f)
            cc, ss = bbox()
            mn = mathutils.Vector((min(mn.x, cc.x - ss.x / 2), min(mn.y, cc.y - ss.y / 2),
                                   min(mn.z, cc.z - ss.z / 2)))
            mx = mathutils.Vector((max(mx.x, cc.x + ss.x / 2), max(mx.y, cc.y + ss.y / 2),
                                   max(mx.z, cc.z + ss.z / 2)))
        c = (mn + mx) / 2
        s = mx - mn
        world((0.010, 0.012, 0.018))
        clear_lights()
        lights(c, 0.95)
        camera(c, s, azimuth=az, elevation=0.16, zoom=1.0, lens=60,
               res=(420, 540), margin=1.06)
        tmp = []
        for i, f in enumerate(frames):
            pose(action, f)
            pth = os.path.join("/tmp", f"gif_{name}_{i:03d}.png")
            render(pth, 420, 540 / 420, 24)
            tmp.append(pth)
        ims = [Image.open(x).convert("RGB") for x in tmp]
        out = os.path.join(OUTDIR, f"anim_{name}.gif")
        ims[0].save(out, save_all=True, append_images=ims[1:],
                    duration=int(1000 * step / 30), loop=0, optimize=True)
        print("GIF", out, len(ims), "frame")
        for x in tmp:
            os.remove(x)


if ONLY_HEAD:
    render_head_only()
elif ONLY_TURN:
    render_turnaround()
elif DO_STILLS:
    render_stills()
    render_turnaround()
if DO_GIF and not ONLY_TURN:
    # ELFO1_ONLY_GIF=death rifa' solo quella clip (comodo quando si tocca
    # un'animazione sola senza rifare 15 minuti di render)
    only = [x.strip() for x in os.environ.get("ELFO1_ONLY_GIF", "").split(",") if x.strip()]
    render_gifs(only or None)
if DO_STILLS and not ONLY_TURN:
    render_detail_compare()      # per ultima: riapre i .blend da zero

print("[preview] fatto")
