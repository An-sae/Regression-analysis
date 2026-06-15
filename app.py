"""
Passing–Bablok Regression Tool
================================
Run with:  streamlit run app.py
"""

import sys
import os

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from analysis.regression import passing_bablok
from analysis.statistics import summary_stats
from plots.regression_plot import make_regression_plot, make_bland_altman_plot
from analysis.export import (
    results_to_csv, build_html_report, DPI_LABELS, dpi_from_label,
)
from plots.mpl_export import (
    render_pb_png, render_ba_png,
    mpl_fig_to_png_bytes, mpl_fig_to_svg_bytes,
)


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Passing–Bablok Regression",
    page_icon="📊",
    layout="wide",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_pasted(text: str) -> pd.DataFrame:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    rows = []
    for line in lines:
        if "\t" in line:
            parts = line.split("\t")
        elif ";" in line:
            parts = line.split(";")
        else:
            parts = line.split()
        if len(parts) < 2:
            continue
        try:
            a = float(parts[0].replace(",", "."))
            b = float(parts[1].replace(",", "."))
            rows.append((a, b))
        except ValueError:
            continue
    if not rows:
        raise ValueError("No numeric rows found. Check that your data has two columns of numbers.")
    return pd.DataFrame(rows, columns=["reference", "candidate"])


def fmt(v, decimals):
    return f"{v:.{decimals}f}".replace(".", ",")


def _num_input(label, default_val, key):
    """A number input that accepts both comma and point as decimal."""
    raw = st.text_input(label, value=str(default_val).replace(".", ","), key=key)
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return default_val


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("📊 PB Regression Tool")
    st.markdown(
        "Passing–Bablok regression is a robust, non-parametric method "
        "for comparing two analytical measurement methods."
    )
    st.divider()

    # ── Data input ────────────────────────────────────────────────────────────
    input_mode = st.radio("Data input method", ["📂 Upload file", "📋 Paste data"])

    uploaded_file = None
    pasted_text   = None

    if input_mode == "📂 Upload file":
        uploaded_file = st.file_uploader(
            "Upload CSV or Excel file", type=["csv", "xlsx", "xls"],
        )
    else:
        st.markdown(
            "Copy two columns from Excel and paste below.  \n"
            "Comma **or** point accepted as decimal separator."
        )
        pasted_text = st.text_area(
            "Paste data here", height=200,
            placeholder="10,2\t10,5\n15,7\t16,1\n...",
        )

    st.divider()

    # ── Method names ──────────────────────────────────────────────────────────
    st.subheader("Method names")
    x_label = st.text_input("Reference method", value="Reference Method")
    y_label = st.text_input("Candidate method", value="Candidate Method")

    st.divider()

    # ── Graph titles ──────────────────────────────────────────────────────────
    st.subheader("Graph titles")
    pb_title = st.text_input("Passing–Bablok title",
                              value="Passing–Bablok Method Comparison")
    ba_title_input = st.text_input("Bland–Altman title",
                                   value="",
                                   placeholder="Leave blank for auto (adds % if % mode on)")

    st.divider()

    # ── Decimal places ────────────────────────────────────────────────────────
    st.subheader("Decimal places")
    decimals = st.slider("Number of decimals in results", min_value=1, max_value=8, value=4)

    st.divider()

    # ── Axis ranges ───────────────────────────────────────────────────────────
    with st.expander("📐 Axis ranges"):
        st.markdown("**Passing–Bablok axes** (leave blank for auto)")
        pb_ax_cols = st.columns(2)
        pb_xmin_str = pb_ax_cols[0].text_input("X min", value="0",  key="pb_xmin")
        pb_xmax_str = pb_ax_cols[1].text_input("X max", value="",   key="pb_xmax")
        pb_ymin_str = pb_ax_cols[0].text_input("Y min", value="0",  key="pb_ymin")
        pb_ymax_str = pb_ax_cols[1].text_input("Y max", value="",   key="pb_ymax")

        st.markdown("**Bland–Altman axes** (leave blank for auto)")
        ba_ax_cols = st.columns(2)
        ba_xmin_str = ba_ax_cols[0].text_input("X min", value="", key="ba_xmin")
        ba_xmax_str = ba_ax_cols[1].text_input("X max", value="", key="ba_xmax")
        ba_ymin_str = ba_ax_cols[0].text_input("Y min", value="", key="ba_ymin")
        ba_ymax_str = ba_ax_cols[1].text_input("Y max", value="", key="ba_ymax")

    def _parse_axis(s):
        """Return float if non-empty, else None."""
        s = s.strip().replace(",", ".")
        if s == "":
            return None
        try:
            return float(s)
        except ValueError:
            return None

    pb_x_min = _parse_axis(pb_xmin_str)
    pb_x_max = _parse_axis(pb_xmax_str)
    pb_y_min = _parse_axis(pb_ymin_str)
    pb_y_max = _parse_axis(pb_ymax_str)

    ba_x_min = _parse_axis(ba_xmin_str)
    ba_x_max = _parse_axis(ba_xmax_str)
    ba_y_min = _parse_axis(ba_ymin_str)
    ba_y_max = _parse_axis(ba_ymax_str)

    st.divider()

    # ── Bland–Altman y-axis mode ──────────────────────────────────────────────
    st.subheader("Bland–Altman Y-axis")
    ba_pct_diff = st.toggle(
        "Show difference as % instead of absolute",
        value=False,
        help="Y-axis shows (candidate − reference) / mean × 100 %",
    )

    st.divider()

    # ── Colour & legend settings ──────────────────────────────────────────────
    with st.expander("🎨 Graph colours & legend names"):

        st.markdown("**Passing–Bablok plot**")
        pb_color_scatter    = st.color_picker("Scatter points",  "#2563EB", key="pb_cs")
        pb_color_identity   = st.color_picker("Identity line",   "#9CA3AF", key="pb_ci")
        pb_color_regression = st.color_picker("Regression line", "#DC2626", key="pb_cr")

        pb_legend_scatter    = st.text_input("Legend: scatter",    "Observations",     key="pb_ls")
        pb_legend_identity   = st.text_input("Legend: identity",   "Identity (y = x)", key="pb_li")
        pb_legend_regression = st.text_input("Legend: regression", "PB Regression",    key="pb_lr")

        st.markdown("**Confidence interval band**")
        pb_show_ci    = st.toggle("Show 95% CI band", value=True, key="pb_show_ci")
        pb_color_ci   = st.color_picker("CI band colour", "#DC2626", key="pb_color_ci")
        pb_ci_alpha   = st.slider("CI band transparency (0 = invisible, 1 = solid)",
                                  min_value=0.0, max_value=1.0, value=0.15, step=0.01,
                                  key="pb_ci_alpha")
        pb_legend_ci  = st.text_input("Legend: CI band", "95% CI", key="pb_lci")

        st.markdown("**Bland–Altman plot**")
        ba_color_scatter = st.color_picker("Scatter points", "#2563EB", key="ba_cs")
        ba_color_mean    = st.color_picker("Mean bias line", "#DC2626", key="ba_cm")
        ba_color_loa     = st.color_picker("LoA lines",      "#F97316", key="ba_cl")

        ba_legend_scatter  = st.text_input("Legend: scatter",   "Difference", key="ba_ls")
        ba_label_mean      = st.text_input("Annotation: mean",  "Mean",       key="ba_lm")
        ba_label_loa_upper = st.text_input("Annotation: +LoA",  "+1,96 SD",   key="ba_lu")
        ba_label_loa_lower = st.text_input("Annotation: −LoA",  "−1,96 SD",   key="ba_ll")

    st.divider()
    st.caption("Passing & Bablok, J Clin Chem Clin Biochem, 1983")


