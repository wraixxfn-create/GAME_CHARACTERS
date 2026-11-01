# DRESS1 — capo cerimoniale maschile

Capo statico dalla vita all'orlo, ispirato alla reference. Contiene **solo il vestito**: nessun corpetto inventato, corpo, gambe o calzature. La vita e l'orlo sono aperti per permettere l'adattamento a un personaggio maschile.

![Vista frontale](preview/hero_front.png)

## Dettagli

- Lino avorio con pieghe morbide, falde sovrapposte con tagli diagonali e orlo asimmetrico a punte.
- Fascia in vita avvolta, cintura scura sottile e fibbia circolare in ottone.
- Nastro frontale scuro appeso alla fibbia, con rombi, cerchio, linee e punta a V dorati; pannelli scuri laterali più corti con ricami e bordi dorati.
- Fodera interna scura aperta; non sostituisce un corpo e può richiedere adattamenti per la mesh del personaggio.

## File

| File | Contenuto |
|---|---|
| `DRESS1.blend` | Scena Blender con mesh e texture incorporate |
| `DRESS1.glb` | glTF 2.0 autonomo, 77.224 triangoli |
| `DRESS1_LOD1.glb` | 31.093 triangoli |
| `DRESS1_LOD2.glb` | 11.177 triangoli |
| `DRESS1.fbx` | FBX con materiali e texture incorporate |
| `DRESS1_tex/` | Mappe PNG separate, inclusa AO |
| `preview/` | Render e confronto con la reference |
| [`QA.md`](QA.md) | Controlli e misure degli export |

Il modello è una mesh statica senza rig, skin o animazioni: per usarlo su un personaggio occorrono adattamento, pesatura allo scheletro e gestione delle collisioni o del movimento della stoffa. Il capo è alto circa 96 cm; l'origine è a terra, con orlo più basso a circa 12 cm. Blender e FBX sono Z-up (fronte −Y); i GLB sono Y-up. I materiali PBR usano texture a 1024² e AO bakeata; i LOD hanno texture ridimensionate.

Pipeline riproducibile e test: [`tools/README.md`](tools/README.md).
