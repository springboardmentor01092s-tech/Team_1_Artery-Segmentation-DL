"""Synthetic-only tests; never open project datasets, app fixtures or databases."""
from dataclasses import replace
import csv
import gzip
import json
import struct
import xml.etree.ElementTree as ET
import zipfile

import nibabel as nib
import numpy as np
import pytest

from tools.imagecas_readiness import validator as v


PAIR_FIELDS = ["publisher_case_id", "split", "ct_path", "reference_path",
               "ct_sha256", "reference_sha256", "ct_bytes", "reference_bytes",
               "dataset_version", "pairing_evidence", "readiness_status", "blockers"]


def csv_file(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def split_file(path, assignments):
    return csv_file(path, ["FileName", "Split-4"],
                    [{"FileName": i, "Split-4": s} for i, s in assignments])


def volume(path, values=None, affine=None, units="mm", version=1):
    if values is None:
        values = np.ones((3, 4, 5), dtype=np.uint8)
    image_type = nib.Nifti1Image if version == 1 else nib.Nifti2Image
    image = image_type(values, np.eye(4) if affine is None else affine)
    image.header.set_xyzt_units(units)
    image.set_qform(None, 0)
    image.set_sform(image.affine, 2)
    nib.save(image, path)
    return path


def mutate_header(path, offset, fmt, value):
    data = bytearray(gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes())
    struct.pack_into(fmt, data, offset, value)
    path.write_bytes(gzip.compress(data) if path.suffix == ".gz" else data)


def make_xlsx(path, assignments, sheet="v2-latest", formula=False):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    sheet_xml = ET.Element("worksheet", xmlns=ns)
    data = ET.SubElement(sheet_xml, "sheetData")
    rows = [["FileName", "Split-4"]] + [[str(i), label] for i, label in assignments]
    for number, values in enumerate(rows, 2):
        row = ET.SubElement(data, "row", r=str(number))
        for column, value in zip(["A", "B"], values):
            cell = ET.SubElement(row, "c", r=f"{column}{number}", t="inlineStr")
            ET.SubElement(ET.SubElement(cell, "is"), "t").text = value
            if formula and number == 3 and column == "A":
                ET.SubElement(cell, "f").text = "1+0"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{sheet}" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", ET.tostring(sheet_xml))
    return path


@pytest.fixture
def dataset(tmp_path):
    sources = tmp_path / "sources"
    sources.mkdir()
    ct = volume(sources / "1.img.nii.gz", np.zeros((3, 4, 5), dtype=np.int16))
    reference = volume(sources / "1.label.nii.gz")
    split = split_file(tmp_path / "split.csv", [(1, "Training")])
    row = {"publisher_case_id": 1, "split": "Training", "ct_path": str(ct),
           "reference_path": str(reference), "ct_sha256": v.sha256(ct),
           "reference_sha256": v.sha256(reference), "ct_bytes": ct.stat().st_size,
           "reference_bytes": reference.stat().st_size, "dataset_version": "synthetic-v1",
           "pairing_evidence": "Synthetic explicit mapping", "readiness_status": "PAIR_VERIFIED_READY_FOR_REVIEW",
           "blockers": ""}
    pairs = csv_file(tmp_path / "pairs.csv", PAIR_FIELDS, [row])
    config = v.Config(split, "Split-4", pair_manifest=pairs, source_roots=(sources,))
    return config, row, ct, reference


def update_pair(config, row):
    csv_file(config.pair_manifest, PAIR_FIELDS, [row])


def codes(report):
    return {issue["code"] for issue in report["issues"]}


def test_valid_split_and_default_unverified_checks(dataset):
    config, _, _, _ = dataset
    report = v.validate(config)
    assert report["split"]["counts"] == {"Training": 1, "Val": 0, "Testing": 0}
    assert report["status"] == "NOT_VERIFIED"
    assert report["pair_summary"]["complete_pairs"] == 1
    assert report["checks"]["patient_level_leakage"] == "NOT_VERIFIED"
    assert report["checks"]["anatomical_registration"] == "NOT_VERIFIED"
    assert any("patient/group" in item for item in report["limitations"])


@pytest.mark.parametrize("assignments,expected", [
    ([(1, "Training"), (1, "Training")], "DUPLICATE_CASE_ID"),
    ([(1, "Training"), (1, "Val")], "SPLIT_LEAKAGE"),
    ([(1, "Train")], "INVALID_SPLIT"),
    ([("", "Training")], "INVALID_CASE_ID"),
    ([("not-an-id", "Training")], "INVALID_CASE_ID"),
    ([(0, "Training")], "INVALID_CASE_ID"),
])
def test_bad_split_records(dataset, assignments, expected):
    config, *_ = dataset
    split_file(config.split_manifest, assignments)
    report = v.validate(config)
    assert report["status"] == "BLOCKED_MANIFEST"
    assert expected in codes(report)


