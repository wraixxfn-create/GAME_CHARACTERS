# Pipeline ELFO1

Script Blender headless che trasformano il modello grezzo
`ImageToStl.com_elf+character+3d+model(1).blend` (339.022 triangoli, senza rig,
tre texture 4096^2) in un personaggio game-ready animato, con LOD e QA
automatica.

## Requisiti

```bash
pip install bpy==5.0.1 numpy==1.26.4 scipy==1.13.1 pillow==10.4.0   # vedi requirements.txt
```

Sono usati solo moduli headless di Blender (`bpy` come modulo Python), nessuna
GPU: bake AO e render di anteprima girano su Cycles CPU.

> Su Linux il wheel `bpy` richiede le librerie di sistema X11/GL anche in
> modalita' headless: `libxrender1 libxi6 libxxf86vm1 libxfixes3 libxext6
> libgl1 libxkbcommon0 libsm6 libice6`. Il wheel 5.0.1 e' compilato contro
> NumPy 1.x: con NumPy 2 il modulo si carica ma esplode al primo uso.

## Esecuzione

```bash
cd ELFO1/tools
python3 01_optimize.py    # 339k -> 55k tri adattivi, simmetria, normali pesate
python3 02_rig.py         # armatura 43 ossa + skinning geodesico
python3 03_animate.py     # Idle / Walk / Run / Cast / Death
python3 04_material.py    # texture 2K + AO bakeata + ORM + rune emissive
python3 05_export.py      # ELFO1.blend/.glb/.fbx + LOD1/LOD2, scala 1,85 m
python3 06_preview.py     # render di presentazione e GIF (facoltativo, lento)
python3 07_validate.py    # QA dei file esportati -> ELFO1/QA.md
```

I `.blend` intermedi finiscono in `$ELFO1_WORK` (default `/home/user/work/elfo`),
fuori dal repository; solo i file finali vanno in `ELFO1/`.
Gli step 1-5 girano in circa un minuto; i render di anteprima sono la parte
lenta (Cycles CPU, ~15 minuti a 1000 px).

## Step

| file | cosa fa |
|---|---|
| `01_optimize.py` | sgancia la mesh dagli empty di ImageToStl, applica le trasformazioni, calcola un **peso di dettaglio per vertice** (curvatura + boost su viso, capelli, mani, piedi, tessuto) e decima a 55k con `DECIMATE` e **simmetria X**. Pulisce i duplicati e ricalcola le normali pesate. |
| `02_rig.py` | 43 ossa (vedi `skeleton.py`) e **skinning geodesico**: semi per osso sulla superficie, multi-source Dijkstra sullo scheletro di edge (scipy), peso `1/d^4`, smoothing laplaciano, 4 influenze. Maschere anatomiche per capelli e gonnellone. |
| `03_animate.py` | 5 clip a 30 fps in **angoli anatomici** (character frame) con composizione esatta della catena dei genitori, quaternioni con continuita' di segno, tutti i canali keyati in ogni clip, caduta della `Death` appoggiata al pavimento con una misura della mesh in posa. Include un'**autoverifica numerica** (direzione del ginocchio, contatto dei piedi, direzione della spinta del `Cast`, appoggio finale della `Death`) e scrive `anim_report.json` per lo step 7. |
| `04_material.py` | basecolor e normal a 2048, ORM a 1024 con **AO bakeata** nel rosso, emissive 1024 ricavata dalle rune dipinte nella basecolor. Nella basecolor alza le ombre, riscalda la fodera scura del gonnellone e **dipinge occhi e sopracciglia** sulla posizione 3D dei texel. Materiale double-sided. |
| `05_export.py` | scala metrica a **1,85 m** (mesh, ossa e keyframe), rinomina le azioni `ELFO1_*`, export `.blend` compresso, `.glb` con le 5 clip, `.fbx` con 5 take, LOD1 (35%) e LOD2 (12%). |
| `06_preview.py` | hero shot della posa di lancio, ritratto, turnaround a 4 viste, confronto sorgente/LOD0, GIF 420x540 delle 5 animazioni (inquadratura calcolata sul bounding box di tutta la clip, cosi' nessuna posa esce dal fotogramma). |
| `07_validate.py` | legge i `.glb` senza Blender: triangoli, joint, influenze, durate, chiusura dei loop, canali PBR, dimensioni texture, altezza. Scrive `ELFO1/QA.md` ed esce con errore se qualcosa non torna. |

## Dettagli che vale la pena conoscere

**Il tessuto non deve appendere alle gambe.** La gonna passa a tre centimetri
dalle ginocchia: con la sola distanza geodesica (che corre lungo la superficie
del gonnellone) l'orlo risultava "vicino" allo stinco e prendeva fino al 100% di
peso da `thigh`/`shin`. Nella camminata quei vertici restavano indietro e la
stoffa si allungava in schegge lunghe mezzo metro. Le ossa delle gambe ora
pesano solo entro 17 cm dall'asse dell'osso (distanza euclidea) e i pochi
vertici che si discostavano dalla media dei vicini vengono riportati a quella
media. Lunghezza massima di un edge in posa: era 10x il riposo, ora 2x.

**La falcata deve stare dentro la gamba.** Con una semi-falcata di 0,26 unita'
contro un arto di 0,37 il bacino doveva scendere di 10 cm a ogni appoggio: il
"walk" sembrava un affondo. La semi-falcata e' 0,185 (passo 0,68 m) e il
ginocchio resta quasi disteso in appoggio.

**Le macchie nere sul gonnellone non erano texture.** Nella v2 la fodera
interna del tessuto veniva fuori nera in tutti i render. Non erano buchi
(rendendo la mesh in emissione bianca su fondo ciano la silhouette era piena),
non erano texel neri (nella basecolor nessun texel sotto 0,20 di luminanza) e
non erano facce con la normale invertita. Era il nodo che *ribaltava* la
normale sulle facce posteriori: Cycles la gira gia' da solo, il secondo
ribaltamento la mandava dentro la superficie e la fodera non prendeva piu' luce.
Togliendo quel nodo il gonnellone si e' schiarito senza toccare ne' la texture
ne' le luci.

**L'inquadratura si calcola dalla sfera che contiene il personaggio.** La
versione precedente stimava il campo visivo sull'altezza e tagliava il viso nei
primi piani e i piedi nelle pose distese. Ora `camera()` prende centro e
dimensione della posa, costruisce la sfera che la contiene e sceglie il fuoco
piu' stretto fra orizzontale e verticale in base all'aspect ratio. Le GIF usano
il bounding box di **tutta** la clip: la camera non insegue il personaggio
frame per frame.

**La decimation di Blender ha i pesi al contrario.** Nel modificatore
`DECIMATE` il peso 1 autorizza a togliere facce e il peso 0 le conserva: al
vertex group "dettaglio" va quindi passato il **complemento**. Con i pesi
dritti il viso perdeva due terzi dei vertici (662 invece di 8.500).

**Le maschere anatomiche non sono confini rigidi.** Capelli e gonnellone sono
superfici sottili appoggiate al corpo: la distanza geodesica, da sola, "salta"
dalla punta di una ciocca alla spalla e dal tessuto alla coscia. Le maschere
servono a scegliere i **semi** e a impedire l'invasione del corpo, ma dentro la
regione (tutta la chioma, tutto il gonnellone) le ossa restano libere di
competere: con confini netti fra i quadranti della gonna il foglio si strappava
appena le ossa ruotavano in modo diverso.

**La soglia dei pesi va calcolata dopo le maschere.** Se la distanza minima per
la soglia `1/d^4` viene da un osso poi mascherato, il vertice resta senza nessuna
influenza e nella posa rimane piantato a terra mentre il corpo si muove: erano
le "schegge" bianche della prima versione della `Death`. C'e' comunque un
fallback euclideo che recupera i vertici orfani.

**Le rune emissive vengono dai pixel, non dal rumore.** Nella basecolor le rune
sono rosso cupo e saturo; con soglia `sat > 0.48` e dominante rossa si prende
l'inchiostro (0,34% della superficie UV) e non l'ombra calda della pelle. Con una
soglia piu' bassa si accendeva mezza schiena.

**La caduta si appoggia al pavimento da sola.** Per i frame della `Death` lo
script valuta la mesh in posa, prende il punto piu' basso e sposta il `root` di
conseguenza: cambiare la rotazione del crollo non richiede piu' di ritoccare le
traslazioni a mano.
