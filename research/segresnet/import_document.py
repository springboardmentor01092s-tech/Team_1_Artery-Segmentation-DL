"""Bind actual completed Val results to verified application IDs, offline only.

Bindings must be recovered from real stored CT records/checksums. This tool does
not create cases, fabricate IDs or upload/import records. Run from repository root.
"""
import argparse
import json
from pathlib import Path
import sys

from evaluation import sha256


def build_document(results, checkpoint, bindings):
    if not results.get("complete") or results["summary"]["included_case_count"] != 50:
        raise ValueError("All 50 actual native-grid validation results are required")
    if sha256(checkpoint) != results["checkpoint_sha256"]:
        raise ValueError("Actual checkpoint bytes do not match evaluation")
    if set(bindings) != {str(i) for i in range(851, 901)}:
        raise ValueError("Exactly 50 verified canonical case bindings are required")
    provenance = results["provenance"]
    rows = []
    for row in results["cases"]:
        binding = bindings[row["dataset_case_id"]]
        if binding["ct_sha256"] != row["ct_sha256"]:
            raise ValueError("Stored application CT checksum differs from evaluated source")
        if not row.get("prediction_sha256") or row.get("exclusion_reason"):
            raise ValueError("Missing actual prediction artifact or failed measurement")
        rows.append({"case_id": binding["case_id"], "dataset_case_id": row["dataset_case_id"],
                     "reference_sha256": row["reference_sha256"], "prediction_sha256": row["prediction_sha256"],
                     "metrics": row["metrics"], "confusion_counts": row["confusion_counts"],
                     "mask_provenance": {"origin": "model_prediction", "mask_sha256": row["prediction_sha256"],
                                         "model_checkpoint_sha256": results["checkpoint_sha256"]}})
    manifest = provenance["cache_manifest"]
    return {"schema_version": "offline-evaluation/1.0", "metadata": {
        "model": {"id": "monai-segresnet-1mm-200training", "architecture": "MONAI SegResNet",
                  "display_name": "SegResNet · 1 mm · 200 Training cases"},
        "checkpoint": {"sha256": results["checkpoint_sha256"], "training_run_id": provenance["training_run_id"],
                       "reported_training_steps": results["optimizer_steps"]},
        "threshold": .5, "validation_split_source": {"dataset": "Original ImageCAS, Split-4",
            "manifest_sha256": manifest["manifest_sha256"], "workbook_sha256": manifest["workbook_sha256"],
            "sheet": manifest["sheet"], "split_column": manifest["split_column"], "split": "Val"},
        "metric_definitions": results["metric_definitions"],
        "provenance": {"training": provenance, "validation_grid": "original native grid",
                       "aggregation": "macro_unweighted_per_case; pooled_micro_separate",
                       "prediction_origin": "actual_model_prediction", "Testing_accessed": False}}, "cases": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = build_document(json.loads(args.results.read_text(encoding="utf-8")), args.checkpoint,
                           json.loads(args.bindings.read_text(encoding="utf-8")))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
    from app.schemas.evaluation import EvaluationDocument
    document = EvaluationDocument.model_validate(value)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(document.model_dump_json(indent=2))
    print(json.dumps({"cases": len(document.cases), "source_artifact_id": "not created: protected upload still required"}))


if __name__ == "__main__":
    main()
