# DRESS1 — Gonna cerimoniale avorio e ottone

Modello statico per videogiochi, ricostruito a partire dalla reference e
rifinito nei drappeggi e nei dettagli. Il confronto mostra il concept originale
e l'asset 3D aggiornato:

![Confronto tra reference e DRESS1](preview/ref_compare.png)

## Dettagli della revisione

- **Fascia in vita:** due teli incrociati, cintura scura diagonale e fibbia
  d'ottone con piccoli rivetti e fondo scuro.
- **Gonna:** pieghe geometriche continue e otto falde avorio sovrapposte, con
  lunghezze e punte sfalsate. Le falde seguono lo spostamento della gonna
  anziché attraversarne le pieghe.
- **Staffa centrale:** nastro scuro a punta, con cerchio, rombi, asta e doppio
  bordo a V dorati. Le decorazioni sono geometria, non un'immagine proiettata.
- **Scialli laterali:** bordi e motivi geometrici dorati modellati sopra lo
  spessore del tessuto; i ricami rimangono presenti anche nei LOD.
- **Piedi:** posa più aperta, fasciature scure e sandali con suola bruna.
- Materiali PBR, texture incorporate e occlusione ambientale bakeata. La
  pipeline e i test verificano anche i file esportati, non solo la scena Blender.

## File

| File | Contenuto |
|---|---|
| `DRESS1.blend` | Scena Blender, mesh e texture incorporate; gruppo `keep` per i dettagli |
| `DRESS1.glb` | glTF 2.0 autonomo, **77.999 triangoli** |
| `DRESS1_LOD1.glb` | **27.298 triangoli**, texture a metà risoluzione |
| `DRESS1_LOD2.glb` | **9.358 triangoli**, texture a un quarto di risoluzione |
| `DRESS1.fbx` | FBX con geometria, materiali e texture supportate incorporate |
| `DRESS1_tex/` | Texture PNG separate, inclusa l'AO |
| [`QA.md`](QA.md) | Misure e controlli degli export GLB |
| `preview/` | Viste frontale, tre quarti, vita, piedi, retro, turnaround e confronto |

Il `.blend` contiene **una mesh** composta dalle isole dei vari pezzi, non
oggetti separati. L'asset non ha rig, skin o animazioni: per indossarlo su un
personaggio serve un adattamento allo scheletro e una gestione del movimento
della stoffa.

## Materiali e scala

| Materiale | Uso |
|---|---|
| `DRESS1_Linen` | Gonna e fascia avorio |
| `DRESS1_Wool` | Cintura, scialli, staffa e fasciature scure |
| `DRESS1_Gold` | Fibbia e rivetti d'ottone |
| `DRESS1_GoldTrim` | Ricami e simboli dorati |
| `DRESS1_Canvas` | Suole scure |
| `DRESS1_Skin` | Piedi e caviglie |

Le quattro superfici testurizzate usano base color, normal e ORM a **1024²**;
l'AO è bakeata a 1024² con 32 campioni. In `DRESS1_tex/` l'AO è separata dalle
mappe ORM; nei GLB viene incorporata nel canale R delle mappe
occlusion/metallic-roughness. Le texture dei LOD sono ridimensionate.

L'asset misura **1,099 m** in altezza, circa 57,6 cm in larghezza e 51,7 cm
in profondità; l'origine è tra i piedi. In Blender l'asse verticale è Z,
mentre i GLB sono esportati Y-up. L'FBX usa Z-up e direzione frontale −Y.

## Pipeline e verifiche

La ricostruzione è riproducibile con Blender 4.5 LTS e il modulo Python `bpy`:
vedi [`tools/README.md`](tools/README.md). I test in `tests/` controllano le
pieghe, la posizione della staffa rispetto alle falde, lo spessore sotto i
ricami e la reimportazione dei GLB e dell'FBX. `tools/06_validate.py` verifica
inoltre dimensioni, materiali, UV, texture incorporate e budget dei LOD.
