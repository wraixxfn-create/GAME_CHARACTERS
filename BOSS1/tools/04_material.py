"""Step 4 - Materiale (v2).

Migliorie rispetto alla v1:

* **basecolor e normal a 2048** (la normal e' quella che conta di piu' sulle
  spine e sui solchi: a 1024 il dettaglio si perdeva), ORM ed emissive a 1024.
* **AO bakeata** con Cycles e infilata nel canale rosso dell'ORM, come vuole
  il glTF (`R = occlusion, G = roughness, B = metallic`). L'AO e' collegata
  anche al nodo *glTF Material Output* -> `Occlusion`, altrimenti l'exporter
  la ignorerebbe.
* **vene incandescenti** rigenerate a partire da basecolor + rumore fBm
  (invece delle tre sinusoidi della v1): piu' organiche e senza pattern
  ripetuti visibili.
* materiale opaco, backface culling attivo (in glTF diventa `doubleSided:
  false`, come si aspetta un motore), normal map in spazio tangente.

Output: /home/user/work/stage4.blend
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
BASE_SIZE = 2048       # basecolor
NORMAL_SIZE = 2048     # normal
ORM_SIZE = 1024        # occlusion + roughness + metallic
EMIS_SIZE = 1024       # emissive
AO_SAMPLES = 24
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
    """Pixel come array (h, w, 4) float32. Va letto *prima* di packare
    l'immagine: dopo il pack il buffer in memoria puo' essere rilasciato."""
    w, h = img.size
    return np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)


base_arr = pixels(base)
rm_arr = pixels(rm)


def save_and_pack(img, path, fmt='JPEG', quality=92):
    """Salva su disco e impacchetta. Il colorspace NON va toccato qui: assegnarlo
    invalida il buffer dell'immagine (e per le immagini generate il file
    finirebbe nero). Va impostato una sola volta, prima di scrivere i pixel."""
    img.file_format = fmt
    img.filepath_raw = path
    if fmt == 'JPEG':
        sc.render.image_settings.quality = quality
    img.save()
    img.pack()
    return img


base = save_and_pack(base, f"{TEX_DIR}/BOSS1_basecolor.jpg", 'JPEG', 92)
normal = save_and_pack(normal, f"{TEX_DIR}/BOSS1_normal.jpg", 'JPEG', 94)
rm = save_and_pack(rm, f"{TEX_DIR}/BOSS1_orm.jpg", 'JPEG', 90)

# ------------------------------------------------------------------ AO bake --
# L'occlusione ambientale e' quello che fa "sedere" il personaggio nella scena:
# senza AO i solchi tra le spine e le pieghe della carne restano piatti.
ao = bpy.data.images.new("BOSS1_ao", ORM_SIZE, ORM_SIZE, alpha=False)
ao.colorspace_settings.name = 'Non-Color'

# nodo immagine temporaneo su cui bakeare
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
sc.render.bake.margin = 12
sc.render.bake.use_selected_to_active = False
try:
    bpy.ops.object.bake(type='AO')
    print("[ao] bake completata")
except Exception as exc:  # pragma: no cover
    print("[ao] bake fallita, uso un grigio neutro:", exc)
    ao.pixels[:] = [0.85] * (ORM_SIZE * ORM_SIZE * 4)
nt.nodes.remove(tmp)

# ------------------------------------------------- combinazione canali ORM ----
w = h = ORM_SIZE
ao_buf = pixels(ao)
ao_lum = np.clip(ao_buf[..., 0], 0.0, 1.0)
# l'AO bakeata contiene solo l'occlusione: la rimappo per non scurire troppo
ao_lum = 0.35 + 0.65 * ao_lum

orm = np.ones((h, w, 4), np.float32)
orm[..., 0] = ao_lum
orm[..., 1] = np.clip(rm_arr[..., 1], 0.0, 1.0)    # roughness
orm[..., 2] = np.clip(rm_arr[..., 2], 0.0, 1.0)    # metallic
orm[..., 3] = 1.0

# NB: il colorspace va impostato *prima* di scrivere i pixel, altrimenti
# Blender invalida il buffer e il file salvato viene nero.
orm_img = bpy.data.images.new("BOSS1_orm_final", w, h, alpha=False)
orm_img.colorspace_settings.name = 'Non-Color'
orm_img.pixels[:] = orm.ravel()
orm_img = save_and_pack(orm_img, f"{TEX_DIR}/BOSS1_orm.jpg", 'JPEG', 90)
print(f"[orm] AO media={ao_lum.mean():.3f} min={ao_lum.min():.3f}  "
      f"roughness media={orm[..., 1].mean():.3f} metallic media={orm[..., 2].mean():.3f}")

# ---------------------------------------------------- vene incandescenti -----


def fbm(h, w, octaves=5, seed=11):
    """Rumore fBm periodico (somma di ottave con frequenze irrazionali)."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32) / np.float32(max(h, w))
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        freq = 3.0 * (1.9 ** o)
        ang = rng.random(4) * 6.283
        out += amp * (0.5 + 0.5 * np.sin(xx * freq * 6.283 + ang[0] + 1.3 * np.sin(yy * freq * 2.7 + ang[1]))
                      * np.cos(yy * freq * 6.283 + ang[2] + 1.1 * np.sin(xx * freq * 3.1 + ang[3])))
        total += amp
        amp *= 0.55
    return out / total


