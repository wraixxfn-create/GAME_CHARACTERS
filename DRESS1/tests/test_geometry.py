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
    def test_skirt_folds_continue_to_the_hem(self):
        # Regression: the old negative span made skirt_disp identically zero.
        samples = [dress.skirt_disp(a, 0.60) for a in (0.1, 0.3, 0.7, 1.2)]
        self.assertGreater(max(abs(x) for x in samples), 0.005)
        # le pieghe chiudono sul giro: stesso valore a 0 e a 2*pi. La piccola
        # deriva lungo la caduta e' volutamente non periodica (e' la
        # piegolina fine), quindi si confronta il profilo della piega.
        seam = max(abs(dress.pleats(i * math.tau / 64.0, 0.6)
                       - dress.pleats(i * math.tau / 64.0 + math.tau, 0.6))
                   for i in range(64))
        self.assertLess(seam, 1e-9)

    def test_reference_drapes_end_above_lower_skirt(self):
        # The dark side panels should frame the hips, not run to the hem.
        for _, _, heights, _, _ in dress.drape_specs():
            self.assertGreaterEqual(heights[-1][1], 0.44)
            # la punta resta ben sopra l'orlo: gli scialli incorniciano il
            # fianco, non scendono fino in fondo
            self.assertGreater(heights[-1][1] - dress.hem_z(0), 0.16)

    def test_reference_buckle_is_delicate(self):
        ring = dress.build_ring()[0]
        xs = [v.co.x for v in ring.data.vertices]
        # diametro esterno ~7,4 cm: nel disegno l'anello e' grande quanto
        # mezza vita, ma non fino a sembrare un cerchione
        self.assertLess(max(xs) - min(xs), 0.082)
        self.assertGreater(max(xs) - min(xs), 0.066)

    def test_garment_has_no_body_parts(self):
        # Il capo e' **solo** il vestito: niente gambe, piedi, caviglie o
        # sandali. Queste funzioni non esistono piu' e, se qualcuno le
        # reintroduce, la mesh torna a contenere anatomia.
        for name in ("build_legs", "build_feet", "build_legwraps",
                     "build_sandals", "LEG_PROFILE", "FOOT_SECTIONS"):
            self.assertFalse(hasattr(dress, name), name)

    def test_lining_closes_the_garment(self):
        # Senza fodera, guardando sotto l'orlo si vede il guscio vuoto.
        lining = dress.build_lining()[0]
        zs = [v.co.z for v in lining.data.vertices]
        radii = [max(abs(v.co.x), abs(v.co.y)) for v in lining.data.vertices]
        self.assertLess(min(zs), 0.45)          # scende dentro la gonna
        self.assertLess(max(radii), 0.20)       # e si stringe verso l'interno
        self.assertGreater(max(zs), 0.60)       # parte in alto, sotto la fascia

    def test_drape_folds_have_round_crests_and_narrow_valleys(self):
        # Nella reference le pieghe sono campate morbide: cresta tonda e
        # larga, valle stretta in ombra. Una sinusoide le avrebbe uguali
        # (stoffa gonfia), una piega a coltello avrebbe la faccia dritta.
        xs = [i / 400.0 for i in range(400)]
        vals = [dress.drape_fold(x) for x in xs]
        self.assertAlmostEqual(max(vals), 1.0, places=3)
        self.assertAlmostEqual(min(vals), 0.0, places=3)
        crest = sum(1 for v in vals if v > 0.5) / len(vals)
        valley = sum(1 for v in vals if v < 0.5) / len(vals)
        self.assertGreater(crest, 0.55)   # cresta larga
        self.assertLess(valley, 0.45)     # valle stretta
        # poche pieghe profonde, non una plissettatura fitta
        self.assertLessEqual(dress.PLEAT_N, 20)
        self.assertGreaterEqual(dress.PLEAT_DEPTH, 0.028)

    def test_sash_crosses_and_belt_get_a_material(self):
        # Regressione: questi due gruppi restavano senza materiale e nel
        # render comparivano grigi (la cintura scura spariva).
        dress.reset_scene()
        objs = dress.build_all()
        for ob in objs:
            self.assertTrue(ob.data.materials, ob.name)

    def test_center_strap_has_a_pointed_hem(self):
        self.assertLess(dress.STRAP_TIP_Z, dress.STRAP_SHOULDER_Z)
        self.assertGreater(dress.strap_halfwidth(dress.STRAP_SHOULDER_Z), 0.02)

    def test_strap_tip_is_a_v_with_a_centre_notch(self):
        # Nel disegno la punta e' una V: scende al centro e risale ai lati,
        # con un piccolo intaglio sul centro esatto.
        self.assertGreater(dress.strap_bottom_z(1.0) - dress.strap_bottom_z(0.12),
                           0.02)
        self.assertGreater(dress.strap_bottom_z(0.0),
                           dress.strap_bottom_z(0.12) - 0.002)

    def test_lappets_follow_the_skirt_pleats(self):
        # I veli sono la stessa stoffa pieghettata della gonna: se smettono di
        # seguirla diventano cartone (era il problema della prima revisione).
        pnl = dress.Panel("T", [(0.0, 0.2), (1.0, 0.25)],
                          [(0.0, dress.SKIRT_TOP_Z), (1.0, 0.3)], "lapB",
                          follow=1.0)
        # il margine rispetto alla gonna e' piccolo e costante: il velo le sta
        # sopra, non se ne stacca come una lamiera
        for u in (0.3, 0.5, 0.7):
            for v in (0.35, 0.6, 0.85):
                a, z, _ = pnl.params(u, v)
                drift = (pnl.pt(u, v) - dress.surface(a, z, "base")).length
                self.assertLess(drift, 0.055, (u, v))
        # e la sua sezione segue le creste: su un giro di 1/31 di giro il
        # raggio cambia come quello della gonna sottostante
        a0 = 0.24
        span = []
        for k in range(9):
            aa = a0 + (k - 4) * (math.tau / dress.PLEAT_N) / 8.0
            v = 0.8
            p = dress.surface(aa, pnl.params(0.5, v)[1], "base",
                              extra=dress.skirt_disp(aa, pnl.params(0.5, v)[1]))
            span.append(Vector((p.x, p.y, 0.0)).length)
        self.assertGreater(max(span) - min(span), 0.008)


class WaistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dress.reset_scene()
        cls.sash = dress.build_sash()

    def test_crossed_bands_wrap_all_the_way_round(self):
        # I teli in croce non sono strisce appoggiate sul davanti: girano
        # attorno alla vita e si infilano dietro, come un nastro avvolto.
        bands = [o for o in self.sash if o.name.startswith("Sash_Cross")]
        self.assertGreaterEqual(len(bands), 2)
        for ob in bands[:2]:
            ys = [v.co.y for v in ob.data.vertices]
            self.assertLess(min(ys), -0.10)   # davanti
            self.assertGreater(max(ys), 0.10)  # dietro
            zs = [v.co.z for v in ob.data.vertices]
            self.assertGreater(max(zs) - min(zs), 0.05)

    def test_band_ends_taper_and_hide_under_the_waist(self):
        band = [o for o in self.sash if o.name == "Sash_CrossA"][0]
        # il telo e' piu' strettamente avvolto alle estremita' che al centro
        front = [v.co for v in band.data.vertices if abs(v.co.x) < 0.02
                 and v.co.y < 0]
        self.assertTrue(front)
        self.assertLess(max(abs(p.x) for p in front), 0.03)


class LayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dress.reset_scene()
        cls.lappets = dress.build_lappets()
        cls.straps, _ = dress.build_strap()
        cls.drapes, cls.panels = dress.build_drapes()
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        cls.lap_bvhs = [(ob.name, BVHTree.FromObject(ob, dg)) for ob in cls.lappets]
        cls.strap_bvh = BVHTree.FromObject(cls.straps[0], dg)
        cls.drape_bvhs = [BVHTree.FromObject(ob, dg) for ob in cls.drapes]

    def test_strap_sits_in_front_of_the_white_layers(self):
        # Ray-cast at both edges as well as the center. This catches the white
        # patches that previously pierced the dark ribbon just below the belt.
        for z in (0.43, 0.5, 0.6, 0.7, 0.8, 0.9, 0.94, 0.96):
            half = dress.strap_halfwidth(z)
            for fraction in (-0.8, -0.4, 0, 0.4, 0.8):
                origin = Vector((fraction * half, -1.0, z))
                direction = Vector((0, 1, 0))
                p, _, _, _ = self.strap_bvh.ray_cast(origin, direction, 2.0)
                self.assertIsNotNone(p, (z, fraction))
                for name, tree in self.lap_bvhs:
                    other, _, _, _ = tree.ray_cast(origin, direction, 2.0)
                    if other is not None:
                        self.assertLess(p.y, other.y + 0.0002, (z, fraction, name))

    def test_embroideries_clear_solidified_drapes(self):
        # Solidify extrudes the cloth outward. Embroidery must sit beyond that
        # surface, not merely above the unthickened parametric grid.
        for panel, tree in zip(self.panels[:2], self.drape_bvhs[:2]):
            for u in (0.2, 0.5, 0.8):
                for v in (0.25, 0.5, 0.75):
                    normal = panel.nrm(u, v)
                    point = panel.pt(u, v) + normal * 0.0052
                    hit, _, _, dist = tree.ray_cast(point, -normal, 0.02)
                    self.assertIsNotNone(hit, (panel.name, u, v))
                    self.assertGreater(dist, 0.0007, (panel.name, u, v, dist))
                    self.assertLess(dist, 0.006, (panel.name, u, v, dist))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
