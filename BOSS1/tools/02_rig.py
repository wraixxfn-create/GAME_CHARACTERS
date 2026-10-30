"""Step 2 - Rig.

Costruisce un'armatura per il boss knuckle-walker partendo dalle landmark
ricavate automaticamente dalla geometria (medial axis + sezioni):
- catena root > hips > spine > chest > neck > head (+ jaw, 'aureola')
- braccia a 4 segmenti (clavicola, braccio, avambraccio, mano) + 3 artigli
- gambe digitigrade a 4 segmenti (coscia, stinco, metatarso, dita)
- coda a 2 segmenti
- pesi automatici (heat) + correzioni per regioni isolate (aureola, creste)
- limite a 4 influenze per vertice, normalizzato (standard game)

Output: /home/user/work/stage2.blend
"""
import bpy
import math
import os
import sys
import numpy as np
from mathutils import Vector

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common import WORK


SRC = os.path.join(WORK, "stage1.blend")
OUT = os.path.join(WORK, "stage2.blend")

bpy.ops.wm.open_mainfile(filepath=SRC)
mesh_ob = next(o for o in bpy.data.objects if o.type == 'MESH')
mesh_ob.name = "BOSS1_body"

# ---------------------------------------------------------------- skeleton --
# (name, parent, head, tail, connected)
# Coordinate ricavate dalle landmark (vedi docs/wip/anatomy):
#  spalla ~(-0.13,-0.08,0.66)  gomito ~(-0.34,-0.02,0.42)  polso ~(-0.44,-0.10,0.13)
#  anca  ~(-0.09, 0.20,0.44)   ginocchio ~(-0.15,0.15,0.31) tallone ~(-0.16,0.28,0.22)
BONES = [
    # core
    ("root",       None,       (0.0,  0.02, 0.02), (0.0,  0.02, 0.16), False),
    ("hips",       "root",     (0.0,  0.18, 0.42), (0.0,  0.07, 0.50), False),
    ("spine",      "hips",     (0.0,  0.07, 0.50), (0.0, -0.03, 0.58), True),
    ("chest",      "spine",    (0.0, -0.03, 0.58), (0.0, -0.09, 0.66), True),
    ("neck",       "chest",    (0.0, -0.09, 0.66), (0.0, -0.16, 0.69), True),
    ("head",       "neck",     (0.0, -0.16, 0.69), (0.0, -0.30, 0.65), True),
    ("jaw",        "head",     (0.0, -0.21, 0.69), (0.0, -0.34, 0.63), False),
    # aureola/corona di spine
    ("halo_base",  "chest",    (0.0, -0.02, 0.68), (0.0, -0.03, 0.76), False),
    ("halo_mid",   "halo_base", (0.0, -0.03, 0.76), (0.03, -0.05, 0.83), True),
    ("halo_tip",   "halo_mid", (0.03, -0.05, 0.83), (0.09, -0.06, 0.85), True),
    # coda (stub)
    ("tail_01",    "hips",     (0.0,  0.22, 0.44), (0.0,  0.26, 0.41), False),
    ("tail_02",    "tail_01",  (0.0,  0.26, 0.41), (0.02, 0.30, 0.37), True),
]

def mirrored(entry, suffix, limb_names):
    name, parent, h, t, conn = entry
    p = f"{parent}.{suffix}" if parent in limb_names else parent
    return (f"{name}.{suffix}", p, h, t, conn)

ARM_L = [
    ("clavicle", "chest",     (-0.02, -0.04, 0.64), (-0.13, -0.08, 0.66), False),
    ("upperarm", "clavicle",  (-0.13, -0.08, 0.66), (-0.33, -0.03, 0.43), True),
    ("forearm",  "upperarm",  (-0.33, -0.03, 0.43), (-0.44, -0.10, 0.13), True),
    ("hand",     "forearm",   (-0.44, -0.10, 0.13), (-0.46, -0.14, 0.03), True),
    ("claw_a",   "hand",      (-0.46, -0.15, 0.04), (-0.50, -0.22, 0.00), False),
    ("claw_b",   "hand",      (-0.44, -0.13, 0.03), (-0.46, -0.20, -0.01), False),
    ("claw_c",   "hand",      (-0.41, -0.10, 0.03), (-0.41, -0.17, -0.01), False),
]
LEG_L = [
    ("thigh", "hips",     (-0.09, 0.20, 0.44), (-0.15, 0.15, 0.31), False),
    ("shin",  "thigh",    (-0.15, 0.15, 0.31), (-0.16, 0.28, 0.22), True),
    ("foot",  "shin",     (-0.16, 0.28, 0.22), (-0.20, 0.25, 0.06), True),
    ("toe",   "foot",     (-0.20, 0.25, 0.06), (-0.21, 0.32, 0.02), True),
]

