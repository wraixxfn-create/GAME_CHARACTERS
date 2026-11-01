"""DRESS1 — costruzione della geometria (dettagli dalla reference).

Il capo e' ridisegnato da zero seguendo il concept: gonna in lino avorio a
**pieghe morbide** profonde (creste tonde, valli strette in ombra), silhouette
ad A che si allarga regolare fino all'orlo a punte asimmetriche, fascia
incrociata in vita con anello d'ottone, staffa scura liscia con simboli
geometrici dorati e scialli scuri stretti sui fianchi con rune.

Questo e' il **solo capo**: gambe, piedi, caviglie e sandali sono stati tolti,
cosi' la gonna resta un asset di abbigliamento da montare su un personaggio.
L'apertura in vita e quella in fondo sono chiuse da una fodera interna, quindi
il capo si guarda anche da sotto senza vedere un guscio vuoto.

La gonna e i lembi usano la stessa superficie ``surface(a, z, layer)`` e lo
stesso spostamento di piega. Gli scialli hanno uno strato piu' teso; staffa e
ricami condividono la rispettiva superficie di appoggio.

Quote (metri, Z in alto, davanti = -Y). Il capo resta alla quota che avrebbe
indossato: l'origine e' al suolo, sotto la gonna.

```
z = 1.080  bordo alto della fascia (ai fianchi)
z = 1.021  cintura scura + anello
z = 0.952  fondo della fascia
z = 0.964  attacco della gonna
z = 0.300  orlo medio (falde piu' lunghe sotto)
z = 0.196  fondo della fodera interna
z = 0.000  suolo (origine, dove poggerebbero i piedi)
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

SASH_BOT_Z = 0.936
WAIST_RX = 0.152
WAIST_RY = 0.126

SKIRT_TOP_Z = 0.964

# (z, rx, ry) — profilo ad A: stretto in vita, poi discesa quasi lineare.
# Nella reference la gonna non si gonfia sui fianchi ne' rientra sul fondo:
# si allarga in modo regolare e monotono fino all'orlo, dove la larghezza e'
# circa 1,7 volte la vita. Il vecchio profilo a campana (massimo a meta'
# coscia e rientro sul fondo) leggeva come palloncino, non come lino appeso.
PROFILE = [
    (0.964, 0.150, 0.126),
    (0.900, 0.170, 0.143),
    (0.820, 0.188, 0.158),
    (0.740, 0.201, 0.169),
    (0.660, 0.211, 0.177),
    (0.580, 0.219, 0.184),
    (0.500, 0.226, 0.190),
    (0.430, 0.231, 0.194),
    (0.370, 0.235, 0.198),
    (0.320, 0.238, 0.200),
    (0.270, 0.241, 0.203),
    (0.220, 0.243, 0.205),
    (0.170, 0.245, 0.206),
    (0.130, 0.246, 0.207),
]


# offset di raggio per strato (m).
# Gli strati sono volutamente vicini (6-8 mm): nella reference i lembi sono
# sovrapposti e aderenti, non un ventaglio di ali staccate dal corpo.
LAYER = {
    "under": -0.045,
    "base": 0.000,
    "drape": 0.031,      # scialli scuri: sopra i veli, sui fianchi
    "drape2": 0.034,
    "lapB": 0.012,       # veli avorio, dal piu' basso al piu' alto
    "lap": 0.016,
    "lap2": 0.019,
    "lap3": 0.022,
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

    La gonna di base ha un orlo mosso da tre lobi asimmetrici: nella reference
    il fondo non e' una riga orizzontale ma una linea di punte e intacchi, e
    le punte lunghe vengono dalle **falde** sovrapposte (vedi
    ``build_lappets``). I lobi qui disegnano le campate fra una punta e
    l'altra; tenere l'orlo troppo regolare faceva leggere le falde come
    toppe applicate invece che come il fondo del tessuto.
    """
    lobes = (0.034 * max(0.0, math.sin(a + 0.30)) ** 2.0
             + 0.020 * max(0.0, math.sin(2.0 * a - 1.02)) ** 2.4
             + 0.012 * max(0.0, math.sin(3.0 * a + 2.0)) ** 2.8)
    return 0.252 - lobes


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
# gonna
# --------------------------------------------------------------------------

PLEAT_N = 20          # pieghe morbide lungo tutto il giro
PLEAT_DEPTH = 0.042   # profondita' cresta-valle all'orlo (m)


def drape_fold(x):
    """Profilo di una piega **morbida** di lino appeso.

    Nella reference le pieghe non sono pressate: sono campate di stoffa che
    ricade, con la cresta tonda e larga e la valle stretta in ombra. Una
    sinusoide pura avrebbe creste e valli della stessa larghezza (stoffa
    gonfia); una piega a coltello avrebbe la faccia dritta (lino stirato).
    Qui ``c`` e' una campana cosinusoidale e l'esponente < 1 allarga le
    creste e stringe le valli in una linea d'ombra sottile, come nel disegno.

    ``x`` va da 0 (cresta) a 1 (cresta successiva); la valle sta a 0.5.
    """
    c = 0.5 * (1.0 + math.cos(TAU * x))
    return c ** 0.50


