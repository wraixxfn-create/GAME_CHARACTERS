# BOSS1 — Demone Cornuto (game-ready)

Personaggio ricavato dal modello grezzo `ImageToStl.com_monster+3d+model.blend`
(export Tripo da 501.022 triangoli, senza rig) e portato a standard da
videogioco: mesh ottimizzata con densita' adattiva, UV originali preservate,
materiale PBR con AO bakeata, scheletro da 34 ossa con skinning geodesico,
cinque animazioni, tre livelli di dettaglio e QA automatica.

![hero](preview/hero_roar.png)

## Cosa e' cambiato nella v2

| | v1 | **v2** |
|---|---|---|
| triangoli | 60.000, decimation uniforme | **80.000**, densita' adattiva (piu' facce su testa, aureola, artigli) e simmetria X |
| skinning | pesi automatici "bone heat" + correzioni a mano | **distanza geodesica** sulla superficie, smoothing laplaciano, 4 influenze |
| animazioni | 3 (`Idle`, `Roar`, `Attack`) | **5**: aggiunte `Walk` (loop) e `Death`, rotazioni in **assi mondo** e quaternioni |
| texture | 3 × 1024² JPEG | basecolor e normal **2048²**, ORM 1024², emissive 1024² |
| materiale | ORM senza occlusione | **AO bakeata** nell'ORM (`R=AO, G=roughness, B=metallic`) via nodo `glTF Material Output` |
| vene emissive | 3 sinusoidi | rumore **fBm** a 4 ottave su maschera "carne", copertura 6,5% |
| scala | 0,868 m (da scalare a mano) | **2,90 m**, unita' metriche, mesh e traslazioni del root riscalate |
| LOD | – | `BOSS1_LOD1.glb` (40%) e `BOSS1_LOD2.glb` (12%) |
| QA | – | `tools/07_validate.py` -> [`QA.md`](QA.md) |
| bug noti v1 | `Attack`/`Roar` distorti; il `root` ruotato dalla `Death` "sporcava" le altre clip; mappa ORM nera in export | risolti |

## Prima / dopo

| | prima (sorgente) | dopo (`BOSS1.*`) |
|---|---|---|
| triangoli | 501.022 | **80.000** (-84%) |
| vertici | 250.499 | 45.926 (nello `.glb`, dopo lo split delle UV) |
| texture | 3 × 4096² PNG/JPG (~decine di MB) | 2048² + 2048² + 1024² + 1024² JPEG |
| scheletro | – | 34 ossa, max 4 influenze/vertice |
| animazioni | – | `BOSS1_Idle`, `BOSS1_Walk`, `BOSS1_Roar`, `BOSS1_Attack`, `BOSS1_Death` |
| altezza | 0,868 m | **2,90 m** |
| file | 25,5 MB (.blend) | 4,7 MB .blend / 4,2 MB .glb / 5,5 MB .fbx |

## File

| file | contenuto |
|---|---|
| `BOSS1.blend` | scena completa: mesh skinnata, rig, 5 azioni, texture impacchettate |
| `BOSS1.glb` | glTF 2.0, LOD0, skin + 5 clip (web, Unity, Unreal, Godot) |
| `BOSS1_LOD1.glb` | 32.000 triangoli, stesso rig e stesse clip |
| `BOSS1_LOD2.glb` | 9.600 triangoli, per istanze lontane |
| `BOSS1.fbx` | FBX binary con skin + 5 take d'animazione |
| `QA.md` | report di validazione generato da `tools/07_validate.py` |
| `preview/` | render di presentazione e GIF delle animazioni |
| `tools/` | pipeline riproducibile (vedi `tools/README.md`) |

Anteprime:

| file | cosa mostra |
|---|---|
| `preview/hero_roar.png` | posa del ruggito, luce da boss fight |
| `preview/hero_idle.png` | vista frontale, aureola e silhouette completa |
| `preview/hero_head.png` | primo piano: dettaglio delle spine, AO e vene emissive |
| `preview/turnaround.png` | 4 viste affiancate su fondo neutro |
| `preview/detail_compare.png` | confronto v1 (60k uniformi) / v2 (80k adattivi) |
| `preview/anim_*.gif` | `idle`, `walk`, `roar`, `attack`, `death` |

## Specifiche tecniche

**Mesh** — 80.000 triangoli, 1 UV set (`UVMap`), un solo materiale, shading
smooth con normali pesate (le spine restano a spigolo vivo). Le UV originali
sono intatte: nessun bake, nessuna perdita d'autore.

La densita' non e' uniforme: un vertex group di dettaglio (curvatura locale +
zone "da primo piano") guida la `DECIMATE`, quindi testa, muso, aureola, mani e
artigli mantengono piu' risoluzione del torso, che e' quasi liscio. La
decimation usa `use_symmetry` sull'asse X, cosi' i due lati del corpo restano
identici e lo skinning e' simmetrico.

**Materiale** (`BOSS1_MAT`) — PBR glTF-safe, opaco, backface culling attivo:

