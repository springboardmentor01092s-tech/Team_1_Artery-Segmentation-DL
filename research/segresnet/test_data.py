"""Tiny synthetic cache/coordinate tests. No cohort or model execution."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
import numpy as np
from cache import target_grid, resample
from data import CacheStore, crop_patch, patch_batch


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        folder = self.root / "Training/401"
        folder.mkdir(parents=True)
        (self.root / "manifest.json").write_text(json.dumps({"schema_version": "imagecas-cache/1.0", "spacing_mm": [1, 1, 1], "training_ids": ["401"], "validation_ids": []}))
        self.image = np.arange(210, dtype=np.float16).reshape(5, 6, 7) / np.float16(210)
        self.mask = np.zeros((5, 6, 7), dtype=np.uint8)
        self.mask[2, 2:4, 2:5] = 1
        np.save(folder / "image.npy", self.image)
        np.save(folder / "mask.npy", self.mask)
        (folder / "case.json").write_text(json.dumps({"case_id": "401", "split": "Training"}))

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, compression):
        path = self.root / "cache.zip"
        with zipfile.ZipFile(path, "x", compression=compression) as archive:
            for p in self.root.rglob("*"):
                if p.is_file() and p != path:
                    archive.write(p, p.relative_to(self.root).as_posix())
        return path

    def test_stored_archive_maps_exact_values_and_axes(self):
        store = CacheStore(self.archive(zipfile.ZIP_STORED))
        np.testing.assert_array_equal(store.array("Training", "401", "image"), self.image)
        np.testing.assert_array_equal(store.array("Training", "401", "mask"), self.mask)

    def test_complete_identity_is_directory_zip_invariant_and_detects_change(self):
        folder = self.root / "Training/401"
        files = [{"name": name, "bytes": (folder/name).stat().st_size,
                  "sha256": hashlib.sha256((folder/name).read_bytes()).hexdigest()} for name in ("image.npy", "mask.npy")]
        (folder / "case.json").write_text(json.dumps({"case_id": "401", "split": "Training", "files": files}))
        expected = CacheStore(self.root).verify()
        self.assertEqual(CacheStore(self.archive(zipfile.ZIP_STORED)).verify(), expected)
        with (folder / "image.npy").open("ab") as stream:
            stream.write(b"corruption")
        with self.assertRaisesRegex(ValueError, "hash or size"):
            CacheStore(self.root).verify()

    def test_deflated_archive_is_refused(self):
        store = CacheStore(self.archive(zipfile.ZIP_DEFLATED))
        with self.assertRaisesRegex(ValueError, "ZIP_STORED"):
            store.array("Training", "401", "image")

    def test_object_payload_is_refused(self):
        np.save(self.root / "Training/401/image.npy", np.array([{"unsafe": True}], dtype=object))
        store = CacheStore(self.archive(zipfile.ZIP_STORED))
        with self.assertRaisesRegex(ValueError, "dtype|dimensions"):
            store.array("Training", "401", "image")

    def test_testing_and_unknown_ids_are_refused(self):
        store = CacheStore(self.root)
        for split, case_id in [("Testing", "401"), ("Training", "1"), ("Training", "../401")]:
            with self.assertRaisesRegex(ValueError, "permitted"):
                store.array(split, case_id, "mask")

    def test_overlapping_splits_are_refused(self):
        path = self.root / "manifest.json"
        data = json.loads(path.read_text())
        data["validation_ids"] = ["401"]
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            CacheStore(self.root)

    def test_boundary_padding_preserves_source_position(self):
        result = crop_patch(self.image, (0, 0, 0), 8)
        self.assertEqual(result.shape, (8, 8, 8))
        np.testing.assert_array_equal(result[4:, 4:, 4:], self.image[:4, :4, :4])
        self.assertEqual(np.count_nonzero(result[:4]), 0)

    def test_sampling_is_reproducible_and_categorical(self):
        store = CacheStore(self.root)
        first = patch_batch(store, 7, size=8)
        second = patch_batch(store, 7, size=8)
        np.testing.assert_array_equal(first[0], second[0])
        np.testing.assert_array_equal(first[1], second[1])
        self.assertEqual(first[0].shape, (2, 1, 8, 8, 8))
        self.assertEqual(first[1].dtype, np.int64)
        self.assertLessEqual(set(np.unique(first[1])), {0, 1})
        np.testing.assert_array_equal(np.load(self.root / "Training/401/mask.npy"), self.mask)

    def test_mismatched_partner_shapes_are_refused(self):
        np.save(self.root / "Training/401/mask.npy", np.zeros((2, 3, 4), dtype=np.uint8))
        with self.assertRaisesRegex(ValueError, "mismatch"):
            patch_batch(CacheStore(self.root), 0)

    def test_anisotropic_oblique_grid_keeps_axes_origin_and_coverage(self):
        angle = .3
        rotation = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]])
        affine = np.eye(4)
        affine[:3, :3] = rotation @ np.diag([.5, .75, 1.5])
        affine[:3, 3] = [4., -7., 12.]
        shape, result = target_grid((9, 7, 5), affine)
        self.assertEqual(shape, (5, 6, 7))
        np.testing.assert_allclose(result[:3, :3], rotation)
        np.testing.assert_allclose(result[:3, 3], affine[:3, 3])
        mask = np.ones((9, 7, 5), dtype=np.uint8)
        transformed = resample(mask, affine, result, shape, 0)
        self.assertEqual(transformed.dtype, np.uint8)
        self.assertLessEqual(set(np.unique(transformed)), {0, 1})


if __name__ == "__main__":
    unittest.main()
