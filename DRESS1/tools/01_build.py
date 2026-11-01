"""DRESS1 — costruzione della geometria (dettagli dalla reference).

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

SASH_BOT_Z = 0.952
WAIST_RX = 0.152
WAIST_RY = 0.126

SKIRT_TOP_Z = 0.964
LEG_X = 0.110

# (z, rx, ry) — profilo a campana, svasatura dolce
# (z, rx, ry) — profilo ad A: stretto in vita, poi discesa quasi lineare.
# Nella reference la gonna non si gonfia sui fianchi: si allarga in modo
# regolare fino all'orlo, dove la larghezza e' circa il doppio della vita.
PROFILE = [
    (0.964, 0.152, 0.128),
    (0.900, 0.163, 0.137),
    (0.800, 0.177, 0.149),
    (0.700, 0.190, 0.160),
    (0.600, 0.202, 0.170),
    (0.500, 0.214, 0.180),
    (0.430, 0.222, 0.187),
    (0.370, 0.228, 0.192),
    (0.330, 0.231, 0.195),
    (0.290, 0.233, 0.197),
    (0.250, 0.231, 0.195),
    (0.210, 0.228, 0.192),
    (0.170, 0.224, 0.189),
]

# offset di raggio per strato (m).
# Gli strati sono volutamente vicini (6-8 mm): nella reference i lembi sono
# sovrapposti e aderenti, non un ventaglio di ali staccate dal corpo.
LAYER = {
    "under": -0.045,
    "base": 0.000,
    "lapB": 0.011,
    "lap": 0.018,
    "lap2": 0.025,
    "lap3": 0.032,
    "drape": 0.0405,
    "drape2": 0.0470,
    "trim": 0.050,
    "strap": 0.058,
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
    """Quota dell'orlo della gonna.

    Nella reference l'orlo e' fatto di punte lunghe e asimmetriche, non di un
    bordo ondulato regolare: le punte piu' profonde cadono ai due lati del
    davanti, mentre il centro resta piu' corto per lasciare vedere la staffa.
    """
    lobes = (0.058 * max(0.0, math.sin(a * 1.0 + 0.30)) ** 1.9
             + 0.034 * max(0.0, math.sin(a * 2.0 - 1.02)) ** 2.3
             + 0.019 * max(0.0, math.sin(a * 3.0 + 2.15)) ** 2.6
             + 0.011 * max(0.0, math.sin(a * 5.0 - 0.55)) ** 3.0)
    return 0.312 - lobes


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
          squash=1.0, flat=1.0):
    """Anello: ``flat`` schiaccia la sezione lungo l'asse (anello piatto)."""
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
                         + axis * (minor * flat * math.sin(b)))
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
    # Tallone arrotondato in fondo, dorso basso e affusolato verso le dita:
    # nella reference il piede e' quasi piatto, non un cappello di legno.
    (0.092, 0.013, 0.052, 0.030),
    (0.082, 0.021, 0.072, 0.038),
    (0.068, 0.028, 0.086, 0.045),
    (0.048, 0.033, 0.094, 0.049),
    (0.022, 0.035, 0.088, 0.047),
    (-0.008, 0.037, 0.078, 0.043),
    (-0.040, 0.039, 0.065, 0.037),
    (-0.072, 0.040, 0.055, 0.031),
    (-0.104, 0.040, 0.046, 0.026),
    (-0.132, 0.038, 0.038, 0.021),
    (-0.156, 0.034, 0.032, 0.017),
    (-0.174, 0.028, 0.027, 0.014),
    (-0.186, 0.019, 0.022, 0.012),
]


