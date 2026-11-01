"""DRESS1 — materiali PBR e bake AO.

Cinque materiali: tre stoffe testurizzate (lino, lana e cuoio della
staffa/cintura) e due metalli a tinta piena (ottone e ricamo). Le immagini
sono generate in numpy, l'AO viene bakeata su Cycles e le mappe sono
impacchettate nel .blend. Le connessioni al nodo glTF Material Output
permettono all'exporter di includere l'occlusione nei GLB.
"""

from __future__ import annotations

import math
import os
import sys

import bpy  # noqa: E402
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ensure_dir, work_dir

TEX = 1024


# --------------------------------------------------------------------------
# rumore + pattern (numpy, deterministico)
# --------------------------------------------------------------------------

def rng(seed):
    return np.random.default_rng(seed)


def value_noise(size, cells, seed):
    g = rng(seed).random((cells + 1, cells + 1)).astype(np.float32)
    g[-1, :] = g[0, :]
    g[:, -1] = g[:, 0]
    xs = np.linspace(0, cells, size, endpoint=False)
    ys = np.linspace(0, cells, size, endpoint=False)
    x0 = xs.astype(int)
    y0 = ys.astype(int)
    fx = xs - x0
    fy = ys - y0
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    x1 = (x0 + 1) % cells
    y1 = (y0 + 1) % cells
    a = g[np.ix_(y0, x0)]
    b = g[np.ix_(y0, x1)]
    c = g[np.ix_(y1, x0)]
    d = g[np.ix_(y1, x1)]
    fx2 = fx[None, :]
    fy2 = fy[:, None]
    return ((a * (1 - fx2) + b * fx2) * (1 - fy2)
            + (c * (1 - fx2) + d * fx2) * fy2).astype(np.float32)


def fbm(size, base_cells=4, octaves=4, seed=0, gain=0.5, lac=2.0):
    out = np.zeros((size, size), np.float32)
    amp, cells = 1.0, base_cells
    norm = 0.0
    for o in range(octaves):
        out += amp * value_noise(size, max(2, int(cells)), seed + o * 17)
        norm += amp
        amp *= gain
        cells *= lac
    return out / max(norm, 1e-6)


def weave(width=1, height=1, size=TEX):
    """Trama tessuta: fili in ordito e trama."""
    yy, xx = np.mgrid[0:size, 0:size]
    u = (xx // width + yy // height) % 2
    return u.astype(np.float32)


def cloth_map(size=TEX, seed=7, fiber=0.55):
    """Altezza di una stoffa: trama finissima + fibrille + pieghe larghe.

    La trama e' a 1 texel: sulle UV del capo (isole da 0,1-0,3 unita') si
    legge come tessuto a filo fine invece che come una scacchiera.
    """
    w = weave(1, 1, size)
    fib = fbm(size, base_cells=96, octaves=3, seed=seed + 5)
    big = fbm(size, base_cells=7, octaves=5, seed=seed + 11)
    h = (0.10 * w + 0.55 * fiber * fib + 0.35 * big)
    return h.astype(np.float32)


def normal_from_height(h, strength=2.0):
    """Normale tangente da una mappa di altezza (Sobel)."""
    gy, gx = np.gradient(h.astype(np.float32))
    nx = -gx * strength
    ny = -gy * strength
    nz = np.ones_like(nx)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / ln, ny / ln, nz / ln
    rgb = np.stack([nx * 0.5 + 0.5, ny * 0.5 + 0.5, nz * 0.5 + 0.5], axis=-1)
    return (rgb * 255.0).clip(0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# immagini in Blender
# --------------------------------------------------------------------------

TEX_DIR = os.path.join(work_dir(), "tex")


def image_from_array(name, arr, colorspace="Non-Color"):
    """Scrive l'array su PNG, lo ricarica e lo impacchetta nel .blend.

    Passare per il filesystem e' l'unico modo affidabile: un'immagine
    "generated" con i pixel scritti a mano non sopravvive al salvataggio (si
    ricarica nera), quindi si salva, si ricarica come ``FILE`` e si packa.
    """
    ensure_dir(TEX_DIR)
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0, 1) * 255.0).astype(np.uint8)
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        rgba = np.dstack([arr, np.full((h, w, 1), 255, np.uint8)])
    else:
        rgba = arr
    img = bpy.data.images.new(name, width=w, height=h, alpha=False)
    flat = (rgba[::-1].astype(np.float32) / 255.0).ravel()
    img.pixels.foreach_set(flat)
    img.update()
    path = os.path.join(TEX_DIR, name + ".png")
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    img.source = "FILE"
    img.filepath = path
    img.reload()
    img.pack()
    img.colorspace_settings.name = colorspace
    return img


