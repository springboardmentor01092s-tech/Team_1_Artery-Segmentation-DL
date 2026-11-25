"""Explicit, optional SegResNet runtime matching the frozen 1 mm recipe.

This is research artery segmentation, never a stenosis provider. Importing the
normal API does not import this module, Torch or MONAI. No checkpoint discovery,
automatic architecture detection, training, morphology or gate registration.
"""
from pathlib import Path
import json
import pickle
import re
import time
from uuid import UUID

import monai
from monai.inferers import sliding_window_inference
from monai.networks.nets import SegResNet
import numpy as np
from scipy.ndimage import affine_transform
import torch

from app.services.source_fingerprint import file_version, source_sha256
from .inference import InferenceError, LIMITATION, load_volume, save_like, select_device, sha256_file

MODEL = dict(spatial_dims=3, init_filters=16, in_channels=1, out_channels=2,
             blocks_down=[1, 2, 2, 4], blocks_up=[1, 1, 1], upsample_mode="deconv")
MAX_CACHE_VOXELS = 32_000_000


def load_model(path, device, expected_sha256):
    path = Path(path)
    if not expected_sha256 or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise InferenceError("SegResNet requires an explicit trusted checkpoint SHA-256.", 503)
    if monai.__version__ != "1.6.1":
        raise InferenceError("SegResNet recipe requires MONAI 1.6.1.", 503)
    try:
        before = file_version(path)
        if path.is_symlink() or sha256_file(path) != expected_sha256:
            raise ValueError("Checkpoint identity differs")
        # The actual training artifact records torch.__version__ as this string
        # subclass. No unrestricted pickle fallback or user-supplied allowlist.
        with torch.serialization.safe_globals([torch.torch_version.TorchVersion]):
            checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        if file_version(path) != before or sha256_file(path) != expected_sha256:
            raise ValueError("Checkpoint changed while loading")
        provenance = checkpoint["provenance"]
        config = provenance["model_config"]
        normalized_config = {key: list(value) if isinstance(value, (list, tuple)) else value
                             for key, value in config.items()}
        if (provenance["schema_version"] != "segresnet-training/1.0"
                or provenance["model"] != "MONAI SegResNet"
                or normalized_config != MODEL
                or provenance["threshold"] != .5
                or provenance["patch"] != [96, 96, 96]
                or provenance["monai"] != "1.6.1"):
            raise ValueError("Unrecognized training recipe")
        UUID(provenance["training_run_id"])
        steps = checkpoint["optimizer_steps"]
        if type(steps) is not int or steps <= 0:
            raise ValueError("No verified optimizer step count")
        model = SegResNet(**MODEL)
        model.load_state_dict(checkpoint["model"], strict=True)
        if sum(p.numel() for p in model.parameters()) != 4_744_034:
            raise ValueError("Parameter count differs")
        if any(not torch.isfinite(t).all() for t in model.state_dict().values()):
            raise ValueError("Nonfinite weights")
        return model.to(device).eval(), {"training_run_id": provenance["training_run_id"],
                                         "optimizer_steps": steps}
    except (OSError, KeyError, TypeError, ValueError, RuntimeError, EOFError, AttributeError, pickle.UnpicklingError) as exc:
        raise InferenceError("SegResNet checkpoint identity, weights or frozen recipe could not be verified.", 503) from exc


def prepare_input(source, raw):
    affine = np.asarray(source.affine, dtype=np.float64)
    if source.header.get_xyzt_units()[0] != "mm" or int(source.header["sform_code"]) <= 0:
        raise InferenceError("SegResNet requires coded CT millimetre geometry; unknown units are not inferred.")
    spacing = np.linalg.norm(affine[:3, :3], axis=0)
    if (not np.isfinite(affine).all() or np.any(spacing <= 0)
            or not np.allclose(affine[3], [0, 0, 0, 1], atol=1e-8, rtol=0)):
        raise InferenceError("Invalid physical affine.")
    directions = affine[:3, :3] / spacing
    if not np.allclose(directions.T @ directions, np.eye(3), atol=1e-6, rtol=0):
        raise InferenceError("Sheared CT geometry is unsupported by the frozen SegResNet recipe.")
    dimensions = np.ceil((np.asarray(raw.shape) - 1) * spacing) + 1
    if not np.isfinite(dimensions).all() or np.any(dimensions < 1) or np.prod(dimensions) > MAX_CACHE_VOXELS:
        raise InferenceError("1 mm input exceeds the frozen 32-million-voxel cache bound.")
    grid = affine.copy()
    grid[:3, :3] = directions
    shape = tuple(int(n) for n in dimensions)
    transform = np.linalg.inv(affine) @ grid
    image = affine_transform(raw, transform[:3, :3], offset=transform[:3, 3],
                             output_shape=shape, output=np.float32, order=1,
                             mode="constant", cval=-200, prefilter=False)
    np.clip(image, -200, 800, out=image)
    image += 200
    image /= 1000
    # Reproduce the cache's float16 storage quantization before model float32.
    return image.astype(np.float16).astype(np.float32), grid


