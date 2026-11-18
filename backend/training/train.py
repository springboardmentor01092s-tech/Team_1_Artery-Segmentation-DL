"""Single CPU/CUDA baseline CLI. Default execution is read-only preflight."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import random
import signal
import sys
import uuid

import nibabel as nib
import numpy as np
import torch

from app.services.segmentation.model import SmallUNet3D
from .checkpoint import (HISTORICAL_SHA256, CheckpointError, atomic_save, initialize_weights,
                         inspect_resume, make_checkpoint, restore_checkpoint, _strict_state,
                         initial_validation_state, validation_phase, rng_state, restore_rng,
                         resume_assessment, digest)
from .dataset import DataError, SingleCaseCache, VOXEL_WARNING, build_index, check_pair
from .losses import weighted_bce_dice
from .sampling import PatchSampler
from .validation import ValidationCancelled, confusion, validate_cohort
from .runtime import (select_device, amp_enabled, autocast_context, make_scaler,
                      gpu_status, reset_peak_memory, portable_absolute, native_paths)
from .identity import identity_config, identity_paths


MODEL = {"architecture": "SmallUNet3D", "base_channels": 8}
PREPROCESSING = {"clip": [-200, 800], "normalization": "(image + 200) / 1000", "nifti_scaling": "apply_once"}
LOSS = {"positive_weight": 5.0, "smooth": 1e-6, "aggregation": "mean_BCE_plus_mean_per_sample_soft_Dice"}
OPTIMIZER = {"name": "AdamW", "lr": .0002, "weight_decay": .00001, "betas": [.9, .999], "eps": 1e-8, "gradient_clip_norm": 1.0}
VALIDATION = {"threshold": .70, "stride": 32}


def validate_config(cfg):
    cfg = dict(cfg) if isinstance(cfg, dict) else cfg
    required = {"schema_version", "dataset_root", "manifest", "expected_training_cases", "expected_validation_cases",
                "spatial_policy", "output_root", "seed", "cpu_threads", "batch_size", "num_workers", "pin_memory",
                "max_cache_bytes", "max_steps", "checkpoint_every", "validation_every", "model", "preprocessing",
                "sampling", "loss", "optimizer", "validation", "initialization_checkpoint"}
    optional = {"device", "mixed_precision", "gpu_monitoring", "cache_directory", "dataset_identity"}
    if not isinstance(cfg, dict) or not required.issubset(cfg) or set(cfg) - required - optional or cfg["schema_version"] != 1:
        raise ValueError("Config keys/schema differ from the documented explicit configuration.")
    for key, value in {"device": "cpu", "mixed_precision": False, "gpu_monitoring": False, "cache_directory": None}.items():
        cfg.setdefault(key, value)
    cfg["dataset_identity"] = identity_config(cfg.get("dataset_identity"))
    if cfg["device"] not in ("auto", "cpu", "cuda") or any(type(cfg[k]) is not bool for k in ("mixed_precision", "gpu_monitoring")):
        raise ValueError("Invalid device, mixed_precision or gpu_monitoring configuration.")
    for key in ["expected_training_cases", "expected_validation_cases", "cpu_threads", "max_cache_bytes", "max_steps", "checkpoint_every", "validation_every"]:
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ValueError("Expected positive integer configuration limits.")
    if (type(cfg["seed"]) is not int or not 0 <= cfg["seed"] <= 2**32-1
            or cfg["cpu_threads"] > 12 or cfg["max_cache_bytes"] > 512 * 1024 * 1024
            or cfg["batch_size"] != 1 or cfg["num_workers"] != 0 or cfg["pin_memory"] is not False
            or cfg["spatial_policy"] != "voxel_grid_only"):
        raise ValueError("Unsupported CPU/memory/voxel-grid configuration.")
    for key, expected in [("model", MODEL), ("preprocessing", PREPROCESSING), ("loss", LOSS), ("optimizer", OPTIMIZER), ("validation", VALIDATION)]:
        if cfg[key] != expected:
            raise ValueError(f"{key} differs from the frozen baseline settings.")
    sampling = cfg["sampling"]
    if (not isinstance(sampling, dict) or set(sampling) != {"patch_size", "foreground_probability", "attempted_empty_probability", "random_probability", "empty_attempts", "patches_per_case", "case_order"}
            or sampling["patch_size"] != [64, 64, 64] or sampling["foreground_probability"] != .5
            or sampling["attempted_empty_probability"] != .25 or sampling["random_probability"] != .25
            or sampling["empty_attempts"] != 30 or sampling["case_order"] != "shuffled_without_replacement"
            or type(sampling["patches_per_case"]) is not int or sampling["patches_per_case"] < 1):
        raise ValueError("Unsupported or undocumented sampling configuration.")
    init = cfg["initialization_checkpoint"]
    if init is not None and (not isinstance(init, dict) or set(init) != {"path", "sha256"} or init["sha256"] != HISTORICAL_SHA256):
        raise ValueError("Only the hash-identified historical initialization is permitted.")
    parsed = {k: portable_absolute(cfg[k]) for k in ("dataset_root", "manifest", "output_root")}
    protected = [parsed["dataset_root"], parsed["manifest"].parent]
    for i, value in enumerate(identity_paths(cfg["dataset_identity"])):
        parsed[f"identity_{i}"] = portable_absolute(value)
        protected.append(parsed[f"identity_{i}"].parent)
    if init:
        parsed["initialization"] = portable_absolute(init["path"])
        protected.append(parsed["initialization"].parent)
    if cfg["cache_directory"] is not None:
        parsed["cache_directory"] = portable_absolute(cfg["cache_directory"])
    if len({type(p) for p in parsed.values()}) != 1:
        raise ValueError("Do not mix Windows and POSIX path configurations.")
    if native_paths(cfg):
        protected = [Path(p).resolve() for p in protected] + [Path(__file__).resolve().parents[2]]
        destinations = [Path(cfg["output_root"]).resolve()]
        if cfg["cache_directory"]:
            destinations.append(Path(cfg["cache_directory"]).resolve())
    else:
        destinations = [parsed["output_root"]] + ([parsed["cache_directory"]] if cfg["cache_directory"] else [])
    if any(destination.is_relative_to(path) for destination in destinations for path in protected):
        raise ValueError("Output/cache roots must be outside repository and protected source directories.")
    return cfg


def load_config(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        return validate_config(json.load(stream))


def environment_info(threads, device=None, mixed_precision=False):
    device = torch.device("cpu") if device is None else torch.device(device)
    gpu = torch.cuda.get_device_properties(device) if device.type == "cuda" else None
    return {"python": platform.python_version(), "platform": platform.platform(),
            "machine": platform.machine(), "processor": platform.processor(),
            "torch": str(torch.__version__), "numpy": str(np.__version__), "nibabel": str(nib.__version__),
            "device": str(device), "mixed_precision": mixed_precision,
            "cuda_runtime": torch.version.cuda if gpu else None,
            "gpu_name": gpu.name if gpu else None,
            "compute_capability": [gpu.major, gpu.minor] if gpu else None,
            "cudnn": torch.backends.cudnn.version() if gpu else None,
            "cpu_threads": threads, "interop_threads": torch.get_num_interop_threads(),
            "deterministic_algorithms": True, "mkldnn_deterministic": True,
            "tf32": False}


def context_for(cfg, index, device=None):
    device = select_device(cfg.get("device", "cpu")) if device is None else device
    return {**index.contract(), "model_config": {**cfg["model"], "parameter_count": 85_177},
            "preprocessing_config": cfg["preprocessing"], "sampling_config": cfg["sampling"],
            "loss_config": cfg["loss"], "optimizer_config": cfg["optimizer"],
            "validation_config": cfg["validation"], "spatial_policy": cfg["spatial_policy"],
            "physical_measurements_authorized": False, "seed": cfg["seed"],
            "memory_config": {k: cfg[k] for k in ("batch_size", "num_workers", "pin_memory", "max_cache_bytes")},
            "checkpoint_every": cfg["checkpoint_every"], "validation_every": cfg["validation_every"],
            "environment": environment_info(cfg["cpu_threads"], device, cfg.get("mixed_precision", False))}


def preflight(cfg, resume=None):
    cfg = validate_config(cfg)
    if not native_paths(cfg):
        raise ValueError("Config paths belong to another operating system; run on their intended host.")
    device = select_device(cfg["device"])
    amp_enabled(device, cfg["mixed_precision"])
    index = build_index(cfg["dataset_root"], cfg["manifest"], expected_training=cfg["expected_training_cases"], expected_validation=cfg["expected_validation_cases"], dataset_identity=cfg["dataset_identity"])
    unknown_masks, largest = 0, 0
    for case in index.cases.values():
        ct, mask = check_pair(index, case, cfg["sampling"]["patch_size"])
        required = math.prod(ct.shape) * 3
        largest = max(largest, required)
        if required > cfg["max_cache_bytes"]:
            raise DataError("A case exceeds the configured cache budget.")
        unknown_masks += int(mask.units == "unknown")
    model = SmallUNet3D(base=8)
    if sum(p.numel() for p in model.parameters()) != 85_177:
        raise CheckpointError("Unexpected model parameter count.")
    context = context_for(cfg, index, device)
    initialization = {"kind": "fresh_seeded_initialization", "sha256": None}
    recovery, compatibility = initial_validation_state(), {"runtime_compatible": None, "exact_resume_supported": None,
                                                         "reason": "No resume checkpoint supplied; historical initialization is not exact resume."}
    if resume:
        saved = inspect_resume(resume, context)
        _strict_state(model, saved["model_state_dict"])
        initialization = {"kind": "new_experiment_resume", "global_step": saved["global_step"]}
        recovery, compatibility = saved["validation_state"], resume_assessment(saved, context)
    elif cfg["initialization_checkpoint"]:
        init = cfg["initialization_checkpoint"]
        initialization = initialize_weights(model, init["path"], init["sha256"], index.ids("Training"))
    return index, {"mode": "preflight_only", "training_started": False, "forward_passes": 0,
                   "optimizer_updates": 0, "headers_checked": len(index.cases) * 2,
                   "training_cases": len(index.ids("Training")), "validation_cases": len(index.ids("Val")),
                   "testing_cases_indexed": 0, "testing_records_excluded": index.testing_excluded,
                   "unknown_mask_units": unknown_masks, "warning": VOXEL_WARNING,
                   "parameters": 85_177, "initialization": initialization,
                   "validation_recovery": recovery, "runtime_compatibility": compatibility,
                   "dataset_identity_level": index.dataset_identity["level"],
                   "manifest_provenance": index.dataset_identity["provenance"],
                   "device": str(device), "mixed_precision": cfg["mixed_precision"],
                   "gpu": gpu_status(device, cfg["gpu_monitoring"]),
                   "cache_directory": cfg["cache_directory"],
                   "memory": {"single_case_cache": True, "raw_CT_and_uint8_mask_max_bytes": largest,
                              **{k: cfg[k] for k in ("max_cache_bytes", "batch_size", "num_workers", "pin_memory", "cpu_threads")}},
                   "fingerprints": index.contract(),
                   "voxel_payload_scan": "No voxel decoding; compressed file SHA-256 verified" if cfg["dataset_identity"]["verify_content"] else "not performed during preflight",
                   "resume_limits": "Exact resume requires compatible runtime/numerical settings and verified/pinned identity for relocated storage; pending validation precedes training."}


def configure_runtime(cfg, device=None):
    if device is not None and device.type == "cuda":
        if os.environ.get("CUBLAS_WORKSPACE_CONFIG") not in (":4096:8", ":16:8"):
            raise ValueError("Set CUBLAS_WORKSPACE_CONFIG=:4096:8 before starting the CUDA process for deterministic execution.")
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_num_threads(cfg["cpu_threads"])
    torch.use_deterministic_algorithms(True)
    torch.backends.mkldnn.deterministic = True
    random.seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    torch.manual_seed(cfg["seed"])


def make_optimizer(model, cfg):
    o = cfg["optimizer"]
    return torch.optim.AdamW(model.parameters(), lr=o["lr"], weight_decay=o["weight_decay"],
                            betas=tuple(o["betas"]), eps=o["eps"], foreach=False, fused=False)


def training_step(model, optimizer, sampler, cache, cfg, *, device=None, scaler=None):
    device = torch.device(device) if device is not None else next(model.parameters()).device
    mixed = amp_enabled(device, cfg.get("mixed_precision", False))
    scaler = make_scaler(device, mixed) if scaler is None else scaler
    x, y, info = sampler.draw(cache)
    model.train()
    optimizer.zero_grad(set_to_none=True)
    with autocast_context(device, mixed):
        logits = model(torch.from_numpy(x).to(device))
    targets = torch.from_numpy(y).to(device)
    loss = weighted_bce_dice(logits.float(), targets.float(), cfg["loss"]["positive_weight"], cfg["loss"]["smooth"])
    if not torch.isfinite(loss):
        raise DataError("Non-finite training loss.")
    scaler.scale(loss).backward()
    scaler.unscale_(optimizer)  # Clipping must see unscaled gradients.
    finite = all(p.grad is None or torch.isfinite(p.grad).all().item() for p in model.parameters())
    if not finite and not mixed:
        raise DataError("Non-finite gradient; no optimizer update performed.")
    norm = torch.nn.utils.clip_grad_norm_(model.parameters(), cfg["optimizer"]["gradient_clip_norm"], error_if_nonfinite=True) if finite else None
    # GradScaler skips an overflowing FP16 update and reduces the scale. Record
    # this explicitly; the batch/sampler boundary still advances coherently.
    scaler.step(optimizer)
    scaler.update()
    with torch.no_grad():
        metrics = confusion(torch.sigmoid(logits.float()).cpu().numpy() >= .5, y > 0)
    return {**info, "loss": float(loss.item()), "gradient_norm_before_clip": float(norm.item()) if norm is not None else None,
            "optimizer_update_performed": finite, "amp_overflow": not finite,
            "grad_scaler_scale": scaler.get_scale(),
            "training_patch_threshold": .5, "patch_metrics": metrics}


def run_training(cfg, index, resume=None):
    """Called only after the explicit --train gate; never by import/preflight."""
    cfg = validate_config(cfg)
    device = select_device(cfg["device"])
    mixed = amp_enabled(device, cfg["mixed_precision"])
    configure_runtime(cfg, device)
    model = SmallUNet3D(base=8)
    initialization = {"kind": "fresh_seeded_initialization", "sha256": None}
    if not resume and cfg["initialization_checkpoint"]:
        init = cfg["initialization_checkpoint"]
        initialization = initialize_weights(model, init["path"], init["sha256"], index.ids("Training"))
    model = model.to(device)  # Keep FP32 parameters; only forward uses autocast.
    optimizer = make_optimizer(model, cfg)  # Always fresh for historical initialization.
    scaler = make_scaler(device, mixed)
    sampler = PatchSampler(index.ids("Training"), cfg["seed"], cfg["sampling"]["patches_per_case"])
    context = context_for(cfg, index, device)
    step = updates = 0
    validation_state = initial_validation_state()
    if resume:
        saved = inspect_resume(resume, context)
        step, initialization = restore_checkpoint(saved, model, optimizer, sampler, scaler=scaler)
        updates = saved["optimizer_updates"]
        validation_state = saved["validation_state"]
    if step > cfg["max_steps"]:
        raise ValueError("Resume step exceeds the requested maximum.")
    root = Path(cfg["output_root"])
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    run_dir.mkdir(exist_ok=False)
    with (run_dir / "config.json").open("x", encoding="utf-8") as stream:
        json.dump(cfg, stream, indent=2, allow_nan=False)
    cache = SingleCaseCache(index, cfg["sampling"]["patch_size"], cfg["max_cache_bytes"], cfg["cache_directory"])
    stop, previous_handlers, last_saved = [False], {}, None
    latest_checkpoint, pending_hash = None, None
    interruption = None
    reset_peak_memory(device, cfg["gpu_monitoring"])
    def request_stop(signum, frame):
        stop[0] = True  # Finish this step, then serialize a coherent boundary.
    def save():
        nonlocal last_saved, latest_checkpoint, pending_hash
        phase = validation_phase(validation_state, step, cfg["validation_every"])
        key = (step, phase)
        if key != last_saved:
            suffix = "-validation-completed" if phase == "validation_completed" else ""
            path = run_dir / f"step-{step:09d}{suffix}.pt"
            value = make_checkpoint(model, optimizer, sampler, step, context, initialization,
                                    scaler=scaler, configuration=cfg, optimizer_updates=updates,
                                    validation_state=validation_state)
            if phase == "validation_completed":
                value["validation_parent_sha256"] = pending_hash
            atomic_save(path, value)
            latest_checkpoint, last_saved = path, key
            if phase == "validation_pending":
                pending_hash = digest(path)
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[sig] = signal.signal(sig, request_stop)
        with (run_dir / "metrics.jsonl").open("x", encoding="utf-8") as log:
            save()  # Reproducible initialization/resume boundary before the first update.
            while not stop[0]:
                if validation_state["pending"]:
                    # Pending state is durable before any validation work. A
                    # failed/cancelled validation never permits another update.
                    validation_rng, prior_mode = rng_state(device), model.training
                    try:
                        result = validate_cohort(model, cache, **cfg["validation"], stop_requested=lambda: stop[0],
                                                 device=device, mixed_precision=mixed)
                    except (ValidationCancelled, KeyboardInterrupt):
                        stop[0] = True
                        interruption = "validation_pending_recovery_required"
                        continue
                    finally:
                        restore_rng(validation_rng)
                        model.train(prior_mode)
                    validation_state = {"pending": False, "completed": True, "validation_step": step,
                                        "last_completed_step": step, "last_completed_result": result}
                    save()  # Persist the result before logging or another batch.
                    log.write(json.dumps({"phase": "validation", "global_step": step, **result}, allow_nan=False) + "\n")
                    log.flush()
                    continue
                if step >= cfg["max_steps"]:
                    break
                boundary = make_checkpoint(model, optimizer, sampler, step, context, initialization,
                                           scaler=scaler, configuration=cfg, optimizer_updates=updates,
                                           validation_state=validation_state)
                try:
                    row = training_step(model, optimizer, sampler, cache, cfg, device=device, scaler=scaler)
                except KeyboardInterrupt:
                    # A raw KeyboardInterrupt can arrive mid-update. Roll back
                    # model/BN, optimizer, sampler, scaler and RNG, not just step.
                    if device.type == "cuda":
                        torch.cuda.synchronize(device)
                    scaler = make_scaler(device, mixed)
                    restore_checkpoint(boundary, model, optimizer, sampler, scaler=scaler)
                    stop[0], interruption = True, "keyboard_rolled_back_to_completed_boundary"
                    break
                step += 1
                updates += int(row["optimizer_update_performed"])
                if step % cfg["validation_every"] == 0:
                    validation_state = {**validation_state, "pending": True, "completed": False, "validation_step": step}
                    save()  # Required even when a stop signal arrived this batch.
                if cfg["gpu_monitoring"]:
                    row["gpu"] = gpu_status(device)
                log.write(json.dumps({"phase": "training", "global_step": step, **row}, allow_nan=False) + "\n")
                log.flush()
                if step % cfg["checkpoint_every"] == 0:
                    save()
            save()
    finally:
        cache.clear()
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
    return {"run_directory": str(run_dir), "global_step": step, "optimizer_updates": updates,
            "validation_state": validation_state, "latest_checkpoint": str(latest_checkpoint),
            "stopped_by_signal": stop[0], "interruption": interruption,
            "gpu": gpu_status(device, cfg["gpu_monitoring"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--preflight", action="store_true")
    action.add_argument("--train", action="store_true", help="Explicitly authorize execution; omission means preflight only.")
    parser.add_argument("--resume", type=Path, help="Only a new-format complete experiment checkpoint; never historical weights.")
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config)
        index, report = preflight(cfg, args.resume)
        print(json.dumps(report, indent=2, allow_nan=False), flush=True)
        if args.train:
            print(json.dumps(run_training(cfg, index, args.resume), indent=2), flush=True)
        return 0
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(f"Stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
