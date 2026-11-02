# DRESS1 — pipeline riproducibile

Richiede Blender 4.5 LTS con `bpy` e numpy. Dalla cartella `DRESS1/`, con un interprete Python che disponga di `bpy`:

```bash
export DRESS1_WORK=/tmp/dress1_work
B=/percorso/python-con-bpy
for script in 01_build 02_optimize 03_material 04_export; do
    "$B" "tools/$script.py"
done
python3 tools/06_validate.py
"$B" tests/test_geometry.py
"$B" tests/test_exports.py
"$B" tools/05_preview.py
```

Gli script costruiscono il capo procedurale, ottimizzano e preparano UV e gruppi di dettaglio, generano materiali e AO, esportano `.blend`, GLB con LOD e FBX, e infine producono anteprime e QA. I temporanei restano in `DRESS1_WORK`.

Il capo segue la reference dalla vita in giù e non viene generato un corpetto o un corpo. Gli strati si costruiscono così:

- `build_sash` — fascia avorio piatta, **cinghie scure incrociate** (`sash_band`) che formano la X davanti alla fibbia, anello d'ottone e fascio di lana nel foro.
- `build_belt` — cintura scura sottile alla base della fascia, che nasconde l'attacco dei pannelli.
- `build_skirt` / `build_underskirt` / `build_lining` — gonna pieghettata (`pleats`, `skirt_disp`), sottogonna e fodera interna.
- `build_overlays` — i tre teli sovrapposti con orli a punta; `Piece` è il lembo parametrico che li genera.
- `build_falls` — le tre lingue del davanti, le punte più basse del capo.
- `build_drapes` + `build_drape_runes` — pannelli di lana sui fianchi e i loro ricami dorati, tracciati in (angolo, quota) e non nello spazio UV.
- `build_strap` + `strap_gold` — staffa frontale e motivo dorato completo (asta, rombo, cerchio con croce, secondo rombo, V annidate, cuneo).

Fascia e fodera lasciano aperto il passaggio per il personaggio. I gruppi `keep` e `mid` preservano i dettagli nella generazione dei LOD. I test controllano geometria, apertura centrale, materiali, distacco degli strati, visibilità dei dettagli e reimportazione degli export.

Variabili opzionali: `DRESS1_AO_SIZE` (default 1024), `DRESS1_AO_SAMPLES` (32), `DRESS1_PREVIEW_SAMPLES` (32), `DRESS1_PREVIEW_SCALE` (1, tra 0.25 e 1).
