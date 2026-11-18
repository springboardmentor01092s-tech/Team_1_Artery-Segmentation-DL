"""Restricted loading and atomic, experiment-scoped research checkpoints."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import random
import tempfile

import numpy as np
import torch


HISTORICAL_SHA256 = "e208fa586bb9bb50dc77b913caa0355a547bad529f9f0d61df17880b2efc5254"
FORMAT = "vascuai-baseline-training-v3"


class CheckpointError(ValueError):
    pass


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def restricted_load(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise CheckpointError("Missing or oversized baseline checkpoint.")
    before = (path.stat().st_size, path.stat().st_mtime_ns, digest(path))
    try:
        data = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
    except Exception as exc:
        raise CheckpointError("Restricted checkpoint loading failed; no unsafe fallback is allowed.") from exc
    if before != (path.stat().st_size, path.stat().st_mtime_ns, digest(path)):
        raise CheckpointError("Checkpoint changed while reading.")
    if not isinstance(data, dict):
        raise CheckpointError("Expected a checkpoint mapping.")
    return data


def _strict_state(model, state):
    if not isinstance(state, dict) or any(not torch.is_tensor(v) or not torch.isfinite(v).all() for v in state.values()):
        raise CheckpointError("Invalid or non-finite model state.")
    try:
        model.load_state_dict(state, strict=True)
    except (RuntimeError, KeyError) as exc:
        raise CheckpointError("Strict architecture/state compatibility failed.") from exc


def initialize_weights(model, path, expected_sha256, training_ids):
    if digest(path) != expected_sha256:
        raise CheckpointError("Initialization checkpoint SHA-256 mismatch.")
    saved = restricted_load(path)
    if (saved.get("base_channels") != 8 or tuple(saved.get("patch_size", ())) != (64, 64, 64)
            or sum(p.numel() for p in model.parameters()) != 85_177):
        raise CheckpointError("Initialization requires the compatible SmallUNet3D base-8 architecture.")
    ids = saved.get("training_case_ids")
    if (not isinstance(ids, list) or not ids or any(type(i) is not int for i in ids)
            or len(ids) != len(set(ids)) or not set(ids).issubset(training_ids)):
        raise CheckpointError("Initialization declares non-Training or unknown case IDs.")
    _strict_state(model, saved.get("model_state_dict"))
    # Deliberately do not read/restore historical optimizer or RNG state.
    return {"kind": "historical_weights_only", "sha256": expected_sha256,
            "historical_recorded_step": saved.get("step"), "new_global_step": 0}


def rng_state(device=None):
    legacy = np.random.get_state()
    cuda = []
    if device is not None and torch.device(device).type == "cuda":
        device = torch.device(device)
        cuda = [{"device": device.index or 0, "state": torch.cuda.get_rng_state(device).cpu().clone()}]
    return {"python": random.getstate(), "torch_cpu": torch.get_rng_state().clone(), "cuda": cuda,
            "numpy": {"name": legacy[0], "keys": legacy[1].tolist(), "position": legacy[2],
                      "has_gauss": legacy[3], "cached_gaussian": legacy[4]}}


def restore_rng(state):
    random.setstate(state["python"])
    torch.set_rng_state(state["torch_cpu"])
    n = state["numpy"]
    np.random.set_state((n["name"], np.asarray(n["keys"], dtype=np.uint32), n["position"], n["has_gauss"], n["cached_gaussian"]))
    for item in state.get("cuda", []):
        if not torch.cuda.is_available():
            raise CheckpointError("CUDA RNG state requires a compatible CUDA runtime.")
        torch.cuda.set_rng_state(item["state"].cpu(), device=item["device"])


def initial_validation_state():
    return {"pending": False, "completed": False, "validation_step": None,
            "last_completed_step": None, "last_completed_result": None}


def validation_phase(state, step, every=None):
    """Reject ambiguous state rather than silently skipping a required validation."""
    if not isinstance(state, dict) or set(state) != set(initial_validation_state()):
        raise CheckpointError("Missing/invalid validation recovery state.")
    pending, completed = state["pending"], state["completed"]
    current, last = state["validation_step"], state["last_completed_step"]
    if type(pending) is not bool or type(completed) is not bool or (pending and completed):
        raise CheckpointError("Inconsistent validation status.")
    if current is None:
        if state != initial_validation_state():
            raise CheckpointError("Inconsistent initial validation state.")
    else:
        if type(current) is not int or not 0 < current <= step or pending == completed:
            raise CheckpointError("Invalid validation step/status.")
        if pending and current != step:
            raise CheckpointError("Training advanced past pending validation.")
        if completed and last != current:
            raise CheckpointError("Completed validation result is not bound to its step.")
    if last is None:
        if state["last_completed_result"] is not None or completed:
            raise CheckpointError("Missing completed validation step.")
    elif type(last) is not int or not 0 < last <= step or (pending and last >= current) or not isinstance(state["last_completed_result"], dict):
        raise CheckpointError("Invalid last completed validation result.")
    try:
        json.dumps(state, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CheckpointError("Validation result is not finite JSON data.") from exc
    if every is not None:
        due = step // every * every
        if (current != (due or None) or (last is not None and last % every)
                or (pending and last != ((due - every) or None))):
            raise CheckpointError("Scheduled validation was skipped or has the wrong step.")
    return "validation_pending" if pending else "validation_completed" if completed and current == step else "completed_training_step"


def make_checkpoint(model, optimizer, sampler, global_step, context, initialization, *,
                    scaler=None, scheduler=None, configuration=None, optimizer_updates=None, validation_state=None):
    if sampler.draws != global_step:
        raise CheckpointError("Checkpoint must describe a completed training-batch boundary.")
    state = copy.deepcopy(initial_validation_state() if validation_state is None else validation_state)
    phase = validation_phase(state, global_step, context.get("validation_every"))
    return {"format": FORMAT, "step": global_step, "global_step": global_step,
            "epoch": sampler.epoch, "phase": phase, "validation_state": state,
            "model_state_dict": copy.deepcopy(model.state_dict()),
            "optimizer_state_dict": copy.deepcopy(optimizer.state_dict()),
            "rng_states": rng_state(next(model.parameters()).device), "sampler_state": sampler.state_dict(),
            "grad_scaler_state": copy.deepcopy(scaler.state_dict()) if scaler is not None else None,
            "scheduler_state": copy.deepcopy(scheduler.state_dict()) if scheduler is not None else None,
            "configuration": copy.deepcopy(configuration),
            "optimizer_updates": global_step if optimizer_updates is None else optimizer_updates,
            "initialization": copy.deepcopy(initialization),
            "initialization_checkpoint_sha256": initialization.get("sha256"),
            "context": copy.deepcopy(context), **copy.deepcopy(context)}


def atomic_save(path, value):
    """Flush and close an owned same-directory temporary, then os.replace.

    Run directories are unique single-writer experiment directories. Existing
    destinations (including historical weights) are refused, not updated.
    """
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise FileExistsError("Checkpoint destination already exists.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w+b", prefix=".checkpoint-", suffix=".tmp", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            torch.save(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists() or path.is_symlink():
            raise FileExistsError("Checkpoint destination appeared during serialization.")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)  # Only this call's owned temporary.


def resume_assessment(saved, context):
    old = saved.get("context", {})
    dataset_same = all(old.get(k) == context.get(k) for k in
                       ("manifest_fingerprint", "split_fingerprint", "dataset_identity", "training_case_ids", "validation_case_ids"))
    storage_same = old.get("storage") == context.get("storage")
    level = context.get("dataset_identity", {}).get("level", "structural")
    runtime_same = old.get("environment") == context.get("environment")
    remaining = lambda value: {k: v for k, v in value.items() if k not in ("storage", "environment")}
    numerical_same = remaining(old) == remaining(context)
    return {"dataset_identity_matches": dataset_same, "runtime_compatible": runtime_same,
            "storage_unchanged": storage_same, "dataset_identity_level": level,
            "exact_resume_supported": dataset_same and runtime_same and numerical_same and
                                      (storage_same or level in ("version-pinned", "content-verified")),
            "restriction": "Unchanged runtime/numerical settings required; relocation needs a pinned version or verified content, not structural metadata alone."}


def inspect_resume(path, context):
    saved = restricted_load(path)
    if saved.get("format") != FORMAT:
        raise CheckpointError("Historical weights are initialization only; older experiment formats lack v3 recovery state.")
    assessment = resume_assessment(saved, context)
    if not assessment["exact_resume_supported"]:
        raise CheckpointError("Resume dataset/split, runtime, numerical configuration or unverified storage differs: " + json.dumps(assessment))
    if (type(saved.get("global_step")) is not int or saved["global_step"] < 0
            or saved.get("step") != saved["global_step"]
            or saved.get("sampler_state", {}).get("draws") != saved["global_step"]
            or saved.get("epoch") != saved["sampler_state"].get("epoch")):
        raise CheckpointError("Resume counters/phase are inconsistent.")
    if saved.get("phase") != validation_phase(saved.get("validation_state"), saved["global_step"], context.get("validation_every")):
        raise CheckpointError("Resume validation phase is inconsistent.")
    if (type(saved.get("optimizer_updates")) is not int
            or not 0 <= saved["optimizer_updates"] <= saved["global_step"]):
        raise CheckpointError("Invalid optimizer-update count.")
    for key, value in saved["context"].items():
        if saved.get(key) != value:
            raise CheckpointError("Checkpoint context fields disagree.")
    if saved["validation_state"]["pending"]:
        # A caller may retain the pre-validation filename. Prefer only a
        # completed sibling cryptographically bound to this exact checkpoint.
        path = Path(path)
        completed = path.with_name(path.stem + "-validation-completed.pt")
        if completed.exists():
            result = inspect_resume(completed, context)
            if (result.get("validation_parent_sha256") != digest(path)
                    or result["global_step"] != saved["global_step"]
                    or result["phase"] != "validation_completed"):
                raise CheckpointError("Completed validation sibling is not bound to the pending checkpoint.")
            return result
    return saved


def restore_checkpoint(saved, model, optimizer, sampler, *, scaler=None, scheduler=None):
    _strict_state(model, saved["model_state_dict"])
    try:
        optimizer.load_state_dict(saved["optimizer_state_dict"])
        sampler.load_state_dict(saved["sampler_state"])
        if (scaler is None) != (saved.get("grad_scaler_state") is None):
            raise CheckpointError("Scaler configuration differs from the checkpoint.")
        if scaler is not None:
            scaler.load_state_dict(saved["grad_scaler_state"])
        if (scheduler is None) != (saved.get("scheduler_state") is None):
            raise CheckpointError("Scheduler configuration differs from the checkpoint.")
        if scheduler is not None:
            scheduler.load_state_dict(saved["scheduler_state"])
        restore_rng(saved["rng_states"])
    except (KeyError, ValueError, RuntimeError, TypeError) as exc:
        raise CheckpointError("Cannot restore a complete experiment state.") from exc
    return saved["global_step"], saved["initialization"]
