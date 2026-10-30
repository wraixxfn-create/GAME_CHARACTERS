"""Step 1 - Ottimizzazione game-ready.

- pulizia della scena importata (empty/camera/luci di ImageToStl)
- applicazione delle trasformazioni
- decimation collapse 500k -> ~60k triangoli (UV preservate)
- normali pesate per mantenere gli spigoli delle spine
- pulizia materiali (via il materiale orfano)

Output: /home/user/work/stage1.blend
"""
import bpy
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common import (open_src, get_mesh, purge_scene_extras,
                    apply_matrix, tri_count, WORK)

TARGET_TRIS = 60000

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

bpy.context.view_layer.objects.active = ob
mod = ob.modifiers.new("Decimate", 'DECIMATE')
mod.decimate_type = 'COLLAPSE'
mod.ratio = TARGET_TRIS / tris0
mod.use_collapse_triangulate = True
bpy.ops.object.modifier_apply(modifier=mod.name)

me = ob.data
tris1 = tri_count(me)
print(f"[decimated] verts={len(me.vertices)} tris={tris1} "
      f"({tris1 / tris0:.1%} dell'originale)")

for p in me.polygons:
    p.use_smooth = True
wn = ob.modifiers.new("WeightedNormal", 'WEIGHTED_NORMAL')
wn.keep_sharp = True
wn.weight = 50
bpy.ops.object.modifier_apply(modifier=wn.name)

for m in list(bpy.data.materials):
    if m.users == 0:
        bpy.data.materials.remove(m)
me.materials[0].name = "BOSS1_MAT"
print("[mat]", [x.name for x in me.materials])
print("[uv] after:", [l.name for l in me.uv_layers])

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(WORK, "stage1.blend"))
print("SAVED stage1.blend")