# media del profilo su un periodo: centra la piega fra cresta e valle
FOLD_MEAN = sum(drape_fold(i / 512.0) for i in range(512)) / 512.0


def pleats(a, v, seed=0.0, n=PLEAT_N, amp=1.0, hem_fade=0.0):
    """Spostamento radiale delle pieghe (cresta +, valle -).

    ``amp`` e' la profondita' cresta-valle in metri; il valore restituito e'
    in unita' di ``amp``. Le pieghe non sono tutte uguali: due armoniche lente
    ne abbassano alcune lungo il giro, e una lieve deriva verticale evita il
    tubo scanalato. Le valli restano allineate, quindi le linee d'ombra
    corrono continue dalla vita all'orlo come nel disegno.
    """
    n = max(2, int(n))
    drift = 0.10 * math.sin(v * 2.2 + seed * 0.31) * smoothstep(0.03, 0.7, v)
    phase = n * a + seed * 1.7 + drift * 2.0
    x = (phase / TAU) % 1.0
    fold = drape_fold(x) - FOLD_MEAN
    # pieghe di profondita' diversa: un ventaglio perfetto pare plastica
    depth = 1.0 + 0.20 * math.cos(3.0 * a + seed * 0.7) \
        + 0.09 * math.cos(7.0 * a - 0.4 + seed)
    depth = max(0.35, depth)
    # sotto la fascia la stoffa e' tirata: le pieghe nascono dolci
    envelope = 0.22 + 0.78 * smoothstep(0.02, 0.34, v)
    if hem_fade:
        envelope *= 1.0 - hem_fade * smoothstep(0.90, 1.0, v)
    return amp * fold * depth * envelope


def skirt_disp(a, z):
    """Spostamento radiale della gonna, condiviso da tutti gli strati.

    Il tratto scende dall'alto all'orlo: la distanza e' positiva. Usare il
    segno opposto azzerava le pieghe per ogni lembo e causava compenetrazioni.
    """
    span = SKIRT_TOP_Z - hem_z(a)
    v = min(1.0, max(0.0, (SKIRT_TOP_Z - z) / max(span, 1e-6)))
    # la fascia tira il lino al centro davanti: li' le pieghe sono piu' basse
    soft = 0.52 + 0.48 * (1.0 - math.exp(-(a / 0.62) ** 2))
    f = pleats(a, v, 0.0, n=PLEAT_N, amp=PLEAT_DEPTH * soft)
    # increspatura secondaria molto bassa: toglie l'effetto "tubo"
    f += 0.0009 * math.cos(a * 41.0 + v * 2.1) * smoothstep(0.20, 0.80, v)
    f += 0.0006 * math.sin(a * 57.0 + v * 1.6) * smoothstep(0.10, 0.55, v)
    return f


def build_lining():
    """Fodera interna che **chiude** il capo.

    Il vestito non ha gambe dentro: senza fodera, guardando sotto l'orlo si
    vede il guscio vuoto. La fodera scende dalla gonna e si richiude verso
    l'interno formando una sacca profonda: da fuori si legge come il rovescio
    della stoffa, da sotto il capo e' chiuso. Il fondo resta alto e stretto,
    cosi' non si vede un "secchio" affacciato all'orlo.
    """
    nu, nv = 80, 14

    def surf(u, v):
        a = TAU * u
        # v: 0 = sotto la gonna, 1 = fondo della sacca
        z = 0.700 - 0.330 * v ** 1.08
        # restringimento rapido: la sacca sta lontana dalle valli delle pieghe,
        # altrimenti affiora fra una piega e l'altra come un cilindro chiaro
        shrink = 1.0 - 0.62 * smoothstep(0.0, 1.0, v)
        rx = (prof(0.60)[0] - 0.070) * shrink
        ry = (prof(0.60)[1] - 0.062) * shrink
        p = Vector((rx * math.sin(a), -ry * math.cos(a), z))
        p += normal_dir(a) * (0.0010 * math.cos(a * 17.0 + v * 2.0) * (1 - v))
        return p

    return [cloth_grid("Lining", nu, nv, surf, thickness=0.0)]


def build_underskirt():
    """Secondo strato di lino appena sotto la gonna (il "sottogonna").

    E' piu' corto e meno pieghettato: si vede solo nel salto di livello fra le
    falde, come nella reference, e non deve sporgere sotto l'orlo.
    """
    nu, nv = 92, 16
    z_top = SKIRT_TOP_Z - 0.010
    z_bot = 0.210

    def surf(u, v):
        a = TAU * u
        z = z_top + (z_bot - z_top) * v ** 1.05
        rx, ry = radius(z, "under")
        f = pleats(a, v, 0.4, n=15, amp=0.0075, hem_fade=0.45)
        p = surface(a, z, "under", extra=f)
        p += normal_dir(a) * wrinkle(p, 0.0006, 11.0, 1.3)
        return p

    return [cloth_grid("UnderSkirt", nu, nv, surf, thickness=0.0)]


