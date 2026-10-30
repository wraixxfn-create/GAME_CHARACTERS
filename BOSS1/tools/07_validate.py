"""Step 7 - Validazione dei file esportati.

Non usa Blender: legge direttamente i `.glb` (contenitore glTF binario) e
controlla quello che serve sapere prima di consegnare un asset a un motore:

  * triangoli e vertici per ogni LOD
  * skin: numero di joint e **influenze per vertice** (max 4, somma = 1)
  * clip di animazione: nomi, durata in secondi, numero di canali
  * loop: per `Idle` e `Walk` il primo e l'ultimo keyframe devono coincidere
  * texture: dimensioni, formato e se i canali PBR ci sono tutti
    (baseColor, metallicRoughness, occlusion, normal, emissive)
  * altezza del modello in metri (dal min/max delle POSITION, con l'asse Y-up
    del glTF)

Scrive un riepilogo in `BOSS1/QA.md` e termina con codice != 0 se qualcosa non
torna (utile in CI).

Uso: python3 07_validate.py [cartella BOSS1]
"""
import json
import os
import struct
import sys

import numpy as np

HERE = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["BOSS1.glb", "BOSS1_LOD1.glb", "BOSS1_LOD2.glb"]
CHANNELS = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2), 5123: ('H', 2),
            5125: ('I', 4), 5126: ('f', 4)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    data = open(path, 'rb').read()
    magic, version, length = struct.unpack('<III', data[:12])
    assert magic == 0x46546C67, f"{path}: non e' un GLB"
    off, js, bin_chunk = 12, None, b""
    while off < length:
        clen, ctype = struct.unpack('<II', data[off:off + 8])
        off += 8
        chunk = data[off:off + clen]
        off += clen
        if ctype == 0x4E4F534A:
            js = json.loads(chunk.decode('utf-8'))
        elif ctype == 0x004E4942:
            bin_chunk = chunk
    return js, bin_chunk, len(data)


def accessor(js, binary, idx):
    acc = js['accessors'][idx]
    bv = js['bufferViews'][acc['bufferView']]
    fmt, size = CHANNELS[acc['componentType']]
    n = NCOMP[acc['type']]
    start = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
    count = acc['count']
    stride = bv.get('byteStride') or size * n
    if stride == size * n:
        raw = binary[start:start + count * stride]
        arr = np.frombuffer(raw, dtype=np.dtype(fmt))
        return arr.reshape(count, n) if n > 1 else arr
    out = np.zeros((count, n), dtype=np.dtype(fmt))
    for i in range(count):
        off = start + i * stride
        out[i] = np.frombuffer(binary[off:off + size * n], dtype=np.dtype(fmt))
    return out


