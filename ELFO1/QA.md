# QA ELFO1

Generato da `tools/07_validate.py`.

| file | tris | verts | joint | clip | durate | MB | doubleSided | esito |
|---|---|---|---|---|---|---|---|---|
| `ELFO1.glb` | 55000 | 40408 | 43 | 5 | 2.40s, 3.00s, 4.00s, 0.80s, 1.20s | 3.75 | si | OK |
| `ELFO1_LOD1.glb` | 19250 | 18610 | 43 | 5 | 2.40s, 3.00s, 4.00s, 0.80s, 1.20s | 2.40 | si | OK |
| `ELFO1_LOD2.glb` | 6600 | 8678 | 43 | 5 | 2.40s, 3.00s, 4.00s, 0.80s, 1.20s | 1.81 | si | OK |

## Controlli

- [x] scala metrica (altezza 1,4-2,2 m)
- [x] massimo 4 influenze per vertice, pesi normalizzati
- [x] 5 clip di animazione in ogni LOD
- [x] loop chiusi su `Idle`, `Walk` e `Run` (primo = ultimo keyframe)
- [x] baseColor + metallicRoughness + occlusion + normal + emissive
- [x] materiale double-sided (gonnellone e ciocche sono fogli aperti)

## Sanita' delle animazioni (misurata da `03_animate.py`)

- [x] direzione del ginocchio: in flessione il tallone va *dietro* (niente 'passo dell'oca')
- [x] `Walk`: contatto piede-terra su 100% dei frame campionati (ogni frame)
- [x] `Run`: contatto piede-terra su 50% dei frame campionati (>= meta' frame (volo))
- [x] `Cast`: al frame della spinta le mani sono davanti al petto (non dietro la schiena)
- [x] `Death`: posa finale appoggiata a terra (testa a 0.22 unita' sorgente, grounding su 5 frame chiave)
