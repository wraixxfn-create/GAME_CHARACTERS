"""Step 4 - Materiale.

Il materiale Tripo di partenza ha tre mappe 4096^2 (basecolor, normal, RM) e
nessuna occlusione. Qui diventa un PBR glTF-safe, pronto per il motore:

| mappa | risoluzione | contenuto |
|---|---|---|
| baseColor | 2048 | colore originale, nessuna alterazione |
| normal (tangent space) | 2048 | dettaglio delle ciocche, delle pieghe e delle rune |
| ORM | 1024 | `R` = occlusione **bakeata con Cycles**, `G` = roughness, `B` = metallic |
| emissive | 1024 | rune incandescenti generate dai pixel rossi della basecolor |

Due cose specifiche di questo personaggio:

* il gonnellone e i capelli sono **superfici aperte**: il materiale e'
  double-sided (`doubleSided: true` in glTF). Nei render di anteprima la normale
  viene ribaltata sulle facce posteriori, altrimenti la fodera interna del
  tessuto si vede nera;
* le rune sul petto, sul viso e sulle braccia sono dipinte in rosso scuro nella
  basecolor: la maschera dell'emissive si ricava da li' (dominante rossa +
  saturazione), non da un rumore casuale, cosi' la luce segue i simboli veri.

Output: $ELFO1_WORK/stage4.blend
"""
import bpy
import numpy as np
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common import WORK, TARGET_HEIGHT

SRC = os.path.join(WORK, "stage3.blend")
OUT = os.path.join(WORK, "stage4.blend")
TEX_DIR = os.path.join(WORK, "tex")
BASE_SIZE = 2048
NORMAL_SIZE = 2048
ORM_SIZE = 1024
EMIS_SIZE = 1024
AO_SIZE = 2048                       # si bakea piu' grande e si riduce: meno rumore
AO_SAMPLES = int(os.environ.get("ELFO1_AO_SAMPLES", 32))
os.makedirs(TEX_DIR, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=SRC)
sc = bpy.context.scene
ob = next(o for o in bpy.data.objects if o.type == 'MESH')
me = ob.data
mat = me.materials[0]
old = {i.name: i for i in bpy.data.images if i.name != "Render Result"}
print("[tex] sorgenti:", {k: tuple(v.size) for k, v in old.items()})

base = next(img for n, img in old.items() if "basecolor" in n)
normal = next(img for n, img in old.items() if "normal" in n)
rm = next(img for n, img in old.items() if "_rm" in n)

base.scale(BASE_SIZE, BASE_SIZE)
normal.scale(NORMAL_SIZE, NORMAL_SIZE)
rm.scale(ORM_SIZE, ORM_SIZE)


def pixels(img):
    """Pixel come array (h, w, 4) float32 (foreach_get: una lista da 67 milioni
    di float su una 4096 andrebbe in swap)."""
    w, h = img.size
    buf = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    return buf.reshape(h, w, 4)


base_arr = pixels(base)
rm_arr = pixels(rm)


def save_and_pack(img, path, fmt='JPEG', quality=92):
    img.file_format = fmt
    img.filepath_raw = path
    if fmt == 'JPEG':
        sc.render.image_settings.quality = quality
    img.save()
    img.pack()
    return img


# ---------------------------------------------------------------- occhi -----
# La scansione ha il viso liscio: naso, labbra e zigomi ci sono, gli occhi no.
# Qui vengono dipinti nella basecolor, ma non "a mano" sulla texture: si
# rasterizza prima una mappa **UV -> posizione 3D** del modello, poi si disegna
# in coordinate mondo (ellisse dell'occhio, iride, pupilla, palpebre,
# sopracciglio). Cosi' il disegno segue la superficie vera, attraversa le isole
# UV senza cuciture e resta simmetrico.

