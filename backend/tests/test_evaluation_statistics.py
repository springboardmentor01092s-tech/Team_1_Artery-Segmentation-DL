"""Tiny count records only; never generate/replay phantoms or medical images."""
from types import SimpleNamespace
from copy import deepcopy

import pytest
from app.schemas.evaluation import ConfusionCounts, SupplementalEvaluationMetrics
from app.services.evaluation_statistics import from_counts, supplemental_metrics


def case(identifier, counts, excluded=None):
    return SimpleNamespace(case_id=identifier, confusion_counts=ConfusionCounts(**counts) if counts is not None else None,
                           exclusion_reason=excluded)


def test_actual_formulas_and_legitimate_zero_values():
    metrics, reasons = from_counts(dict(tp=3, fp=2, fn=1, tn=14))
    assert metrics == dict(voxel_accuracy=17/20, specificity=14/16, sensitivity=3/4, f1_score=6/9)
    assert reasons == {}
    zero, reasons = from_counts(dict(tp=0, fp=2, fn=3, tn=0))
    assert zero == dict.fromkeys(metrics, 0)
    assert reasons == {}


def test_tn_is_not_invented_and_zero_denominators_are_null():
    metrics, reasons = from_counts(dict(tp=1, fp=1, fn=0))
    assert metrics == dict(voxel_accuracy=None, specificity=None, sensitivity=1, f1_score=2/3)
    assert reasons == dict(voxel_accuracy="true_negative_count_unavailable", specificity="true_negative_count_unavailable")
    empty, reasons = from_counts(dict(tp=0, fp=0, fn=0, tn=0))
    assert all(value is None for value in empty.values())
    assert set(reasons.values()) == {"zero_denominator"}


def test_macro_is_case_unweighted_micro_separate_and_inputs_unchanged():
    rows = [case(1, dict(tp=1, fp=1, fn=0, tn=2)), case(2, dict(tp=9, fp=0, fn=1, tn=90))]
    before = deepcopy([row.confusion_counts.model_dump() for row in rows])
    result = supplemental_metrics(rows)
    assert result["macro_metrics"]["voxel_accuracy"] == pytest.approx((3/4 + 99/100)/2)
    assert result["pooled_micro_metrics"]["voxel_accuracy"] == pytest.approx(102/104)
    assert result["macro_metrics"]["voxel_accuracy"] != result["pooled_micro_metrics"]["voxel_accuracy"]
    assert result["macro_denominators"]["specificity"] == dict(defined_cases=2, undefined_cases=0)
    assert before == [row.confusion_counts.model_dump() for row in rows]
    assert SupplementalEvaluationMetrics.model_validate(result).version == "confusion-derived/1.0"


def test_exclusions_stay_visible_and_do_not_improve_or_degrade_aggregates():
    result = supplemental_metrics([case(1, dict(tp=1, fp=1, fn=1, tn=1)),
                                   case(2, dict(tp=1000, fp=0, fn=0, tn=1000), "Excluded fixture")])
    assert all(value == .5 for value in result["macro_metrics"].values())
    assert len(result["per_case"]) == 2 and result["per_case"][1]["included"] is False
    assert result["per_case"][1]["exclusion_reason"] == "Excluded fixture"
    assert all(value["defined_cases"] == 1 for value in result["macro_denominators"].values())


def test_per_metric_coverage_and_partial_tn_availability():
    result = supplemental_metrics([case(1, dict(tp=1, fp=0, fn=1, tn=2)), case(2, dict(tp=9, fp=1, fn=0))])
    assert result["macro_denominators"]["specificity"] == dict(defined_cases=1, undefined_cases=1)
    assert result["macro_denominators"]["sensitivity"] == dict(defined_cases=2, undefined_cases=0)
    assert result["pooled_micro_metrics"]["specificity"] is None
    assert result["pooled_micro_metrics"]["sensitivity"] == 10/11
    assert result["pooled_unavailable_reasons"]["voxel_accuracy"] == "true_negative_count_unavailable"


def test_missing_counts_stay_in_macro_coverage_and_prevent_partial_pooling():
    result = supplemental_metrics([case(1, dict(tp=1, fp=1, fn=0, tn=1)), case(2, None)])
    assert result["macro_denominators"]["voxel_accuracy"] == dict(defined_cases=1, undefined_cases=1)
    assert all(value is None for value in result["pooled_micro_metrics"].values())
    assert set(result["pooled_unavailable_reasons"].values()) == {"incomplete_included_confusion_counts"}
    assert all(value is None for value in supplemental_metrics([])["macro_metrics"].values())


def test_surface_distances_are_explicitly_unavailable_not_derived_from_counts():
    result = supplemental_metrics([case(1, dict(tp=99, fp=0, fn=0, tn=99))])
    distances = result["surface_distances"]
    assert distances["status"] == "unavailable_not_computed"
    assert distances["hausdorff_distance"] is distances["average_surface_distance"] is distances["units"] is None
    assert "cannot be recovered" in distances["reason"]


@pytest.mark.parametrize("counts", [dict(tp=-1, fp=0, fn=0), dict(tp=True, fp=0, fn=0),
                                     dict(tp=1.5, fp=0, fn=0), dict(tp=0, fp=0, fn=0, tn=-1), {}])
def test_unvalidated_counts_fail_closed(counts):
    with pytest.raises(ValueError):
        from_counts(counts)
