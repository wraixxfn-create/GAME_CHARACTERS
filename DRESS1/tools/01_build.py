"""DRESS1 — costruzione della geometria (v5, dettagli dal concept).

Il capo e' ridisegnato da zero seguendo il concept: gonna in lino avorio a pieghe
fitte, fascia incrociata in vita con anello d'ottone, staffa scura con simboli
geometrici dorati, scialli scuri sui fianchi con rune, caviglie fasciate e
sandali aperti.

La gonna e i lembi usano la stessa superficie ``surface(a, z, layer)`` e lo
stesso spostamento di piega. Gli scialli hanno uno strato piu' teso; staffa e
ricami condividono la rispettiva superficie di appoggio.

Quote (metri, Z in alto, davanti = -Y):

```
z = 1.090  bordo alto della fascia (ai fianchi)
z = 1.026  cintura scura + anello
z = 0.945  fondo della fascia
z = 0.964  attacco della gonna
z = 0.290  orlo medio (falde piu' lunghe sotto)
z = 0.000  pavimento
```
"""

from __future__ import annotations

import math
import os
import sys

import bpy  # noqa: E402  (deve precedere bmesh)
import bmesh
from mathutils import Matrix, Vector, noise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (TAU, cloth_grid, ensure_dir, mesh_from_pydata, reset_scene,
                    smoothstep, work_dir)

# --------------------------------------------------------------------------
# quote e profilo
# --------------------------------------------------------------------------

SASH_BOT_Z = 0.945
WAIST_RX = 0.152
WAIST_RY = 0.126

SKIRT_TOP_Z = 0.964
LEG_X = 0.110

# (z, rx, ry) — profilo a campana, svasatura dolce
PROFILE = [
    (0.964, 0.152, 0.128),
    (0.900, 0.157, 0.133),
    (0.800, 0.166, 0.142),
    (0.700, 0.179, 0.151),
    (0.600, 0.190, 0.160),
    (0.500, 0.202, 0.170),
    (0.430, 0.211, 0.178),
    (0.370, 0.220, 0.185),
    (0.330, 0.224, 0.188),
    (0.290, 0.225, 0.189),
    (0.250, 0.223, 0.187),
    (0.210, 0.219, 0.184),
    (0.170, 0.215, 0.181),
]

# offset di raggio per strato (m)
LAYER = {
    "under": -0.045,
    "base": 0.000,
    "lapB": 0.019,
    "lap": 0.030,
    "lap2": 0.043,
    "lap3": 0.055,
    "drape": 0.073,
    "drape2": 0.085,
    "trim": 0.091,
    "strap": 0.082,
}


def prof(z):
    pts = PROFILE
    if z >= pts[0][0]:
        return pts[0][1], pts[0][2]
    if z <= pts[-1][0]:
        return pts[-1][1], pts[-1][2]
    for i in range(len(pts) - 1):
        z0, x0, y0 = pts[i]
        z1, x1, y1 = pts[i + 1]
        if z1 <= z <= z0:
            t = (z0 - z) / (z0 - z1)
            t = t * t * (3.0 - 2.0 * t)
            return x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
    return pts[-1][1], pts[-1][2]


def radius(z, layer="base"):
    rx, ry = prof(z)
    o = LAYER[layer]
    return rx + o, ry + o


def surface(a, z, layer="base", extra=0.0):
    """Punto sulla gonna: ``a`` e' l'angolo misurato dall'avanti verso +X."""
    rx, ry = radius(z, layer)
    rx += extra
    ry += extra
    return Vector((rx * math.sin(a), -ry * math.cos(a), z))


def normal_dir(a):
    return Vector((math.sin(a), -math.cos(a), 0.0)).normalized()


def fbm(p, octaves=3, lac=2.0, gain=0.5):
    amp, freq, total = 1.0, 1.0, 0.0
    for _ in range(octaves):
        total += amp * noise.noise(Vector(p) * freq)
        freq *= lac
        amp *= gain
    return total


def wrinkle(p, amp=0.002, freq=6.0, seed=0.0):
    q = (p[0] * freq + seed, p[1] * freq - seed * 0.7, p[2] * freq * 0.5)
    return fbm(q, 3) * amp


def lerp_table(table, v):
    """Interpola una tabella [(v, valore), ...] con smorzamento morbido."""
    if v <= table[0][0]:
        return table[0][1]
    if v >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        v0, a0 = table[i]
        v1, a1 = table[i + 1]
        if v0 <= v <= v1:
            t = (v - v0) / (v1 - v0) if v1 > v0 else 0.0
            t = t * t * (3.0 - 2.0 * t)
            return a0 + (a1 - a0) * t
    return table[-1][1]


def hem_z(a):
    """Quota dell'orlo della gonna: discesa morbida con due punte larghe."""
    lobes = (0.042 * max(0.0, math.sin(a * 1.0 + 0.25)) ** 1.4
             + 0.022 * max(0.0, math.sin(a * 2.0 - 1.05)) ** 1.6
             + 0.010 * max(0.0, math.sin(a * 3.0 + 2.2)) ** 2.0)
    return 0.292 - lobes


# --------------------------------------------------------------------------
# primitive
# --------------------------------------------------------------------------

def mesh_obj(name, verts, faces, smooth=True, thickness=0.0, offset=0.0):
    ob = mesh_from_pydata(name, verts, faces, smooth=smooth)
    if thickness:
        from common import add_solidify
        add_solidify(ob, thickness, offset=offset)
    return ob


def ribbon(name, pts, width, thickness=0.0028, up=(0, 0, 1), widths=None):
    pts = [Vector(p) for p in pts]
    n = len(pts)
    verts, faces = [], []
    up = Vector(up)
    for i, p in enumerate(pts):
        if i == 0:
            d = pts[1] - pts[0]
        elif i == n - 1:
            d = pts[-1] - pts[-2]
        else:
            d = pts[i + 1] - pts[i - 1]
        t = d.normalized() if d.length > 1e-9 else Vector((0, 0, 1))
        side = t.cross(up)
        if side.length < 1e-6:
            side = t.cross(Vector((1, 0, 0)))
        side.normalize()
        w = widths[i] if widths is not None else width
        verts.append(p - side * (w * 0.5))
        verts.append(p + side * (w * 0.5))
    for i in range(n - 1):
        a = i * 2
        faces.append((a, a + 1, a + 3, a + 2))
    return mesh_obj(name, verts, faces, smooth=True, thickness=thickness)


