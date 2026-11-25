"""Portable cohort identity; physical storage and runtime are separate contracts.

Only Training/Val files supplied by the already filtered Index are ever hashed.
Workbook parsing uses stdlib ZIP/XML and reads assignment metadata, not images.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .dataset import DataError, file_version, fingerprint
from .runtime import portable_absolute


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def identity_config(value=None):
    defaults = dict(dataset_id="ImageCAS", version_id=None, provenance=None,
                    content_manifest=None, content_manifest_sha256=None,
                    verify_content=False, expected_manifest_fingerprint=None)
    if value is None:
        return defaults
    if not isinstance(value, dict) or set(value) - set(defaults):
        raise DataError("Unknown dataset_identity configuration.")
    result = {**defaults, **value}
    if (not isinstance(result["dataset_id"], str) or not result["dataset_id"].strip()
            or (result["version_id"] is not None and
                (not isinstance(result["version_id"], str) or not result["version_id"].strip()))
            or type(result["verify_content"]) is not bool):
        raise DataError("Invalid stable dataset/version identifier or verification flag.")
    for key in ("content_manifest_sha256", "expected_manifest_fingerprint"):
        if result[key] is not None and not _hash(result[key]):
            raise DataError("Expected a lowercase SHA-256 identity pin.")
    if (result["content_manifest"] is None) != (result["content_manifest_sha256"] is None):
        raise DataError("Content manifest requires its independently recorded SHA-256 pin.")
    if result["content_manifest"]:
        portable_absolute(result["content_manifest"])
    provenance = result["provenance"]
    if provenance is not None:
        keys = {"workbook_path", "workbook_sha256", "sheet", "header_row", "id_column", "split_column"}
        if (not isinstance(provenance, dict) or set(provenance) != keys
                or not _hash(provenance["workbook_sha256"])
                or provenance["sheet"] != "v2-latest" or provenance["header_row"] != 2
                or provenance["id_column"] != "FileName" or provenance["split_column"] != "Split-4"):
            raise DataError("Require explicit authoritative ImageCAS v2-latest / Split-4 provenance.")
        portable_absolute(provenance["workbook_path"])
    if (result["version_id"] or result["verify_content"]) and provenance is None:
        raise DataError("Pinned/verified identity requires authoritative workbook provenance.")
    if result["verify_content"] and result["content_manifest"] is None:
        raise DataError("Content verification requires a pinned content manifest.")
    return result


def identity_paths(options):
    result = []
    if options.get("provenance"):
        result.append(options["provenance"]["workbook_path"])
    if options.get("content_manifest"):
        result.append(options["content_manifest"])
    return result


def workbook_assignments(path, provenance):
    """Read a small, hash-pinned XLSX without formulas, external links or code."""
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist()) > 32 * 1024 * 1024:
            raise DataError("Oversized split workbook.")
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = [s for s in book.findall("s:sheets/s:sheet", ns) if s.get("name") == provenance["sheet"]]
        if len(sheets) != 1:
            raise DataError("Authoritative workbook sheet is missing/ambiguous.")
        rid = sheets[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = [r.get("Target") for r in rels if r.get("Id") == rid and r.get("TargetMode") != "External"]
        if len(targets) != 1:
            raise DataError("Unsafe workbook sheet relationship.")
        member = targets[0].lstrip("/") if targets[0].startswith("/") else "xl/" + targets[0]
        if ".." in PurePosixPath(member).parts or "\\" in member:
            raise DataError("Unsafe workbook sheet path.")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(i.itertext()) for i in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", ns)]
        rows = ET.fromstring(archive.read(member)).findall("s:sheetData/s:row", ns)
        columns, assignments = {}, {}
        for row in rows:
            values = {}
            for cell in row.findall("s:c", ns):
                column = re.sub(r"[0-9]", "", cell.get("r", ""))
                if cell.find("s:f", ns) is not None:
                    raise DataError("Formula cells are unsupported in authoritative split data.")
                value = cell.findtext("s:v", default="", namespaces=ns)
                if cell.get("t") == "s":
                    value = strings[int(value)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(cell.find("s:is", ns).itertext())
                values[column] = value.strip()
            number = int(row.get("r"))
            if number == provenance["header_row"]:
                for name in (provenance["id_column"], provenance["split_column"]):
                    matches = [c for c, v in values.items() if v == name]
                    if len(matches) != 1:
                        raise DataError("Missing/duplicate authoritative split column.")
                    columns[name] = matches[0]
            elif number > provenance["header_row"]:
                if not columns:
                    raise DataError("Authoritative header row was not found.")
                cid, split = (values.get(columns[k], "") for k in (provenance["id_column"], provenance["split_column"]))
                if not cid and not split:
                    continue
                if not cid.isdecimal() or not 1 <= int(cid) <= 1000 or split not in ("Training", "Val", "Testing") or int(cid) in assignments:
                    raise DataError("Invalid authoritative assignment.")
                assignments[int(cid)] = split
    return assignments


def build_identity(index, records, value=None):
    options = identity_config(value)
    pin = options["expected_manifest_fingerprint"]
    if pin and pin != index.manifest_fingerprint:
        raise DataError("Canonical manifest fingerprint mismatch.")
    provenance = options["provenance"]
    verified_provenance = None
    if provenance:
        path = Path(provenance["workbook_path"])
        before = file_version(path)
        if sha256(path) != provenance["workbook_sha256"]:
            raise DataError("Authoritative workbook SHA-256 mismatch.")
        if workbook_assignments(path, provenance) != index.assignments:
            raise DataError("Manifest split assignments differ from authoritative workbook.")
        if file_version(path) != before or sha256(path) != provenance["workbook_sha256"]:
            raise DataError("Authoritative workbook changed while reading.")
        verified_provenance = {k: v for k, v in provenance.items() if k != "workbook_path"}
    content_fingerprint = None
    if options["content_manifest"]:
        payload = Path(options["content_manifest"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != options["content_manifest_sha256"]:
            raise DataError("Content manifest SHA-256 mismatch.")
        content = json.loads(payload)
        if not isinstance(content, dict) or set(content) != {"schema_version", "files"} or content["schema_version"] != 1 or not isinstance(content["files"], list):
            raise DataError("Invalid content manifest schema.")
        expected = {r["case_id"]: r for r in records if r["split"] != "Testing"}
        found = {}
        for row in content["files"]:
            if not isinstance(row, dict) or set(row) != {"case_id", "split", "ct_member", "mask_member", "ct_sha256", "mask_sha256"}:
                raise DataError("Invalid content record.")
            cid = row["case_id"]
            if type(cid) is not int or cid not in expected or cid in found:
                raise DataError("Content manifest must contain exactly the permitted Training/Val cases.")
            canonical = {k: row[k] for k in expected[cid]}
            if canonical != expected[cid] or not all(_hash(row[k]) for k in ("ct_sha256", "mask_sha256")):
                raise DataError("Content manifest case/split/member mapping mismatch.")
            found[cid] = row
        if set(found) != set(expected):
            raise DataError("Incomplete content manifest.")
        content_fingerprint = fingerprint([found[i] for i in sorted(found)])
        if options["verify_content"]:
            for cid, row in found.items():
                case = index.cases[cid]
                for kind in ("ct", "mask"):
                    path = getattr(case, kind)
                    version = getattr(case, kind + "_version")
                    if file_version(path) != version or sha256(path) != row[kind + "_sha256"] or file_version(path) != version:
                        raise DataError(f"Source content SHA-256/version mismatch for case {cid} ({kind}).")
    level = "content-verified" if options["verify_content"] else "version-pinned" if options["version_id"] else "structural"
    identity = {"level": level, "dataset_id": options["dataset_id"], "version_id": options["version_id"],
                "manifest_fingerprint": index.manifest_fingerprint, "split_fingerprint": index.split_fingerprint,
                "provenance": verified_provenance, "content_manifest_fingerprint": content_fingerprint,
                "content_identity_verified": options["verify_content"]}
    return {**identity, "fingerprint": fingerprint(identity)}
