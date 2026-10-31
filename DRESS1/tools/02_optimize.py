"""DRESS1 — ottimizzazione per il motore.

Il capo nasce a ~514k triangoli (griglie uniformi, comodo da modellare) e deve
uscire a misura di motore. La decimation non e' uniforme: i dettagli sottili —
ricami dorati da 3 mm, nastri, staffa, fasciature — hanno un budget tutto loro,
altrimenti a 60k triangoli spariscono.

Strategia: si dividono le facce in **stoffa** e **dettagli** usando il vertex
group ``keep`` creato da ``01_build.py``, ognuna viene decimata col proprio
rapporto, poi si riuniscono. Il gruppo `keep` rimane nella mesh per permettere
all'export di generare i LOD con budget separati.
"""

from __future__ import annotations

import math
import os
import sys

import bpy  # noqa: E402
import bmesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (apply_modifiers, ensure_dir, tri_count, uv_unwrap,
                    work_dir)

CLOTH_TARGET = 52000     # triangoli di stoffa (griglie, pieghe, gambe, piedi)
TRIM_TARGET = 26000      # triangoli dei dettagli (oro, staffa, fasciature)


# --------------------------------------------------------------------------
# split / join
# --------------------------------------------------------------------------

def split_by_group(ob, group_name="keep"):
    """Divide l'oggetto in (stoffa, dettagli) secondo il vertex group."""
    gi = ob.vertex_groups[group_name].index
    weights = [0.0] * len(ob.data.vertices)
    for v in ob.data.vertices:
        for g in v.groups:
            if g.group == gi:
                weights[v.index] = g.weight
    keep = [w > 0.5 for w in weights]

    meshes = []
    for tag, want in (("cloth", False), ("trim", True)):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.faces.ensure_lookup_table()
        layer_uv = bm.loops.layers.uv.active
        drop = []
        for f in bm.faces:
            if all(keep[v.index] for v in f.verts) != want:
                drop.append(f)
        bmesh.ops.delete(bm, geom=drop, context="FACES")
        me = bpy.data.meshes.new(f"{ob.name}_{tag}")
        bm.to_mesh(me)
        bm.free()
        for mat in ob.data.materials:
            me.materials.append(mat)
        if layer_uv is None:
            me.uv_layers.new(name="UVMap")
        new = bpy.data.objects.new(f"{ob.name}_{tag}", me)
        bpy.context.scene.collection.objects.link(new)
        if want:
            # Conserva il gruppo anche dopo lo split/join: l'export crea LOD
            # con budget separati e non deve distruggere i ricami sottili.
            group = new.vertex_groups.new(name=group_name)
            group.add(list(range(len(me.vertices))), 1.0, "REPLACE")
        meshes.append(new)
    return meshes


def join_objects(objs, name="DRESS1"):
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    ob = bpy.context.object
    ob.name = name
    ob.data.name = name + "_mesh"
    return ob


# --------------------------------------------------------------------------
# decimation
# --------------------------------------------------------------------------

def decimate(ob, target_tris):
    cur = tri_count(ob)
    if cur <= target_tris:
        return ob
    m = ob.modifiers.new("Decimate", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = max(0.001, min(1.0, target_tris / max(cur, 1)))
    m.use_collapse_triangulate = False
    apply_modifiers(ob)
    return ob


def triangulate(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.triangulate(bm, faces=bm.faces, quad_method="BEAUTY",
                          ngon_method="BEAUTY")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def finalize(ob):
    """UV e normali smussate in base all'angolo."""
    uv_unwrap(ob, angle=58.0, margin=0.0012)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.object.shade_smooth()
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(46.0))
    except Exception:
        pass
    ob.modifiers.clear()
    return ob


def main():
    src = os.path.join(work_dir(), "build", "DRESS1_build.blend")
    out = ensure_dir(os.path.join(work_dir(), "opt"))
    bpy.ops.wm.open_mainfile(filepath=src)
    ob = bpy.data.objects["DRESS1"]
    print(f"[opt] sorgente: {tri_count(ob)} triangoli, "
          f"{len(ob.data.vertices)} vertici")

    triangulate(ob)
    cloth, trim = split_by_group(ob)
    print(f"[opt] stoffa {tri_count(cloth)} tri, dettagli {tri_count(trim)} tri")

    decimate(cloth, CLOTH_TARGET)
    decimate(trim, TRIM_TARGET)
    print(f"[opt] dopo decimation: stoffa {tri_count(cloth)}, "
          f"dettagli {tri_count(trim)}")

    bpy.data.objects.remove(ob, do_unlink=True)
    ob = join_objects([cloth, trim], "DRESS1")
    finalize(ob)
    print(f"[opt] LOD0: {tri_count(ob)} triangoli, {len(ob.data.vertices)} vertici, "
          f"{len(ob.data.materials)} materiali")

    path0 = os.path.join(out, "DRESS1_opt.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path0)
    print("[opt] salvato", path0)




if __name__ == "__main__":
    main()
