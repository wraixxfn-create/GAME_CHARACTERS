"""DRESS1 — costruzione della geometria dal concept dell'utente.

Il capo e' ridisegnato sulle misure prese direttamente dalla reference
(``preview/concept.png``): **solo il vestito**, dalla vita all'orlo, senza
corpo, gambe o calzature.

Struttura del capo (dall'alto in basso), come nel disegno:

* fascia avorio **piatta**, non un rotolo: due teli larghi incrociati in
  diagonale che formano una **X** davanti all'anello d'ottone; il bordo alto
  scende al centro (dove il nodo stringe la stoffa) e sale sui fianchi.
* anello d'ottone piccolo e schiacciato, appoggiato sul nodo: il nastro
  scuro lo attraversa e prosegue nella staffa frontale.
* gonna di lino a **pieghe fitte e nette** (40 pieghe, cresta piatta e valle
  a spigolo, come il lino stirato del disegno), che si apre ad A dalla vita.
* due **teli sovrapposti lisci** (non pieghettati) con orli diritti e punte
  angolari: nel disegno le falde del davanti sono pannelli tesi, non balze.
* tre **lingue** strette al centro del davanti, le punte piu' basse del capo.
* due **pannelli scuri** sui fianchi, larghi, lisci, con filetto dorato lungo
  il bordo e piccoli segni geometrici in alto, come nella reference.
* staffa frontale scura con il motivo dorato completo: asta affusolata,
  rombo, cerchio attraversato dalla croce, secondo rombo, doppia V e punta
  piena dorata.

Misure lette sulla reference (px -> metri, capo alto 0,90 m = 282 px fra il
bordo alto della fascia e la punta piu' bassa, cioe' 3,19 mm per pixel;
``y`` contato dall'alto dell'immagine):

```
y =   6 px  bordo alto della fascia            z = 1,058
y =  24 px  centro dell'anello                 z = 0,998
y =  51 px  fondo della fascia                 z = 0,914
y =  55 px  attacco dei pannelli scuri         z = 0,901
y = 180 px  punta dei pannelli scuri           z = 0,503
y = 178..210 px  staffa: punta dorata          z = 0,503..0,401
y = 230..250 px  orlo della gonna pieghettata  z = 0,336..0,272
y = 273 px  punta delle lingue del davanti     z = 0,199
```

Quote di progetto (metri, Z in alto, davanti = -Y, origine a terra):

```
z = 1.058  bordo alto della fascia (sui fianchi)
z = 1.032  bordo alto della fascia al centro (il nodo lo tira in basso)
z = 0.998  anello d'ottone e incrocio dei teli
z = 0.932  fondo della fascia / attacco della gonna
z = 0.262  orlo medio della gonna pieghettata
z = 0.199  punta piu' bassa (lingue del davanti)
z = 0.000  suolo (origine, dove poggerebbero i piedi)
```

Gonna, teli e lingue condividono la superficie ``surface(a, z, layer)``: gli
strati sono offset radiali di pochi millimetri sulla stessa superficie. La
gonna porta le pieghe (``skirt_disp``), i teli lisci **non** le seguono: nel
disegno restano tesi e gettano un'ombra netta sulla pieghettatura sotto.
"""

from __future__ import annotations

import math
import os
import sys

import bpy  # noqa: E402
from mathutils import Vector, noise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (TAU, add_solidify, cloth_grid, ensure_dir, mesh_from_pydata,
                    reset_scene, smoothstep, work_dir)

# --------------------------------------------------------------------------
# quote e profilo (misurate sulla reference)
# --------------------------------------------------------------------------

WAIST_TOP_Z = 1.0470      # bordo alto della fascia sui fianchi (y = 6 px)
WAIST_DIP = 0.0300        # quanto il nodo tira in basso il bordo al centro
SASH_BOT_Z = 0.9200       # fondo della fascia, dove nasce la gonna (y = 50)
RING_Z = 0.9960           # centro dell'anello d'ottone (y = 24 px)
RING_MAJOR = 0.0293       # raggio medio: esterno 0,069 m (22 px nel disegno)
RING_MINOR = 0.0052       # sezione del tondino: foro 0,048 m
BELT_Z = 0.9295           # la cintura scura chiude il fondo della fascia
BELT_W = 0.0125           # larghezza della cintura scura
SASH_SLOPE = 0.0330       # pendenza delle cinghie incrociate: dz/dangolo
SASH_HALF = 0.0158        # mezza altezza delle cinghie incrociate (3,2 cm)

# Giro vita: la reference misura 82 px alla fascia, cioe' 0,26 m di larghezza.
WAIST_RX = 0.1420
WAIST_RY = 0.1160
SASH_TOP_SCALE = 0.955    # la fascia stringe in vita e si allarga sui fianchi

SKIRT_TOP_Z = 0.926

# (z, rx, ry) — profilo ad A misurato sulla silhouette della reference: la
# gonna e' **larga** (0,51 m all'orlo, 0,36 m sotto la fascia), la sezione e'
# ellittica come il bacino maschile e il davanti e' piu' piatto dei fianchi.
PROFILE = [
    (0.926, 0.1475, 0.1200),
    (0.880, 0.1625, 0.1315),
    (0.820, 0.1785, 0.1430),
    (0.760, 0.1925, 0.1530),
    (0.700, 0.2055, 0.1625),
    (0.640, 0.2175, 0.1712),
    (0.580, 0.2290, 0.1795),
    (0.520, 0.2395, 0.1872),
    (0.460, 0.2490, 0.1942),
    (0.400, 0.2575, 0.2005),
    (0.340, 0.2645, 0.2058),
    (0.280, 0.2695, 0.2098),
    (0.190, 0.2730, 0.2125),
]

# Offset di raggio per strato (m). I teli lisci stanno **sopra** le creste
# delle pieghe: cosi' nessuna piega trapassa i pannelli, che nel disegno sono
# tesi e gettano un'ombra netta sulla pieghettatura sotto.
LAYER = {
    "lining": -0.052,    # fodera interna
    "under": -0.016,     # sottogonna interno (chiude i vuoti fra le pieghe)
    "base": 0.000,       # gonna pieghettata
}

# Distacco dalla gonna dei lembi appesi (v = 0 in cima, 1 all'orlo del lembo).
# In cima sono attaccati alla vita, scendendo si staccano di pochi millimetri:
# e' quello che fa leggere la sovrapposizione come stoffa e non come piastre.
OFF_WRAP = [(0.00, 0.0030), (0.10, 0.0070), (0.45, 0.0100), (1.00, 0.0126)]
OFF_WRAP_C = [(0.00, 0.0026), (0.12, 0.0062), (0.50, 0.0086), (1.00, 0.0098)]

# Quanto i teli seguono le pieghe della gonna. Teli e pannelli usano lo
# **stesso** fattore: cosi' il termine delle pieghe si elide nel confronto e
# basta un margine costante perche' la lana copra sempre il lino.
FOLLOW_PANEL = 0.60
OFF_TONGUE = [(0.00, 0.0020), (0.12, 0.0060), (1.00, 0.0110)]
OFF_DRAPE = [(0.00, 0.0182), (0.12, 0.0186), (0.42, 0.0196), (1.00, 0.0216)]


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


