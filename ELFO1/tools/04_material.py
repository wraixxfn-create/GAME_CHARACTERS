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
from common import WORK

SRC = os.path.join(WORK, "stage3.blend")
OUT = os.path.join(WORK, "stage4.blend")
TEX_DIR = os.path.join(WORK, "tex")
BASE_SIZE = 2048
NORMAL_SIZE = 2048
ORM_SIZE = 1024
EMIS_SIZE = 1024
AO_SAMPLES = int(os.environ.get("ELFO1_AO_SAMPLES", 16))
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


base = save_and_pack(base, f"{TEX_DIR}/ELFO1_basecolor.jpg", 'JPEG', 93)
base.name = "ELFO1_basecolor"
normal = save_and_pack(normal, f"{TEX_DIR}/ELFO1_normal.jpg", 'JPEG', 94)
normal.name = "ELFO1_normal"
rm = save_and_pack(rm, f"{TEX_DIR}/ELFO1_orm_raw.jpg", 'JPEG', 90)

# ------------------------------------------------------------------ AO bake --
ao = bpy.data.images.new("ELFO1_ao", ORM_SIZE, ORM_SIZE, alpha=False)
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
    ao.pixels.foreach_set(np.full(ORM_SIZE * ORM_SIZE * 4, 0.85, dtype=np.float32))
nt.nodes.remove(tmp)

# ------------------------------------------------------- combinazione ORM ----
w = h = ORM_SIZE
ao_buf = pixels(ao)
ao_lum = np.clip(ao_buf[..., 0], 0.0, 1.0)
ao_lum = 0.32 + 0.68 * ao_lum          # non scurire troppo: e' un elfo chiaro

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


def make_emissive(buf):
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
    rune = (r > g + 0.06) & (r > b + 0.06) & (sat > 0.48) & (mx > 0.12)
    rune = dilate(rune, 2)
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

    col_cold = np.array([0.55, 0.035, 0.010], np.float32)   # brace scura
    col_hot = np.array([1.00, 0.42, 0.10], np.float32)      # ambra
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


emissive = make_emissive(base_arr)

for n in list(bpy.data.images):
    if n.name != "Render Result" and n not in (base, normal, orm_img, emissive):
        bpy.data.images.remove(n)

# -------------------------------------------------------------------- nodi --
mat.name = "ELFO1_MAT"
mat.use_nodes = True
mat.use_backface_culling = False        # tessuto e capelli sono fogli aperti
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
nrm_map.inputs["Strength"].default_value = 1.0

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
bsdf.inputs["Emission Strength"].default_value = 2.2
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