def ribbon_n(name, pts, normals, width, thickness=0.0016, widths=None):
    """Nastro appoggiato su una superficie: la larghezza sta nel piano tangente.

    ``normals`` e' la normale alla superficie in ogni punto: la direzione di
    larghezza e' ``normale x tangente``, quindi il nastro non "taglia" mai la
    stoffa ne' si solleva ai bordi.
    """
    pts = [Vector(p) for p in pts]
    n = len(pts)
    verts, faces = [], []
    for i, p in enumerate(pts):
        if i == 0:
            d = pts[1] - pts[0]
        elif i == n - 1:
            d = pts[-1] - pts[-2]
        else:
            d = pts[i + 1] - pts[i - 1]
        t = d.normalized() if d.length > 1e-9 else Vector((0, 0, 1))
        nrm = Vector(normals[i]).normalized()
        side = nrm.cross(t)
        if side.length < 1e-6:
            side = Vector((1, 0, 0))
        side.normalize()
        w = widths[i] if widths is not None else width
        verts.append(p - side * (w * 0.5))
        verts.append(p + side * (w * 0.5))
    for i in range(n - 1):
        a = i * 2
        faces.append((a, a + 1, a + 3, a + 2))
    return mesh_obj(name, verts, faces, smooth=True, thickness=thickness)


def tube(name, pts, radius, segs=8, caps=True):
    pts = [Vector(p) for p in pts]
    n = len(pts)
    verts, faces = [], []
    up = Vector((0, 0, 1))
    prev_side = None
    for i, p in enumerate(pts):
        if i == 0:
            t = (pts[1] - pts[0]).normalized()
        elif i == n - 1:
            t = (pts[-1] - pts[-2]).normalized()
        else:
            t = (pts[i + 1] - pts[i - 1]).normalized()
        if prev_side is None:
            side = t.cross(up)
            if side.length < 1e-5:
                side = t.cross(Vector((1, 0, 0)))
            side.normalize()
        else:
            side = (prev_side - t * prev_side.dot(t)).normalized()
        prev_side = side
        nrm = t.cross(side).normalized()
        r = radius(i / (n - 1)) if callable(radius) else radius
        for k in range(segs):
            a = TAU * k / segs
            verts.append(p + side * (math.cos(a) * r) + nrm * (math.sin(a) * r))
    for i in range(n - 1):
        for k in range(segs):
            a = i * segs + k
            b = i * segs + (k + 1) % segs
            c = (i + 1) * segs + (k + 1) % segs
            d = (i + 1) * segs + k
            faces.append((a, b, c, d))
    if caps:
        c0 = len(verts)
        verts.append(pts[0])
        for k in range(segs):
            faces.append((c0, (k + 1) % segs, k))
        c1 = len(verts)
        verts.append(pts[-1])
        last = (n - 1) * segs
        for k in range(segs):
            faces.append((c1, last + k, last + (k + 1) % segs))
    return mesh_obj(name, verts, faces)


def torus(name, center, axis, major, minor, seg_major=64, seg_minor=14,
          squash=1.0):
    axis = Vector(axis).normalized()
    ref = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
    u = axis.cross(ref).normalized()
    v = axis.cross(u).normalized()
    c = Vector(center)
    verts, faces = [], []
    for i in range(seg_major):
        a = TAU * i / seg_major
        d = u * math.cos(a) + v * math.sin(a) * squash
        for k in range(seg_minor):
            b = TAU * k / seg_minor
            verts.append(c + d * (major + minor * math.cos(b))
                         + axis * (minor * math.sin(b)))
    for i in range(seg_major):
        for k in range(seg_minor):
            a = i * seg_minor + k
            b = ((i + 1) % seg_major) * seg_minor + k
            cc = ((i + 1) % seg_major) * seg_minor + (k + 1) % seg_minor
            d = i * seg_minor + (k + 1) % seg_minor
            faces.append((a, b, cc, d))
    return mesh_obj(name, verts, faces)


def ellipsoid(name, center, radii, segs=16, rings=10):
    cx, cy, cz = center
    rx, ry, rz = radii
    verts, faces = [], []
    for j in range(rings + 1):
        phi = math.pi * j / rings
        sp, cp = math.sin(phi), math.cos(phi)
        for i in range(segs):
            th = TAU * i / segs
            verts.append(Vector((cx + rx * sp * math.cos(th),
                                 cy + ry * sp * math.sin(th),
                                 cz + rz * cp)))
    for j in range(rings):
        for i in range(segs):
            a = j * segs + i
            b = j * segs + (i + 1) % segs
            c = (j + 1) * segs + (i + 1) % segs
            d = (j + 1) * segs + i
            faces.append((a, b, c, d))
    return mesh_obj(name, verts, faces)


def loft(name, sections, rings=24, cap_bottom=True, cap_top=True):
    verts, faces = [], []
    for c, rx, ry in sections:
        for i in range(rings):
            a = TAU * i / rings
            verts.append(Vector((c[0] + rx * math.cos(a),
                                 c[1] + ry * math.sin(a), c[2])))
    for k in range(len(sections) - 1):
        for i in range(rings):
            a = k * rings + i
            b = k * rings + (i + 1) % rings
            c = (k + 1) * rings + (i + 1) % rings
            d = (k + 1) * rings + i
            faces.append((a, b, c, d))
    if cap_bottom:
        i0 = len(verts)
        verts.append(Vector(sections[0][0]))
        for i in range(rings):
            faces.append((i0, (i + 1) % rings, i))
    if cap_top:
        i1 = len(verts)
        verts.append(Vector(sections[-1][0]))
        last = (len(sections) - 1) * rings
        for i in range(rings):
            faces.append((i1, last + i, last + (i + 1) % rings))
    return mesh_obj(name, verts, faces)


# --------------------------------------------------------------------------
# gambe e piedi
# --------------------------------------------------------------------------

LEG_PROFILE = [
    (0.985, 0.074, 0.072, 0.008),
    (0.900, 0.069, 0.068, 0.010),
    (0.780, 0.062, 0.061, 0.012),
    (0.650, 0.054, 0.054, 0.010),
    (0.545, 0.048, 0.049, 0.004),
    (0.470, 0.045, 0.048, -0.002),
    (0.410, 0.045, 0.052, -0.007),
    (0.350, 0.044, 0.054, -0.010),
    (0.290, 0.040, 0.047, -0.012),
    (0.235, 0.034, 0.039, -0.013),
    (0.185, 0.029, 0.033, -0.013),
    (0.140, 0.026, 0.029, -0.014),
    (0.108, 0.025, 0.030, -0.014),
]


