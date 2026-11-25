import copy
import numpy as np
import pytest

from training.dataset import DataError, SingleCaseCache
from training.sampling import PatchSampler, random_origin, sample_origin
from training.tests.test_dataset import make_cohort, index_for


def test_foreground_rank_matches_historical_argwhere():
    mask = np.zeros((9, 10, 11), dtype=np.uint8)
    mask[1:8:2, 2:9:3, 3:10:2] = 1
    counts = np.array([np.count_nonzero(plane) for plane in mask])
    for seed in range(20):
        a, b = np.random.default_rng(seed), np.random.default_rng(seed)
        point = np.argwhere(mask > 0)[int(b.integers(counts.sum()))]
        expected = tuple(max(0, min(int(point[i])-2, mask.shape[i]-4)) for i in range(3))
        assert sample_origin(mask, counts, (4, 4, 4), a, mode="foreground")[0] == expected


def test_attempted_empty_uses_30_tries_then_random_fallback():
    class RNG:
        calls = 0
        def integers(self, low, high=None):
            self.calls += 1
            return 0
    rng = RNG(); mask = np.ones((8, 8, 8), dtype=np.uint8)
    origin, info = sample_origin(mask, np.full(8, 64), (4, 4, 4), rng, mode="attempted_empty")
    assert origin == (0, 0, 0) and info["actual_mode"] == "random_fallback"
    assert rng.calls == 31 * 3


@pytest.mark.parametrize("draw,expected", [(.1, "foreground"), (.6, "attempted_empty"), (.9, "random")])
def test_mode_probabilities_and_bounds(draw, expected):
    class RNG:
        def random(self): return draw
        def integers(self, low, high=None): return 0
    mask = np.zeros((8, 8, 8), dtype=np.uint8); mask[7, 7, 7] = 1
    origin, info = sample_origin(mask, np.array([0]*7+[1]), (4, 4, 4), RNG())
    assert info["requested_mode"] == expected
    assert all(0 <= i <= 4 for i in origin)
    if expected == "foreground": assert origin == (4, 4, 4)
    assert random_origin((4, 4, 4), (4, 4, 4), np.random.default_rng(5)) == (0, 0, 0)


def test_sampler_roundtrip_and_grouping(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    index = index_for(root, manifest); cache = SingleCaseCache(index, (4, 4, 4))
    sampler = PatchSampler(index.ids("Training"), seed=456, patches_per_case=2)
    first = [sampler.draw(cache)[2] for _ in range(3)]
    assert first[0]["case_id"] == first[1]["case_id"] != first[2]["case_id"]
    saved = sampler.state_dict()
    expected = [sampler.draw(cache) for _ in range(7)]
    restored = PatchSampler(index.ids("Training"), seed=999, patches_per_case=2)
    restored.load_state_dict(saved)
    for x, y, info in expected:
        rx, ry, ri = restored.draw(cache)
        assert ri == info and np.array_equal(rx, x) and np.array_equal(ry, y)
    bad = copy.deepcopy(saved); bad["draws"] += 1
    with pytest.raises(DataError): restored.load_state_dict(bad)


def test_sampler_cannot_load_validation_case(tmp_path):
    root, manifest, _ = make_cohort(tmp_path)
    cache = SingleCaseCache(index_for(root, manifest), (4, 4, 4))
    sampler = PatchSampler([851])
    with pytest.raises(DataError): sampler.draw(cache)
