# QA DRESS1

Generato da `tools/06_validate.py` (parser glTF senza Blender).

| file | tris | verts | materiali | mappe | MB | doppia faccia |
|---|---|---|---|---|---|---|
| `DRESS1.glb` | 78000 | 68592 | 6 | 12 | 11.70 | si |
| `DRESS1_LOD1.glb` | 27298 | 29664 | 6 | 12 | 3.82 | si |
| `DRESS1_LOD2.glb` | 9351 | 12349 | 6 | 12 | 1.23 | si |

## Controlli

- [x] scala metrica (altezza 0,9-1,5 m) — 1.089 m
- [x] origine ai piedi (min |y| < 8 mm) — -3.0 mm
- [x] centrato sull'asse X (|x| < 20 mm) — -0.4 mm
- [x] massimo 6 materiali — 6
- [x] nessuna mappa emissive — assente
- [x] loop di indipendenza (nessuna skin) — 0 skin
- [x] LOD1/LOD2 piu' leggeri del LOD0 — 78000 27298 9351
- [x] stessi materiali in tutti i LOD — ok
- [x] doppia faccia solo su stoffa e pelle — DRESS1_Canvas, DRESS1_Wool, DRESS1_Linen, DRESS1_Gold
- [x] nessuna animazione/skin (asset statico) — 0 clip

## Materiali

| materiale | baseColor | metallicRoughness | normal | occlusion | doubleSided |
|---|---|---|---|---|---|
| `DRESS1_Skin` | si | si | si | si | no |
| `DRESS1_Canvas` | si | si | si | si | si |
| `DRESS1_Wool` | si | si | si | si | si |
| `DRESS1_GoldTrim` | colore + factor | valori | — | — | no |
| `DRESS1_Linen` | si | si | si | si | si |
| `DRESS1_Gold` | colore + factor | valori | — | — | si |

## Quote

- altezza totale: **108.9 cm**
- larghezza (X): **54.5 cm**
- profondita' (Z glTF): **48.4 cm**
- estensioni usate: nessuna