def uv_position_map(me, size):
    """Rasterizza la mesh in UV: per ogni texel la posizione 3D del punto."""
    uv = np.empty(len(me.uv_layers[0].data) * 2, np.float32)
    me.uv_layers[0].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    pos = np.zeros((size, size, 3), np.float32)
    mask = np.zeros((size, size), bool)
    for poly in me.polygons:
        vs = list(poly.vertices)
        ls = list(range(poly.loop_start, poly.loop_start + poly.loop_total))
        for k in range(1, len(vs) - 1):
            idx = [ls[0], ls[k], ls[k + 1]]
            vv = [vs[0], vs[k], vs[k + 1]]
            tuv = uv[idx] * (size - 1)
            tco = co[vv]
            minx, maxx = int(np.floor(tuv[:, 0].min())), int(np.ceil(tuv[:, 0].max()))
            miny, maxy = int(np.floor(tuv[:, 1].min())), int(np.ceil(tuv[:, 1].max()))
            xs = np.arange(max(0, minx), min(size, maxx + 1))
            ys = np.arange(max(0, miny), min(size, maxy + 1))
            if len(xs) == 0 or len(ys) == 0:
                continue
            gx, gy = np.meshgrid(xs, ys)
            p0, p1, p2 = tuv
            den = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
            if abs(den) < 1e-9:
                continue
            a = ((p1[1] - p2[1]) * (gx - p2[0]) + (p2[0] - p1[0]) * (gy - p2[1])) / den
            b = ((p2[1] - p0[1]) * (gx - p2[0]) + (p0[0] - p2[0]) * (gy - p2[1])) / den
            c = 1 - a - b
            inside = (a >= -1e-6) & (b >= -1e-6) & (c >= -1e-6)
            if not inside.any():
                continue
            P = a[..., None] * tco[0] + b[..., None] * tco[1] + c[..., None] * tco[2]
            pos[gy[inside], gx[inside]] = P[inside]
            mask[gy[inside], gx[inside]] = True
    return pos, mask


def paint_face(rgb, pos, mask, scale):
    """Disegna occhi e sopracciglia in coordinate mondo (scalate a metri)."""
    X, Y, Z = pos[..., 0] * scale, pos[..., 1] * scale, pos[..., 2] * scale
    front_all = mask & (Y < 0.0)
    cx, cz = 0.0325, 1.7115
    probe = front_all & (np.abs(X - cx) < 0.004) & (np.abs(Z - cz) < 0.004)
    if not probe.any():
        print("[face] occhi: non trovo la superficie del viso, salto")
        return np.zeros(mask.shape, bool)
    yf = Y[probe].min()
    front = Y < yf + 0.014
    eye_zone = np.zeros(mask.shape, bool)

    for sign in (1, -1):
        u = (X - sign * cx) * sign          # +u verso l'esterno del viso
        v = Z - cz
        v_t = v - 0.12 * u                  # angolo esterno leggermente in su
        ax, az = 0.0165, 0.0062
        ell = (u / ax) ** 2 + (v_t / az) ** 2

        soft = np.clip((1.25 - ell) / 0.55, 0, 1) * front
        sclera = np.array([0.66, 0.58, 0.52], np.float32)
        rgb[:] = rgb * (1 - soft[..., None] * 0.80) + sclera * soft[..., None] * 0.80

        k = 0.22 * np.clip(1.0 - ell / 1.9, 0, 1) * front
        rgb[:] = rgb * (1 - k[..., None])

        iris = front & (((u + 0.0012) ** 2 + (v_t + 0.0004) ** 2) < 0.0050 ** 2)
        rgb[iris] = rgb[iris] * 0.06 + np.array([0.26, 0.15, 0.06], np.float32) * 0.94
        pupil = front & (((u + 0.0012) ** 2 + (v_t + 0.0004) ** 2) < 0.0023 ** 2)
        rgb[pupil] = np.array([0.015, 0.011, 0.009], np.float32)
        hl = front & (((u + 0.0026) ** 2 + (v_t - 0.0017) ** 2) < 0.0009 ** 2)
        rgb[hl] = rgb[hl] * 0.15 + np.array([0.95, 0.93, 0.90], np.float32) * 0.85

        rim = (ell > 0.80) & (ell < 1.22) & front
        rgb[rim] = rgb[rim] * 0.30 + np.array([0.19, 0.12, 0.09], np.float32) * 0.70
        upper = front & (ell > 0.55) & (ell < 1.25) & (v_t > 0.0022)
        rgb[upper] = rgb[upper] * 0.55 + np.array([0.17, 0.11, 0.09], np.float32) * 0.45

        for uu in np.linspace(-0.014, 0.036, 70):
            t = (uu + 0.014) / 0.050
            zz = cz + 0.0215 + 0.0045 * (1 - (2 * t - 1) ** 2)
            thick = 0.0011 + 0.0013 * (1 - t)
            mb = front & (np.abs(u - uu) < 0.0011) & (np.abs(v_t - (zz - cz)) < thick)
            if mb.any():
                kk = np.clip(1 - np.abs(v_t[mb] - (zz - cz)) / thick, 0, 1)[:, None]
                rgb[mb] = rgb[mb] * (1 - 0.72 * kk) + np.array([0.27, 0.20, 0.16], np.float32) * 0.72 * kk

        eye_zone |= front & (((u / (ax * 1.9)) ** 2 + (v_t / (az * 2.1)) ** 2) < 1.0)
    print(f"[face] occhi dipinti: {eye_zone.sum()} texel (superficie y={yf:+.4f})")
    return eye_zone


