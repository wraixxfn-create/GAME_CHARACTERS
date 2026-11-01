"""DRESS1 — export per il motore.

Genera, a partire dal `.blend` con i materiali:

* `DRESS1.blend`        scena completa (mesh + 4 materiali + texture packate)
* `DRESS1.glb`          glTF 2.0 binario, LOD0
* `DRESS1_LOD1.glb`     35% dei triangoli
* `DRESS1_LOD2.glb`     12% dei triangoli
* `DRESS1.fbx`          FBX binary, unita' metriche, Z-up, fronte -Y
* `DRESS1_tex/`         le mappe esportate singolarmente (per chi non usa glb)

Gli export sono in metri e hanno origine a terra, sotto l'orlo (il capo
occupa la stessa quota che avrebbe indossato). I GLB sono Y-up; il FBX usa
Z-up e fronte -Y, come la scena Blender.
"""

from __future__ import annotations

import math
import importlib.util
import os
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
    # Sovrascrive solo le mappe generate, senza cancellare eventuali file
    # aggiunti dall'utente alla cartella delle texture.
    written = export_textures(ob, texdir)
    print("[export] texture:", len(written))

    # --- LOD: tessuto e dettagli conservano budget separati. Una decimazione
    # globale schiacciava in particolare le linee dorate larghe pochi mm.
    spec = importlib.util.spec_from_file_location(
        "dress1_optimize", os.path.join(os.path.dirname(__file__), "02_optimize.py"))
    opt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(opt)
    for tag, cloth_ratio, mid_ratio, trim_ratio, tex_scale in (
            ("LOD1", 0.25, 0.50, 0.58, 0.50),
            ("LOD2", 0.08, 0.18, 0.22, 0.25)):
        bpy.ops.wm.open_mainfile(filepath=blend)
        o = bpy.data.objects["DRESS1"]
        prepare_scene(o)
        for img in bpy.data.images:
            if img.size[0] > 8:
                w = max(64, int(img.size[0] * tex_scale))
                h = max(64, int(img.size[1] * tex_scale))
                img.scale(w, h)
        if o.vertex_groups.get("keep") is None:
            raise RuntimeError("Manca il gruppo 'keep' per preservare i ricami nei LOD")
        cloth, mid, trim = opt.split_by_group(o)
        opt.decimate(cloth, int(tri_count(cloth) * cloth_ratio))
        opt.decimate(mid, int(tri_count(mid) * mid_ratio))
        opt.decimate(trim, int(tri_count(trim) * trim_ratio))
        bpy.data.objects.remove(o, do_unlink=True)
        o = opt.join_objects([cloth, mid, trim], "DRESS1")
        bpy.context.view_layer.objects.active = o
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
