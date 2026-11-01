# DRESS1 — Gonna cerimoniale avorio e ottone

Modello statico per videogiochi, ricostruito a partire dal concept e rifinito
nei drappeggi e nei dettagli. Il confronto mostra il disegno originale e
l'asset 3D:

![Confronto tra reference e DRESS1](preview/ref_compare.png)

## Cosa e' cambiato in questa revisione

- **Solo il capo.** Gambe, piedi, caviglie fasciate e sandali sono stati tolti:
  `DRESS1` ora e' un asset di abbigliamento, non mezzo personaggio. La fodera
  interna chiude il capo, quindi guardando sotto l'orlo non si vede un guscio
  vuoto, e si puo' montare su qualsiasi personaggio. L'origine resta a terra,
  sotto l'orlo, come se il vestito fosse indossato.
- **Pieghe a coltello al posto della sinusoide.** La gonna ha 31 pieghe
  pressate: la faccia sale quasi dritta, la cresta resta tonda e la valle e'
  un angolo vivo che disegna una linea d'ombra continua dalla vita all'orlo.
  Prima le pieghe erano sinusoidi e, decimate all'8%, leggevano come stoffa
  gonfia. La profondita' e' irregolare, quindi il ventaglio non e' meccanico.
- **Falde lunghe a V.** Sei veli avorio con punta lunga e asimmetrica
  (`Lap_FrontL/R`, `Lap_MidL/R`, `Lap_SideL/R`, piu' il telo diagonale
  `Lap_WaistL`) e una lingua centrale sotto la staffa. Ogni falda segue la
  stessa superficie pieghettata della gonna: la stoffa resta pieghettata
  anche sui veli, invece di diventare un pannello di cartone.
- **Fascia in vita.** Corpo in lino con pieghe a spirale (solchi veri nella
  mesh) che si stringono verso l'anello, bordino superiore arrotolato perche'
  dall'alto non si veda il taglio vivo, tre teli in croce con estremita'
  assottigliate che rientrano sotto gli altri strati, e il nodo sull'anello.
  Sotto i teli corre la **cintura scura diagonale** che prosegue nella staffa;
  sopra tutto l'**anello d'ottone** con rivetti e placchetta.
- **Staffa centrale.** Nastro largo circa 6,3 cm, incollato alle pieghe:
  per ogni punto si calcola l'angolo reale sulla gonna, quindi il lino non
  affiora piu' ai bordi del nastro (prima lo spezzava in strisce). Ricamo
  dorato ricostruito dal disegno: asta, rombo, cerchio con traversa e croce,
  asta con barretta, rombo, fascia a pettine e doppio V della punta. I simboli
  sono geometria appoggiata alla superficie e campionata sulla curvatura.
- **Scialli laterali.** Pannelli di lana sui fianchi, dalla vita a meta'
  coscia, con punta a V e bordo dorato continuo piu' due sigilli (gancio a
  spirale squadrata e rombo con barrette).
- **Materiali.** Avorio piu' caldo, lana scura piu' neutra, ottone meno giallo,
  ricami dorati piu' sottili e meno in rilievo (prima sembravano plastica).
  PBR con texture incorporate e occlusione ambientale bakeata.
- **LOD a tre livelli.** Le griglie nascono gia' alla densita' del LOD0 e i
  gruppi `keep` / `mid` proteggono ricami, staffa e bordi vivi: le pieghe e i
  ricami restano leggibili anche nei LOD.

## File

| File | Contenuto |
|---|---|
| `DRESS1.blend` | Scena Blender, mesh e texture incorporate; gruppi `keep` e `mid` per i dettagli |
| `DRESS1.glb` | glTF 2.0 autonomo, **79.224 triangoli** |
| `DRESS1_LOD1.glb` | **31.758 triangoli**, texture a metà risoluzione |
| `DRESS1_LOD2.glb` | **11.407 triangoli**, texture a un quarto di risoluzione |
| `DRESS1.fbx` | FBX con geometria, materiali e texture supportate incorporate |
| `DRESS1_tex/` | Texture PNG separate, inclusa l'AO |
| [`QA.md`](QA.md) | Misure e controlli degli export GLB |
| `preview/` | Viste frontale, tre quarti, vita, orlo, interno, retro, turnaround e confronto |

Il `.blend` contiene **una mesh** composta dalle isole dei vari pezzi, non
oggetti separati. L'asset non ha rig, skin o animazioni: per indossarlo su un
personaggio serve un adattamento allo scheletro e una gestione del movimento
della stoffa.

## Materiali e scala

| Materiale | Uso |
|---|---|
| `DRESS1_Linen` | Gonna, falde, fascia e teli in croce |
| `DRESS1_Wool` | Cintura, scialli e staffa |
| `DRESS1_Gold` | Anello e rivetti d'ottone |
| `DRESS1_GoldTrim` | Ricami e simboli dorati |

Le due superfici testurizzate usano base color, normal e ORM a **1024²**; l'AO
è bakeata a 1024² con 32 campioni. In `DRESS1_tex/` l'AO è separata dalle mappe
ORM; nei GLB viene incorporata nel canale R delle mappe occlusion/
metallic-roughness. Le texture dei LOD sono ridimensionate.

Il capo misura **96,4 cm** in altezza (dalla vita all'orlo), circa 55,6 cm in
larghezza e 47,4 cm in profondità. L'origine è a terra, sotto l'orlo: il
vestito occupa la stessa quota che avrebbe indossato, quindi **l'orlo più basso
sta a 12 cm da terra**. In Blender l'asse verticale è Z, mentre i GLB sono
esportati Y-up. L'FBX usa Z-up e direzione frontale −Y.

## Pipeline e verifiche

La ricostruzione è riproducibile con Blender 4.5 LTS e il modulo Python `bpy`:
vedi [`tools/README.md`](tools/README.md). I test in `tests/` controllano le
pieghe a coltello, la fodera che chiude il capo, l'assenza di anatomia, la
posizione della staffa rispetto alle falde, lo spessore sotto i ricami e la
reimportazione dei GLB e dell'FBX. `tools/06_validate.py` verifica inoltre
dimensioni, materiali, UV, texture incorporate e budget dei LOD.