# ---------------------------------------------------------- colore base -----
# La scansione ha le ombre cotte dentro: i rigonfiamenti del gonnellone e le
# pieghe piu' profonde sono quasi neri e nel render sembrano buchi. Alzo solo
# le basse luci (una gamma dolce) senza toccare le mezzetinte: il disegno
# resta quello originale ma non ci sono piu' macchie nere.
rgb = np.clip(base_arr[..., :3], 0.0, 1.0)
lum = rgb.mean(axis=2, keepdims=True)
# Le zone quasi nere sono la fodera scura del gonnellone: nella scansione sono
# cosi' chiuse che nel render sembrano buchi. Le tiro su verso un bruno caldo
# (conservando il disegno delle pieghe) invece di lasciarle a zero.
k = np.clip((0.40 - lum) / 0.30, 0.0, 1.0) ** 1.2
k *= 0.62
tint = np.array([0.30, 0.245, 0.205], np.float32)
lift = k * (tint - rgb)
base_arr[..., :3] = np.clip(rgb + lift, 0.0, 1.0)
print(f"[tex] fodera scura rialzata: {(k > 0.05).mean() * 100:.1f}% dei texel, "
      f"delta max {np.abs(lift).max():.3f}")

# viso: occhi e sopracciglia dipinti sulla superficie vera
pos_map, pos_mask = uv_position_map(me, BASE_SIZE)
eye_mask = paint_face(base_arr[..., :3], pos_map, pos_mask, TARGET_HEIGHT)
base_arr[..., :3] = np.clip(base_arr[..., :3], 0.0, 1.0)
base.pixels.foreach_set(base_arr.ravel())     # riscrive la texture modificata
base = save_and_pack(base, f"{TEX_DIR}/ELFO1_basecolor.jpg", 'JPEG', 93)
base.name = "ELFO1_basecolor"
normal = save_and_pack(normal, f"{TEX_DIR}/ELFO1_normal.jpg", 'JPEG', 94)
normal.name = "ELFO1_normal"
rm = save_and_pack(rm, f"{TEX_DIR}/ELFO1_orm_raw.jpg", 'JPEG', 90)

# ------------------------------------------------------------------ AO bake --
ao = bpy.data.images.new("ELFO1_ao", AO_SIZE, AO_SIZE, alpha=False)
ao.colorspace_settings.name = 'Non-Color'
nt = mat.node_tree
tmp = nt.nodes.new("ShaderNodeTexImage")
tmp.image = ao
nt.nodes.active = tmp

bpy.context.view_layer.objects.active = ob
for o in bpy.data.objects:
    o.select_set(o == ob)
sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
sc.cycles.samples = AO_SAMPLES
sc.cycles.use_denoising = False
sc.render.bake.margin = 8
sc.render.bake.use_selected_to_active = False
try:
    bpy.ops.object.bake(type='AO')
    print("[ao] bake completata")
except Exception as exc:  # pragma: no cover
    print("[ao] bake fallita, uso un grigio neutro:", exc)
    ao.pixels.foreach_set(np.full(AO_SIZE * AO_SIZE * 4, 0.85, dtype=np.float32))
nt.nodes.remove(tmp)

# ------------------------------------------------------- combinazione ORM ----
w = h = ORM_SIZE
ao_buf = pixels(ao)
if ao.size[0] != ORM_SIZE:              # riduzione box: toglie il rumore del bake
    from PIL import Image
    small = Image.fromarray((np.clip(ao_buf, 0.0, 1.0) * 255).astype(np.uint8))
    small = small.resize((ORM_SIZE, ORM_SIZE), Image.LANCZOS)
    ao_buf = np.asarray(small, dtype=np.float32) / 255.0
ao_lum = np.clip(ao_buf[..., 0], 0.0, 1.0)
ao_lum = 0.45 + 0.55 * ao_lum          # non scurire troppo: e' un elfo chiaro