def build_skirt():
    """Gonna principale: pieghe a coltello fitte, orlo appena mosso.

    La griglia e' gia' alla densita' del LOD0 (sette colonne per piega): cosi'
    la decimazione non deve toccarla e le pieghe restano nette anche nel file
    finale. Una griglia sovradimensionata veniva ridotta all'8% e diventava
    una stoffa molle.
    """
    nu, nv = PLEAT_N * 7, 26

    def surf(u, v):
        a = TAU * u
        z = SKIRT_TOP_Z + (hem_z(a) - SKIRT_TOP_Z) * v ** 1.02
        # Anche i lembi chiamano queste funzioni: bordi e creste coincidono.
        p = surface(a, z, "base", extra=skirt_disp(a, z))
        # rumore basso: se e' troppo forte la crease della piega si
        # spezza in dentini visibili in controluce
        p += normal_dir(a) * wrinkle(p, 0.00028, 15.0, 3.1)
        return p

    return [cloth_grid("Skirt", nu, nv, surf, thickness=0.0)]


class Panel:
    """Lembo parametrico appoggiato sulla gonna.

    Espone ``pt(u, v, extra)`` e ``nrm(u, v)``: cosi' i ricami possono essere
    definiti nello stesso spazio parametrico del lembo e restano *sempre*
    sopra la stoffa, senza sbordare.
    """

    def __init__(self, name, ang_table, z_table, layer, width_table=None,
                 tip=0.0, tip_pow=1.0, seed=0.0, pleat_n=27,
                 pleat_amp=0.010, edge_tuck=0.0, corner_lift=0.0,
                 skew=0.0, phase=0.0, blend_top=0.0, top_taper=0.0,
                 follow=1.0, edge_roll=0.0, clearance=(0.0, 0.0)):
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
        self.follow = follow
        self.edge_roll = edge_roll
        # (in alto, in basso): margine radiale aggiuntivo rispetto alla gonna.
        # Le pieghe a coltello hanno creste di 3 cm: un pannello che non le
        # segue deve stare sopra le creste, altrimenti sparisce nelle valli.
        self.clearance = clearance

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
        z += 0.0016 * math.sin(u * 5.0 + self.seed) * smoothstep(0.85, 1.0, v)
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
        if self.name.startswith("Lap_") and self.follow:
            for center in (0.29, 0.70):
                center += 0.018 * math.sin(v * 3.0 + self.seed)
                creases -= (0.0030 * math.exp(-((u - center) / 0.035) ** 2)
                            * smoothstep(0.03, 0.18, v) * fade)
        elif self.name.startswith("Drape"):
            # la lana degli scialli ricade in pieghe oblique, non parallele
            # all'orlo: e' quello che la distingue da una toppa di cuoio
            for k, (u0, tilt) in enumerate(((0.18, 0.55), (0.52, 0.42),
                                            (0.84, 0.62))):
                line = u0 + tilt * (v - 0.45) + 0.02 * math.sin(v * 2.4 + k)
                creases -= (0.0034 * math.exp(-((u - line) / 0.045) ** 2)
                            * smoothstep(0.02, 0.20, v))
        # Il bordo del lembo si arrotola leggermente verso l'interno: e' il
        # bordo vivo che nel disegno separa due falde sovrapposte.
        rolled = -self.edge_roll * (edge ** 3.0) * smoothstep(0.02, 0.25, v)
        clear = (self.clearance[0]
                 + (self.clearance[1] - self.clearance[0]) * v)
        p = surface(a, z, "base", extra=LAYER[self.layer] + sd * self.follow
                    + f * amp + creases + rolled + clear + extra)
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
          tip_pow=1.0, seed=0.0, nu=130, nv=58, thickness=0.0035,
          pleat_n=27, pleat_amp=0.010, edge_tuck=0.0, corner_lift=0.0,
          skew=0.0, phase=0.0, blend_top=0.0, top_taper=0.0,
          follow=1.0, edge_roll=0.0, clearance=(0.0, 0.0)):
    pnl = Panel(name, ang_table, z_table, layer, width_table, tip, tip_pow,
                seed, pleat_n, pleat_amp, edge_tuck, corner_lift, skew, phase,
                blend_top, top_taper, follow, edge_roll, clearance)
    return pnl.build(nu, nv, thickness)


