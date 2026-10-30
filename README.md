# GAME_CHARACTERS

Modelli di personaggi per videogiochi, lavorati per essere pronti al motore.

| personaggio | stato | file |
|---|---|---|
| **BOSS1** — Demone Cornuto | game-ready: 80k tri, rig 34 ossa, 5 animazioni, PBR 2K + AO, LOD1/LOD2, scala 2,90 m | [BOSS1/](BOSS1/) → `BOSS1.blend`, `BOSS1.glb`, `BOSS1.fbx`, `BOSS1_LOD1.glb`, `BOSS1_LOD2.glb` |

## BOSS1 in breve

- 501.022 → **80.000** triangoli, densita' adattiva (piu' dettaglio su testa,
  aureola e artigli) e simmetria X; UV originali intatte
- scheletro 34 ossa con **skinning geodesico**, max 4 influenze, pesi normalizzati
- 5 clip a 30 fps: `BOSS1_Idle`, `BOSS1_Walk` (loop, in place), `BOSS1_Roar`,
  `BOSS1_Attack`, `BOSS1_Death`
- materiale PBR glTF-safe: basecolor e normal 2K, ORM con **AO bakeata**,
  vene emissive
- scala metrica reale (**2,90 m**), export Y-up, LOD1 (32k) e LOD2 (9,6k)
- QA automatica dei file esportati in [`BOSS1/QA.md`](BOSS1/QA.md)
- pipeline riproducibile in `BOSS1/tools/`

![BOSS1](BOSS1/preview/hero_roar.png)

Confronto della densita' di triangoli tra la v1 (60k uniformi) e questa
versione (80k adattivi): `BOSS1/preview/detail_compare.png`.
