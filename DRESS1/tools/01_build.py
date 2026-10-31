"""DRESS1 — costruzione della geometria (v4).

Il capo e' ridisegnato da zero seguendo il concept: gonna in lino avorio a pieghe
fitte, fascia incrociata in vita con anello d'ottone, staffa scura con simboli
geometrici dorati, scialli scuri sui fianchi con rune, caviglie fasciate e
sandali aperti.

Regola d'oro di questa versione: **ogni pezzo nasce dalla stessa superficie**
``surface(a, z, layer)``. Cosi' lembi, scialli, cordoni e ricami restano
appoggiati alla gonna senza compenetrarla ne' staccarsi.

Quote (metri, Z in alto, davanti = -Y):

```
z = 1.100  bordo alto della fascia (ai fianchi)
z = 1.040  cintura scura + anello
z = 0.945  fondo della fascia
z = 0.966  attacco della gonna
z = 0.290  orlo medio (punte a 0.220)
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

TOP_Z = 1.100
SASH_BOT_Z = 0.945
WAIST_RX = 0.152
WAIST_RY = 0.126

SKIRT_TOP_Z = 0.964
LEG_X = 0.070

# (z, rx, ry) — profilo a campana, svasatura dolce
PROFILE = [
    (0.964, 0.152, 0.128),
    (0.900, 0.157, 0.133),
    (0.800, 0.166, 0.142),
    (0.700, 0.177, 0.153),
    (0.600, 0.190, 0.165),
    (0.500, 0.203, 0.177),
    (0.430, 0.213, 0.186),
    (0.370, 0.221, 0.193),
    (0.330, 0.224, 0.196),
    (0.290, 0.222, 0.194),
    (0.250, 0.216, 0.189),
    (0.210, 0.207, 0.181),
    (0.170, 0.195, 0.171),
]

# offset di raggio per strato (m)
LAYER = {
    "under": -0.045,
    "base": 0.000,
    "lapB": 0.026,
    "lap": 0.034,
    "lap2": 0.046,
    "lap3": 0.052,
    "drape": 0.056,
    "drape2": 0.062,
    "trim": 0.068,
    "strap": 0.074,
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


def sharpen(x, k):
    """Onda -> onda a spigolo, senza discontinuita' (per pieghe 'a coltello')."""
    return math.tanh(k * x) / math.tanh(k) if abs(math.tanh(k)) > 1e-6 else x


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


def build_legs():
    objs = []
    for side, sx in (("L", 1.0), ("R", -1.0)):
        secs = []
        for (z, rx, ry, dy) in LEG_PROFILE:
            cx = sx * (LEG_X + 0.004 * (1.0 - z))
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
        rot = Matrix.Rotation(-math.radians(6.0) * sx, 4, "Z")
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
        rot = Matrix.Rotation(-math.radians(6.0) * sx, 4, "Z")

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

def pleats(a, v, seed=0.0, n=26, amp=1.0, sharp=1.15, hem_fade=0.0):
    """Pieghe a coltello: onda triangolare + modulazione lenta.

    ``sharp`` controlla quanto e' viva la piega, ``hem_fade`` spegne
    gradualmente l'ampiezza negli ultimi centimetri (orlo pulito).
    """
    def tri(x):
        return 2.0 * abs(2.0 * ((x / TAU) % 1.0) - 1.0) - 1.0

    def knife(x):
        """Dente di sega: salita lenta, caduta ripida (piega a coltello)."""
        t = (x / TAU) % 1.0
        return 2.0 * (t ** 0.62) - 1.0 if t < 1.0 else 0.0

    base = (0.66 * knife(a * n + seed)
            + 0.22 * knife(a * (n * 0.5) - 0.8 + seed)
            + 0.12 * tri(a * (n * 2.0) + 2.4))
    base = sharpen(base, sharp)
    mod = (0.70 + 0.30 * math.sin(a * 3.0 - 0.7 + seed)
           * 0.5 + 0.15 * math.sin(a * 7.0 + 1.1))
    f = base * mod * amp * smoothstep(0.0, 0.12, v)
    if hem_fade:
        f *= 1.0 - hem_fade * smoothstep(0.90, 1.0, v)
    return f