def leg_radius(z, side_x):
    """Centro (x, y) e semiassi della gamba alla quota z (interpolati)."""
    tbl = LEG_PROFILE
    z = min(max(z, tbl[-1][0]), tbl[0][0])
    for i in range(len(tbl) - 1):
        z0, x0, y0, dy0 = tbl[i]
        z1, x1, y1, dy1 = tbl[i + 1]
        if z1 <= z <= z0:
            t = (z0 - z) / (z0 - z1)
            t = t * t * (3.0 - 2.0 * t)
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            dy = dy0 + (dy1 - dy0) * t
            return x, y, dy
    z0, x0, y0, dy0 = tbl[-1]
    return x0, y0, dy0


def leg_center_x(z):
    # Le gambe si allargano solo sotto la gonna; ai fianchi restano all'interno
    # della fascia anche con una posa dei piedi piu' aperta.
    return 0.070 + (LEG_X - 0.070) * (1.0 - smoothstep(0.24, 0.90, z))


def build_legs():
    objs = []
    for side, sx in (("L", 1.0), ("R", -1.0)):
        secs = []
        for (z, rx, ry, dy) in LEG_PROFILE:
            cx = sx * (leg_center_x(z) + 0.004 * (1.0 - z))
            secs.append(((cx, dy, z), rx, ry))
        secs.sort(key=lambda s: s[0][2])
        objs.append(loft(f"Leg_{side}", secs, rings=24))
    return objs


FOOT_SECTIONS = [
    # (y, mezza larghezza, altezza totale, centro z)
    (0.070, 0.033, 0.104, 0.052),
    (0.040, 0.038, 0.112, 0.058),
    (0.006, 0.041, 0.100, 0.054),
    (-0.032, 0.044, 0.082, 0.046),
    (-0.072, 0.046, 0.066, 0.037),
    (-0.110, 0.047, 0.052, 0.029),
    (-0.142, 0.044, 0.042, 0.023),
    (-0.167, 0.037, 0.035, 0.019),
    (-0.183, 0.027, 0.029, 0.016),
    (-0.191, 0.016, 0.022, 0.014),
]


def build_feet():
    objs = []
    for side, sx in (("L", 1.0), ("R", -1.0)):
        base = Vector((sx * LEG_X, -0.014, 0.0))
        rot = Matrix.Rotation(math.radians(14.0) * sx, 4, "Z")
        rings = 22
        verts, faces = [], []
        for (y, hw, hz, cy) in FOOT_SECTIONS:
            for i in range(rings):
                a = TAU * i / rings
                ca, sa = math.cos(a), math.sin(a)
                e = 2.6
                px = math.copysign(abs(ca) ** (2.0 / e), ca) * hw
                pz = math.copysign(abs(sa) ** (2.0 / e), sa) * (hz * 0.5)
                z = max(cy + pz, 0.0035)
                verts.append(base + rot @ Vector((px, y, z)))
        for k in range(len(FOOT_SECTIONS) - 1):
            for i in range(rings):
                a = k * rings + i
                b = k * rings + (i + 1) % rings
                c = (k + 1) * rings + (i + 1) % rings
                d = (k + 1) * rings + i
                faces.append((a, b, c, d))
        c0 = len(verts)
        verts.append(base + rot @ Vector((0, FOOT_SECTIONS[0][0] + 0.012, 0.048)))
        for i in range(rings):
            faces.append((c0, (i + 1) % rings, i))
        c1 = len(verts)
        verts.append(base + rot @ Vector((0, FOOT_SECTIONS[-1][0] - 0.006, 0.014)))
        last = (len(FOOT_SECTIONS) - 1) * rings
        for i in range(rings):
            faces.append((c1, last + i, last + (i + 1) % rings))
        objs.append(mesh_obj(f"Foot_{side}", verts, faces))
        # dita: cinque cuscinetti sulla punta, arco naturale
        toes = [(-0.030, -0.186, 0.0105), (-0.014, -0.193, 0.0098),
                (0.002, -0.192, 0.0090), (0.017, -0.186, 0.0080),
                (0.030, -0.177, 0.0068)]
        for k, (fx, fy, r) in enumerate(toes):
            objs.append(ellipsoid(f"Toe_{side}{k}",
                                  base + rot @ Vector((fx, fy, 0.012 + r * 0.25)),
                                  (r * 1.05, r * 1.5, r * 0.9), segs=14, rings=10))
    return objs


# --------------------------------------------------------------------------
# fasciature e sandali
# --------------------------------------------------------------------------

def wrap_band(name, sx, z_center, dip, width, thick_off=0.0035, n=56):
    """Banda attorno alla gamba che segue davvero la superficie della gamba."""
    verts, faces = [], []
    for i in range(n + 1):
        t = i / n
        a = TAU * t
        # la banda scende a V sul davanti
        z = z_center - dip * (0.5 + 0.5 * math.cos(a))
        rx, ry, dy = leg_radius(z, sx)
        rx += thick_off
        ry += thick_off
        for zz in (z - width * 0.5, z + width * 0.5):
            rx2, ry2, dy2 = leg_radius(zz, sx)
            verts.append(Vector((sx * (LEG_X + 0.004 * (1 - zz)) + (rx2 + thick_off) * math.cos(a),
                                 dy2 + (ry2 + thick_off) * math.sin(a), zz)))
    for i in range(n):
        a = i * 2
        faces.append((a, a + 1, a + 3, a + 2))
    return mesh_obj(name, verts, faces, thickness=0.0032)


