# DRESS1 — pipeline riproducibile

Gli script usano Python con `bpy` di Blender 4.5 LTS e numpy. I file temporanei
restano fuori dal repository nella directory `DRESS1_WORK`.

| Script | Input | Output |
|---|---|---|
| `01_build.py` | Parametri nel sorgente | Mesh procedurale grezza in `build/` |
| `02_optimize.py` | Build | LOD0 ottimizzato, UV e gruppo `keep` in `opt/` |
| `03_material.py` | LOD0 ottimizzato | Materiali, texture e bake AO in `mat/` |
| `04_export.py` | LOD0 con materiali | `.blend`, GLB LOD0/1/2, FBX e PNG nel repo |
| `05_preview.py` | `DRESS1.blend` | Render in `preview/` |
| `06_validate.py` | Tre GLB | `QA.md`; esce con errore se un controllo fallisce |

## Esecuzione

Dalla cartella `DRESS1/`, usando un interprete Python con `bpy` disponibile:

```bash
export DRESS1_WORK=/tmp/dress1_work
B=/percorso/python-con-bpy
for script in 01_build 02_optimize 03_material 04_export; do
    "$B" "tools/$script.py"
done
python3 tools/06_validate.py
"$B" tests/test_geometry.py
"$B" tests/test_exports.py
"$B" tools/05_preview.py  # opzionale: render Cycles su CPU
```

### Parametri opzionali

| Variabile | Default | Uso |
|---|---:|---|
| `DRESS1_WORK` | `/tmp/dress1_work` | Cartella temporanea della pipeline |
| `DRESS1_AO_SIZE` | `1024` | Lato in pixel della mappa AO |
| `DRESS1_AO_SAMPLES` | `32` | Campioni Cycles per l'AO |
| `DRESS1_PREVIEW_SAMPLES` | `32` | Campioni di ciascun render |
| `DRESS1_PREVIEW_SCALE` | `1` | Scala delle anteprime, tra `0.25` e `1` |

## Scelte importanti

- **Pieghe continue:** `skirt_disp(a, z)` usa la distanza positiva fra vita e
  orlo ed è condivisa con le falde. Le armoniche intere sono continue alla
  cucitura; i solchi delle falde sono geometria, non linee dipinte.
- **Spessore dei ricami:** i motivi laterali vengono proiettati sul pannello e
  sollevati oltre il suo spessore di 3,2 mm. La staffa e i suoi simboli usano
  la stessa superficie curva.
- **Budget separati:** il gruppo `keep` protegge nastri, fibbia e ricami. Il
  LOD0 usa circa 52k triangoli per stoffa e anatomia e 26k per i dettagli; i
  LOD successivi decimano i due gruppi separatamente (25%/55% e 8%/20%).
- **AO:** il bake usa la UV comune e prepara un nodo immagine attivo in ogni
  slot materiale. Le texture vengono salvate su disco, ricaricate e
  impacchettate nel `.blend`; i GLB sono autonomi.
- **Test:** `test_geometry.py` controlla le superfici procedurali e le distanze
  dei ricami dalla stoffa; `test_exports.py` reimporta GLB e FBX e controlla la
  visibilità della staffa e la presenza dei ricami in ogni LOD. La QA dei GLB
  gira anche con Python standard, senza Blender.