def build_lappets():
    """Veli avorio sovrapposti: la gonna "a punte" del concept.

    Nel disegno la gonna non finisce con un orlo dritto: davanti scendono
    **veli** sovrapposti, ognuno chiuso da una V netta e sfalsata, e sotto la
    staffa resta una lingua centrale piu' lunga. I veli sono la stessa stoffa
    pieghettata della gonna, quindi seguono la sua superficie (``follow=1``)
    con un margine costante: le creste dei veli stanno esattamente sopra le
    creste della gonna e non nasce nessun incrocio.

    La lingua centrale e' stretta di proposito: la staffa scura la copre quasi
    tutta, e sotto la punta della staffa se ne vede solo l'estremo, come nel
    disegno.
    """
    R = math.radians
    defs = [
        # nome, angolo alto, angolo basso, larghezza alta, larghezza bassa,
        #       fondo, strato, punta, seed, sollevamento angoli
        ("Lap_Tongue", -4, 5, 8, 7, 0.210, "lap3", 0.085, 1.4, 0.012),
        # Due veli larghissimi: coprono quasi tutto il davanti e si
        # sovrappongono al centro, cosi' l'orlo e' continuo. Nella reference
        # le punte davanti sono le piu' lunghe e scendono sfalsate.
        ("Lap_FrontL", -20, -27, 38, 32, 0.272, "lapB", 0.138, 0.6, 0.048),
        ("Lap_FrontR", 23, 30, 37, 31, 0.262, "lap", 0.132, 2.1, 0.046),
        ("Lap_MidL", -58, -67, 22, 19, 0.330, "lap2", 0.118, 4.4, 0.034),
        ("Lap_MidR", 60, 68, 21, 18, 0.318, "lap3", 0.112, 5.8, 0.032),
        ("Lap_SideL", 82, 91, 17, 15, 0.400, "lap2", 0.096, 3.7, 0.026),
        ("Lap_SideR", -82, -92, 17, 15, 0.388, "lap3", 0.092, 5.2, 0.024),
        ("Lap_BackL", 152, 161, 26, 23, 0.330, "lapB", 0.112, 6.6, 0.030),
        ("Lap_BackR", -152, -162, 25, 22, 0.344, "lap", 0.108, 7.3, 0.028),
        # telo diagonale che attraversa la vita e scende a sinistra
        ("Lap_WaistL", -46, -34, 25, 21, 0.400, "lap", 0.130, 8.4, 0.026),
    ]
    objs = []
    for name, a0, a1, w0, w1, zbot, layer, tip, seed, lift in defs:
        objs.append(panel(
            name, [(0.0, R(a0)), (1.0, R(a1))],
            [(0.0, SKIRT_TOP_Z + 0.002), (1.0, zbot)], layer,
            width_table=[(0.0, R(w0)), (1.0, R(w1))],
            tip=tip, tip_pow=0.62, seed=seed,
            nu=40, nv=22, thickness=0.0016,
            pleat_n=13, pleat_amp=0.005, corner_lift=lift,
            edge_tuck=0.0, blend_top=0.92, top_taper=0.90,
            edge_roll=0.0030, follow=1.0,
            clearance=(0.0, 0.004)))
    return objs


def drape_specs():
    """Scialli obliqui sui fianchi, con punta a meta' coscia.

    Nella reference i pannelli scuri stanno **sui fianchi**, quasi di profilo:
    dal davanti si vedono solo come due lame scure ai bordi della silhouette,
    non come due toppe appoggiate sulla gonna. Per questo partono da 62 gradi
    e arrivano oltre i 100: sono la superficie esterna del fianco, mentre il
    davanti resta avorio.
    """
    R = math.radians
    return [
        ("Drape_L", [(0.0, R(62)), (0.5, R(68)), (1.0, R(75))],
         [(0.0, 0.944), (1.0, 0.500)], [(0.0, R(13.0)), (1.0, R(11.5))], 1.2),
        ("Drape_R", [(0.0, R(-62)), (0.5, R(-68)), (1.0, R(-75))],
         [(0.0, 0.944), (1.0, 0.488)], [(0.0, R(13.0)), (1.0, R(11.5))], 3.4),
        ("Drape_L2", [(0.0, R(88)), (1.0, R(102))],
         [(0.0, 0.928), (1.0, 0.516)], [(0.0, R(9.5)), (1.0, R(8.0))], 5.0),
        ("Drape_R2", [(0.0, R(-88)), (1.0, R(-102))],
         [(0.0, 0.928), (1.0, 0.512)], [(0.0, R(9.5)), (1.0, R(8.0))], 7.1),
    ]


def build_drapes():
    """Scialli scuri con punta in basso, piegati come la gonna."""
    objs = []
    drapes = []
    for name, ang, ztab, wtab, seed in drape_specs():
        layer = "drape2" if name.endswith("2") else "drape"
        pnl = Panel(name, ang, ztab, layer, width_table=wtab,
                    tip=0.085 if not name.endswith("2") else 0.060,
                    tip_pow=1.0, seed=seed,
                    pleat_n=13, pleat_amp=0.0075, edge_tuck=0.0,
                    blend_top=0.80, top_taper=0.80, corner_lift=0.024,
                    follow=1.0, edge_roll=0.0024,
                    clearance=(0.0, 0.003))
        objs.append(pnl.build(nu=40, nv=22, thickness=0.0018))
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
    # il bordo non e' una circonferenza tagliata: la stoffa si increspa
    bunch = (0.0016 * math.cos(a * 7.0 + 0.5)
             + 0.0009 * math.cos(a * 13.0 - 1.2))
    # sin^2 e' derivabile ovunque: la vecchia |sin|^1.4 lasciava uno spigolo
    # sul retro, dove la fascia sembrava tagliata con la sega.
    rise = 0.015 * math.sin(a) ** 2
    return 1.062 + rise + knot + bunch


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
        # i bordi lunghi del telo rientrano nella fascia: un taglio vivo
        # sollevato leggeva come una scheggia chiara appoggiata al nastro
        return waist_pt(a, z, off * (0.35 + 0.65 * env) * (0.30 + 0.70 * b)
                        + roll * b * env + crease)
    return cloth_grid(name, nu, nv, surf, thickness=thickness)


