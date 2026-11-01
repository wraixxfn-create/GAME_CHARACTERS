# DRESS1 — Gonna cerimoniale avorio e ottone

Modello statico per videogiochi, ricostruito a partire dal concept e rifinito
nei drappeggi e nei dettagli. Il confronto mostra il disegno originale e
l'asset 3D:

![Confronto tra reference e DRESS1](preview/ref_compare.png)

## Cosa e' cambiato in questa revisione

- **Pieghe morbide, non plissettatura.** Sulla reference le pieghe della gonna
  sono campate di lino appeso: cresta tonda e larga, valle stretta in ombra,
  una linea d'ombra continua dalla vita all'orlo. La vecchia plissettatura a
  coltello (31 pieghe pressate) leggeva come ventaglio piegato. Ora le pieghe
  sono 20, profonde fino a 4,2 cm all'orlo, con profondita' irregolare lungo
  il giro perche' il drappeggio non sia meccanico.
- **Silhouette ad A.** Il profilo svasa rapido sui fianchi e poi scende quasi
  dritto, massimo all'orlo: niente pancia a campana e niente rientro sul
  fondo (faceva palloncino). Larghezza all'orlo circa 1,65 volte la vita.
- **Orlo a fazzoletto.** Tre lobi asimmetrici sull'orlo della gonna e veli
  piu' lunghi e larghi: le punte davanti scendono sfalsate fin quasi alla
  caviglia, con intacchi profondi fra una punta e l'altra, come nel disegno.
- **Staffa di cuoio liscia.** Nella reference il nastro scuro e' teso: bordi
  dritti, superficie senza pieghe. Prima seguiva una cresta per colonna e
  ondulava i bordi; ora segue solo la bombatura del centro davanti e resta
  sollevato con margine costante sopra i veli pieghettati. Filetto dorato ai
  bordi piu' sottile e simboli appena alleggeriti.
- **Anello pulito.** Come nel disegno la fibbia e' un semplice cerchio
  d'ottone: tolti rivetti e controanello in rilievo, resta la placchetta che
  attacca la staffa.
- **Scialli piu' stretti.** I pannelli scuri sui fianchi sono lame strette
  che si fermano a meta' coscia, con bordo dorato continuo e due sigilli
  (gancio a spirale squadrata e rombo con barrette).
- **Solo il capo.** Gambe, piedi, caviglie fasciate e sandali non ci sono:
  `DRESS1` e' un asset di abbigliamento da montare su un personaggio. La
  fodera interna chiude il capo, quindi guardando sotto l'orlo non si vede
  un guscio vuoto. L'origine resta a terra, sotto l'orlo, come se il vestito
  fosse indossato.
- **Fascia in vita.** Corpo in lino con pieghe a spirale (solchi veri nella
  mesh) che si stringono verso l'anello, bordino superiore arrotolato perche'
  dall'alto non si veda il taglio vivo, teli in croce con estremita'
  assottigliate che rientrano sotto gli altri strati, e il nodo sull'anello.
  Sotto i teli corre la **cintura scura diagonale** che prosegue nella staffa.
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
| `DRESS1.glb` | glTF 2.0 autonomo, **79.223 triangoli** |
| `DRESS1_LOD1.glb` | **31.757 triangoli**, texture a metà risoluzione |
| `DRESS1_LOD2.glb` | **11.401 triangoli**, texture a un quarto di risoluzione |
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
| `DRESS1_Gold` | Anello d'ottone e placchetta di attacco |
| `DRESS1_GoldTrim` | Ricami e simboli dorati |

Le due superfici testurizzate usano base color, normal e ORM a **1024²**; l'AO
è bakeata a 1024² con 32 campioni. In `DRESS1_tex/` l'AO è separata dalle mappe
ORM; nei GLB viene incorporata nel canale R delle mappe occlusion/
metallic-roughness. Le texture dei LOD sono ridimensionate.

Il capo misura **96,0 cm** in altezza (dall'orlo basso al bordo della fascia),
circa 56,1 cm in larghezza e 48,6 cm in profondità. L'origine è a terra, sotto
l'orlo: il vestito occupa la stessa quota che avrebbe indossato, quindi
**l'orlo più basso sta a 12,4 cm da terra**. In Blender l'asse verticale è Z,
mentre i GLB sono esportati Y-up. L'FBX usa Z-up e direzione frontale −Y.

## Pipeline e verifiche

La ricostruzione è riproducibile con Blender 4.5 LTS e il modulo Python `bpy`:
vedi [`tools/README.md`](tools/README.md). I test in `tests/` controllano le
pieghe a coltello, la fodera che chiude il capo, l'assenza di anatomia, la
posizione della staffa rispetto alle falde, lo spessore sotto i ricami e la
reimportazione dei GLB e dell'FBX. `tools/06_validate.py` verifica inoltre
dimensioni, materiali, UV, texture incorporate e budget dei LOD.