def image_solid(name, rgb, size=8, colorspace="sRGB"):
    arr = np.zeros((size, size, 3), np.uint8)
    arr[..., 0] = int(rgb[0] * 255)
    arr[..., 1] = int(rgb[1] * 255)
    arr[..., 2] = int(rgb[2] * 255)
    return image_from_array(name, arr, colorspace)


def bake_ao(ob, resolution=1024, samples=32, distance=0.30):
    """Bake AO sulla UV comune, con una destinazione per *ogni* materiale.

    Blender cerca il nodo immagine attivo nello slot della faccia che sta
    cuocendo. Preparare solo lo slot zero lascia vuota la maggior parte della
    mappa. I nodi temporanei vengono rimossi dopo il bake.
    """
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.bake.use_pass_direct = False
    sc.render.bake.use_pass_indirect = False
    sc.render.bake.margin = 6
    sc.world.light_settings.distance = distance

    img = bpy.data.images.new("DRESS1_AO", resolution, resolution, alpha=False)
    targets = []
    for mat in ob.data.materials:
        if mat is None:
            continue
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = img
        for node in nodes:
            node.select = False
        tex.select = True
        nodes.active = tex
        targets.append((nodes, tex))
    sc.cycles.bake_type = "AO"
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    try:
        bpy.ops.object.bake(type="AO")
    finally:
        for nodes, tex in targets:
            nodes.remove(tex)

    ensure_dir(TEX_DIR)
    path = os.path.join(TEX_DIR, "DRESS1_AO.png")
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    img.source = "FILE"
    img.filepath = path
    img.reload()
    img.colorspace_settings.name = "Non-Color"
    img.pack()
    return img


# --------------------------------------------------------------------------
# materiali
# --------------------------------------------------------------------------

def gltf_output_group(mat):
    """Nodo glTF Material Output per l'occlusione (lo legge l'exporter)."""
    ng = bpy.data.node_groups.get("glTF Material Output")
    if ng is None:
        ng = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        ng.interface.new_socket(name="Occlusion", in_out="INPUT",
                                socket_type="NodeSocketFloat")
    node = mat.node_tree.nodes.new("ShaderNodeGroup")
    node.node_tree = ng
    node.name = "glTF Settings"
    return node


