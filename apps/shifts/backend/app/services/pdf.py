"""Single-page A4 schedule lists, downloaded without a browser print dialog."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from itertools import combinations
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from ..config import settings
from ..branding import LOGO_PATH
from ..i18n import month_name
from ..models import Assignment, Schedule

# ReportLab ships these Unicode fonts, including Portuguese accents, in its wheel.
FONT_DIR = Path(reportlab.__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("Rota", str(FONT_DIR / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("RotaBold", str(FONT_DIR / "VeraBd.ttf")))
RED = HexColor("#c81018")
GREEN = HexColor("#183c2f")
MUTED = HexColor("#6f6567")


@dataclass
class MonthBlock:
    title: str
    rows: list[tuple[str, Paragraph, float]]
    height: float


def _columns(blocks: list[MonthBlock], count: int) -> list[list[MonthBlock]]:
    """Balance complete months across columns, retaining chronological order."""
    best: list[list[MonthBlock]] = []
    best_height = float("inf")
    for cuts in combinations(range(1, len(blocks)), count - 1):
        edges = (0, *cuts, len(blocks))
        groups = [blocks[left:right] for left, right in zip(edges, edges[1:])]
        height = max(sum(block.height for block in group) for group in groups)
        if height < best_height:
            best, best_height = groups, height
    return best


def _layout(
    months: dict[tuple[int, int], list[Assignment]], width: float, available: float
) -> tuple[list[list[MonthBlock]], float, float, float]:
    """Fit the entire list on one page, wrapping names instead of truncating them."""
    for count in range(1, min(4, len(months)) + 1):
        column_width = (width - (count - 1) * 7 * mm) / count
        for size in range(16, 7, -1):
            style = ParagraphStyle(
                "team", fontName="RotaBold", fontSize=size, leading=size * 1.3,
                textColor=GREEN, splitLongWords=True,
            )
            blocks = []
            for (year, month), assignments in months.items():
                rows = []
                for assignment in assignments:
                    text = assignment.team.name if assignment.team else "Sem atribuição"
                    paragraph = Paragraph(escape(text), style)
                    _, height = paragraph.wrap(column_width - size * 2.5, available)
                    rows.append((str(assignment.date.day), paragraph, height + size * 0.3))
                if not rows:
                    paragraph = Paragraph("Sem turnos neste período.", style)
                    _, height = paragraph.wrap(column_width - size * 2.5, available)
                    rows.append(("", paragraph, height + size * 0.3))
                blocks.append(MonthBlock(
                    f"{month_name(month)} {year}", rows,
                    size * 2 + sum(row[2] for row in rows) + size,
                ))
            groups = _columns(blocks, count)
            height = max(sum(block.height for block in group) for group in groups)
            if height <= available:
                return groups, column_width, size, 1.0
    # Very dense ranges or unusually long names still retain every row on A4.
    return groups, column_width, size, min(1.0, available / height)


def build_schedule_pdf(
    schedule: Schedule, assignments: list[Assignment], start: date, end: date
) -> bytes:
    output = BytesIO()
    canvas = Canvas(output, pagesize=A4)
    canvas.setTitle(schedule.name)
    canvas.setAuthor(settings.app_name)
    width, height = A4
    margin = 16 * mm
    left_margin = 24 * mm
    content_width = width - left_margin - margin
    text_x = left_margin + 94
    text_width = content_width - 112
    brand = Paragraph(escape(settings.app_name.upper()), ParagraphStyle(
        "brand", fontName="RotaBold", fontSize=9, leading=12, textColor=MUTED,
    ))
    _, brand_height = brand.wrap(text_width, height)
    title = Paragraph(escape(schedule.name), ParagraphStyle(
        "title", fontName="RotaBold", fontSize=24, leading=29, textColor=RED,
    ))
    _, title_height = title.wrap(text_width, height)
    header_height = max(94, brand_height + title_height + 43)
    header_top = height - margin
    header_bottom = header_top - header_height

    # A softly tinted banner and white logo badge frame the CRR identity.
    canvas.setFillColor(HexColor("#fff4f4"))
    canvas.roundRect(left_margin, header_bottom, content_width, header_height, 10, stroke=0, fill=1)
    badge_y = header_bottom + (header_height - 68) / 2
    canvas.setFillColor(HexColor("#ffffff"))
    canvas.roundRect(left_margin + 12, badge_y, 68, 68, 8, stroke=0, fill=1)
    canvas.drawImage(
        str(LOGO_PATH), left_margin + 18, badge_y + 6, width=56, height=56,
        preserveAspectRatio=True, anchor="c", mask="auto",
    )
    text_top = header_bottom + (header_height + brand_height + 7 + title_height) / 2
    brand.drawOn(canvas, text_x, text_top - brand_height)
    title.drawOn(canvas, text_x, text_top - brand_height - 7 - title_height)

    canvas.setStrokeColor(HexColor("#eedada"))
    canvas.setLineWidth(0.7)
    canvas.line(left_margin, header_bottom - 12, width - margin, header_bottom - 12)
    canvas.setStrokeColor(RED)
    canvas.setLineWidth(3)
    canvas.line(left_margin, header_bottom - 12, left_margin + 44, header_bottom - 12)
    top = header_bottom - 30
    available = top - margin

    months: dict[tuple[int, int], list[Assignment]] = defaultdict(list)
    for assignment in sorted(assignments, key=lambda row: row.date):
        months[(assignment.date.year, assignment.date.month)].append(assignment)
    if not months:
        months[(start.year, start.month)] = []
    groups, column_width, size, scale = _layout(months, content_width, available)
    canvas.saveState()
    canvas.translate(left_margin, top)
    canvas.scale(scale, scale)
    for index, group in enumerate(groups):
        x = index * (column_width + 7 * mm)
        y = 0.0
        for block in group:
            canvas.setFillColor(RED)
            canvas.setFont("RotaBold", size)
            canvas.drawString(x, y - size, block.title)
            y -= size * 2
            for day, paragraph, row_height in block.rows:
                canvas.setFillColor(GREEN)
                canvas.setFont("RotaBold", size)
                canvas.drawRightString(x + size * 1.5, y - size, day)
                paragraph.drawOn(canvas, x + size * 2.5, y - paragraph.height)
                y -= row_height
            y -= size
    canvas.restoreState()
    canvas.showPage()
    canvas.save()
    return output.getvalue()