def mirror_x(entry):
    name, parent, h, t, conn = entry
    return (name, parent, (-h[0], h[1], h[2]), (-t[0], t[1], t[2]), conn)

LIMB_NAMES = {e[0] for e in ARM_L + LEG_L}
for side, sign in (("L", 1), ("R", -1)):
    for e in ARM_L + LEG_L:
        if sign == 1:
            BONES.append(mirrored(e, "L", LIMB_NAMES))
        else:
            name, parent, h, t, conn = mirror_x(e)
            BONES.append(mirrored((name, parent, h, t, conn), "R", LIMB_NAMES))

arm_data = bpy.data.armatures.new("BOSS1_rig")
arm_ob = bpy.data.objects.new("BOSS1_rig", arm_data)
bpy.context.collection.objects.link(arm_ob)
bpy.context.view_layer.objects.active = arm_ob
arm_ob.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')

eb = arm_data.edit_bones
for name, parent, h, t, conn in BONES:
    b = eb.new(name)
    b.head = Vector(h)
    b.tail = Vector(t)
    b.use_deform = name != "root"
for name, parent, h, t, conn in BONES:
    if parent:
        eb[name].parent = eb[parent]
        eb[name].use_connect = conn

# roll: le braccia/gambe con l'asse X verso l'esterno, il resto allineato a +X
for b in eb:
    b.align_roll(Vector((0, 0, 1)) if b.name.startswith(("upperarm", "forearm",
                  "thigh", "shin")) else Vector((0, -1, 0)))
bpy.ops.object.mode_set(mode='OBJECT')

print(f"[rig] {len(arm_data.bones)} bones")
for b in arm_data.bones:
    print(f"   {b.name:14s} head={tuple(round(v,3) for v in b.head_local)} "
          f"len={b.length:.3f} deform={b.use_deform}")

# --------------------------------------------------------------- weighting --
bpy.ops.object.select_all(action='DESELECT')
mesh_ob.select_set(True)
arm_ob.select_set(True)
bpy.context.view_layer.objects.active = arm_ob
bpy.ops.object.parent_set(type='ARMATURE_AUTO')
print("[rig] automatic weights done")

me = mesh_ob.data
vg = mesh_ob.vertex_groups


def vg_get(name):
    return vg.get(name)


def normalize_and_limit(obj, limit=4):
    """Limita a `limit` influenze per vertice e normalizza."""
    me = obj.data
    groups = {g.index: g.name for g in obj.vertex_groups}
    for v in me.vertices:
        items = sorted(((g.weight, g.group) for g in v.groups), reverse=True)
        keep = items[:limit]
        tot = sum(w for w, _ in keep) or 1.0
        for w, gi in items:
            g = obj.vertex_groups[groups[gi]]
            if (w, gi) in keep:
                g.add([v.index], w / tot, 'REPLACE')
            else:
                g.remove([v.index])


normalize_and_limit(mesh_ob, 4)
print("[rig] weights limited to 4 influences and normalized")

# --------------------------------------------------- correzioni di regione --
co = np.empty(len(me.vertices) * 3, dtype=np.float32)
me.vertices.foreach_get("co", co)
co = co.reshape(-1, 3)


def assign_region(mask, bone_names, blend_radius=0.0):
    """Assegna peso 1 ai vertici del mask sui bone indicati (media se piu' di 1)."""
    if mask.sum() == 0:
        return 0
    idx = np.where(mask)[0].tolist()
    for vgname in [g.name for g in mesh_ob.vertex_groups]:
        grp = mesh_ob.vertex_groups[vgname]
        if vgname not in bone_names:
            grp.remove(idx)
    w = 1.0 / len(bone_names)
    for name in bone_names:
        mesh_ob.vertex_groups[name].add(idx, w, 'REPLACE')
    return len(idx)


# aureola: anello di spine sopra la schiena (z alto, vicino all'asse, dietro il muso)
halo = (co[:, 2] > 0.675) & (np.abs(co[:, 0]) < 0.15) & (co[:, 1] > -0.22) & \
       (co[:, 1] < 0.02) & (np.linalg.norm(co - np.array([0.0, -0.06, 0.78]), axis=1) < 0.20)
n = assign_region(halo, ["halo_mid", "halo_tip"])
print(f"[rig] halo region: {n} verts")

# coda (stub sul posteriore, sotto l'attacco della coscia)
tail = (co[:, 1] > 0.30) & (np.abs(co[:, 0]) < 0.10) & (co[:, 2] > 0.28) & (co[:, 2] < 0.46)
n = assign_region(tail, ["tail_02"])
print(f"[rig] tail region: {n} verts")

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED stage2.blend")
