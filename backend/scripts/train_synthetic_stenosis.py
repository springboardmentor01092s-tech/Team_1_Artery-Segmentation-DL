"""Train the optional synthetic-only stenosis research classifier.

Example: python -B scripts/train_synthetic_stenosis.py --output "$env:TEMP\\vascuai-synth-run"
The destination must be new. Never point this tool at a patient/dataset directory.
"""
import argparse
import json

from app.services.synthetic_stenosis_ml import train_synthetic_model


def main():
    parser = argparse.ArgumentParser(description="Synthetic phantom-only experimental 3D classifier; no clinical data accepted")
    parser.add_argument("--output", required=True, help="New empty output directory; checkpoint and metrics are written here")
    parser.add_argument("--samples", type=int, default=100, help="Multiple of 5, range 25 to 500")
    parser.add_argument("--epochs", type=int, default=5, help="Range 1 to 50")
    parser.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args()
    if not 25 <= args.samples <= 500 or args.samples % 5:
        parser.error("--samples must be a multiple of five between 25 and 500")
    try:
        result = train_synthetic_model(args.output, args.samples, args.epochs, args.seed)
    except (ValueError, FileExistsError, RuntimeError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
