"""Historical patch modes, with explicitly grouped, shuffled case traversal."""
from __future__ import annotations

import copy
import numpy as np

from .dataset import DataError


def random_origin(shape, patch_size, rng):
    return tuple(int(rng.integers(0, dim - size + 1)) for dim, size in zip(shape, patch_size))


def sample_origin(mask, counts, patch_size, rng, *, mode=None):
    if mask.ndim != 3 or any(n > d for n, d in zip(patch_size, mask.shape)):
        raise DataError("Invalid patch shape.")
    if mode is None:
        draw = rng.random()
        mode = "foreground" if draw < .5 else "attempted_empty" if draw < .75 else "random"
    actual = mode
    if mode == "foreground":
        total = int(counts.sum())
        if total == 0:
            raise DataError("Foreground sampling requires a nonempty mask.")
        rank = int(rng.integers(total))
        cumulative = np.cumsum(counts)
        axis0 = int(np.searchsorted(cumulative, rank, side="right"))
        local_rank = rank - (int(cumulative[axis0 - 1]) if axis0 else 0)
        # Exactly the C-order rank used by np.argwhere, without full 3D coordinates.
        plane_indices = np.flatnonzero(mask[axis0].ravel(order="C"))
        axis1, axis2 = np.unravel_index(int(plane_indices[local_rank]), mask.shape[1:])
        point = (axis0, int(axis1), int(axis2))
        origin = tuple(max(0, min(point[i] - patch_size[i] // 2, mask.shape[i] - patch_size[i])) for i in range(3))
    elif mode == "attempted_empty":
        origin = None
        for _ in range(30):
            candidate = random_origin(mask.shape, patch_size, rng)
            region = tuple(slice(s, s + n) for s, n in zip(candidate, patch_size))
            if not np.any(mask[region] > 0):
                origin = candidate
                break
        if origin is None:
            origin = random_origin(mask.shape, patch_size, rng)
            actual = "random_fallback"
    elif mode == "random":
        origin = random_origin(mask.shape, patch_size, rng)
    else:
        raise DataError("Unknown sampling mode.")
    return origin, {"requested_mode": mode, "actual_mode": actual}


class PatchSampler:
    def __init__(self, training_ids, seed=456, patches_per_case=8):
        self.ids = sorted(training_ids)
        if not self.ids or len(set(self.ids)) != len(self.ids) or patches_per_case < 1:
            raise DataError("Invalid sampler case index.")
        self.patches_per_case = patches_per_case
        self.rng = np.random.default_rng(seed)
        self.order = [int(i) for i in self.rng.permutation(self.ids)]
        self.case_cursor = self.patch_cursor = self.epoch = self.draws = 0

    def draw(self, cache):
        cid = self.order[self.case_cursor]
        cache.load(cache.index.case(cid, "Training"))
        origin, modes = sample_origin(cache.mask, cache.foreground_counts, cache.patch_size, self.rng)
        x, y = cache.patch(origin)
        info = {"case_id": cid, "origin": list(origin), "epoch": self.epoch,
                "target_positive_voxels": int(np.count_nonzero(y)), **modes}
        self.draws += 1
        self.patch_cursor += 1
        if self.patch_cursor == self.patches_per_case:
            self.patch_cursor = 0
            self.case_cursor += 1
            if self.case_cursor == len(self.ids):
                self.epoch += 1
                self.case_cursor = 0
                self.order = [int(i) for i in self.rng.permutation(self.ids)]
        return x, y, info

    def state_dict(self):
        return copy.deepcopy({"ids": self.ids, "patches_per_case": self.patches_per_case,
                              "order": self.order, "case_cursor": self.case_cursor,
                              "patch_cursor": self.patch_cursor, "epoch": self.epoch,
                              "draws": self.draws, "rng": self.rng.bit_generator.state})

    def load_state_dict(self, state):
        if (state["ids"] != self.ids or state["patches_per_case"] != self.patches_per_case
                or sorted(state["order"]) != self.ids or not 0 <= state["case_cursor"] < len(self.ids)
                or not 0 <= state["patch_cursor"] < self.patches_per_case
                or state["epoch"] < 0 or state["draws"] < 0):
            raise DataError("Sampler resume state is incompatible.")
        expected = (state["epoch"] * len(self.ids) + state["case_cursor"]) * self.patches_per_case + state["patch_cursor"]
        if expected != state["draws"]:
            raise DataError("Sampler counters are inconsistent.")
        self.rng.bit_generator.state = copy.deepcopy(state["rng"])
        for name in ("order", "case_cursor", "patch_cursor", "epoch", "draws"):
            setattr(self, name, copy.deepcopy(state[name]))
