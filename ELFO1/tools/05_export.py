"""Step 5 - Finalizzazione ed export.

* **scala metrica reale**: il sorgente e' alto 1,000 unita' (arbitrarie); qui il
  personaggio diventa alto **1,85 m**, con mesh, ossa e traslazioni dei keyframe
  scalate in modo coerente. Nel motore non si scala piu' nulla.
* **LOD**: `ELFO1_LOD1.glb` (35% del LOD0) e `ELFO1_LOD2.glb` (12%), stesso rig,
  stesse clip, stesso materiale: si swappano a runtime.
* `.blend` compresso con le texture impacchettate, `.glb` con le 5 clip, `.fbx`
  con 5 take.
* verifica finale stampata a video (triangoli, ossa, clip, immagini).

Output: ELFO1/ELFO1.blend, ELFO1/ELFO1.glb, ELFO1/ELFO1.fbx,
        ELFO1/ELFO1_LOD1.glb, ELFO1/ELFO1_LOD2.glb
"""
import bpy
import os
import sys
from mathutils import Matrix

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common import WORK, HERE, TARGET_HEIGHT

SRC = os.path.join(WORK, "stage4.blend")
OUT_DIR = HERE
RENAMES = {"Idle": "ELFO1_Idle", "Walk": "ELFO1_Walk", "Run": "ELFO1_Run",
           "Cast": "ELFO1_Cast", "Death": "ELFO1_Death"}
LOD_RATIOS = {"ELFO1_LOD1": 0.35, "ELFO1_LOD2": 0.12}

bpy.ops.wm.open_mainfile(filepath=SRC)
sc = bpy.context.scene
mesh_ob = next(o for o in bpy.data.objects if o.type == 'MESH')
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')

# ------------------------------------------------------------ scala metrica --
me = mesh_ob.data
zmin = min(v.co.z for v in me.vertices)
zmax = max(v.co.z for v in me.vertices)
S = TARGET_HEIGHT / (zmax - zmin)
print(f"[scale] altezza sorgente {zmax - zmin:.4f} -> {TARGET_HEIGHT} m (x{S:.4f})")

me.transform(Matrix.Scale(S, 4))

parent = mesh_ob.parent
mw = mesh_ob.matrix_world.copy()
mesh_ob.parent = None
mesh_ob.matrix_world = mw

bpy.ops.object.select_all(action='DESELECT')
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
arm.scale = (S, S, S)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
mesh_ob.parent = parent
mesh_ob.matrix_parent_inverse = Matrix.Identity(4)


def all_fcurves(act):
    if hasattr(act, "fcurves") and len(getattr(act, "fcurves", [])):
        return list(act.fcurves)
    curves = []
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                curves.extend(cb.fcurves)
    return curves


nloc = 0
for act in bpy.data.actions:
    for fc in all_fcurves(act):
        if fc.data_path.endswith("location"):
            for kp in fc.keyframe_points:
                kp.co[1] *= S
                kp.handle_left[1] *= S
                kp.handle_right[1] *= S
            nloc += 1
print(f"[scale] canali di traslazione riscalati: {nloc}")

dim = mesh_ob.dimensions
print(f"[scale] dimensioni finali: {dim.x:.2f} x {dim.y:.2f} x {dim.z:.2f} m")

# ------------------------------------------------------------- naming/fps ----
sc.render.fps = 30
sc.unit_settings.system = 'METRIC'
sc.unit_settings.scale_length = 1.0
sc.frame_start, sc.frame_end = 1, 120

for old, new in RENAMES.items():
    if old in bpy.data.actions:
        bpy.data.actions[old].name = new
        bpy.data.actions[new].use_fake_user = True

arm.name = "ELFO1_rig"
arm.data.name = "ELFO1_rig"
mesh_ob.name = "ELFO1_body"
mesh_ob.data.name = "ELFO1_body_mesh"
arm.animation_data.action = bpy.data.actions["ELFO1_Idle"]
if hasattr(arm.animation_data, 'action_slot') and arm.animation_data.action.slots:
    arm.animation_data.action_slot = arm.animation_data.action.slots[0]