def make_trim_material(name):
    """Oro "foglia" dei ricami: opaco, si legge anche da lontano e in miniatura.

    I nastri dorati sono larghi 3-4 mm: una superficie perfettamente
    metallica li fa sparire in controluce. Qui sono oro dipinto, quindi
    metallic alto ma roughness alta.
    """
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    # Il rombo grande sta in una zona che l'incrocio dei veli mette in ombra:
    # l'oro resta un filo piu' chiaro e piu' metallico perche' il simbolo
    # resti leggibile anche li'.
    bsdf.inputs["Base Color"].default_value = (0.575, 0.425, 0.155, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.62
    bsdf.inputs["Roughness"].default_value = 0.40
    mat.use_backface_culling = True
    return mat


def make_brass_material(name, base_rgb=(0.430, 0.298, 0.108),
                        metallic=0.82, roughness=0.40):
    """Ottone a tinta piena.

    Un anello di 6 cm occupa pochi texel della mappa: una texture a chiazze
    li' si legge come camouflage. Il metallo va descritto con valori
    uniformi (base color + metallic + roughness), che sono anche i piu'
    leggeri per il motore.
    """
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*base_rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    mat.use_backface_culling = True
    return mat


def make_material(name, base_img, orm_img, normal_img=None, ao_img=None,
                  emissive_img=None, metallic=0.0, roughness=1.0,
                  normal_strength=1.0, emissive_strength=1.0,
                  double_sided=False, sheen=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (250, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    # baseColor
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = base_img
    t.location = (-400, 250)
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])

    # ORM -> R occlusione, G roughness, B metallic
    if orm_img is not None:
        t2 = nt.nodes.new("ShaderNodeTexImage")
        t2.image = orm_img
        t2.location = (-400, -50)
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        sep.location = (-120, -50)
        nt.links.new(t2.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
        if ao_img is not None:
            tao = nt.nodes.new("ShaderNodeTexImage")
            tao.image = ao_img
            tao.location = (-400, -350)
            # Il canale R delle ORM e' bianco; collegare direttamente il
            # bake al nodo glTF preserva occlusionTexture anche nell'export.
            grp = gltf_output_group(mat)
            grp.location = (250, -420)
            nt.links.new(tao.outputs["Color"], grp.inputs["Occlusion"])
    else:
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness

    if normal_img is not None:
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = normal_img
        tn.location = (-400, -650)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.location = (-120, -650)
        nm.inputs["Strength"].default_value = normal_strength
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])

    if emissive_img is not None:
        te = nt.nodes.new("ShaderNodeTexImage")
        te.image = emissive_img
        te.location = (-400, -950)
        nt.links.new(te.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emissive_strength

    if sheen:
        bsdf.inputs["Sheen Weight"].default_value = sheen
        bsdf.inputs["Sheen Roughness"].default_value = 0.4

    mat.use_backface_culling = not double_sided
    return mat


# --------------------------------------------------------------------------
# set di mappe per tipo di superficie
# --------------------------------------------------------------------------

def linen_maps():
    h = cloth_map(TEX, seed=7, fiber=0.8)
    base = np.zeros((TEX, TEX, 3), np.float32)
    tone = 0.80 + 0.20 * h
    # avorio caldo con variazioni di tono (la reference e' color crema)
    base[..., 0] = 0.882 * tone
    base[..., 1] = 0.840 * tone * 0.995
    base[..., 2] = 0.752 * tone * 0.99
    # macchie di usura
    wear = fbm(TEX, base_cells=3, octaves=5, seed=31)
    base *= (0.90 + 0.18 * wear)[..., None]
    base = (base * 255).clip(0, 255).astype(np.uint8)

    nrm = normal_from_height(h, strength=1.0)
    rough = np.clip(0.62 + 0.16 * (1.0 - h) + 0.06 * wear, 0, 1)
    orm = np.zeros((TEX, TEX, 3), np.uint8)
    orm[..., 0] = 255
    orm[..., 1] = (rough * 255).astype(np.uint8)
    orm[..., 2] = 0
    return base, nrm, orm


def wool_maps():
    h = cloth_map(TEX, seed=21, fiber=1.3)
    base = np.zeros((TEX, TEX, 3), np.float32)
    tone = 0.72 + 0.28 * h
    base[..., 0] = 0.132 * tone
    base[..., 1] = 0.108 * tone
    base[..., 2] = 0.086 * tone
    nrm = normal_from_height(h, strength=1.3)
    rough = np.clip(0.78 + 0.12 * (1.0 - h), 0, 1)
    orm = np.zeros((TEX, TEX, 3), np.uint8)
    orm[..., 0] = 255
    orm[..., 1] = (rough * 255).astype(np.uint8)
    orm[..., 2] = 0
    return base, nrm, orm


def leather_maps():
    """Cuoio della staffa e della cintura.

    Nel disegno il nastro che scende dall'anello e' piu' chiaro della lana
    degli scialli: un cuoio bruno medio, quasi senza trama, con una grana
    fine. Modellarlo con la lana scura lo faceva sparire contro i veli.
    """
    h = cloth_map(TEX, seed=61, fiber=0.75)
    big = fbm(TEX, base_cells=5, octaves=4, seed=91)
    base = np.zeros((TEX, TEX, 3), np.float32)
    tone = 0.82 + 0.18 * h
    base[..., 0] = 0.292 * tone
    base[..., 1] = 0.208 * tone
    base[..., 2] = 0.156 * tone
    base *= (0.92 + 0.14 * big)[..., None]
    base = (base * 255).clip(0, 255).astype(np.uint8)
    nrm = normal_from_height(h * 0.7 + 0.3 * big, strength=1.1)
    rough = np.clip(0.56 + 0.10 * (1.0 - h) + 0.05 * big, 0, 1)
    orm = np.zeros((TEX, TEX, 3), np.uint8)
    orm[..., 0] = 255
    orm[..., 1] = (rough * 255).astype(np.uint8)
    orm[..., 2] = 0
    return base, nrm, orm


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    src = os.path.join(work_dir(), "opt", "DRESS1_opt.blend")
    out = ensure_dir(os.path.join(work_dir(), "mat"))
    bpy.ops.wm.open_mainfile(filepath=src)
    ob = bpy.data.objects["DRESS1"]
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"

    # AO: si cuoce sulla UV dell'oggetto intero, poi si riusa per tutti i
    # materiali (la mappa e' nello spazio UV del capo, non del singolo pezzo)
    print("[mat] bake AO...")
    if sc.world is None:
        w = bpy.data.worlds.new("W")
        sc.world = w
        w.use_nodes = True
    sc.world.light_settings.distance = 0.30
    ao_resolution = int(os.environ.get("DRESS1_AO_SIZE", "1024"))
    ao_samples = int(os.environ.get("DRESS1_AO_SAMPLES", "32"))
    ao_img = bake_ao(ob, resolution=ao_resolution, samples=ao_samples,
                     distance=0.30)
    print(f"[mat] AO ok ({ao_resolution}px, {ao_samples} samples)")

    base, nrm, orm = linen_maps()
    linen_base = image_from_array("DRESS1_Linen_BaseColor", base, "sRGB")
    linen_nrm = image_from_array("DRESS1_Linen_Normal", nrm, "Non-Color")
    linen_orm = image_from_array("DRESS1_Linen_ORM", orm, "Non-Color")

    wbase, wnrm, worm = wool_maps()
    wool_base = image_from_array("DRESS1_Wool_BaseColor", wbase, "sRGB")
    wool_nrm = image_from_array("DRESS1_Wool_Normal", wnrm, "Non-Color")
    wool_orm = image_from_array("DRESS1_Wool_ORM", worm, "Non-Color")

    lbase, lnrm, lorm = leather_maps()
    leather_base = image_from_array("DRESS1_Leather_BaseColor", lbase, "sRGB")
    leather_nrm = image_from_array("DRESS1_Leather_Normal", lnrm, "Non-Color")
    leather_orm = image_from_array("DRESS1_Leather_ORM", lorm, "Non-Color")

    mats = {}
    mats["DRESS1_Linen"] = make_material(
        "DRESS1_Linen", linen_base, linen_orm, linen_nrm, ao_img=ao_img,
        normal_strength=0.9, double_sided=True)
    mats["DRESS1_Wool"] = make_material(
        "DRESS1_Wool", wool_base, wool_orm, wool_nrm, ao_img=ao_img,
        normal_strength=1.2, double_sided=True)
    mats["DRESS1_Leather"] = make_material(
        "DRESS1_Leather", leather_base, leather_orm, leather_nrm,
        ao_img=ao_img, normal_strength=1.1, double_sided=True)
    mats["DRESS1_Gold"] = make_brass_material("DRESS1_Gold")
    mats["DRESS1_GoldTrim"] = make_trim_material("DRESS1_GoldTrim")

    # rimappa gli slot esistenti sui materiali nuovi
    for slot in ob.material_slots:
        old = slot.material.name if slot.material else ""
        new = mats.get(old)
        if new is None:
            if "Wool" in old:
                new = mats["DRESS1_Wool"]
            elif "Leather" in old:
                new = mats["DRESS1_Leather"]
            elif "GoldTrim" in old:
                new = mats["DRESS1_GoldTrim"]
            elif "Gold" in old:
                new = mats["DRESS1_Gold"]
            else:
                new = mats["DRESS1_Linen"]
        slot.material = new

    print("[mat] slot finali:", [s.material.name for s in ob.material_slots])
    path = os.path.join(out, "DRESS1_mat.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("[mat] salvato", path)




if __name__ == "__main__":
    main()