def lerp_table(table, v):
    """Interpola una tabella [(v, valore), ...] in modo **lineare**.

    Lineare e non smorzato: gli orli dei teli nel disegno sono segmenti
    dritti che si incontrano in punte nette; uno smorzamento arrotonderebbe
    proprio gli angoli che rendono riconoscibile il capo.
    """
    if v <= table[0][0]:
        return table[0][1]
    if v >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        v0, a0 = table[i]
        v1, a1 = table[i + 1]
        if v0 <= v <= v1:
            t = (v - v0) / (v1 - v0) if v1 > v0 else 0.0
            return a0 + (a1 - a0) * t
    return table[-1][1]


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


# --------------------------------------------------------------------------
# orlo e pieghe della gonna
# --------------------------------------------------------------------------

def hem_z(a):
    """Quota dell'orlo della gonna pieghettata.

    Nel disegno l'orlo e' quasi orizzontale, con un'onda larga e appena
    percettibile: le punte lunghe vengono dalle lingue e dai teli, non dalla
    gonna.
    """
    return (0.2380
            + 0.0040 * math.cos(2.0 * a + 0.9)
            + 0.0024 * math.sin(3.0 * a + 0.6)
            + 0.0030 * (0.5 + 0.5 * math.cos(PLEAT_N * a * 0.5 + 0.4)) ** 2.0)


PLEAT_N = 46            # pieghe lungo tutto il giro (passo ~3 cm all'orlo)
PLEAT_DEPTH = 0.0115    # profondita' cresta-valle all'orlo (m)


def drape_fold(x):
    """Profilo di una piega di lino.

    Nel disegno le pieghe sono **larghe e morbide**: una faccia quasi piatta
    in luce, una valle arrotondata in ombra, senza spigoli. La cresta occupa
    il 44% del passo; verso la valle il profilo scende con una curva che si
    appiattisce, cosi' la stoffa legge come lino e non come lamiera ondulata.

    ``x`` va da 0 (valle) a 1 (valle successiva); la cresta sta a 0.5.
    """
    t = abs(2.0 * x - 1.0)          # 0 sulla cresta, 1 nella valle
    if t <= 0.44:
        return 1.0
    u = (t - 0.44) / 0.56
    return (1.0 - u * u * (3.0 - 2.0 * u))


# media del profilo su un periodo: centra la piega fra cresta e valle
FOLD_MEAN = sum(drape_fold(i / 512.0) for i in range(512)) / 512.0


def pleats(a, v, seed=0.0, n=PLEAT_N, amp=1.0, hem_fade=0.0):
    """Spostamento radiale delle pieghe (cresta +, valle -).

    ``amp`` e' la profondita' cresta-valle in metri; il valore restituito e'
    in unita' di ``amp``. Le pieghe non sono tutte uguali: due armoniche lente
    spostano le valli, quindi alcune campate sono piu' larghe e altre piu'
    strette, come nel disegno. Le valli restano allineate lungo la caduta,
    quindi le linee d'ombra corrono continue dalla vita all'orlo.
    """
    n = max(2, int(n))
    warp = (1.05 * math.sin(2.0 * a + 0.7 + seed * 0.2)
            + 0.52 * math.sin(3.0 * a - 1.3)
            + 0.26 * math.sin(5.0 * a + 2.2 + seed * 0.1)
            + 0.14 * math.sin(8.0 * a + 0.4))
    # la piega si torce appena scendendo: senza questa deriva sembra lamiera
    phase = n * a + warp + seed * 1.7 + 0.45 * math.sin(v * 2.2 + seed)
    x = (phase / TAU) % 1.0
    fold = drape_fold(x) - FOLD_MEAN
    depth = (1.0 + 0.22 * math.cos(3.0 * a + seed * 0.7)
             + 0.10 * math.cos(7.0 * a - 0.4 + seed)
             + 0.06 * math.cos(11.0 * a + 1.6 + seed * 0.3))
    depth = max(0.45, depth)
    # sotto la fascia la stoffa e' tirata: le pieghe nascono dolci e si
    # aprono solo nel secondo quarto della caduta, come nel disegno
    envelope = smoothstep(0.0, 0.19, v)
    if hem_fade:
        envelope *= 1.0 - hem_fade * smoothstep(0.94, 1.0, v)
    return amp * fold * depth * envelope


def skirt_disp(a, z):
    """Spostamento radiale della gonna, condiviso da tutti gli strati."""
    span = SKIRT_TOP_Z - hem_z(a)
    v = min(1.0, max(0.0, (SKIRT_TOP_Z - z) / max(span, 1e-6)))
    # la fascia tira il lino al centro davanti: li' le pieghe sono piu' basse
    soft = 0.62 + 0.38 * (1.0 - math.exp(-(a / 0.55) ** 2))
    return pleats(a, v, 0.0, n=PLEAT_N, amp=PLEAT_DEPTH * soft, hem_fade=0.45)


# --------------------------------------------------------------------------
# primitive
# --------------------------------------------------------------------------

def mesh_obj(name, verts, faces, smooth=True, thickness=0.0, offset=0.0):
    ob = mesh_from_pydata(name, verts, faces, smooth=smooth)
    if thickness:
        add_solidify(ob, thickness, offset=offset)
    return ob


def ribbon_n(name, pts, normals, width, thickness=0.0016, widths=None):
    """Nastro appoggiato su una superficie: la larghezza sta nel piano tangente."""
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


def torus(name, center, axis, major, minor, seg_major=64, seg_minor=14,
          squash=1.0, flat=1.0, profile=None, section_pow=1.0):
    """Anello: ``flat`` schiaccia la sezione lungo l'asse (anello piatto).

    ``profile(angle)`` -> (larghezza, spessore) permette di cambiare sezione
    lungo il giro: l'anello della reference e' un tondino con il bordo
    esterno piu' pieno e il canale interno piu' sottile.
    """
    axis = Vector(axis).normalized()
    ref = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
    u = axis.cross(ref).normalized()
    v = axis.cross(u).normalized()
    c = Vector(center)
    verts, faces = [], []
    for i in range(seg_major):
        a = TAU * i / seg_major
        d = u * math.cos(a) + v * math.sin(a) * squash
        mw, mf = profile(a) if profile else (1.0, 1.0)
        for k in range(seg_minor):
            b = TAU * k / seg_minor
            cb = math.copysign(abs(math.cos(b)) ** section_pow, math.cos(b))
            sb = math.copysign(abs(math.sin(b)) ** section_pow, math.sin(b))
            verts.append(c + d * (major + minor * mw * cb)
                         + axis * (minor * flat * mf * sb))
    for i in range(seg_major):
        for k in range(seg_minor):
            a = i * seg_minor + k
            b = ((i + 1) % seg_major) * seg_minor + k
            cc = ((i + 1) % seg_major) * seg_minor + (k + 1) % seg_minor
            d = i * seg_minor + (k + 1) % seg_minor
            faces.append((a, b, cc, d))
    return mesh_obj(name, verts, faces)


