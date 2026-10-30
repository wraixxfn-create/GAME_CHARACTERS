"""Step 1 - Ottimizzazione game-ready (v2).

Rispetto alla v1 (decimation uniforme a 60k) la densita' dei triangoli viene
distribuita in base al dettaglio reale della superficie:

  * punteggi di curvatura calcolati sulla mesh ad alta risoluzione (spigoli
    vivi = spine, artigli, denti, creste)
  * boost esplicito sulle zone "da primo piano" (testa/muso, aureola, mani e
    artigli, piedi)
  * `DECIMATE` con vertex group: le zone pesate perdono molta meno risoluzione
    del torso, che e' quasi liscio
  * simmetria sull'asse X: i due lati restano identici, cosa che rende
    simmetrico anche lo skinning
  * merge dei vertici duplicati (la mesh Tripo ne ha alcuni a distanza zero)
    e normali pesate per non perdere gli spigoli delle spine

Output: /home/user/work/stage1.blend
"""
import bpy
import os
import sys
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common import (open_src, get_mesh, purge_scene_extras, apply_matrix,
                    tri_count, WORK, vertex_array, edge_array,
                    curvature_scores, region_masks, set_vertex_group)

TARGET_TRIS = int(os.environ.get("BOSS1_TARGET_TRIS", 80000))
DETAIL_GROUP = "detail"

open_src()
purge_scene_extras()
ob = get_mesh()
apply_matrix(ob)
ob.name = "BOSS1_body"
ob.data.name = "BOSS1_body_mesh"

me = ob.data
tris0 = tri_count(me)
print(f"[src] verts={len(me.vertices)} tris={tris0}")
print(f"[uv] layers={[l.name for l in me.uv_layers]}")

# I custom split normal dell'high-poly non servono piu' dopo la decimation.
if "custom_normal" in me.attributes:
    me.attributes.remove(me.attributes["custom_normal"])

# --------------------------------------------------------- pesi di dettaglio --
co = vertex_array(me)
curv = curvature_scores(me)
masks = region_masks(co)
detail = 0.55 * curv
detail += 0.45 * masks["head"]
detail += 0.35 * masks["halo"]
detail += 0.40 * masks["hands"]
detail += 0.25 * (masks["feet"] & (curv > 0.2))
detail = np.clip(detail / np.percentile(detail, 99), 0.0, 1.0)
set_vertex_group(ob, DETAIL_GROUP, detail)
print(f"[detail] media={detail.mean():.3f} alto(>0.5)={(detail > 0.5).mean():.1%} "
      f"regioni: testa={masks['head'].sum()} aureola={masks['halo'].sum()} "
      f"mani={masks['hands'].sum()} piedi={masks['feet'].sum()}")

bpy.context.view_layer.objects.active = ob
mod = ob.modifiers.new("Decimate", 'DECIMATE')
mod.decimate_type = 'COLLAPSE'
mod.ratio = TARGET_TRIS / tris0
mod.use_collapse_triangulate = True
mod.vertex_group = DETAIL_GROUP
mod.vertex_group_factor = 12.0      # quanto i pesi spostano il rapporto locale
mod.use_symmetry = True
mod.symmetry_axis = 'X'
bpy.ops.object.modifier_apply(modifier=mod.name)
ob.vertex_groups.remove(ob.vertex_groups[DETAIL_GROUP])

me = ob.data
tris1 = tri_count(me)
print(f"[decimated] verts={len(me.vertices)} tris={tris1} "
      f"({tris1 / tris0:.1%} dell'originale)")

# ------------------------------------------------------------ pulizia mesh --
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.delete_loose(use_verts=True, use_edges=True, use_faces=False)
bpy.ops.mesh.remove_doubles(threshold=2e-5)
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode='OBJECT')

for p in me.polygons:
    p.use_smooth = True
wn = ob.modifiers.new("WeightedNormal", 'WEIGHTED_NORMAL')
wn.keep_sharp = True
wn.weight = 60
bpy.ops.object.modifier_apply(modifier=wn.name)

# ------------------------------------------------------------- diagnostica --
me = ob.data
co = vertex_array(me)
E = edge_array(me)
L = np.linalg.norm(co[E[:, 0]] - co[E[:, 1]], axis=1)
print(f"[mesh] verts={len(me.vertices)} tris={tri_count(me)} edges={len(E)} "
      f"edge_len min={L.min():.5f} med={np.median(L):.4f} max={L.max():.4f}")
masks = region_masks(co)
tri = np.array([p.vertices[:] for p in me.polygons], dtype=np.int32)
centers = co[tri].mean(axis=1)
for name, m in masks.items():
    print(f"[density] {name:6s}: {m.sum():6d} verts")
for z0, z1 in ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.75), (0.75, 1.0)):
    sel = (centers[:, 2] >= z0) & (centers[:, 2] < z1)
    print(f"[density] z {z0:.2f}-{z1:.2f}: {sel.sum():6d} tris")

for m in list(bpy.data.materials):
    if m.users == 0:
        bpy.data.materials.remove(m)
me.materials[0].name = "BOSS1_MAT"
print("[mat]", [x.name for x in me.materials])
print("[uv] after:", [l.name for l in me.uv_layers])

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(WORK, "stage1.blend"))
print("SAVED stage1.blend")