# ── Main area ─────────────────────────────────────────────────────────────────

st.title("Passing–Bablok Method Comparison")

# ── Load data ─────────────────────────────────────────────────────────────────

if input_mode == "📂 Upload file":
    if uploaded_file is None:
        st.info("👈 Upload a CSV or Excel file in the sidebar to get started.")
        with st.expander("📄 Expected data format"):
            st.dataframe(pd.DataFrame({
                "reference": [10.2, 15.7, 8.3],
                "candidate": [10.5, 16.1, 8.0],
            }), use_container_width=True)
        st.stop()

    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, decimal=",", sep=None, engine="python")
            if len(df.select_dtypes(include=[np.number]).columns) < 2:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Could not read file: {e}")
        st.stop()

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) < 2:
        st.error("Your file must contain at least two numeric columns.")
        st.stop()

    c1, c2 = st.columns(2)
    with c1:
        x_col = st.selectbox("Reference method column (x)", numeric_cols, index=0)
    with c2:
        y_col = st.selectbox("Candidate method column (y)", numeric_cols,
                             index=min(1, len(numeric_cols) - 1))

    x_raw = df[x_col].values.astype(float)
    y_raw = df[y_col].values.astype(float)

else:
    if not pasted_text or not pasted_text.strip():
        st.info("👈 Paste your data in the sidebar to get started.")
        with st.expander("📄 Expected format"):
            st.markdown(
                "Two columns per row, tab- or semicolon-separated.  \n"
                "Comma or point accepted as decimal.  \n\n"
                "```\n10,2\t10,5\n15,7\t16,1\n8,3\t8,0\n```"
            )
        st.stop()

    try:
        df = parse_pasted(pasted_text)
    except ValueError as e:
        st.error(str(e))
        st.stop()

    x_raw = df["reference"].values
    y_raw = df["candidate"].values
    st.success(f"✅ Parsed {len(df)} rows from pasted data.")