def test_expected_counts_are_explicit_not_hardcoded(dataset):
    config, *_ = dataset
    assert "SPLIT_COUNT_MISMATCH" not in codes(v.validate(config))
    assert "SPLIT_COUNT_MISMATCH" in codes(v.validate(replace(config, expected_counts={"Training": 700})))
    assert "SPLIT_COUNT_MISMATCH" not in codes(v.validate(replace(config, expected_counts={"Training": 1})))


@pytest.mark.parametrize("role", ["ct", "reference"])
def test_missing_source(dataset, role):
    config, row, *_ = dataset
    row[role + "_path"] = ""
    update_pair(config, row)
    report = v.validate(config)
    assert report["status"] == "BLOCKED_MISSING_DATA"
    assert report["pair_summary"]["missing_" + role] == 1
    assert report["pair_summary"]["unmatched_pairs"] == 1


@pytest.mark.parametrize("role", ["ct", "reference"])
def test_duplicate_source_paths(dataset, role):
    config, row, ct, reference = dataset
    split_file(config.split_manifest, [(1, "Training"), (2, "Val")])
    second = {**row, "publisher_case_id": 2, "split": "Val"}
    other = "reference" if role == "ct" else "ct"
    second[other + "_path"] = str(volume(ct.parent / ("2.label.nii.gz" if other == "reference" else "2.img.nii.gz")))
    csv_file(config.pair_manifest, PAIR_FIELDS, [row, second])
    assert "DUPLICATE_SOURCE_PATH" in codes(v.validate(config))


def test_same_path_for_image_and_mask_is_invalid(dataset):
    config, row, ct, _ = dataset
    row["reference_path"] = str(ct)
    update_pair(config, row)
    assert "DUPLICATE_SOURCE_PATH" in codes(v.validate(config))


def test_pair_split_and_filename_conflicts(dataset):
    config, row, ct, _ = dataset
    row["split"] = "Val"
    update_pair(config, row)
    assert "PAIR_SPLIT_CONFLICT" in codes(v.validate(config))
    row["split"] = "Training"
    row["ct_path"] = str(ct.parent / "2.img.nii.gz")
    update_pair(config, row)
    assert "FILENAME_CASE_CONFLICT" in codes(v.validate(config))


def test_reversed_image_mask_names_are_rejected(dataset):
    config, row, ct, reference = dataset
    row["ct_path"], row["reference_path"] = str(reference), str(ct)
    update_pair(config, row)
    assert "FILENAME_ROLE_CONFLICT" in codes(v.validate(config))


def test_duplicate_pair_ids(dataset):
    config, row, *_ = dataset
    csv_file(config.pair_manifest, PAIR_FIELDS, [row, row])
    report = v.validate(config)
    assert "DUPLICATE_PAIR_ID" in codes(report)
    assert report["pair_summary"]["complete_pairs"] == 0


@pytest.mark.parametrize("version", [1, 2])
def test_matching_headers_and_no_volume_proxy_load(dataset, monkeypatch, version):
    config, _, ct, reference = dataset
    volume(ct, np.zeros((3, 4, 5), dtype=np.int16), version=version)
    volume(reference, version=version)
    monkeypatch.setattr(nib, "load", lambda *a, **k: pytest.fail("Header inspection must not load image proxies"))
    report = v.validate(config)
    assert report["pairs"][0]["ct"]["header"]["shape"] == [3, 4, 5]
    assert report["pairs"][0]["ct"]["header"]["orientation"] == ["R", "A", "S"]
    assert "BLOCKED_GEOMETRY" not in report["blocking_statuses"]


