"""
Export Module
=============
Exports results to CSV, high-resolution PNG, SVG, and a self-contained HTML report.

PNG DPI mapping (Plotly uses a 700×520 px base canvas at scale=1):
    scale = desired_dpi / 96  (96 is Plotly's assumed screen DPI)
    150 dpi  → scale ≈ 1.56   (good screen / presentation quality)
    300 dpi  → scale ≈ 3.13   (print / Word / PowerPoint standard)
    600 dpi  → scale ≈ 6.25   (journal submission quality)
"""

import re
import copy
from typing import Dict
import pandas as pd


# ── PNG / SVG ─────────────────────────────────────────────────────────────────

_DPI_PRESETS = {
    "150 dpi  (screen / presentation)": 150,
    "300 dpi  (print / Word / PowerPoint)": 300,
    "600 dpi  (journal / high-end print)": 600,
}

DPI_LABELS = list(_DPI_PRESETS.keys())


def _strip_html_tags(text: str) -> str:
    """Remove all HTML tags from a string (e.g. <b>, <br>)."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def _sanitize_fig(fig):
    """
    Return a deep copy of fig with all HTML stripped from annotation text.
    Kaleido's headless renderer crashes on <b>, <br> etc. in annotation boxes.
    The interactive on-screen version keeps the HTML; only the export copy is cleaned.
    """
    fig_copy = copy.deepcopy(fig)
    for ann in fig_copy.layout.annotations:
        if ann.text:
            ann.text = _strip_html_tags(ann.text)
            # Switch to a plain font for the export — bold via weight instead of <b>
            if ann.font:
                ann.font.update({"weight": "bold"})
    return fig_copy


def fig_to_png_bytes(fig, dpi: int = 300, width_px: int = 1400, height_px: int = 1040) -> bytes:
    """Render a Plotly figure to PNG bytes at a given DPI."""
    scale = dpi / 96.0
    return _sanitize_fig(fig).to_image(
        format="png",
        width=width_px,
        height=height_px,
        scale=scale,
    )


def dpi_from_label(label: str) -> int:
    return _DPI_PRESETS.get(label, 300)


def fig_to_svg_bytes(fig, width_px: int = 1400, height_px: int = 1040) -> bytes:
    """Render a Plotly figure to SVG — vector, infinitely scalable."""
    return _sanitize_fig(fig).to_image(
        format="svg",
        width=width_px,
        height=height_px,
    )


# ── CSV ───────────────────────────────────────────────────────────────────────

def results_to_csv(pb_results: Dict, stats: Dict) -> str:
    rows = [
        ("Slope",             pb_results["slope"]),
        ("Slope CI Lower",    pb_results["slope_lower"]),
        ("Slope CI Upper",    pb_results["slope_upper"]),
        ("Intercept",         pb_results["intercept"]),
        ("Intercept CI Lower", pb_results["intercept_lower"]),
        ("Intercept CI Upper", pb_results["intercept_upper"]),
        ("R²",                stats["r_squared"]),
        ("Pearson r",         stats["pearson_r"]),
        ("Bias (mean diff)",  stats["bias"]),
        ("LoA Lower",         stats["loa_lower"]),
        ("LoA Upper",         stats["loa_upper"]),
        ("N (valid)",         pb_results["n"]),
        ("N (excluded)",      pb_results["n_excluded"]),
    ]
    df = pd.DataFrame(rows, columns=["Statistic", "Value"])
    return df.to_csv(index=False)


# ── HTML report ───────────────────────────────────────────────────────────────

def build_html_report(
    pb_results: Dict,
    stats: Dict,
    fig_pb,
    fig_ba=None,
    x_label: str = "Reference Method",
    y_label: str = "Candidate Method",
) -> str:
    def _fig_html(fig):
        try:
            return fig.to_html(full_html=False, include_plotlyjs="cdn")
        except Exception:
            return "<p><em>Figure could not be rendered.</em></p>"

    fig_pb_html = _fig_html(fig_pb)
    fig_ba_html = _fig_html(fig_ba) if fig_ba is not None else ""

    rows_html = ""
    table_data = [
        ("Slope",                  f"{pb_results['slope']:.6f}"),
        ("Slope 95% CI",           f"[{pb_results['slope_lower']:.6f}, {pb_results['slope_upper']:.6f}]"),
        ("Intercept",              f"{pb_results['intercept']:.6f}"),
        ("Intercept 95% CI",       f"[{pb_results['intercept_lower']:.6f}, {pb_results['intercept_upper']:.6f}]"),
        ("R²",                     f"{stats['r_squared']:.6f}"),
        ("Pearson r",              f"{stats['pearson_r']:.6f}"),
        ("Bias",                   f"{stats['bias']:.6f}"),
        ("LoA (±1.96 SD)",         f"[{stats['loa_lower']:.6f}, {stats['loa_upper']:.6f}]"),
        ("Valid observations (n)", str(pb_results["n"])),
        ("Excluded (NaN)",         str(pb_results["n_excluded"])),
    ]
    for stat, val in table_data:
        rows_html += f"  <tr><td>{stat}</td><td>{val}</td></tr>\n"

    ba_section = f"""
<div class="fig">
<h2>Bland–Altman Plot</h2>
{fig_ba_html}
</div>""" if fig_ba_html else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Passing–Bablok Method Comparison Report</title>
<style>
  body {{ font-family: Inter, Arial, sans-serif; max-width: 960px; margin: 40px auto; padding: 0 20px; color: #111; }}
  h1 {{ font-size: 1.6rem; border-bottom: 2px solid #2563EB; padding-bottom: 8px; }}
  h2 {{ font-size: 1.1rem; color: #374151; margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 0.5rem; }}
  th, td {{ padding: 8px 14px; text-align: left; border-bottom: 1px solid #E5E7EB; }}
  th {{ background: #F9FAFB; font-weight: 600; }}
  td:last-child {{ font-family: Courier New, monospace; }}
  .fig {{ margin-top: 2rem; }}
  footer {{ margin-top: 3rem; font-size: 0.8rem; color: #9CA3AF; }}
</style>
</head>
<body>
<h1>Passing–Bablok Method Comparison Report</h1>
<p><strong>Reference:</strong> {x_label} &nbsp;|&nbsp; <strong>Candidate:</strong> {y_label}</p>

<h2>Statistical Results</h2>
<table>
  <thead><tr><th>Statistic</th><th>Value</th></tr></thead>
  <tbody>
{rows_html}  </tbody>
</table>

<div class="fig">
<h2>Passing–Bablok Plot</h2>
{fig_pb_html}
</div>
{ba_section}
<footer>Generated by Passing–Bablok Regression Tool</footer>
</body>
</html>"""