# ── Data summary ──────────────────────────────────────────────────────────────

n_total   = len(x_raw)
n_missing = int(np.sum(~(np.isfinite(x_raw) & np.isfinite(y_raw))))

c1, c2, c3 = st.columns(3)
c1.metric("Total rows", n_total)
c2.metric("Missing / excluded", n_missing)
c3.metric("Valid pairs", n_total - n_missing)

# ── Analyze button — results stored in session_state so widget changes
#    (DPI, colours, axis ranges, decimals) never wipe the analysis. ────────────

if st.button("▶ Analyze", type="primary"):
    try:
        st.session_state["pb"]    = passing_bablok(x_raw, y_raw)
        st.session_state["stats"] = summary_stats(x_raw, y_raw)
        st.session_state["x_raw"] = x_raw.copy()
        st.session_state["y_raw"] = y_raw.copy()
    except ValueError as e:
        st.error(f"Analysis failed: {e}")
        st.stop()

if "pb" not in st.session_state:
    st.stop()

pb    = st.session_state["pb"]
stats = st.session_state["stats"]
x_raw = st.session_state["x_raw"]
y_raw = st.session_state["y_raw"]

# ── Results table ─────────────────────────────────────────────────────────────

st.subheader("Results")

results_df = pd.DataFrame([
    {"Statistic": "Slope",
     "Value": fmt(pb["slope"], decimals),
     "95% CI": f"[{fmt(pb['slope_lower'], decimals)} – {fmt(pb['slope_upper'], decimals)}]"},
    {"Statistic": "Intercept",
     "Value": fmt(pb["intercept"], decimals),
     "95% CI": f"[{fmt(pb['intercept_lower'], decimals)} – {fmt(pb['intercept_upper'], decimals)}]"},
    {"Statistic": "R²",
     "Value": fmt(stats["r_squared"], decimals), "95% CI": "—"},
    {"Statistic": "Pearson r",
     "Value": fmt(stats["pearson_r"], decimals), "95% CI": "—"},
    {"Statistic": "Bias (mean diff)",
     "Value": fmt(stats["bias"], decimals), "95% CI": "—"},
    {"Statistic": "LoA lower (−1,96 SD)",
     "Value": fmt(stats["loa_lower"], decimals), "95% CI": "—"},
    {"Statistic": "LoA upper (+1,96 SD)",
     "Value": fmt(stats["loa_upper"], decimals), "95% CI": "—"},
])

st.dataframe(results_df, use_container_width=True, hide_index=True)

# ── Plots side by side ────────────────────────────────────────────────────────

col_pb, col_ba = st.columns(2)

with col_pb:
    fig_pb = make_regression_plot(
        x_raw, y_raw,
        slope=pb["slope"],
        intercept=pb["intercept"],
        slope_lower=pb["slope_lower"],
        slope_upper=pb["slope_upper"],
        intercept_lower=pb["intercept_lower"],
        intercept_upper=pb["intercept_upper"],
        r_squared=stats["r_squared"],
        x_label=x_label,
        y_label=y_label,
        title=pb_title,
        color_scatter=pb_color_scatter,
        color_identity=pb_color_identity,
        color_regression=pb_color_regression,
        color_ci=pb_color_ci,
        ci_alpha=pb_ci_alpha,
        show_ci=pb_show_ci,
        legend_scatter=pb_legend_scatter,
        legend_identity=pb_legend_identity,
        legend_regression=pb_legend_regression,
        legend_ci=pb_legend_ci,
        x_min=pb_x_min,
        x_max=pb_x_max,
        y_min=pb_y_min,
        y_max=pb_y_max,
        decimals=decimals,
    )
    st.plotly_chart(fig_pb, use_container_width=True)

with col_ba:
    fig_ba = make_bland_altman_plot(
        x_raw, y_raw,
        mean_diff=stats["mean_diff"],
        loa_lower=stats["loa_lower"],
        loa_upper=stats["loa_upper"],
        x_label=x_label,
        y_label=y_label,
        title=ba_title_input,
        pct_diff=ba_pct_diff,
        color_scatter=ba_color_scatter,
        color_mean=ba_color_mean,
        color_loa=ba_color_loa,
        legend_scatter=ba_legend_scatter,
        label_mean=ba_label_mean,
        label_loa_upper=ba_label_loa_upper,
        label_loa_lower=ba_label_loa_lower,
        x_min=ba_x_min,
        x_max=ba_x_max,
        y_min=ba_y_min,
        y_max=ba_y_max,
        decimals=decimals,
    )
    st.plotly_chart(fig_ba, use_container_width=True)