def skirt_disp(a, z):
    """Spostamento radiale della gonna in (a, z).

    Le falde appoggiate sopra devono seguire la *superficie pieghettata*,
    altrimenti le creste delle pieghe trapassano la stoffa sovrapposta.
    """
    span = hem_z(a) - SKIRT_TOP_Z
    v = 0.0 if span <= 1e-6 else min(1.0, max(0.0, (z - SKIRT_TOP_Z) / span))
    f = pleats(a, v, 0.0, n=13, amp=0.0200, sharp=1.02, hem_fade=0.85)
    f += 0.0028 * math.sin(a * 67.0 + v * 1.6) * smoothstep(0.05, 0.5, v)
    return f


def build_underskirt():
    nu, nv = 150, 36
    z_top = SKIRT_TOP_Z - 0.006
    z_bot = 0.252

    def surf(u, v):
        a = TAU * u
        z = z_top + (z_bot - z_top) * v ** 1.02
        rx, ry = radius(z, "under")
        f = pleats(a, v, 0.4, n=9, amp=0.0030, sharp=1.0, hem_fade=1.0)
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
        f = pleats(a, v, 0.0, n=13, amp=0.0200, sharp=1.02, hem_fade=0.85)
        # micro pieghe sfalsate
        f += 0.0028 * math.sin(a * 67.0 + v * 1.6) * smoothstep(0.05, 0.5, v)
        p = surface(a, z, "base", extra=f)
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
        amp = (self.pleat_amp * (0.60 + 0.40 * smoothstep(0.0, 0.30, v))
               * fade)
        sd = skirt_disp(a, z) if self.layer != "under" else 0.0
        p = surface(a, z, "base", extra=LAYER[self.layer] + sd + f * amp + extra)
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
        du, dv = 1e-3, 1e-3
        p0 = self.pt(u, v)
        pu = self.pt(min(u + du, 1.0), v)
        pv = self.pt(u, min(v + dv, 1.0))
        n = (pu - p0).cross(pv - p0)
        if n.length < 1e-9:
            a, _, _ = self.params(u, v)
            return normal_dir(a)
        n.normalize()
        a, _, _ = self.params(u, v)
        if n.dot(normal_dir(a)) < 0:
            n = -n
        return n

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
    """Falde sovrapposte: la lettura a strati del concept."""
    objs = []
    R = math.radians

    # grande falda frontale sinistra che scavalca il centro e finisce a punta
    objs.append(panel(
        "Lap_FrontL",
        [(0.0, R(-30)), (1.0, R(22))],
        [(0.0, SKIRT_TOP_Z + 0.002), (0.55, 0.335), (1.0, 0.272)],
        "lap", width_table=[(0.0, R(70)), (0.5, R(74)), (1.0, R(78))],
        tip=0.115, tip_pow=1.45, seed=0.4, nu=150, nv=64,
        pleat_n=13, pleat_amp=0.0190, corner_lift=0.060, edge_tuck=0.004,
        blend_top=1.0))
    # falda destra, piu' corta, con orlo a punta piu' bassa sul fianco
    objs.append(panel(
        "Lap_FrontR",
        [(0.0, R(24)), (1.0, R(8))],
        [(0.0, SKIRT_TOP_Z + 0.001), (0.6, 0.372), (1.0, 0.300)],
        "lapB", width_table=[(0.0, R(58)), (1.0, R(66))],
        tip=0.085, tip_pow=1.6, seed=2.1, nu=130, nv=58,
        pleat_n=13, pleat_amp=0.0180, corner_lift=0.050, edge_tuck=0.004,
        blend_top=1.0))
    # falda laterale sinistra, molto lunga e stretta (asimmetria del concept)
    objs.append(panel(
        "Lap_SideL",
        [(0.0, R(52)), (1.0, R(38))],
        [(0.0, SKIRT_TOP_Z + 0.004), (0.6, 0.300), (1.0, 0.155)],
        "lap2", width_table=[(0.0, R(40)), (1.0, R(30))],
        tip=0.055, tip_pow=1.7, seed=3.7, nu=96, nv=76,
        pleat_n=9, pleat_amp=0.015, edge_tuck=0.0, corner_lift=0.030,
        blend_top=1.0, top_taper=0.45))
    # falda laterale destra piu' corta
    objs.append(panel(
        "Lap_SideR",
        [(0.0, R(-54)), (1.0, R(-44))],
        [(0.0, SKIRT_TOP_Z + 0.003), (0.65, 0.350), (1.0, 0.272)],
        "lap3", width_table=[(0.0, R(38)), (1.0, R(30))],
        tip=0.050, tip_pow=1.7, seed=5.2, nu=90, nv=58,
        pleat_n=9, pleat_amp=0.015, edge_tuck=0.0, corner_lift=0.026,
        blend_top=1.0, top_taper=0.45))
    # dietro: due falde simmetriche
    objs.append(panel(
        "Lap_Back",
        [(0.0, R(152)), (1.0, R(196))],
        [(0.0, SKIRT_TOP_Z + 0.002), (0.6, 0.315), (1.0, 0.278)],
        "lap", width_table=[(0.0, R(50)), (1.0, R(46))],
        tip=0.055, tip_pow=1.5, seed=6.6, nu=120, nv=54,
        pleat_n=11, pleat_amp=0.016, edge_tuck=0.0, corner_lift=0.040,
        blend_top=1.0, top_taper=0.40))
    return objs


