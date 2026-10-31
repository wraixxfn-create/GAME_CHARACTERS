"""DRESS1 — render di presentazione.

Genera in ``DRESS1/preview/``:

* ``hero_front.png``     vista frontale, luce da studio
* ``hero_three.png``     tre quarti
* ``hero_waist.png``     primo piano su fascia, anello e staffa
* ``hero_feet.png``      primo piano su caviglie e sandali
* ``hero_back.png``      retro, luce da studio
* ``turnaround.png``     quattro viste affiancate (0/90/180/270 gradi)
* ``ref_compare.png``    concept dell'utente e render finale affiancati
"""

from __future__ import annotations

import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (add_area, add_camera, ensure_dir, link, render_to,
                    setup_world, work_dir)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PREVIEW = os.path.join(REPO, "preview")

BG = (0.055, 0.058, 0.066)


def studio(target=(0, 0, 0.62), scale=1.0):
    """Rig di luce: key calda da sinistra, fill freddo, rim posteriore."""
    L = []
    L.append(add_area("Key", (2.1 * scale, -2.6 * scale, 2.3 * scale), target,
                      energy=330 * scale ** 2, size=2.6 * scale,
                      color=(1.0, 0.96, 0.90)))
    L.append(add_area("Fill", (-2.7 * scale, -1.8 * scale, 1.1 * scale), target,
                      energy=95 * scale ** 2, size=3.4 * scale,
                      color=(0.82, 0.88, 1.0)))
    L.append(add_area("Rim", (-0.8 * scale, 2.8 * scale, 2.2 * scale), target,
                      energy=230 * scale ** 2, size=2.0 * scale,
                      color=(1.0, 0.94, 0.86)))
    L.append(add_area("Top", (0.0, 0.4 * scale, 3.3 * scale), target,
                      energy=120 * scale ** 2, size=2.4 * scale,
                      color=(1.0, 0.98, 0.94)))
    return L


def ground(z=0.0, size=6.0, color=(0.10, 0.105, 0.115)):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z))
    ob = bpy.context.object
    ob.name = "Ground"
    link(ob, "STUDIO")
    mat = bpy.data.materials.new("GroundMat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.55
    ob.data.materials.append(mat)
    return ob


def load(path):
    bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    return bpy.data.objects["DRESS1"]


def frame(cam, angle_deg, dist, target, height):
    a = math.radians(angle_deg)
    cam.location = (math.sin(a) * dist, -math.cos(a) * dist, height)
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (Vector(target) - Vector(cam.location)).to_track_quat(
        "-Z", "Y")


def main():
    ensure_dir(PREVIEW)
    src = os.path.join(REPO, "DRESS1.blend")
    ob = load(src)
    sc = bpy.context.scene
    setup_world(0.75, BG)
    studio(target=(0, 0, 0.62))
    ground(-0.004)
    cam = add_camera("Hero", (0, -3.3, 0.78), (0, 0, 0.58), lens=88)
    sc.camera = cam

    frame(cam, 0, 3.3, (0, 0, 0.58), 0.78)
    render_to(os.path.join(PREVIEW, "hero_front.png"), res=(900, 1240),
              samples=96, transparent=False)

    frame(cam, 34, 3.3, (0, 0, 0.58), 0.80)
    render_to(os.path.join(PREVIEW, "hero_three.png"), res=(900, 1240),
              samples=96, transparent=False)

    # primo piano vita
    cam.data.lens = 110
    frame(cam, 22, 1.05, (0.0, 0, 0.96), 1.06)
    render_to(os.path.join(PREVIEW, "hero_waist.png"), res=(1200, 1000),
              samples=104, transparent=False)

    # primo piano piedi
    cam.data.lens = 95
    frame(cam, 18, 0.95, (0, 0, 0.16), 0.36)
    render_to(os.path.join(PREVIEW, "hero_feet.png"), res=(1200, 900),
              samples=104, transparent=False)

    # dietro
    cam.data.lens = 88
    frame(cam, 180, 3.3, (0, 0, 0.58), 0.80)
    render_to(os.path.join(PREVIEW, "hero_back.png"), res=(900, 1240),
              samples=80, transparent=False)

    # turnaround: quattro viste su fondo neutro, poi affiancate in numpy
    tmp = ensure_dir(os.path.join(work_dir(), "preview"))
    files = []
    for tag, ang in (("f", 0), ("s", 90), ("b", 180), ("q", 270)):
        frame(cam, ang, 3.4, (0, 0, 0.58), 0.78)
        p = os.path.join(tmp, f"turn_{tag}.png")
        render_to(p, res=(620, 1000), samples=64, transparent=True)
        files.append(p)
    compose_turnaround(files, os.path.join(PREVIEW, "turnaround.png"))

    compose_compare(os.path.join(PREVIEW, "concept.png"),
                    os.path.join(PREVIEW, "hero_front.png"),
                    os.path.join(PREVIEW, "ref_compare.png"))
    print("[preview] fatto")


def compose_compare(ref_path, render_path, out_path):
    """Concept dell'utente contro il render finale, stessa altezza."""
    import numpy as np

    def load_arr(path):
        img = bpy.data.images.load(path)
        w, h = img.size
        px = np.zeros(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        arr = px.reshape(h, w, 4)[::-1].copy()
        bpy.data.images.remove(img)
        return arr

    def resize_to_height(arr, height):
        h, w = arr.shape[:2]
        width = max(1, int(round(w * height / h)))
        ys = (np.arange(height) * (h / height)).astype(int).clip(0, h - 1)
        xs = (np.arange(width) * (w / width)).astype(int).clip(0, w - 1)
        return arr[ys][:, xs]

    if not os.path.exists(ref_path):
        return
    ref = load_arr(ref_path)
    ren = load_arr(render_path)
    H = 1000
    ref = resize_to_height(ref, H)
    ren = resize_to_height(ren, H)
    gap = 24
    W = ref.shape[1] + ren.shape[1] + gap
    canvas = np.zeros((H, W, 4), dtype=np.float32)
    canvas[..., :3] = 0.94
    canvas[..., 3] = 1.0
    canvas[:, :ref.shape[1], :] = ref / np.maximum(ref[..., 3:4], 1e-3)
    x = ref.shape[1] + gap
    canvas[:, x:x + ren.shape[1], :] = ren
    save_array(canvas, out_path)


def compose_turnaround(files, out):
    import numpy as np

    tiles = []
    for f in files:
        img = bpy.data.images.load(f)
        w, h = img.size
        px = np.zeros(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        arr = px.reshape(h, w, 4)[::-1]
        tiles.append(arr)
        bpy.data.images.remove(img)
    h = max(t.shape[0] for t in tiles)
    w = sum(t.shape[1] for t in tiles) + 12 * (len(tiles) - 1)
    canvas = np.zeros((h, w, 4), dtype=np.float32)
    canvas[..., :3] = 0.055
    canvas[..., 3] = 1.0
    x = 0
    for t in tiles:
        th, tw = t.shape[:2]
        a = t[..., 3:4]
        region = canvas[0:th, x:x + tw, :3]
        canvas[0:th, x:x + tw, :3] = region * (1 - a) + t[..., :3] * a
        x += tw + 12
    save_array(canvas, out)


def save_array(arr, path):
    import numpy as np

    h, w = arr.shape[:2]
    img = bpy.data.images.new("compose", w, h, alpha=False)
    flat = np.clip(arr[::-1], 0, 1).astype(np.float32).ravel()
    img.pixels.foreach_set(flat)
    img.update()
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    print("[preview]", path)


if __name__ == "__main__":
    main()
