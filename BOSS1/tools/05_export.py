"""Step 5 - Finalizzazione ed export.

- rinomina le azioni in modo parlante per i motori (BOSS1_Idle, ...)
- imposta unita' metriche, fps e frame range
- salva il .blend finale con tutto impacchettato
- esporta GLB (glTF 2.0, tutte le animazioni) e FBX

Output: BOSS1/BOSS1.blend, BOSS1/BOSS1.glb, BOSS1/BOSS1.fbx
"""
import bpy
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common import WORK, HERE
SRC = os.path.join(WORK, "stage4.blend")
OUT_DIR = HERE

bpy.ops.wm.open_mainfile(filepath=SRC)
sc = bpy.context.scene

# ------------------------------------------------------------- naming/fps --
sc.render.fps = 30
sc.unit_settings.system = 'METRIC'
sc.unit_settings.scale_length = 1.0
sc.frame_start, sc.frame_end = 1, 120

for old, new in (("Idle", "BOSS1_Idle"), ("Roar", "BOSS1_Roar"),
                 ("Attack", "BOSS1_Attack")):
    if old in bpy.data.actions:
        bpy.data.actions[old].name = new
        bpy.data.actions[new].use_fake_user = True

arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
arm.name = "BOSS1_rig"
arm.data.name = "BOSS1_rig"
arm.animation_data.action = bpy.data.actions["BOSS1_Idle"]

# collezione pulita
for c in list(bpy.data.collections):
    if not c.objects and not c.children:
        bpy.data.collections.remove(c)

print("[final] azioni:", [a.name for a in bpy.data.actions])
print("[final] oggetti:", [(o.name, o.type) for o in bpy.data.objects])
print("[final] immagini:", [(i.name, tuple(i.size), i.packed_file is not None)
                            for i in bpy.data.images if i.name != "Render Result"])

# assicura che le texture siano impacchettate nel .blend
bpy.ops.file.pack_all()
blend_out = os.path.join(OUT_DIR, "BOSS1.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_out, compress=True)
print("SAVED", blend_out, os.path.getsize(blend_out) // 1024, "KB")

# ------------------------------------------------------------------ export --
for ob in bpy.data.objects:
    ob.select_set(True)
bpy.context.view_layer.objects.active = arm

glb_out = os.path.join(OUT_DIR, "BOSS1.glb")
bpy.ops.export_scene.gltf(
    filepath=glb_out,
    export_format='GLB',
    use_selection=False,
    export_apply=True,
    export_yup=True,
    export_animations=True,
    export_animation_mode='ACTIONS',
    export_bake_animation=False,
    export_nla_strips=False,
    export_optimize_animation_size=True,
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
print("SAVED", glb_out, os.path.getsize(glb_out) // 1024, "KB")

fbx_out = os.path.join(OUT_DIR, "BOSS1.fbx")
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
