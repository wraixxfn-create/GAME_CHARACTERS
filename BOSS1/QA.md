# QA BOSS1

Generato da `tools/07_validate.py`.

| file | tris | verts | joint | clip | durate | MB | esito |
|---|---|---|---|---|---|---|---|
| `BOSS1.glb` | 80000 | 45926 | 34 | 5 | 1.80s, 3.20s, 4.00s, 2.80s, 1.33s | 4.33 | OK |
| `BOSS1_LOD1.glb` | 32000 | 20673 | 34 | 5 | 1.80s, 3.20s, 4.00s, 2.80s, 1.33s | 2.73 | OK |
| `BOSS1_LOD2.glb` | 9600 | 7615 | 34 | 5 | 1.80s, 3.20s, 4.00s, 2.80s, 1.33s | 1.92 | OK |

## Controlli

- [x] scala metrica (altezza 2,0-4,0 m)
- [x] massimo 4 influenze per vertice, pesi normalizzati
- [x] 5 clip di animazione per LOD
- [x] loop chiusi su Idle e Walk (primo keyframe = ultimo)
- [x] baseColor + metallicRoughness + occlusion + normal + emissive