def build_sash():
    """Fascia avorio annodata: corpo, teli in croce e nodo sull'anello.

    Nel concept la fascia non e' un tubo liscio: e' stoffa **avvolta in
    diagonale**, con le pieghe che spirano attorno alla vita e si stringono
    verso l'anello. Qui le pieghe sono solchi veri nella superficie (non
    dipinti) e seguono ``k*a + m*z``, cioe' spirali continue: si vedono girare
    anche di profilo, che e' quello che rende leggibile il volume del nodo.
    """
    objs = []
    nu = 96

    def body(u, v):
        a = TAU * u
        top = sash_top(a)
        z = top + (SASH_BOT_Z - top) * v
        # spirali di stoffa avvolta: piu' marcate a meta' altezza
        t = smoothstep(0.0, 0.18, v) * (1.0 - smoothstep(0.80, 1.0, v))
        wrap = (0.0026 * math.cos(4.0 * a + 46.0 * z)
                + 0.0013 * math.cos(9.0 * a - 61.0 * z + 1.1)
                + 0.0007 * math.cos(15.0 * a + 88.0 * z + 2.3)) * t
        # il nodo stringe il tessuto verso l'anello
        pinch = -0.0038 * math.exp(-(a / 0.62) ** 2) * smoothstep(0.0, 0.22, v)
        # il bordo superiore si ripiega verso l'interno: niente taglio vivo
        roll = -0.0022 * (1.0 - smoothstep(0.0, 0.12, v))
        return waist_pt(a, z, wrap + pinch + roll)

    objs.append(cloth_grid("Sash_Body", nu, 22, body, thickness=0.0))

    def liner(u, v):
        a = TAU * u
        return waist_pt(a, sash_top(a) - 0.003 - 0.042 * v,
                        -0.005 - 0.025 * v)

    objs.append(cloth_grid("Sash_Liner", nu, 5, liner, thickness=0.0))

    def floor(u, v):
        a = TAU * u
        r = 1.0 - 0.94 * v ** 1.6
        z = sash_top(a) - 0.020 - 0.560 * v
        return Vector(((WAIST_RX - 0.006) * r * math.sin(a),
                       -(WAIST_RY - 0.006) * r * math.cos(a), z))

    objs.append(cloth_grid("Sash_Floor", nu, 4, floor, thickness=0.0))

    # Bordo superiore arrotolato: un tubo di stoffa che gira attorno alla vita
    # e si richiude verso l'interno. Senza, dall'alto si vedeva il taglio vivo
    # della fascia come una lamiera.
    rim = []
    n_rim = 128
    for i in range(n_rim + 1):
        a = TAU * i / n_rim
        rim.append(waist_pt(a, sash_top(a) - 0.0030, 0.0012))
    objs.append(tube("Sash_Roll", rim, 0.0058, segs=12, caps=False))

    # Teli in croce: si incrociano davanti all'anello (che li copre) e le due
    # diagonali divergono subito, come nel disegno. Il telo B passa sotto A.
    objs.append(sash_wrap("Sash_CrossB", -3.08, 3.08, 1.074, 0.954, 0.030,
                          0.0078, seed=3.1, taper=0.11, steep=2.9, nu=92,
                          nv=12, thickness=0.0))
    objs.append(sash_wrap("Sash_CrossA", -3.02, 3.02, 0.948, 1.030, 0.026,
                          0.0112, seed=0.9, taper=0.11, steep=2.9, nu=92,
                          nv=12, thickness=0.0))
    # seconda passata piu' stretta, visibile sul fianco destro della reference
    objs.append(sash_wrap("Sash_CrossC", 0.35, 2.75, 1.038, 0.962, 0.030,
                          0.0056, seed=5.4, taper=0.22, nv=9, roll=0.0016,
                          nu=72, steep=1.9, thickness=0.0))
    # codina che esce dal nodo e si infila sotto la croce, a sinistra
    objs.append(sash_wrap("Sash_CrossD", -0.30, -2.60, 0.988, 1.046, 0.026,
                          0.0030, seed=7.7, taper=0.26, nv=8, roll=0.0014,
                          nu=64, steep=1.7, thickness=0.0))
    # nodo: fascio di stoffa stretto fra i due teli, nascosto dietro anello
    # e cintura: nella reference non sporgono barrette chiare ai lati della
    # fibbia, quindi il nodo resta sotto il nastro scuro.
    knot = []
    for i in range(7):
        t = i / 6.0
        ang = -0.22 + 0.44 * t
        z = 1.0295 + 0.0050 * math.sin(math.pi * t)
        knot.append(waist_pt(ang, z, 0.0115 - 0.0025 * abs(t - 0.5)))
    objs.append(ribbon("Sash_Knot", knot, 0.0150, thickness=0.0036))
    return objs


