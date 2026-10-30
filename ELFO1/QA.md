# QA ELFO1

Generato da `tools/07_validate.py`.

| file | tris | verts | joint | clip | durate | MB | doubleSided | esito |
|---|---|---|---|---|---|---|---|---|
| `ELFO1.glb` | 55000 | 40408 | 43 | 5 | 2.40s, 3.00s, 4.00s, 0.80s, 1.20s | 3.72 | si | OK |
| `ELFO1_LOD1.glb` | 19250 | 18610 | 43 | 5 | 2.40s, 3.00s, 4.00s, 0.80s, 1.20s | 2.37 | si | OK |
| `ELFO1_LOD2.glb` | 6600 | 8678 | 43 | 5 | 2.40s, 3.00s, 4.00s, 0.80s, 1.20s | 1.78 | si | OK |

## Controlli

- [x] scala metrica (altezza 1,4-2,2 m)
- [x] massimo 4 influenze per vertice, pesi normalizzati
- [x] 5 clip di animazione in ogni LOD
- [x] loop chiusi su `Idle`, `Walk` e `Run` (primo = ultimo keyframe)
- [x] baseColor + metallicRoughness + occlusion + normal + emissive
- [x] materiale double-sided (gonnellone e ciocche sono fogli aperti)
