"""Single-device execution, optional CUDA FP16 and portable path validation."""
from contextlib import nullcontext
import os
from pathlib import PurePosixPath, PureWindowsPath

import torch


def select_device(name):
    if name not in ("auto", "cpu", "cuda"):
        raise ValueError("Device must be auto, cpu or cuda.")
    available = torch.cuda.is_available()
    if name == "cuda" and not available:
        raise ValueError("CUDA was explicitly requested but is unavailable in this runtime.")
    return torch.device("cuda:0" if name == "cuda" or (name == "auto" and available) else "cpu")


def amp_enabled(device, requested):
    if type(requested) is not bool:
        raise ValueError("mixed_precision must be boolean.")
    if requested and device.type != "cuda":
        raise ValueError("FP16 mixed precision requires a selected CUDA device; disable it for CPU.")
    return requested


def autocast_context(device, enabled):
    return torch.amp.autocast("cuda", dtype=torch.float16) if enabled else nullcontext()


def make_scaler(device, enabled):
    return torch.amp.GradScaler(device.type, enabled=enabled)


def gpu_status(device, enabled=True):
    available = torch.cuda.is_available()
    report = {"selected_device": str(device), "cuda_available": available,
              "device_name": None, "total_memory_bytes": None, "allocated_bytes": None,
              "reserved_bytes": None, "peak_allocated_bytes": None}
    if enabled and available and device.type == "cuda":
        properties = torch.cuda.get_device_properties(device)
        report.update(device_name=properties.name, total_memory_bytes=properties.total_memory,
                      allocated_bytes=torch.cuda.memory_allocated(device),
                      reserved_bytes=torch.cuda.memory_reserved(device),
                      peak_allocated_bytes=torch.cuda.max_memory_allocated(device))
    return report


def reset_peak_memory(device, enabled=True):
    if enabled and device.type == "cuda" and torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats(device)


def portable_absolute(value):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("Use an explicit absolute path.")
    if PureWindowsPath(value).is_absolute():
        path = PureWindowsPath(value)
    elif PurePosixPath(value).is_absolute():
        path = PurePosixPath(value)
    else:
        raise ValueError("Use an explicit absolute Windows or POSIX path.")
    if ".." in path.parts:
        raise ValueError("Configuration paths must not contain traversal.")
    return path


def native_paths(cfg):
    from .identity import identity_paths
    values = [cfg[k] for k in ("dataset_root", "manifest", "output_root")]
    values.extend(identity_paths(cfg.get("dataset_identity", {})))
    if cfg.get("cache_directory"):
        values.append(cfg["cache_directory"])
    if cfg["initialization_checkpoint"]:
        values.append(cfg["initialization_checkpoint"]["path"])
    return all(isinstance(portable_absolute(v), PureWindowsPath) == (os.name == "nt") for v in values)
