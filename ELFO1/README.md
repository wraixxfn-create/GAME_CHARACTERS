# ELFO1 — Elfo Runico (game-ready)

Personaggio ricavato dal modello grezzo
`ImageToStl.com_elf+character+3d+model(1).blend` (339.022 triangoli, nessun rig,
tre texture 4096^2) e portato a standard da videogioco: mesh ottimizzata con
densita' adattiva, UV originali intatte, materiale PBR con AO bakeata e rune
emissive, scheletro da 43 ossa con skinning geodesico, cinque animazioni, tre
livelli di dettaglio e QA automatica.

![hero](preview/hero_cast.png)

## Cosa e' cambiato

| | sorgente (Tripo) | **ELFO1** |
|---|---|---|
| triangoli | 339.022 | **55.000**, densita' adattiva (viso, orecchie, ciocche, mani e falde del gonnellone) e simmetria X |
| vertici | 168.853 | 26.842 (40.408 nello `.glb`, dopo lo split delle UV) |
| materiale | basecolor + RM + normal, nessuna occlusione | **PBR glTF-safe**: basecolor 2048, normal 2048, ORM 1024 con **AO bakeata**, emissive 1024 con le **rune accese** |
| scheletro | – | **43 ossa** (42 deformanti), max 4 influenze per vertice, skinning **geodesico** |
| animazioni | – | **5 clip** a 30 fps: `Idle`, `Walk`, `Run`, `Cast`, `Death` |
| scala | 1,0 unita' (~1,85 m solo per caso) | **1,85 m** metrici, unita' = metro, nessuna scala da applicare all'import |
| LOD | – | `ELFO1_LOD1.glb` (35%, 19.250 tri) e `ELFO1_LOD2.glb` (12%, 6.600 tri) |
| file | 18,6 MB `.blend` non compresso | 3,7 MB `.blend` / 3,7 MB `.glb` / 4,8 MB `.fbx` |
| QA | – | `tools/07_validate.py` → [`QA.md`](QA.md) |

## File

| file | contenuto |
|---|---|
| `ELFO1.blend` | scena completa: mesh skinnata, rig, 5 azioni, texture impacchettate |
| `ELFO1.glb` | glTF 2.0, LOD0, skin + 5 clip (web, Unity, Unreal, Godot) |
| `ELFO1_LOD1.glb` | 19.250 triangoli, stesso rig e stesse clip |
| `ELFO1_LOD2.glb` | 6.600 triangoli, per istanze lontane |
| `ELFO1.fbx` | FBX binary con skin + 5 take d'animazione |
| `QA.md` | report di validazione generato da `tools/07_validate.py` |
| `preview/` | render di presentazione e GIF delle animazioni |
| `tools/` | pipeline riproducibile (vedi [`tools/README.md`](tools/README.md)) |

Anteprime:

| file | cosa mostra |
|---|---|
| `preview/hero_cast.png` | posa del lancio, luce fredda e rim lunare |
| `preview/hero_idle.png` | tre quarti, rune accese e silhouette completa |
| `preview/hero_head.png` | primo piano: viso, orecchie a punta, ciocche, rune |
| `preview/turnaround.png` | 4 viste affiancate su fondo neutro |
| `preview/detail_compare.png` | sorgente 339k contro LOD0 55k, stesso primo piano |
| `preview/anim_*.gif` | `idle`, `walk`, `run`, `cast`, `death` |

## Specifiche tecniche

**Mesh** — 55.000 triangoli, 1 UV set (`UVMap`), un solo materiale, shading
smooth con normali pesate. Le UV originali sono intatte: nessun bake, nessuna
perdita d'autore.

La densita' non e' uniforme. Un vertex group di dettaglio (curvatura locale +
zone "da primo piano") guida la `DECIMATE`: il viso, le orecchie a punta, le
ciocche e le falde del gonnellone mantengono piu' risoluzione della pelle del
torso e delle braccia, che sono quasi lisce. La decimation usa `use_symmetry`
sull'asse X, quindi i due lati restano identici e lo skinning e' simmetrico.

Distribuzione finale dei triangoli per fascia di altezza:

| fascia | triangoli |
|---|---|
| piedi e caviglie (0,00–0,15) | 2.203 |
| gonnellone (0,15–0,35) | 14.136 |
| bacino e mani (0,35–0,55) | 9.605 |
| busto e spalle (0,55–0,75) | 6.728 |
| collo, viso, orecchie (0,75–0,90) | 15.142 |
| chioma e cresta (0,90–1,00) | 7.186 |

**Materiale** (`ELFO1_MAT`) — PBR glTF-safe:

| mappa | risoluzione | note |
|---|---|---|
| baseColor | 2048² JPEG | da sorgente 4K, nessuna alterazione di colore |
| normal (tangent space) | 2048² JPEG | ciocche, pieghe del viso, rune in rilievo |
| ORM | 1024² JPEG | `R` = occlusione **bakeata con Cycles**, `G` = roughness, `B` = metallic |
| emissive | 1024² JPEG | rune incandescenti su maschera ricavata dai pixel, strength 2,2 |

L'occlusione e' collegata anche al nodo `glTF Material Output`: e' quello che
l'exporter usa per scrivere `occlusionTexture`, senza resterebbe dentro il
`.blend` e fuori dal `.glb`.