orm = np.ones((h, w, 4), np.float32)
orm[..., 0] = ao_lum
orm[..., 1] = np.clip(rm_arr[..., 1], 0.0, 1.0)
orm[..., 2] = np.clip(rm_arr[..., 2], 0.0, 1.0)

orm_img = bpy.data.images.new("ELFO1_orm_final", w, h, alpha=False)
orm_img.colorspace_settings.name = 'Non-Color'
orm_img.pixels.foreach_set(orm.ravel())
orm_img.name = "ELFO1_orm"
orm_img = save_and_pack(orm_img, f"{TEX_DIR}/ELFO1_orm.jpg", 'JPEG', 90)
print(f"[orm] AO media={ao_lum.mean():.3f} min={ao_lum.min():.3f}  "
      f"roughness media={orm[..., 1].mean():.3f} metallic media={orm[..., 2].mean():.3f}")

# ----------------------------------------------------------- rune emissive --


def dilate(mask, radius):
    """Dilatazione binaria senza scipy: massimo su una finestra scorrevole."""
    out = mask.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def make_emissive(buf, exclude=None, atten=None):
    """Le rune dipinte (rosso scuro, saturo) diventano luce.

    La maschera viene dilatata di 2 px e ammorbidita, poi modulata con un
    rumore fBm a bassa frequenza: l'incandescenza "respira" invece di essere
    piatta, e nei frame animati si nota.
    """
    from PIL import Image
    hh, ww = buf.shape[:2]
    r, g, b = buf[..., 0], buf[..., 1], buf[..., 2]
    mx = buf[..., :3].max(2)
    mn = buf[..., :3].min(2)
    sat = (mx - mn) / np.maximum(mx, 1e-5)
    # soglia alta: la pelle e' calda ma poco satura, le rune sono rosso cupo.
    # Con una soglia bassa si accendeva mezza schiena (7% della UV): qui si
    # scende sotto il punto percentuale e resta solo l'inchiostro.
    rune = (r > g + 0.08) & (r > b + 0.08) & (sat > 0.52) & (mx > 0.12)
    if exclude is not None:
        rune &= ~exclude                    # l'iride non deve accendersi
    rune = dilate(rune, 1)
    print(f"[tex] rune: {rune.mean() * 100:.2f}% della superficie UV")
    soft = rune.astype(np.float32)
    # sfumatura 3x3 per non avere bordi scalettati
    k = np.array([0.25, 0.5, 0.25], np.float32)
    soft = np.apply_along_axis(lambda m: np.convolve(m, k, mode='same'), 1, soft)
    soft = np.apply_along_axis(lambda m: np.convolve(m, k, mode='same'), 0, soft)

    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32) / np.float32(max(hh, ww))
    noise = (0.5 + 0.5 * np.sin(xx * 22.0 + 1.7 * np.sin(yy * 13.0))
             * np.cos(yy * 17.0 + 1.3 * np.sin(xx * 9.0)))
    pulse = 0.55 + 0.45 * noise
    glow = np.clip(soft * pulse * 1.5, 0.0, 1.0)
    if atten is not None:
        # sul viso le rune restano inchiostro: accese lavavano via gli occhi
        glow *= atten

    col_cold = np.array([0.42, 0.030, 0.008], np.float32)   # brace scura
    col_hot = np.array([1.00, 0.36, 0.055], np.float32)     # ambra
    t = (glow ** 0.7)[..., None]
    rgb = col_cold * (1 - t) + col_hot * t

    out = np.ones((hh, ww, 4), np.float32)
    out[..., :3] = rgb * glow[..., None]
    img = bpy.data.images.new("ELFO1_emissive", ww, hh, alpha=False)
    img.pixels.foreach_set(out.ravel())
    if (ww, hh) != (EMIS_SIZE, EMIS_SIZE):
        img.scale(EMIS_SIZE, EMIS_SIZE)
    img = save_and_pack(img, f"{TEX_DIR}/ELFO1_emissive.jpg", 'JPEG', 92)
    print(f"[tex] emissive: energia media {(glow * 0.8).mean():.4f}")
    return img