@pytest.mark.parametrize("problem,expected", [
    ("shape", "SHAPE_MISMATCH"), ("affine", "AFFINE_MISMATCH"),
    ("unknown", "UNKNOWN_SPATIAL_UNITS"), ("incompatible", "INCOMPATIBLE_SPATIAL_UNITS"),
    ("four_d", "UNSUPPORTED_DIMENSIONS"), ("nan_spacing", "INVALID_SPACING"),
    ("uncoded", "UNCODED_OR_INVALID_TRANSFORM"), ("conflicting", "CONFLICTING_CODED_TRANSFORMS"),
    ("inconsistent_spacing", "AFFINE_SPACING_INCONSISTENT"),
    ("bad", "INVALID_NIFTI_OR_PAYLOAD"),
])
def test_geometry_failures(dataset, problem, expected):
    config, _, _, reference = dataset
    if problem == "shape":
        volume(reference, np.ones((2, 3, 4), dtype=np.uint8))
    elif problem == "affine":
        affine = np.eye(4); affine[0, 3] = 2
        volume(reference, affine=affine)
    elif problem in ("unknown", "incompatible"):
        volume(reference, units="unknown" if problem == "unknown" else "meter")
    elif problem == "four_d":
        volume(reference, np.ones((3, 4, 5, 2), dtype=np.uint8))
    elif problem == "nan_spacing":
        mutate_header(reference, 80, "<f", float("nan"))
    elif problem == "uncoded":
        mutate_header(reference, 254, "<h", 0)
    elif problem == "conflicting":
        mutate_header(reference, 252, "<h", 1)
        mutate_header(reference, 280, "<f", -1)
    elif problem == "inconsistent_spacing":
        mutate_header(reference, 80, "<f", 2)
    else:
        reference.write_bytes(b"invalid header")
    report = v.validate(config)
    assert expected in codes(report)
    assert "BLOCKED_GEOMETRY" in report["blocking_statuses"]
    json.dumps(report, allow_nan=False)


def test_geometry_tolerance(dataset):
    config, _, _, reference = dataset
    affine = np.eye(4); affine[0, 3] = v.AFFINE_ATOL / 2
    volume(reference, affine=affine)
    assert "AFFINE_MISMATCH" not in codes(v.validate(config))


def test_correct_hashes_and_binary_labels_ready_for_review_only(dataset):
    config, _, _, _ = dataset
    report = v.validate(replace(config, verify_hashes=True, deep_label_scan=True))
    assert report["status"] == "READY_FOR_REVIEW"
    assert report["pairs"][0]["ct"]["hash"]["status"] == "MATCH"
    assert report["pairs"][0]["reference"]["labels"]["status"] == "PASS"
    assert report["automatic_dataset_approval"] is False
    assert report["clinical_validation"] is False


@pytest.mark.parametrize("expected,code", [("0" * 64, "HASH_MISMATCH"), ("", "MISSING_EXPECTED_HASH"), ("invalid", "HASH_MISMATCH")])
def test_bad_or_missing_expected_hash(dataset, expected, code):
    config, row, *_ = dataset
    row["ct_sha256"] = expected
    update_pair(config, row)
    report = v.validate(replace(config, verify_hashes=True))
    assert code in codes(report)


def test_default_does_not_hash_or_scan_source_payloads(dataset, monkeypatch):
    config, _, ct, reference = dataset
    real = v.sha256
    def guard(path):
        assert path not in [ct, reference]
        return real(path)
    monkeypatch.setattr(v, "sha256", guard)
    monkeypatch.setattr(v, "scan_labels", lambda *a: pytest.fail("Deep scan was not requested"))
    assert v.validate(config)["status"] == "NOT_VERIFIED"


@pytest.mark.parametrize("value", [2, -1, float("nan"), float("inf")])
def test_bad_label_values(dataset, value):
    config, _, _, reference = dataset
    values = np.ones((3, 4, 5), dtype=np.float32); values[0, 0, 0] = value
    volume(reference, values)
    report = v.validate(replace(config, deep_label_scan=True))
    assert "INVALID_LABELS" in codes(report)
    assert report["pairs"][0]["reference"]["labels"]["status"] == "FAIL"


def test_label_scaling_is_applied(dataset):
    config, _, _, reference = dataset
    mutate_header(reference, 112, "<f", 2)
    report = v.validate(replace(config, deep_label_scan=True))
    assert "INVALID_LABELS" in codes(report)


def test_original_float64_label_precision_is_retained(dataset):
    config, _, _, reference = dataset
    values = np.ones((3, 4, 5), dtype=np.float64)
    values[0, 0, 0] = 1e-300
    volume(reference, values)
    report = v.validate(replace(config, deep_label_scan=True))
    assert report["pairs"][0]["reference"]["labels"]["unexpected_label_voxels"] == 1


def test_empty_reference_is_not_silently_approved(dataset):
    config, _, _, reference = dataset
    volume(reference, np.zeros((3, 4, 5), dtype=np.uint8))
    assert "EMPTY_REFERENCE" in codes(v.validate(replace(config, deep_label_scan=True)))


def test_truncated_reference_payload(dataset):
    config, _, _, reference = dataset
    data = gzip.decompress(reference.read_bytes())
    reference.write_bytes(gzip.compress(data[:-10]))
    assert "INVALID_NIFTI_OR_PAYLOAD" in codes(v.validate(replace(config, deep_label_scan=True)))


