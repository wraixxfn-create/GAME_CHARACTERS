"""Step 2 - Rig e skinning.

Lo scheletro e' definito in `skeleton.py` (43 ossa, 42 deformanti): catena
root/hips/spine/chest/neck/head, braccia a 5 segmenti (con pollice e dita),
gambe a 4, due catene di ciocche laterali, tre posteriori + cresta, e otto ossa
per il gonnellone.

Lo **skinning** non usa i pesi automatici di Blender ma la distanza
**geodesica** lungo la superficie:

1. per ogni osso si prendono come seed i vertici di superficie piu' vicini
   al segmento (banda di 2 cm attorno al punto di minima distanza);
2. multi-source Dijkstra sullo scheletro di edge della mesh (scipy): per ogni
   vertice si ottiene la distanza *sulla superficie* da ogni osso;
3. peso = 1 / d^4 (solo per le ossa entro ~3x la distanza minima), smoothing
   laplaciano sui pesi (6 iterazioni) per togliere i gradini;
4. limite a 4 influenze per vertice, normalizzazione, soglia 0,01.

Perche' conta su un personaggio vestito: il gonnellone e' una superficie
distante pochi centimetri dalle cosce ma **lontana sulla mesh** (si deve
risalire fino alla vita). Con una distanza euclidea la stoffa si incollerebbe
alle gambe; con quella geodesica la prendono le ossa della gonna, e le gambe
muovono solo la stoffa che toccano davvero.

Output: $ELFO1_WORK/stage2.blend
"""
import bpy
import os
import sys
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common import WORK, vertex_array, edge_array, set_vertex_group
from skeleton import build_armature, DEFORM

try:
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
except ImportError:  # pragma: no cover
    raise SystemExit("serve scipy: pip install scipy")

SRC = os.path.join(WORK, "stage1.blend")
OUT = os.path.join(WORK, "stage2.blend")
SEED_BAND = float(os.environ.get("ELFO1_SEED_BAND", 0.02))

bpy.ops.wm.open_mainfile(filepath=SRC)
mesh_ob = next(o for o in bpy.data.objects if o.type == 'MESH')
mesh_ob.name = "ELFO1_body"

arm_ob = build_armature("ELFO1_rig")
arm_data = arm_ob.data
deform = [b.name for b in arm_data.bones if b.use_deform]
print(f"[rig] {len(arm_data.bones)} bones ({len(deform)} deform)")
assert set(deform) == set(DEFORM), (len(deform), len(DEFORM))

# --------------------------------------------------------------- skinning ---
me = mesh_ob.data
co = vertex_array(me).astype(np.float64)
E = edge_array(me)
nv = len(co)

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
    t = np.clip(ap @ ab / max(ab @ ab, 1e-12), 0.0, 1.0)
    proj = a + t[:, None] * ab
    return np.linalg.norm(p - proj, axis=1)


# --- maschere anatomiche -----------------------------------------------------
# Le ciocche e la stoffa sono superfici sottili appoggiate al corpo: senza un
# vincolo, il percorso geodesico "salta" dalla punta di una ciocca alla spalla
# e le ossa dei capelli si prendono mezzo busto. Queste maschere limitano semi
# e influenza delle ossa "secondarie" alla regione che devono muovere.
z, y, x = co[:, 2], co[:, 1], co[:, 0]
ax = np.abs(x)
# Il volume dei capelli, misurato sul modello: sopra le spalle (z > 0.70) le
# ciocche stanno davanti e dietro il collo (|y| > 0.035) o ai lati della testa
# (|x| > 0.042); sotto le spalle (0.55 < z < 0.70) restano solo le ciocche
# libere, cioe' quelle che sporgono oltre la schiena (y > 0.058) o oltre le
# spalle (|x| > 0.075). Il resto e' pelle.
hair_hi = (z > 0.70) & ((y > 0.035) | (ax > 0.042))
hair_lo = (z > 0.55) & (z <= 0.70) & ((y > 0.058) | (ax > 0.075))
hair = hair_hi | hair_lo
cloth = (z > 0.11) & (z < 0.49)