def image_size(js, binary, idx):
    img = js['images'][idx]
    if 'bufferView' not in img:
        return (0, 0), img.get('mimeType', '?')
    bv = js['bufferViews'][img['bufferView']]
    blob = binary[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]
    mime = img.get('mimeType', 'image/jpeg')
    if blob[:8] == b'\x89PNG\r\n\x1a\n':
        w, h = struct.unpack('>II', blob[16:24])
        return (w, h), 'image/png'
    if blob[:2] == b'\xff\xd8':
        i = 2
        while i < len(blob) - 9:
            if blob[i] != 0xFF:
                i += 1
                continue
            marker = blob[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack('>HH', blob[i + 5:i + 9])
                return (w, h), 'image/jpeg'
            seg = struct.unpack('>H', blob[i + 2:i + 4])[0]
            i += 2 + seg
    return (0, 0), mime


def check_file(path, report):
    js, binary, size = read_glb(path)
    name = os.path.basename(path)
    print(f"\n=== {name} ({size / 1e6:.2f} MB)")
    errs = []

    # ---- mesh
    tris = verts = 0
    for mesh in js.get('meshes', []):
        for prim in mesh['primitives']:
            tris += js['accessors'][prim['indices']]['count'] // 3
            verts += js['accessors'][prim['attributes']['POSITION']]['count']
    pos = accessor(js, binary, js['meshes'][0]['primitives'][0]['attributes']['POSITION'])
    ext = pos.max(axis=0) - pos.min(axis=0)
    print(f"  mesh: {tris} tris, {verts} verts, {len(js['meshes'][0]['primitives'])} primitiva/e")
    print(f"  dimensioni (Y-up glTF): X={ext[0]:.2f}  Y={ext[1]:.2f} (altezza)  Z={ext[2]:.2f} m")
    if not (2.0 <= ext[1] <= 4.0):
        errs.append(f"altezza fuori scala: {ext[1]:.2f} m")

    # ---- skin
    joints = len(js['skins'][0]['joints']) if js.get('skins') else 0
    print(f"  skin: {len(js.get('skins', []))} skin, {joints} joint")
    prim = js['meshes'][0]['primitives'][0]
    if 'WEIGHTS_0' in prim['attributes']:
        w = accessor(js, binary, prim['attributes']['WEIGHTS_0']).astype(np.float64)
        sums = w.sum(axis=1)
        influences = (w > 1e-4).sum(axis=1)
        print(f"  pesi: somma min={sums.min():.4f} max={sums.max():.4f}; "
              f"influenze max={influences.max()} media={influences.mean():.2f}")
        if influences.max() > 4:
            errs.append(f"{influences.max()} influenze per vertice (max 4)")
        if abs(sums.min() - 1) > 0.01 or abs(sums.max() - 1) > 0.01:
            errs.append("pesi non normalizzati")
    else:
        errs.append("nessun WEIGHTS_0")

    # ---- animazioni
    anims = []
    for anim in js.get('animations', []):
        dur = 0.0
        for sampler in anim['samplers']:
            t = accessor(js, binary, sampler['input'])
            dur = max(dur, float(np.max(t)))
        loops = anim.get('name', '').split('_')[-1] in ("Idle", "Walk")
        ok = None
        if loops:
            ok = True
            for ch in anim['channels']:
                s = anim['samplers'][ch['sampler']]
                out = accessor(js, binary, s['output']).astype(np.float64)
                if out.ndim == 1:
                    out = out[:, None]
                if not np.allclose(out[0], out[-1], atol=2e-3):
                    ok = False
        anims.append((anim.get('name', '?'), dur, len(anim['channels']), loops, ok))
    for nm, dur, nch, loops, ok in anims:
        flag = "" if ok is None else (" loop OK" if ok else " LOOP ROTTO")
        print(f"  clip {nm:14s} {dur:5.2f}s  {nch:3d} canali{flag}")
        if ok is False:
            errs.append(f"loop non chiuso in {nm}")
    if len(anims) < 5:
        errs.append(f"solo {len(anims)} clip")

    # ---- materiali e texture
    mat = js['materials'][0]
    pbr = mat.get('pbrMetallicRoughness', {})
    have = {
        'baseColor': 'baseColorTexture' in pbr,
        'metallicRoughness': 'metallicRoughnessTexture' in pbr,
        'occlusion': 'occlusionTexture' in mat,
        'normal': 'normalTexture' in mat,
        'emissive': 'emissiveTexture' in mat,
    }
    print("  canali PBR: " + ", ".join(
        "%s=%s" % (k, "si" if v else "NO") for k, v in have.items()))
    for k, v in have.items():
        if not v:
            errs.append(f"texture mancante: {k}")
    tex_idx = set()
    for tex in (pbr.get('baseColorTexture'), pbr.get('metallicRoughnessTexture'),
                mat.get('occlusionTexture'), mat.get('normalTexture'),
                mat.get('emissiveTexture')):
        if tex:
            tex_idx.add(tex['index'])
    for ti in sorted(tex_idx):
        src = js['textures'][ti]['source']
        (w, h), mime = image_size(js, binary, src)
        print(f"  texture[{ti}] {js['images'][src].get('name', '?'):16s} {w}x{h} {mime.split('/')[-1]}")
        if max(w, h) > 4096:
            errs.append("texture oltre 4K")
    if mat.get('doubleSided'):
        print("  nota: materiale double-sided")

    report.append((name, tris, verts, joints, len(anims),
                   ", ".join(f"{d:.2f}s" for _, d, _, _, _ in anims),
                   size / 1e6, errs))
    return errs


def main():
    report = []
    all_errs = []
    for f in FILES:
        path = os.path.join(HERE, f)
        if not os.path.exists(path):
            print(f"MANCA {path}")
            all_errs.append(f"{f} mancante")
            continue
        all_errs += check_file(path, report)

    # .blend e .fbx
    for f in ("BOSS1.blend", "BOSS1.fbx"):
        path = os.path.join(HERE, f)
        ok = os.path.exists(path)
        print(f"{'OK  ' if ok else 'MANCA'} {f} "
              f"({os.path.getsize(path) / 1e6:.2f} MB)" if ok else f"MANCA {f}")
        if not ok:
            all_errs.append(f"{f} mancante")

    lines = ["# QA BOSS1", "",
             "Generato da `tools/07_validate.py`.", "",
             "| file | tris | verts | joint | clip | durate | MB | esito |",
             "|---|---|---|---|---|---|---|---|"]
    for name, tris, verts, joints, nclip, durs, mb, errs in report:
        lines.append(f"| `{name}` | {tris} | {verts} | {joints} | {nclip} | "
                     f"{durs} | {mb:.2f} | {'OK' if not errs else '; '.join(errs)} |")
    lines += ["", "## Controlli", "",
              "- [x] scala metrica (altezza 2,0-4,0 m)",
              "- [x] massimo 4 influenze per vertice, pesi normalizzati",
              "- [x] 5 clip di animazione per LOD",
              "- [x] loop chiusi su Idle e Walk (primo keyframe = ultimo)",
              "- [x] baseColor + metallicRoughness + occlusion + normal + emissive",
              ""]
    if all_errs:
        lines += ["## Problemi", ""] + [f"- {e}" for e in all_errs] + [""]
    out = os.path.join(HERE, "QA.md")
    open(out, "w").write("\n".join(lines))
    print("\nQA:", out)
    if all_errs:
        print("PROBLEMI:", all_errs)
        sys.exit(1)
    print("TUTTO OK")


if __name__ == "__main__":
    main()
