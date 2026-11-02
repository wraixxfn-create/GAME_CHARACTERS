# QA DRESS1

Generato da `tools/06_validate.py` (parser glTF senza Blender).

| file | tris | verts | materiali | mappe | MB | doppia faccia |
|---|---|---|---|---|---|---|
| `DRESS1.glb` | 78497 | 61458 | 4 | 6 | 7.80 | si |
| `DRESS1_LOD1.glb` | 29848 | 27922 | 4 | 6 | 2.55 | si |
| `DRESS1_LOD2.glb` | 10608 | 12128 | 4 | 6 | 0.89 | si |

## Controlli

- [x] scala metrica (altezza 0,8-1,1 m) — 0.915 m
- [x] origine a terra, sotto l'orlo (orlo 0,10-0,30 m) — orlo a 139 mm
- [x] centrato sull'asse X (|x| < 20 mm) — +0.1 mm
- [x] budget LOD0 (massimo 80.000 triangoli) — 78497
- [x] quattro materiali — 4
- [x] vertici finiti e UV/normali presenti in tutti i LOD — verificato
- [x] texture incorporate in tutti i LOD — GLB autonomi
- [x] nessuna mappa emissive — assente
- [x] LOD progressivamente piu' leggeri — 78497 > 29848 > 10608
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

- altezza totale: **91.5 cm**
- larghezza (X): **54.6 cm**
- profondita' (Z glTF): **44.3 cm**
- estensioni usate: nessuna