def build_legwraps():
    """Caviglie fasciate: due bande scure e un nastro diagonale.

    Nel concept si vedono bande separate da pelle: qui la pelle resta scoperta
    fra una banda e l'altra, altrimenti la caviglia diventa un tubo nero.
    """
    objs = []
    for side, sx in (("L", 1.0), ("R", -1.0)):
        sgn = 1.0 if sx > 0 else -1.0
        # due bande larghe con una finestra di pelle in mezzo
        for k, (zc, dip, w) in enumerate(((0.124, 0.012, 0.016),
                                          (0.176, 0.016, 0.013),
                                          (0.222, 0.020, 0.015))):
            objs.append(wrap_band(f"AnkleBand_{side}{k}", sgn, zc, dip, w))
        # nastro diagonale che sale incrociando le due bande
        verts, faces = [], []
        n = 72
        for i in range(n + 1):
            t = i / n
            z = 0.120 + 0.112 * t
            a = TAU * (0.30 + 1.05 * t) * sgn
            for da in (-0.13, 0.13):
                aa = a + da
                zz = z + da * 0.11
                rx2, ry2, dy2 = leg_radius(zz, sgn)
                verts.append(Vector((sgn * (LEG_X + 0.004 * (1 - zz))
                                     + (rx2 + 0.0045) * math.cos(aa),
                                     dy2 + (ry2 + 0.0045) * math.sin(aa), zz)))
        for i in range(n):
            a = i * 2
            faces.append((a, a + 1, a + 3, a + 2))
        objs.append(mesh_obj(f"AnkleSpiral_{side}", verts, faces, thickness=0.0032))
        # coda del nastro che pende di lato
        pts = []
        for i in range(7):
            t = i / 6
            z = 0.232 - 0.032 * t
            a = (2.9 - 0.8 * t) * sgn
            rx, ry, dy = leg_radius(z, sgn)
            pts.append((sgn * (LEG_X + 0.004 * (1 - z))
                        + (rx + 0.009) * math.cos(a),
                        dy + (ry + 0.009) * math.sin(a), z))
        objs.append(ribbon(f"AnkleTail_{side}", pts, 0.013, thickness=0.003,
                           up=(0, 0, 1)))
    return objs


SOLE_OUTLINE = [
    (0.028, 0.060), (0.042, 0.036), (0.047, -0.010), (0.052, -0.070),
    (0.050, -0.126), (0.042, -0.166), (0.026, -0.190), (0.000, -0.198),
    (-0.026, -0.190), (-0.042, -0.166), (-0.048, -0.120), (-0.047, -0.062),
    (-0.043, 0.008), (-0.034, 0.048), (-0.010, 0.064),
]


def foot_top(y):
    """Quota della superficie superiore del piede alla coordinata y."""
    tbl = FOOT_SECTIONS
    if y >= tbl[0][0]:
        _, _, hz, cy = tbl[0]
        return cy + hz * 0.5
    if y <= tbl[-1][0]:
        _, _, hz, cy = tbl[-1]
        return cy + hz * 0.5
    for i in range(len(tbl) - 1):
        y0, hw0, hz0, cy0 = tbl[i]
        y1, hw1, hz1, cy1 = tbl[i + 1]
        if y1 <= y <= y0:
            t = (y0 - y) / (y0 - y1)
            return (cy0 + hz0 * 0.5) * (1 - t) + (cy1 + hz1 * 0.5) * t
    return 0.02


def foot_halfwidth(y):
    tbl = FOOT_SECTIONS
    if y >= tbl[0][0]:
        return tbl[0][1]
    if y <= tbl[-1][0]:
        return tbl[-1][1]
    for i in range(len(tbl) - 1):
        y0, hw0, _, _ = tbl[i]
        y1, hw1, _, _ = tbl[i + 1]
        if y1 <= y <= y0:
            t = (y0 - y) / (y0 - y1)
            return hw0 * (1 - t) + hw1 * t
    return 0.03


def build_sandals():
    """Sandalo aperto: suola avorio e fascette scure appoggiate sul dorso."""
    objs = []
    for side, sx in (("L", 1.0), ("R", -1.0)):
        base = Vector((sx * LEG_X, -0.014, 0.0))
        rot = Matrix.Rotation(math.radians(14.0) * sx, 4, "Z")

        def P(x, y, z):
            return base + rot @ Vector((x, y, z))

        # --- suola: profilo del piede, bordo vivo, spessore 12 mm
        verts, faces = [], []
        for (z, sc) in ((-0.003, 0.95), (0.004, 1.02), (0.012, 1.0)):
            for (px, py) in SOLE_OUTLINE:
                verts.append(P(px * sc, py * sc, z))
        m = len(SOLE_OUTLINE)
        for ring in range(2):
            for i in range(m):
                a = ring * m + i
                b = ring * m + (i + 1) % m
                faces.append((a, b, b + m, a + m))
        faces.append(tuple(range(m - 1, -1, -1)))
        faces.append(tuple(range(2 * m, 3 * m)))
        objs.append(mesh_obj(f"Sole_{side}", verts, faces))

        # --- fascette: seguono il dorso del piede (y -> z dalla tabella)
        def strap(name, waypoints, width, thick=0.0042):
            """Cinturino appoggiato sul dorso del piede.

            La normale viene dal centro della sezione: cosi' il nastro resta
            aderente e non "gira" nei tratti quasi verticali.
            """
            pts, nrm = [], []
            for (x, y, lift) in waypoints:
                z = foot_top(y) + lift
                p = P(x, y, z)
                pts.append(p)
                # normale esterna: dal centro del piede verso il punto
                c = P(0.0, y, max(foot_top(y) * 0.45, 0.01))
                n = (p - c)
                n.z = max(n.z, 0.25 * n.length)
                nrm.append(n.normalized())
            objs.append(ribbon_n(name, pts, nrm, width, thickness=thick))

        # Y rovesciata: dal mignolo al pollice passando fra le dita
        strap(f"SandalDig_{side}", [
            (0.044, -0.050, 0.004), (0.042, -0.066, 0.005),
            (0.038, -0.084, 0.006), (0.031, -0.104, 0.006),
            (0.021, -0.126, 0.005), (0.008, -0.146, 0.004),
            (-0.006, -0.162, 0.003), (-0.020, -0.172, 0.002),
            (-0.032, -0.176, 0.001)], 0.015)
        # traversa sull'avampiede
        strap(f"SandalCross_{side}", [
            (-0.046, -0.014, 0.004), (-0.038, -0.030, 0.005),
            (-0.026, -0.044, 0.006), (-0.012, -0.054, 0.007),
            (0.000, -0.058, 0.007), (0.014, -0.055, 0.006),
            (0.028, -0.048, 0.006), (0.040, -0.038, 0.005),
            (0.047, -0.026, 0.004)], 0.016)
        # cinturino verticale che unisce traversa e suola
        strap(f"SandalRiser_{side}", [
            (0.000, -0.058, 0.008), (0.002, -0.070, 0.006),
            (0.004, -0.082, 0.004), (0.005, -0.094, 0.003),
            (0.006, -0.102, 0.002)], 0.011)
        # cinturino al tallone
        pts = []
        for i in range(9):
            t = i / 8
            ang = math.pi * (0.04 + 0.92 * t)
            pts.append(P(math.cos(ang) * 0.036, 0.050 + 0.010 * math.sin(ang),
                         0.006 + math.sin(ang) * 0.062))
        objs.append(ribbon(f"HeelStrap_{side}", pts, 0.014, thickness=0.005,
                           up=(0, 1, 0)))
    return objs