def ellipsoid(name, center, radii, segs=16, rings=10, rot=None):
    cx, cy, cz = center
    rx, ry, rz = radii
    verts, faces = [], []
    for j in range(rings + 1):
        phi = math.pi * j / rings
        sp, cp = math.sin(phi), math.cos(phi)
        for i in range(segs):
            th = TAU * i / segs
            p = Vector((rx * sp * math.cos(th), ry * sp * math.sin(th),
                        rz * cp))
            if rot is not None:
                p = rot @ p
            verts.append(Vector((cx, cy, cz)) + p)
    for j in range(rings):
        for i in range(segs):
            a = j * segs + i
            b = j * segs + (i + 1) % segs
            c = (j + 1) * segs + (i + 1) % segs
            d = (j + 1) * segs + i
            faces.append((a, b, c, d))
    return mesh_obj(name, verts, faces)


# --------------------------------------------------------------------------
# lembi lisci: teli sovrapposti, lingue, pannelli scuri
# --------------------------------------------------------------------------

class Piece:
    """Lembo di stoffa parametrico appeso alla gonna.

    ``(u, v)`` copre il lembo (larghezza, caduta). Il bordo inferiore e' una
    **spezzata** ``hem = [(u, z), ...]``: gli angoli restano netti, ed e'
    quello che distingue i pannelli del disegno dalle balze arrotondate.

    ``offsets`` e' il distacco dalla gonna lungo la caduta: in cima il lembo
    e' attaccato (pochi millimetri sopra le pieghe), scendendo si stacca e la
    sua ombra si legge sulla pieghettatura sotto. ``climb`` aggiunge un
    allontanamento quadratico: e' il telo che si apre verso l'orlo.

    ``follow`` e' quanto il lembo segue le pieghe della gonna: i teli lisci
    non le seguono (0), le lingue si' (0,85).
    """

    def __init__(self, name, a0, a1, hem, offsets, follow=0.0, climb=0.0,
                 folds=(), pleat_amp=0.0, pleat_n=PLEAT_N, seed=0.0,
                 top_z=None, drop_pow=1.0, edge_roll=0.0, edge_w=0.14,
                 tuck=0.0, wave=0.0, follow_fade=None):
        self.name = name
        self.a0 = a0
        self.a1 = a1
        self.hem = hem
        self.offsets = offsets
        self.follow = follow
        self.climb = climb
        self.folds = folds
        self.pleat_amp = pleat_amp
        self.pleat_n = pleat_n
        self.seed = seed
        self.top_z = SKIRT_TOP_Z + 0.0006 if top_z is None else top_z
        self.drop_pow = drop_pow
        self.edge_roll = edge_roll
        self.edge_w = edge_w
        self.tuck = tuck
        self.wave = wave
        # (v0, v1): sotto v0 il lembo segue le pieghe della gonna, sopra v1
        # se ne stacca. Serve ai pannelli scuri: l'attacco deve appoggiarsi
        # sulla pieghettatura, altrimenti le creste lo tagliano a denti.
        self.follow_fade = follow_fade

    def follow_at(self, v):
        if not self.follow_fade:
            return self.follow
        v0, v1 = self.follow_fade
        return self.follow * (1.0 - smoothstep(v0, v1, v))

    def params(self, u, v):
        a = self.a0 + (self.a1 - self.a0) * u
        zh = lerp_table(self.hem, u)
        z = self.top_z + (zh - self.top_z) * v ** self.drop_pow
        return a, z

    def pt(self, u, v):
        a, z = self.params(u, v)
        d = lerp_table(self.offsets, v)
        d += skirt_disp(a, z) * self.follow_at(v)
        d += self.climb * v * v
        if self.pleat_amp:
            d += self.pleat_amp * pleats(a, v, self.seed, n=self.pleat_n,
                                         amp=1.0)
        for amp, k, phase, v0, v1 in self.folds:
            d += amp * math.sin(k * a + phase + 0.7 * v) * smoothstep(v0, v1, v)
        edge = min(u, 1.0 - u)
        if self.edge_roll:
            # il bordo vivo si arrotola verso l'interno invece di sporgere
            d -= self.edge_roll * smoothstep(self.edge_w, 0.0, edge)
        if self.tuck:
            d *= smoothstep(0.0, self.tuck, v) ** 0.65
        if self.wave:
            d += self.wave * math.sin(9.0 * u + self.seed) * smoothstep(0.9, 1.0, v)
        p = surface(a, z, "base", extra=d)
        p += normal_dir(a) * (wrinkle(p, 0.00032, 11.0, self.seed)
                              * (1.0 - smoothstep(0.0, self.edge_w * 1.6, edge)))
        return p

    def nrm(self, u, v):
        du, dv = 1e-3, 1e-3
        pu = self.pt(min(u + du, 1.0), v) - self.pt(max(u - du, 0.0), v)
        pv = self.pt(u, min(v + dv, 1.0)) - self.pt(u, max(v - dv, 0.0))
        n = pu.cross(pv)
        a, _ = self.params(u, v)
        if n.length < 1e-9:
            return normal_dir(a)
        n.normalize()
        return -n if n.dot(normal_dir(a)) < 0 else n

    def build(self, nu=110, nv=28, thickness=0.0016):
        return cloth_grid(self.name, nu, nv, lambda u, v: self.pt(u, v),
                          thickness=thickness)


# --------------------------------------------------------------------------
# gonna, sottogonna, fodera
# --------------------------------------------------------------------------

def build_lining():
    """Fodera interna di lino, aperta in alto e in basso.

    Il vestito non ha gambe dentro: la fodera chiude il guscio sotto la vita
    e si ferma **sopra** l'orlo, cosi' dal basso si vede stoffa chiara invece
    del vuoto. Resta 3 cm dentro la gonna e non stringe il passaggio per le
    gambe del personaggio.
    """
    nu, nv = 64, 10

    def surf(u, v):
        a = TAU * u
        z = 0.845 - 0.560 * v ** 1.02
        shrink = 1.0 - 0.045 * smoothstep(0.0, 1.0, v)
        # la fodera segue il profilo della gonna restando 2 cm dentro: se si
        # stringesse troppo, dal basso si vedrebbe il vuoto del guscio
        rx = (prof(z)[0] - 0.030) * shrink
        ry = (prof(z)[1] - 0.026) * shrink
        p = Vector((rx * math.sin(a), -ry * math.cos(a), z))
        p += normal_dir(a) * (0.0012 * math.cos(a * 17.0 + v * 2.0) * (1 - v))
        return p

    return [cloth_grid("Lining", nu, nv, surf, thickness=0.0)]


def build_underskirt():
    """Sottogonna interno: chiude i vuoti fra le pieghe e il fondo.

    E' pieghettato meno della gonna e sta 1,4 cm dentro: si intravede appena
    nelle valli d'ombra, come il secondo strato del disegno, e non sporge
    mai sotto l'orlo.
    """
    nu, nv = 76, 12
    z_bot = 0.232

    def surf(u, v):
        a = TAU * u
        z = SKIRT_TOP_Z - 0.010 + (z_bot - SKIRT_TOP_Z + 0.010) * v ** 1.04
        f = pleats(a, v, 0.4, n=18, amp=0.0042, hem_fade=0.5)
        p = surface(a, z, "under", extra=f)
        p += normal_dir(a) * wrinkle(p, 0.0005, 11.0, 1.3)
        return p

    return [cloth_grid("UnderSkirt", nu, nv, surf, thickness=0.0)]


