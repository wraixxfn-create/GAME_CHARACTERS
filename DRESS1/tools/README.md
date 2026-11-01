# DRESS1 — pipeline riproducibile

Gli script usano Python con `bpy` di Blender 4.5 LTS e numpy. I file temporanei
restano fuori dal repository nella directory `DRESS1_WORK`.

| Script | Input | Output |
|---|---|---|
| `01_build.py` | Parametri nel sorgente | Mesh procedurale grezza in `build/` |
| `02_optimize.py` | Build | LOD0 ottimizzato, UV e gruppo `keep` in `opt/` |
| `03_material.py` | LOD0 ottimizzato | Materiali, texture e bake AO in `mat/` |
| `04_export.py` | LOD0 con materiali | `.blend`, GLB LOD0/1/2, FBX e PNG nel repo |
| `05_preview.py` | `DRESS1.blend` | Render in `preview/` (frontale, tre quarti, vita, orlo, interno, retro, turnaround) |
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

- **Profilo pieno misurato sul disegno:** `PROFILE` segue la larghezza della
  reference riga per riga: svasatura decisa sotto il fianco, discesa quasi
  cilindrica (a metà altezza la gonna è già al 90% della bocca), lieve
  rientro ai due terzi e riacceleratura finale. L'orlo sta a ~1,8 volte la
  vita.
- **Pieghe morbide:** `drape_fold(x)` descrive una campata di lino appeso
  (cresta tonda e larga, valle stretta in ombra) e `pleats()` la distribuisce
  su 20 periodi con profondità irregolare, fino a 4,6 cm all'orlo.
  `skirt_disp(a, z)` è condivisa da gonna, falde, lingua e scialli: chi segue
  la gonna si muove con lei.
- **Densità al primo colpo:** le griglie nascono alla risoluzione del LOD0
  (7 colonne per piega sulla gonna). Prima nascevano molto più fitte e la
  decimation le portava all'8%: le pieghe si scioglievano.
- **Staffa tesa e corta:** `strap_point()` ricava l'angolo reale sulla gonna
  per ogni `x` ma segue solo la bombatura del centro davanti: il cuoio resta
  liscio, con i bordi dritti e un margine costante sopra le creste dei veli.
  Il nastro finisce a metà coscia (z ≈ 0,46): sotto continua la lingua. I
  ricami (`_gold2d`) sono griglie campionate sulla superficie e sollevate
  lungo la normale radiale.
- **La lingua e il suo rombo:** la lingua è un pannello largo con i solchi
  spostati ai bordi, così il centro resta un cartiglio liscio;
  `build_tongue_gold()` vi appoggia il rombo con la croce (il simbolo più
  grande del disegno) campionando la superficie del pannello con una
  bisezione sulla quota (`_tongue_v_for_z`).
- **Catena dorata sobria:** sulla staffa solo un piccolo rombo a metà
  discesa, una barretta, l'asta lunga col rombo al centro e il filetto sui
  bordi: nel disegno il cuoio è nudo nel tratto alto.
- **Capo chiuso:** `build_lining()` crea la sacca interna che chiude gonna e
  fascia, così l'asset si guarda anche da sotto senza mostrare un guscio vuoto.
- **Teli in vita:** `sash_wrap` stende un nastro fra due angoli con estremità
  assottigliate e salita ripida al centro, così l'incrocio davanti forma la X
  del nodo e le estremità si nascondono sotto gli altri strati.
- **Cinque materiali:** lino, lana e cuoio testurizzati più ottone e oro dei
  ricami a tinta piena. Il cuoio (`DRESS1_Leather`) separa staffa e cintura
  dagli scialli scuri come nel disegno.
- **Spessore dei ricami:** i motivi laterali vengono proiettati sul pannello e
  sollevati di 2,6 mm; sulla staffa i simboli usano la normale radiale calcolata
  nel punto, non una pendenza media.
- **Budget separati su tre livelli:** i gruppi `keep` (nastri, fibbia, ricami)
  e `mid` (teli in croce e cintura, stoffa con bordi vivi e pochi centimetri di
  larghezza) proteggono i dettagli delicati. Il LOD0 usa circa 43k triangoli
  per la stoffa, 10k per la stoffa media e 26k per i dettagli; i LOD
  successivi decimano i tre gruppi separatamente (25/50/58% e 8/18/22%).
- **AO:** il bake usa la UV comune e prepara un nodo immagine attivo in ogni
  slot materiale. Le texture vengono salvate su disco, ricaricate e
  impacchettate nel `.blend`; i GLB sono autonomi.
- **Test:** `test_geometry.py` controlla le superfici procedurali, le distanze
  dei ricami dalla stoffa e la catena dorata (cuoio nudo in alto, rombo grande
  sotto la punta); `test_exports.py` reimporta GLB e FBX e controlla la
  visibilità della staffa e la presenza dei ricami in ogni LOD. La QA dei GLB
  gira anche con Python standard, senza Blender.

## Ambiente di build senza display

Il modulo `bpy` di PyPI funziona anche in un container headless (è così che sono
stati rigenerati gli asset e le anteprime di questa revisione). Servono le
librerie presenti in una normale installazione desktop (GL, X11, xkbcommon);
in un container minimale si possono creare dei piccoli stub condivisi e
caricarli con `LD_LIBRARY_PATH` / `LD_PRELOAD`. Nessuno script della pipeline
apre finestre: si usano solo `bpy.ops` che non richiedono un contesto UI.
