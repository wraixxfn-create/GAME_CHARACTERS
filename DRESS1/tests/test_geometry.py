"""Regression checks for the procedural garment (run with Blender's bpy)."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys
import unittest

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("dress1_build", TOOLS / "01_build.py")
dress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dress)


class ShapeTests(unittest.TestCase):
    def test_garment_has_no_body_parts(self):
        # Il capo e' **solo** il vestito: niente gambe, piedi, caviglie o
        # sandali. Se qualcuno reintroduce queste funzioni, la mesh torna a
        # contenere anatomia.
        for name in ("build_legs", "build_feet", "build_legwraps",
                     "build_sandals", "build_bodice", "LEG_PROFILE",
                     "FOOT_SECTIONS"):
            self.assertFalse(hasattr(dress, name), name)

    def test_garment_is_waist_down_and_open_for_wearer(self):
        # Nessun corpetto: l'asset parte dalla vita. Il passaggio centrale
        # resta libero per il personaggio che lo indossa.
        self.assertLess(dress.WAIST_TOP_Z, 1.10)
        dress.reset_scene()
        names = {o.name for o in dress.build_all()}
        for forbidden in ("Bodice", "Sleeve", "Corset"):
            self.assertNotIn(forbidden, names)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        for ob in bpy.context.scene.objects:
            if ob.type != "MESH":
                continue
            tree = BVHTree.FromObject(ob, dg)
            hit, _, _, _ = tree.ray_cast(Vector((0, 0, 1.2)),
                                         Vector((0, 0, -1)), 1.1)
            self.assertIsNone(hit, ob.name)

    def test_skirt_is_a_wide_a_line(self):
        # Profilo ad A misurato sulla silhouette: si allarga scendendo e
        # all'orlo supera i 0,48 m di larghezza (0,51 m nella reference).
        widths = [dress.prof(z)[0] for z in (0.90, 0.75, 0.60, 0.45, 0.30)]
        self.assertEqual(widths, sorted(widths))
        self.assertGreater(2.0 * dress.prof(0.30)[0], 0.48)
        self.assertLess(2.0 * dress.prof(0.30)[0], 0.58)
        # il davanti e' piu' piatto del fianco, come un bacino maschile
        rx, ry = dress.prof(0.60)
        self.assertGreater(rx / ry, 1.15)

    def test_hem_is_even_and_above_the_tongues(self):
        # L'orlo della gonna e' quasi orizzontale: le punte lunghe vengono
        # dalle lingue del davanti, non da un orlo seghettato.
        zs = [dress.hem_z(math.tau * i / 72.0) for i in range(72)]
        self.assertLess(max(zs) - min(zs), 0.030)
        # orlo sopra la caviglia: la reference lascia scoperti piedi e sandali
        self.assertGreater(min(zs), 0.20)
        self.assertLess(max(zs), 0.30)
        for _name, _c, _hw, zbot, tip, _layer, _seed in dress.FALLS:
            self.assertLess(zbot - tip, min(zs) - 0.02)

    def test_pleats_are_fine_crisp_and_close_on_the_ring(self):
        # Piega larga e piatta in luce, valle netta in ombra; il passo sulla
        # reference e' di ~3 cm, cioe' 30-50 pieghe sul giro.
        self.assertGreaterEqual(dress.PLEAT_N, 36)
        self.assertLessEqual(dress.PLEAT_N, 52)
        self.assertGreaterEqual(dress.PLEAT_DEPTH, 0.008)
        self.assertLessEqual(dress.PLEAT_DEPTH, 0.020)
        xs = [i / 400.0 for i in range(400)]
        vals = [dress.drape_fold(x) for x in xs]
        self.assertAlmostEqual(max(vals), 1.0, places=3)
        self.assertAlmostEqual(min(vals), 0.0, places=3)
        crest = sum(1 for v in vals if v > 0.5) / len(vals)
        self.assertGreater(crest, 0.55)          # cresta larga
        # la derivata si annulla sulla cresta: faccia piatta, non campana
        d1 = abs(dress.drape_fold(0.505) - dress.drape_fold(0.495))
        d2 = abs(dress.drape_fold(0.84) - dress.drape_fold(0.80))
        self.assertLess(d1, d2)
        # le pieghe chiudono sul giro: stesso valore a 0 e a 2*pi
        seam = max(abs(dress.pleats(i * math.tau / 64.0, 0.6)
                       - dress.pleats(i * math.tau / 64.0 + math.tau, 0.6))
                   for i in range(64))
        self.assertLess(seam, 1e-9)

    def test_skirt_folds_survive_the_whole_drop(self):
        # Regressione: uno span di segno sbagliato azzerava skirt_disp.
        samples = [dress.skirt_disp(math.tau * i / 96.0, 0.60) for i in range(96)]
        self.assertGreater(max(abs(x) for x in samples), 0.004)
        top = max(abs(dress.skirt_disp(math.tau * i / 96.0, 0.92))
                  for i in range(96))
        low = max(abs(dress.skirt_disp(math.tau * i / 96.0, 0.34))
                  for i in range(96))
        # le pieghe nascono tirate sotto la fascia e si aprono scendendo
        self.assertLess(top, low * 0.75)

    def test_overlay_panels_hang_outside_the_skirt(self):
        dress.reset_scene()
        wraps = dress.build_overlays()
        self.assertEqual(len(wraps), len(dress.WRAPS))
        for ob in wraps:
            zs = [v.co.z for v in ob.data.vertices]
            self.assertGreater(max(zs), dress.SKIRT_TOP_Z - 0.02, ob.name)
            # non scendono sotto le lingue del davanti
            self.assertGreater(min(zs), 0.36, ob.name)
            # stanno **fuori** dalla superficie della gonna: nessun pezzo
            # affonda nella pieghettatura
            for v in list(ob.data.vertices)[::97]:
                base_r = dress.prof(dress.SKIRT_TOP_Z - 0.0)[0]
                _ = base_r
                self.assertGreater(math.hypot(v.co.x, v.co.y),
                                   dress.prof(max(v.co.z, 0.19))[1] * 0.95,
                                   ob.name)

    def test_panel_hems_are_pointed_not_flat(self):
        # Nel disegno le falde sono teli con **orli a punta**: la spezzata
        # dell'orlo deve avere almeno un angolo vivo (una punta che scende
        # di 3 cm sotto i due punti vicini), non essere una curva piatta.
        for spec in dress.WRAPS:
            hem = spec["hem"]
            points = [z for _u, z in hem]
            self.assertGreaterEqual(len(points), 5, spec["name"])
            dips = [i for i, z in enumerate(points)
                    if (i == 0 or points[i - 1] > z) and
                       (i == len(points) - 1 or points[i + 1] > z)]
            tips = [points[i] for i in dips
                    if max(points) - points[i] > 0.040]
            self.assertTrue(tips, spec["name"])
            # e l'orlo non e' una riga: c'e' almeno 5 cm fra punta e spalla
            self.assertGreater(max(points) - min(points), 0.050, spec["name"])

    def test_tongues_are_the_lowest_point(self):
        dress.reset_scene()
        tongues = dress.build_falls()
        self.assertEqual(len(tongues), len(dress.FALLS))
        for ob in tongues:
            zs = [v.co.z for v in ob.data.vertices]
            self.assertLess(min(zs), 0.26, ob.name)
        centre = [o for o in tongues if o.name == "Fall_C"][0]
        self.assertLess(min(v.co.z for v in centre.data.vertices), 0.21)
        # le lingue sono **strette**: una lingua larga legge come un pannello
        widths = []
        for _n, _c, hw, *_rest in dress.FALLS:
            widths.append(hw)
        self.assertLess(max(widths), math.radians(11.0))

    def test_dark_panels_sit_on_the_hips(self):
        # I pannelli scuri stanno sui fianchi, non sul davanti: la loro
        # larghezza resta sotto i 75 gradi di apertura per lato.
        specs = dress.drape_specs()
        self.assertEqual(len(specs), 2)
        for name, a0, a1, _ztab, _seed in specs:
            centre = abs(0.5 * (a0 + a1))
            self.assertGreater(centre, math.radians(55.0), name)
            self.assertLess(centre, math.radians(85.0), name)
            self.assertGreater(abs(a1 - a0), math.radians(50.0), name)
        # i due pannelli stanno ai due lati opposti
        self.assertLess(specs[0][1] * specs[1][1], 0.0)

    def test_panels_end_above_the_skirt_hem(self):
        # I pannelli scuri finiscono a meta' coscia: ben sopra l'orlo, e il
        # loro attacco resta nascosto dietro la cintura.
        for name, _a0, _a1, ztab, _seed in dress.drape_specs():
            self.assertGreater(min(z for _, z in ztab), dress.hem_z(0) + 0.10,
                               name)
            self.assertLess(max(z for _, z in ztab), dress.BELT_Z - 0.20, name)

    def test_dark_panels_are_clear_of_the_pleats(self):
        # Le creste del lino non devono trapassare la lana: ogni punto del
        # pannello sta **fuori** dalla superficie pieghettata della gonna,
        # comprese le creste (skirt_disp), con almeno 1,5 mm di margine.
        dress.reset_scene()
        _objs, panels = dress.build_drapes()
        self.assertEqual(len(panels), 2)
        for pnl in panels:
            for i in range(1, 12):
                u = i / 12.0
                for j in range(1, 10):
                    v = j / 10.0
                    a, z = pnl.params(u, v)
                    if min(u, 1.0 - u) < 0.12:
                        continue          # bordo vivo: rientra per disegno
                    p = pnl.pt(u, v)
                    crest = dress.surface(a, z, "base",
                                          extra=dress.skirt_disp(a, z))
                    self.assertGreater(math.hypot(p.x, p.y),
                                       math.hypot(crest.x, crest.y) + 0.0015,
                                       (pnl.name, u, v))

    def test_lining_closes_the_shell_above_the_hem(self):
        lining = dress.build_lining()[0]
        zs = [v.co.z for v in lining.data.vertices]
        self.assertLess(min(zs), 0.42)          # scende dentro la gonna
        self.assertGreater(min(zs), dress.hem_z(0) - 0.04)
        self.assertGreater(max(zs), 0.80)       # parte in alto, sotto la fascia
        # resta **dentro** la gonna: nessun punto sporge all'esterno
        for v in list(lining.data.vertices)[::17]:
            rx, ry = dress.prof(max(v.co.z, 0.19))
            self.assertLess(math.hypot(v.co.x, v.co.y), rx - 0.010)

    def test_ring_is_a_belt_buckle_not_a_wheel(self):
        ring = dress.build_ring()[0]
        xs = [v.co.x for v in ring.data.vertices]
        # 0,070 m di diametro esterno: nella reference l'anello misura 22 px
        # su una vita di 82 px, cioe' meno di un terzo della larghezza.
        self.assertLess(max(xs) - min(xs), 0.080)
        self.assertGreater(max(xs) - min(xs), 0.058)
        # il foro deve essere grande abbastanza per la staffa (3,4 cm)
        self.assertGreater(2.0 * (dress.RING_MAJOR - dress.RING_MINOR), 0.034)
        # e restare in avanti rispetto alla stoffa: la fibbia e' l'elemento
        # piu' avanzato del capo
        cloth_y = dress.sash_pt(0.0, dress.RING_Z).y
        self.assertLess(dress.RING_C.y, cloth_y - 0.012)

    def test_ring_hole_is_filled_by_a_dark_disc(self):
        # Senza il disco scuro, dentro la fibbia si vede lino chiaro e
        # l'anello sembra un occhiolino.
        disc = [o for o in dress.build_sash() if o.name == "Sash_KnotDark"][0]
        xs = [v.co.x for v in disc.data.vertices]
        self.assertGreater(max(xs) - min(xs),
                           2.0 * (dress.RING_MAJOR - dress.RING_MINOR))

    def test_crossed_bands_make_an_x_on_the_front(self):
        dress.reset_scene()
        sash = dress.build_sash()
        bands = [o for o in sash if o.name.startswith("Sash_Cross")]
        self.assertGreaterEqual(len(bands), 2)
        slopes = []
        for ob in bands:
            ys = [v.co.y for v in ob.data.vertices]
            self.assertLess(min(ys), -0.108)     # passano davanti alla vita
            zs = [v.co.z for v in ob.data.vertices]
            self.assertGreater(max(zs) - min(zs), 0.05)
            near = [(v.co.x, v.co.z) for v in ob.data.vertices
                    if v.co.y < -0.100 and abs(v.co.x) > 0.03]
            left = [z for x, z in near if x < 0]
            right = [z for x, z in near if x > 0]
            self.assertTrue(left and right)
            slopes.append(sum(right) / len(right) - sum(left) / len(left))
        # un telo sale e l'altro scende: e' la X della reference
        self.assertLess(slopes[0] * slopes[1], 0)

    def test_sash_edges_stay_inside_the_waist_block(self):
        # I teli incrociati non devono sporgere sopra il bordo alto della
        # fascia ne' scendere sotto l'attacco della gonna.
        for a in (-1.2, -0.6, 0.0, 0.6, 1.2):
            for sgn in (-1.0, 1.0):
                z = dress.cross_band_line(a, sgn)
                self.assertLess(z + dress.SASH_HALF, dress.WAIST_TOP_Z + 0.02)
                self.assertGreater(z - dress.SASH_HALF, dress.SASH_BOT_Z - 0.02)

    def test_strap_is_wide_and_ends_in_a_blunt_shield(self):
        # Nella reference il nastro e' largo ~3,7 cm e la punta e' uno scudo
        # con gli angoli tagliati, non un ago.
        self.assertGreater(dress.strap_halfwidth(dress.STRAP_SHOULDER_Z), 0.016)
        self.assertLess(dress.strap_halfwidth(dress.STRAP_SHOULDER_Z), 0.021)
        self.assertGreater(dress.strap_halfwidth(dress.STRAP_TIP_Z + 0.004),
                           0.014)
        self.assertLess(dress.strap_bottom_z(1.0) - dress.strap_bottom_z(0.0),
                        0.060)
        # intaglio sul centro: al centro il bordo sale di ~1 cm
        self.assertGreater(dress.strap_bottom_z(0.0), dress.strap_bottom_z(0.35))
        self.assertLess(dress.strap_bottom_z(0.0) - dress.strap_bottom_z(0.35),
                        0.014)

    def test_gold_motif_is_built_on_the_strap(self):
        dress.reset_scene()
        gold = dress.strap_gold()
        self.assertGreaterEqual(len(gold), 10)
        names = " ".join(o.name for o in gold)
        for part in ("circle", "dia1", "dia2", "tipV1", "tipFill"):
            self.assertIn(part, names)
        # gli ultimi simboli devono stare sopra la punta del nastro, non
        # oltre: nessun ricamo che sporge nel vuoto
        tip = dress.strap_bottom_z(0.0)
        for ob in gold:
            zs = [v.co.z for v in ob.data.vertices]
            self.assertGreater(min(zs), tip - 0.004, ob.name)
            self.assertLess(max(zs), dress.STRAP_TOP_Z + 0.004, ob.name)

    def test_strap_sits_in_front_of_every_layer(self):
        dress.reset_scene()
        strap = dress.build_strap()[0][0]
        wraps = dress.build_overlays()
        tongues = dress.build_falls()
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        strap_tree = BVHTree.FromObject(strap, dg)
        others = [(o.name, BVHTree.FromObject(o, dg))
                  for o in wraps + tongues]
        for z in (0.46, 0.50, 0.56, 0.66, 0.76, 0.86, 0.91):
            half = dress.strap_halfwidth(z)
            for fraction in (-0.7, -0.35, 0.0, 0.35, 0.7):
                origin = Vector((fraction * half, -1.0, z))
                direction = Vector((0, 1, 0))
                p, _, _, _ = strap_tree.ray_cast(origin, direction, 2.0)
                self.assertIsNotNone(p, (z, fraction))
                for name, tree in others:
                    other, _, _, _ = tree.ray_cast(origin, direction, 2.0)
                    if other is not None:
                        self.assertLess(p.y, other.y + 0.0002,
                                        (z, fraction, name))

    def test_every_piece_gets_a_material(self):
        # Regressione: in una versione precedente cintura e teli restavano
        # senza materiale e nel render comparivano grigi.
        dress.reset_scene()
        for ob in dress.build_all():
            self.assertTrue(ob.data.materials, ob.name)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