def build_skirt():
    """Gonna principale: lino pieghettato fitto, orlo quasi dritto.

    La griglia e' gia' alla densita' del LOD0 (dodici colonne per piega):
    cosi' la cresta resta una faccia piatta e la valle una linea d'ombra
    netta anche dopo la decimazione.
    """
    nu, nv = PLEAT_N * 12, 44

    def surf(u, v):
        a = TAU * u
        z = SKIRT_TOP_Z + (hem_z(a) - SKIRT_TOP_Z) * v ** 1.04
        # L'attacco rientra di 5 mm sotto la fascia: l'orlo della fascia non
        # deve tagliare le creste delle pieghe in una fila di dentini.
        tuck = -0.0050 * (1.0 - smoothstep(0.0, 0.10, v))
        p = surface(a, z, "base", extra=skirt_disp(a, z) + tuck)
        p += normal_dir(a) * wrinkle(p, 0.00016, 16.0, 3.1)
        return p

    return [cloth_grid("Skirt", nu, nv, surf, thickness=0.0)]


# --------------------------------------------------------------------------
# teli sovrapposti lisci
# --------------------------------------------------------------------------

R = math.radians

# Ogni telo e' un pannello che gira dal fianco al davanti. L'orlo e' una
# spezzata con **punte nette**: nel disegno le falde sono teli tesi con
# angoli vivi, non balze. Il telo destro copre quello sinistro al centro.
WRAPS = [
    # I teli del davanti, dal piu' interno al piu' esterno. Nel disegno la
    # gonna e' coperta da pannelli sovrapposti con **orli a punta**: le punte
    # scendono verso il centro davanti, gli orli si incrociano sotto la staffa
    # e le pieghe del lino continuano da uno strato all'altro. Il pannello
    # corto in cima e' quello che dà il taglio diagonale alla vita.
    dict(name="Wrap_L", a0=R(-128), a1=R(-6), climb=0.0022, seed=1.7,
         hem=[(0.00, 0.4380), (0.10, 0.3820), (0.26, 0.4700),
              (0.52, 0.5100), (0.74, 0.4780), (0.86, 0.4260),
              (0.94, 0.4660), (1.00, 0.4980)],
         folds=[(0.0030, 2.0, 0.4, 0.02, 0.85)]),
    dict(name="Wrap_R", a0=R(6), a1=R(128), climb=0.0020, seed=4.3,
         hem=[(0.00, 0.4980), (0.10, 0.4740), (0.20, 0.4240),
              (0.30, 0.4520), (0.48, 0.4820), (0.66, 0.5040),
              (0.82, 0.4740), (0.92, 0.3880), (1.00, 0.4320)],
         folds=[(0.0028, 2.0, 2.6, 0.02, 0.85)]),
    dict(name="Wrap_C", a0=R(-62), a1=R(62), climb=0.0014, seed=7.9,
         hem=[(0.00, 0.6760), (0.16, 0.6480), (0.34, 0.6120),
              (0.50, 0.5920), (0.66, 0.6120), (0.84, 0.6480),
              (1.00, 0.6760)],
         folds=[(0.0016, 3.0, 1.1, 0.02, 0.8)]),
]


def layer_hem(a, spec):
    """Quota dell'orlo del telo ``spec`` a quell'angolo."""
    t = (a - spec["a0"]) / (spec["a1"] - spec["a0"])
    t = min(1.0, max(0.0, t))
    return lerp_table(spec["hem"], t)


def build_overlays():
    """I due teli sovrapposti del davanti (lisci, con punte angolari)."""
    objs = []
    for spec in WRAPS:
        offs = OFF_WRAP_C if spec["name"] == "Wrap_C" else OFF_WRAP
        pnl = Piece(spec["name"], spec["a0"], spec["a1"], spec["hem"],
                    offs, follow=FOLLOW_PANEL, climb=spec["climb"],
                    folds=spec["folds"], seed=spec["seed"],
                    edge_roll=0.0022, edge_w=0.04, tuck=0.06)
        objs.append(pnl.build(nu=150, nv=30, thickness=0.0014))
    return objs


# --------------------------------------------------------------------------
# lingue del davanti
# --------------------------------------------------------------------------

FALLS = [
    # nome, centro (rad), semilarghezza (rad), fondo, punta, strato, seed
    # Sotto la staffa il disegno mostra tre lingue di lino **larghe e corte**:
    # la centrale scende piu' in basso, le due accanto si fermano prima. Sono
    # le punte piu' basse del capo e si vedono fra i teli sovrapposti.
    ("Fall_C", R(0.0), R(9.6), 0.1930, 0.0550, "tongue", 1.1),
    ("Fall_L1", R(-15.0), R(6.0), 0.2160, 0.0460, "tongue", 2.3),
    ("Fall_R1", R(16.0), R(5.6), 0.2220, 0.0430, "tongue", 4.6),
]


def build_falls():
    """Le lingue del davanti, le punte piu' basse del capo."""
    objs = []
    for name, center, hw, zbot, tip, _layer, seed in FALLS:
        pnl = Piece(name, center - hw, center + hw,
                    [(0.0, zbot + 0.006), (0.62, zbot - tip),
                     (1.0, zbot + 0.012)],
                    OFF_TONGUE, follow=0.85, climb=0.003,
                    pleat_amp=0.0032, pleat_n=7, seed=seed,
                    folds=[(0.0012, 5.0, seed, 0.1, 0.9)],
                    edge_roll=0.0012, edge_w=0.16, tuck=0.10, wave=0.0008)
        objs.append(pnl.build(nu=40, nv=30, thickness=0.0012))
    return objs


# --------------------------------------------------------------------------
# pannelli scuri sui fianchi
# --------------------------------------------------------------------------

def drape_specs():
    """Pannelli scuri sui fianchi: uno per lato, larghi e lisci.

    Nel disegno il telo scuro non e' una lista di nastri: e' un pannello di
    lana che copre il fianco dalla fascia fino a meta' coscia, con l'orlo a
    punta verso il davanti e il filetto dorato lungo il bordo. E' **stretto**:
    resta sul fianco, dove la curvatura lo mostra quasi di taglio, e non
    invade il davanti.
    """
    return [
        ("Drape_L", R(-96), R(-44),
         [(0.00, 0.6540), (0.18, 0.5860), (0.44, 0.5280), (0.62, 0.4740),
          (0.76, 0.5320), (0.90, 0.6020), (1.00, 0.6620)], 1.2),
        ("Drape_R", R(44), R(96),
         [(0.00, 0.6620), (0.10, 0.6020), (0.24, 0.5320), (0.38, 0.4740),
          (0.56, 0.5280), (0.82, 0.5860), (1.00, 0.6540)], 3.4),
    ]


def build_drapes():
    """I due pannelli scuri, tesi sopra il lino.

    Stanno sopra le creste delle pieghe (``follow=0`` piu' un margine): le
    creste del lino non devono trapassare la lana a schegge. In cima il
    pannello rientra sotto la fascia, in basso si stacca di pochi millimetri.
    """
    objs = []
    panels = []
    for name, a0, a1, ztab, seed in drape_specs():
        pnl = Piece(name, a0, a1, ztab, OFF_DRAPE,
                    follow=FOLLOW_PANEL, climb=0.0004,
                    folds=[(0.0018, 1.6, seed, 0.05, 0.9),
                           (0.0008, 4.0, seed * 2.1, 0.2, 1.0)],
                    seed=seed, edge_roll=0.0075, edge_w=0.13,
                    top_z=BELT_Z - 0.0060)
        objs.append(pnl.build(nu=76, nv=34, thickness=0.0016))
        panels.append(pnl)
    return objs, panels


