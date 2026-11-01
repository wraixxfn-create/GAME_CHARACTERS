# QA DRESS1

Generato da `tools/06_validate.py` (parser glTF senza Blender).

| file | tris | verts | materiali | mappe | MB | doppia faccia |
|---|---|---|---|---|---|---|
| `DRESS1.glb` | 79223 | 59846 | 4 | 6 | 8.48 | si |
| `DRESS1_LOD1.glb` | 31756 | 28231 | 4 | 6 | 2.83 | si |
| `DRESS1_LOD2.glb` | 11402 | 12593 | 4 | 6 | 0.97 | si |

## Controlli

- [x] scala metrica (altezza 0,9-1,5 m) — 0.960 m
- [x] origine a terra, sotto l'orlo (orlo 0,10-0,30 m) — orlo a 124 mm
- [x] centrato sull'asse X (|x| < 20 mm) — -2.8 mm
- [x] budget LOD0 (massimo 80.000 triangoli) — 79223
- [x] quattro materiali — 4
- [x] vertici finiti e UV/normali presenti in tutti i LOD — verificato
- [x] texture incorporate in tutti i LOD — GLB autonomi
- [x] nessuna mappa emissive — assente
- [x] LOD progressivamente piu' leggeri — 79223 > 31756 > 11402
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

- altezza totale: **96.0 cm**
- larghezza (X): **56.1 cm**
- profondita' (Z glTF): **48.0 cm**
- estensioni usate: nessuna
