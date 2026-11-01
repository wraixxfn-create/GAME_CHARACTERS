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

Il capo segue la reference dalla vita in giù: `build_sash`, `build_skirt`, `build_lappets`, `build_drapes` e `build_strap` costruiscono gli strati; non viene generato un corpetto o un corpo. La fascia e la fodera lasciano aperto il passaggio per il personaggio. Il nastro e i ricami seguono superfici condivise; i gruppi `keep` e `mid` preservano i dettagli nella generazione dei LOD. I test controllano geometria, apertura centrale, materiali, visibilità dei dettagli e reimportazione degli export.

Variabili opzionali: `DRESS1_AO_SIZE` (default 1024), `DRESS1_AO_SAMPLES` (32), `DRESS1_PREVIEW_SAMPLES` (32), `DRESS1_PREVIEW_SCALE` (1, tra 0.25 e 1).
