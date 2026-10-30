# Pipeline BOSS1

Script Blender headless che trasformano il modello grezzo
`ImageToStl.com_monster+3d+model.blend` (501k triangoli, senza rig) in un
personaggio game-ready animato, con LOD e QA automatica.

## Requisiti

```bash
pip install bpy==5.0.1 numpy scipy pillow      # vedi requirements.txt
```

Sono usati solo moduli headless di Blender (`bpy` come modulo Python), nessuna
GPU: i render di anteprima girano su Cycles CPU.

> Su Linux il wheel `bpy` richiede le librerie di sistema di X11/GL anche in
> modalita' headless: `libxrender1 libxi6 libxxf86vm1 libxfixes3 libxext6
> libgl1 libxkbcommon0 libsm6 libice6`.

## Esecuzione

```bash
cd BOSS1/tools
python3 01_optimize.py    # 501k -> 80k tri adattivi, simmetria, normali pesate
python3 02_rig.py         # armatura 34 ossa + skinning geodesico
python3 03_animate.py     # Idle / Walk / Roar / Attack / Death
python3 04_material.py    # texture 2K + AO bakeata + ORM + emissive
python3 05_export.py      # BOSS1.blend/.glb/.fbx + LOD1/LOD2, scala 2,90 m
python3 06_preview.py     # render di presentazione e GIF (facoltativo)
python3 07_validate.py    # QA dei file esportati -> BOSS1/QA.md
```

I `.blend` intermedi finiscono in `$BOSS1_WORK` (default `/home/user/work`),
fuori dal repository; solo i file finali vanno in `BOSS1/`.
L'intera pipeline (1-5) gira in meno di un minuto; i render di anteprima sono
la parte lenta (Cycles CPU).

## Step

| file | cosa fa |
|---|---|
| `01_optimize.py` | sgancia la mesh dagli empty importati, applica le trasformazioni, calcola un **peso di dettaglio per vertice** (curvatura della superficie + boost su testa, aureola, mani e piedi) e decima a 80k triangoli con `DECIMATE` pesato e **simmetria sull'asse X**. Pulisce la mesh dai vertici duplicati, ricalcola le normali (Weighted Normal). |
| `02_rig.py` | 34 ossa: catena root/hips/spine/chest/neck/head + jaw, aureola a 3 segmenti, coda, braccia a 4 segmenti con 3 artigli, gambe digitigrade a 4 segmenti. **Skinning geodesico**: per ogni osso si prendono i vertici di superficie piu' vicini come seed, poi multi-source Dijkstra sullo scheletro di edge della mesh (scipy); peso `1/d^4`, smoothing laplaciano (6 iterazioni), limite a 4 influenze e normalizzazione. Niente bleed tra arti vicini. |
| `03_animate.py` | 5 azioni a 30 fps: `Idle` 120f (loop), `Walk` 40f (loop, in place), `Roar` 84f, `Attack` 54f, `Death` 96f. Le rotazioni sono espresse in **assi mondo** e convertite nello spazio dell'osso (`M_rest⁻¹ · R · M_rest`), con quaternioni e continuita' di segno tra i keyframe. Ogni clip definisce tutte le ossa (niente pose "avanzate" da una clip all'altra). |
| `04_material.py` | basecolor e normal a 2048, ORM a 1024 con **AO bakeata** nel canale rosso, emissive 1024 con vene generate da basecolor + fBm. Materiale opaco, backface culling. |
| `05_export.py` | scala metrica a **2,90 m**, rinomina le azioni `BOSS1_*`, export `.blend` (texture impacchettate), `.glb` (tutte le clip), `.fbx` (take multiple) e **LOD1 (40%) / LOD2 (12%)** con lo stesso rig. |
| `06_preview.py` | hero shot, primo piano, turnaround a 4 viste e GIF delle 5 animazioni. |
| `07_validate.py` | legge i `.glb` senza Blender: triangoli, joint, influenze per vertice, lunghezza delle clip, chiusura dei loop, canali PBR e dimensioni delle texture. Scrive `BOSS1/QA.md` ed esce con errore se qualcosa non torna. |

## Dettagli che vale la pena conoscere

**Perche' la decimation e' adattiva.** Una decimation uniforme a 60k triangoli
toglie il 12% della risoluzione in modo omogeneo: le zone lisce (torso) tengono
triangoli che non servono, mentre punte, artigli e muso perdono gli spigoli che
danno carattere al personaggio. Con il vertex group di dettaglio le stesse 80k
facce si concentrano dove la curvatura e' alta.

**Perche' i pesi sono geodesici.** La posa di riferimento e' accovacciata: le
mani stanno a terra accanto ai piedi e l'aureola tocca la schiena. Una distanza
euclidea (o i pesi "bone heat") confonde queste zone contigue nello spazio ma
lontane sulla superficie. La distanza sulla mesh risolve il problema alla radice
e il risultato e' stabile anche in pose estreme (Death, Roar).

**Perche' niente "bone heat".** I pesi automatici di Blender richiedono che le
ossa siano dentro il volume e non gestiscono bene code, artigli e aureole, che
venivano corretti a mano nella v1. Con il calcolo esplicito il risultato e'
deterministico e riproducibile.