def _panel_path(pnl, verts, width=0.0016, lift=0.0026, sub=0.02, name="gold"):
    """Ricamo dorato proiettato sul lembo, appena sopra la sua superficie."""
    uv = []
    for (u0, v0), (u1, v1) in zip(verts, verts[1:]):
        count = max(1, int(math.ceil(max(abs(u1 - u0), abs(v1 - v0)) / sub)))
        uv.extend((u0 + (u1 - u0) * i / count, v0 + (v1 - v0) * i / count)
                  for i in range(count))
    uv.append(verts[-1])
    normals = [pnl.nrm(u, v) for u, v in uv]
    pts = [pnl.pt(u, v) + n * lift for (u, v), n in zip(uv, normals)]
    return ribbon_n(f"{pnl.name}_{name}", pts, normals, width, thickness=0.0004)


def _panel_uv(pnl, a, z):
    """(u, v) del punto (angolo, quota) sul lembo ``pnl``."""
    u = (a - pnl.a0) / (pnl.a1 - pnl.a0)
    u = min(1.0, max(0.0, u))
    zh = lerp_table(pnl.hem, u)
    span = zh - pnl.top_z
    v = 0.0 if abs(span) < 1e-6 else (z - pnl.top_z) / span
    return u, min(1.0, max(0.0, v))


def _panel_mark(pnl, path, width=0.0015, lift=0.0026, name="mark", sub=0.012):
    """Ricamo dorato tracciato in **coordinate del capo** (angolo, quota).

    Disegnare i segni nello spazio (angolo, z) invece che nello spazio UV del
    lembo li tiene dritti e leggibili: le UV di un pannello inclinato
    stirano qualunque zig-zag fino a farlo sembrare uno scarabocchio.
    """
    uv = []
    for (a0, z0), (a1, z1) in zip(path, path[1:]):
        count = max(1, int(math.ceil(math.hypot(a1 - a0, (z1 - z0) /
                                                 max(_panel_scale(pnl), 1e-6))
                                     / max(sub, 1e-6))))
        for i in range(count):
            u, v = _panel_uv(pnl, a0 + (a1 - a0) * i / count,
                             z0 + (z1 - z0) * i / count)
            uv.append((u, v))
    u, v = _panel_uv(pnl, path[-1][0], path[-1][1])
    uv.append((u, v))
    normals = [pnl.nrm(u, v) for u, v in uv]
    pts = [pnl.pt(u, v) + n * lift for (u, v), n in zip(uv, normals)]
    return ribbon_n(f"{pnl.name}_{name}", pts, normals, width, thickness=0.0004)


def _panel_scale(pnl):
    """Raggio medio del capo: converte i millimetri in angoli."""
    return max((radius(pnl.top_z, "base")[0] + radius(0.5, "base")[0]) * 0.5,
               1e-3)


def build_drape_welt(panels):
    """Bordo in rilievo (lucido) lungo il perimetro dei pannelli scuri.

    La lana del pannello e' tesa sopra le pieghe, quindi ai bordi incontra le
    creste del lino. Il bordo in rilievo e' il **profilo arrotondato** che
    copre quell'incontro: e' quello che nel disegno legge come cucitura
    rilevata, e toglie di mezzo i dentini bianchi del lino sotto la lana.
    """
    objs = []
    for pnl in panels:
        for u in (0.028, 0.972):
            pts, normals = [], []
            for i in range(0, 41):
                v = i / 40.0
                pts.append(pnl.pt(u, v))
                normals.append(pnl.nrm(u, v))
            objs.append(ribbon_n(f"{pnl.name}_welt{u:.2f}", pts, normals,
                                 0.0062, thickness=0.0016))
        # bordo inferiore: segue l'orlo a punta
        pts, normals = [], []
        for i in range(0, 61):
            u = i / 60.0
            p = pnl.pt(u, 0.975)
            pts.append(p)
            normals.append(pnl.nrm(u, 0.975))
        objs.append(ribbon_n(f"{pnl.name}_weltHem", pts, normals, 0.0060,
                             thickness=0.0016))
    return objs


def build_drape_runes(drapes):
    """Filetti e segni dorati dei pannelli scuri.

    Dalla reference: un filetto continuo che segue il bordo esterno, un
    secondo filetto piu' corto all'interno e, in alto, pochi segni
    geometrici (due V, un rombo, una barretta) che scendono lungo la
    striscia. Pochi e spessi: riempire il pannello di linee lo fa sembrare un
    circuito stampato.
    """
    objs = []
    for pnl in drapes:
        for u, tag in ((0.13, "borderOut"), (0.34, "borderIn")):
            objs.append(_panel_path(pnl, [(u, 0.06), (u, 0.90 if u < 0.2 else 0.72)],
                                    0.0016 if u < 0.2 else 0.0012, name=tag))
        # Nel disegno i segni del pannello sono **pochi e corti**: due
        # trattini angolari in alto, un rombo al centro e una barretta. Si
        # tracciano in (angolo, quota) perche' restino leggibili anche
        # quando il pannello si vede di taglio.
        a0, a1 = pnl.a0, pnl.a1
        sgn = 1.0 if a1 > 0 else -1.0
        ae = a0 if sgn > 0 else a1          # bordo esterno, verso il fianco
        step = abs(a1 - a0)

        def A(f):
            return ae + sgn * step * f

        # due trattini paralleli che seguono l'inclinazione del pannello
        for i, uu in enumerate((0.30, 0.42)):
            objs.append(_panel_mark(pnl, [(A(uu), 0.880), (A(uu + 0.06), 0.816)],
                                    0.0016, name=f"rune{i}"))
        # rombo piccolo al centro
        objs.append(_panel_mark(pnl, [(A(0.40), 0.760), (A(0.47), 0.734),
                                      (A(0.40), 0.708), (A(0.33), 0.734),
                                      (A(0.40), 0.760)], 0.0014, name="rune2"))
        # barretta di chiusura verso la punta
        objs.append(_panel_mark(pnl, [(A(0.34), 0.668), (A(0.50), 0.668)],
                                0.0012, name="rune3"))
    return objs


# --------------------------------------------------------------------------
# fascia, teli incrociati, nodo, anello
# --------------------------------------------------------------------------

def sash_top(a):
    """Bordo alto della fascia: onda larga che il nodo tira al centro.

    Nella reference i due teli avvolti lasciano un bordo alto **mosso**: sale
    sui fianchi, scende davanti (dove il nodo stringe il tessuto) e si
    abbassa appena anche sul dietro.
    """
    knot = -WAIST_DIP * math.exp(-(math.atan2(math.sin(a), math.cos(a)) / 0.62) ** 2)
    waves = (0.0055 * math.cos(2.0 * a + 0.35)
             + 0.0022 * math.sin(3.0 * a - 0.9)
             + 0.0012 * math.cos(5.0 * a + 1.7))
    return WAIST_TOP_Z + knot + waves