def make_emissive(buf, path, size=EMIS_SIZE):
    """Vene incandescenti: dove la basecolor e' "carne" (rosso dominante) e il
    rumore fBm crea dei canali, la superficie emette."""
    h, w = buf.shape[:2]
    r, g, b = buf[..., 0], buf[..., 1], buf[..., 2]
    meat = np.clip((r - (g + b) * 0.5) * 6.5, 0.0, 1.0) ** 1.3
    n1 = fbm(h, w, 4, seed=3)
    n2 = fbm(h, w, 3, seed=17)
    ridges = np.clip(1.0 - np.abs(n1 - 0.5) * 4.6, 0.0, 1.0) ** 2.4
    patch = np.clip((fbm(h, w, 2, seed=41) - 0.42) * 3.2, 0.0, 1.0)   # chiazze
    vein = np.clip(ridges * 1.9 - 0.55, 0.0, 1.0) * meat * patch
    vein = np.clip(vein + 0.45 * np.clip(n2 - 0.78, 0, 1) * meat * patch, 0.0, 1.0)
    col_cold = np.array([0.42, 0.015, 0.008], np.float32)
    col_hot = np.array([1.0, 0.34, 0.07], np.float32)
    t = (vein ** 0.65)[..., None]
    rgb = col_cold * (1 - t) + col_hot * t
    out = np.ones((h, w, 4), np.float32)
    out[..., :3] = rgb * vein[..., None]
    img = bpy.data.images.new("BOSS1_emissive", w, h, alpha=False)
    img.pixels[:] = out.ravel()
    if (w, h) != (EMIS_SIZE, EMIS_SIZE):
        img.scale(EMIS_SIZE, EMIS_SIZE)
    img = save_and_pack(img, path, 'JPEG', 90)
    print(f"[tex] emissive: vene su {(vein > 0.05).mean() * 100:.1f}% della superficie UV")
    return img


emissive = make_emissive(base_arr, f"{TEX_DIR}/BOSS1_emissive.jpg")

for n in list(bpy.data.images):
    if n.name != "Render Result" and n not in (base, normal, orm_img, emissive):
        bpy.data.images.remove(n)

# ------------------------------------------------------------------ nodi -----
mat.name = "BOSS1_MAT"
mat.use_nodes = True
mat.use_backface_culling = True
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

# glTF: il nodo "glTF Material Output" con l'input Occlusion e' quello che
# l'exporter riconosce per esportare l'AO dell'ORM anche nei motori esterni.
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
bsdf.inputs["Emission Strength"].default_value = 1.6
bsdf.inputs["Specular IOR Level"].default_value = 0.42
bsdf.inputs["IOR"].default_value = 1.45

nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

# ------------------------------------------------------------- verifica -----
try:
    from PIL import Image
    for name, path, chans in (("basecolor", f"{TEX_DIR}/BOSS1_basecolor.jpg", "RGB"),
                              ("ormal", f"{TEX_DIR}/BOSS1_normal.jpg", "RGB"),
                              ("orm", f"{TEX_DIR}/BOSS1_orm.jpg", "RGB"),
                              ("emissive", f"{TEX_DIR}/BOSS1_emissive.jpg", "RGB")):
        arr = np.asarray(Image.open(path).convert(chans), dtype=np.float32) / 255.0
        print(f"[check] {name:10s} {arr.shape[1]}x{arr.shape[0]}  "
              + "  ".join(f"{c}={arr[..., i].mean():.3f}" for i, c in enumerate(chans)))
        if arr.max() <= 0.002:
            raise SystemExit(f"[check] ERRORE: {name} e' completamente nera")
except ImportError:
    print("[check] PIL non disponibile, salto la verifica")

mat.node_tree.nodes.active = tex_orm
print("[mat] nodi:", len(nt.nodes), "link:", len(nt.links))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED stage4.blend")