def hair_seed(name):
    if name.startswith("hair_crest"):
        return z > 0.90
    if name.startswith("hair_back"):
        seg = int(name.split("_")[-1])
        lo = {1: 0.72, 2: 0.62, 3: 0.55}[seg]
        return hair & (y > 0.032) & (ax < 0.085) & (z > lo)
    if name.startswith("hair_side"):
        seg = int(name.split("_")[-1].split('.')[0])
        hi = 0.90 if seg == 1 else 0.84
        lo = 0.62 if seg == 1 else 0.54
        return hair & (ax > 0.040) & (z > lo) & (z < hi)
    return None


def cloth_seed(name):
    if name.startswith("skirt_front"):
        return cloth & (y < -0.025)
    if name.startswith("skirt_back"):
        return cloth & (y > 0.025)
    if name.startswith("skirt"):
        return cloth & (ax > 0.045) & (np.abs(y) < 0.075)
    return None


# La maschera serve solo a scegliere i semi e a impedire che le ossa "soft"
# invadano il corpo. Dentro la regione di competenza (capelli o tessuto) tutte
# le ossa di quel gruppo restano libere: con confini netti fra i quadranti del
# gonnellone il foglio si strappava quando le ossa ruotavano in modo diverso
# (squarci visibili nella posa di Cast).
SEED_MASK = {}
INFLUENCE_MASK = {}
for name in deform:
    if name.startswith("hair"):
        SEED_MASK[name] = hair_seed(name)
        INFLUENCE_MASK[name] = hair
    elif name.startswith("skirt"):
        SEED_MASK[name] = cloth_seed(name)
        INFLUENCE_MASK[name] = cloth

D = np.full((nv, len(deform)), np.inf, dtype=np.float32)
seeds_n = {}
for bi, name in enumerate(deform):
    a, b = POS[name]
    d = point_segment_distance(co, a, b)
    sm = SEED_MASK.get(name)
    if sm is not None:
        d = np.where(sm, d, np.inf)
    dmin = d.min()
    seeds = np.where(d <= dmin + SEED_BAND)[0]
    if len(seeds) == 0:
        seeds = np.argsort(d)[:8]
    seeds_n[name] = len(seeds)
    D[:, bi] = dijkstra(graph, indices=seeds, min_only=True, directed=False)
print("[skin] distanze geodesiche calcolate per", len(deform), "ossa;",
      "ossa con maschera:", len(INFLUENCE_MASK))

# ------------------------------------------------------------ pesi iniziali --
eps = 1e-4
# Le maschere vanno applicate *prima* di calcolare la distanza minima: se si
# tara la soglia su un osso poi mascherato (per esempio la gonna su un vertice
# della cintura) il vertice resta senza nessuna influenza e, nella posa, si
# pianta a terra mentre il resto del corpo si muove (le "schegge" bianche).
BONE_MASK = np.ones((nv, len(deform)), dtype=bool)
for bi, name in enumerate(deform):
    im = INFLUENCE_MASK.get(name)
    if im is not None:
        BONE_MASK[:, bi] = im
Da = np.where(BONE_MASK, D, np.inf)
dmin = Da.min(axis=1, keepdims=True)
mask = Da <= np.maximum(2.5 * dmin, dmin + 0.03)
W = np.where(mask, 1.0 / np.maximum(Da, eps) ** 4, 0.0)
W /= np.maximum(W.sum(axis=1, keepdims=True), 1e-12)

