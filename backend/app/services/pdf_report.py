"""
pdf_report.py — Geosphy Monte Carlo Simulation PDF Report Generator.

Uses ReportLab Platypus to build a professional multi-page PDF containing:
  - Cover section: branding, location, assessment metadata
  - Executive summary: base / best / worst case ROI impact
  - Risk pillar uncertainty bands table (p10 / p50 / p90)
  - ROI sensitivity tornado table sorted by swing size
  - Methodology & data attribution footer
"""
import io
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Brand colours ─────────────────────────────────────────────────────────────
BRAND_DARK   = colors.HexColor("#0f172a")   # slate-900
BRAND_BLUE   = colors.HexColor("#3b82f6")   # blue-500
BRAND_TEXT   = colors.HexColor("#1e293b")   # slate-800
MUTED        = colors.HexColor("#64748b")   # slate-500
ROW_ALT      = colors.HexColor("#f1f5f9")   # slate-100
BORDER       = colors.HexColor("#cbd5e1")   # slate-300
RED          = colors.HexColor("#ef4444")
ORANGE       = colors.HexColor("#f97316")
YELLOW       = colors.HexColor("#eab308")
GREEN        = colors.HexColor("#22c55e")
DARK_RED     = colors.HexColor("#7f1d1d")
DARK_GREEN   = colors.HexColor("#14532d")


def _level_color(score: float) -> colors.Color:
    if score >= 0.85:  return RED
    if score >= 0.65:  return ORANGE
    if score >= 0.45:  return YELLOW
    return GREEN


def _level_label(score: float) -> str:
    if score >= 0.85:  return "EXTREME"
    if score >= 0.65:  return "HIGH"
    if score >= 0.45:  return "MEDIUM"
    return "LOW"


def _fmt_usd(v: float) -> str:
    abs_v = abs(v)
    if abs_v >= 1_000_000:
        return f"${v / 1_000_000:,.2f}M"
    if abs_v >= 1_000:
        return f"${v / 1_000:,.0f}K"
    return f"${v:,.0f}"


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


# ── Style sheet ───────────────────────────────────────────────────────────────

def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title", fontName="Helvetica-Bold",
            fontSize=26, textColor=BRAND_DARK, leading=32, spaceAfter=6,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", fontName="Helvetica",
            fontSize=12, textColor=MUTED, leading=16, spaceAfter=4,
        ),
        "section": ParagraphStyle(
            "section", fontName="Helvetica-Bold",
            fontSize=13, textColor=BRAND_DARK, leading=18,
            spaceBefore=14, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica",
            fontSize=9, textColor=BRAND_TEXT, leading=13, spaceAfter=4,
        ),
        "caption": ParagraphStyle(
            "caption", fontName="Helvetica",
            fontSize=8, textColor=MUTED, leading=11, spaceAfter=2,
        ),
        "footer": ParagraphStyle(
            "footer", fontName="Helvetica",
            fontSize=7.5, textColor=MUTED, leading=10, alignment=TA_CENTER,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label", fontName="Helvetica",
            fontSize=8, textColor=MUTED, leading=10, alignment=TA_CENTER,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value", fontName="Helvetica-Bold",
            fontSize=18, textColor=BRAND_DARK, leading=22, alignment=TA_CENTER,
        ),
        "th": ParagraphStyle(
            "th", fontName="Helvetica-Bold",
            fontSize=8, textColor=colors.white, leading=10, alignment=TA_CENTER,
        ),
        "td": ParagraphStyle(
            "td", fontName="Helvetica",
            fontSize=8, textColor=BRAND_TEXT, leading=10, alignment=TA_CENTER,
        ),
        "td_left": ParagraphStyle(
            "td_left", fontName="Helvetica",
            fontSize=8, textColor=BRAND_TEXT, leading=10, alignment=TA_LEFT,
        ),
    }


# ── Header / footer callback ───────────────────────────────────────────────────

