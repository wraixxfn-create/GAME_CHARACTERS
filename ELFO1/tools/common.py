"""Utility condivise per la pipeline ELFO1 (Blender headless).

La pipeline e' divisa in step numerati; ogni step salva un .blend intermedio in
`$ELFO1_WORK` (default `/home/user/work/elfo`, fuori dal repository) e l'ultimo
produce i file finali in `ELFO1/`.

Convenzioni del modello sorgente (export Tripo/ImageToStl):

  * mesh Y-up nel file, con la rotazione -90deg su X appesa agli empty:
    dopo `purge_scene_extras()` la scena e' **Z-up** e la mesh e' applicata
    (location/rotation/scale = identita');
  * altezza 1,000 unita' con i piedi a z = 0, il viso verso **-Y**;
  * 339.022 triangoli, 168.853 vertici, 1 UV set, texture 4096^2 impacchettate.
"""
import bpy
import mathutils
import numpy as np
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ELFO1/
SRC_BLEND = os.path.join(HERE, "ImageToStl.com_elf+character+3d+model(1).blend")
# cartella di lavoro per i .blend intermedi (fuori dal repo)
WORK = os.environ.get("ELFO1_WORK", "/home/user/work/elfo")
os.makedirs(WORK, exist_ok=True)

# altezza del sorgente (unita' del file, piedi a z=0, testa a z=1.0)
SRC_HEIGHT = 1.0
# altezza finale in metri: elfo alto e slanciato
TARGET_HEIGHT = 1.85
# fattore di scala applicato all'ultimo step
SCALE = TARGET_HEIGHT / SRC_HEIGHT


def open_src():
    bpy.ops.wm.open_mainfile(filepath=SRC_BLEND)


def get_mesh():
    return next(o for o in bpy.data.objects if o.type == 'MESH')


def get_rig():
    return next(o for o in bpy.data.objects if o.type == 'ARMATURE')


def purge_scene_extras():
    """Tiene solo la mesh: sgancia i figli dagli empty (conservando la posizione
    nel mondo, perche' la rotazione -90deg su X sta sugli empty di ImageToStl)
    e poi cancella tutto il resto."""
    for ob in bpy.data.objects:
        if ob.parent is not None:
            mw = ob.matrix_world.copy()
            ob.parent = None
            ob.matrix_world = mw
    for ob in list(bpy.data.objects):
        if ob.type != 'MESH':
            bpy.data.objects.remove(ob, do_unlink=True)


def apply_matrix(ob):
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def tri_count(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


# --------------------------------------------------------------- geometria --

def vertex_array(me, attr="co"):
    """Coordinate (o normali) dei vertici come array (n, 3) float32."""
    n = len(me.vertices)
    arr = np.empty(n * 3, dtype=np.float32)
    if attr == "co":
        me.vertices.foreach_get("co", arr)
    else:
        me.vertex_normals.foreach_get("vector", arr)
    return arr.reshape(-1, 3)


def edge_array(me):
    e = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", e)
    return e.reshape(-1, 2)


def triangle_array(me):
    return np.array([p.vertices[:] for p in me.polygons], dtype=np.int32)


def curvature_scores(me):
    """Score di dettaglio per vertice: 0 = superficie piatta/liscia,
    1 = spigolo vivo (punta dell'orecchio, pieghe del viso, ciocche)."""
    co = vertex_array(me)
    nrm = vertex_array(me, "normal")
    E = edge_array(me)
    if len(E) == 0:
        return np.zeros(len(co), dtype=np.float32)
    d = np.abs(np.einsum("ij,ij->i", nrm[E[:, 0]], nrm[E[:, 1]]))
    sharp = 1.0 - np.clip(d, 0.0, 1.0)
    acc = np.zeros(len(co), dtype=np.float64)
    cnt = np.zeros(len(co), dtype=np.float64)
    np.add.at(acc, E[:, 0], sharp)
    np.add.at(acc, E[:, 1], sharp)
    np.add.at(cnt, E[:, 0], 1.0)
    np.add.at(cnt, E[:, 1], 1.0)
    score = acc / np.maximum(cnt, 1.0)
    hi = np.percentile(score, 97)
    if hi <= 0:
        return np.zeros(len(co), dtype=np.float32)
    return np.clip(score / hi, 0.0, 1.0).astype(np.float32)


def smoothstep(x, a, b):
    t = np.clip((np.asarray(x, dtype=np.float64) - a) / max(b - a, 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def set_vertex_group(ob, name, weights, quant=1000.0):
    """Crea/sovrascrive un vertex group con i pesi dati (array per vertice)."""
    vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
    vg.remove(range(len(ob.data.vertices)))
    q = np.round(np.asarray(weights, dtype=np.float64) * quant).astype(np.int64)
    for w in np.unique(q):
        if w <= 0:
            continue
        idx = np.where(q == w)[0].tolist()
        vg.add(idx, float(w) / quant, 'REPLACE')
    return vg


# -------------------------------------------------------- regioni anatomici --

def region_masks(co):
    """Maschere delle zone che meritano piu' densita' di triangoli.

    Coordinate: z = altezza (0 piedi, 1 cima dei capelli), -y = davanti,
    x = fianco (destra del personaggio = +x visto di fronte? no: +x e' la
    sinistra schermo quando lo si guarda in faccia, quindi la sua sinistra).
    """
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    face = (z > 0.82) & (y < 0.05)                       # viso, orecchie, cresta
    hair = (z > 0.58) & ((y > 0.045) | ((np.abs(x) > 0.052) & (z > 0.66)))
    hands = (np.abs(x) > 0.195) & (z < 0.66)             # mani e dita
    feet = (z < 0.095)                                   # caviglie, piedi, sandali
    # tessuto: gonnellone e cintura (dalla vita in giu', fuori dalle gambe)
    cloth = (z > 0.13) & (z < 0.475) & ((np.abs(y) > 0.052) | (np.abs(x) > 0.085))
    hem = cloth & (z < 0.30)                       # falde, dove servono i contorni
    return {"face": face, "hair": hair, "hands": hands, "feet": feet,
            "cloth": cloth, "hem": hem}


def world_bbox(ob):
    """Bounding box world della mesh valutata (con le modificatori applicati)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    m = ev.to_mesh()
    c = np.empty(len(m.vertices) * 3)
    m.vertices.foreach_get("co", c)
    c = c.reshape(-1, 3)
    mn, mx = c.min(0), c.max(0)
    ev.to_mesh_clear()
    return mathutils.Vector(mn), mathutils.Vector(mx)
