"""Round-trip GLB/FBX checks (requires Blender's bpy module)."""
from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
MATERIALS = {"DRESS1_Linen", "DRESS1_Wool", "DRESS1_Gold", "DRESS1_GoldTrim"}


def only_mesh():
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(meshes) != 1:
        raise AssertionError(f"expected one mesh, got {len(meshes)}")
    return meshes[0]


class ExportTests(unittest.TestCase):
    def test_glb_round_trip_and_strap_visibility(self):
        previous = None
        for name in ("DRESS1.glb", "DRESS1_LOD1.glb", "DRESS1_LOD2.glb"):
            with self.subTest(file=name):
                bpy.ops.wm.read_factory_settings(use_empty=True)
                self.assertEqual(bpy.ops.import_scene.gltf(filepath=str(ROOT / name)),
                                 {"FINISHED"})
                ob = only_mesh()
                self.assertEqual({m.name for m in ob.data.materials}, MATERIALS)
                triangles = sum(len(p.vertices) - 2 for p in ob.data.polygons)
                if previous is not None:
                    self.assertLess(triangles, previous)
                previous = triangles
                self.assertTrue(ob.data.uv_layers)
                self.assertTrue(all(im.size[0] > 0 and im.packed_file
                                    for im in bpy.data.images))

                # Ensure both the front motif and the side embroidery survive
                # the engine export and the LOD reduction, not only the .blend.
                gold_id = ob.data.materials.find("DRESS1_GoldTrim")
                gold = [p for p in ob.data.polygons if p.material_index == gold_id]
                self.assertGreater(len(gold), 500)
                side_faces = sum(
                    1 for p in gold if any(abs(ob.data.vertices[i].co.x) > 0.16
                                           for i in p.vertices))
                self.assertGreater(side_faces, 40, "side embroidery disappeared")

                bpy.context.view_layer.update()
                tree = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get())
                for z in (0.43, 0.5, 0.6, 0.7, 0.8, 0.9, 0.94, 0.96):
                    for x in (-0.018, -0.009, 0, 0.009, 0.018):
                        _, _, index, _ = tree.ray_cast(Vector((x, -1.0, z)),
                                                       Vector((0, 1, 0)), 2.0)
                        self.assertIsNotNone(index, (name, x, z))
                        mat = ob.data.materials[ob.data.polygons[index].material_index]
                        self.assertIn(mat.name, {"DRESS1_Wool", "DRESS1_GoldTrim"},
                                      (name, x, z, mat.name))

    def test_fbx_imports_from_a_standalone_copy(self):
        # Copying only the FBX proves it does not rely on paths in the checkout.
        with tempfile.TemporaryDirectory(prefix="dress1-fbx-") as directory:
            path = Path(directory) / "DRESS1.fbx"
            shutil.copy2(ROOT / "DRESS1.fbx", path)
            bpy.ops.wm.read_factory_settings(use_empty=True)
            self.assertEqual(bpy.ops.import_scene.fbx(filepath=str(path),
                                                      use_image_search=False),
                             {"FINISHED"})
            ob = only_mesh()
            self.assertEqual({m.name for m in ob.data.materials}, MATERIALS)
            self.assertGreater(len(ob.data.polygons), 70000)
            # 2 superfici testurizzate x (basecolor, normal, ORM) + AO:
            # 4 mappe, perche' l'ORM e l'AO di lino e lana finiscono in slot
            # distinti ma le immagini condivise restano le stesse.
            self.assertGreaterEqual(len(bpy.data.images), 4)
            self.assertTrue(all(im.size[0] > 0 and im.packed_file
                                for im in bpy.data.images))
            coordinates = [ob.matrix_world @ v.co for v in ob.data.vertices]
            height = max(v.z for v in coordinates) - min(v.z for v in coordinates)
            # Confronta con il GLB dello stesso LOD invece di una quota fissa:
            # la verifica resta valida anche quando il capo viene riproporzionato.
            bpy.ops.wm.read_factory_settings(use_empty=True)
            bpy.ops.import_scene.gltf(filepath=str(ROOT / "DRESS1.glb"))
            glb = only_mesh()
            zs = [(glb.matrix_world @ v.co).z for v in glb.data.vertices]
            self.assertAlmostEqual(height, max(zs) - min(zs), delta=0.004)
            # Il capo e' solo la gonna: l'altezza e' quella della vita ai
            # piedi (l'origine resta a terra, sotto l'orlo).
            self.assertGreater(height, 0.85)
            self.assertLess(height, 1.25)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
