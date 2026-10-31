"""DRESS1 — export per il motore.

Genera, a partire dal `.blend` con i materiali:

* `DRESS1.blend`        scena completa (mesh + 6 materiali + texture packate)
* `DRESS1.glb`          glTF 2.0 binario, LOD0
* `DRESS1_LOD1.glb`     35% dei triangoli
* `DRESS1_LOD2.glb`     12% dei triangoli
* `DRESS1.fbx`          FBX binary, unita' metriche, asse Y
* `DRESS1_tex/`         le mappe esportate singolarmente (per chi non usa glb)

Tutti gli export sono in metri, Y-up, origine ai piedi (z=0 al pavimento).
"""

from __future__ import annotations

import math
import os
import shutil
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ensure_dir, tri_count, work_dir

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def prepare_scene(ob):
    """Pulizia: solo la mesh, trasformazioni applicate, origine ai piedi."""
    sc = bpy.context.scene
    for o in list(bpy.data.objects):
        if o is not ob:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.location = (0.0, 0.0, 0.0)
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    return ob


def export_gltf(path, ob):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
        export_draco_mesh_compression_enable=False,
        export_animations=False,
        export_skins=False,
        export_morph=False,
    )
    return path


def export_fbx(path, ob):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.fbx(
        filepath=path,
        use_selection=True,
        apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Y",
        axis_up="Z",
        object_types={"MESH"},
        mesh_smooth_type="FACE",
        use_tspace=True,
        bake_anim=False,
        path_mode="COPY",
        embed_textures=True,
    )
    return path


def export_textures(ob, outdir):
    ensure_dir(outdir)
    written = []
    seen = set()
    for slot in ob.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type != "TEX_IMAGE" or node.image is None:
                continue
            img = node.image
            if img.name in seen or img.size[0] == 0:
                continue
            seen.add(img.name)
            path = os.path.join(outdir, img.name + ".png")
            img.filepath_raw = path
            img.file_format = "PNG"
            img.save()
            written.append(path)
    return written


def main():
    src = os.path.join(work_dir(), "mat", "DRESS1_mat.blend")
    bpy.ops.wm.open_mainfile(filepath=src)
    ob = bpy.data.objects["DRESS1"]
    prepare_scene(ob)
    print(f"[export] {tri_count(ob)} triangoli, {len(ob.data.vertices)} vertici, "
          f"{len(ob.data.materials)} materiali")

    os.makedirs(REPO, exist_ok=True)
    # --- .blend
    blend = os.path.join(REPO, "DRESS1.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    print("[export]", blend, f"{os.path.getsize(blend)/1e6:.1f} MB")

    # --- .glb LOD0
    glb = export_gltf(os.path.join(REPO, "DRESS1.glb"), ob)
    print("[export]", glb, f"{os.path.getsize(glb)/1e6:.1f} MB")

    # --- texture sciolte
    texdir = os.path.join(REPO, "DRESS1_tex")
    if os.path.isdir(texdir):
        shutil.rmtree(texdir)
    export_textures(ob, texdir)
    print("[export] texture:", len(os.listdir(texdir)))

    # --- LOD1 / LOD2 glb: decimati dal LOD0 gia' testurizzato, cosi'
    # materiali e mappe restano gli stessi per costruzione
    for tag, ratio, tex_scale in (("LOD1", 0.35, 0.5), ("LOD2", 0.12, 0.25)):
        bpy.ops.wm.open_mainfile(filepath=blend)
        o = bpy.data.objects["DRESS1"]
        prepare_scene(o)
        # i LOD usano mappe piu' piccole: e' pratica standard e tiene i file
        # autonomi senza ripetere 12 texture a piena risoluzione
        for img in bpy.data.images:
            if img.size[0] > 8:
                w = max(64, int(img.size[0] * tex_scale))
                h = max(64, int(img.size[1] * tex_scale))
                img.scale(w, h)
        target = int(tri_count(o) * ratio)
        m = o.modifiers.new("Decimate", "DECIMATE")
        m.decimate_type = "COLLAPSE"
        m.ratio = max(0.001, target / max(tri_count(o), 1))
        m.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(46.0))
        path = export_gltf(os.path.join(REPO, f"DRESS1_{tag}.glb"), o)
        print("[export]", path, f"{tri_count(o)} tri",
              f"{os.path.getsize(path)/1e6:.2f} MB")

    # --- .fbx
    bpy.ops.wm.open_mainfile(filepath=blend)
    ob = bpy.data.objects["DRESS1"]
    fbx = export_fbx(os.path.join(REPO, "DRESS1.fbx"), ob)
    print("[export]", fbx, f"{os.path.getsize(fbx)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
