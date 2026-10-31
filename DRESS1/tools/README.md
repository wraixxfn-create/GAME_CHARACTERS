# DRESS1 — pipeline

Sei script, tutti eseguiti dentro Blender tramite il modulo `bpy` (4.5 LTS).
Nessuna GUI, nessuna dipendenza oltre a numpy e Pillow (incluse nel pacchetto
`bpy`).

| script | input | output | tempo |
|---|---|---|---|
| `01_build.py` | — (geometria procedurale) | `$DRESS1_WORK/build/DRESS1_build.blend` | ~18 s |
| `02_optimize.py` | build | `opt/DRESS1_opt.blend` + `LOD1/LOD2` | ~18 s |
| `03_material.py` | opt | `mat/DRESS1_mat.blend` + LOD con materiali | ~40 s (bake AO) |
| `04_export.py` | mat | `DRESS1.blend`, `.glb` x3, `.fbx`, `DRESS1_tex/` | ~27 s |
| `05_preview.py` | `DRESS1.blend` | `preview/*.png` | ~15 min (Cycles CPU) |
| `06_validate.py` | i `.glb` | `QA.md` | < 1 s |

`06_validate.py` gira anche **senza Blender**: è Python puro con un parser
minimo di glTF, così la QA si può mettere in CI.

## Variabili

| nome | default | significato |
|---|---|---|
| `DRESS1_WORK` | `/tmp/dress1_work` | cartella di lavoro (fuori dal repo) |

## Come si rilancia tutto

```bash
export DRESS1_WORK=/tmp/dress1_work
B=/path/to/python/con/bpy          # interprete con il modulo bpy installato

for f in tools/01_build.py tools/02_optimize.py tools/03_material.py \
         tools/04_export.py tools/06_validate.py; do
    "$B" "$f"
done
"$B" tools/05_preview.py           # opzionale: render lunghi
```

## Scelte che vale la pena conoscere

**Una superficie per tutto.** `01_build.py` espone
`surface(angolo, quota, strato)`; gonna, falde, scialli, staffa e ricami
leggono tutti da lì con un offset di raggio per strato. È quello che evita le
compenetrazioni: se si sposta una quota in `PROFILE`, si muove tutto insieme.

**Split prima della decimation.** A 60k triangoli un ricamo dorato largo 3 mm
sparisce. `02_optimize.py` divide le facce in *stoffa* e *dettagli* usando il
vertex group `keep` creato in `01_build.py` e le decima con budget separati
(52k + 26k). I dettagli sono il 30% dei triangoli su meno del 10% della
superficie.

**Immagini: sempre per il disco.** Un'immagine `generated` con i pixel scritti
via `foreach_set` non sopravvive al salvataggio (si ricarica nera). Le mappe
vengono quindi salvate su PNG, ricaricate come `FILE` e impacchettate.

**Uno strato per lembo, mai due uguali.** Dove due superfici condividono lo
stesso offset il render alterna i due pezzi: il bordo si legge come una fila di
dentini. La mappa `LAYER` in `01_build.py` assegna quindi un offset diverso a
ogni falda e a ogni scialle (`lapB` 26 mm, `lap` 34, `lap2` 46, `lap3` 52,
`drape` 56, `drape2` 62, `trim` 68, `strap` 74). Se si aggiunge un lembo, gli
si dà uno strato proprio.

**Le falde seguono le pieghe.** `skirt_disp(a, z)` restituisce lo spostamento
radiale della gonna in quel punto; i lembi lo sommano al proprio offset, così
si appoggiano alla superficie pieghettata invece di attraversarla.

**Metalli a tinta piena.** Anello e ricami non hanno mappe: sono valori
uniformi. Su un anello da 6 cm una texture a chiazze si legge come
camouflage, e l'asset pesa meno.
