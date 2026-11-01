# DRESS1 — Gonna cerimoniale avorio, cuoio e ottone

Modello statico per videogiochi, ricostruito a partire dal concept e rifinito
nei drappeggi e nei dettagli. Il confronto mostra il disegno originale e
l'asset 3D:

![Confronto tra reference e DRESS1](preview/ref_compare.png)

## Cosa e' cambiato in questa revisione

Questa revisione rilesge il disegno riga per riga (profili, ombre, zanne
d'oro) e riporta l'asset alle sue proporzioni e alla sua gerarchia di
dettagli.

- **Gonna piena, non a A stretta.** Misurato sul disegno: sotto il fianco la
  gonna si apre in fretta e a meta' altezza e' gia' larga come al 90% della
  bocca; da li' scende quasi cilindrica, con un lieve rientro ai due terzi e
  una riacceleratura sugli ultimi centimetri. L'orlo sta a circa 1,8 volte la
  vita (1,9-2,0 con le creste delle pieghe) e il capo occupa in larghezza
  circa i due terzi della sua altezza: 60,2 cm di larghezza su 93,3 di
  altezza. Prima la vita restava stretta fino a meta' coscia e leggeva come
  un cono, non come il lino pieno del disegno.
- **Pieghe piu' profonde.** Le 20 campate morbide scendono ora a 4,6 cm
  cresta-valle all'orlo: le linee d'ombra restano continue dalla vita al
  fondo anche sulla superficie piu' ampia.
- **La staffa finisce a meta' coscia.** Nel disegno il nastro di cuoio corre
  **nudo** dall'anello fino a meta' coscia e li' si ferma: sotto prosegue la
  lingua di lino. Prima il cuoio arrivava quasi all'orlo e nascondeva la
  lingua.
- **La lingua centra il davanti ed e' un pezzo vero.** E' larga (~10 cm alla
  bocca), scende fin quasi all'orlo con una punta netta e i due veli
  frontali si aprono ai suoi lati lasciando una tacca profonda, come nel
  disegno. Prima era una striscia nascosta sotto la staffa.
- **Il rombo grande sta sulla lingua.** Il simbolo piu' grande del disegno —
  un rombo con una croce interna, largo quanto la lingua — ora campeggia sul
  cartiglio sotto la punta della staffa. Prima il simbolo piu' grande (un
  cerchio con la croce) stava in alto, in un punto dove nel disegno il cuoio
  e' liscio.
- **Catena dorata piu' sobria.** Sulla staffa restano un piccolo rombo a
  meta' discesa, una barretta, l'asta lunga e sottile col rombo al centro e
  il filetto dorato sui due bordi: niente piu' simboli ammucchiati nel tratto
  alto. I sigilli degli scialli sono scesi a meta' pannello (z ~ 0,77-0,62),
  dove li mette il disegno.
- **Cuoio per la staffa e la cintura.** Nel disegno il nastro che passa
  dietro l'anello e prosegue nella staffa e' un cuoio bruno medio, ben piu'
  chiaro della lana scura degli scialli: ora ha un suo materiale
  (`DRESS1_Leather`) con grana fine, e si stacca dai veli anche in controluce.
- **Anello piu' piccolo e schiacciato.** Come nel disegno la fibbia e'
  leggermente piu' larga che alta e misura ~6,8 cm.
- **Solo il capo.** Gambe, piedi, caviglie fasciate e sandali non ci sono:
  `DRESS1` e' un asset di abbigliamento da montare su un personaggio. La
  fodera interna chiude il capo, quindi guardando sotto l'orlo non si vede un
  guscio vuoto. L'origine resta a terra, sotto l'orlo, come se il vestito
  fosse indossato.
- **Fascia in vita.** Corpo in lino con pieghe a spirale (solchi veri nella
  mesh) che si stringono verso l'anello, bordino superiore arrotolato, teli
  in croce con estremita' assottigliate che rientrano sotto gli altri strati
  e il nodo sull'anello. Sotto i teli corre la cintura di cuoio diagonale che
  prosegue nella staffa.
- **LOD a tre livelli.** Le griglie nascono gia' alla densita' del LOD0 e i
  gruppi `keep` / `mid` proteggono ricami, staffa e bordi vivi: le pieghe e i
  simboli restano leggibili anche nei LOD.

## File

| File | Contenuto |
|---|---|
| `DRESS1.blend` | Scena Blender, mesh e texture incorporate; gruppi `keep` e `mid` per i dettagli |
| `DRESS1.glb` | glTF 2.0 autonomo, **79.224 triangoli** |
| `DRESS1_LOD1.glb` | **31.758 triangoli**, texture a metà risoluzione |
| `DRESS1_LOD2.glb` | **11.406 triangoli**, texture a un quarto di risoluzione |
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
| `DRESS1_Linen` | Gonna, falde, lingua, fascia e teli in croce |
| `DRESS1_Wool` | Scialli laterali |
| `DRESS1_Leather` | Staffa, cintura e retro della fibbia |
| `DRESS1_Gold` | Anello d'ottone e placchetta di attacco |
| `DRESS1_GoldTrim` | Ricami e simboli dorati, rombo grande compreso |

Le tre superfici testurizzate usano base color, normal e ORM a **1024²**;
l'AO è bakeata a 1024² con 32 campioni. In `DRESS1_tex/` l'AO è separata
dalle mappe ORM; nei GLB viene incorporata nel canale R delle mappe
occlusion/metallic-roughness. Le texture dei LOD sono ridimensionate.

Il capo misura **93,3 cm** in altezza (dalla punta più bassa al bordo della
fascia), circa **60,2 cm** in larghezza e **51,2 cm** in profondità.
L'origine è a terra, sotto l'orlo: il vestito occupa la stessa quota che
avrebbe indossato, quindi **la punta più bassa sta a 15,0 cm da terra**. In
Blender l'asse verticale è Z, mentre i GLB sono esportati Y-up. L'FBX usa
Z-up e direzione frontale −Y.

## Pipeline e verifiche

La ricostruzione è riproducibile con Blender 4.5 LTS e il modulo Python
`bpy`: vedi [`tools/README.md`](tools/README.md). I test in `tests/`
controllano le pieghe, la fodera che chiude il capo, l'assenza di anatomia,
la posizione della staffa rispetto alle falde, la catena dorata e il rombo
della lingua, lo spessore sotto i ricami e la reimportazione dei GLB e
dell'FBX. `tools/06_validate.py` verifica inoltre dimensioni, materiali, UV,
texture incorporate e budget dei LOD.