def drape_specs():
    """Scialli scuri: (nome, tabella angoli, tabella quote, semiampiezza)."""
    R = math.radians
    return [
        ("Drape_L", [(0.0, R(72)), (0.45, R(88)), (1.0, R(108))],
         [(0.0, 0.950), (0.5, 0.700), (1.0, 0.415)], [(0.0, R(22)), (1.0, R(13))], 1.2),
        ("Drape_R", [(0.0, R(-74)), (0.45, R(-90)), (1.0, R(-110))],
         [(0.0, 0.950), (0.5, 0.695), (1.0, 0.410)], [(0.0, R(22)), (1.0, R(13))], 3.4),
        ("Drape_L2", [(0.0, R(100)), (1.0, R(116))],
         [(0.0, 0.930), (1.0, 0.560)], [(0.0, R(11)), (1.0, R(7))], 5.0),
        ("Drape_R2", [(0.0, R(-102)), (1.0, R(-118))],
         [(0.0, 0.930), (1.0, 0.555)], [(0.0, R(11)), (1.0, R(7))], 7.1),
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
                    blend_top=0.9, top_taper=0.62)
        objs.append(pnl.build(nu=96, nv=70, thickness=0.0032))
        drapes.append(pnl)
    return objs, drapes


# --------------------------------------------------------------------------
# fascia e cintura
# --------------------------------------------------------------------------

SASH_TOP = [(0.0, 1.058), (0.5, 1.086), (1.0, 1.084), (1.5, 1.058),
            (2.0, 1.058)]


def sash_top(a):
    """Bordo alto della fascia: sale ai fianchi come un obi inamidato."""
    # a misurato da -pi a pi partendo dal davanti
    aa = ((a + math.pi) % TAU) - math.pi
    return 1.062 + 0.030 * abs(math.sin(aa)) ** 1.4


