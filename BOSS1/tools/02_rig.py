"""Step 2 - Rig e skinning (v2).

Lo scheletro e' lo stesso della v1 (34 ossa, catena root/hips/spine/chest/neck/
head + jaw, aureola a 3 segmenti, coda, braccia a 4 segmenti con 3 artigli,
gambe digitigrade a 4 segmenti), ma i **pesi** sono completamente diversi.

La v1 usava i pesi automatici "bone heat" di Blender, che su una creatura
accovacciata (mani a terra vicine ai piedi, aureola appoggiata alla schiena)
sbagliano facilmente: un vertice della mano finiva influenzato dalla coscia
perche' vicino **nello spazio**, non **sulla superficie**.

Qui il peso nasce dalla distanza geodesica lungo la mesh:

1. per ogni osso si prendono come seed i vertici di superficie piu' vicini
   all'osso (banda di 2 cm sul punto di minima distanza);
2. multi-source Dijkstra sullo scheletro di edge della mesh (scipy) da quei
   seed: per ogni vertice si ottiene la distanza *sulla superficie* da ogni osso;
3. peso = 1 / d^4 (solo per gli ossi entro 3x la distanza minima), quindi
   smoothing laplaciano sui pesi (6 iterazioni) per togliere i gradini;
4. limite a 4 influenze per vertice, normalizzazione, pulizia dei pesi < 0.01.

Il risultato e' uno skinning che segue l'anatomia, senza bleed tra arti e con
transizioni morbide su spalle, gomiti, anche e coda.

Output: /home/user/work/stage2.blend
"""
import bpy
import math
import os
import sys
import numpy as np
from mathutils import Vector

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common import (WORK, vertex_array, edge_array, set_vertex_group)

try:
    from scipy.sparse import coo_matrix, csr_matrix
    from scipy.sparse.csgraph import dijkstra
except ImportError:  # pragma: no cover
    raise SystemExit("serve scipy: pip install scipy")

SRC = os.path.join(WORK, "stage1.blend")
OUT = os.path.join(WORK, "stage2.blend")

bpy.ops.wm.open_mainfile(filepath=SRC)
mesh_ob = next(o for o in bpy.data.objects if o.type == 'MESH')
mesh_ob.name = "BOSS1_body"

# ---------------------------------------------------------------- skeleton --
# (name, parent, head, tail, connected)
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


def mirrored(entry, suffix, limb_names):
    name, parent, h, t, conn = entry
    p = f"{parent}.{suffix}" if parent in limb_names else parent
    return (f"{name}.{suffix}", p, h, t, conn)


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

# roll: gli arti con l'asse X verso l'esterno, il resto allineato a +X
for b in eb:
    b.align_roll(Vector((0, 0, 1)) if b.name.startswith(("upperarm", "forearm",
                  "thigh", "shin")) else Vector((0, -1, 0)))
bpy.ops.object.mode_set(mode='OBJECT')

deform = [b.name for b in arm_data.bones if b.use_deform]
print(f"[rig] {len(arm_data.bones)} bones ({len(deform)} deform)")

# --------------------------------------------------------------- skinning ---
me = mesh_ob.data
co = vertex_array(me).astype(np.float64)
E = edge_array(me)
nv = len(co)

# scheletro di edge pesato con la lunghezza euclidea (per Dijkstra)
elen = np.linalg.norm(co[E[:, 0]] - co[E[:, 1]], axis=1)
elen = np.maximum(elen, 1e-5)
graph = coo_matrix((np.concatenate([elen, elen]),
                    (np.concatenate([E[:, 0], E[:, 1]]),
                     np.concatenate([E[:, 1], E[:, 0]]))),
                   shape=(nv, nv)).tocsr()

POS = {b.name: (np.array(b.head_local), np.array(b.tail_local))
       for b in arm_data.bones if b.use_deform}


