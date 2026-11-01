# QA DRESS1

Generato da `tools/06_validate.py` (parser glTF senza Blender).

| file | tris | verts | materiali | mappe | MB | doppia faccia |
|---|---|---|---|---|---|---|
| `DRESS1.glb` | 79224 | 66367 | 4 | 6 | 8.71 | si |
| `DRESS1_LOD1.glb` | 31757 | 31991 | 4 | 6 | 2.95 | si |
| `DRESS1_LOD2.glb` | 11408 | 14222 | 4 | 6 | 1.02 | si |

## Controlli

- [x] scala metrica (altezza 0,9-1,5 m) — 0.964 m
- [x] origine a terra, sotto l'orlo (orlo 0,10-0,30 m) — orlo a 120 mm
- [x] centrato sull'asse X (|x| < 20 mm) — -0.6 mm
- [x] budget LOD0 (massimo 80.000 triangoli) — 79224
- [x] quattro materiali — 4
- [x] vertici finiti e UV/normali presenti in tutti i LOD — verificato
- [x] texture incorporate in tutti i LOD — GLB autonomi
- [x] nessuna mappa emissive — assente
- [x] LOD progressivamente piu' leggeri — 79224 > 31757 > 11408
- [x] stessi materiali in tutti i LOD — ok
- [x] doppia faccia sui materiali di stoffa — DRESS1_Linen, DRESS1_Wool
- [x] nessuna animazione o skin (asset statico) — 0 clip, 0 skin
- [x] nessuna estensione glTF richiesta — nessuna
- [x] base color, normal, ORM e AO sulle superfici PBR — 2 materiali testurizzati

## Materiali

| materiale | baseColor | metallicRoughness | normal | occlusion | doubleSided |
|---|---|---|---|---|---|
| `DRESS1_Linen` | si | si | si | si | si |
| `DRESS1_Wool` | si | si | si | si | si |
| `DRESS1_GoldTrim` | colore + factor | valori | — | — | no |
| `DRESS1_Gold` | colore + factor | valori | — | — | no |

## Quote

- altezza totale: **96.4 cm**
- larghezza (X): **55.6 cm**
- profondita' (Z glTF): **47.4 cm**
- estensioni usate: nessuna