def build_feet():
    objs = []
    for side, sx in (("L", 1.0), ("R", -1.0)):
        base = Vector((sx * LEG_X, -0.014, 0.0))
        rot = Matrix.Rotation(math.radians(9.0) * sx, 4, "Z")
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
        verts.append(base + rot @ Vector((0, FOOT_SECTIONS[0][0] + 0.010, 0.032)))
        for i in range(rings):
            faces.append((c0, (i + 1) % rings, i))
        c1 = len(verts)
        verts.append(base + rot @ Vector((0, FOOT_SECTIONS[-1][0] - 0.005, 0.011)))
        last = (len(FOOT_SECTIONS) - 1) * rings
        for i in range(rings):
            faces.append((c1, last + i, last + (i + 1) % rings))
        objs.append(mesh_obj(f"Foot_{side}", verts, faces))
        # Dita: cuscinetti affusolati in arco, l'alluce piu' grande e piu'
        # avanzato; le punte si assottigliano invece di essere sferette.
        toes = [(-0.024, -0.183, 0.0112, 0.0190), (-0.008, -0.190, 0.0088, 0.0155),
                (0.005, -0.190, 0.0080, 0.0140), (0.017, -0.186, 0.0072, 0.0128),
                (0.028, -0.178, 0.0062, 0.0110)]
        for k, (fx, fy, r, ln) in enumerate(toes):
            objs.append(ellipsoid(f"Toe_{side}{k}",
                                  base + rot @ Vector((fx, fy, 0.0075 + r * 0.22)),
                                  (r, ln * 0.5, r * 0.80), segs=16, rings=12))
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
        for k, (zc, dip, w) in enumerate(((0.108, 0.010, 0.017),
                                          (0.158, 0.016, 0.013),
                                          (0.208, 0.020, 0.015))):
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


def foot_halfwidth(y):
    """Mezza larghezza del piede alla coordinata y (misure del piede snello)."""
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


def foot_center(y):
    """(altezza totale, centro z) della sezione del piede a y."""
    tbl = FOOT_SECTIONS
    if y >= tbl[0][0]:
        return tbl[0][2], tbl[0][3]
    if y <= tbl[-1][0]:
        return tbl[-1][2], tbl[-1][3]
    for i in range(len(tbl) - 1):
        y0, _, hz0, cy0 = tbl[i]
        y1, _, hz1, cy1 = tbl[i + 1]
        if y1 <= y <= y0:
            t = (y0 - y) / (y0 - y1)
            return hz0 * (1 - t) + hz1 * t, cy0 * (1 - t) + cy1 * t
    return tbl[-1][2], tbl[-1][3]


def foot_surface(x, y, lift=0.0):
    """Punto sul dorso del piede (coordinate locali del piede).

    La sezione del piede e' una superellisse con lo stesso esponente usato per
    generare la mesh: le fascette del sandalo restano cosi' appoggiate alla
    pelle invece di attraversarla.
    """
    hw = max(foot_halfwidth(y), 1e-6)
    hz, cy = foot_center(y)
    e = 2.6
    t = min(1.0, abs(x) / hw)
    z = cy + 0.5 * hz * (1.0 - t ** e) ** (1.0 / e)
    return Vector((x, y, z + lift))


