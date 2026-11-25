"""Run a deterministic synthetic-only measurement/localization benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.synthetic_stenosis_validation import benchmark_synthetic_measurements


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True,
                        help="New output directory; existing directories are never overwritten")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    report = benchmark_synthetic_measurements()
    (output / "measurement-benchmark.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8",
    )
    print(json.dumps({
        "output_dir": str(output.resolve()),
        "cases": report["counts"]["cases"],
        "candidate_precision": report["candidate_detection"]["precision"],
        "candidate_recall": report["candidate_detection"]["recall"],
        "reference_radius_mae": report["measurement_error"]["reference_radius_synthetic_voxels"]["mae"],
        "minimum_radius_mae": report["measurement_error"]["minimum_radius_synthetic_voxels"]["mae"],
        "narrowing_mae": report["measurement_error"]["percentage_narrowing_points"]["mae"],
        "clinical_gate_authorized": False,
        "training_release_authorized": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