def build_sash():
    """Fascia in vita: banda avorio con bordo arrotolato e fodera interna.

    Il bordo superiore non e' un disco: e' un *orlo* sottile che si arrotola
    verso l'interno e scende in una fodera, come una vera fascia di stoffa.
    Cosi' dall'alto si vede la fodera (non un tappo) e di lato il bordo resta
    una linea, non una tesa di cappello.
    """
    objs = []
    nu = 208
    z_top_side = 1.062
    z_top_front = 1.046

    def topline(a):
        aa = ((a + math.pi) % TAU) - math.pi
        # bordo quasi dritto con una lieve onda: si legge come una fascia,
        # non come la tesa di un cappello
        return z_top_front + (z_top_side - z_top_front) * abs(math.sin(aa)) ** 2.2

    def shell(a, z, extra):
        pull = 0.007 * max(0.0, math.cos(a)) ** 3
        return Vector(((WAIST_RX - pull + extra) * math.sin(a),
                       -(WAIST_RY - pull + extra) * math.cos(a), z))

    # --- parete esterna: dal bordo alto al fondo, con panciotto leggero
    def surf(u, v):
        a = TAU * u
        zt = topline(a)
        zb = SASH_BOT_Z - 0.002
        z = zt + (zb - zt) * v
        bulge = 0.005 * math.sin(math.pi * min(v * 1.1, 1.0)) ** 0.8
        p = shell(a, z, bulge)
        p += normal_dir(a) * wrinkle(p, 0.0014, 12.0, 0.6)
        return p

    objs.append(cloth_grid("Sash_Body", nu, 22, surf, thickness=0.007))

    # --- fodera: scende verso l'interno, si vede dall'alto
    def surf_liner(u, v):
        a = TAU * u
        zt = topline(a)
        extra = -0.006 - 0.030 * v
        z = zt - 0.004 - 0.040 * v
        return shell(a, z, extra)

    objs.append(cloth_grid("Sash_Liner", nu, 8, surf_liner, thickness=0.0))

    # fondo: chiude l'interno del capo, nascosto sotto il bordo
    def surf_floor(u, v):
        a = TAU * u
        # imbuto molto allungato: si comporta come una colonna chiusa, quindi
        # non si vede nessun piano orizzontale guardando dentro il capo
        r = 1.0 - 0.94 * v ** 1.6
        z = topline(a) - 0.020 - 0.560 * v
        return Vector(((WAIST_RX - 0.006) * r * math.sin(a),
                       -(WAIST_RY - 0.006) * r * math.cos(a), z))

    objs.append(cloth_grid("Sash_Floor", nu, 6, surf_floor, thickness=0.0))

    # --- teli incrociati: due nastri alti che si incrociano davanti
    for k, sgn in enumerate((1.0, -1.0)):
        def surf_cross(u, v, sgn=sgn, k=k):
            a = TAU * u
            aa = ((a + math.pi) % TAU) - math.pi
            center = 1.030 + sgn * 0.026 * math.sin(aa) - 0.008 * math.cos(aa) ** 2
            half = 0.030 * (0.85 + 0.15 * abs(math.sin(aa)))
            z = center - half + 2.0 * half * v
            # i teli stanno appena sopra la fascia: 4-6 mm, non 15
            extra = 0.0055 + 0.0022 * k
            p = shell(a, z, extra - 0.002 * max(0.0, math.cos(a)) ** 2)
            p += normal_dir(a) * wrinkle(p, 0.0014, 13.0, 1.4 + k)
            return p

        objs.append(cloth_grid(f"Sash_Cross{k}", nu, 10, surf_cross,
                               thickness=0.006))
    return objs


def waist_pt(a, z, extra=0.0):
    return Vector(((WAIST_RX + extra) * math.sin(a),
                   -(WAIST_RY + extra) * math.cos(a), z))


def build_belt():
    """Cinghia scura in vita, appoggiata sopra la fascia."""
    objs = []
    pts, widths = [], []
    n = 168
    for i in range(n + 1):
        t = i / n
        a = TAU * t
        aa = ((a + math.pi) % TAU) - math.pi
        z = 1.036 - 0.018 * max(0.0, math.cos(aa)) ** 2
        pts.append(waist_pt(a, z, 0.0085))
        widths.append(0.024 * (0.90 + 0.10 * abs(math.sin(a))))
    objs.append(ribbon("Belt_Dark", pts, 0.024, thickness=0.0040,
                       up=(0, 0, 1), widths=widths))
    return objs