def sash_scale(a, z):
    """Larghezza della fascia a quella quota (tronco di cono, non cilindro)."""
    top = sash_top(a)
    t = min(1.0, max(0.0, (top - z) / max(top - SASH_BOT_Z, 1e-6)))
    return SASH_TOP_SCALE + (1.0 - SASH_TOP_SCALE) * math.sqrt(t)


def sash_thickness(a, z):
    """Rilievo della stoffa avvolta: grinze morbide e pizzicatura sul nodo.

    Niente rotoli: nella reference la fascia e' **liscia**, sono i due teli
    incrociati a dare il rilievo. Qui restano le grinze della stoffa tirata
    dal nodo e un leggero rigonfiamento sul fondo, dove il telo gira.
    """
    top = sash_top(a)
    t = min(1.0, max(0.0, (top - z) / max(top - SASH_BOT_Z, 1e-6)))
    env = smoothstep(0.04, 0.26, t) * (1.0 - smoothstep(0.84, 1.0, t))
    crease = (0.0012 * math.cos(3.0 * a + 9.0 * z + 0.4)
              + 0.0007 * math.cos(7.0 * a - 4.0 * z - 1.1)) * env
    pinch = -0.0040 * math.exp(-(math.atan2(math.sin(a), math.cos(a)) / 0.50) ** 2) \
        * math.sin(math.pi * t) ** 0.8
    bottom = 0.0018 * smoothstep(0.88, 1.0, t)
    return crease + pinch + bottom


def sash_pt(a, z, extra=0.0):
    d = sash_thickness(a, z) + extra
    k = sash_scale(a, z)
    return Vector(((WAIST_RX * k + d) * math.sin(a),
                   -(WAIST_RY * k + d) * math.cos(a), z))


def _signed(a, center=0.0):
    return math.atan2(math.sin(a - center), math.cos(a - center))


def cross_band_line(a, sgn):
    """Quota della cinghia incrociata ``sgn`` all'angolo ``a``.

    Le due cinghie scure partono dai pannelli dei fianchi, salgono e si
    incrociano davanti all'anello. Nella reference la X in vita non e' fatta
    dei teli avorio ma di **due cinghie di lana scura**: sono loro a legare i
    pannelli laterali alla fibbia, e sono quello che si legge da lontano.
    """
    s = _signed(a, 0.0)
    z = RING_Z + sgn * SASH_SLOPE * math.sin(s)
    # Al bordo del pannello scuro la cinghia **entra dentro la fascia** e
    # sparisce sotto la lana: e' la fine naturale del suo percorso.
    # La cinghia scende fino alla cintura sottile e **ci si fonde dentro**:
    # le punte non finiscono mai in aria, si perdono nella stessa lana scura.
    t = smoothstep(0.74, 1.20, abs(s))
    return z + (BELT_Z + 0.0028 - z) * t


def sash_band(name, sgn, off, seed, nu=170, nv=10, a0=-1.31, a1=1.31,
              under=False):
    """Cinghia scura incrociata, avvolta sulla fascia.

    La sezione e' un nastro piatto: quello che conta e' il **bordo** con la
    sua ombra, perche' e' l'orlo della cinghia a disegnare la X.
    """
    def surf(u, v):
        a = a0 + (a1 - a0) * u
        zc = cross_band_line(a, sgn) + 0.0030 * math.sin(2.0 * a + seed)
        env = smoothstep(0.0, 0.14, u) * smoothstep(0.0, 0.14, 1.0 - u)
        # La cinghia resta larga fino in fondo: ai fianchi la sua estremita'
        # finisce **sotto il pannello di lana**, che la copre. Nessuna punta
        # rastremata, quindi nessun effetto "fiocco".
        tail = smoothstep(0.74, 1.20, abs(_signed(a, 0.0)))
        half = SASH_HALF * (0.86 + 0.14 * env) * (1.0 - 0.55 * tail)
        t = v - 0.5
        z = zc + t * 2.0 * half
        # la cinghia non scavalca mai il bordo alto della fascia
        z = min(z, sash_top(a) - 0.0032)
        r = abs(2.0 * t)
        b = max(0.0, 1.0 - r ** 10) ** 0.34
        crease = (0.0005 * math.cos(a * 7.0 + t * 2.0 + seed)) * b
        lift = off * b + crease
        if under:
            # la cinghia che passa **sotto** si appoggia alla fascia nel punto
            # d'incrocio: senza questo rientro fra le due cinghie resta una
            # fessura a lente da cui si vede il lino
            lift -= 0.0090 * b * math.exp(-(a / 0.34) ** 2)
        # Alle estremita' la cinghia si assottiglia e affonda quel tanto che
        # basta a entrare nella cintura: la punta sparisce dentro la lana.
        sink = -0.013 * tail
        return sash_pt(a, z, lift + sink)

    return cloth_grid(name, nu, nv, surf, thickness=0.0022)


def build_sash():
    """Fascia avorio piatta, cinghie scure incrociate e fibbia.

    Nella reference la vita non e' un rotolo di stoffa: e' un telo **teso**,
    legato da due cinghie di lana scura che si incrociano davanti all'anello.
    """
    objs = []
    nu = 180

    def body(u, v):
        a = TAU * u
        top = sash_top(a)
        z = top + (SASH_BOT_Z - top) * v ** 0.985
        # bordo superiore arrotondato: la stoffa gira su se stessa invece di
        # chiudersi con un taglio vivo come un secchio
        roll_top = -0.0052 * (1.0 - smoothstep(0.0, 0.075, v)) ** 1.6
        diag = (0.0009 * math.cos(5.0 * a + 1.2)
                + 0.0005 * math.cos(9.0 * a - 0.6)) \
            * smoothstep(0.10, 0.34, v) * (1.0 - smoothstep(0.80, 1.0, v))
        roll_bot = 0.0022 * smoothstep(0.90, 1.0, v)
        # Il lino si increspa a raggiera attorno alla fibbia: sono le pieghe
        # della stoffa tirata dal nodo, non un pezzo appoggiato sopra.
        r = math.hypot(a / 0.46, (RING_Z - z) / 0.085)
        gather = (0.0018 * math.cos(11.0 * math.atan2(a, RING_Z - z))
                  * math.exp(-r * r) * smoothstep(0.0, 0.12, v))
        return sash_pt(a, z, roll_top + diag + roll_bot + gather)

    objs.append(cloth_grid("Sash_Body", nu, 52, body, thickness=0.0))

    def liner(u, v):
        a = TAU * u
        top = sash_top(a)
        return sash_pt(a, top - 0.008 - 0.078 * v, -0.018 - 0.030 * v)

    objs.append(cloth_grid("Sash_Liner", nu, 7, liner, thickness=0.0))

    # le due cinghie scure incrociate: quella che sale passa sopra l'altra
    objs.append(sash_band("Sash_CrossA", -1.0, 0.0042, 0.9, under=True))
    objs.append(sash_band("Sash_CrossB", 1.0, 0.0078, 3.7))


    # Il foro dell'anello e' scuro: un fascio di lana appena dietro il tondino,
    # cosi' la fibbia legge vuota e in ombra come nel disegno.
    # Il disco scuro riempie **tutto** il foro del tondino: se resta piu'
    # piccolo si vede un anello di stoffa chiara dentro la fibbia.
    objs.append(ellipsoid("Sash_KnotDark",
                          (0.0, RING_C.y + 0.0032, RING_Z),
                          (0.0242, 0.0024, 0.0242), segs=48, rings=12))
    return objs