# ── Export ────────────────────────────────────────────────────────────────────

st.subheader("Export")

with st.expander("⚙️ Image resolution & size", expanded=True):
    res_col, w_col, h_col = st.columns(3)
    dpi_label  = res_col.selectbox(
        "Resolution", DPI_LABELS, index=1,
        help="300 dpi is standard for Word/PowerPoint. 600 dpi for journal submission.",
    )
    img_width  = w_col.number_input("Width (px)",  min_value=400, max_value=6000, value=1400, step=100)
    img_height = h_col.number_input("Height (px)", min_value=300, max_value=6000, value=1040, step=100)
    dpi = dpi_from_label(dpi_label)
    st.caption(
        f"Output: **{img_width} × {img_height} px** at **{dpi} dpi** — "
        f"≈ **{img_width/dpi*2.54:.1f} × {img_height/dpi*2.54:.1f} cm** printed. "
        "SVG is vector and scales to any size without quality loss."
    )

# Shared kwargs passed to both renderers
_pb_kwargs = dict(
    slope=pb["slope"], intercept=pb["intercept"],
    slope_lower=pb["slope_lower"], slope_upper=pb["slope_upper"],
    intercept_lower=pb["intercept_lower"], intercept_upper=pb["intercept_upper"],
    r_squared=stats["r_squared"],
    x_label=x_label, y_label=y_label,
    title=pb_title,
    color_scatter=pb_color_scatter, color_identity=pb_color_identity,
    color_regression=pb_color_regression, color_ci=pb_color_ci,
    ci_alpha=pb_ci_alpha, show_ci=pb_show_ci,
    legend_scatter=pb_legend_scatter, legend_identity=pb_legend_identity,
    legend_regression=pb_legend_regression, legend_ci=pb_legend_ci,
    x_min=pb_x_min, x_max=pb_x_max, y_min=pb_y_min, y_max=pb_y_max,
    decimals=decimals,
)

_ba_kwargs = dict(
    mean_diff=stats["mean_diff"], loa_lower=stats["loa_lower"], loa_upper=stats["loa_upper"],
    x_label=x_label, y_label=y_label,
    title=ba_title_input,
    pct_diff=ba_pct_diff,
    color_scatter=ba_color_scatter, color_mean=ba_color_mean, color_loa=ba_color_loa,
    legend_scatter=ba_legend_scatter, label_mean=ba_label_mean,
    label_loa_upper=ba_label_loa_upper, label_loa_lower=ba_label_loa_lower,
    x_min=ba_x_min, x_max=ba_x_max, y_min=ba_y_min, y_max=ba_y_max,
    decimals=decimals,
)

for render_fn, kwargs, label, slug in [
    (render_pb_png, _pb_kwargs, "Passing–Bablok plot", "pb"),
    (render_ba_png, _ba_kwargs, "Bland–Altman plot",   "ba"),
]:
    st.markdown(f"**{label}**")
    c_png, c_svg, _ = st.columns([1, 1, 2])

    mpl_fig = render_fn(x_raw, y_raw, dpi=dpi,
                        width_px=int(img_width), height_px=int(img_height),
                        **kwargs)

    c_png.download_button(
        label=f"🖼 PNG  ({dpi} dpi)",
        data=mpl_fig_to_png_bytes(mpl_fig, dpi=dpi),
        file_name=f"{slug}_plot_{dpi}dpi.png",
        mime="image/png",
        key=f"dl_png_{slug}",
    )

    mpl_fig2 = render_fn(x_raw, y_raw, dpi=dpi,
                         width_px=int(img_width), height_px=int(img_height),
                         **kwargs)
    c_svg.download_button(
        label="📐 SVG  (vector)",
        data=mpl_fig_to_svg_bytes(mpl_fig2),
        file_name=f"{slug}_plot.svg",
        mime="image/svg+xml",
        key=f"dl_svg_{slug}",
    )

st.divider()

st.markdown("**Results data & full report**")
rep_col1, rep_col2, _ = st.columns([1, 1, 2])

csv_str = results_to_csv(pb, stats)
rep_col1.download_button(
    "📥 Results CSV", data=csv_str,
    file_name="pb_results.csv", mime="text/csv", key="dl_csv",
)

html_report = build_html_report(pb, stats, fig_pb, fig_ba,
                                x_label=x_label, y_label=y_label)
rep_col2.download_button(
    "📄 HTML Report (both plots)", data=html_report,
    file_name="pb_report.html", mime="text/html", key="dl_html",
)