def build_ring():
    """Anello d'ottone al centro della vita, appoggiato sulla cinghia."""
    c = waist_pt(0.0, 1.036, 0.052)
    c.y -= 0.002
    objs = [torus("BeltRing", c, (0.0, 1.0, 0.10), 0.0255, 0.0055,
                  seg_major=72, seg_minor=16, squash=1.06)]
    return objs


# --------------------------------------------------------------------------
# staffa con i simboli
# --------------------------------------------------------------------------

STRAP_TOP_Z = 1.020
STRAP_BOT_Z = 0.402


def strap_halfwidth(z):
    t = (STRAP_TOP_Z - z) / (STRAP_TOP_Z - STRAP_BOT_Z)
    return 0.0275 * (1.0 - 0.10 * t) - 0.019 * max(0.0, t - 0.90) ** 1.4


def strap_point(x, z, off=0.0):
    """Punto sulla staffa: x laterale in metri, z quota, off verso l'esterno."""
    w = max(strap_halfwidth(z), 1e-3)
    # la staffa si appoggia sulla falda frontale
    base = surface(0.0, z, "lap", extra=0.0)
    y = base.y - 0.010 - off - 0.0025 * (x / w) ** 2
    return Vector((x, y, z))


def build_strap():
    objs = []
    nu, nv = 14, 96

    def surf(u, v):
        z = STRAP_TOP_Z + (STRAP_BOT_Z - STRAP_TOP_Z) * v
        w = max(strap_halfwidth(z), 1e-3)
        x = (u - 0.5) * 2.0 * w
        zz = z - 0.050 * max(0.0, v - 0.94) / 0.06
        p = strap_point(x, z, 0.0)
        p.z = zz
        return p

    objs.append(cloth_grid("Strap", nu, nv, surf, thickness=0.0035))
    return objs, strap_gold()


def _gold(pts3d, width, thickness=0.0020):
    nrm = [Vector((0, -1, 0))] * len(pts3d)
    return ribbon_n("StrapGold", pts3d, nrm, width, thickness=thickness)


def _gold2d(pts2d, width, off=0.0055):
    return _gold([strap_point(x, z, off) for (x, z) in pts2d], width)


def strap_gold():
    """Ricami dorati: bordo a freccia, catena di simboli, punta."""
    objs = []
    zb = STRAP_BOT_Z
    # punta: bordo a freccia
    objs.append(_gold2d([(-0.026, zb + 0.036), (0.0, zb - 0.038),
                         (0.026, zb + 0.036)], 0.0062))
    objs.append(_gold2d([(-0.020, zb + 0.002), (0.0, zb - 0.058),
                         (0.020, zb + 0.002)], 0.0042))
    # bordi laterali della staffa
    for s in (-1.0, 1.0):
        pts = [(s * (strap_halfwidth(z) - 0.0035), z)
               for z in [zb + 0.06 + 0.30 * i / 14 for i in range(15)]]
        objs.append(_gold2d(pts, 0.0038))
    # catena di simboli
    objs.append(_gold2d([(-0.008, 0.996), (0.0, 1.006), (0.008, 0.996)],
                        0.0032))
    for cz, rx, rz in ((0.968, 0.0115, 0.020), (0.726, 0.0100, 0.016)):
        pts = []
        for i in range(5):
            ang = TAU * i / 4 + math.pi / 2
            pts.append((rx * math.cos(ang), cz + rz * math.sin(ang)))
        objs.append(_gold2d(pts, 0.0040))
    objs.append(_gold2d([(0.0, 0.946), (0.0, 0.930)], 0.0032))
    # cerchio con asta (simbolo centrale)
    pts = []
    for i in range(37):
        ang = TAU * i / 36
        pts.append((0.0175 * math.cos(ang), 0.872 + 0.0175 * math.sin(ang)))
    objs.append(_gold2d(pts, 0.0042))
    objs.append(_gold2d([(0.0, 0.8545), (0.0, 0.786)], 0.0032))
    objs.append(_gold2d([(-0.013, 0.806), (0.013, 0.806)], 0.0030))
    objs.append(_gold2d([(0.0, 0.708), (0.0, 0.640)], 0.0026))
    return objs


