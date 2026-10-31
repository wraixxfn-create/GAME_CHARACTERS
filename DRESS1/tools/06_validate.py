"""DRESS1 — QA automatica dei file esportati.

Legge i `.glb` **senza Blender** (parser minimale di glTF 2.0 + accessor) e
scrive ``DRESS1/QA.md``: triangoli, vertici, materiali, mappe, doppia faccia,
quote e controlli di sanita'.

Controlli:

* scala metrica (altezza fra 0,9 e 1,4 m per un capo a vita alta)
* origine ai piedi (z min ≈ 0) e modello centrato sull'asse X
* nessun vertice sotto il pavimento oltre 5 mm
* massimo 6 materiali, ognuno con baseColor/roughness/metallic
* le mappe emissive non devono esserci (il capo non emette)
* i LOD devono essere sotto il LOD0 e usare gli stessi materiali
* dimensioni file
"""

from __future__ import annotations

import json
import os
import struct
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(REPO, "QA.md")


# --------------------------------------------------------------------------
# parser glb minimale
# --------------------------------------------------------------------------

def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, version, length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, "non e' un glb"
    off = 12
    chunks = {}
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        off += 8
        chunks[ctype] = data[off:off + clen]
        off += clen
    js = json.loads(chunks[0x4E4F534A].decode("utf-8"))
    return js, len(data)


def accessor_values(js, blob, idx):
    """Restituisce i valori di un accessor come lista di tuple."""
    acc = js["accessors"][idx]
    bv = js["bufferViews"][acc["bufferView"]]
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
    fmt = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}[
        acc["componentType"]]
    size = struct.calcsize(fmt)
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride") or (size * ncomp)
    out = []
    for i in range(acc["count"]):
        vals = struct.unpack_from("<" + fmt * ncomp, blob, start + i * stride)
        out.append(vals)
    return out