def predict(model, image, device, batch_size, progress=None):
    completed = 0
    tensor = torch.from_numpy(image)[None, None]

    def predictor(patches):
        nonlocal completed
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16, enabled=device.type == "cuda"):
            logits = model(patches)
            if logits.shape != (len(patches), 2, *patches.shape[2:]) or not torch.isfinite(logits).all():
                raise InferenceError("SegResNet produced invalid logits.", 500)
            probability = torch.softmax(logits, dim=1)[:, 1:2].float()
        completed += len(patches)
        if progress:
            progress(completed, None)  # Total not estimated as a fabricated percentage.
        return probability

    with torch.inference_mode():
        probability = sliding_window_inference(tensor, (96, 96, 96), batch_size, predictor,
                                               overlap=.25, mode="gaussian", sw_device=device,
                                               device="cpu")[0, 0].numpy()
    if probability.shape != image.shape or not np.isfinite(probability).all() or np.any((probability < 0) | (probability > 1)):
        raise InferenceError("SegResNet produced invalid probabilities.", 500)
    return probability


def restore_native(probability, grid, native_affine, native_shape):
    transform = np.linalg.inv(grid) @ native_affine
    result = np.empty(native_shape, dtype=np.float32)
    for start in range(0, native_shape[2], 16):
        stop = min(start + 16, native_shape[2])
        offset = transform[:3, 3] + transform[:3, 2] * start
        result[:, :, start:stop] = affine_transform(
            probability, transform[:3, :3], offset=offset,
            output_shape=(*native_shape[:2], stop - start), output=np.float32,
            order=1, mode="constant", cval=0, prefilter=False)
    return result


def run_inference(ct_path, checkpoint_path, output_dir, threshold=.5, batch_size=1,
                  device="cpu", max_voxels=67_108_864, max_bytes=2_000 * 1024 * 1024,
                  progress=None, *, expected_checkpoint_sha256=None):
    if type(threshold) not in (float, int) or threshold != .5:
        raise InferenceError("The frozen SegResNet recipe requires threshold 0.5; no retuning is enabled.")
    if type(batch_size) is not int or not 1 <= batch_size <= 16:
        raise InferenceError("Batch size must be between 1 and 16.")
    started = time.monotonic()
    selected = select_device(device)
    model, identity = load_model(checkpoint_path, selected, expected_checkpoint_sha256)
    path = Path(ct_path)
    before = file_version(path)
    checksum = source_sha256(path)
    source, raw = load_volume(path, max_voxels, max_bytes)
    image, grid = prepare_input(source, raw)
    del raw
    cached_probability = predict(model, image, selected, batch_size, progress)
    del model, image
    probability = restore_native(cached_probability, grid, source.affine, source.shape)
    del cached_probability
    if file_version(path) != before or source_sha256(path) != checksum:
        raise InferenceError("Input volume changed during inference.", 409)
    mask = (probability >= .5).astype(np.uint8)
    metadata = {"architecture": "MONAI SegResNet", "recipe": "segresnet-1mm-v1",
                "parameter_count": 4_744_034, "checkpoint_sha256": expected_checkpoint_sha256,
                **identity, "checkpoint_step": identity["optimizer_steps"],
                "source_sha256": checksum, "shape": list(source.shape),
                "affine": source.affine.tolist(), "xyzt_units": int(source.header["xyzt_units"]),
                "cache_affine": grid.tolist(), "spacing_mm": 1, "patch_size": [96, 96, 96],
                "overlap": .25, "blending": "gaussian", "threshold": .5,
                "preprocessing": "1 mm original axes/origin; linear HU with -200 exterior; clip [-200,800]; normalize; float16 cache quantization",
                "native_mapping": "linear foreground probability; 16-slice slabs; threshold after mapping",
                "postprocessing": "none", "foreground_voxels": int(mask.sum()),
                "probability_min": float(probability.min()), "probability_max": float(probability.max()),
                "device": str(selected), "compute_precision": "cuda_amp_float16" if selected.type == "cuda" else "cpu_float32",
                "numerical_note": "CPU and GPU arithmetic may differ; no bitwise equivalence claim.",
                "experimental": True, "clinical_validation": False, "limitations": LIMITATION}
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    try:
        save_like(source, probability, output / "probabilities.nii.gz", np.float32)
        save_like(source, mask, output / "prediction_mask.nii.gz", np.uint8)
        metadata["duration_seconds"] = round(time.monotonic() - started, 3)
        (output / "metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except Exception:
        for name in ("probabilities.nii.gz", "prediction_mask.nii.gz", "metadata.json"):
            (output / name).unlink(missing_ok=True)
        output.rmdir()
        raise
    return metadata