class _PageDecorator:
    """Draws page header and footer on every page."""

    def __init__(self, address: str, generated_at: str):
        self.address = address
        self.generated_at = generated_at

    def __call__(self, canvas, doc):
        canvas.saveState()
        w, h = A4

        # Top bar
        canvas.setFillColor(BRAND_DARK)
        canvas.rect(0, h - 14*mm, w, 14*mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(15*mm, h - 9*mm, "GEOSPHY™")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(15*mm + 52, h - 9*mm, "Data Center Climate Risk Intelligence")
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(w - 15*mm, h - 9*mm, f"Page {doc.page}")

        # Blue accent line under header
        canvas.setStrokeColor(BRAND_BLUE)
        canvas.setLineWidth(1.5)
        canvas.line(0, h - 14*mm, w, h - 14*mm)

        # Bottom footer
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(15*mm, 14*mm, w - 15*mm, 14*mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(15*mm, 9*mm, f"Location: {self.address}")
        canvas.drawRightString(w - 15*mm, 9*mm,
            f"Generated: {self.generated_at}  |  CSRD/ESRS E1 · EU Taxonomy · DORA")

        canvas.restoreState()


# ── Table helpers ─────────────────────────────────────────────────────────────

def _header_row(cells: list[str], st: dict) -> list[Paragraph]:
    return [Paragraph(c, st["th"]) for c in cells]


def _td(text: str, st: dict, left: bool = False) -> Paragraph:
    return Paragraph(str(text), st["td_left"] if left else st["td"])


def _base_table_style() -> list:
    return [
        ("BACKGROUND",  (0, 0), (-1, 0), BRAND_DARK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("GRID",        (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ]


# ── Main builder ─────────────────────────────────────────────────────────────

def build_simulation_pdf(
    simulation_result: dict[str, Any],
    location: str = "Unknown Location",
    risk_scores: dict[str, float] | None = None,
) -> bytes:
    """
    Build and return a PDF report as bytes.

    Parameters
    ----------
    simulation_result : dict
        The JSON response from POST /api/v1/simulate.
    location : str
        Canonical address string shown in the header and cover.
    risk_scores : dict, optional
        Point-estimate scores for {thermal, flood, water, storm, grid, overall}.
    """
    buf = io.BytesIO()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )

    decorator = _PageDecorator(location, generated_at)
    st = _styles()
    story = []

    W = A4[0] - 30*mm   # usable width

    # ── Cover block ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("Monte Carlo Climate Risk Report", st["cover_title"]))
    story.append(Paragraph(location, st["cover_sub"]))
    story.append(Paragraph(
        f"EU Physical Risk Assessment  ·  CSRD / ESRS E1  ·  EU Taxonomy  ·  DORA",
        st["cover_sub"],
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=BRAND_BLUE, spaceAfter=10))

    # ── Executive KPI row ──────────────────────────────────────────────────────
    n_iter = simulation_result.get("n_iterations", 1000)
    base   = simulation_result.get("total_base_impact_usd", 0)
    worst  = simulation_result.get("total_worst_case_usd", 0)
    best   = simulation_result.get("total_best_case_usd", 0)

    kpi_data = [
        [
            Paragraph("BEST CASE (p10)", st["kpi_label"]),
            Paragraph("BASE CASE (point est.)", st["kpi_label"]),
            Paragraph("WORST CASE (p90)", st["kpi_label"]),
            Paragraph("ITERATIONS", st["kpi_label"]),
        ],
        [
            Paragraph(_fmt_usd(best),  ParagraphStyle("kv_g", fontName="Helvetica-Bold",
                fontSize=16, textColor=GREEN, alignment=TA_CENTER)),
            Paragraph(_fmt_usd(base),  ParagraphStyle("kv_b", fontName="Helvetica-Bold",
                fontSize=16, textColor=BRAND_DARK, alignment=TA_CENTER)),
            Paragraph(_fmt_usd(worst), ParagraphStyle("kv_r", fontName="Helvetica-Bold",
                fontSize=16, textColor=RED, alignment=TA_CENTER)),
            Paragraph(f"{n_iter:,}", ParagraphStyle("kv_n", fontName="Helvetica-Bold",
                fontSize=16, textColor=BRAND_BLUE, alignment=TA_CENTER)),
        ],
        [
            Paragraph("Annual risk-adjusted cost", st["kpi_label"]),
            Paragraph("Annual risk-adjusted cost", st["kpi_label"]),
            Paragraph("Annual risk-adjusted cost", st["kpi_label"]),
            Paragraph("Monte Carlo Beta dist.", st["kpi_label"]),
        ],
    ]

    col_w = W / 4
    kpi_table = Table(kpi_data, colWidths=[col_w] * 4, rowHeights=[14, 24, 12])
    kpi_table.setStyle(TableStyle([
        ("BOX",         (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID",   (0, 0), (-1, -1), 0.4, BORDER),
        ("BACKGROUND",  (0, 0), (0, 2),   colors.HexColor("#f0fdf4")),   # green tint
        ("BACKGROUND",  (1, 0), (1, 2),   colors.HexColor("#f8fafc")),   # neutral
        ("BACKGROUND",  (2, 0), (2, 2),   colors.HexColor("#fff1f2")),   # red tint
        ("BACKGROUND",  (3, 0), (3, 2),   colors.HexColor("#eff6ff")),   # blue tint
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 6*mm))

    # ── Risk Pillar Uncertainty Bands ─────────────────────────────────────────
    story.append(Paragraph("Risk Pillar Uncertainty Bands", st["section"]))
    story.append(Paragraph(
        "Percentile distribution of each pillar score across all Monte Carlo iterations. "
        "The IQR (p25–p75) represents the most likely outcome range; p10–p90 spans the "
        "full uncertainty envelope.",
        st["body"],
    ))

    bands = simulation_result.get("pillar_bands", [])
    band_header = _header_row(
        ["Pillar", "Point Est.", "p10 (Best)", "p25", "p50 (Median)", "p75", "p90 (Worst)", "Risk Level"],
        st,
    )
    band_rows = [band_header]

    for b in bands:
        pe = b.get("point_estimate", 0)
        level_label = _level_label(pe)
        level_col   = _level_color(pe)
        band_rows.append([
            _td(b.get("pillar", ""), st, left=True),
            _td(_pct(pe),                           st),
            _td(_pct(b.get("p10", 0)),              st),
            _td(_pct(b.get("p25", 0)),              st),
            _td(_pct(b.get("p50", 0)),              st),
            _td(_pct(b.get("p75", 0)),              st),
            _td(_pct(b.get("p90", 0)),              st),
            Paragraph(level_label, ParagraphStyle(
                "lvl", fontName="Helvetica-Bold", fontSize=7.5,
                textColor=level_col, alignment=TA_CENTER,
            )),
        ])

    col_widths = [28*mm, 18*mm, 20*mm, 16*mm, 24*mm, 16*mm, 24*mm, 22*mm]
    band_table = Table(band_rows, colWidths=col_widths)
    ts = _base_table_style()
    # Colour p90 column to hint at worst case
    ts.append(("TEXTCOLOR", (6, 1), (6, -1), ORANGE))
    ts.append(("TEXTCOLOR", (2, 1), (2, -1), GREEN))
    band_table.setStyle(TableStyle(ts))
    story.append(band_table)
    story.append(Spacer(1, 6*mm))

    # ── ROI Sensitivity (Tornado) ─────────────────────────────────────────────
    story.append(Paragraph("ROI Sensitivity Analysis (Tornado)", st["section"]))
    story.append(Paragraph(
        "Each row shows the annual financial impact of one risk driver, "
        "ranging from its p10 (optimistic) to p90 (stressed) scenario. "
        "The swing column quantifies how much that driver moves total cost — "
        "the primary input for capital allocation and risk mitigation prioritisation.",
        st["body"],
    ))

    sensitivity = simulation_result.get("roi_sensitivity", [])
    sens_header = _header_row(
        ["Risk Driver", "Base Impact", "Best Case (p10)", "Worst Case (p90)",
         "Swing", "% of Total"],
        st,
    )
    sens_rows = [sens_header]

    for i, s in enumerate(sensitivity):
        swing = s.get("swing_usd", 0)
        pct   = s.get("pct_of_total", 0)
        # Bar width as fraction of swing column
        bar_width_pct = min(pct / 100, 1.0)
        sens_rows.append([
            _td(s.get("driver", ""), st, left=True),
            _td(_fmt_usd(s.get("base_impact_usd", 0)),  st),
            Paragraph(_fmt_usd(s.get("low_impact_usd", 0)),
                ParagraphStyle("td_g", fontName="Helvetica", fontSize=8,
                    textColor=DARK_GREEN, alignment=TA_CENTER)),
            Paragraph(_fmt_usd(s.get("high_impact_usd", 0)),
                ParagraphStyle("td_r", fontName="Helvetica", fontSize=8,
                    textColor=DARK_RED, alignment=TA_CENTER)),
            Paragraph(f"<b>{_fmt_usd(swing)}</b>",
                ParagraphStyle("td_s", fontName="Helvetica-Bold", fontSize=8,
                    textColor=BRAND_DARK, alignment=TA_CENTER)),
            _td(f"{pct:.1f}%", st),
        ])

    sens_col_w = [52*mm, 26*mm, 28*mm, 28*mm, 24*mm, 20*mm]
    sens_table = Table(sens_rows, colWidths=sens_col_w)
    sts2 = _base_table_style()
    sts2.append(("FONTNAME", (0, 1), (0, -1), "Helvetica"))
    sens_table.setStyle(TableStyle(sts2))
    story.append(sens_table)
    story.append(Spacer(1, 6*mm))

    # ── ROI impact model breakdown ─────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=6))
    story.append(Paragraph("ROI Impact Model Components", st["section"]))

    model_rows = [
        _header_row(["Component", "Driver", "Formula", "Range"], st),
        [
            _td("CapEx Risk Premium", st, left=True),
            _td("Flood + Storm", st),
            _td("(Flood x 0.65 + Storm x 0.35) x 18% of CapEx", st, left=True),
            _td("0% - 18% of CapEx", st),
        ],
        [
            _td("Cooling OpEx", st, left=True),
            _td("Thermal", st),
            _td("(PUE-1) x IT Load x 8760h x Tariff; PUE = 1.2 + score x 0.6", st, left=True),
            _td("PUE 1.2 - 1.8", st),
        ],
        [
            _td("Downtime Cost", st, left=True),
            _td("Grid", st),
            _td("SAIDI x (1 + Grid x 3) x Hourly Revenue", st, left=True),
            _td("1x - 4x SAIDI", st),
        ],
        [
            _td("Insurance Premium", st, left=True),
            _td("Overall", st),
            _td("0.3% + score x 2.2% of Asset Value", st, left=True),
            _td("0.3% - 2.5% AV", st),
        ],
    ]
    model_col_w = [38*mm, 24*mm, 80*mm, 26*mm]
    model_table = Table(model_rows, colWidths=model_col_w)
    model_table.setStyle(TableStyle(_base_table_style()))
    story.append(model_table)
    story.append(Spacer(1, 5*mm))

    # ── Methodology note ──────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=4))
    story.append(Paragraph(
        "<b>Methodology:</b>  Monte Carlo simulation using Beta distributions (Johnk's method via "
        "Python random.gammavariate). Each risk pillar is sampled independently from a Beta(alpha, beta) "
        "distribution parameterised by its point estimate and a confidence half-width of ±15%. "
        "The overall score is computed as a weighted mean: Thermal 28%, Flood 22%, Water 20%, "
        "Storm 15%, Grid 15%. All financial impact figures are annual estimates in USD.",
        st["body"],
    ))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(
        "<b>Regulatory Framework:</b>  This report supports compliance with CSRD/ESRS E1 (Physical Climate "
        "Risk Disclosure), EU Taxonomy Regulation (Technical Screening Criteria — Climate Change Adaptation), "
        "DORA (ICT Risk Management for Digital Infrastructure), and EU Delegated Regulation 2024/1364 (WUE). "
        "All scores are indicative and must be reviewed by a qualified climate risk professional before "
        "use in statutory disclosures.",
        st["body"],
    ))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(
        "<b>Data Sources:</b>  Open-Meteo ERA5 Reanalysis · World Bank CCKP (SSP2-4.5, 2050) · "
        "FEMA National Flood Hazard Layer · NOAA CDO · OSM Nominatim · Overpass API. "
        "Generated by Geosphy™ — geosphy.io",
        st["caption"],
    ))

    # ── Build PDF ──────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=decorator, onLaterPages=decorator)
    return buf.getvalue()
