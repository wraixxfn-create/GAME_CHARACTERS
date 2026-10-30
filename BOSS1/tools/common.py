"""Utility condivise per la pipeline BOSS1 (Blender headless).

La pipeline e' divisa in step numerati; ogni step salva un .blend intermedio in
`/home/user/work/` e l'ultimo produce i file finali in `BOSS1/`.
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


def open_src():
    bpy.ops.wm.open_mainfile(filepath=SRC_BLEND)


def get_mesh():
    return next(o for o in bpy.data.objects if o.type == 'MESH')


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
