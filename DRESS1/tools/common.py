"""Utility condivise dalla pipeline DRESS1.

Tutto gira dentro Blender (modulo ``bpy``); nessuna dipendenza esterna oltre a
numpy e a Pillow, gia' presenti nel pacchetto ``bpy``.

Convenzioni di scena
--------------------
* unita' = metro, Z in alto, il davanti del capo guarda **-Y**
* il bordo del pavimento e' a ``z = 0``
* il bordo superiore della fascia in vita e' a ``WAIST_Z``

Le superfici di stoffa sono tutte generate da ``cloth_grid``: una griglia
parametrizzata (u lungo il giro, v dall'alto verso il basso) sulla quale si
applicano pieghe, svasature e orli sagomati.
"""

from __future__ import annotations

import math
import os
import sys

import bpy  # noqa: E402
import bmesh
from mathutils import Vector, Matrix, Quaternion

# --------------------------------------------------------------------------
# costanti del capo (metri)
# --------------------------------------------------------------------------

WAIST_Z = 1.10          # bordo superiore della fascia
WAIST_RX = 0.168        # semiassi del giro vita
WAIST_RY = 0.140
HEM_Z = 0.235           # quota media dell'orlo
TAU = math.tau


# --------------------------------------------------------------------------
# ambiente
# --------------------------------------------------------------------------

def work_dir() -> str:
    return os.environ.get("DRESS1_WORK", "/tmp/dress1_work")


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def reset_scene() -> bpy.types.Scene:
    """Nuova scena vuota con unita' metriche e color management agnostico."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    sc.unit_settings.length_unit = "METERS"
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    return sc


def collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def link(obj: bpy.types.Object, col_name: str = "DRESS1") -> bpy.types.Object:
    col = collection(col_name)
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


# --------------------------------------------------------------------------
# mesh utils
# --------------------------------------------------------------------------

def mesh_from_pydata(name, verts, faces, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    return ob


def bm_to_object(bm, name, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    return ob


def add_solidify(ob, thickness=0.004, offset=-1.0, rim=True):
    m = ob.modifiers.new("Solidify", "SOLIDIFY")
    m.thickness = thickness
    m.offset = offset
    m.use_rim = rim
    m.use_rim_only = False
    m.use_quality_normals = True
    return m


def add_weighted_normals(ob, keep_sharp=True):
    m = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    m.keep_sharp = keep_sharp
    m.weight = 50
    return m


def apply_modifiers(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ob_eval = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ob_eval, preserve_all_data_layers=True,
                                         depsgraph=dg)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)
    return ob


def remove_doubles(ob, dist=1e-5):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def tri_count(ob):
    return sum(max(len(p.vertices) - 2, 0) for p in ob.data.polygons)


# --------------------------------------------------------------------------
# UV
# --------------------------------------------------------------------------

def uv_unwrap(ob, angle=66.0, margin=0.0015, scale=1.0):
    """Smart UV project stabile: nessun operatore che dipenda dal contesto UI."""
    me = ob.data
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle),
                             island_margin=margin,
                             correct_aspect=True,
                             scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    if scale != 1.0:
        for d in me.uv_layers[0].data:
            d.uv = (d.uv[0] * scale, d.uv[1] * scale)


# --------------------------------------------------------------------------
# superfici di stoffa
# --------------------------------------------------------------------------

def ellipse_point(a, rx, ry, z, cx=0.0, cy=0.0):
    """Punto su un'ellisse; ``a`` misurato dall'avanti (-Y) verso +X."""
    return Vector((cx + rx * math.sin(a), cy - ry * math.cos(a), z))


def cloth_grid(name, nu, nv, surf, thickness=0.004, smooth=True,
               uv=(12.0, 12.0), uv_mode="world"):
    """Griglia di stoffa a partire da una funzione di superficie.

    ``surf(u, v)`` con ``u, v`` in [0, 1] restituisce un ``Vector``.
    ``uv_mode='world'`` proietta le UV dall'alto (buono per stoffe quasi
    verticali), ``'param'`` usa direttamente (u * uv[0], v * uv[1]) e
    ``'flat'`` proietta sul piano XY.
    """
    verts = []
    for j in range(nv + 1):
        v = j / nv
        for i in range(nu + 1):
            u = i / nu
            verts.append(surf(u, v))

    faces = []
    for j in range(nv):
        for i in range(nu):
            a = j * (nu + 1) + i
            b = a + 1
            c = a + (nu + 1) + 1
            d = a + (nu + 1)
            faces.append((a, b, c, d))

    ob = mesh_from_pydata(name, verts, faces, smooth=smooth)
    me = ob.data
    uvl = me.uv_layers.new(name="UVMap")
    data = uvl.data
    if uv_mode == "param":
        for poly in me.polygons:
            for li in poly.loop_indices:
                vi = me.loops[li].vertex_index
                j, i = divmod(vi, nu + 1)
                data[li].uv = (i / nu * uv[0], 1.0 - j / nv * uv[1])
    else:
        for poly in me.polygons:
            for li in poly.loop_indices:
                co = me.vertices[me.loops[li].vertex_index].co
                if uv_mode == "flat":
                    data[li].uv = (co.x * uv[0], co.y * uv[1])
                else:
                    data[li].uv = (co.x * uv[0] + co.y * uv[1] * 0.5,
                                   co.z * uv[0] * 0.85)
    if thickness:
        add_solidify(ob, thickness)
    return ob


def pleat(a, v, harmonics, amp):
    """Somma di armoniche in funzione dell'angolo: pieghe verticali."""
    total = 0.0
    for k, phase, w in harmonics:
        total += math.sin(a * k + phase + v * w) / k
    return total * amp