def build_sandals():
    """Sandalo aperto: suola sottile e fascette che seguono il dorso."""
    objs = []
    for side, sx in (("L", 1.0), ("R", -1.0)):
        base = Vector((sx * LEG_X, -0.014, 0.0))
        rot = Matrix.Rotation(math.radians(9.0) * sx, 4, "Z")

        def P(x, y, z):
            return base + rot @ Vector((x, y, z))

        def N(x, y):
            d = 0.0012
            t1 = foot_surface(x + d, y) - foot_surface(x - d, y)
            t2 = foot_surface(x, y + d) - foot_surface(x, y - d)
            n = t2.cross(t1)
            if n.length < 1e-9:
                return rot @ Vector((0, 0, 1))
            n.normalize()
            if n.z < 0:
                n = -n
            return rot @ n

        # --- suola: profilo ricavato dal piede, bordo vivo e spessore 9 mm
        ys = [0.064, 0.052, 0.034, 0.012, -0.014, -0.040, -0.066, -0.092,
              -0.116, -0.138, -0.156, -0.170, -0.182, -0.189]
        outline = [(foot_halfwidth(y) + 0.0032, y) for y in ys]
        outline += [(-foot_halfwidth(y) - 0.0032, y) for y in reversed(ys)]
        m = len(outline)
        verts, faces = [], []
        for (z, sc) in ((0.0008, 0.955), (0.0060, 1.0), (0.0110, 0.985)):
            for (px, py) in outline:
                verts.append(P(px * sc, py * sc, z))
        for ring in range(2):
            for i in range(m):
                a = ring * m + i
                b = ring * m + (i + 1) % m
                faces.append((a, b, b + m, a + m))
        faces.append(tuple(range(m - 1, -1, -1)))
        faces.append(tuple(range(2 * m, 3 * m)))
        objs.append(mesh_obj(f"Sole_{side}", verts, faces))

        # --- fascia sull'avampiede: attraversa il dorso e scende ai due lati
        def across(y, width, lift=0.0016, thick=0.0034, half=0.955):
            hw = foot_halfwidth(y)
            pts, nrm = [], []
            steps = 20
            for i in range(steps + 1):
                x = (-1.0 + 2.0 * i / steps) * hw * half
                pts.append(P(*foot_surface(x, y, lift)))
                nrm.append(N(x, y))
            objs.append(ribbon_n(f"SandalBand_{side}{y:.3f}", pts, nrm,
                                 width, thickness=thick))

        across(-0.052, 0.0155)
        across(-0.098, 0.0130, lift=0.0014)

        # --- fascia fra le dita: unisce la suola al centro dell'avampiede
        pts, nrm = [], []
        for i in range(13):
            t = i / 12
            y = -0.158 + 0.058 * t
            x = 0.004 + 0.002 * t
            pts.append(P(*foot_surface(x, y, 0.0014)))
            n = N(x, y)
            nrm.append((n + Vector((0, 0.25 * t, 0))).normalized())
        objs.append(ribbon_n(f"SandalToe_{side}", pts, nrm, 0.0105,
                             thickness=0.0032))

        # --- fascetta al tallone: giro orizzontale che segue la pianta del
        # piede (prima era un arco sospeso che usciva dal tallone).
        ring = []
        for i in range(len(ys)):
            if ys[i] >= 0.004:
                ring.append((ys[i], 1.0))
            elif ys[i] >= -0.030:
                ring.append((ys[i], 0.92))
        ring = [(foot_halfwidth(y) + 0.0026, y, sc) for y, sc in ring]
        half = len(ring)
        outline_h = [(hw, y) for hw, y, _ in ring]
        outline_h += [(-hw * 0.99, y) for hw, y, _ in reversed(ring)]
        n_h = len(outline_h)
        verts, faces = [], []
        for dz in (-0.0080, 0.0080):
            for (px, py) in outline_h:
                z = 0.031 + 0.030 * max(0.0, (py - 0.004) / 0.095) + dz
                hw = foot_halfwidth(py)
                sx2 = px / max(hw + 0.0026, 1e-6)
                verts.append(P(px, py * (1.0 + 0.004 * (1.0 - abs(sx2))), z))
        for i in range(n_h):
            a = i
            b = (i + 1) % n_h
            faces.append((a, b, b + n_h, a + n_h))
        objs.append(mesh_obj(f"HeelStrap_{side}", verts, faces,
                             thickness=0.0030))
    return objs


# --------------------------------------------------------------------------
# gonna
# --------------------------------------------------------------------------