# rete di sicurezza: se un vertice non ha preso niente (maschere troppo strette
# o distanze degeneri) si usa la distanza euclidea dai segmenti, che c'e' sempre
orphan = np.where(~np.isfinite(dmin[:, 0]) | (W.sum(axis=1) < 0.5))[0]
if len(orphan):
    de = np.zeros((len(orphan), len(deform)), dtype=np.float64)
    for bi, name in enumerate(deform):
        a, b = POS[name]
        de[:, bi] = point_segment_distance(co[orphan], a, b)
    de = 1.0 / np.maximum(de, 1e-3) ** 2
    de /= de.sum(axis=1, keepdims=True)
    W[orphan] = de
    print(f"[skin] {len(orphan)} vertici recuperati con fallback euclideo")

# smoothing laplaciano sui pesi
deg = np.bincount(np.concatenate([E[:, 0], E[:, 1]]), minlength=nv).astype(np.float64)
A = coo_matrix((np.ones(len(E) * 2) / np.concatenate([deg[E[:, 0]], deg[E[:, 1]]]),
                (np.concatenate([E[:, 0], E[:, 1]]),
                 np.concatenate([E[:, 1], E[:, 0]]))), shape=(nv, nv)).tocsr()
for _ in range(6):
    W = 0.45 * W + 0.55 * (A @ W)
    W = np.where(BONE_MASK, W, 0.0)
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
    rows, cols = np.where(keep == j)
    w[rows] = Wk[rows, cols]
    set_vertex_group(mesh_ob, name, w)

# ------------------------------------------------------------- bind + cura --
mesh_ob.parent = arm_ob                      # parent "OBJECT": deforma solo
mesh_ob.parent_type = 'OBJECT'               # il modificatore, non il parent
mesh_ob.matrix_parent_inverse = arm_ob.matrix_world.inverted()
mod = mesh_ob.modifiers.new("Armature", 'ARMATURE')
mod.object = arm_ob
mod.use_vertex_groups = True

# piccola cura: le ciocche davanti al viso non devono seguire la testa in modo
# rigido, altrimenti nei movimenti bruschi "affettano" la faccia. Aggiungo un
# 25% di peso delle catene laterali ai vertici delle ciocche che scendono
# davanti alle spalle (z < 0.80 e y < 0.02, fuori dalla faccia).
z = co[:, 2]
y = co[:, 1]
x = co[:, 0]
strand = (z < 0.80) & (z > 0.60) & (np.abs(x) > 0.035) & (np.abs(x) < 0.115) & (y < 0.035)
print(f"[skin] vertici delle ciocche anteriori: {int(strand.sum())}")
for side, sign in (("L", 1), ("R", -1)):
    sel = strand & (np.sign(x) == sign)
    if not sel.any():
        continue
    vg = mesh_ob.vertex_groups[f"hair_side_01.{side}"]
    vg.add(np.where(sel)[0].tolist(), 0.18, 'ADD')
# rinormalizzo (limite 4 influenza resta valido perche' e' un solo add)
bpy.context.view_layer.objects.active = mesh_ob
bpy.ops.object.vertex_group_limit_total(limit=4)
bpy.ops.object.vertex_group_normalize_all(lock_active=False)

# ------------------------------------------------------------ diagnostica ---
counts = {}
for j, name in enumerate(deform):
    w = np.zeros(nv)
    rows, cols = np.where(keep == j)
    w[rows] = Wk[rows, cols]
    counts[name] = int((w > 0.2).sum() + ((strand) & (np.sign(x) == (1 if name.endswith('.L') else -1))
                                          & name.startswith("hair_side_01")).sum())
print("[skin] vertici con peso > 0.2 per osso:")
for name in deform:
    print(f"   {name:16s} {counts[name]:6d}")
weak = [n for n, c in counts.items() if c < 5]
if weak:
    print("[skin] ATTENZIONE, ossa quasi senza peso:", weak)

tris = sum(len(p.vertices) - 2 for p in me.polygons)
print(f"[final] {len(me.vertices)} verts, {tris} tris, {len(arm_data.bones)} ossa")
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED stage2.blend")