def smoothstep(e0, e1, x):
    if e1 == e0:
        return 0.0 if x < e0 else 1.0
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def ease_out(x, p=2.0):
    return 1.0 - (1.0 - x) ** p


def ease_in(x, p=2.0):
    return x ** p


# --------------------------------------------------------------------------
# luce, camera, render
# --------------------------------------------------------------------------

def setup_world(strength=0.35, color=(0.055, 0.058, 0.065)):
    w = bpy.data.worlds.new("DRESS1_World")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (*color, 1.0)
    bg.inputs[1].default_value = strength
    return w


def add_area(name, loc, target, energy, size, color=(1, 1, 1), shape="SQUARE"):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.size = size
    ld.shape = shape
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    link(ob, "LIGHTS")
    ob.location = loc
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y")
    return ob


def add_camera(name, loc, target, lens=85.0, ortho=None):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    ob = bpy.data.objects.new(name, cd)
    link(ob, "CAMERAS")
    ob.location = loc
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y")
    return ob


def studio_lights(target=(0, 0, 0.72), scale=1.0):
    """Luce da catalogo: key tiepida, fill freddo, rim posteriore."""
    L = []
    L.append(add_area("Key", (2.4 * scale, -2.5 * scale, 2.35 * scale), target,
                      energy=520 * scale ** 2, size=2.4 * scale,
                      color=(1.0, 0.955, 0.90)))
    L.append(add_area("Fill", (-2.8 * scale, -1.9 * scale, 1.05 * scale), target,
                      energy=150 * scale ** 2, size=3.0 * scale,
                      color=(0.80, 0.88, 1.0)))
    L.append(add_area("Rim", (-0.7 * scale, 2.9 * scale, 2.10 * scale), target,
                      energy=420 * scale ** 2, size=1.6 * scale,
                      color=(1.0, 0.94, 0.86)))
    L.append(add_area("Top", (0.0, 0.3 * scale, 3.4 * scale), target,
                      energy=180 * scale ** 2, size=2.0 * scale,
                      color=(1.0, 0.98, 0.95)))
    return L


def render_to(path, res=(900, 1200), samples=96, transparent=False, denoise=True):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.cycles.samples = samples
    sc.cycles.use_denoising = denoise
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path
