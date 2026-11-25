"""Build/verify an offline CCTA manifest; never modify source image files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from app.services.ccta_dataset_preparation import (
    DatasetPreparationError,
    prepare_dataset,
    verify_manifest,
    write_manifest,
)


def _read_json(path: Path) -> dict:
    if path.stat().st_size > 16 * 1024 * 1024:
        raise DatasetPreparationError("Registration or manifest document exceeds size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DatasetPreparationError("Registration or manifest is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise DatasetPreparationError("Registration or manifest root must be an object")
    return value


def _outside(path: Path, protected: Path, what: str) -> None:
    try:
        path.resolve().relative_to(protected.resolve())
    except ValueError:
        return
    raise DatasetPreparationError(f"{what} must be outside the protected directory")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Read-only extracted dataset root")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--registration", type=Path, help="Versioned dataset-registration JSON")
    group.add_argument("--verify-manifest", type=Path, help="Existing manifest to revalidate")
    parser.add_argument("--output", type=Path, help="New manifest path; required for --registration")
    args = parser.parse_args()

    try:
        repo_root = Path(__file__).resolve().parents[2]
        root = args.root.resolve(strict=True)
        if args.registration:
            if not args.output:
                raise DatasetPreparationError("--output is required with --registration")
            output = args.output.resolve()
            _outside(output, root, "Manifest output")
            _outside(output, repo_root, "Manifest output")
            _outside(args.registration.resolve(strict=True), repo_root, "Registration file")
            manifest = prepare_dataset(root, _read_json(args.registration))
            write_manifest(output, manifest)
            print(json.dumps({"created": True, "manifest_sha256": manifest["manifest_sha256"],
                              "case_count": manifest["statistics"]["case_count"],
                              "statistics": manifest["statistics"],
                              "training_eligible": False}, sort_keys=True))
        else:
            path = args.verify_manifest.resolve(strict=True)
            _outside(path, repo_root, "Manifest")
            result = verify_manifest(root, _read_json(path))
            print(json.dumps(result, sort_keys=True))
        return 0
    except (DatasetPreparationError, OSError) as exc:
        print(f"dataset preparation refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