| mappa | risoluzione | note |
|---|---|---|
| baseColor | 2048² JPEG | da sorgente 4K, nessuna alterazione di colore |
| normal (tangent space) | 2048² JPEG | dettaglio di spine, solchi e pori |
| ORM | 1024² JPEG | `R` = occlusione **bakeata con Cycles**, `G` = roughness, `B` = metallic |
| emissive | 1024² JPEG | vene incandescenti su maschera "carne", rumore fBm, strength 1.6 |

L'occlusione e' collegata anche al nodo `glTF Material Output`, che e' quello
che l'exporter usa per scrivere `occlusionTexture`: senza, l'AO resterebbe
dentro il `.blend` e fuori dal `.glb`.

**Rig** — 34 ossa (33 deformanti):

```
root
└─ hips ─ spine ─ chest ─ neck ─ head ─ jaw
   │                        └─ halo_base ─ halo_mid ─ halo_tip   (aureola di spine)
   ├─ clavicle.L/R ─ upperarm ─ forearm ─ hand ─ claw_a/b/c
   ├─ thigh.L/R ─ shin ─ foot ─ toe
   └─ tail_01 ─ tail_02
```

Ogni vertice pesa su **massimo 4 ossa**, con pesi normalizzati a 1. Il calcolo
non usa i pesi automatici di Blender ma la distanza **geodesica** sulla mesh:
seed per osso, multi-source Dijkstra sul grafo degli edge, peso `1/d⁴`, smoothing
laplaciano (6 iterazioni). Su una creatura accovacciata — mani a terra accanto ai
piedi, aureola appoggiata alla schiena — e' la differenza tra uno skinning che
segue l'anatomia e uno che "tira" i vertici sbagliati.

**Animazioni** (30 fps):

| azione | frame | durata | loop | note |
|---|---|---|---|---|
| `BOSS1_Idle` | 0–120 | 4,00 s | si | respiro, oscillazione del peso, artigli, aureola e coda sfasati |
| `BOSS1_Walk` | 0–40 | 1,33 s | si | andatura da knuckle-walker **in place** (root motion a carico del motore), doppio bob |
| `BOSS1_Roar` | 0–84 | 2,80 s | no | carica, si alza, mascelle aperte, tremore, rientro |
| `BOSS1_Attack` | 0–54 | 1,80 s | no | caricamento, fendente destro con controbilanciamento, recupero |
| `BOSS1_Death` | 0–96 | 3,20 s | no | colpo, gambe che cedono, crollo sul fianco, mascella inerte |

Le rotazioni sono definite in **assi mondo** (`X` fianco, `Y` profondita',
`Z` alto) e convertite nello spazio della singola osso:
`Q = M_rest⁻¹ · R_mondo · M_rest`. I keyframe usano quaternioni con continuita'
di segno, e ogni clip definisce tutte le ossa: non ci sono canali "ereditati"
da un'azione precedente.

## Come e' stato fatto

1. **Ottimizzazione adattiva** — punteggi di curvatura sulla mesh high-poly +
   boost su testa/aureola/mani/piedi, decimation pesata e simmetrica a 80k,
   pulizia, normali pesate.
2. **Landmark e rig** — scheletro costruito sulle landmark anatomiche
   (medial axis + cammini minimi), poi skinning geodesico.
3. **Animazione** — pose chiave in assi mondo, quaternioni, Bezier
   auto-clamped, primo e ultimo frame identici su `Idle` e `Walk`.
4. **Materiale** — downscale selettivo, bake AO su Cycles, ORM impacchettato,
   emissive generata dai pixel della basecolor.
5. **Export** — scala a 2,90 m coerente tra mesh, ossa e traslazioni, poi
   `.blend`, `.glb`, `.fbx` e i due LOD.
6. **QA** — `07_validate.py` controlla i `.glb` senza Blender (triangoli,
   joint, influenze, durate, chiusura dei loop, canali PBR, dimensioni texture)
   e scrive `QA.md`.

Tutti gli step sono in `tools/` e si rilanciano da zero in meno di un minuto.

## Note per il motore

- **Scala metrica**: 2,90 m di altezza, 1 unita' = 1 metro. Nessuna scala da
  applicare all'import.
- **Y-up** negli export (glTF standard, FBX con `axis_up='Y'`): nessuna
  rotazione manuale in Unity/Unreal.
- **LOD**: 80k / 32k / 9,6k triangoli, stesso scheletro e stesse clip: si
  possono swappare a runtime senza rimappare nulla.
- **Materiale**: un solo materiale, cinque mappe, nessuna estensione esotica
  (`KHR_materials_emissive_strength`, `KHR_materials_ior`,
  `KHR_materials_specular`, tutte supportate dai motori moderni).
- **Root motion**: `Walk` e' in place; `Attack`, `Roar` e `Death` hanno
  traslazioni sul `root` (lunge del colpo, crollo) gia' scalate in metri.
- I nomi di materiale, ossa e azioni sono gia' in convenzione `BOSS1_*`,
  `*.L/*.R`.