# --------------------------------------------------------------------------
# rune sugli scialli scuri
# --------------------------------------------------------------------------

def drape_channel(name, ang, ztab, w0, w1, n=26):
    """Solco lungo il bordo dello scialle: due nastri che formano il bordo."""
    objs = []
    for sgn in (-1.0, 1.0):
        pts, ws = [], []
        for i in range(n + 1):
            v = i / n
            a_c = lerp_table(ang, v)
            hw = lerp_table([(0.0, w0), (1.0, w1)], v)
            z = lerp_table(ztab, v)
            pts.append(surface(a_c + sgn * hw * 0.90, z, "drape", extra=0.0012))
            ws.append(0.0050)
        objs.append(ribbon(name + f"_edge{sgn}", pts, 0.005, thickness=0.0022,
                           up=(0, 0, 1), widths=ws))
    return objs


def drape_surface_pt(a, z, extra=0.0025):
    return surface(a, z, "drape", extra=extra)


def build_drape_runes(drapes):
    """Rune dorate incassate negli scialli (parametriche sul lembo)."""
    objs = []
    for pnl in drapes:
        name = pnl.name
        # 1) filo dorato ai due bordi
        for sgn in (-1.0, 1.0):
            us = [0.5 + sgn * 0.5 * 0.90] * 9
            vs = [0.06 + i / 8 * 0.86 for i in range(9)]
            pts = [pnl.pt(u, v, 0.0012) for u, v in zip(us, vs)]
            nrms = [pnl.nrm(u, v) for u, v in zip(us, vs)]
            objs.append(ribbon_n(f"{name}_edge{sgn}", pts, nrms, 0.0030,
                                 thickness=0.0014))
        # 2) zig-zag centrale
        pts, nrms = [], []
        for i in range(19):
            v = 0.12 + 0.76 * i / 18
            u = 0.68 if i % 2 == 0 else 0.32
            pts.append(pnl.pt(u, v, 0.0014))
            nrms.append(pnl.nrm(u, v))
        objs.append(ribbon_n(f"{name}_zig", pts, nrms, 0.0030,
                             thickness=0.0014))
        # 3) rombi
        for v, rr in ((0.55, 0.0070), (0.78, 0.0050)):
            c = pnl.pt(0.5, v, 0.0014)
            n = pnl.nrm(0.5, v)
            t = (pnl.pt(0.56, v) - pnl.pt(0.44, v)).normalized()
            b = n.cross(t).normalized()
            quad = [c + t * (rr * math.cos(TAU * j / 4 + math.pi / 2))
                    + b * (rr * 1.7 * math.sin(TAU * j / 4 + math.pi / 2))
                    for j in range(5)]
            objs.append(ribbon_n(f"{name}_dia{v}", quad, [n] * 5, 0.0028,
                                 thickness=0.0014))
    return objs


def surface_normal(a, z, layer="drape", extra=0.0):
    da, dz = 1e-3, 1e-3
    p = surface(a, z, layer, extra)
    pa = surface(a + da, z, layer, extra)
    pz = surface(a, z + dz, layer, extra)
    nrm = (pa - p).cross(pz - p)
    if nrm.length < 1e-9:
        return normal_dir(a)
    nrm.normalize()
    if nrm.dot(normal_dir(a)) < 0:
        nrm = -nrm
    return nrm


def gold_path(name, pts_az, layer="drape", width=0.0035, extra=0.0016,
              thickness=0.0016):
    """Nastro dorato tracciato in coordinate superficie (angolo, quota)."""
    pts, nrm = [], []
    for (a, z) in pts_az:
        n = surface_normal(a, z, layer)
        pts.append(surface(a, z, layer, extra) + n * extra)
        nrm.append(n)
    return ribbon_n(name, pts, nrm, width, thickness=thickness)


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
                   + build_sash() + build_belt()),
        "dark": drapes + strap_body,
        "gold": build_ring(),
        "gold_trim": build_drape_runes(drape_panels) + strap_gold_parts,
        "gold": (build_ring() + build_drape_runes(drape_panels) + []),
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