Il materiale e' **double-sided** (`doubleSided: true`): il gonnellone e le
ciocche sono fogli aperti, non solidi. I render di anteprima ribaltano la
normale sulle facce posteriori, cosi' la fodera interna del tessuto non si vede
nera.

**Rig** — 43 ossa (42 deformanti):

```
root
└─ hips ─ spine_01 ─ spine_02 ─ chest ─ neck ─ head
   │                              │              ├─ hair_crest
   │                              │              ├─ hair_back_01 ─ 02 ─ 03
   │                              │              └─ hair_side_01.L/R ─ 02
   │                              └─ clavicle.L/R ─ upperarm ─ forearm ─ hand ─ fingers / thumb
   ├─ thigh.L/R ─ shin ─ foot ─ toe
   └─ skirt_front_01 ─ 02,  skirt_back_01 ─ 02,  skirt_01.L/R ─ 02
```

Ogni vertice pesa su **massimo 4 ossa**, con pesi normalizzati a 1. Il calcolo
non usa i pesi automatici di Blender ma la distanza **geodesica** sulla mesh:
seed per osso, multi-source Dijkstra sul grafo degli edge, peso `1/d⁴`, smoothing
laplaciano (6 iterazioni). Su un personaggio vestito fa la differenza: il
gonnellone e' a pochi centimetri dalle cosce ma **lontano sulla superficie**
(bisogna risalire fino alla vita), quindi la stoffa la prendono le ossa della
gonna e le gambe muovono solo cio' che toccano davvero.

**Animazioni** (30 fps):

| azione | frame | durata | loop | note |
|---|---|---|---|---|
| `ELFO1_Idle` | 0–120 | 4,00 s | si | respiro a 2 cicli, trasferimento di peso, testa che si guarda intorno, ciocche e falde in ritardo |
| `ELFO1_Walk` | 0–36 | 1,20 s | si | passo umano **in place** (root motion a carico del motore), doppio bob, contro-rotazione del busto, braccia in opposizione |
| `ELFO1_Run` | 0–24 | 0,80 s | si | falcata lunga, busto inclinato in avanti, braccia a 90° che pompano |
| `ELFO1_Cast` | 0–72 | 2,40 s | no | raccolta dell'energia, apertura delle braccia, spinta dei palmi, rientro |
| `ELFO1_Death` | 0–90 | 3,00 s | no | colpo, ginocchia che cedono, caduta all'indietro, assestamento a terra |

Le rotazioni sono definite in **assi mondo** (`X` = beccheggio, `Y` = rollio,
`Z` = imbardata) e convertite nello spazio della singola osso:
`Q = M_rest⁻¹ · R_mondo · M_rest`. I keyframe usano quaternioni con continuita'
di segno e ogni clip definisce **tutte** le ossa: non ci sono canali "ereditati"
da un'azione precedente.

I cicli (`Idle`, `Walk`, `Run`) sono generati campionando una funzione di fase,
quindi il primo e l'ultimo frame coincidono per costruzione: il loop e' chiuso
senza aggiustamenti a mano. Nella `Death` il `root` ruota e trasla, e ogni
frame chiave viene appoggiato al pavimento misurando il punto piu' basso della
mesh in posa.

## Come e' stato fatto

1. **Ottimizzazione adattiva** — punteggi di curvatura sulla mesh high-poly +
   boost su viso/ciocche/mani/piedi/tessuto, decimation pesata e simmetrica a
   55k, pulizia, normali pesate.
2. **Rig e skinning** — armatura da 43 ossa costruita su landmark anatomici,
   poi skinning geodesico con maschere per capelli e gonnellone.
3. **Animazione** — pose chiave in assi mondo, quaternioni, Bezier
   auto-clamped, cicli chiusi per costruzione, caduta appoggiata al suolo.
4. **Materiale** — downscale selettivo, bake AO su Cycles, ORM impacchettato,
   emissive generata dalle rune dipinte.
5. **Export** — scala a 1,85 m coerente tra mesh, ossa e traslazioni, poi
   `.blend`, `.glb`, `.fbx` e i due LOD.
6. **QA** — `07_validate.py` controlla i `.glb` senza Blender (triangoli, joint,
   influenze, durate, chiusura dei loop, canali PBR, dimensioni texture, altezza)
   e scrive `QA.md`.

Tutti gli step sono in `tools/` e si rilanciano da zero in meno di un minuto
(i render di anteprima esclusi).

## Note per il motore

- **Scala metrica**: 1,85 m di altezza, 1 unita' = 1 metro. Nessuna scala da
  applicare all'import.
- **Y-up** negli export (glTF standard, FBX con `axis_up='Y'`): nessuna
  rotazione manuale in Unity/Unreal.
- **LOD**: 55k / 19,2k / 6,6k triangoli, stesso scheletro e stesse clip: si
  possono swappare a runtime senza rimappare nulla.
- **Materiale**: un solo materiale, quattro mappe, double-sided. Nessuna
  estensione esotica oltre a `KHR_materials_emissive_strength`.
- **Root motion**: `Walk` e `Run` sono in place; `Cast` ha una piccola
  traslazione del `root` (passo in avanti), `Death` ha rotazione e traslazione
  del `root` gia' scalate in metri e appoggiate al pavimento.
- Nomi di materiale, ossa e azioni gia' in convenzione `ELFO1_*`, `*.L`/`*.R`.
- Le ossa `hair_*` e `skirt_*` sono **secondarie**: se un motore usa un rig
  semplificato si possono togliere senza toccare la gerarchia principale.