def build_belt():
    """Cintura scura diagonale sotto la fascia, non un bordo orizzontale.

    E' il nastro di cuoio che passa dietro l'anello e prosegue nella staffa
    centrale. Nel disegno si vede **sopra** i teli avorio, ai lati del nodo:
    qui sta appena fuori dalla fascia (0,016 m) e la sua quota segue una
    sinusoide, quindi entra ed esce dagli incroci di stoffa invece di restare
    una cintura da pantalone.
    """
    def surf(u, v):
        a = TAU * u
        width = 0.032 * (1.0 + 0.06 * math.sin(a * 2.0 + 1.2))
        center = 1.0210 + 0.0230 * math.sin(a + 0.40)
        t = v - 0.5
        z = center + t * width
        bulge = (1.0 - (2.0 * t) ** 2) ** 0.7
        # Il nastro sta **sulla** fascia: il raggio si ricava dalla fascia
        # stessa (gonfiore + spirali) invece di essere un offset fisso, che
        # sul retro la lasciava sospesa.
        fold = (0.0026 * math.cos(4.0 * a + 46.0 * z)
                + 0.0013 * math.cos(9.0 * a - 61.0 * z + 1.1))
        env = smoothstep(0.0, 0.18, (z - sash_top(a)) / (SASH_BOT_Z - sash_top(a)))
        return waist_pt(a, z, 0.0185 + 0.0016 * bulge + fold * env * 0.6)
    return [cloth_grid("Belt_Dark", 96, 8, surf, thickness=0.0022)]


def build_buckle_back():
    # Il cuoio dietro la fibbia impedisce di vedere il lino nel foro.
    c = Vector((0.0, -0.1492, 1.0265))
    return [ellipsoid("Buckle_Back", c, (0.0368, 0.0034, 0.0368),
                      segs=24, rings=10)]


RING_C = Vector((0.0, -0.1500, 1.0265))


def build_ring():
    """Fibbia d'ottone: un cerchio pulito con la placchetta di attacco."""
    c = RING_C
    # Nella reference l'anello e' un cerchio d'ottone liscio: niente rivetti
    # ne' controanello in rilievo, solo il nastro scuro che si vede nel foro.
    objs = [torus("BeltRing", c, (0.0, 1.0, 0.0), 0.0322, 0.0046,
                  seg_major=56, seg_minor=12, squash=1.0, flat=0.46)]
    # placchetta di attacco fra anello e staffa
    objs.append(ellipsoid("Buckle_Clasp", c + Vector((0.0, 0.0014, -0.0330)),
                          (0.0086, 0.0034, 0.0060), segs=16, rings=8))
    return objs


# --------------------------------------------------------------------------
# staffa con i simboli
# --------------------------------------------------------------------------

STRAP_TOP_Z = 1.0512
STRAP_SHOULDER_Z = 0.398
STRAP_TIP_Z = 0.322


def strap_halfwidth(z):
    """Mezza larghezza del nastro, misurata sulla reference.

    Il nastro e' quasi parallelo, appena piu' largo dove corre sui lembi e
    rastremato negli ultimi centimetri prima della punta.
    """
    t = min(1.0, max(0.0, (STRAP_TOP_Z - z) /
                         (STRAP_TOP_Z - STRAP_TIP_Z)))
    return lerp_table([(0.00, 0.0272), (0.16, 0.0300), (0.55, 0.0316),
                       (0.82, 0.0306), (0.93, 0.0280), (1.00, 0.0224)], t)


def strap_point(x, z, off=0.0):
    """Superficie della staffa e dei suoi ricami; davanti = -Y.

    La staffa e' **incollata** alla stoffa: per ogni ``x`` si calcola l'angolo
    reale sulla gonna e si segue la piega in quel punto. Prima il nastro usava
    lo spostamento del centro davanti per tutta la larghezza e, dove le creste
    delle pieghe rientravano di piu', il lino affiorava ai bordi del nastro
    spezzandolo in strisce.
    """
    w = max(strap_halfwidth(z), 1e-3)
    if z >= SKIRT_TOP_Z:
        # Sopra la gonna la staffa sale sulla fascia, fino al bordo alto: nella
        # reference il nastro scuro si vede anche sopra l'anello, sopra i teli
        # avorio incrociati. Il gradino di livello sotto la fascia resta
        # nascosto dal bordo inferiore della fascia stessa.
        rx = WAIST_RX + 0.0168
        a = math.asin(max(-1.0, min(1.0, x / rx)))
        base = waist_pt(a, z, 0.0168)
    else:
        # Nella reference la staffa e' un nastro di cuoio **liscio**: i bordi
        # scendono dritti e la superficie non segue una piega per colonna.
        # Seguire le creste una a una (come prima) ondulava i bordi e faceva
        # affiorare il lino a strisce. Qui il nastro segue solo la bombatura
        # del centro davanti e resta teso sopra le creste, come un cuoio
        # appeso all'anello: margine costante sui veli pieghettati.
        # raccordo morbido con il tratto in fascia: senza, il nastro piegava
        # di netto sul bordo della gonna e leggeva come un collo ripiegato
        t = smoothstep(0.86, SKIRT_TOP_Z, z)
        off_z = 0.0420 - 0.0220 * t
        f_blend = smoothstep(0.0, 0.035, SKIRT_TOP_Z - z)
        rx, _ = radius(z, "base")
        a = math.asin(max(-1.0, min(1.0, x / max(rx, 1e-6))))
        base = surface(a, z, "base",
                       extra=off_z + 0.50 * skirt_disp(0.0, z) * f_blend)
    # Una lieve convessita' mantiene naturale il nastro, senza tagli bianchi.
    y = base.y - off - 0.0018 * (x / w) ** 2
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
    nu, nv = 28, 64

    def surf(u, v):
        side = 2.0 * u - 1.0
        end_z = strap_bottom_z(side)
        z = STRAP_TOP_Z + (end_z - STRAP_TOP_Z) * v
        x = side * strap_halfwidth(z)
        return strap_point(x, z)

    body = cloth_grid("Strap", nu, nv, surf, thickness=0.0025)
    return [body], strap_gold()