for a in bpy.data.actions:
    a.use_fake_user = True

for c in list(bpy.data.collections):
    if not c.objects and not c.children:
        bpy.data.collections.remove(c)

print("[final] azioni:", [a.name for a in bpy.data.actions])
print("[final] oggetti:", [(o.name, o.type) for o in bpy.data.objects])
print("[final] immagini:", [(i.name, tuple(i.size), i.packed_file is not None)
                            for i in bpy.data.images if i.name != "Render Result"])

bpy.ops.file.pack_all()
blend_out = os.path.join(OUT_DIR, "ELFO1.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_out, compress=True)
print("SAVED", blend_out, os.path.getsize(blend_out) // 1024, "KB")

# ------------------------------------------------------------------ export ---


def export_glb(path, selection=False):
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format='GLB',
        use_selection=selection,
        export_apply=True,
        export_yup=True,
        export_animations=True,
        export_animation_mode='ACTIONS',
        export_bake_animation=False,
        export_nla_strips=False,
        export_optimize_animation_size=True,
        export_optimize_animation_keep_anim_armature=True,
        export_anim_slide_to_zero=True,
        export_skins=True,
        export_all_influences=False,
        export_image_format='AUTO',
        export_normals=True,
        export_tangents=False,
        export_materials='EXPORT',
        export_cameras=False,
        export_lights=False,
    )
    print("SAVED", path, os.path.getsize(path) // 1024, "KB")


glb_out = os.path.join(OUT_DIR, "ELFO1.glb")
export_glb(glb_out)

fbx_out = os.path.join(OUT_DIR, "ELFO1.fbx")
for ob in bpy.data.objects:
    ob.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.fbx(
    filepath=fbx_out,
    use_selection=True,
    object_types={'ARMATURE', 'MESH'},
    apply_scale_options='FBX_SCALE_ALL',
    mesh_smooth_type='OFF',
    use_tspace=False,
    add_leaf_bones=False,
    primary_bone_axis='Y',
    secondary_bone_axis='X',
    bake_anim=True,
    bake_anim_use_all_actions=True,
    bake_anim_use_nla_strips=False,
    bake_anim_step=1.0,
    bake_anim_simplify_factor=0.0,
    path_mode='COPY',
    embed_textures=True,
    axis_forward='-Z',
    axis_up='Y',
)
print("SAVED", fbx_out, os.path.getsize(fbx_out) // 1024, "KB")

# --------------------------------------------------------------------- LOD ---
base_tris = sum(len(p.vertices) - 2 for p in me.polygons)
for lod_name, ratio in LOD_RATIOS.items():
    lod_mesh = mesh_ob.copy()
    lod_mesh.data = mesh_ob.data.copy()
    lod_mesh.name = lod_name
    lod_mesh.data.name = f"{lod_name}_mesh"
    bpy.context.collection.objects.link(lod_mesh)
    lod_mesh.parent = arm
    mod = lod_mesh.modifiers.new("Decimate", 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = ratio
    mod.use_collapse_triangulate = True
    bpy.context.view_layer.objects.active = lod_mesh
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.vertex_group_limit_total(limit=4)
    bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    tris = sum(len(p.vertices) - 2 for p in lod_mesh.data.polygons)
    print(f"[lod] {lod_name}: {tris} tris ({tris / base_tris:.1%} del LOD0)")

    for ob in bpy.data.objects:
        ob.select_set(ob in (lod_mesh, arm))
    bpy.context.view_layer.objects.active = arm
    path = os.path.join(OUT_DIR, f"{lod_name}.glb")
    export_glb(path, selection=True)
    bpy.data.objects.remove(lod_mesh, do_unlink=True)

print("[done] export completato")