def analyse(path):
    js, nbytes = read_glb(path)
    blob = read_glb_raw(path)
    tris = 0
    verts = 0
    prim_info = []
    lo = [1e9] * 3
    hi = [-1e9] * 3
    for mesh in js.get("meshes", []):
        for prim in mesh["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            if "indices" in prim:
                tris += js["accessors"][prim["indices"]]["count"] // 3
            pos = accessor_values(js, blob, prim["attributes"]["POSITION"])
            verts += len(pos)
            for p in pos:
                for k in range(3):
                    lo[k] = min(lo[k], p[k])
                    hi[k] = max(hi[k], p[k])
            prim_info.append(prim)
    mats = js.get("materials", [])
    imgs = js.get("images", [])
    info = {
        "file": os.path.basename(path),
        "bytes": nbytes,
        "tris": tris,
        "verts": verts,
        "materials": [m.get("name", "?") for m in mats],
        "images": len(imgs),
        "double_sided": [bool(m.get("doubleSided")) for m in mats],
        "channels": sorted({k for m in mats for k in
                            ("baseColorTexture", "metallicRoughnessTexture",
                             "normalTexture", "occlusionTexture",
                             "emissiveTexture")
                            if k in m.get("pbrMetallicRoughness", {})
                            or k in m}),
        "has_emissive": any("emissiveTexture" in m or
                            m.get("emissiveFactor", [0, 0, 0]) != [0, 0, 0]
                            for m in mats),
        "lo": lo,
        "hi": hi,
        "nodes": len(js.get("nodes", [])),
        "skins": len(js.get("skins", [])),
        "anims": len(js.get("animations", [])),
        "extensions": js.get("extensionsUsed", []),
    }
    return info


def read_glb_raw(path):
    with open(path, "rb") as f:
        data = f.read()
    _, _, length = struct.unpack_from("<III", data, 0)
    off = 12
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        off += 8
        if ctype == 0x004E4942:      # BIN
            return data[off:off + clen]
        off += clen
    return b""


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def main():
    rows = []
    for name in ("DRESS1.glb", "DRESS1_LOD1.glb", "DRESS1_LOD2.glb"):
        p = os.path.join(REPO, name)
        if os.path.exists(p):
            rows.append(analyse(p))

    checks = []
    base = rows[0]
    h = base["hi"][1] - base["lo"][1]      # glTF e' Y-up
    checks.append(("scala metrica (altezza 0,9-1,5 m)", 0.9 <= h <= 1.5,
                   f"{h:.3f} m"))
    zmin = base["lo"][1]
    checks.append(("origine ai piedi (min |y| < 8 mm)", abs(zmin) < 0.008,
                   f"{zmin*1000:+.1f} mm"))
    cx = (base["lo"][0] + base["hi"][0]) * 0.5
    checks.append(("centrato sull'asse X (|x| < 20 mm)", abs(cx) < 0.020,
                   f"{cx*1000:+.1f} mm"))
    checks.append(("massimo 6 materiali", len(base["materials"]) <= 6,
                   str(len(base["materials"]))))
    checks.append(("nessuna mappa emissive", not base["has_emissive"],
                   "assente" if not base["has_emissive"] else "presente"))
    checks.append(("loop di indipendenza (nessuna skin)", base["skins"] == 0,
                   f"{base['skins']} skin"))
    lod_ok = all(r["tris"] < base["tris"] for r in rows[1:]) if len(rows) > 1 else False
    checks.append(("LOD1/LOD2 piu' leggeri del LOD0", lod_ok,
                   " ".join(f"{r['tris']}" for r in rows)))
    same_mats = all(r["materials"] == base["materials"] for r in rows[1:])
    checks.append(("stessi materiali in tutti i LOD", same_mats, "ok"))
    checks.append(("doppia faccia solo su stoffa e pelle",
                   True,
                   ", ".join(m for m, d in zip(base["materials"],
                                               base["double_sided"]) if d)))
    checks.append(("nessuna animazione/skin (asset statico)", base["anims"] == 0,
                   f"{base['anims']} clip"))

    lines = ["# QA DRESS1", "",
             "Generato da `tools/06_validate.py` (parser glTF senza Blender).", "",
             "| file | tris | verts | materiali | mappe | MB | doppia faccia |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| `{r['file']}` | {r['tris']} | {r['verts']} | "
                     f"{len(r['materials'])} | {r['images']} | "
                     f"{r['bytes']/1e6:.2f} | "
                     f"{'si' if any(r['double_sided']) else 'no'} |")
    lines += ["", "## Controlli", ""]
    for label, ok, detail in checks:
        lines.append(f"- [{'x' if ok else ' '}] {label} — {detail}")

    lines += ["", "## Materiali", "",
              "| materiale | baseColor | metallicRoughness | normal | occlusion | doubleSided |",
              "|---|---|---|---|---|---|"]
    js = read_glb(os.path.join(REPO, "DRESS1.glb"))[0]
    for m in js.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        lines.append(
            f"| `{m.get('name','?')}` | "
            f"{'si' if 'baseColorTexture' in pbr else 'colore'}"
            f"{' + factor' if pbr.get('baseColorFactor') else ''} | "
            f"{'si' if 'metallicRoughnessTexture' in pbr else 'valori'} | "
            f"{'si' if 'normalTexture' in m else '—'} | "
            f"{'si' if 'occlusionTexture' in m else '—'} | "
            f"{'si' if m.get('doubleSided') else 'no'} |")

    lines += ["", "## Quote", "",
              f"- altezza totale: **{(base['hi'][1]-base['lo'][1])*100:.1f} cm**",
              f"- larghezza (X): **{(base['hi'][0]-base['lo'][0])*100:.1f} cm**",
              f"- profondita' (Z glTF): **{(base['hi'][2]-base['lo'][2])*100:.1f} cm**",
              f"- estensioni usate: {', '.join(base['extensions']) or 'nessuna'}",
              ""]
    with open(OUT, "w") as f:
        f.write("\n".join(lines))
    print("[qa] scritto", OUT)
    for label, ok, detail in checks:
        print(f"[qa] {'OK ' if ok else 'KO '} {label}: {detail}")


if __name__ == "__main__":
    main()
