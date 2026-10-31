# QA DRESS1

Generato da `tools/06_validate.py` (parser glTF senza Blender).

| file | tris | verts | materiali | mappe | MB | doppia faccia |
|---|---|---|---|---|---|---|
| `DRESS1.glb` | 77999 | 62197 | 6 | 12 | 14.12 | si |
| `DRESS1_LOD1.glb` | 28737 | 29323 | 6 | 12 | 4.50 | si |
| `DRESS1_LOD2.glb` | 10135 | 12349 | 6 | 12 | 1.43 | si |

## Controlli

- [x] scala metrica (altezza 0,9-1,5 m) — 1.078 m
- [x] origine ai piedi (min |y| < 8 mm) — +0.8 mm
- [x] centrato sull'asse X (|x| < 20 mm) — +3.1 mm
- [x] budget LOD0 (massimo 80.000 triangoli) — 77999
- [x] sei materiali — 6
- [x] vertici finiti e UV/normali presenti in tutti i LOD — verificato
- [x] texture incorporate in tutti i LOD — GLB autonomi
- [x] nessuna mappa emissive — assente
- [x] LOD progressivamente piu' leggeri — 77999 > 28737 > 10135
- [x] stessi materiali in tutti i LOD — ok
- [x] doppia faccia sui materiali di stoffa — DRESS1_Canvas, DRESS1_Linen, DRESS1_Wool
- [x] nessuna animazione o skin (asset statico) — 0 clip, 0 skin
- [x] nessuna estensione glTF richiesta — nessuna
- [x] base color, normal, ORM e AO sulle superfici PBR — 4 materiali testurizzati

## Materiali

| materiale | baseColor | metallicRoughness | normal | occlusion | doubleSided |
|---|---|---|---|---|---|
| `DRESS1_Skin` | si | si | si | si | no |
| `DRESS1_Canvas` | si | si | si | si | si |
| `DRESS1_Wool` | si | si | si | si | si |
| `DRESS1_GoldTrim` | colore + factor | valori | — | — | no |
| `DRESS1_Linen` | si | si | si | si | si |
| `DRESS1_Gold` | colore + factor | valori | — | — | no |

## Quote

- altezza totale: **107.8 cm**
- larghezza (X): **54.7 cm**
- profondita' (Z glTF): **47.0 cm**
- estensioni usate: nessuna