# L'anello appoggia **sopra** il nodo dei teli incrociati, non dietro: nel
# disegno la fibbia e' l'elemento piu' avanzato del capo. Il distacco tiene
# conto anche del rigonfiamento del nodo (7-10 mm), altrimenti il tondino
# affonda nella stoffa e si vede solo a mezzaluna.
RING_C = Vector((0.0, sash_pt(0.0, RING_Z).y - 0.0205, RING_Z))
RING_FRONT_Y = RING_C.y - RING_MINOR * 0.55


def build_ring():
    """Fibbia d'ottone: anello piccolo e schiacciato, tondino pieno.

    La reference mostra un anello di 22 px su una vita di 82 px, cioe'
    **0,070 m** di diametro esterno: un anello da cintura, non un cerchione.
    La sezione e' piu' spessa sul bordo esterno e piu' sottile sul canale
    interno, cosi' il metallo prende luce sul contorno.
    """
    def section(_a):
        return (1.0, 0.78)

    return [torus("BeltRing", RING_C, (0.0, 1.0, 0.0), RING_MAJOR, RING_MINOR,
                  seg_major=96, seg_minor=16, squash=1.0, flat=0.58,
                  profile=section, section_pow=0.85)]


def build_belt():
    """Cintura scura sottile che passa sotto l'anello, alla base della fascia."""
    def surf(u, v):
        a = TAU * (u - 0.5)
        center = BELT_Z + 0.0040 * math.sin(a + 0.5)
        w = BELT_W * (1.0 - 0.05 * abs(math.sin(a)))
        t = v - 0.5
        z = center + t * w
        b = max(0.0, 1.0 - (2.0 * t) ** 2) ** 0.18
        return sash_pt(a, z, 0.0026 + 0.0011 * b)

    return [cloth_grid("Belt_Dark", 150, 8, surf, thickness=0.0020)]


# --------------------------------------------------------------------------
# staffa con i simboli
# --------------------------------------------------------------------------

STRAP_TOP_Z = 1.0000      # nasce dentro il foro dell'anello
STRAP_SHOULDER_Z = 0.4560  # dove inizia la punta a V
STRAP_TIP_Z = 0.3880
STRAP_W_TOP = 0.0155
STRAP_W_MID = 0.0192


def strap_halfwidth(z):
    """Mezza larghezza del nastro (reference: 11 px = 3,5 cm di larghezza)."""
    t = min(1.0, max(0.0, (STRAP_TOP_Z - z) /
                     (STRAP_TOP_Z - STRAP_TIP_Z)))
    # Il nastro resta **largo fino in fondo** e si chiude a scudo: nella
    # reference la punta e' un rettangolo con gli angoli tagliati, non un ago.
    return lerp_table([(0.00, STRAP_W_TOP), (0.05, 0.0168),
                       (0.40, STRAP_W_MID), (0.80, 0.0192),
                       (0.90, 0.0190), (0.97, 0.0180), (1.00, 0.0166)], t)


def _strap_clearance(z):
    """Quanto la staffa deve stare davanti agli strati a questa quota."""
    extra = 0.0034
    extra = max(extra, 0.0105 * smoothstep(0.040, 0.0, abs(z - SASH_BOT_Z)))
    for spec in WRAPS:
        if layer_hem(0.0, spec) - 0.06 <= z <= SKIRT_TOP_Z:
            extra = max(extra, OFF_WRAP[-1][1] + spec["climb"] + 0.0034)
    for _name, _c, _hw, zbot, tip, _layer, _seed in FALLS:
        if zbot - tip - 0.03 <= z <= SKIRT_TOP_Z:
            extra = max(extra, OFF_TONGUE[-1][1] + 0.003 + 0.0032)
    return extra


def _strap_sash_off(z):
    """Quanto la staffa sta davanti alla fascia.

    All'altezza dell'anello il nastro e' **dentro il foro**, quindi quasi
    sulla superficie della fascia; scendendo esce sotto il tondino e passa
    davanti ai teli incrociati, che sporgono di 8 mm.
    """
    return 0.0100 + 0.0075 * smoothstep(0.995, 0.940, z)


def strap_point(x, z, off=0.0):
    """Superficie della staffa e dei suoi ricami; davanti = -Y."""
    w = max(strap_halfwidth(z), 1e-3)
    rx_sash = WAIST_RX + _strap_sash_off(z)
    a_sash = math.asin(max(-1.0, min(1.0, x / max(rx_sash, 1e-6))))
    sash_front = sash_pt(a_sash, min(z, SASH_BOT_Z), _strap_sash_off(SASH_BOT_Z))
    rx, _ = radius(z, "base")
    a = math.asin(max(-1.0, min(1.0, x / max(rx, 1e-6))))
    skirt_front = surface(a, z, "base", extra=_strap_clearance(z))
    if z >= SASH_BOT_Z + 0.02:
        base = sash_pt(a_sash, z, _strap_sash_off(z))
    elif z <= SASH_BOT_Z - 0.045:
        base = skirt_front
    else:
        t = smoothstep(SASH_BOT_Z - 0.045, SASH_BOT_Z + 0.02, z)
        base = skirt_front.lerp(sash_front, t)
        base.z = z
    y = base.y - off - 0.0016 * (x / w) ** 2
    return Vector((x, y, z))


def strap_bottom_z(side):
    """Bordo inferiore della staffa: V con un piccolo intaglio al centro."""
    s = abs(side)
    # orlo quasi dritto al centro (con l'intaglio) e angoli tagliati di netto
    z = STRAP_TIP_Z + (STRAP_SHOULDER_Z - STRAP_TIP_Z) * (s ** 3.2)
    z += 0.0090 * math.exp(-(side / 0.26) ** 2)
    return z


def build_strap():
    nu, nv = 34, 84

    def surf(u, v):
        side = 2.0 * u - 1.0
        end_z = strap_bottom_z(side)
        z = STRAP_TOP_Z + (end_z - STRAP_TOP_Z) * v
        x = side * strap_halfwidth(z)
        return strap_point(x, z)

    body = cloth_grid("Strap", nu, nv, surf, thickness=0.0020)
    return [body], strap_gold()


def _gold2d(pts2d, width, off=0.0032, thick=0.0004, name="StrapGold"):
    """Ricamo dorato appoggiato sulla staffa, su un piano parallelo alla faccia."""
    dense = []
    for (x0, z0), (x1, z1) in zip(pts2d, pts2d[1:]):
        n = max(1, int(math.ceil(math.hypot(x1 - x0, z1 - z0) / 0.0018)))
        dense.extend((x0 + (x1 - x0) * i / n, z0 + (z1 - z0) * i / n)
                     for i in range(n))
    dense.append(pts2d[-1])

    verts, faces = [], []
    for x, z in dense:
        base = strap_point(x, z)
        half = width * 0.5
        y = base.y - off
        for k in (-1.0, 1.0):
            verts.append(Vector((x + half * k, y, z)))
    m = len(dense)
    for i in range(m - 1):
        a = i * 2
        faces.append((a, a + 1, a + 3, a + 2))
    ob = mesh_from_pydata(name, verts, faces, smooth=True)
    add_solidify(ob, thick, offset=1.0)
    return ob