def pleats(a, v, seed=0.0, n=26, amp=1.0, hem_fade=0.0):
    """Pieghe continue e leggermente irregolari, non un dente di sega.

    Le armoniche intere chiudono senza discontinuita' sul retro. Una piccola
    deriva lungo la lunghezza evita che le pieghe sembrino scanalature rigide;
    il profilo "a libro" (cresta tonda, valle piu' netta) e' quello che nel
    disegno da' il contrasto di luce fra una piega e l'altra.
    """
    n = max(2, int(n))
    drift = 0.26 * math.sin(v * 2.2 + seed * 0.31) * smoothstep(0.05, 0.8, v)
    phase = n * a + seed + drift
    fold = (0.80 * (math.cos(phase) + 0.26 * math.cos(2.0 * phase - 0.40))
            + 0.13 * math.cos((n // 2) * a + 0.55 + v * 0.30)
            + 0.05 * math.cos((n // 3) * a - 0.90 - v * 0.20))
    # ogni piega ha la sua profondita': un ventaglio di pieghe tutte uguali
    # si legge come una fisarmonica di plastica
    fold *= 1.0 + 0.13 * math.cos(3.0 * a + seed * 0.7)
    envelope = 0.32 + 0.68 * smoothstep(0.0, 0.22, v)
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
    f = pleats(a, v, 0.0, n=23, amp=0.0095, hem_fade=0.30)
    # piega secondaria molto bassa: toglie l'effetto "lamelle" fra le pieghe
    f += 0.0008 * math.cos(a * 47.0 + v * 2.1) * smoothstep(0.15, 0.75, v)
    f += 0.0006 * math.sin(a * 59.0 + v * 1.6) * smoothstep(0.05, 0.5, v)
    return f


def build_underskirt():
    nu, nv = 150, 40
    z_top = SKIRT_TOP_Z - 0.006
    z_bot = 0.196

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
    """Gonna principale: pieghe morbide, orlo irregolare."""
    nu, nv = 288, 72

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
        ("Lap_FrontL", -32, -28, 32, 34, 0.47, "lapB", 0.075, 0.6),
        ("Lap_FrontR",  32,  29, 32, 35, 0.37, "lap",  0.070, 2.1),
        # Due code strette incorniciano la staffa e scendono sotto il resto.
        ("Lap_CenterL", -21, -17, 17, 15, 0.246, "lap3", 0.052, 4.4),
        ("Lap_CenterR",  21,  17, 17, 15, 0.228, "lap3", 0.044, 5.8),
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
            tip=tip, tip_pow=0.78, seed=seed,
            nu=112 if 'Center' not in name else 64, nv=66,
            pleat_n=11, pleat_amp=0.012, corner_lift=0.030,
            edge_tuck=0.0, blend_top=0.92, top_taper=0.78))
    return objs


def drape_specs():
    """Scialli obliqui sui fianchi, appoggiati sotto il davanti avorio.

    Nella reference i pannelli scuri si vedono ai due lati del davanti e
    arrivano a meta' coscia con una punta netta: sono piu' larghi di una
    striscia e restano arretrati rispetto ai lembi chiari.
    """
    R = math.radians
    return [
        ("Drape_L", [(0.0, R(58)), (0.5, R(66)), (1.0, R(74))],
         [(0.0, 0.946), (1.0, 0.570)], [(0.0, R(13.5)), (1.0, R(12.0))], 1.2),
        ("Drape_R", [(0.0, R(-58)), (0.5, R(-66)), (1.0, R(-74))],
         [(0.0, 0.946), (1.0, 0.558)], [(0.0, R(13.5)), (1.0, R(12.0))], 3.4),
        ("Drape_L2", [(0.0, R(86)), (1.0, R(104))],
         [(0.0, 0.930), (1.0, 0.565)], [(0.0, R(10)), (1.0, R(8.5))], 5.0),
        ("Drape_R2", [(0.0, R(-86)), (1.0, R(-104))],
         [(0.0, 0.930), (1.0, 0.560)], [(0.0, R(10)), (1.0, R(8.5))], 7.1),
    ]


def build_drapes():
    """Scialli scuri con punta in basso, piegati come la gonna."""
    objs = []
    drapes = []
    for name, ang, ztab, wtab, seed in drape_specs():
        layer = "drape2" if name.endswith("2") else "drape"
        pnl = Panel(name, ang, ztab, layer, width_table=wtab,
                    tip=0.068 if not name.endswith("2") else 0.050,
                    tip_pow=1.35, seed=seed,
                    pleat_n=13, pleat_amp=0.0075, edge_tuck=0.0,
                    blend_top=0.80, top_taper=0.80, corner_lift=0.010)
        objs.append(pnl.build(nu=120, nv=80, thickness=0.0032))
        drapes.append(pnl)
    return objs, drapes


# --------------------------------------------------------------------------
# fascia e cintura
# --------------------------------------------------------------------------

def sash_top(a):
    """Bordo alto della fascia: sale sui fianchi e si incassa al centro.

    Nella reference il nodo stringe il tessuto verso l'anello, quindi il bordo
    superiore non e' una linea orizzontale ma una V morbida sul davanti.
    """
    knot = -0.011 * math.exp(-(a / 0.75) ** 2)
    return 1.062 + 0.015 * abs(math.sin(a)) ** 1.4 + knot


def waist_pt(a, z, extra=0.0):
    return Vector(((WAIST_RX + extra) * math.sin(a),
                   -(WAIST_RY + extra) * math.cos(a), z))


def sash_wrap(name, a0, a1, z0, z1, width, off, seed=0.0, taper=0.24,
              nu=140, nv=18, roll=0.0022, thickness=0.0026, steep=3.2):
    """Telo diagonale avvolto attorno alla vita.

    Il telo va da ``a0`` a ``a1`` salendo (o scendendo) da ``z0`` a ``z1``: e'
    il modo in cui una fascia si avvolge davvero, e all'incrocio davanti i due
    teli formano la X del nodo. La salita e' ripida al centro (dove i teli si
    incrociano) e si appiattisce sui fianchi; le estremita' si assottigliano e
    rientrano nel corpo, come se fossero infilate sotto gli altri strati.
    """
    zb, zt = 0.5 * (z0 + z1), 0.5 * (z1 - z0)

    def surf(u, v):
        a = a0 + (a1 - a0) * u
        env = smoothstep(0.0, taper, u) * smoothstep(0.0, taper, 1.0 - u)
        w = width * (0.26 + 0.74 * env)
        s = math.tanh(steep * (u - 0.5)) / math.tanh(steep * 0.5)
        zc = zb + zt * s
        t = v - 0.5
        z = zc + t * w
        b = (1.0 - (2.0 * t) ** 2) ** 0.70
        crease = (0.00055 * math.cos(a * 27.0 + t * 2.6 + seed)
                  + 0.00035 * math.cos(a * 44.0 - t * 1.8 + seed * 1.7))
        return waist_pt(a, z, off * (0.35 + 0.65 * env) + roll * b * env + crease)
    return cloth_grid(name, nu, nv, surf, thickness=thickness)


def build_sash():
    """Fascia avorio annodata: corpo, due teli in croce e nodo sull'anello.

    La croce dei teli e' a 0 rad (davanti), all'altezza dell'anello: sopra e
    sotto si vedono i due angoli di stoffa, come nel disegno.
    """
    objs = []
    nu = 216

    def body(u, v):
        a = TAU * u
        top = sash_top(a)
        z = top + (SASH_BOT_Z - top) * v
        # gonfiore del tessuto e pieghe verticali lasciate dal nodo
        fullness = 0.0018 * math.sin(math.pi * v) ** 0.8
        folds = (0.0010 * math.cos(a * 23.0 + 0.6)
                 + 0.0007 * math.cos(a * 41.0 - 1.1)) * math.sin(math.pi * v)
        # il bordo superiore si ripiega verso l'interno: niente taglio vivo
        roll = -0.0042 * (1.0 - smoothstep(0.0, 0.07, v))
        return waist_pt(a, z, fullness + folds + roll)

    objs.append(cloth_grid("Sash_Body", nu, 34, body, thickness=0.004))

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

    # Telai in croce: si incrociano davanti all'anello (che li copre) e le due
    # diagonali divergono subito, come nel disegno. Il telo B passa sotto A.
    objs.append(sash_wrap("Sash_CrossB", -3.08, 3.08, 1.071, 0.956, 0.029,
                          0.0092, seed=3.1, taper=0.11, steep=2.9, nu=220))
    objs.append(sash_wrap("Sash_CrossA", -3.02, 3.02, 0.960, 1.067, 0.031,
                          0.0148, seed=0.9, taper=0.11, steep=2.9, nu=220))
    # seconda passata piu' stretta, visibile sul fianco destro della reference
    objs.append(sash_wrap("Sash_CrossC", 0.35, 2.75, 1.034, 0.964, 0.028,
                          0.0058, seed=5.4, taper=0.22, nv=14, roll=0.0016,
                          steep=1.9))
    # codina che esce dal nodo e si infila sotto la croce, a sinistra
    objs.append(sash_wrap("Sash_CrossD", -0.30, -2.60, 0.992, 1.042, 0.024,
                          0.0034, seed=7.7, taper=0.26, nv=12, roll=0.0014,
                          steep=1.7))
    return objs


def build_belt():
    """Cintura scura diagonale sotto la fascia, non un bordo orizzontale.

    E' il nastro di cuoio che passa dietro l'anello e prosegue nella staffa
    centrale: sta sotto i teli avorio, si vede negli angoli del nodo e sui
    fianchi, come nel disegno.
    """
    def surf(u, v):
        a = TAU * u
        width = 0.036 * (1.0 + 0.05 * math.sin(a * 2.0 + 1.2))
        center = 1.0255 + 0.0235 * math.sin(a + 0.40)
        t = v - 0.5
        z = center + t * width
        bulge = (1.0 - (2.0 * t) ** 2) ** 0.7
        return waist_pt(a, z, 0.0078 + 0.0014 * bulge)
    return [cloth_grid("Belt_Dark", 216, 14, surf, thickness=0.0026)]


def build_buckle_back():
    # Il cuoio dietro la fibbia impedisce di vedere il lino nel foro.
    c = Vector((0.0, -0.1432, 1.0205))
    return [ellipsoid("Buckle_Back", c, (0.0286, 0.0030, 0.0286),
                      segs=40, rings=16)]


RING_C = Vector((0.0, -0.1500, 1.0205))


def build_ring():
    """Fibbia d'ottone sottile con piccoli rivetti e placchetta di attacco."""
    c = RING_C
    objs = [torus("BeltRing", c, (0.0, 1.0, 0.0), 0.0270, 0.0038,
                  seg_major=84, seg_minor=20, squash=1.0, flat=0.46)]
    # controanello interno in rilievo: da' lo spessore "da fibbia" del disegno
    objs.append(torus("BeltRing_Inner", c + Vector((0, 0.0022, 0)),
                      (0.0, 1.0, 0.0), 0.0226, 0.0012,
                      seg_major=64, seg_minor=12, flat=0.80))
    for k in range(8):
        a = TAU * k / 8.0 + 0.13
        p = c + Vector((0.0270 * math.cos(a), -0.0030,
                        0.0270 * math.sin(a)))
        objs.append(ellipsoid(f"Buckle_Stud{k}", p,
                              (0.0009, 0.0007, 0.0009), segs=10, rings=6))
    # placchetta di attacco fra anello e staffa
    objs.append(ellipsoid("Buckle_Clasp", c + Vector((0.0, 0.0014, -0.0250)),
                          (0.0074, 0.0030, 0.0052), segs=24, rings=12))
    return objs


# --------------------------------------------------------------------------
# staffa con i simboli
# --------------------------------------------------------------------------

STRAP_TOP_Z = 1.0512
STRAP_SHOULDER_Z = 0.403
STRAP_TIP_Z = 0.350


def strap_halfwidth(z):
    """Mezza larghezza del nastro, misurata sulla reference.

    Il nastro e' quasi parallelo, appena piu' largo dove corre sui lembi e
    rastremato negli ultimi centimetri prima della punta.
    """
    t = min(1.0, max(0.0, (STRAP_TOP_Z - z) /
                         (STRAP_TOP_Z - STRAP_TIP_Z)))
    return lerp_table([(0.00, 0.0228), (0.16, 0.0246), (0.55, 0.0256),
                       (0.82, 0.0244), (0.93, 0.0218), (1.00, 0.0176)], t)


def strap_point(x, z, off=0.0):
    """Superficie della staffa e dei suoi ricami; davanti = -Y."""
    w = max(strap_halfwidth(z), 1e-3)
    # In vita la staffa passa DIETRO l'anello, appoggiata sulla fascia; appena
    # sotto il bordo della fascia (che la copre) scende davanti ai lembi. Il
    # salto di livello avviene sotto la fascia, cosi' non si vede, e resta
    # ripido: uno strato che sale piano incurva il nastro e storce i ricami.
    if z >= SKIRT_TOP_Z:
        # Sopra la gonna la staffa sale sulla fascia, fino al bordo alto: nella
        # reference il nastro scuro si vede anche sopra l'anello, sopra i teli
        # avorio incrociati. Il gradino di livello sotto la fascia resta
        # nascosto dal bordo inferiore della fascia stessa.
        base = waist_pt(0.0, z, 0.0102)
    else:
        layer = 0.0100 + 0.0285 * smoothstep(0.0, 0.011, SKIRT_TOP_Z - z)
        f = skirt_disp(0.0, z) * smoothstep(0.0, 0.035, SKIRT_TOP_Z - z)
        base = surface(0.0, z, "base", extra=layer + f)
    # Una lieve convessita' mantiene naturale il nastro, senza tagli bianchi.
    y = base.y - off - 0.0022 * (x / w) ** 2
    return Vector((x, y, z))


def strap_bottom_z(side):
    """Bordo inferiore della staffa.

    Come nel disegno la punta non e' un semplice V: al centro c'e' un piccolo
    intaglio che la apre in due lobe, e i due angoli esterni salgono di netto.
    """
    s = abs(side)
    z = STRAP_TIP_Z + (STRAP_SHOULDER_Z - STRAP_TIP_Z) * (s ** 1.9)
    z += 0.0120 * math.exp(-(side / 0.24) ** 2)
    return z


def build_strap():
    nu, nv = 64, 170

    def surf(u, v):
        side = 2.0 * u - 1.0
        end_z = strap_bottom_z(side)
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
        n = max(1, int(math.ceil(math.hypot(x1 - x0, z1 - z0) / 0.005)))
        dense.extend((x0 + (x1 - x0) * i / n,
                      z0 + (z1 - z0) * i / n) for i in range(n))
    dense.append(pts2d[-1])
    return _gold([strap_point(x, z, off) for x, z in dense], width)


def strap_gold():
    """Ricamo centrale della staffa, ricostruito dal disegno.

    Dall'alto: asta sottile, rombo, cerchio con traversa e croce, asta lunga con
    barretta, rombo, asta, e in fondo la fascia decorata con le barrette
    verticali e il doppio V della punta.
    """
    objs = []

    def stroke(points, width=0.0022):
        objs.append(_gold2d(points, width))

    def diamond(cz, rx, rz, width=0.0024):
        stroke([(0, cz + rz), (rx, cz), (0, cz - rz),
                (-rx, cz), (0, cz + rz)], width)

    # --- parte alta, sotto l'anello
    stroke([(0.0, 0.966), (0.0, 0.928)], 0.0018)
    diamond(0.912, 0.0058, 0.0105)
    # --- cerchio con traversa e croce
    stroke([(0.0, 0.900), (0.0, 0.884)], 0.0017)
    circle = [(0.0168 * math.cos(TAU * i / 56),
               0.858 + 0.0168 * math.sin(TAU * i / 56)) for i in range(57)]
    stroke(circle, 0.0027)
    stroke([(-0.0115, 0.8382), (0.0115, 0.8382)], 0.0022)
    stroke([(0.0, 0.8382), (0.0, 0.8060)], 0.0020)
    stroke([(-0.0082, 0.8210), (0.0082, 0.8210)], 0.0018)
    # --- asta lunga con barretta
    stroke([(0.0, 0.8040), (0.0, 0.6980)], 0.0020)
    stroke([(-0.0075, 0.7620), (0.0075, 0.7620)], 0.0017)
    diamond(0.6800, 0.0068, 0.0115)
    stroke([(0.0, 0.6660), (0.0, 0.5330)], 0.0021)
    # --- doppio V della punta, contenuto nel nastro
    stroke([(-0.0228, 0.4530), (0.0, 0.4060), (0.0228, 0.4530)], 0.0030)
    stroke([(-0.0192, 0.4345), (0.0, 0.3960), (0.0192, 0.4345)], 0.0021)
    for side in (-1, 1):
        stroke([(side * 0.0204, 0.4720), (side * 0.0204, 0.4500)], 0.0022)
        stroke([(side * 0.0090, 0.4100), (side * 0.0090, 0.4310)], 0.0025)
    # --- fascia decorata sopra la punta: barrette verticali fra due righe
    stroke([(-0.0150, 0.5480), (0.0150, 0.5480)], 0.0019)
    for k in range(-3, 4):
        x = k * 0.0042
        stroke([(x, 0.5458), (x, 0.5290)], 0.0014)
    stroke([(-0.0150, 0.5268), (0.0150, 0.5268)], 0.0019)
    # --- filetto dorato lungo i due bordi del nastro
    for side in (-1, 1):
        edge = []
        z = 1.0340
        while z > 0.4560:
            hw = strap_halfwidth(z)
            edge.append((side * (hw - 0.0032), z))
            z -= 0.012
        stroke(edge, 0.0017)
    return objs


# --------------------------------------------------------------------------
# rune sugli scialli scuri
# --------------------------------------------------------------------------

def build_drape_runes(drapes):
    """Bordi e motivi geometrici dorati, applicati ai veri lembi laterali.

    Nella reference lo scialle scuro ha un bordo dorato continuo sui due lati
    lunghi, una linea che segue la punta e, sopra, due sigilli angolari: un
    gancio a spirale squadrata e un rombo. Sono ricami spessi, non un filo.
    """
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
        big = not name.endswith("2")
        # bordi continui lungo i due lati del lembo
        for u in (0.075, 0.925):
            path(pnl, name + "_border", [(u, 0.06), (u, 0.93)],
                 0.0027 if big else 0.0022)
        # bordo che segue l'orlo a punta
        path(pnl, name + "_hem", [(0.10, 0.905), (0.50, 0.945), (0.90, 0.905)],
             0.0024 if big else 0.0019)
        if not big:
            continue
        # gancio a spirale squadrata (il sigillo della reference)
        path(pnl, name + "_rune",
             [(0.38, 0.185), (0.38, 0.335), (0.63, 0.335),
              (0.63, 0.235), (0.485, 0.235)], 0.0029)
        # asta sotto il gancio
        path(pnl, name + "_stem", [(0.38, 0.185), (0.38, 0.135)], 0.0024)
        # rombo piu' in basso
        path(pnl, name + "_diamond",
             [(0.50, 0.545), (0.635, 0.625), (0.50, 0.705),
              (0.365, 0.625), (0.50, 0.545)], 0.0026)
        # due barrette ai lati del rombo
        for u in (0.30, 0.70):
            path(pnl, name + "_bar", [(u, 0.600), (u, 0.650)], 0.0019)
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


def tag_group(objs, name):
    for ob in objs:
        vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
        vg.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")


def tag_keep(objs):
    """Segna i vertici dei dettagli sottili (ricami, nastri, staffa).

    ``02_optimize`` usa questo gruppo per decimare molto meno proprio questi
    pezzi: a 60k triangoli un ricamo dorato largo 3 mm sparirebbe.
    """
    tag_group(objs, "keep")


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
    sash = build_sash()
    soles = [o for o in sandals if o.name.startswith("Sole")]
    straps = [o for o in sandals if not o.name.startswith("Sole")]
    # I teli incrociati e la cintura sono stoffa, ma con bordi vivi e pochi
    # centimetri di larghezza: la decimazione della gonna li sfrangerebbe.
    # Vanno nel gruppo intermedio, decimato molto meno.
    mid = [o for o in sash if o.name.startswith("Sash_Cross")]
    mid += build_belt()

    groups = {
        "legs": build_legs(),
        "feet": build_feet(),
        "wrap": build_legwraps() + straps,
        "sole": soles,
        "fabric": (build_underskirt() + build_skirt() + build_lappets()
                   + [o for o in sash if o.name not in {m.name for m in mid}]),
        "dark": drapes + strap_body + build_buckle_back(),
        "gold": build_ring(),
        "gold_trim": build_drape_runes(drape_panels) + strap_gold_parts,
    }
    all_objs = []
    for key, objs in groups.items():
        assign_material(objs, PART_MATERIAL[key])
        if key in KEEP_GROUPS:
            tag_keep(objs)
        all_objs += objs
    tag_group(mid, "mid")
    all_objs += mid
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
