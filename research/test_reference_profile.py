"""Independent tiny synthetic checks for the reference-only plane operator."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
from reference_profile import measure_section, vtk_polylines


class ReferenceProfileTests(unittest.TestCase):
    def tube(self, radius=2., spacing=(.25, .25, .25), angle=0):
        affine = np.eye(4)
        rotation = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]])
        affine[:3, :3] = rotation @ np.diag(spacing)
        affine[:3, 3] = -affine[:3, :3] @ np.array([16, 16, 16])
        i, j, k = np.indices((33, 33, 33))
        x = affine[0, 0] * (i - 16) + affine[0, 2] * (k - 16)
        y = spacing[1] * (j - 16)
        mask = (x*x + y*y <= radius*radius).astype(np.uint8)
        return mask, affine

    def test_known_circle_area(self):
        mask, affine = self.tube()
        result = measure_section(mask, affine, np.zeros(3), np.array([0., 0., 1.]), radius=3., pitch=.1)
        self.assertEqual(result["status"], "reference_measurement_unvalidated")
        self.assertAlmostEqual(result["diameter_mm"], 4., delta=.18)

    def test_anisotropic_oblique_world_geometry(self):
        mask, affine = self.tube(spacing=(.3, .4, .5), angle=.3)
        result = measure_section(mask, affine, np.zeros(3), np.array([0., 0., 1.]), radius=3., pitch=.1)
        self.assertAlmostEqual(result["diameter_mm"], 4., delta=.2)

    def test_background_center_abstains_without_selecting_nearest(self):
        mask, affine = self.tube()
        result = measure_section(mask, affine, np.array([3., 0., 0.]), np.array([0., 0., 1.]), radius=3., pitch=.1)
        self.assertIsNone(result["diameter_mm"])
        self.assertEqual(result["reason"], "supplied_centerline_outside_reference_lumen")

    def test_field_of_view_is_not_filled_or_closed(self):
        mask, affine = self.tube(radius=3.)
        result = measure_section(mask, affine, np.zeros(3), np.array([0., 0., 1.]), radius=2., pitch=.1)
        self.assertIsNone(result["diameter_mm"])
        self.assertEqual(result["reason"], "plane_FOV_limited")

    def test_hole_at_center_is_not_filled(self):
        mask, affine = self.tube()
        inner, _ = self.tube(radius=.8)
        mask[inner > 0] = 0
        result = measure_section(mask, affine, np.zeros(3), np.array([0., 0., 1.]), radius=3., pitch=.1)
        self.assertIsNone(result["diameter_mm"])

    def test_binary_vtk_connectivity_is_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.vtk"
            points = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [1, 1, 0]], dtype=">f4")
            data = b"# vtk DataFile Version 5.1\nsynthetic\nBINARY\nDATASET POLYDATA\nPOINTS 4 float\n" + points.tobytes()
            data += b"\nLINES 3 5\nOFFSETS vtktypeint64\n" + np.array([0, 3, 5], dtype=">i8").tobytes()
            data += b"\nCONNECTIVITY vtktypeint64\n" + np.array([0, 1, 2, 1, 3], dtype=">i8").tobytes() + b"\n"
            path.write_bytes(data)
            actual, cells = vtk_polylines(path)
            np.testing.assert_array_equal(actual, points)
            self.assertEqual(cells, [[0, 1, 2], [1, 3]])


if __name__ == "__main__":
    unittest.main()
