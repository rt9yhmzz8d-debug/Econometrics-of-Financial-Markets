#!/usr/bin/env python3
"""Render the source-checked IEM pilot as a one-page explanation."""

import argparse
import csv
from datetime import date
from io import BytesIO
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

HERE = Path(__file__).resolve().parent
NAVY = "#14324B"
TEAL = "#007F79"
BLUE = "#426FA8"
ORANGE = "#C06A22"
RED = "#B53C40"
GREY = "#556471"


def build(output):
    checks = json.loads((HERE / "source_checks.json").read_text())
    summary = json.loads((HERE / "generated/audit_summary.json").read_text())
    with (HERE / "generated/pilot_2001_11_06.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    with (HERE / "generated/zero_quantity_price_changes.csv").open() as stream:
        anomalies = [r for r in csv.DictReader(stream)
                     if r["market_id"] == "51" and r["contract"] in checks["pilot"]["contracts"].values()]
    dates = [date.fromisoformat(r["date"]) for r in rows]
    meeting = date.fromisoformat(checks["pilot"]["meeting_date"])
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
    fig, ax = plt.subplots(figsize=(8.2, 3.35))
    fig.subplots_adjust(left=.085, right=.985, bottom=.16, top=.84)
    for direction, colour, label in (("down", TEAL, "Lower target"),
                                     ("same", BLUE, "Unchanged target"),
                                     ("up", ORANGE, "Higher target")):
        values = [float(r["reported_last_" + direction]) for r in rows]
        ax.plot(dates, values, color=colour, lw=1.7, label=label, zorder=2)
        active = [i for i, r in enumerate(rows) if float(r["reported_quantity_" + direction]) > 0]
        ax.scatter([dates[i] for i in active], [values[i] for i in active], color=colour, s=9, zorder=3)
    ax.scatter([date.fromisoformat(r["observation_date"]) for r in anomalies],
               [float(r["last_price"]) for r in anomalies],
               facecolors="none", edgecolors=RED, s=46, linewidths=1.15,
               marker="s", label="Changed price, zero units", zorder=5)
    ax.axvspan(meeting, dates[-1], color="#F6D694", alpha=.55, zorder=0)
    ax.axvline(meeting, color="#A67726", linestyle="--", lw=1)
    ax.text(meeting, 1.035, "  6 Nov decision", color="#80551D", fontsize=8,
            ha="right", va="bottom")
    ax.set_xlim(dates[0], dates[-1])
    ax.set_ylim(-.025, 1.10)
    ax.set_ylabel("Reported last price (USD)", color=NAVY)
    ticks = [date(2001, 10, d) for d in (3, 10, 17, 24, 31)] + [meeting]
    ax.set_xticks(ticks)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.grid(axis="y", color="#E0E7EC", lw=.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["bottom", "left"]].set_color("#B7C4CD")
    ax.tick_params(colors=GREY, length=3)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.025), ncol=2,
              frameon=False, fontsize=8, borderaxespad=0)
    image = BytesIO()
    fig.savefig(image, format="png", dpi=220, facecolor="white")
    plt.close(fig)
    image.seek(0)

    for name, weight in (("DV", "normal"), ("DV-Bold", "bold")):
        font = findfont(FontProperties(family="DejaVu Sans", weight=weight))
        pdfmetrics.registerFont(TTFont(name, font))
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output), pagesize=A4)
    pdf.setTitle("ECMT3150 - One Fed meeting: a worked data example")
    pdf.setAuthor("ECMT3150 research working notes")
    width, height = A4
    margin, usable = 42, width - 84

    def text(label, x, y, size=10, colour=NAVY, bold=False):
        pdf.setFont("DV-Bold" if bold else "DV", size)
        pdf.setFillColor(colors.HexColor(colour))
        pdf.drawString(x, y, label)

    def paragraph(label, y, size=9, colour=NAVY, leading=13):
        style = ParagraphStyle("body", fontName="DV", fontSize=size,
                               textColor=colors.HexColor(colour), leading=leading)
        item = Paragraph(label, style)
        _, item_height = item.wrap(usable, height)
        item.drawOn(pdf, margin, y - item_height)
        return y - item_height

    def table(data, top, widths, heights):
        item = Table(data, colWidths=widths, rowHeights=heights)
        item.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "DV"), ("FONTSIZE", (0, 0), (-1, -1), 8.3),
            ("FONTNAME", (0, 0), (-1, 0), "DV-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(NAVY)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F4")),
            ("LINEBELOW", (0, 0), (-1, 0), .7, colors.HexColor("#CAD6DF")),
            ("LINEBELOW", (0, 1), (-1, -1), .35, colors.HexColor("#E3E9EE")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        _, item_height = item.wrap(usable, height)
        item.drawOn(pdf, margin, top - item_height)

    text("ECMT3150  /  WORKED DATA EXAMPLE", margin, 801, 8, GREY, True)
    text("Reading one Fed meeting", margin, 770, 23, NAVY, True)
    text("6 November 2001     Iowa Electronic Markets, FedPolicyB", margin, 750, 10, GREY)
    paragraph("Before testing which market moves first, establish what its prices mean. "
              "This example checks the IEM side of one meeting using the original Round 4 download.", 733, 9.4, leading=14)
    pdf.setFillColor(colors.HexColor("#FFF1D5"))
    pdf.roundRect(margin, 667, usable, 28, 5, fill=1, stroke=0)
    text("Contract definitions checked. Price/volume consistency unresolved.", margin + 10, 678, 9.1, "#75501C", True)

    text("1. What the three contracts mean", margin, 647, 10.5, NAVY, True)
    table([
        ["Contract", "Pays USD 1 if the 6 November target rate is..."],
        ["FRdown1101", "lower than on 3 October 2001"],
        ["FRsame1101", "unchanged from 3 October 2001"],
        ["FRup1101", "higher than on 3 October 2001"],
    ], 635, [119, usable - 119], [20, 19, 19, 19])
    text("2. Follow the reported prices through time", margin, 539, 10.5, NAVY, True)
    pdf.drawImage(ImageReader(image), margin - 5, 302, width=usable + 5, height=224)
    paragraph("Dots mark positive reported units. Red squares flag changed prices with zero units. "
              "The shaded meeting date and later observations are excluded from a pre-announcement study. "
              "Lines show raw reported prices, without probability normalization.", 297, 8.0, GREY, 11)

    text("3. A source inconsistency we must resolve", margin, 250, 10.5, NAVY, True)
    table([
        ["4 October", "Previous last", "New last", "Reported units"],
        ["FRdown1101", "0.550", "0.571", "0"],
        ["FRsame1101", "0.550", "0.485", "0"],
        ["FRup1101", "0.065", "0.002", "0"],
    ], 239, [130, 115, 110, usable - 355], [19, 17, 17, 17])
    paragraph("These values also appear in the cached source HTML. A zero in the volume field does "
              "not explain how the last-trade price changed. The audit flags the inconsistency instead "
              "of treating the row as fresh trading evidence.", 162, 8.5, leading=12)

    text("Next step", margin, 110, 10, NAVY, True)
    paragraph("Resolve the field inconsistency, then match a verified Fed funds futures contract and "
              "align daily observations. This one-market example cannot establish which market leads.", 100, 8.4, leading=12)
    text(f"Audit context: {summary['contracts']} contracts; 107 meeting-interval and 6 quarterly families.", margin, 59, 7.5, GREY)
    text("Sources: IEM prospectus and price archive; Federal Reserve 2001 calendar.", margin, 46, 7.2, GREY)
    pdf.linkURL(checks["pilot"]["definition_source"], (margin, 43, margin + 159, 55), relative=0)
    pdf.linkURL("https://iemweb.biz.uiowa.edu/iem_pricehistory/pricehistory/?Market_ID=51&Month=October&Year=2001",
                (margin + 159, 43, margin + 254, 55), relative=0)
    pdf.linkURL(checks["pilot"]["calendar_source"], (margin + 254, 43, width - margin, 55), relative=0)
    text("Prepared 19 September 2026. Validation example; no econometric model fitted.", margin, 30, 7, GREY)
    pdf.showPage()
    pdf.save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
