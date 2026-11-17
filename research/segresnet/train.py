"""Kaggle Save & Run All; actual SegResNet training and native-grid Val results.

No application DB/API access, inference provider, Testing data, or gate changes.
Each new run is a genuinely new run; resumption requires its own exact checkpoint.
"""
import argparse
import csv
import json
import platform
from pathlib import Path
import time
from uuid import uuid4

import monai
import nibabel
import numpy as np
import scipy
import torch
from monai.inferers import sliding_window_inference
from monai.losses import DiceCELoss
from monai.networks.nets import SegResNet

from benchmark import MODEL
from data import CacheStore, patch_batch
from evaluation import aggregate, evaluate_native, sha256, write_json

SEED = 20261117
STEPS_PER_EPOCH = 400  # 800 sampled patches; not one complete CT pass.
TOTAL_STEPS = 40_000
VALIDATE_EVERY = 4_000


def save_checkpoint(path, model, optimizer, scheduler, scaler, provenance, step, best, attempts):
    temporary = path.with_name(path.name + ".partial")
    if temporary.exists():
        raise FileExistsError("Checkpoint partial from an interrupted operation retained")
    torch.save({"model": model.state_dict(), "optimizer": optimizer.state_dict(),
                "scheduler": scheduler.state_dict(), "scaler": scaler.state_dict(),
                "provenance": provenance, "optimizer_steps": step, "best_macro_dice": best,
                "attempts": attempts,
                "torch_rng": torch.get_rng_state(), "cuda_rng": torch.cuda.get_rng_state_all()}, temporary)
    temporary.replace(path)