# --------------------------------------------------------------------------
# gonna
# --------------------------------------------------------------------------

def pleats(a, v, seed=0.0, n=26, amp=1.0, hem_fade=0.0):
    """Pieghe continue e leggermente irregolari, non un dente di sega.

    Le armoniche intere chiudono senza discontinuita' sul retro. Una piccola
    deriva lungo la lunghezza evita che le pieghe sembrino scanalature rigide.
    """
    n = max(2, int(n))
    drift = 0.30 * math.sin(v * 2.4 + seed * 0.31) * smoothstep(0.05, 0.8, v)
    phase = n * a + seed + drift
    fold = (0.62 * math.cos(phase)
            + 0.20 * math.cos(phase * 2.0 - 0.35)
            + 0.18 * math.cos((n // 2) * a + 0.55 + v * 0.3))
    envelope = 0.35 + 0.65 * smoothstep(0.0, 0.20, v)
    if hem_fade:
        envelope *= 1.0 - hem_fade * smoothstep(0.88, 1.0, v)
    return amp * fold * envelope


def skirt_disp(a, z):
    """Spostamento radiale della gonna, condiviso da tutti gli strati.

    Il tratto scende dall'alto all'orlo: la distanza e' positiva. Usare il
    segno opposto azzerava le pieghe per ogni lembo e causava compenetrazioni.
    """
    span = SKIRT_TOP_Z - hem_z(a)
    v = min(1.0, max(0.0, (SKIRT_TOP_Z - z) / max(span, 1e-6)))
    f = pleats(a, v, 0.0, n=13, amp=0.021, hem_fade=0.25)
    f += 0.0012 * math.sin(a * 39.0 + v * 1.6) * smoothstep(0.05, 0.5, v)
    return f


def build_underskirt():
    nu, nv = 150, 36
    z_top = SKIRT_TOP_Z - 0.006
    z_bot = 0.252

    def surf(u, v):
        a = TAU * u
        z = z_top + (z_bot - z_top) * v ** 1.02
        rx, ry = radius(z, "under")
        f = pleats(a, v, 0.4, n=9, amp=0.0030, hem_fade=1.0)
        p = surface(a, z, "under", extra=f)
        p += normal_dir(a) * wrinkle(p, 0.0006, 11.0, 1.3)
        return p

    return [cloth_grid("UnderSkirt", nu, nv, surf, thickness=0.003)]


def build_skirt():
    """Gonna principale: pieghe fitte, orlo irregolare."""
    nu, nv = 240, 64

    def surf(u, v):
        a = TAU * u
        z = SKIRT_TOP_Z + (hem_z(a) - SKIRT_TOP_Z) * v ** 1.02
        # Anche i lembi chiamano questa funzione: bordi e creste coincidono.
        p = surface(a, z, "base", extra=skirt_disp(a, z))
        # rumore basso: se e' troppo forte la crease della piega si
        # spezza in dentini visibili in controluce
        p += normal_dir(a) * wrinkle(p, 0.00035, 13.0, 3.1)
        return p

    return [cloth_grid("Skirt", nu, nv, surf, thickness=0.003)]


class Panel:
    """Lembo parametrico appoggiato sulla gonna.

    Espone ``pt(u, v, extra)`` e ``nrm(u, v)``: cosi' i ricami possono essere
    definiti nello stesso spazio parametrico del lembo e restano *sempre*
    sopra la stoffa, senza sbordare.
    """

    def __init__(self, name, ang_table, z_table, layer, width_table=None,
                 tip=0.0, tip_pow=1.5, seed=0.0, pleat_n=27,
                 pleat_amp=0.010, edge_tuck=0.0, corner_lift=0.0,
                 skew=0.0, phase=0.0, blend_top=0.0, top_taper=0.0):
        self.name = name
        self.ang = ang_table
        self.z = z_table
        self.layer = layer
        self.width = width_table or [(0.0, 0.5), (1.0, 0.5)]
        self.tip = tip
        self.tip_pow = tip_pow
        self.seed = seed
        self.pleat_n = pleat_n
        self.pleat_amp = pleat_amp
        self.edge_tuck = edge_tuck
        self.corner_lift = corner_lift
        self.skew = skew
        self.phase = phase
        self.blend_top = blend_top
        self.top_taper = top_taper

    def params(self, u, v):
        """(angolo, quota, bordo) del punto (u, v)."""
        uu = (u - 0.5) * 2.0
        edge = abs(uu)
        a_c = lerp_table(self.ang, v) + self.skew * v
        hw = lerp_table(self.width, v) * (self.top_taper + (1.0 - self.top_taper) * min(v * 4.0, 1.0))
        a = a_c + hw * uu
        z = lerp_table(self.z, v)
        if self.tip:
            z -= self.tip * (1.0 - edge) ** self.tip_pow * smoothstep(0.30, 1.0, v)
        if self.corner_lift:
            z += self.corner_lift * (edge ** 2.0) * smoothstep(0.45, 1.0, v)
        # orlo leggermente ondulato: la stoffa non e' un cartone
        z += 0.006 * math.sin(u * 9.0 + self.seed) * smoothstep(0.75, 1.0, v)
        return a, z, edge

    def pt(self, u, v, extra=0.0):
        a, z, edge = self.params(u, v)
        f = pleats(a + self.phase, v, self.seed, n=self.pleat_n, amp=1.0)
        # le pieghe si spengono verso i bordi del lembo: l'orlo laterale resta
        # una curva di stoffa, non una fila di dentini
        fade = 1.0 - edge ** 1.35
        # Le pieghe principali provengono gia' dalla gonna. Una piega locale
        # piu' sottile aggiunge carattere senza far attraversare gli strati.
        amp = (self.pleat_amp * 0.30 * smoothstep(0.0, 0.20, v) * fade)
        # Gli scialli sono uno strato di lana piu' spesso e teso: seguire le
        # pieghe strette del lino li ripiegherebbe su se stessi e nasconderebbe
        # i ricami. Un piccolo margine li tiene sopra le creste della gonna.
        if self.layer in {"drape", "drape2"}:
            sd = 0.006
        else:
            sd = skirt_disp(a, z) if self.layer != "under" else 0.0
        # Solchi verticali delicati, modellati nella stoffa e non dipinti.
        # Seguono lentamente la caduta del lembo, lasciando puliti gli orli.
        creases = 0.0
        if self.name.startswith("Lap_"):
            for center in (0.29, 0.70):
                center += 0.018 * math.sin(v * 3.0 + self.seed)
                creases -= (0.0035 * math.exp(-((u - center) / 0.035) ** 2)
                            * smoothstep(0.03, 0.18, v) * fade)
        p = surface(a, z, "base", extra=LAYER[self.layer] + sd + f * amp
                    + creases + extra)
        if self.blend_top:
            # in cima il lembo si appoggia sulla gonna invece di sporgere...
            # ma resta 2 mm sopra la superficie pieghettata: se ci finisse
            # esattamente sopra, le micro-pieghe della gonna trapassano il
            # bordo e l'orlo sembra seghettato.
            lift = max(0.0, LAYER[self.layer] * self.blend_top - 0.002)
            p -= normal_dir(a) * (lift * (1.0 - smoothstep(0.0, 0.30, v)))
        if self.edge_tuck:
            p -= normal_dir(a) * (self.edge_tuck * edge ** 2.2)
        p += normal_dir(a) * (wrinkle(p, 0.0007, 10.0, self.seed)
                              * (1.0 - edge ** 2.0))
        return p

    def nrm(self, u, v):
        # Differenze centrate anche sui bordi: una derivata zero faceva girare
        # i ricami all'estremita' delle falde.
        du, dv = 1e-3, 1e-3
        pu = self.pt(min(u + du, 1.0), v) - self.pt(max(u - du, 0.0), v)
        pv = self.pt(u, min(v + dv, 1.0)) - self.pt(u, max(v - dv, 0.0))
        n = pu.cross(pv)
        a, _, _ = self.params(u, v)
        if n.length < 1e-9:
            return normal_dir(a)
        n.normalize()
        return -n if n.dot(normal_dir(a)) < 0 else n


    def build(self, nu=130, nv=58, thickness=0.0035):
        return cloth_grid(self.name, nu, nv, lambda u, v: self.pt(u, v),
                          thickness=thickness)


def panel(name, ang_table, z_table, layer, width_table=None, tip=0.0,
          tip_pow=1.5, seed=0.0, nu=130, nv=58, thickness=0.0035,
          pleat_n=27, pleat_amp=0.010, edge_tuck=0.0, corner_lift=0.0,
          skew=0.0, phase=0.0, blend_top=0.0, top_taper=0.0):
    pnl = Panel(name, ang_table, z_table, layer, width_table, tip, tip_pow,
                seed, pleat_n, pleat_amp, edge_tuck, corner_lift, skew, phase,
                blend_top, top_taper)
    return pnl.build(nu, nv, thickness)


def build_lappets():
    """Lembi sovrapposti, con punte sfalsate e libere come nel disegno."""
    R = math.radians
    defs = [
        # Due pannelli larghi: quello a sinistra e' piu' corto.
        ("Lap_FrontL", -32, -28, 32, 34, 0.49, "lapB", 0.055, 0.6),
        ("Lap_FrontR",  32,  29, 32, 35, 0.32, "lap",  0.050, 2.1),
        # Due code strette incorniciano la staffa e scendono sotto il resto.
        ("Lap_CenterL", -15, -13, 12, 12, 0.235, "lap3", 0.045, 4.4),
        ("Lap_CenterR",  15,  13, 12, 12, 0.215, "lap3", 0.036, 5.8),
        # Falde laterali e posteriori: la silhouette non e' una campana chiusa.
        ("Lap_SideL",  65,  68, 26, 24, 0.300, "lap2", 0.045, 3.7),
        ("Lap_SideR", -65, -68, 26, 24, 0.285, "lap2", 0.050, 5.2),
        ("Lap_BackL",  147,  151, 34, 33, 0.285, "lapB", 0.055, 6.6),
        ("Lap_BackR", -147, -151, 34, 33, 0.300, "lap", 0.050, 7.3),
    ]
    objs = []
    for name, a0, a1, w0, w1, zbot, layer, tip, seed in defs:
        objs.append(panel(
            name, [(0.0, R(a0)), (1.0, R(a1))],
            [(0.0, SKIRT_TOP_Z + 0.002), (1.0, zbot)], layer,
            width_table=[(0.0, R(w0)), (1.0, R(w1))],
            tip=tip, tip_pow=1.25, seed=seed,
            nu=112 if 'Center' not in name else 64, nv=66,
            pleat_n=11, pleat_amp=0.012, corner_lift=0.022,
            edge_tuck=0.0, blend_top=0.92, top_taper=0.78))
    return objs


def drape_specs():
    """Scialli obliqui sui fianchi, visibili anche dalla vista frontale."""
    R = math.radians
    return [
        ("Drape_L", [(0.0, R(64)), (0.5, R(70)), (1.0, R(78))],
         [(0.0, 0.952), (1.0, 0.535)], [(0.0, R(17)), (1.0, R(16))], 1.2),
        ("Drape_R", [(0.0, R(-64)), (0.5, R(-70)), (1.0, R(-78))],
         [(0.0, 0.952), (1.0, 0.535)], [(0.0, R(17)), (1.0, R(16))], 3.4),
        ("Drape_L2", [(0.0, R(92)), (1.0, R(109))],
         [(0.0, 0.933), (1.0, 0.540)], [(0.0, R(11)), (1.0, R(9))], 5.0),
        ("Drape_R2", [(0.0, R(-92)), (1.0, R(-109))],
         [(0.0, 0.933), (1.0, 0.540)], [(0.0, R(11)), (1.0, R(9))], 7.1),
    ]


def build_drapes():
    """Scialli scuri con punta in basso, piegati come la gonna."""
    objs = []
    drapes = []
    for name, ang, ztab, wtab, seed in drape_specs():
        layer = "drape2" if name.endswith("2") else "drape"
        pnl = Panel(name, ang, ztab, layer, width_table=wtab,
                    tip=0.052, tip_pow=1.4, seed=seed,
                    pleat_n=11, pleat_amp=0.0060, edge_tuck=0.0,
                    blend_top=0.85, top_taper=0.85)
        objs.append(pnl.build(nu=96, nv=70, thickness=0.0032))
        drapes.append(pnl)
    return objs, drapes


# --------------------------------------------------------------------------
# fascia e cintura
# --------------------------------------------------------------------------

def sash_top(a):
    """Bordo alto morbido, appena piu' alto sui fianchi."""
    return 1.072 + 0.018 * abs(math.sin(a)) ** 1.5


def waist_pt(a, z, extra=0.0):
    return Vector(((WAIST_RX + extra) * math.sin(a),
                   -(WAIST_RY + extra) * math.cos(a), z))


def build_sash():
    """Fascia avorio e due veri teli diagonali incrociati intorno alla vita."""
    objs = []
    nu = 208

    def body(u, v):
        a = TAU * u
        z = sash_top(a) + (SASH_BOT_Z - sash_top(a)) * v
        fullness = 0.0025 * math.sin(math.pi * v)
        return waist_pt(a, z, fullness)

    objs.append(cloth_grid("Sash_Body", nu, 28, body, thickness=0.004))

    def liner(u, v):
        a = TAU * u
        return waist_pt(a, sash_top(a) - 0.003 - 0.042 * v,
                        -0.005 - 0.025 * v)

    objs.append(cloth_grid("Sash_Liner", nu, 8, liner, thickness=0.0))

    def floor(u, v):
        a = TAU * u
        r = 1.0 - 0.94 * v ** 1.6
        z = sash_top(a) - 0.020 - 0.560 * v
        return Vector(((WAIST_RX - 0.006) * r * math.sin(a),
                       -(WAIST_RY - 0.006) * r * math.cos(a), z))

    objs.append(cloth_grid("Sash_Floor", nu, 6, floor, thickness=0.0))

    # Diversi offset tengono distinti i due drappeggi al loro incrocio.
    for k, sgn in enumerate((1.0, -1.0)):
        def cross(u, v, sgn=sgn, k=k):
            a = TAU * u
            center = 1.022 + sgn * 0.050 * math.sin(a)
            width = 0.042 + 0.005 * abs(math.sin(a))
            z = center + (v - 0.5) * width
            # Tre solchi soffici nel tessuto, orientati lungo il nastro.
            fold = 0.0018 * math.cos(3.0 * math.pi * v + 0.7 * math.sin(a))
            return waist_pt(a, z, 0.014 + k * 0.006 + fold)

        objs.append(cloth_grid(f"Sash_Cross{k}", nu, 20, cross,
                               thickness=0.0028))
    return objs


def build_belt():
    """Cintura scura diagonale sulla fascia, non un bordo orizzontale."""
    def surf(u, v):
        a = TAU * u
        center = 1.025 - 0.020 * math.sin(a)
        z = center + (v - 0.5) * 0.029
        return waist_pt(a, z, 0.011)
    return [cloth_grid("Belt_Dark", 192, 8, surf, thickness=0.0025)]


def build_buckle_back():
    # Il cuoio dietro la fibbia impedisce di vedere il lino nel foro.
    return [ellipsoid("Buckle_Back", (0, -0.152, 1.026),
                      (0.025, 0.0025, 0.025), segs=40, rings=16)]


def build_ring():
    """Fibbia d'ottone con rivetti minuti come nel concept."""
    c = Vector((0.0, -0.159, 1.026))
    objs = [torus("BeltRing", c, (0.0, 1.0, 0.0), 0.0255, 0.0048,
                  seg_major=72, seg_minor=16, squash=1.0)]
    for k in range(8):
        a = TAU * k / 8.0
        p = c + Vector((0.0255 * math.cos(a), -0.0042,
                        0.0255 * math.sin(a)))
        objs.append(ellipsoid(f"Buckle_Stud{k}", p,
                              (0.0015, 0.0010, 0.0015), segs=10, rings=6))
    return objs


# --------------------------------------------------------------------------
# staffa con i simboli
# --------------------------------------------------------------------------

STRAP_TOP_Z = 1.041
STRAP_SHOULDER_Z = 0.403
STRAP_TIP_Z = 0.350


def strap_halfwidth(z):
    t = min(1.0, max(0.0, (STRAP_TOP_Z - z) /
                         (STRAP_TOP_Z - STRAP_TIP_Z)))
    return 0.0265 * (1.0 - 0.10 * t)


def strap_point(x, z, off=0.0):
    """Superficie della staffa e dei suoi ricami; davanti = -Y."""
    w = max(strap_halfwidth(z), 1e-3)
    # In vita si infila sotto la fibbia; sotto si appoggia sopra i lembi.
    layer = 0.021 + 0.056 * smoothstep(0.0, 0.14, SKIRT_TOP_Z - z)
    f = skirt_disp(0.0, z)
    base = surface(0.0, min(z, SKIRT_TOP_Z), "base", extra=layer + f)
    # Una lieve convessita' mantiene naturale il nastro, senza tagli bianchi.
    y = base.y - off - 0.0025 * (x / w) ** 2
    return Vector((x, y, z))


def build_strap():
    nu, nv = 20, 120

    def surf(u, v):
        side = 2.0 * u - 1.0
        end_z = STRAP_TIP_Z + (STRAP_SHOULDER_Z - STRAP_TIP_Z) * abs(side)
        z = STRAP_TOP_Z + (end_z - STRAP_TOP_Z) * v
        x = side * strap_halfwidth(z)
        return strap_point(x, z)

    body = cloth_grid("Strap", nu, nv, surf, thickness=0.0025)
    return [body], strap_gold()


def _gold(pts3d, width, thickness=0.0010):
    nrm = []
    for p in pts3d:
        dz = 0.001
        slope = (strap_point(p.x, p.z + dz).y -
                 strap_point(p.x, p.z - dz).y) / (2.0 * dz)
        nrm.append(Vector((0, -1, slope)).normalized())
    return ribbon_n("StrapGold", pts3d, nrm, width, thickness=thickness)


def _gold2d(pts2d, width, off=0.0028):
    # Campionare anche i segmenti lunghi: il ricamo segue la curvatura della
    # stoffa invece di attraversarla fra i soli due estremi.
    dense = []
    for (x0, z0), (x1, z1) in zip(pts2d, pts2d[1:]):
        n = max(1, int(math.ceil(math.hypot(x1 - x0, z1 - z0) / 0.008)))
        dense.extend((x0 + (x1 - x0) * i / n,
                      z0 + (z1 - z0) * i / n) for i in range(n))
    dense.append(pts2d[-1])
    return _gold([strap_point(x, z, off) for x, z in dense], width)


def strap_gold():
    """Catena centrale: rombo, cerchio, asta, rombo e doppia punta dorata."""
    objs = []
    def stroke(points, width=0.0022):
        objs.append(_gold2d(points, width))
    def diamond(cz, rx, rz):
        stroke([(0, cz + rz), (rx, cz), (0, cz - rz),
                (-rx, cz), (0, cz + rz)], 0.0025)

    # Segno superiore, allungato; cerchio e piccola traversa.
    stroke([(0.0, 0.934), (0.0, 0.870)], 0.0017)
    diamond(0.858, 0.0070, 0.012)
    circle = [(0.017 * math.cos(TAU * i / 48),
               0.820 + 0.017 * math.sin(TAU * i / 48)) for i in range(49)]
    stroke(circle, 0.0026)
    stroke([(0, 0.803), (0, 0.654)], 0.0020)
    stroke([(-0.008, 0.790), (0.008, 0.790)], 0.0020)
    diamond(0.642, 0.0078, 0.012)
    stroke([(0, 0.630), (0, 0.484)], 0.0022)
    # La parte finale a freccia rimane dentro il bordo a V del nastro.
    stroke([(-0.022, 0.411), (0, 0.365), (0.022, 0.411)], 0.0030)
    stroke([(-0.019, 0.395), (0, 0.358), (0.019, 0.395)], 0.0022)
    for side in (-1, 1):
        stroke([(side * 0.019, 0.426), (side * 0.019, 0.402)], 0.0023)
        stroke([(side * 0.008, 0.375), (side * 0.008, 0.397)], 0.0027)
    return objs


# --------------------------------------------------------------------------
# rune sugli scialli scuri
# --------------------------------------------------------------------------

def build_drape_runes(drapes):
    """Bordi e motivi geometrici dorati, applicati ai veri lembi laterali."""
    objs = []

    def path(pnl, name, vertices, width=0.0023):
        # Suddividiamo i tratti prima di proiettarli sul lembo piegato.
        uv = []
        for (u0, v0), (u1, v1) in zip(vertices, vertices[1:]):
            count = max(1, int(math.ceil(max(abs(u1-u0), abs(v1-v0)) / 0.018)))
            uv.extend((u0+(u1-u0)*i/count, v0+(v1-v0)*i/count)
                      for i in range(count))
        uv.append(vertices[-1])
        normals = [pnl.nrm(u, v) for u, v in uv]
        # La griglia ha 3.2 mm di spessore sul lato esterno: stare sopra
        # l'estrusione, non sotto la superficie originale della griglia.
        pts = [pnl.pt(u, v) + n * 0.0052 for (u, v), n in zip(uv, normals)]
        objs.append(ribbon_n(name, pts, normals, width, thickness=0.0009))

    for pnl in drapes:
        name = pnl.name
        for u in (0.10, 0.90):
            path(pnl, name + "_border", [(u, 0.08), (u, 0.90)], 0.0022)
        if name.endswith("2"):
            continue
        # Motivo angolare come un ricamo, non un fitto zig-zag ornamentale.
        path(pnl, name + "_diagonal", [(0.18, 0.23), (0.76, 0.43),
                                      (0.30, 0.60), (0.76, 0.77)], 0.0026)
        for v in (0.37, 0.60):
            path(pnl, name + "_diamond", [(0.50, v-0.047), (0.66, v),
                                           (0.50, v+0.047), (0.34, v),
                                           (0.50, v-0.047)], 0.0023)
    return objs


# --------------------------------------------------------------------------
# assemblaggio
# --------------------------------------------------------------------------

PART_MATERIAL = {
    "legs": "DRESS1_Skin",
    "feet": "DRESS1_Skin",
    "wrap": "DRESS1_Wool",
    "sole": "DRESS1_Canvas",
    "fabric": "DRESS1_Linen",
    "dark": "DRESS1_Wool",
    "gold": "DRESS1_Gold",
    "gold_trim": "DRESS1_GoldTrim",
}


KEEP_GROUPS = ("wrap", "dark", "gold", "gold_trim")


def tag_keep(objs):
    """Segna i vertici dei dettagli sottili (ricami, nastri, staffa).

    ``02_optimize`` usa questo gruppo per decimare molto meno proprio questi
    pezzi: a 60k triangoli un ricamo dorato largo 3 mm sparirebbe.
    """
    for ob in objs:
        vg = ob.vertex_groups.get("keep") or ob.vertex_groups.new(name="keep")
        vg.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")


def assign_material(objs, mat_name):
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True
    for ob in objs:
        ob.data.materials.clear()
        ob.data.materials.append(mat)
    return objs


def build_all():
    reset_scene()
    sandals = build_sandals()
    drapes, drape_panels = build_drapes()
    strap_body, strap_gold_parts = build_strap()
    soles = [o for o in sandals if o.name.startswith("Sole")]
    straps = [o for o in sandals if not o.name.startswith("Sole")]

    groups = {
        "legs": build_legs(),
        "feet": build_feet(),
        "wrap": build_legwraps() + straps,
        "sole": soles,
        "fabric": (build_underskirt() + build_skirt() + build_lappets()
                   + build_sash()),
        "dark": drapes + strap_body + build_belt() + build_buckle_back(),
        "gold": build_ring(),
        "gold_trim": build_drape_runes(drape_panels) + strap_gold_parts,
    }
    all_objs = []
    for key, objs in groups.items():
        assign_material(objs, PART_MATERIAL[key])
        if key in KEEP_GROUPS:
            tag_keep(objs)
        all_objs += objs
    return all_objs


def join_all(objs, name="DRESS1"):
    from common import apply_modifiers, remove_doubles
    for ob in objs:
        apply_modifiers(ob)
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objs:
        if ob.name in bpy.data.objects:
            ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    ob = bpy.context.object
    ob.name = name
    ob.data.name = name + "_mesh"
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    remove_doubles(ob, 1e-5)
    # spigoli vivi sulle pieghe: senza questo le pieghe si "sciolgono"
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(46.0))
    return ob


def main():
    out = ensure_dir(os.path.join(work_dir(), "build"))
    objs = build_all()
    print(f"[build] {len(objs)} oggetti")
    ob = join_all(objs)
    from common import tri_count
    zs = [v.co.z for v in ob.data.vertices]
    print(f"[build] {ob.name}: {tri_count(ob)} triangoli, "
          f"{len(ob.data.vertices)} vertici, {len(ob.data.materials)} materiali, "
          f"z {min(zs):.3f}..{max(zs):.3f}")
    path = os.path.join(out, "DRESS1_build.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("[build] salvato", path)


if __name__ == "__main__":
    main()
