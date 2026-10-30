# Pipeline BOSS1

Script Blender headless che trasformano il modello grezzo
`ImageToStl.com_monster+3d+model.blend` (500k triangoli, senza rig) in un
personaggio game-ready animato.

## Requisiti

```bash
pip install bpy==5.0.1 pillow numpy scipy
```

Sono usati solo moduli headless di Blender (`bpy` come modulo Python), nessuna
GPU: i render di anteprima girano su Cycles CPU.

## Esecuzione

```bash
cd BOSS1/tools
python3 01_optimize.py    # 500k -> 60k tri, normali pesate
python3 02_rig.py         # armatura 34 ossa + skinning
python3 03_animate.py     # Idle / Roar / Attack
python3 04_material.py    # texture 1K + emissive vene
python3 05_export.py      # BOSS1.blend + BOSS1.glb + BOSS1.fbx
python3 06_preview.py     # render di presentazione (facoltativo)
```

I `.blend` intermedi finiscono in `$BOSS1_WORK` (default `/home/user/work`),
fuori dal repository; solo i file finali vanno in `BOSS1/`.

## Step

| file | cosa fa |
|---|---|
| `01_optimize.py` | sgancia la mesh dagli empty importati (la rotazione sta li), applica le trasformazioni, decimation collapse a 60k tri con UV preservate, Weighted Normal per non perdere gli spigoli delle spine |
| `02_rig.py` | 34 ossa: catena root/hips/spine/chest/neck/head + jaw, aureola a 3 segmenti, coda, braccia a 4 segmenti con 3 artigli, gambe digitigrade a 4 segmenti. Pesi automatici (heat map) + overlay manuale per aureola e coda, limite 4 influenze e normalizzazione |
| `03_animate.py` | 3 azioni a 30 fps: `Idle` 120f (loop), `Roar` 72f, `Attack` 60f |
| `04_material.py` | texture 4096 -> 1024 (JPEG), materiale PBR glTF-safe, mappa emissiva generata dai pixel della basecolor (vene incandescenti) |
| `05_export.py` | rinomina azioni `BOSS1_*`, pack di tutte le texture, export `.blend`, `.glb` (tutte le animazioni) e `.fbx` |
| `06_preview.py` | hero shot + turnaround per la documentazione |

## Landmark anatomici

Ricavati automaticamente dalla geometria (`skeleton_from_geometry`): voxel
fill della mesh a 1.2 cm, distance transform, grafo 26-connesso con costo
inverso al clearance (medial axis) e cammini minimi dal bacino verso mani,
piedi, testa e sommita' dell'aureola. I punti di giunzione delle ossa
(spalla, gomito, polso, anca, ginocchio, tallone) sono presi da quei cammini,
non a occhio.
