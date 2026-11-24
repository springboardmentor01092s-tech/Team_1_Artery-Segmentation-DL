"""Short actual-data SegResNet benchmark. Not a completed training experiment."""
import argparse
import json
import platform
from pathlib import Path
import time

import numpy as np
import torch
import monai
from monai.losses import DiceCELoss
from monai.networks.nets import SegResNet
from data import CacheStore, patch_batch

MODEL = dict(spatial_dims=3, init_filters=16, in_channels=1, out_channels=2,
             blocks_down=(1, 2, 2, 4), blocks_up=(1, 1, 1), upsample_mode="deconv")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/kaggle/working"))
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--steps", type=int, default=20)
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("GPU unavailable; refusing a misleading CPU training benchmark")
    args.output.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(20261117)
    store = CacheStore(args.cache)
    model = SegResNet(**MODEL).cuda()
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-4, weight_decay=1e-5)
    loss_fn = DiceCELoss(to_onehot_y=True, softmax=True, include_background=False)
    scaler = torch.amp.GradScaler("cuda")
    torch.cuda.reset_peak_memory_stats()
    started = None
    timed_updates = 0
    for step in range(args.warmup + args.steps):
        if step == args.warmup:
            torch.cuda.synchronize()
            started = time.perf_counter()
        image, target = patch_batch(store, step)
        image, target = torch.from_numpy(image).cuda(), torch.from_numpy(target).cuda()
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.float16):
            loss = loss_fn(model(image), target)
        if not torch.isfinite(loss):
            raise RuntimeError("Nonfinite benchmark loss")
        scaler.scale(loss).backward()
        previous_scale = scaler.get_scale()
        scaler.step(optimizer)
        scaler.update()
        if step >= args.warmup and scaler.get_scale() >= previous_scale:
            timed_updates += 1
    torch.cuda.synchronize()
    seconds = time.perf_counter() - started
    result = {"mode": "benchmark_only", "gpu": torch.cuda.get_device_name(0),
              "gpu_count_available": torch.cuda.device_count(), "gpu_count_used": 1,
              "python": platform.python_version(), "torch": torch.__version__,
              "monai": monai.__version__, "numpy": np.__version__, "cuda": torch.version.cuda,
              "model": "MONAI SegResNet", "model_config": MODEL,
              "parameters": sum(p.numel() for p in model.parameters()),
              "batch_size": 2, "patch": [96, 96, 96], "precision": "CUDA AMP float16",
              "warmup_steps": args.warmup, "measured_steps": args.steps,
              "seconds": seconds, "steps_per_second": args.steps / seconds,
              "optimizer_updates": timed_updates, "optimizer_updates_per_second": timed_updates / seconds,
              "skipped_updates": args.steps - timed_updates,
              "peak_gpu_allocated_bytes": torch.cuda.max_memory_allocated(),
              "peak_gpu_reserved_bytes": torch.cuda.max_memory_reserved(),
              "source_training_cases": store.manifest["training_ids"],
              "scope": "Actual cached Training patches; includes patch preparation, transfer, forward/backward and optimizer. Warm filesystem cache; excludes validation and full-cohort IO. Benchmark weights discarded."}
    path = args.output / "benchmark.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
