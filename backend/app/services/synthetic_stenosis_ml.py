"""Synthetic-only 3D stenosis-classification experiment.

This optional research module trains and evaluates only on procedurally generated
phantoms. It deliberately refuses unbound volumes at inference and is not a clinical
provider, patient-case service, or source of ground truth. PyTorch is imported lazily
so the ordinary API runtime does not acquire a hard dependency.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

GENERATOR_ID = "vascuai-synthetic-vessel-phantom"
GENERATOR_VERSION = "0.1.0"
MODEL_ID = "synthetic-3d-cnn"
MODEL_VERSION = "0.1.0"
NOTICE = "SYNTHETIC RESEARCH ONLY - NOT A PATIENT RESULT OR CLINICAL DIAGNOSIS"
CLASS_NAMES = ("normal", "mild", "moderate", "severe", "critical_very_severe")
# Generator bins only. These are not clinical cutoffs and must never be reused as
# clinical severity thresholds.
SYNTHETIC_REDUCTION_BINS = ((0.0, 0.0), (0.15, 0.28), (0.35, 0.48), (0.55, 0.68), (0.75, 0.88))
DEFAULT_RESEARCH_SEVERITY_THRESHOLDS = (10.0, 30.0, 50.0, 70.0)
# Backward-compatible name used by the synthetic training/checkpoint metadata.
SYNTHETIC_SEVERITY_THRESHOLDS = DEFAULT_RESEARCH_SEVERITY_THRESHOLDS
SYNTHETIC_TRIGGER_RATIO = 0.75
SYNTHETIC_RADIAL_SQUARED_QUANTILE = 0.90
SYNTHETIC_PEAK_PROMINENCE = 0.05
DEFAULT_SHAPE = (24, 24, 24)


def generate_phantom(sample_id: int, class_id: int, seed: int, shape=DEFAULT_SHAPE, *,
                     orientation_ijk: tuple[float, float, float] | None = None,
                     noise_std: float = 0.025,
                     multiple_narrowings: bool | None = None,
                     include_geometry_ground_truth: bool = False) -> dict[str, Any]:
    """Create one noisy, oblique synthetic tube with a controlled radius change."""
    if type(sample_id) is not int or sample_id < 0 or type(class_id) is not int or not 0 <= class_id < len(CLASS_NAMES):
        raise ValueError("invalid synthetic sample identity or class")
    if type(seed) is not int or seed < 0 or tuple(shape) != DEFAULT_SHAPE:
        raise ValueError("unsupported synthetic seed or shape")
    if type(noise_std) not in (float, int) or not np.isfinite(noise_std) or not 0 <= noise_std <= 0.15:
        raise ValueError("noise_std must be finite and between 0 and 0.15")
    if multiple_narrowings is not None and type(multiple_narrowings) is not bool:
        raise ValueError("multiple_narrowings must be a boolean or None")
    if type(include_geometry_ground_truth) is not bool:
        raise ValueError("include_geometry_ground_truth must be a boolean")
    if class_id == 0 and multiple_narrowings is True:
        raise ValueError("normal phantoms cannot contain synthetic narrowings")
    if orientation_ijk is not None:
        requested_axis = np.asarray(orientation_ijk, dtype=np.float32)
        if requested_axis.shape != (3,) or not np.isfinite(requested_axis).all() or np.linalg.norm(requested_axis) <= 1e-8:
            raise ValueError("orientation_ijk must be a finite nonzero 3-vector")
        requested_axis /= np.linalg.norm(requested_axis)
    rng = np.random.default_rng(seed)
    coords = np.indices(DEFAULT_SHAPE, dtype=np.float32)
    center = np.asarray([(n - 1) / 2 for n in DEFAULT_SHAPE], dtype=np.float32)
    center += rng.uniform(-0.75, 0.75, size=3).astype(np.float32)
    axis = rng.normal(size=3).astype(np.float32)
    axis /= np.linalg.norm(axis)
    # Consume the same random axis draw as the original generator so optional
    # controlled orientations do not perturb the later seeded parameters.
    if orientation_ijk is not None:
        axis = requested_axis
    relative = coords - center[:, None, None, None]
    axial = np.einsum("i,ijkl->jkl", axis, relative)
    radial2 = np.maximum(0.0, np.sum(relative * relative, axis=0) - axial * axial)
    radius = float(rng.uniform(4.0, 6.0))
    low, high = SYNTHETIC_REDUCTION_BINS[class_id]
    reduction = 0.0 if class_id == 0 else float(rng.uniform(low, high))
    lesion_center = float(rng.uniform(-1.0, 1.0))
    lesion_width = float(rng.uniform(1.6, 2.8))
    profile = np.zeros(DEFAULT_SHAPE, dtype=np.float32)
    if class_id:
        profile = reduction * np.exp(-0.5 * ((axial - lesion_center) / lesion_width) ** 2)
    sampled_multiple = bool(class_id > 0 and rng.random() < 0.25)
    multiple = sampled_multiple if multiple_narrowings is None else multiple_narrowings
    lesions = []
    if class_id > 0:
        lesions.append({"center_axial_voxels": lesion_center, "width_axial_voxels": lesion_width,
                        "peak_diameter_reduction_fraction": reduction})
    if multiple:
        second_center = lesion_center + float(rng.choice((-1.0, 1.0))) * float(rng.uniform(4.0, 6.0))
        second_reduction = reduction * float(rng.uniform(0.55, 0.85))
        profile = np.maximum(profile, second_reduction * np.exp(-0.5 * ((axial - second_center) / lesion_width) ** 2))
        lesions.append({"center_axial_voxels": second_center, "width_axial_voxels": lesion_width,
                        "peak_diameter_reduction_fraction": second_reduction})
    local_radius = radius * (1.0 - profile)
    # This is a generated scalar phantom, not a CT simulation.
    inside = radial2 <= local_radius * local_radius
    noise = rng.normal(0.08, float(noise_std), size=DEFAULT_SHAPE).astype(np.float32)
    volume = np.clip(noise + inside.astype(np.float32) * 0.72, 0.0, 1.0).astype(np.float32)
    digest = hashlib.sha256(volume.tobytes(order="C")).hexdigest()
    provenance = {
        "source": GENERATOR_ID,
        "generator_version": GENERATOR_VERSION,
        "sample_id": sample_id,
        "seed": seed,
        "volume_sha256": digest,
        "controlled_max_diameter_reduction_fraction": reduction,
        "multiple_synthetic_narrowings": multiple,
        "axis_ijk": axis.tolist(),
        "nominal_outer_reference_diameter_voxels": 2 * radius,
        "notice": NOTICE,
    }
    if include_geometry_ground_truth:
        for lesion in lesions:
            center_profile = max(
                item["peak_diameter_reduction_fraction"]
                * np.exp(-0.5 * ((lesion["center_axial_voxels"] - item["center_axial_voxels"])
                                / item["width_axial_voxels"]) ** 2)
                for item in lesions
            )
            minimum_radius = float(radius * (1.0 - center_profile))
            lesion["reference_radius_voxels"] = float(radius)
            lesion["minimum_radius_voxels"] = minimum_radius
            lesion["percentage_narrowing"] = float(100.0 * (1.0 - minimum_radius / radius))
        provenance["synthetic_geometry_ground_truth"] = {
            "lesions": lesions,
            "phantom_center_ijk": center.tolist(),
            "nominal_radius_voxels": radius,
            "nominal_minimum_radius_voxels": float(radius * (1.0 - max((item["peak_diameter_reduction_fraction"] for item in lesions), default=0.0))),
            "nominal_percentage_narrowing": float(100.0 * max((item["peak_diameter_reduction_fraction"] for item in lesions), default=0.0)),
            "noise_std": float(noise_std),
        }
    return {
        "sample_id": sample_id,
        "volume": volume,
        "label": class_id,
        "provenance": provenance,
    }


def make_splits(sample_count: int, seed: int) -> dict[str, list[int]]:
    """Split unique generated sample IDs before materializing volumes."""
    if type(sample_count) is not int or sample_count < 25 or sample_count % 5 or type(seed) is not int:
        raise ValueError("sample_count must be a multiple of five and at least 25")
    rng = np.random.default_rng(seed)
    split_lists = {"train": [], "validation": [], "test": []}
    for class_id in range(len(CLASS_NAMES)):
        class_ids = np.arange(class_id, sample_count, len(CLASS_NAMES))
        rng.shuffle(class_ids)
        train_end = int(len(class_ids) * 0.6)
        valid_end = int(len(class_ids) * 0.8)
        split_lists["train"].extend(class_ids[:train_end].tolist())
        split_lists["validation"].extend(class_ids[train_end:valid_end].tolist())
        split_lists["test"].extend(class_ids[valid_end:].tolist())
    for split in split_lists.values(): rng.shuffle(split)
    splits = split_lists
    if any(not splits[k] for k in splits) or sum(map(len, splits.values())) != sample_count:
        raise ValueError("invalid split")
    sets = [set(splits[k]) for k in splits]
    if any(sets[i] & sets[j] for i in range(3) for j in range(i + 1, 3)):
        raise RuntimeError("sample leakage across splits")
    return splits


def _torch():
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, Dataset
    except ImportError as exc:
        raise RuntimeError("Install the optional CPU/CUDA PyTorch research dependencies first") from exc
    return torch, nn, DataLoader, Dataset


def build_model():
    torch, nn, _, _ = _torch()

    class SyntheticVesselCNN3D(nn.Module):
        def __init__(self):
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv3d(1, 4, 3, padding=1), nn.ReLU(inplace=False), nn.MaxPool3d(2),
                nn.Conv3d(4, 8, 3, padding=1), nn.ReLU(inplace=False), nn.MaxPool3d(2),
                nn.Conv3d(8, 12, 3, padding=1), nn.ReLU(inplace=False),
                nn.AdaptiveAvgPool3d(1),
            )
            self.classifier = nn.Linear(12, len(CLASS_NAMES))

        def forward(self, x):
            return self.classifier(self.features(x).flatten(1))

    return SyntheticVesselCNN3D()


class _PhantomDataset:
    def __new__(cls, samples, ids):
        _, _, _, Dataset = _torch()

        class DatasetImpl(Dataset):
            def __len__(self):
                return len(ids)

            def __getitem__(self, index):
                item = samples[ids[index]]
                return torch.from_numpy(item["volume"][None]), item["label"]

        torch, _, _, _ = _torch()
        return DatasetImpl()


def _scores(truth: list[int], predicted: list[int]) -> dict[str, Any]:
    confusion = np.zeros((len(CLASS_NAMES), len(CLASS_NAMES)), dtype=np.int64)
    for actual, result in zip(truth, predicted):
        confusion[actual, result] += 1
    precision, recall, f1 = [], [], []
    for cls in range(len(CLASS_NAMES)):
        tp = int(confusion[cls, cls]); fp = int(confusion[:, cls].sum() - tp); fn = int(confusion[cls, :].sum() - tp)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        precision.append(p); recall.append(r); f1.append(2 * p * r / (p + r) if p + r else 0.0)
    return {
        "scope": "synthetic_test_split_only",
        "n": len(truth),
        "accuracy": float(np.mean(np.asarray(truth) == np.asarray(predicted))) if truth else None,
        "macro_precision": float(np.mean(precision)),
        "macro_recall": float(np.mean(recall)),
        "macro_f1": float(np.mean(f1)),
        "confusion_matrix_rows_true_columns_predicted": confusion.tolist(),
        "class_names": list(CLASS_NAMES),
        "clinical_performance_claim": False,
    }


def _evaluate(model, samples, ids) -> tuple[dict[str, Any], float]:
    torch, _, _, _ = _torch()
    truth, predictions, total_loss = [], [], 0.0
    loss_fn = torch.nn.CrossEntropyLoss(reduction="sum")
    model.eval()
    with torch.no_grad():
        for sample_id in ids:
            sample = samples[sample_id]
            logits = model(torch.from_numpy(sample["volume"][None, None]))
            label = torch.tensor([sample["label"]], dtype=torch.long)
            total_loss += float(loss_fn(logits, label).item())
            truth.append(sample["label"]); predictions.append(int(logits.argmax(1).item()))
    metrics = _scores(truth, predictions)
    metrics["cross_entropy"] = total_loss / max(1, len(ids))
    return metrics, total_loss / max(1, len(ids))


def train_synthetic_model(output_dir: str | Path, sample_count: int = 100, epochs: int = 5, seed: int = 1729) -> dict[str, Any]:
    """Train a small CPU-capable CNN on generated phantoms, never medical inputs."""
    if type(epochs) is not int or not 1 <= epochs <= 50:
        raise ValueError("epochs must be between 1 and 50")
    torch, nn, DataLoader, _ = _torch()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
    splits = make_splits(sample_count, seed)
    # Balanced classes and unique IDs are generated independently before split selection.
    samples = [generate_phantom(i, i % len(CLASS_NAMES), seed + i * 7919) for i in range(sample_count)]
    train_loader = DataLoader(_PhantomDataset(samples, splits["train"]), batch_size=8, shuffle=True,
                              generator=torch.Generator().manual_seed(seed), num_workers=0)
    model = build_model().cpu()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()
    history = []; best_state = None; best_validation_loss = float("inf")
    for epoch in range(epochs):
        model.train(); total_loss = 0.0; seen = 0
        for x, y in train_loader:
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(x), y)
            loss.backward(); optimizer.step()
            total_loss += float(loss.item()) * len(y); seen += len(y)
        validation_metrics, validation_loss = _evaluate(model, samples, splits["validation"])
        history.append({"epoch": epoch + 1, "train_loss": total_loss / max(1, seen),
                        "validation_loss": validation_loss, "validation_accuracy": validation_metrics["accuracy"],
                        "validation_macro_f1": validation_metrics["macro_f1"]})
        if validation_loss < best_validation_loss:
            best_validation_loss = validation_loss
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
    if best_state is not None: model.load_state_dict(best_state)
    metrics, _ = _evaluate(model, samples, splits["test"])
    dataset_identity = [{"sample_id": item["sample_id"], "label": item["label"],
                         "provenance": item["provenance"]}
                        for item in samples]
    dataset_digest = hashlib.sha256(json.dumps(dataset_identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    checkpoint = {
        "schema_version": "synthetic-stenosis-checkpoint/0.1",
        "model_id": MODEL_ID, "model_version": MODEL_VERSION,
        "model_state_dict": model.state_dict(),
        "input_shape": list(DEFAULT_SHAPE), "class_names": list(CLASS_NAMES),
        "synthetic_reduction_bins": [list(x) for x in SYNTHETIC_REDUCTION_BINS],
        "generator_id": GENERATOR_ID, "generator_version": GENERATOR_VERSION,
        "dataset_sha256": dataset_digest, "split_sample_ids": splits,
        "seed": seed, "epochs": epochs, "training_history": history,
        "test_metrics": metrics,
        "experimental_research": True, "clinical_validation": False,
        "clinical_performance_claim": False,
        "clinical_gate_authorized": False, "training_release_authorized": False,
        "notice": NOTICE,
    }
    checkpoint_path = output / "synthetic-stenosis-cnn3d.pt"
    torch.save(checkpoint, checkpoint_path)
    summary = {k: v for k, v in checkpoint.items() if k != "model_state_dict"}
    (output / "training-summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    return {"checkpoint": str(checkpoint_path), "summary": summary}


def load_synthetic_model(checkpoint_path: str | Path):
    torch, _, _, _ = _torch()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    required = (checkpoint.get("schema_version") == "synthetic-stenosis-checkpoint/0.1"
                and checkpoint.get("model_id") == MODEL_ID
                and checkpoint.get("model_version") == MODEL_VERSION
                and checkpoint.get("input_shape") == list(DEFAULT_SHAPE)
                and checkpoint.get("class_names") == list(CLASS_NAMES)
                and checkpoint.get("synthetic_reduction_bins") == [list(x) for x in SYNTHETIC_REDUCTION_BINS]
                and checkpoint.get("experimental_research") is True
                and checkpoint.get("clinical_validation") is False
                and checkpoint.get("clinical_gate_authorized") is False
                and checkpoint.get("training_release_authorized") is False
                and checkpoint.get("generator_id") == GENERATOR_ID
                and checkpoint.get("generator_version") == GENERATOR_VERSION)
    if not required:
        raise ValueError("checkpoint is not an authorized synthetic-only research artifact")
    model = build_model(); model.load_state_dict(checkpoint["model_state_dict"]); model.eval()
    return model, checkpoint


@lru_cache(maxsize=2)
def _load_checkpoint_by_digest(checkpoint_path: str, actual_sha256: str):
    model, checkpoint = load_synthetic_model(checkpoint_path)
    return model, checkpoint, actual_sha256


def load_verified_checkpoint(checkpoint_path: str, expected_sha256: str):
    """Verify current file bytes, then reuse an already loaded matching model."""
    path = Path(checkpoint_path)
    try:
        junction = getattr(path, "is_junction", lambda: False)()
        if not path.is_absolute() or path.is_symlink() or junction or not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("checkpoint_path_or_size_invalid")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise ValueError("checkpoint_hash_mismatch")
        return _load_checkpoint_by_digest(str(path), actual)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        # Do not leak local checkpoint paths or deserialization details through API.
        raise ValueError("verified_synthetic_checkpoint_unavailable") from exc


def predict_synthetic(model, sample: dict[str, Any]) -> dict[str, Any]:
    """Inference is restricted to generated samples carrying intact synthetic provenance."""
    torch, _, _, _ = _torch()
    provenance = sample.get("provenance") if isinstance(sample, dict) else None
    if not isinstance(provenance, dict) or provenance.get("source") != GENERATOR_ID or provenance.get("generator_version") != GENERATOR_VERSION:
        raise ValueError("synthetic model refuses inputs without generator provenance")
    volume = np.asarray(sample.get("volume"))
    if volume.shape != DEFAULT_SHAPE or volume.dtype != np.float32 or hashlib.sha256(volume.tobytes(order="C")).hexdigest() != provenance.get("volume_sha256"):
        raise ValueError("synthetic input hash/shape/dtype mismatch")
    # Provenance is not trusted as a client claim. Recreate the phantom from the
    # recorded seed/label and require byte identity before permitting inference.
    try:
        recreated = generate_phantom(
            provenance["sample_id"], sample["label"], provenance["seed"],
            include_geometry_ground_truth=("synthetic_geometry_ground_truth" in provenance),
        )
    except (KeyError, TypeError, ValueError):
        raise ValueError("synthetic input cannot be reproduced from generator provenance") from None
    if recreated["provenance"] != provenance or not np.array_equal(recreated["volume"], volume):
        raise ValueError("synthetic generator provenance does not reproduce the supplied input")
    with torch.no_grad():
        probabilities = torch.softmax(model(torch.from_numpy(volume[None, None])), dim=1)[0].cpu().numpy()
    return {"sample_id": provenance["sample_id"], "class": CLASS_NAMES[int(probabilities.argmax())],
            "probabilities": probabilities.tolist(), "scope": "synthetic_generated_phantom_only",
            "notice": NOTICE, "clinical_validation": False, "clinical_gate_authorized": False,
            "training_release_authorized": False}


def gradcam3d(model, sample: dict[str, Any], target_class: int | None = None) -> dict[str, Any]:
    """Real 3D CNN Grad-CAM for a provenance-verified synthetic phantom only."""
    torch, _, _, _ = _torch()
    # Revalidate input through the same inference guard before producing attribution.
    prediction = predict_synthetic(model, sample)
    volume = torch.from_numpy(np.asarray(sample["volume"])[None, None]).requires_grad_(True)
    model.zero_grad(set_to_none=True)
    activations = model.features[:7](volume)
    activations.retain_grad()
    logits = model.classifier(model.features[7:](activations).flatten(1))
    cls = int(logits.argmax(1).item()) if target_class is None else int(target_class)
    if not 0 <= cls < len(CLASS_NAMES):
        raise ValueError("invalid synthetic class target")
    logits[0, cls].backward()
    gradients = activations.grad if activations.grad is not None else None
    if gradients is None:
        # The sequential feature block is not a leaf; capture its gradient explicitly.
        raise RuntimeError("Grad-CAM feature gradients are unavailable")
    weights = gradients.mean(dim=(2, 3, 4), keepdim=True)
    heat = torch.relu((weights * activations).sum(dim=1, keepdim=True))
    heat = torch.nn.functional.interpolate(heat, size=DEFAULT_SHAPE, mode="trilinear", align_corners=False)[0, 0]
    maximum = float(heat.max().item())
    if maximum > 0: heat = heat / maximum
    return {"sample_id": prediction["sample_id"], "target_class": CLASS_NAMES[cls],
            "method": "3d-cnn-grad-cam", "heatmap": heat.detach().cpu().numpy().tolist(),
            "scope": "synthetic_generated_phantom_only", "notice": NOTICE,
            "clinical_validation": False, "clinical_gate_authorized": False,
            "training_release_authorized": False}


def validate_research_severity_thresholds(thresholds=DEFAULT_RESEARCH_SEVERITY_THRESHOLDS) -> tuple[float, float, float, float]:
    """Validate four configurable *research-only* narrowing boundaries."""
    try:
        values = tuple(float(value) for value in thresholds)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("research_severity_thresholds_invalid") from None
    if (len(values) != 4 or not np.isfinite(values).all()
            or values[0] < 0 or values[-1] > 100
            or any(left >= right for left, right in zip(values, values[1:]))):
        raise ValueError("research_severity_thresholds_invalid")
    return values


def provisional_research_severity(narrowing: float, thresholds=DEFAULT_RESEARCH_SEVERITY_THRESHOLDS) -> str:
    thresholds = validate_research_severity_thresholds(thresholds)
    if not np.isfinite(narrowing) or not 0 <= narrowing <= 100:
        raise ValueError("synthetic_narrowing_out_of_range")
    t0, t1, t2, t3 = thresholds
    if narrowing < t0:
        return "normal"
    if narrowing < t1:
        return "mild"
    if narrowing < t2:
        return "moderate"
    if narrowing < t3:
        return "severe"
    return "critical_very_severe"


def _measurement_error_summary(errors: list[float]) -> dict[str, Any]:
    values = np.asarray(errors, dtype=float)
    if not values.size:
        return {"n": 0, "mae": None, "rmse": None, "bias": None,
                "absolute_error_p50": None, "absolute_error_p90": None,
                "absolute_error_max": None}
    absolute = np.abs(values)
    return {"n": int(values.size), "mae": float(np.mean(absolute)),
            "rmse": float(np.sqrt(np.mean(np.square(values)))),
            "bias": float(np.mean(values)),
            "absolute_error_p50": float(np.percentile(absolute, 50)),
            "absolute_error_p90": float(np.percentile(absolute, 90)),
            "absolute_error_max": float(np.max(absolute))}


def extract_synthetic_candidate_profile(
    sample: dict[str, Any], trigger_ratio: float = 0.75,
    severity_thresholds=DEFAULT_RESEARCH_SEVERITY_THRESHOLDS,
) -> dict[str, Any]:
    """Measure candidates on a generated phantom using its declared synthetic axis.

    This is a controlled, generator-axis-assisted experiment, not automatic
    centerline extraction. It validates the generated bytes but deliberately does
    not consult the hidden synthetic lesion ground-truth intervals.
    """
    volume = np.asarray(sample.get("volume"))
    provenance = sample.get("provenance") if isinstance(sample, dict) else None
    if (not isinstance(provenance, dict) or provenance.get("source") != GENERATOR_ID
            or provenance.get("generator_version") != GENERATOR_VERSION
            or volume.shape != DEFAULT_SHAPE or volume.dtype != np.float32
            or not np.isfinite(volume).all() or not np.isfinite(trigger_ratio)
            or not 0 < trigger_ratio < 1):
        raise ValueError("synthetic_geometry_input_invalid")
    thresholds = validate_research_severity_thresholds(severity_thresholds)
    if hashlib.sha256(volume.tobytes(order="C")).hexdigest() != provenance.get("volume_sha256"):
        raise ValueError("synthetic_geometry_source_hash_mismatch")
    axis = np.asarray(provenance.get("axis_ijk"), dtype=float)
    if axis.shape != (3,) or not np.isfinite(axis).all() or abs(np.linalg.norm(axis) - 1.0) > 1e-4:
        raise ValueError("synthetic_geometry_provenance_invalid")
    foreground = volume >= 0.5
    coords = np.argwhere(foreground)
    if len(coords) == 0:
        raise ValueError("synthetic_vessel_empty")
    center = coords.mean(axis=0)
    relative = coords - center
    axial = relative @ axis
    radial2 = np.maximum(0.0, np.sum(relative * relative, axis=1) - axial * axial)
    span = float(axial.max() - axial.min())
    if not np.isfinite(span) or span < 8:
        raise ValueError("synthetic_vessel_span_insufficient")
    positions = np.arange(np.floor(axial.min()) + 1.0, np.ceil(axial.max()) - 1.0, 1.0)
    # Count-based areas were unstable for oblique tubes: lattice-phase changes
    # produced false candidates on normal controls. A high radial-squared
    # quantile estimates the cross-section boundary more consistently.
    radial_boundary2 = np.asarray([
        np.quantile(radial2[np.abs(axial - position) <= 0.55], SYNTHETIC_RADIAL_SQUARED_QUANTILE)
        if np.any(np.abs(axial - position) <= 0.55) else 0.0
        for position in positions
    ], dtype=float)
    areas = np.pi * radial_boundary2
    valid = np.isfinite(areas) & (areas > 0)
    if not valid.any():
        raise ValueError("synthetic_reference_measurement_unavailable")
    reference_area = float(np.percentile(areas[valid], 75))
    if not np.isfinite(reference_area) or reference_area <= 0:
        raise ValueError("synthetic_reference_measurement_unavailable")
    diameters = 2.0 * np.sqrt(areas / np.pi)
    reference_diameter = 2.0 * np.sqrt(reference_area / np.pi)
    area_ratio = areas / reference_area
    triggers = valid & (area_ratio <= trigger_ratio)
    triggered_indices = np.flatnonzero(triggers)
    groups = np.split(triggered_indices, np.flatnonzero(np.diff(triggered_indices) != 1) + 1) if triggered_indices.size else []
    from scipy.signal import find_peaks

    candidates = []
    for group in groups:
        if len(group) < 2:
            continue
        signal = 1.0 - area_ratio[group]
        peak_offsets, _ = find_peaks(signal, distance=3, prominence=SYNTHETIC_PEAK_PROMINENCE)
        peaks = group[peak_offsets]
        peaks = peaks[area_ratio[peaks] <= trigger_ratio]
        if not len(peaks):
            peaks = np.asarray([group[np.argmin(area_ratio[group])]], dtype=int)
        boundaries = [int(p1 + np.argmax(area_ratio[p1:p2 + 1])) for p1, p2 in zip(peaks[:-1], peaks[1:])]
        for peak_index, local in enumerate(peaks):
            first = int(group[0]) if peak_index == 0 else boundaries[peak_index - 1]
            last = int(group[-1]) if peak_index == len(peaks) - 1 else boundaries[peak_index]
            candidate_center = center + axis * positions[local]
            interval_voxels = coords[(axial >= positions[first] - 1) & (axial <= positions[last] + 1)]
            if not len(interval_voxels):
                continue
            minimum_diameter = float(diameters[local])
            narrowing = 100.0 * (reference_diameter - minimum_diameter) / reference_diameter if reference_diameter > 0 else None
            if narrowing is None or not np.isfinite(narrowing) or narrowing < 0 or narrowing > 100:
                severity = None
                narrowing = None
            else:
                severity = provisional_research_severity(narrowing, thresholds)
            candidates.append({
                "candidate_id": f"synthetic-candidate-{len(candidates) + 1:03}",
                "status": "experimental_candidate",
                "location": {"coordinate_space": "synthetic_IJK_voxel_units", "center_ijk": candidate_center.tolist(),
                             "slice_k": float(candidate_center[2]), "candidate_extent_synthetic_units": [float(positions[first]), float(positions[last])],
                             "bounding_box_ijk": {"min": interval_voxels.min(axis=0).astype(int).tolist(), "max": interval_voxels.max(axis=0).astype(int).tolist()}},
                "measurements": {"minimum_radius_synthetic_units": minimum_diameter / 2.0,
                                 "reference_radius_synthetic_units": float(reference_diameter / 2.0),
                                 "minimum_diameter_synthetic_units": minimum_diameter,
                                 "reference_diameter_synthetic_units": float(reference_diameter),
                                 "estimated_percentage_narrowing_synthetic_only": float(narrowing) if narrowing is not None else None,
                                 "severity_synthetic_only": severity,
                                 "severity_thresholds_percent_synthetic_only": list(thresholds),
                                 "measurement_availability": "estimated_synthetic_only" if narrowing is not None else "unavailable",
                                 "measurement_confidence": None,
                                 "measurement_uncertainty": None,
                                 "method": "synthetic_radial-squared-quantile_0.90_peak_profile_area-equivalent_diameter",
                                 "quality": "synthetic_geometry_only_unvalidated"},
            })
    minimum_diameter_profile = float(diameters[valid].min())
    profile_narrowing = 100.0 * (reference_diameter - minimum_diameter_profile) / reference_diameter
    profile_severity = (provisional_research_severity(profile_narrowing, thresholds)
                        if 0 <= profile_narrowing <= 100 else None)
    metrics = {"section_count": int(len(positions)), "reference_area_synthetic_units2": reference_area,
               "minimum_area_synthetic_units2": float(areas[valid].min()),
               "reference_radius_synthetic_units": float(reference_diameter / 2.0),
               "minimum_radius_synthetic_units": float(minimum_diameter_profile / 2.0),
               "estimated_percentage_narrowing_synthetic_only": float(profile_narrowing) if 0 <= profile_narrowing <= 100 else None,
               "provisional_severity_synthetic_only": profile_severity,
               "measurement_availability": "estimated_synthetic_profile_only" if 0 <= profile_narrowing <= 100 else "unavailable",
               "measurement_confidence": None,
               "measurement_uncertainty": None,
               "area_profile_synthetic_units2": areas.astype(float).tolist(),
               "position_profile_synthetic_units": positions.astype(float).tolist(),
               "reference_selection": "75th_percentile_of_valid_synthetic_cross_sections",
               "trigger_ratio": float(trigger_ratio), "threshold_status": "provisional_synthetic_algorithm_parameter",
               "radial_squared_quantile": SYNTHETIC_RADIAL_SQUARED_QUANTILE,
               "peak_prominence": SYNTHETIC_PEAK_PROMINENCE,
               "axis_source": "generator-provided-synthetic-axis-not-automatically-extracted",
               "severity_thresholds_percent_synthetic_only": list(thresholds),
               "severity_threshold_policy": "configurable_research_categories_only_not_clinically_validated"}
    return {"metrics": metrics, "candidates": candidates, "candidate_count": len(candidates),
            "candidate_status": "candidate_preview" if candidates else "no_candidates_in_evaluable_sections"}


def analyze_synthetic_phantom(sample: dict[str, Any], model, checkpoint_sha256: str,
                              severity_thresholds=DEFAULT_RESEARCH_SEVERITY_THRESHOLDS) -> dict[str, Any]:
    """Run synthetic-only geometry and model summaries on an internally generated phantom.

    Geometric values use synthetic voxel-equivalent units. The returned severity
    category is a provisional software label; it is not a clinical classification.
    """
    prediction = predict_synthetic(model, sample)
    thresholds = validate_research_severity_thresholds(severity_thresholds)
    geometry = extract_synthetic_candidate_profile(sample, severity_thresholds=thresholds)
    cam = gradcam3d(model, sample, target_class=int(np.argmax(prediction["probabilities"])))
    heatmap = np.asarray(cam["heatmap"], dtype=np.float32)
    if heatmap.shape != DEFAULT_SHAPE or not np.isfinite(heatmap).all() or (heatmap.size and (heatmap.min() < 0 or heatmap.max() > 1.00001)):
        raise ValueError("synthetic_gradcam_invalid")
    return {
        "schema_version": "experimental-stenosis-analysis/0.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed_synthetic_research_only",
        "notice": NOTICE,
        "provenance": {"synthetic_sample_id": sample["sample_id"], "generator_id": GENERATOR_ID,
                       "generator_version": GENERATOR_VERSION,
                       "volume_sha256": sample["provenance"]["volume_sha256"], "dataset_case_id": None, "patient_case_id": None},
        "geometry_analysis": {
            "method": "synthetic_centerline_axis_cross_section_profile/0.3",
            "measurement_provenance": {
                "scope": "synthetic_generated_phantom_only",
                "generator_id": GENERATOR_ID,
                "generator_version": GENERATOR_VERSION,
                "input_volume_sha256": sample["provenance"]["volume_sha256"],
                "method": "radial-squared-quantile_0.90_area-equivalent-radius_and_peak_profile",
                "axis_source": "generator-provided-synthetic-axis-not-automatically-extracted",
                "trigger_ratio": SYNTHETIC_TRIGGER_RATIO,
                "radial_squared_quantile": SYNTHETIC_RADIAL_SQUARED_QUANTILE,
                "peak_prominence": SYNTHETIC_PEAK_PROMINENCE,
                "provisional_severity_thresholds_percent": list(thresholds),
                "severity_threshold_policy": "configurable_research_categories_only_not_clinically_validated",
                "uncertainty_or_confidence": None,
                "clinical_gate_authorized": False,
                "training_release_authorized": False,
            },
            **geometry,
        },
        "model": {"model_id": MODEL_ID, "model_version": MODEL_VERSION, "checkpoint_sha256": checkpoint_sha256,
                  "predicted_synthetic_class": prediction["class"], "class_probabilities_uncalibrated": prediction["probabilities"],
                  "score_semantics": "uncalibrated_softmax_probability_not_clinical_confidence",
                  "clinical_performance_claim": False},
        "explainability": {"method": cam["method"], "target_class": cam["target_class"],
                           "shape": list(DEFAULT_SHAPE), "heatmap_values": heatmap.reshape(-1).tolist(),
                           "scope": cam["scope"]},
        "clinical_validation": False, "clinical_gate_authorized": False,
        "training_release_authorized": False,
    }
