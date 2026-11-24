"""Additional read-only segmentation statistics from already stored counts.

Does not change imported documents, metric definitions/version, payload hashes,
thresholds, predictions, cases or database records. Counts cannot recover any
surface geometry, physical distance, stenosis label or ROC curve.
"""
import math

NAMES = ("voxel_accuracy", "specificity", "sensitivity", "f1_score")
FORMULAS = {"voxel_accuracy": "(TP+TN)/(TP+TN+FP+FN)", "specificity": "TN/(TN+FP)",
            "sensitivity": "TP/(TP+FN); equivalent to recall", "f1_score": "2TP/(2TP+FP+FN); equivalent to binary Dice"}


def from_counts(counts):
    if counts is None:
        return dict.fromkeys(NAMES), dict.fromkeys(NAMES, "confusion_counts_unavailable")
    if (not isinstance(counts, dict) or any(type(counts.get(key)) is not int or counts[key] < 0 for key in ("tp", "fp", "fn"))
            or counts.get("tn") is not None and (type(counts["tn"]) is not int or counts["tn"] < 0)):
        raise ValueError("Expected verified nonnegative integer confusion counts")
    tp, fp, fn, tn = (counts.get(key) for key in ("tp", "fp", "fn", "tn"))
    metrics, reasons = {}, {}
    ratios = {"voxel_accuracy": None if tn is None else (tp + tn, tp + tn + fp + fn),
              "specificity": None if tn is None else (tn, tn + fp),
              "sensitivity": (tp, tp + fn), "f1_score": (2 * tp, 2 * tp + fp + fn)}
    for name, pair in ratios.items():
        if pair is None:
            metrics[name] = None
            reasons[name] = "true_negative_count_unavailable"
        elif pair[1] == 0:
            metrics[name] = None
            reasons[name] = "zero_denominator"
        else:
            metrics[name] = pair[0] / pair[1]
    return metrics, reasons


def supplemental_metrics(cases):
    rows = []
    counts = []
    for case in cases:
        metrics, reasons = from_counts(case.confusion_counts.model_dump() if case.confusion_counts is not None else None)
        included = case.exclusion_reason is None
        rows.append(dict(case_id=case.case_id, included=included, exclusion_reason=case.exclusion_reason,
                         metrics=metrics, unavailable_reasons=reasons))
        if included:
            counts.append(case.confusion_counts)
    included_rows = [row for row in rows if row["included"]]
    macro, denominators = {}, {}
    for name in NAMES:
        values = [row["metrics"][name] for row in included_rows if row["metrics"][name] is not None]
        macro[name] = math.fsum(values) / len(values) if values else None
        denominators[name] = dict(defined_cases=len(values), undefined_cases=len(included_rows) - len(values))
    if counts and all(value is not None for value in counts):
        # Never pool only the favorable subset. TN-dependent pooled metrics need
        # every included case's TN; TP/FP/FN-dependent metrics do not.
        pooled = {key: sum(getattr(value, key) for value in counts) for key in ("tp", "fp", "fn")}
        pooled["tn"] = sum(value.tn for value in counts) if all(value.tn is not None for value in counts) else None
        micro, reasons = from_counts(pooled)
    else:
        micro = dict.fromkeys(NAMES)
        reasons = dict.fromkeys(NAMES, "no_included_cases" if not counts else "incomplete_included_confusion_counts")
    return dict(version="confusion-derived/1.0", source="stored_case_confusion_counts",
                macro_metrics=macro, macro_denominators=denominators, pooled_micro_metrics=micro,
                pooled_unavailable_reasons=reasons, per_case=rows, formulas=FORMULAS.copy(), zero_denominator="null",
                surface_distances=dict(status="unavailable_not_computed", hausdorff_distance=None,
                                       average_surface_distance=None, units=None,
                                       reason="Surface distances cannot be recovered from confusion counts. Saved surface geometry and an explicitly verified spatial-unit/alignment protocol are required; no distance is inferred."))
