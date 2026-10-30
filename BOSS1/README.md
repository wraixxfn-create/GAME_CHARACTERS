# BOSS1 — Demone Cornuto (game-ready)

Personaggio ricavato dal modello grezzo `ImageToStl.com_monster+3d+model.blend`
(export Tripo da 500.022 triangoli, senza rig, con 3 texture 4K) e portato a
standard da videogioco: mesh ottimizzata, UV preservate, materiale PBR
ottimizzato, scheletro da 34 ossa e tre animazioni pronte per il motore.

| | prima (sorgente) | dopo (`BOSS1.*`) |
|---|---|---|
| triangoli | 501.022 | **60.000** (-88%) |
| vertici | 250.499 | 37.413 |
| texture | 3 × 4096² PNG/JPG (~poche decine di MB) | 4 × 1024² JPEG |
| scheletro | – | 34 ossa, max 4 influenze/vertice |
| animazioni | – | `BOSS1_Idle`, `BOSS1_Roar`, `BOSS1_Attack` |
| dimensioni file | 25,5 MB (.blend) | 3,3 MB .blend / 2,8 MB .glb / 3,5 MB .fbx |

![hero](preview/hero_roar.png)

## File

| file | contenuto |
|---|---|
| `BOSS1.blend` | scena completa: mesh skinnata, rig, 3 azioni, texture impacchettate |
| `BOSS1.glb` | glTF 2.0 con skin + tutte e 3 le animazioni (motori web, Unity, Unreal, Godot) |
| `BOSS1.fbx` | FBX binary con skin + 3 take d'animazione (Unity/Unreal/3ds Max) |
| `preview/` | render di presentazione e GIF delle animazioni |
| `tools/` | pipeline riproducibile (vedi `tools/README.md`) |

Anteprime: `preview/turnaround.png` (4 viste), `preview/hero_idle.png`,
`preview/anim_idle.gif`, `preview/anim_roar.gif`.

## Specifiche tecniche

**Mesh** — 60.000 triangoli, 37.413 vertici, 1 UV set (`UVMap`), normali
ricalcolate con Weighted Normal per conservare gli spigoli delle spine, shading
smooth. Un solo materiale. Le UV originali sono intatte, quindi le texture
restano quelle dell'autore (ridimensionate): nessun bake, nessuna perdita.

**Materiale** (`BOSS1_MAT`) — PBR glTF-safe:

- `baseColor` 1024² JPEG
- `normal` (tangent space) 1024² JPEG
- `metallicRoughness` (ORM, verde = roughness, blu = metallic) 1024² JPEG
- `emissive` 1024² JPEG generata dai pixel della basecolor: le zone di carne
  (canale rosso dominante) moltiplicate per un rumore multi-scala diventano
  **vene incandescenti** che pulsano con un'intensità emissiva di 2.5
  (`KHR_materials_emissive_strength`).

Tutti i nodi del materiale sono mappabili in glTF: il `.glb` renderizza
esattamente come il `.blend`.

**Rig** — 34 ossa:

```
root
└─ hips ─ spine ─ chest ─ neck ─ head ─ jaw
   │                        └─ halo_base ─ halo_mid ─ halo_tip   (aureola di spine)
   ├─ clavicle.L/R ─ upperarm ─ forearm ─ hand ─ claw_a/b/c
   ├─ thigh.L/R ─ shin ─ foot ─ toe
   └─ tail_01 ─ tail_02
```

Pesi con heat map automatica, poi correzioni manuali sulle regioni isolate
(aureola, coda), limite a 4 influenze per vertice e normalizzazione: pronto per
Unity/Unreal senza re-import dei pesi.

**Animazioni** (30 fps, loop `Idle`):

| azione | frame | durata | note |
|---|---|---|---|
| `BOSS1_Idle` | 1–120 | 4,0 s | respiro, oscillazione del peso, artigli che si aprono, aureola che ondeggia — loop perfetto |
| `BOSS1_Roar` | 1–72 | 2,4 s | si carica, si solleva e apre le mascelle (aggro/telegraph) |
| `BOSS1_Attack` | 1–60 | 2,0 s | fendente con l'artiglio destro con controbilanciamento del braccio sinistro |

Le azioni sono esportate sia come clip glTF sia come take FBX (`bake_anim_use_all_actions`).

## Come è stato fatto

1. **Landmark anatomici automatici** — voxel fill della mesh a 1,2 cm,
   distance transform, grafo 26-connesso pesato con l'inverso del clearance
   (medial axis) e cammini minimi dal bacino verso mani, piedi, testa e cima
   dell'aureola. Spalle, gomiti, polsi, anche, ginocchia e talloni vengono da
   quei cammini: le ossa sono dentro il volume del corpo, non posizionate a occhio.
2. **Ottimizzazione** — decimation collapse con UV preservate, poi Weighted Normal.
3. **Rig + skinning** — armatura costruita sui landmark, pesi automatici e
   ritocchi per regione.
4. **Animazione** — pose chiave in coordinate locali delle ossa, interpolazione
   Bezier auto-clamped, primo e ultimo frame identici sull'idle.
5. **Materiale** — downscale delle texture, rimappatura dei canali in ORM,
   generazione della mappa emissiva.
6. **Export** — `.blend` compresso con texture impacchettate, GLB con tutte le
   action, FBX binary con take multiple.

Tutti gli step sono in `tools/` e si rilanciano da zero in circa 15 secondi
(esclusi i render di anteprima).

## Note per il motore

- Scala metrica: il boss è alto **0,87 m** in unità Blender (come il file
  originale). Per un boss alto 3 m basta scalare l'oggetto root di ~3,45.
- Asse Y-up in export (glTF standard, FBX con `axis_up='Y'`): nessuna
  rotazione manuale in Unity/Unreal.
- Il nome dei materiali e delle ossa è già in convenzione `BOSS1_*`, `*.L/*.R`.
- Se serve un LOD1, la stessa decimation a `TARGET_TRIS = 20000` in
  `01_optimize.py` produce una versione alleggerita con lo stesso rig.