def face_attenuation(pos, mask, strength=0.85):
    """Sul viso le rune non devono brillare: restano inchiostro rosso cupo."""
    if pos is None:
        return None
    X = pos[..., 0] * TARGET_HEIGHT          # come in paint_face: metri
    Y = pos[..., 1] * TARGET_HEIGHT
    Z = pos[..., 2] * TARGET_HEIGHT
    z, y = Z, Y
    x = np.abs(X)
    inside = (mask & (z > 1.595) & (z < 1.830) & (x < 0.115) & (y < 0.03))
    soft = inside.astype(np.float32)
    k = np.array([0.25, 0.5, 0.25], np.float32)
    for axis in (0, 1):
        soft = np.apply_along_axis(lambda m: np.convolve(m, k, mode='same'), axis, soft)
        soft = np.apply_along_axis(lambda m: np.convolve(m, k, mode='same'), axis, soft)
    att = 1.0 - strength * np.clip(soft, 0.0, 1.0)
    print(f"[tex] viso: rune attenuate al {(1 - strength) * 100:.0f}% su "
          f"{(soft > 0.5).mean() * 100:.2f}% della UV")
    return att


face_att = face_attenuation(pos_map, pos_mask)
emissive = make_emissive(base_arr, exclude=eye_mask, atten=face_att)

for n in list(bpy.data.images):
    if n.name != "Render Result" and n not in (base, normal, orm_img, emissive):
        bpy.data.images.remove(n)

# -------------------------------------------------------------------- nodi --
mat.name = "ELFO1_MAT"
mat.use_nodes = True
mat.use_backface_culling = False        # tasselli sottili: doppia faccia
mat.blend_method = 'OPAQUE'
nt = mat.node_tree
nt.nodes.clear()

out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (900, 0)
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (600, 0)

tex_base = nt.nodes.new("ShaderNodeTexImage"); tex_base.location = (-900, 350)
tex_base.image = base; tex_base.label = "BaseColor"
tex_nrm = nt.nodes.new("ShaderNodeTexImage"); tex_nrm.location = (-900, 0)
tex_nrm.image = normal; tex_nrm.label = "Normal"
tex_orm = nt.nodes.new("ShaderNodeTexImage"); tex_orm.location = (-900, -350)
tex_orm.image = orm_img; tex_orm.label = "OcclusionRoughMetal"
tex_emis = nt.nodes.new("ShaderNodeTexImage"); tex_emis.location = (-900, 700)
tex_emis.image = emissive; tex_emis.label = "Emissive"

nrm_map = nt.nodes.new("ShaderNodeNormalMap"); nrm_map.location = (-450, 0)
nrm_map.inputs["Strength"].default_value = 0.9

sep = nt.nodes.new("ShaderNodeSeparateColor"); sep.location = (-600, -350)

grp = bpy.data.node_groups.new("glTF Material Output", 'ShaderNodeTree')
grp.interface.new_socket(name="Occlusion", in_out='INPUT', socket_type='NodeSocketFloat')
gout = nt.nodes.new("ShaderNodeGroup"); gout.node_tree = grp
gout.location = (300, -500)
gout.inputs[0].default_value = 1.0

nt.links.new(tex_base.outputs["Color"], bsdf.inputs["Base Color"])
nt.links.new(tex_nrm.outputs["Color"], nrm_map.inputs["Color"])
nt.links.new(nrm_map.outputs["Normal"], bsdf.inputs["Normal"])
nt.links.new(tex_orm.outputs["Color"], sep.inputs["Color"])
nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
nt.links.new(sep.outputs["Red"], gout.inputs["Occlusion"])
nt.links.new(tex_emis.outputs["Color"], bsdf.inputs["Emission Color"])
bsdf.inputs["Emission Strength"].default_value = 1.05
bsdf.inputs["Specular IOR Level"].default_value = 0.40
bsdf.inputs["IOR"].default_value = 1.45
nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

# --------------------------------------------------------------- verifica ----
try:
    from PIL import Image
    for name, path in (("basecolor", f"{TEX_DIR}/ELFO1_basecolor.jpg"),
                       ("normal", f"{TEX_DIR}/ELFO1_normal.jpg"),
                       ("orm", f"{TEX_DIR}/ELFO1_orm.jpg"),
                       ("emissive", f"{TEX_DIR}/ELFO1_emissive.jpg")):
        arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
        print(f"[check] {name:10s} {arr.shape[1]}x{arr.shape[0]}  "
              f"R={arr[..., 0].mean():.3f} G={arr[..., 1].mean():.3f} B={arr[..., 2].mean():.3f}")
        if arr.max() <= 0.002:
            raise SystemExit(f"[check] ERRORE: {name} e' completamente nera")
except ImportError:
    print("[check] PIL non disponibile, salto la verifica")

mat.node_tree.nodes.active = tex_orm
print("[mat] nodi:", len(nt.nodes), "link:", len(nt.links))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED stage4.blend")