def _strap_frame(x, z, d=0.0012):
    """(normale, direzione di larghezza) sulla superficie della staffa.

    La staffa e' un offset **radiale** della gonna, quindi la sua normale e'
    quasi radiale: calcolarla dalle sole derivate (x, z) la faceva ruotare di
    40 gradi sulle creste delle pieghe, e i ricami "scivolavano" di lato
    sparendo dentro la stoffa. Qui la normale e' il versore radiale corretto
    con la pendenza verticale, e la larghezza corre lungo il giro.
    """
    p = strap_point(x, z)
    a = math.atan2(p.x, -p.y)
    er = Vector((math.sin(a), -math.cos(a), 0.0))
    ea = Vector((math.cos(a), math.sin(a), 0.0))
    t = (strap_point(x, z + d) - strap_point(x, z - d))
    if t.length < 1e-9:
        t = Vector((0.0, 0.0, 1.0))
    t.normalize()
    n = er - t * er.dot(t)
    if n.length < 1e-9:
        n = er.copy()
    n.normalize()
    return n, ea


def _gold2d(pts2d, width, off=0.0030, thick=0.0004):
    """Ricamo dorato **appoggiato** sulla staffa.

    Il nastro e' una griglia, non due vertici: la staffa segue le pieghe della
    gonna, quindi una striscia piatta affonderebbe nelle creste e il simbolo si
    vedrebbe a chiazze. Ogni punto del tracciato viene campionato sulla
    superficie e sollevato lungo la normale locale.
    """
    dense = []
    for (x0, z0), (x1, z1) in zip(pts2d, pts2d[1:]):
        n = max(1, int(math.ceil(math.hypot(x1 - x0, z1 - z0) / 0.0025)))
        dense.extend((x0 + (x1 - x0) * i / n, z0 + (z1 - z0) * i / n)
                     for i in range(n))
    dense.append(pts2d[-1])

    verts, faces = [], []
    for x, z in dense:
        nrm, ea = _strap_frame(x, z)
        base = strap_point(x, z)
        half = width * 0.5
        for k in (-1.0, 1.0):
            p = base + ea * (half * k)
            verts.append(p + nrm * off)
    m = len(dense)
    for i in range(m - 1):
        a = i * 2
        faces.append((a, a + 1, a + 3, a + 2))
    ob = mesh_from_pydata("StrapGold", verts, faces, smooth=True)
    from common import add_solidify
    add_solidify(ob, thick, offset=1.0)
    return ob


