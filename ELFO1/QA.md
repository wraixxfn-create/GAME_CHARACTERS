# QA ELFO1

Generato da `tools/07_validate.py`.

| file | tris | verts | joint | clip | durate | MB | doubleSided | esito |
|---|---|---|---|---|---|---|---|---|
| `ELFO1.glb` | 55000 | 40408 | 43 | 5 | 2.40s, 3.00s, 4.00s, 0.80s, 1.20s | 3.70 | si | OK |
| `ELFO1_LOD1.glb` | 19250 | 18610 | 43 | 5 | 2.40s, 3.00s, 4.00s, 0.80s, 1.20s | 2.35 | si | OK |
| `ELFO1_LOD2.glb` | 6600 | 8678 | 43 | 5 | 2.40s, 3.00s, 4.00s, 0.80s, 1.20s | 1.76 | si | OK |

## Controlli

- [x] scala metrica (altezza 1,4-2,2 m)
- [x] massimo 4 influenze per vertice, pesi normalizzati
- [x] 5 clip di animazione in ogni LOD
- [x] loop chiusi su `Idle`, `Walk` e `Run` (primo = ultimo keyframe)
- [x] baseColor + metallicRoughness + occlusion + normal + emissive
- [x] materiale double-sided (gonnellone e ciocche sono fogli aperti)

## Sanita' delle animazioni (misurata da `03_animate.py`)

- [x] ginocchia: in flessione il tallone va *dietro* (niente passo dell'oca)
- [x] `Walk`: appoggio a terra sul 100% dei frame, scarto verticale max 0.0 mm
- [x] `Run`: appoggio sul 100% dei frame di stance, volo di 14.1 cm
- [x] `Idle`: nessun piede sotto il pavimento (scarto max 0.0 mm)
- [x] `Cast`: nessun piede sotto il pavimento (scarto max 0.0 mm)
- [x] `Death`: nessun piede sotto il pavimento (scarto max 0.0 mm)
- [x] `Cast`: alla spinta le mani sono davanti al petto (mani y=-0.3878 vs petto y=-0.1229)
- [x] `Death`: corpo appoggiato a terra (testa a 0.1656 m, minimo finale 0.0 m)
- [x] tutti i check interni di `03_animate.py` superati
