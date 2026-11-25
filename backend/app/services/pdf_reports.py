"""Structured PDF rendering for authorized stenosis research snapshots."""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


INK = colors.HexColor("#222222")
PAPER = colors.HexColor("#FDFFFC")
MUTED = colors.HexColor("#596352")
RULE = colors.HexColor("#D8DED3")
PALE = colors.HexColor("#F2F5EF")


def _value(value) -> str:
    if value is None:
        return "Unavailable"
    return str(value)


def _safe_paragraph(value, style):
    text = escape(_value(value)).replace("\n", "<br/>")
    return Paragraph(text, style)


def _break_hash(value) -> str:
    text = _value(value)
    return "<br/>".join(text[index:index + 32] for index in range(0, len(text), 32))


def _hash_paragraph(value, style):
    text = escape(_value(value))
    return Paragraph("<br/>".join(text[index:index + 32] for index in range(0, len(text), 32)), style)


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "VascuTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=21, leading=26, alignment=TA_LEFT, textColor=INK,
            spaceAfter=7 * mm,
        ),
        "section": ParagraphStyle(
            "VascuSection", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=11.5, leading=14, textColor=INK, spaceBefore=2 * mm,
            spaceAfter=1 * mm, keepWithNext=True,
        ),
        "subsection": ParagraphStyle(
            "VascuSubsection", parent=base["Heading3"], fontName="Helvetica-Bold",
            fontSize=10, leading=13, textColor=INK, spaceBefore=3 * mm,
            spaceAfter=2 * mm, keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "VascuBody", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8.5, leading=11.5, textColor=INK, spaceAfter=1.5 * mm,
        ),
        "small": ParagraphStyle(
            "VascuSmall", parent=base["BodyText"], fontName="Helvetica",
            fontSize=7.5, leading=10, textColor=MUTED,
        ),
        "label": ParagraphStyle(
            "VascuLabel", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=8, leading=11, textColor=MUTED,
        ),
        "value": ParagraphStyle(
            "VascuValue", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8, leading=10.5, textColor=INK,
            wordWrap="CJK",
        ),
        "notice": ParagraphStyle(
            "VascuNotice", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=8.5, leading=12, textColor=INK,
        ),
        "center": ParagraphStyle(
            "VascuCenter", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=8, leading=11, textColor=INK, alignment=TA_CENTER,
        ),
    }


def _table(rows, widths, *, repeat_rows=0, header=True):
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
    ]
    if header and rows:
        style.extend([
            ("BACKGROUND", (0, 0), (-1, 0), PALE),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, RULE),
        ])
    return Table(rows, colWidths=widths, repeatRows=repeat_rows, hAlign="LEFT", style=TableStyle(style))


def _key_values(items, styles, width):
    rows = []
    for label, value, is_hash in items:
        value_cell = _hash_paragraph(value, styles["value"]) if is_hash else _safe_paragraph(value, styles["value"])
        rows.append([_safe_paragraph(label, styles["label"]), value_cell])
    return _table(rows, [width * 0.31, width * 0.69], header=False)