@pytest.mark.parametrize("compressed", [False, True])
def test_label_scan_is_chunk_bounded(tmp_path, monkeypatch, compressed):
    path = volume(tmp_path / ("labels.nii.gz" if compressed else "labels.nii"), np.ones((5, 7, 9), dtype=np.float32))
    _, layout = v.inspect_header(path)
    monkeypatch.setattr(v, "CHUNK_BYTES", 32)
    original = gzip.open if compressed else open
    reads = []
    class Reader:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): self.stream.close()
        def seek(self, offset): return self.stream.seek(offset)
        def read(self, size):
            assert 0 < size <= 32
            reads.append(size)
            return self.stream.read(size)
    def bounded(*args, **kwargs): return Reader(original(*args, **kwargs))
    if compressed:
        monkeypatch.setattr(v.gzip, "open", bounded)
    else:
        monkeypatch.setattr(v, "open", bounded, raising=False)
    result = v.scan_labels(path, layout)
    assert result["voxels_scanned"] == 315
    assert result["foreground_voxels"] == 315
    assert len(reads) > 1


def test_outside_root_is_not_opened(dataset, tmp_path, monkeypatch):
    config, row, _, _ = dataset
    outside = volume(tmp_path / "outside.nii.gz")
    row["ct_path"] = str(outside)
    update_pair(config, row)
    real = v.inspect_header
    def guard(path):
        assert path != outside
        return real(path)
    monkeypatch.setattr(v, "inspect_header", guard)
    report = v.validate(config)
    assert "PATH_OUTSIDE_ROOTS" in codes(report)
    assert str(tmp_path) not in json.dumps(report)


def test_symlink_root_escape_is_not_opened(dataset, tmp_path):
    config, row, ct, _ = dataset
    outside = volume(tmp_path / "outside.nii.gz")
    link = ct.parent / "escape.nii.gz"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Host does not grant symlink creation permission")
    row["ct_path"] = str(link)
    update_pair(config, row)
    assert "PATH_OUTSIDE_ROOTS" in codes(v.validate(config))


def test_test_case_volumes_never_opened(dataset, monkeypatch):
    config, row, ct, reference = dataset
    split_file(config.split_manifest, [(1, "Training"), (2, "Testing")])
    second = {**row, "publisher_case_id": 2, "split": "Testing", "ct_path": "DO_NOT_OPEN", "reference_path": "DO_NOT_OPEN"}
    csv_file(config.pair_manifest, PAIR_FIELDS, [row, second])
    real = v._path
    def guard(value, base, roots, findings, identifier, role):
        assert identifier != 2
        return real(value, base, roots, findings, identifier, role)
    monkeypatch.setattr(v, "_path", guard)
    report = v.validate(replace(config, verify_hashes=True, deep_label_scan=True))
    assert report["pair_summary"]["skipped_test_records"] == 1
    assert len(report["pairs"]) == 1


def test_missing_pair_record(dataset):
    config, *_ = dataset
    split_file(config.split_manifest, [(1, "Training"), (2, "Val")])
    report = v.validate(config)
    assert report["pair_summary"]["missing_pair_records"] == 1
    assert "MISSING_PAIR_RECORDS" in codes(report)


def test_unverified_source_status_cannot_be_approved(dataset):
    config, row, *_ = dataset
    row["readiness_status"] = "SOURCE_VERSION_UNVERIFIED"
    update_pair(config, row)
    report = v.validate(replace(config, verify_hashes=True, deep_label_scan=True))
    assert report["status"] == "NOT_VERIFIED"


def test_xlsx_explicit_sheet_and_exact_csv_comparison(dataset, tmp_path):
    config, *_ = dataset
    workbook = make_xlsx(tmp_path / "split.xlsx", [(1, "Training")])
    report = v.validate(replace(config, split_manifest=workbook, sheet="v2-latest", compare_split=config.split_manifest))
    assert report["split"]["csv_assignment_agreement"] is True
    assert report["split_source"]["sheet"] == "v2-latest"
    for sheet in [None, "v1"]:
        assert v.validate(replace(config, split_manifest=workbook, sheet=sheet))["status"] == "BLOCKED_MANIFEST"


def test_xlsx_formula_is_rejected(dataset, tmp_path):
    config, *_ = dataset
    p = make_xlsx(tmp_path / "formula.xlsx", [(1, "Training")], formula=True)
    assert v.validate(replace(config, split_manifest=p, sheet="v2-latest"))["status"] == "BLOCKED_MANIFEST"