def strap_gold():
    """Ricamo centrale della staffa, ricostruito dal disegno.

    Le posizioni sono espresse in frazione della lunghezza decorata, cosi' il
    motivo resta corretto anche quando la staffa si allunga. Dall'alto: asta
    sottile, rombo, cerchio con traversa e croce (il simbolo piu' grande del
    disegno), asta lunga con barretta, rombo, asta, fascia a pettine e doppio
    V della punta. Il filetto dorato corre anche sui due bordi.
    """
    objs = []

    def stroke(points, width=0.0022):
        objs.append(_gold2d(points, width))

    def diamond(cz, rx, rz, width=0.0024):
        stroke([(0, cz + rz), (rx, cz), (0, cz - rz),
                (-rx, cz), (0, cz + rz)], width)

    top = STRAP_TOP_Z
    tip = STRAP_TIP_Z

    def Z(f):
        """Frazione della lunghezza decorata -> quota."""
        return top + (tip - top) * f

    # --- parte alta, appena sotto l'anello
    stroke([(0.0, Z(0.085)), (0.0, Z(0.140))], 0.0019)
    diamond(Z(0.172), 0.0072, 0.0135)
    # --- cerchio con traversa e croce (simbolo centrale, piu' grande)
    stroke([(0.0, Z(0.200)), (0.0, Z(0.228))], 0.0018)
    r = 0.0218
    cz = Z(0.286)
    circle = [(r * math.cos(TAU * i / 64),
               cz + r * math.sin(TAU * i / 64)) for i in range(65)]
    stroke(circle, 0.0026)
    stroke([(-0.0150, cz - r * 0.98), (0.0150, cz - r * 0.98)], 0.0025)
    stroke([(0.0, cz - r), (0.0, Z(0.372))], 0.0023)
    stroke([(-0.0105, Z(0.338)), (0.0105, Z(0.338))], 0.0021)
    # --- asta lunga con barretta
    stroke([(0.0, Z(0.378)), (0.0, Z(0.512))], 0.0023)
    stroke([(-0.0100, Z(0.452)), (0.0100, Z(0.452))], 0.0019)
    diamond(Z(0.544), 0.0092, 0.0150)
    stroke([(0.0, Z(0.566)), (0.0, Z(0.660))], 0.0023)
    # --- fascia decorata sopra la punta: barrette verticali fra due righe
    halfw = strap_halfwidth(Z(0.690)) - 0.0068
    stroke([(-halfw, Z(0.690)), (halfw, Z(0.690))], 0.0021)
    for k in range(-4, 5):
        x = k * halfw / 4.4
        stroke([(x, Z(0.695)), (x, Z(0.744))], 0.0016)
    stroke([(-halfw, Z(0.748)), (halfw, Z(0.748))], 0.0021)
    # --- doppio V della punta, contenuto nel nastro
    hw_v = strap_halfwidth(Z(0.930)) - 0.0050
    stroke([(-hw_v, Z(0.800)), (0.0, Z(0.930)), (hw_v, Z(0.800))], 0.0026)
    stroke([(-hw_v * 0.74, Z(0.818)), (0.0, Z(0.922)),
            (hw_v * 0.74, Z(0.818))], 0.0020)
    # --- filetto dorato lungo i due bordi del nastro: nella reference e' un
    #     filo sottile, non un bordo dipinto
    for side in (-1, 1):
        edge = []
        z = Z(0.055)
        while z > Z(0.800):
            hw = strap_halfwidth(z)
            edge.append((side * (hw - 0.0046), z))
            z -= 0.010
        stroke(edge, 0.0013)
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
            count = max(1, int(math.ceil(max(abs(u1-u0), abs(v1-v0)) / 0.030)))
            uv.extend((u0+(u1-u0)*i/count, v0+(v1-v0)*i/count)
                      for i in range(count))
        uv.append(vertices[-1])
        normals = [pnl.nrm(u, v) for u, v in uv]
        # La griglia ha 3.2 mm di spessore sul lato esterno: stare sopra
        # l'estrusione, non sotto la superficie originale della griglia.
        pts = [pnl.pt(u, v) + n * 0.0026 for (u, v), n in zip(uv, normals)]
        objs.append(ribbon_n(name, pts, normals, width, thickness=0.0005))

    for pnl in drapes:
        name = pnl.name
        big = not name.endswith("2")
        # bordi continui lungo i due lati del lembo
        for u in (0.062, 0.938):
            path(pnl, name + "_border", [(u, 0.05), (u, 0.94)],
                 0.0021 if big else 0.0017)
        # bordo che segue l'orlo a punta
        path(pnl, name + "_hem", [(0.09, 0.912), (0.50, 0.950), (0.91, 0.912)],
             0.0019 if big else 0.0016)
        if not big:
            continue
        # gancio a spirale squadrata (il sigillo della reference)
        path(pnl, name + "_rune",
             [(0.38, 0.185), (0.38, 0.335), (0.63, 0.335),
              (0.63, 0.235), (0.485, 0.235)], 0.0024)
        # asta sotto il gancio
        path(pnl, name + "_stem", [(0.38, 0.185), (0.38, 0.135)], 0.0020)
        # rombo piu' in basso
        path(pnl, name + "_diamond",
             [(0.50, 0.545), (0.635, 0.625), (0.50, 0.705),
              (0.365, 0.625), (0.50, 0.545)], 0.0022)
        # due barrette ai lati del rombo
        for u in (0.30, 0.70):
            path(pnl, name + "_bar", [(u, 0.600), (u, 0.650)], 0.0016)
    return objs


# --------------------------------------------------------------------------
# assemblaggio
# --------------------------------------------------------------------------

PART_MATERIAL = {
    "fabric": "DRESS1_Linen",
    "dark": "DRESS1_Wool",
    "gold": "DRESS1_Gold",
    "gold_trim": "DRESS1_GoldTrim",
}


KEEP_GROUPS = ("dark", "gold", "gold_trim")


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
    drapes, drape_panels = build_drapes()
    strap_body, strap_gold_parts = build_strap()
    sash = build_sash()
    # I teli incrociati e la cintura sono stoffa, ma con bordi vivi e pochi
    # centimetri di larghezza: la decimazione della gonna li sfrangerebbe.
    # Vanno nel gruppo intermedio, decimato molto meno.
    # I teli in croce sono lino, la cintura e' lana: prima questi due gruppi
    # restavano senza materiale e nel render comparivano grigi (la cintura
    # scura spariva del tutto sotto la fascia).
    mid_cloth = [o for o in sash if o.name.startswith("Sash_Cross")]
    mid_belt = build_belt()
    assign_material(mid_cloth, "DRESS1_Linen")
    assign_material(mid_belt, "DRESS1_Wool")
    mid = mid_cloth + mid_belt

    groups = {
        "fabric": (build_lining() + build_underskirt() + build_skirt()
                   + build_lappets()
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
