# DRESS1 — Gonna cerimoniale avorio e ottone

Modello statico per videogiochi, ricostruito a partire dalla reference e
rifinito nei drappeggi e nei dettagli. Il confronto mostra il concept originale
e l'asset 3D aggiornato:

![Confronto tra reference e DRESS1](preview/ref_compare.png)

## Dettagli della revisione

Ricostruzione fedele ai dettagli del concept, non solo alla silhouette:

- **Fascia in vita:** tre teli diagonali che si avvolgono davvero attorno alla
  vita e si incrociano davanti, con estremita' assottigliate che rientrano
  sotto gli altri strati; il bordo superiore si ripiega verso l'interno. Sotto
  i teli avorio corre la **cintura scura** diagonale e sopra tutto sta la
  **fibbia d'ottone**: anello piatto, controanello in rilievo, dodici rivetti e
  placchetta di attacco.
- **Gonna:** 31 pieghe fitte con creste tonde e valli piu' nette, profondita'
  irregolare, e otto falde avorio sovrapposte con punte sfalsate e lunghe. Le
  falde seguono lo spostamento della gonna anziche' attraversarne le pieghe;
  gli strati stanno a 6-8 mm l'uno dall'altro, come stoffa sovrapposta.
- **Staffa centrale:** nastro quasi parallelo e rastremato verso la punta,
  con **filetto dorato sui due bordi** e catena di simboli ricostruita dal
  disegno: asta, rombo, cerchio con traversa e croce, asta con barretta,
  rombo, fascia a pettine e doppio V. La punta non e' un semplice V ma ha un
  intaglio centrale che la apre in due lobe. Le decorazioni sono geometria.
- **Scialli laterali:** pannelli scuri piu' larghi e arretrati, appoggiati
  sopra il davanti avorio, con punta a meta' coscia, bordo dorato continuo sui
  due lati lunghi e sull'orlo, piu' due sigilli: gancio a spirale squadrata e
  rombo con barrette.
- **Piedi e calzari:** piede piu' snello con tallone arrotondato, dorso basso e
  cinque dita affusolate; suola sottile ricavata dal profilo del piede,
  fascette generate **sulla superficie del piede** (non sospese), fascetta al
  tallone che segue la pianta, caviglie fasciate con bande sfalsate e nastro a
  spirale.
- **Materiali:** avorio piu' caldo, lana scura piu' neutra, ottone meno giallo.
  PBR con texture incorporate e occlusione ambientale bakeata.
- **LOD a tre livelli:** stoffa, stoffa con bordi vivi (teli in croce,
  cintura) e dettagli sottili hanno budget separati, cosi' i ricami dorati e i
  bordi dei teli restano leggibili anche nei LOD.

## File

| File | Contenuto |
|---|---|
| `DRESS1.blend` | Scena Blender, mesh e texture incorporate; gruppi `keep` e `mid` per i dettagli |
| `DRESS1.glb` | glTF 2.0 autonomo, **77.999 triangoli** |
| `DRESS1_LOD1.glb` | **28.737 triangoli**, texture a metà risoluzione |
| `DRESS1_LOD2.glb` | **10.135 triangoli**, texture a un quarto di risoluzione |
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

L'asset misura **1,078 m** in altezza, circa 54,7 cm in larghezza e 47,0 cm
in profondità; l'origine è tra i piedi. In Blender l'asse verticale è Z,
mentre i GLB sono esportati Y-up. L'FBX usa Z-up e direzione frontale −Y.

## Pipeline e verifiche

La ricostruzione è riproducibile con Blender 4.5 LTS e il modulo Python `bpy`:
vedi [`tools/README.md`](tools/README.md). I test in `tests/` controllano le
pieghe, la posizione della staffa rispetto alle falde, lo spessore sotto i
ricami e la reimportazione dei GLB e dell'FBX. `tools/06_validate.py` verifica
inoltre dimensioni, materiali, UV, texture incorporate e budget dei LOD.
