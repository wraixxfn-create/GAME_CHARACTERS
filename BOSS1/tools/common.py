"""Utility condivise per la pipeline BOSS1 (Blender headless).

La pipeline e' divisa in step numerati; ogni step salva un .blend intermedio in
`$BOSS1_WORK` (default `/home/user/work`, fuori dal repository) e l'ultimo
produce i file finali in `BOSS1/`.
"""
import bpy
import math
import mathutils
import numpy as np
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # BOSS1/
SRC_BLEND = os.path.join(HERE, "ImageToStl.com_monster+3d+model.blend")
# cartella di lavoro per i .blend intermedi (fuori dal repo)
WORK = os.environ.get("BOSS1_WORK", "/home/user/work")
os.makedirs(WORK, exist_ok=True)

# convenzioni del personaggio (unita' del file sorgente, ~0.87 m di altezza)
HEIGHT = 0.868


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
    """Vertici di ogni faccia come array (m, k) int32 (k = 3 dopo la
    triangolazione, 4 se restano dei quad)."""
    return np.array([p.vertices[:] for p in me.polygons], dtype=np.int32)


def curvature_scores(me):
    """Score di dettaglio per vertice: 0 = superficie piatta/liscia,
    1 = spigolo vivo (punte, artigli, solchi). Usa l'angolo tra le normali
    dei vertici collegati da uno spigolo."""
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


def set_vertex_group(ob, name, weights):
    """Crea/sovrascrive un vertex group con i pesi dati (array per vertice)."""
    vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
    vg.remove(range(len(ob.data.vertices)))
    # add() in blocchi di vertici con lo stesso peso quantizzato: molto piu'
    # veloce che una chiamata per vertice su mesh da 40k vertici.
    q = np.round(np.asarray(weights, dtype=np.float64) * 200).astype(np.int32)
    for w in np.unique(q):
        if w <= 0:
            continue
        idx = np.where(q == w)[0].tolist()
        vg.add(idx, float(w) / 200.0, 'REPLACE')
    return vg


def region_masks(co):
    """Maschere delle zone che meritano piu' densita' di triangoli."""
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    head = (z > 0.62) & (y < 0.02)                     # testa, muso, mascella
    halo = (z > 0.66) & (np.abs(x) < 0.20) & (y < 0.12)  # aureola di spine
    hands = (z < 0.17) & (np.abs(x) > 0.28)            # mani e artigli
    feet = (z < 0.12) & (np.abs(x) <= 0.28)            # piedi
    return {"head": head, "halo": halo, "hands": hands, "feet": feet}