def test_comparison_duplicates_and_different_assignments(dataset, tmp_path):
    config, *_ = dataset
    compared = split_file(tmp_path / "compared.csv", [(1, "Val"), (1, "Training")])
    report = v.validate(replace(config, compare_split=compared))
    assert "DUPLICATE_CASE_ID" in codes(report)
    assert "SPLIT_EXPORT_MISMATCH" in codes(report)


def test_pair_split_checksum_binding(dataset):
    config, row, *_ = dataset
    fields = [*PAIR_FIELDS, "split_sha256"]
    csv_file(config.pair_manifest, fields, [{**row, "split_sha256": "0" * 64}])
    assert "PAIR_SPLIT_HASH_MISMATCH" in codes(v.validate(config))
    csv_file(config.pair_manifest, fields, [{**row, "split_sha256": v.sha256(config.split_manifest)}])
    assert "PAIR_SPLIT_HASH_MISMATCH" not in codes(v.validate(config))


def test_all_test_cases_do_not_make_a_ready_dataset(dataset):
    config, row, *_ = dataset
    split_file(config.split_manifest, [(1, "Testing")])
    row["split"] = "Testing"
    update_pair(config, row)
    report = v.validate(replace(config, verify_hashes=True, deep_label_scan=True))
    assert report["status"] == "NOT_VERIFIED"
    assert "NO_ELIGIBLE_CASES" in codes(report)


def test_relative_paths_and_size_mismatch(dataset):
    config, row, ct, reference = dataset
    row["ct_path"] = str(ct.relative_to(config.pair_manifest.parent))
    row["reference_path"] = str(reference.relative_to(config.pair_manifest.parent))
    row["ct_bytes"] = ct.stat().st_size + 1
    update_pair(config, row)
    report = v.validate(config)
    assert report["pair_summary"]["complete_pairs"] == 1
    assert "SIZE_MISMATCH" in codes(report)


@pytest.mark.parametrize("content", ["FileName,FileName,Split-4\n1,1,Training\n", "FileName,Split-4\n1,Training,extra\n", "wrong,Split-4\n1,Training\n"])
def test_malformed_csv(dataset, content):
    config, *_ = dataset
    config.split_manifest.write_text(content)
    assert v.validate(config)["status"] == "BLOCKED_MANIFEST"


def test_source_change_during_inspection(dataset, monkeypatch):
    config, _, ct, _ = dataset
    real = v._version
    calls = 0
    def changed(path):
        nonlocal calls
        value = real(path)
        if path == ct:
            calls += 1
            if calls > 1:
                return (value[0] + 1, *value[1:])
        return value
    monkeypatch.setattr(v, "_version", changed)
    assert "SOURCE_CHANGED" in codes(v.validate(config))


def test_duplicate_ct_bytes_across_splits(dataset):
    config, row, ct, _ = dataset
    split_file(config.split_manifest, [(1, "Training"), (2, "Val")])
    copied = ct.parent / "2.img.nii.gz"; copied.write_bytes(ct.read_bytes())
    second = {**row, "publisher_case_id": 2, "split": "Val", "ct_path": str(copied),
              "reference_path": str(volume(ct.parent / "2.label.nii.gz"))}
    csv_file(config.pair_manifest, PAIR_FIELDS, [row, second])
    report = v.validate(replace(config, verify_hashes=True))
    assert any(i["code"] == "DUPLICATE_CONTENT" and i["role"] == "ct" and i["splits"] == ["Training", "Val"] for i in report["issues"])


def test_missing_nifti_dependency_is_not_verified(dataset, monkeypatch):
    config, *_ = dataset
    def absent(*args): raise ImportError
    monkeypatch.setattr(v, "inspect_header", absent)
    report = v.validate(config)
    assert "MISSING_NIFTI_DEPENDENCY" in codes(report)


def test_cli_default_stdout_only_and_explicit_report_protection(dataset, tmp_path, capsys):
    config, *_ = dataset
    args = ["--split-manifest", str(config.split_manifest), "--split-column", "Split-4"]
    before = {str(p) for p in tmp_path.rglob("*")}
    assert v.main(args) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "NOT_VERIFIED"
    assert before == {str(p) for p in tmp_path.rglob("*")}
    report = v.validate(config)
    with pytest.raises(ValueError):
        v.write_report(config.source_roots[0] / "report.json", report, config)
    with pytest.raises(ValueError):
        v.write_report(config.split_manifest.parent / "report.json", report, config)
    outside = tmp_path.parent / (tmp_path.name + "-report.json")
    try:
        v.write_report(outside, report, config)
        saved = outside.read_bytes()
        with pytest.raises(FileExistsError):
            v.write_report(outside, report, config)
        assert outside.read_bytes() == saved
    finally:
        outside.unlink(missing_ok=True)