@torch.inference_mode()
def validate(model, store, output, save_predictions=False, deadline=None):
    model.eval()
    rows = []
    start = time.perf_counter()
    for case_id in store.manifest["validation_ids"]:
        if deadline is not None and time.perf_counter() >= deadline:
            raise TimeoutError("Validation budget exhausted; partial records retained")
        try:
            image = store.array("Val", case_id, "image")
            tensor = torch.from_numpy(np.array(image, dtype=np.float32))[None, None]

            def predictor(patches):
                with torch.autocast("cuda", dtype=torch.float16):
                    return torch.softmax(model(patches), dim=1)[:, 1:2].float()

            # GPU patch computation; stitched foreground probability stays on CPU.
            probability = sliding_window_inference(tensor, (96, 96, 96), 2, predictor,
                                                   overlap=.25, mode="gaussian",
                                                   sw_device="cuda", device="cpu")[0, 0].numpy()
            row = evaluate_native(probability, store, case_id, output, save_predictions)
            del tensor, probability
        except (ValueError, OSError) as exc:
            # A failed measurement stays in coverage; no fabricated replacement.
            row = {"dataset_case_id": case_id, "metrics": dict.fromkeys(("dice", "iou", "precision", "recall")),
                   "confusion_counts": None, "exclusion_reason": f"{type(exc).__name__}: {exc}"}
        rows.append(row)
        write_json(output / "validation-progress.json", {"cases": rows, "complete": False})
    result = {"cases": rows, "summary": aggregate(rows), "seconds": time.perf_counter() - start,
              "complete": True, "metric_definitions": {"version": "binary-voxel/1.0",
              "reference_foreground": "original categorical reference label == 1",
              "prediction_foreground": "native-grid linearly resampled foreground probability >= 0.5",
              "zero_denominator": "null"}}
    model.train()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--expected-cache-identity", required=True)
    parser.add_argument("--output", type=Path, default=Path("/kaggle/working"))
    parser.add_argument("--wall-seconds", type=int, default=36_000)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--resume-best", type=Path)
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("This training run requires a Kaggle GPU")
    if not 1800 <= args.wall_seconds <= 39_600:
        raise ValueError("Explicit session budget must be between 30 minutes and 11 hours")
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "run.json").exists():
        raise FileExistsError("Refusing to overwrite a prior run directory")
    store = CacheStore(args.cache)
    if store.manifest["training_ids"] != [str(i) for i in range(401, 601)] or store.manifest["validation_ids"] != [str(i) for i in range(851, 901)]:
        raise ValueError("This run requires exactly the approved 200 Training and 50 Val identities")
    cache_identity = store.verify()
    if cache_identity != args.expected_cache_identity:
        raise ValueError("Actual cache contents differ from the frozen local source")
    started = time.perf_counter()
    deadline = started + args.wall_seconds
    torch.manual_seed(SEED)
    torch.set_num_threads(4)
    model = SegResNet(**MODEL).cuda()
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-4, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=TOTAL_STEPS)
    scaler = torch.amp.GradScaler("cuda")
    loss_fn = DiceCELoss(to_onehot_y=True, softmax=True, include_background=False)
    provenance = {"schema_version": "segresnet-training/1.0", "training_run_id": str(uuid4()),
                  "seed": SEED, "model": "MONAI SegResNet", "model_config": MODEL,
                  "torch": torch.__version__, "monai": monai.__version__, "numpy": np.__version__,
                  "scipy": scipy.__version__, "nibabel": nibabel.__version__,
                  "python": platform.python_version(), "gpu": torch.cuda.get_device_name(0),
                  "cache_manifest": store.manifest, "cache_sha256": cache_identity,
                  "cache_identity_definition": "SHA256 of sorted canonical relative-path to actual-file-SHA256 mapping; directory/ZIP invariant",
                  "source_hashes": {name: sha256(Path(__file__).parent / name)
                                    for name in ("train.py", "data.py", "benchmark.py", "evaluation.py")},
                  "batch_size": 2, "patch": [96, 96, 96], "threshold": .5,
                  "planned_optimizer_steps": TOTAL_STEPS, "steps_per_logical_epoch": STEPS_PER_EPOCH,
                  "logical_epoch_definition": "400 random mini-batches, not a complete CT-volume pass",
                  "wall_seconds": args.wall_seconds, "training_data": "Training only; validation for checkpoint selection; no Testing"}
    step, best, attempts = 0, -1., 0
    if args.resume:
        # Only an explicitly supplied, operator-trusted checkpoint from this code.
        checkpoint = torch.load(args.resume, map_location="cpu", weights_only=False)
        old = checkpoint["provenance"]
        if any(old[key] != provenance[key] for key in ("cache_sha256", "source_hashes", "model_config", "threshold")):
            raise ValueError("Resume source, data or recipe differs")
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        scheduler.load_state_dict(checkpoint["scheduler"])
        scaler.load_state_dict(checkpoint["scaler"])
        torch.set_rng_state(checkpoint["torch_rng"])
        torch.cuda.set_rng_state_all(checkpoint["cuda_rng"])
        step, best = checkpoint["optimizer_steps"], checkpoint["best_macro_dice"]
        attempts = checkpoint["attempts"]
        provenance["training_run_id"] = old["training_run_id"]
        provenance["resumed_from_sha256"] = sha256(args.resume)
        if best >= 0:
            if args.resume_best is None:
                raise ValueError("Resume requires the actual previous best checkpoint as well as last")
            prior_best = torch.load(args.resume_best, map_location="cpu", weights_only=False)
            if prior_best["provenance"]["training_run_id"] != old["training_run_id"] or prior_best["best_macro_dice"] != best:
                raise ValueError("Previous best checkpoint belongs to another run or selection state")
            import shutil
            shutil.copyfile(args.resume_best, args.output / "best.pt")
    write_json(args.output / "run.json", provenance)
    model.train()
    last_validation_seconds = 0
    with (args.output / "training.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["optimizer_step", "attempt", "loss", "seconds", "scale", "update_applied"])
        while step < TOTAL_STEPS:
            # Reserve at least 20 minutes, or twice the measured validation time.
            reserve = max(1200, 2 * last_validation_seconds + 300)
            if time.perf_counter() >= deadline - reserve:
                break
            x, y = patch_batch(store, attempts)
            x, y = torch.from_numpy(x).cuda(), torch.from_numpy(y).cuda()
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast("cuda", dtype=torch.float16):
                loss = loss_fn(model(x), y)
            if not torch.isfinite(loss):
                raise RuntimeError("Nonfinite training loss; no successful checkpoint claimed")
            previous_scale = scaler.get_scale()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            applied = scaler.get_scale() >= previous_scale
            attempts += 1
            if applied:
                step += 1
                scheduler.step()
            writer.writerow([step, attempts, float(loss.detach()), time.perf_counter() - started, scaler.get_scale(), applied])
            if attempts % 20 == 0:
                stream.flush()
                print(json.dumps({"optimizer_step": step, "attempts": attempts, "loss": float(loss.detach())}), flush=True)
            if not applied and attempts - step > 100:
                raise RuntimeError("Excess skipped AMP updates; preserve failure rather than claim optimizer progress")
            if applied and (step % 400 == 0 or step == TOTAL_STEPS):
                save_checkpoint(args.output / "last.pt", model, optimizer, scheduler, scaler, provenance, step, best, attempts)
            if applied and (step == 400 or step % VALIDATE_EVERY == 0 or step == TOTAL_STEPS):
                result = validate(model, store, args.output, deadline=deadline - 300)
                last_validation_seconds = result["seconds"]
                write_json(args.output / f"validation-step-{step}.json", result)
                score = result["summary"]["macro_metrics"]["dice"]
                # Never select a favorable conditional score from an incomplete cohort.
                if result["summary"]["included_case_count"] == 50 and score is not None and score > best:
                    best = score
                    save_checkpoint(args.output / "best.pt", model, optimizer, scheduler, scaler, provenance, step, best, attempts)
                save_checkpoint(args.output / "last.pt", model, optimizer, scheduler, scaler, provenance, step, best, attempts)
    save_checkpoint(args.output / "last.pt", model, optimizer, scheduler, scaler, provenance, step, best, attempts)
    best_path = args.output / "best.pt"
    result_status = "checkpoint_saved_validation_pending"
    if best_path.exists() and time.perf_counter() + max(600, last_validation_seconds * 1.5) < deadline:
        selected = torch.load(best_path, map_location="cpu", weights_only=False)
        model.load_state_dict(selected["model"])
        result = validate(model, store, args.output, save_predictions=True, deadline=deadline)
        result.update(checkpoint_sha256=sha256(best_path), optimizer_steps=selected["optimizer_steps"], provenance=provenance)
        write_json(args.output / "validation-results.json", result)
        result_status = "native_validation_complete" if result["summary"]["included_case_count"] == 50 else "native_validation_with_failures"
    write_json(args.output / "completion.json", {"training_run_id": provenance["training_run_id"],
               "optimizer_steps": step, "planned_steps": TOTAL_STEPS, "training_complete": step == TOTAL_STEPS,
               "status": result_status, "seconds": time.perf_counter() - started,
               "last_checkpoint_sha256": sha256(args.output / "last.pt"),
               "best_checkpoint_sha256": sha256(best_path) if best_path.exists() else None})


if __name__ == "__main__":
    main()
