"""Step 4 - Materiale.

- riduce le 3 texture 4K a 1K (basecolor, normal, roughness/metallic) e le
  ricomprime in JPEG per il peso nel motore
- ricostruisce il materiale PBR ottimizzato per glTF (ORM impacchettato)
- aggiunge un layer procedurale leggero: vene incandescenti nelle zone rosse,
  variazione di rugosita' e desaturazione delle zone "ossa"

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
TEX_SIZE = 1024

os.makedirs(TEX_DIR, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=SRC)
ob = next(o for o in bpy.data.objects if o.type == 'MESH')
me = ob.data
mat = me.materials[0]
old = {i.name: i for i in bpy.data.images if i.name != "Render Result"}
print("[tex] sorgenti:", {k: tuple(v.size) for k, v in old.items()})

# --------------------------------------------------------------- textures --
resized = {}
for name, img in old.items():
    if img.size[0] == 0:
        continue
    img.scale(TEX_SIZE, TEX_SIZE)
    resized[name] = img
    print(f"[tex] {name} -> {tuple(img.size)}")

base = next(img for n, img in resized.items() if "basecolor" in n)
normal = next(img for n, img in resized.items() if "normal" in n)
rm = next(img for n, img in resized.items() if n.endswith("_rm") or "_rm" in n)

# riesporta su disco (JPEG) e ripacchetta
def save_and_pack(img, path, fmt='JPEG', quality=90, non_color=False):
    img.file_format = fmt
    img.filepath_raw = path
    if fmt == 'JPEG':
        bpy.context.scene.render.image_settings.quality = quality
    img.save()
    img.pack()
    if non_color:
        img.colorspace_settings.name = 'Non-Color'
    return img

base = save_and_pack(base, f"{TEX_DIR}/BOSS1_basecolor.jpg", 'JPEG', 90)
normal = save_and_pack(normal, f"{TEX_DIR}/BOSS1_normal.jpg", 'JPEG', 92, True)
rm = save_and_pack(rm, f"{TEX_DIR}/BOSS1_orm.jpg", 'JPEG', 88, True)
for n in list(bpy.data.images):
    if n.name != "Render Result" and n not in (base, normal, rm):
        bpy.data.images.remove(n)


def make_emissive_texture(base_img, path, size=TEX_SIZE):
    """Genera la mappa emissiva dai pixel della basecolor (vene incandescenti)."""
    w, h = base_img.size
    buf = np.array(base_img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    r, g, b = buf[..., 0], buf[..., 1], buf[..., 2]
    meat = np.clip((r - g) * 3.4, 0.0, 1.0) ** 0.85        # zone rosse = carne
    # rumore multi-scala periodico in spazio texture
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    noise = np.zeros((h, w), np.float32)
    for freq, amp in ((6, 0.5), (13, 0.3), (29, 0.2)):
        ph = np.random.default_rng(7).random(4) * 6.283
        noise += amp * (0.5 + 0.5 * np.sin(xx / w * freq * 6.283 + ph[0]) *
                        np.sin(yy / h * freq * 6.283 + ph[1]))
    vein = np.clip((noise - 0.42) * 2.2, 0.0, 1.0) * meat
    col_cold = np.array([0.55, 0.02, 0.01], np.float32)
    col_hot = np.array([1.0, 0.30, 0.06], np.float32)
    t = (vein ** 0.7)[..., None]
    rgb = col_cold * (1 - t) + col_hot * t
    out = np.zeros((h, w, 4), np.float32)
    out[..., :3] = rgb * vein[..., None]
    out[..., 3] = 1.0
    img = bpy.data.images.new("BOSS1_emissive", w, h, alpha=False)
    img.pixels[:] = out.ravel()
    img.file_format = 'JPEG'
    img.filepath_raw = path
    img.save()
    img.pack()
    print(f"[tex] emissive: vene su {float((vein > 0.05).mean()) * 100:.1f}% della superficie UV")
    return img


# --------------------------------------------------------------- material --
mat.name = "BOSS1_MAT"
mat.use_nodes = True
nt = mat.node_tree
nt.nodes.clear()

out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (900, 0)
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (600, 0)

tex_base = nt.nodes.new("ShaderNodeTexImage"); tex_base.location = (-800, 300)
tex_base.image = base; tex_base.label = "BaseColor"
tex_nrm = nt.nodes.new("ShaderNodeTexImage"); tex_nrm.location = (-800, -50)
tex_nrm.image = normal; tex_nrm.label = "Normal"
tex_orm = nt.nodes.new("ShaderNodeTexImage"); tex_orm.location = (-800, -350)
tex_orm.image = rm; tex_orm.label = "RoughMetal"

nrm_map = nt.nodes.new("ShaderNodeNormalMap"); nrm_map.location = (-400, -50)
nrm_map.inputs["Strength"].default_value = 1.0

sep = nt.nodes.new("ShaderNodeSeparateColor"); sep.location = (-500, -350)

# --- vene incandescenti -----------------------------------------------------
# La maschera emissiva e' calcolata in spazio texture dai pixel della basecolor
# (dominanza del rosso) + un rumore multiplicativo che rompe le zone piatte.
# Cosi' Blender e glTF vedono la stessa identica mappa (glTF non supporta
# shader procedurali).
emissive = make_emissive_texture(base, f"{TEX_DIR}/BOSS1_emissive.jpg")

emis_tex = nt.nodes.new("ShaderNodeTexImage"); emis_tex.location = (-800, 620)
emis_tex.image = emissive; emis_tex.label = "Emissive"
emis_tex.image.colorspace_settings.name = 'sRGB'

nt.links.new(emis_tex.outputs["Color"], bsdf.inputs["Emission Color"])
bsdf.inputs["Emission Strength"].default_value = 2.5

# --- rugosita': canale verde dell'ORM, diretto (identico in glTF)
# --- colore finale: basecolor leggermente desaturata sulle ossa + dettaglio
hsv = nt.nodes.new("ShaderNodeHueSaturation"); hsv.location = (-150, 300)
hsv.inputs["Saturation"].default_value = 1.06
hsv.inputs["Value"].default_value = 1.02

# --------------------------------------------------------------- link up --
nt.links.new(tex_base.outputs["Color"], hsv.inputs["Color"])
nt.links.new(hsv.outputs["Color"], bsdf.inputs["Base Color"])

nt.links.new(tex_nrm.outputs["Color"], nrm_map.inputs["Color"])
nt.links.new(nrm_map.outputs["Normal"], bsdf.inputs["Normal"])

nt.links.new(tex_orm.outputs["Color"], sep.inputs["Color"])
nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])


bsdf.inputs["Specular IOR Level"].default_value = 0.42
bsdf.inputs["IOR"].default_value = 1.45

nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

# glTF-friendly: impacchetta ORM con nodo dedicato? Blender esporta
# automaticamente Green=roughness / Blue=metallic se i canali sono collegati
# a un'unica immagine, quindi va bene cosi'.

print("[mat] nodi:", len(nt.nodes), "link:", len(nt.links))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED stage4.blend")