def point_segment_distance(p, a, b):
    ab = b - a
    ap = p - a
    t = np.clip(ap @ ab / (ab @ ab), 0.0, 1.0)
    proj = a + t[:, None] * ab
    return np.linalg.norm(p - proj, axis=1)


D = np.full((nv, len(deform)), np.inf, dtype=np.float32)
for bi, name in enumerate(deform):
    a, b = POS[name]
    d = point_segment_distance(co, a, b)
    dmin = d.min()
    seeds = np.where(d <= dmin + 0.02)[0]
    if len(seeds) == 0:
        seeds = np.argsort(d)[:8]
    dist = dijkstra(graph, indices=seeds, min_only=True, directed=False)
    D[:, bi] = dist
print("[skin] distanze geodesiche calcolate")

# ------------------------------------------------------------ pesi iniziali --
eps = 1e-4
dmin = D.min(axis=1, keepdims=True)
mask = D <= np.maximum(2.5 * dmin, dmin + 0.03)
W = np.where(mask, 1.0 / np.maximum(D, eps) ** 4, 0.0)
W /= np.maximum(W.sum(axis=1, keepdims=True), 1e-12)

# smoothing laplaciano (solo sui pesi, poi rinormalizza)
deg = np.bincount(np.concatenate([E[:, 0], E[:, 1]]), minlength=nv).astype(np.float64)
A = coo_matrix((np.ones(len(E) * 2) / np.concatenate([deg[E[:, 0]], deg[E[:, 1]]]),
                (np.concatenate([E[:, 0], E[:, 1]]),
                 np.concatenate([E[:, 1], E[:, 0]]))), shape=(nv, nv)).tocsr()
for _ in range(6):
    W = 0.45 * W + 0.55 * (A @ W)
    W /= np.maximum(W.sum(axis=1, keepdims=True), 1e-12)

# limite a 4 influenze + soglia
LIMIT, MIN_W = 4, 0.01
order = np.argsort(-W, axis=1)
keep = order[:, :LIMIT]
Wk = np.take_along_axis(W, keep, axis=1)
Wk[Wk < MIN_W] = 0.0
Wk /= np.maximum(Wk.sum(axis=1, keepdims=True), 1e-12)

for g in list(mesh_ob.vertex_groups):
    mesh_ob.vertex_groups.remove(g)
for j, name in enumerate(deform):
    w = np.zeros(nv)
    sel = keep == j
    rows = np.where(sel.any(axis=1))[0]
    if len(rows) == 0:
        continue
    cols = np.argmax(sel[rows], axis=1)
    w[rows] = Wk[rows, cols]
    if w.any():
        set_vertex_group(mesh_ob, name, w)

mesh_ob.parent = arm_ob
mod = mesh_ob.modifiers.get("Armature") or mesh_ob.modifiers.new("Armature", 'ARMATURE')
mod.object = arm_ob
mod.use_vertex_groups = True

# --------------------------------------------------------------- validazione --
counts = (Wk > 0).sum(axis=1)
tot = Wk.sum(axis=1)
print(f"[skin] influenze per vertice: max={counts.max()} media={counts.mean():.2f} "
      f"senza pesi={(counts == 0).sum()} somma pesi min={tot.min():.3f} max={tot.max():.3f}")

# ogni parte del corpo deve avere almeno un osso con peso sensato
Wfull = np.zeros((nv, len(deform)))
np.put_along_axis(Wfull, keep, Wk, axis=1)
for name in ("head", "jaw", "hand.L", "claw_a.R", "toe.L", "tail_02", "halo_tip"):
    j = deform.index(name)
    n = int((Wfull[:, j] > 0.25).sum())
    print(f"[skin] vertici con {name} > 0.25: {n}")
print(f"[skin] ossi senza vertici dominanti: "
      f"{[n for i, n in enumerate(deform) if (np.argmax(Wfull, axis=1) == i).sum() == 0]}")

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED stage2.blend")
