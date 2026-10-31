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
        self.assertAlmostEqual(dress.skirt_disp(0.0, 0.60),
                               dress.skirt_disp(math.tau, 0.60), places=6)

    def test_upper_legs_are_inside_the_waist(self):
        for z, rx, _, _ in dress.LEG_PROFILE:
            if z >= 0.78:
                outer = dress.leg_center_x(z) + 0.004 * (1.0-z) + rx
                self.assertLess(outer, dress.WAIST_RX)
        self.assertGreater(dress.leg_center_x(0.12), dress.leg_center_x(0.95))

    def test_center_strap_has_a_pointed_hem(self):
        self.assertLess(dress.STRAP_TIP_Z, dress.STRAP_SHOULDER_Z)
        self.assertGreater(dress.strap_halfwidth(dress.STRAP_SHOULDER_Z), 0.02)


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