def _gold_fill2d(polys, name, off=0.0031, thick=0.0005):
    """Riempimento dorato: poligono convesso triangolato a ventaglio.

    Serve per la **punta piena** della staffa e per il centro dei rombi.
    """
    verts, faces = [], []
    for poly in polys:
        base = len(verts)
        for x, z in poly:
            y = strap_point(x, z).y - off
            verts.append(Vector((x, y, z)))
        for i in range(1, len(poly) - 1):
            faces.append((base, base + i, base + i + 1))
    ob = mesh_from_pydata(name, verts, faces, smooth=False)
    add_solidify(ob, thick, offset=1.0)
    return ob


def strap_gold():
    """Motivo dorato della staffa, ricostruito dal disegno.

    Dalla reference, sotto l'anello: un'asta assottigliata, un **rombo** con
    il centro pieno, il grande **cerchio attraversato dalla croce**, un
    secondo rombo, l'asta lunga e infine la punta: due V annidate e un
    **cuneo pieno** che chiude il nastro. I filetti corrono lungo i bordi.
    """
    objs = []
    top, tip = STRAP_TOP_Z, STRAP_TIP_Z

    def Z(f):
        return top + (tip - top) * f

    def stroke(points, width=0.0017, name="line"):
        objs.append(_gold2d(points, width, name=name))

    def diamond(cz, rx, rz, width=0.0015, fill=0.0, name="diamond"):
        stroke([(0, cz + rz), (rx, cz), (0, cz - rz), (-rx, cz),
                (0, cz + rz)], width, name)
        if fill:
            f = fill
            objs.append(_gold_fill2d([[(0, cz + rz * f), (rx * f, cz),
                                       (0, cz - rz * f), (-rx * f, cz)]],
                                     name + "Fill"))

    # asta affusolata che esce dall'anello
    objs.append(_gold_fill2d([[(0.0018, Z(0.130)), (0.0, Z(0.078)),
                               (-0.0018, Z(0.130))]], "stemTip"))
    # primo rombo, pieno al centro
    diamond(Z(0.180), 0.0050, 0.0092, 0.0015, fill=0.52, name="dia1")
    stroke([(0, Z(0.216)), (0, Z(0.286))], 0.0013, "stem0")
    # cerchio grande attraversato dalla croce (simbolo centrale)
    r = 0.0112
    cz = Z(0.348)
    stroke([(r * math.cos(TAU * i / 72), cz + r * math.sin(TAU * i / 72))
            for i in range(73)], 0.0017, "circle")
    stroke([(0, cz - r + 0.0004), (0, cz - r - 0.0092)], 0.0014, "crossStem")
    stroke([(-0.0060, cz - r - 0.0092), (0.0060, cz - r - 0.0092)], 0.0014,
           "crossBar")
    stroke([(0, Z(0.428)), (0, Z(0.512))], 0.0013, "stem1")
    # secondo rombo
    diamond(Z(0.552), 0.0048, 0.0090, 0.0015, fill=0.42, name="dia2")
    stroke([(0, Z(0.588)), (0, Z(0.712))], 0.0013, "stem2")
    # punta: nel disegno il metallo chiude il nastro con due **V annidate**
    # spesse e un cuneo pieno all'estremita'. Le V hanno lo stesso spessore
    # del filetto, cosi' leggono come ricamo e non come una toppa.
    tipz = strap_bottom_z(0.0) - 0.0010
    hb = 0.0168
    stroke([(-hb * 1.00, Z(0.808)), (0.0, Z(0.884)), (hb * 1.00, Z(0.808))],
           0.0034, "tipV1")
    stroke([(-hb * 0.86, Z(0.838)), (0.0, Z(0.908)), (hb * 0.86, Z(0.838))],
           0.0022, "tipV2")
    for sgn in (-1.0, 1.0):
        stroke([(sgn * hb * 1.00, Z(0.808)), (sgn * hb * 0.62, Z(0.850))],
               0.0016, f"tipWing{sgn}")
    # cuneo pieno che chiude il nastro sotto le V (convesso: si triangola)
    w0 = hb * 0.62
    z0 = Z(0.916)
    objs.append(_gold_fill2d([[(0.0, tipz + 0.0015), (-w0, z0),
                              (0.0, z0 + 0.0060), (w0, z0)]], "tipFill"))
    # filetti lungo i bordi nella meta' bassa
    for side in (-1, 1):
        edge = []
        z = Z(0.560)
        while z > strap_bottom_z(0.62) + 0.006:
            edge.append((side * (strap_halfwidth(z) - 0.0020), z))
            z -= 0.006
        stroke(edge, 0.0011, f"edge{side}")
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

# pannelli parametrici costruiti in ``build_all`` (riferimento per i margini).
PANELS: list[Piece] = []


def tag_group(objs, name):
    for ob in objs:
        vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
        vg.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")


def tag_keep(objs):
    """Segna i vertici dei dettagli sottili (ricami, nastri, staffa)."""
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
    """Costruisce tutti i pezzi con i rispettivi materiali e gruppi di LOD."""
    global PANELS
    reset_scene()
    PANELS = []
    overlays = build_overlays()
    falls = build_falls()
    drapes, drape_panels = build_drapes()
    strap_body, strap_gold_parts = build_strap()
    sash = build_sash()
    mid_belt = build_belt()

    groups = {
        "fabric": (build_lining() + build_underskirt() + build_skirt()
                   + overlays + falls
                   + [o for o in sash if not o.name.startswith("Sash_Cross")]),
        "gold": build_ring(),
        "dark": drapes + strap_body + mid_belt + build_drape_welt(drape_panels)
                + [o for o in sash if o.name.startswith("Sash_Cross")],
        "gold_trim": build_drape_runes(drape_panels) + strap_gold_parts,
    }
    all_objs = []
    for key, objs in groups.items():
        assign_material(objs, PART_MATERIAL[key])
        if key in KEEP_GROUPS:
            tag_keep(objs)
        all_objs += objs
    # Il fascio di stoffa dentro l'anello e' di lana scura, come i teli
    # incrociati della reference; la fodera interna resta lino, cosi' sotto
    # l'orlo si vede stoffa chiara e non un buco nero.
    assign_material([o for o in groups["fabric"]
                     if o.name in {"Sash_KnotDark"}],
                    "DRESS1_Wool")
    # Fascia, teli incrociati e cintura hanno bordi vivi e pochi triangoli:
    # vanno nel gruppo "mid", decimato molto meno della gonna.
    sash_parts = [o for o in groups["fabric"]
                  if o.name in {"Sash_Body", "Sash_Liner", "Sash_KnotDark"}]
    sash_parts += [o for o in groups["dark"]
                   if o.name.startswith("Sash_Cross")]
    tag_group(sash_parts + mid_belt, "mid")
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
    # spigoli vivi sulle pieghe: le valli del lino restano linee d'ombra
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(38.0))
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