def _draw_page(canvas: Canvas, doc, report):
    canvas.saveState()
    page_width, page_height = A4
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(doc.leftMargin, page_height - 12 * mm, "VASCUAI  /  RESEARCH REPORT")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(page_width - doc.rightMargin, page_height - 12 * mm, "NOT CLINICALLY VALIDATED")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.6)
    canvas.line(doc.leftMargin, page_height - 15 * mm, page_width - doc.rightMargin, page_height - 15 * mm)
    canvas.line(doc.leftMargin, 13 * mm, page_width - doc.rightMargin, 13 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(doc.leftMargin, 8.5 * mm, f"Analysis {report.analysis.analysis_id}  |  Snapshot {report.generated_at.isoformat()}")
    canvas.drawRightString(page_width - doc.rightMargin, 8.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _measurement_rows(lesion, styles, width):
    rows = [[
        _safe_paragraph("Measurement", styles["label"]),
        _safe_paragraph("Value / status", styles["label"]),
        _safe_paragraph("Method / definition", styles["label"]),
    ]]
    for field, label in (
        ("reference_diameter", "Reference diameter"),
        ("minimum_lumen_diameter", "Minimum lumen diameter"),
        ("percentage_narrowing", "Percentage narrowing"),
    ):
        item = getattr(lesion.measurements, field)
        if item.value is None:
            value = f"Unavailable: {item.unavailable_reason.message}"
        else:
            value = f"{item.value:g} {item.unit}"
        method = " / ".join(part for part in (item.method_id, item.method_version) if part) or "Not supplied"
        if item.definition:
            method += f" - {item.definition}"
        if item.reference_region:
            method += f"; reference: {item.reference_region}"
        rows.append([
            _safe_paragraph(label, styles["value"]),
            _safe_paragraph(value, styles["value"]),
            _safe_paragraph(method, styles["value"]),
        ])
    return _table(rows, [width * .25, width * .35, width * .4], repeat_rows=1)


def _story(report, styles, width):
    story = [
        Paragraph("Stenosis analysis report", styles["title"]),
        _table([[_safe_paragraph(
            "Research software snapshot only. It is not a clinical diagnosis. "
            "Unavailable measurements remain unavailable; zero candidate records do not establish absence of stenosis.",
            styles["notice"],
        )]], [width], header=False),
        Spacer(1, 2 * mm),
        _key_values([
            ("Generated (UTC)", report.generated_at.isoformat(), False),
            ("Report / analysis ID", str(report.analysis.analysis_id), False),
            ("Report state", report.report_state, False),
        ], styles, width),
        Paragraph("Case information", styles["section"]),
        _key_values([
            ("Case reference", report.case.case_reference, False),
            ("Case ID", report.case.case_id, False),
            ("Subject ID", report.case.patient_id, False),
        ], styles, width),
        Paragraph("Analysis summary", styles["section"]),
        _key_values([
            ("Analysis status", report.analysis.status, False),
            ("Method", "/".join(part for part in (report.analysis.provenance.method_id, report.analysis.provenance.method_version) if part) or "Not recorded", False),
            ("Created", report.analysis.created_at.isoformat(), False),
            ("Started", report.analysis.started_at.isoformat() if report.analysis.started_at else None, False),
            ("Completed", report.analysis.completed_at.isoformat() if report.analysis.completed_at else None, False),
        ], styles, width),
        Paragraph("Model and source provenance", styles["section"]),
        _key_values([
            ("Checkpoint SHA-256", report.analysis.provenance.checkpoint_sha256, True),
            ("Source CT SHA-256", report.analysis.provenance.source.source_sha256, True),
            ("Parent segmentation result", report.analysis.provenance.source.parent_segmentation_result_id, False),
        ], styles, width),
    ]

    if report.report_state != "completed" or report.result is None:
        story.extend([
            Paragraph("Findings unavailable", styles["section"]),
            _safe_paragraph(report.unavailable_reason, styles["body"]),
            _safe_paragraph("No completed findings are included in this report.", styles["body"]),
        ])
    else:
        result = report.result
        story.extend([
            Paragraph("Segmentation and geometry references", styles["section"]),
            _key_values([
                ("Segmentation result ID", result.segmentation.id, False),
                ("Geometry fingerprint", result.geometry_fingerprint, True),
                ("Viewer geometry", result.visualization.status, False),
                ("Visualization note", result.visualization.reason, False),
            ], styles, width),
        ])
        if not result.result.lesions:
            story.append(KeepTogether([
                Paragraph("Stenosis candidate records", styles["section"]),
                _safe_paragraph(
                    "No candidate lesion records were stored for this analysis. This is not evidence that stenosis is absent.",
                    styles["body"],
                ),
            ]))
        for index, lesion in enumerate(result.result.lesions, start=1):
            location = "Unavailable"
            if lesion.location:
                location = (
                    f"IJK {', '.join(str(value) for value in lesion.location.voxel_indices)}; "
                    f"RAS mm {', '.join(f'{value:g}' for value in lesion.location.world_coordinates)}"
                )
            severity = (
                f"Supplied category: {lesion.severity.category}"
                if lesion.severity.category is not None
                else f"Unavailable: {lesion.severity.unavailable_reason.message}"
            )
            candidate = [
                *([Paragraph("Stenosis candidate records", styles["section"])] if index == 1 else []),
                Paragraph(f"Candidate record {index}", styles["subsection"]),
                _key_values([
                    ("Record ID", lesion.lesion_id, False),
                    ("Vessel label", lesion.vessel_label, False),
                    ("Location", location, False),
                    ("Localization status", lesion.localization_unavailable_reason.message if lesion.localization_unavailable_reason else "Location supplied", False),
                    ("Severity", severity, False),
                ], styles, width),
                Spacer(1, 2 * mm),
                _measurement_rows(lesion, styles, width),
            ]
            story.append(KeepTogether(candidate))
        story.append(Paragraph("Explanation metadata", styles["section"]))
        if not report.explanations.items:
            story.append(_safe_paragraph(report.explanations.unavailable_reason.message, styles["body"]))
        else:
            for item in report.explanations.items:
                story.append(_safe_paragraph(
                    f"{item.method_name} / {item.method_version}; model {item.model_id} / {item.model_version}; "
                    f"target {item.target.identifier}; scope {item.scope}; artifact {item.artifact_id}; "
                    f"SHA-256 {item.content_sha256}. {item.limitations}",
                    styles["body"],
                ))

    limitations = [Paragraph("Limitations", styles["section"])]
    limitations.extend(_safe_paragraph(f"- {limitation}", styles["body"]) for limitation in report.limitations)
    story.append(KeepTogether(limitations))
    return story


def render_stenosis_report(report) -> bytes:
    """Render an already-authorized structured report without reading UI or files."""
    output = BytesIO()
    page_width, _ = A4
    left = right = 19 * mm
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=right,
        leftMargin=left,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
        title=f"VascuAI research report {report.analysis.analysis_id}",
        author="VascuAI",
    )
    styles = _styles()

    def canvasmaker(*args, **kwargs):
        kwargs["pageCompression"] = 0
        return Canvas(*args, **kwargs)

    doc.build(
        _story(report, styles, page_width - left - right),
        onFirstPage=lambda canvas, document: _draw_page(canvas, document, report),
        onLaterPages=lambda canvas, document: _draw_page(canvas, document, report),
        canvasmaker=canvasmaker,
    )
    return output.getvalue()
