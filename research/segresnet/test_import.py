"""Synthetic schema/binding checks. No upload, database or real results."""
import copy
import hashlib
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from import_document import build_document
from app.schemas.evaluation import EvaluationDocument


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.checkpoint = Path(self.temp.name) / "synthetic.pt"
        self.checkpoint.write_bytes(b"synthetic test checkpoint, never a model")
        checkpoint_hash = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()
        counts = dict(tp=1, fp=0, fn=0, tn=1)
        self.results = {"complete": True, "summary": {"included_case_count": 50},
            "checkpoint_sha256": checkpoint_hash, "optimizer_steps": 1,
            "provenance": {"training_run_id": "synthetic-test-only", "cache_manifest": {
                "manifest_sha256": "a"*64, "workbook_sha256": "b"*64, "sheet": "synthetic", "split_column": "Split-4"}},
            "metric_definitions": {"version": "binary-voxel/1.0", "reference_foreground": "label == 1",
                "prediction_foreground": "probability >= 0.5", "zero_denominator": "null"},
            "cases": [{"dataset_case_id": str(i), "ct_sha256": "c"*64, "reference_sha256": "d"*64,
                "prediction_sha256": "e"*64, "metrics": dict(dice=1., iou=1., precision=1., recall=1.),
                "confusion_counts": counts, "exclusion_reason": None} for i in range(851,901)]}
        # Deliberately different application IDs to prove no dataset-ID reuse.
        self.bindings = {str(i): {"case_id": i+10000, "ct_sha256": "c"*64} for i in range(851,901)}

    def tearDown(self):
        self.temp.cleanup()

    def test_full_document_satisfies_real_schema_with_actual_bindings(self):
        value = EvaluationDocument.model_validate(build_document(self.results, self.checkpoint, self.bindings))
        self.assertEqual(len(value.cases),50)
        self.assertEqual(value.cases[0].case_id,10851)
        self.assertEqual(value.metadata.checkpoint.sha256, self.results["checkpoint_sha256"])
        self.assertNotIn("source_artifact_id", value.model_dump())

    def test_missing_bindings_and_false_ct_identity_refused(self):
        for bad in ({}, {**self.bindings,"851":{"case_id":1,"ct_sha256":"0"*64}}):
            with self.assertRaises(ValueError):
                build_document(self.results,self.checkpoint,bad)

    def test_checkpoint_and_incomplete_measurements_refused(self):
        for field, value in [("complete",False),("checkpoint_sha256","0"*64)]:
            result=copy.deepcopy(self.results)
            result[field]=value
            with self.assertRaises(ValueError):
                build_document(result,self.checkpoint,self.bindings)
        result=copy.deepcopy(self.results)
        result["cases"][0]["prediction_sha256"]=None
        with self.assertRaises(ValueError):
            build_document(result,self.checkpoint,self.bindings)


if __name__ == "__main__":
    unittest.main()
