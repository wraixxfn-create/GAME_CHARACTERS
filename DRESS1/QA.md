# QA DRESS1

Generato da `tools/06_validate.py` (parser glTF senza Blender).

| file | tris | verts | materiali | mappe | MB | doppia faccia |
|---|---|---|---|---|---|---|
| `DRESS1.glb` | 79224 | 58565 | 5 | 9 | 11.12 | si |
| `DRESS1_LOD1.glb` | 31758 | 27586 | 5 | 9 | 3.54 | si |
| `DRESS1_LOD2.glb` | 11406 | 12355 | 5 | 9 | 1.17 | si |

## Controlli

- [x] scala metrica (altezza 0,9-1,5 m) — 0.933 m
- [x] origine a terra, sotto l'orlo (orlo 0,10-0,30 m) — orlo a 150 mm
- [x] centrato sull'asse X (|x| < 20 mm) — -2.2 mm
- [x] budget LOD0 (massimo 80.000 triangoli) — 79224
- [x] cinque materiali — 5
- [x] vertici finiti e UV/normali presenti in tutti i LOD — verificato
- [x] texture incorporate in tutti i LOD — GLB autonomi
- [x] nessuna mappa emissive — assente
- [x] LOD progressivamente piu' leggeri — 79224 > 31758 > 11406
- [x] stessi materiali in tutti i LOD — ok
- [x] doppia faccia sui materiali di stoffa — DRESS1_Leather, DRESS1_Linen, DRESS1_Wool
- [x] nessuna animazione o skin (asset statico) — 0 clip, 0 skin
- [x] nessuna estensione glTF richiesta — nessuna
- [x] base color, normal, ORM e AO sulle superfici PBR — 3 materiali testurizzati

## Materiali

| materiale | baseColor | metallicRoughness | normal | occlusion | doubleSided |
|---|---|---|---|---|---|
| `DRESS1_Linen` | si | si | si | si | si |
| `DRESS1_Wool` | si | si | si | si | si |
| `DRESS1_Leather` | si | si | si | si | si |
| `DRESS1_GoldTrim` | colore + factor | valori | — | — | no |
| `DRESS1_Gold` | colore + factor | valori | — | — | no |

## Quote

- altezza totale: **93.3 cm**
- larghezza (X): **60.2 cm**
- profondita' (Z glTF): **51.2 cm**
- estensioni usate: nessuna
