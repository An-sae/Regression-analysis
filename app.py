"""
Method Comparison Regression Tool
===================================
Supports Passing–Bablok and Deming (ordinary + weighted) regression.
Run with:  streamlit run app.py
"""

import sys, os
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from analysis.regression import passing_bablok
from analysis.deming     import deming, weighted_deming
from analysis.statistics import summary_stats
from plots.regression_plot import make_regression_plot, make_bland_altman_plot
from analysis.export import (
    results_to_csv, build_html_report, DPI_LABELS, dpi_from_label,
)
from plots.mpl_export import (
    render_pb_png, render_ba_png,
    mpl_fig_to_png_bytes, mpl_fig_to_svg_bytes,
)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Method Comparison Tool",
    page_icon="📊",
    layout="wide",
)

# ── Helpers ────────────────────────────────────────────────────────────────────

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


def _parse_axis(s):
    s = s.strip().replace(",", ".")
    return None if s == "" else (float(s) if s.replace(".","").replace("-","").isdigit() or s else None)


def _load_excel_sheet(file, sheet: str, header_row, x_col: str, y_col: str) -> tuple:
    """Load two columns from one sheet, honouring header choice."""
    header = 0 if header_row == "Yes (first row)" else None
    df = pd.read_excel(file, sheet_name=sheet, header=header)
    # If no header, columns are integers — let user pick by position label
    return df[x_col].values.astype(float), df[y_col].values.astype(float)


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("📊 Method Comparison")
    st.divider()

    # ── Regression method ─────────────────────────────────────────────────────
    st.subheader("Regression method")
    reg_method = st.selectbox(
        "Method",
        ["Passing–Bablok", "Deming (ordinary)", "Deming (weighted)"],
    )

    if reg_method.startswith("Deming"):
        error_ratio = st.number_input(
            "Error ratio λ = Var(y) / Var(x)",
            min_value=0.01, max_value=100.0, value=1.0, step=0.1,
            help=(
                "λ = 1.0 → equal error variances (orthogonal regression).\n"
                "For proportional errors use λ = (CV_candidate / CV_reference)²."
            ),
        )
        if reg_method == "Deming (weighted)":
            st.caption(
                "Weighted Deming uses weights ∝ 1/(x² + y²/λ), "
                "suitable when imprecision is proportional to concentration (constant CV)."
            )
    else:
        error_ratio = 1.0

    st.divider()

    # ── Data input ────────────────────────────────────────────────────────────
    st.subheader("Data input")
    input_mode = st.radio("Input method", ["📂 Upload file", "📋 Paste data"])

    uploaded_file = None
    pasted_text   = None
    x_raw_loaded  = None
    y_raw_loaded  = None
    load_error    = None

    if input_mode == "📂 Upload file":
        uploaded_file = st.file_uploader(
            "Upload CSV or Excel file", type=["csv", "xlsx", "xls"],
        )

        if uploaded_file is not None:
            try:
                fname = uploaded_file.name.lower()

                # ── Excel: sheet, header, column selectors ────────────────────
                if fname.endswith((".xlsx", ".xls")):
                    # Read sheet names without loading data
                    import openpyxl
                    from io import BytesIO
                    raw_bytes = uploaded_file.read()
                    uploaded_file.seek(0)

                    wb = openpyxl.load_workbook(BytesIO(raw_bytes), read_only=True, data_only=True)
                    sheet_names = wb.sheetnames
                    wb.close()

                    selected_sheet = st.selectbox("Sheet / tab", sheet_names)

                    header_choice = st.radio(
                        "Does the data have a header row?",
                        ["Yes (first row)", "No header"],
                        horizontal=True,
                    )
                    has_header = header_choice == "Yes (first row)"

                    # Preview the selected sheet
                    preview_df = pd.read_excel(
                        BytesIO(raw_bytes),
                        sheet_name=selected_sheet,
                        header=0 if has_header else None,
                        nrows=5,
                    )
                    # Normalise column names to strings for display
                    preview_df.columns = [str(c) for c in preview_df.columns]
                    st.caption("Preview (first 5 rows):")
                    st.dataframe(preview_df, use_container_width=True)

                    all_cols = [str(c) for c in preview_df.columns]
                    if len(all_cols) < 2:
                        st.error("Sheet must have at least 2 columns.")
                    else:
                        x_col_sel = st.selectbox("Reference method column (x)", all_cols, index=0)
                        y_col_sel = st.selectbox("Candidate method column (y)", all_cols,
                                                 index=min(1, len(all_cols)-1))

                        full_df = pd.read_excel(
                            BytesIO(raw_bytes),
                            sheet_name=selected_sheet,
                            header=0 if has_header else None,
                        )
                        full_df.columns = [str(c) for c in full_df.columns]
                        x_raw_loaded = pd.to_numeric(
                            full_df[x_col_sel].astype(str).str.replace(",", "."),
                            errors="coerce",
                        ).values.astype(float)
                        y_raw_loaded = pd.to_numeric(
                            full_df[y_col_sel].astype(str).str.replace(",", "."),
                            errors="coerce",
                        ).values.astype(float)

                # ── CSV ───────────────────────────────────────────────────────
                else:
                    header_choice = st.radio(
                        "Does the data have a header row?",
                        ["Yes (first row)", "No header"],
                        horizontal=True,
                    )
                    has_header = header_choice == "Yes (first row)"

                    raw_bytes = uploaded_file.read()
                    uploaded_file.seek(0)

                    csv_df = pd.read_csv(
                        BytesIO(raw_bytes),
                        header=0 if has_header else None,
                        sep=None, engine="python",
                        decimal=",",
                    )
                    if csv_df.select_dtypes(include=[np.number]).shape[1] < 2:
                        csv_df = pd.read_csv(
                            BytesIO(raw_bytes),
                            header=0 if has_header else None,
                            sep=None, engine="python",
                        )

                    csv_df.columns = [str(c) for c in csv_df.columns]
                    st.caption("Preview (first 5 rows):")
                    st.dataframe(csv_df.head(), use_container_width=True)

                    all_cols = [str(c) for c in csv_df.columns]
                    x_col_sel = st.selectbox("Reference method column (x)", all_cols, index=0)
                    y_col_sel = st.selectbox("Candidate method column (y)", all_cols,
                                             index=min(1, len(all_cols)-1))

                    x_raw_loaded = pd.to_numeric(
                        csv_df[x_col_sel].astype(str).str.replace(",", "."),
                        errors="coerce",
                    ).values.astype(float)
                    y_raw_loaded = pd.to_numeric(
                        csv_df[y_col_sel].astype(str).str.replace(",", "."),
                        errors="coerce",
                    ).values.astype(float)

            except Exception as e:
                load_error = str(e)

    else:
        st.markdown(
            "Copy two columns from Excel and paste below.  \n"
            "Comma **or** point accepted as decimal separator."
        )
        pasted_text = st.text_area(
            "Paste data here", height=180,
            placeholder="10,2\t10,5\n15,7\t16,1\n...",
        )

    st.divider()

    # ── Method names ──────────────────────────────────────────────────────────
    st.subheader("Method names")
    x_label = st.text_input("Reference method", value="Reference Method")
    y_label = st.text_input("Candidate method",  value="Candidate Method")

    st.divider()

    # ── Graph titles ──────────────────────────────────────────────────────────
    st.subheader("Graph titles")
    reg_default_title = {
        "Passing–Bablok":     "Passing–Bablok Method Comparison",
        "Deming (ordinary)":  "Deming Method Comparison",
        "Deming (weighted)":  "Weighted Deming Method Comparison",
    }[reg_method]

    pb_title       = st.text_input("Regression plot title", value=reg_default_title)
    ba_title_input = st.text_input("Bland–Altman title", value="",
                                   placeholder="Leave blank for auto")

    st.divider()

    # ── Decimal places ────────────────────────────────────────────────────────
    st.subheader("Decimal places")
    decimals = st.slider("Decimals in results", min_value=1, max_value=8, value=4)

    st.divider()

    # ── Axis ranges ───────────────────────────────────────────────────────────
    with st.expander("📐 Axis ranges"):
        st.markdown("**Regression plot axes** (blank = auto)")
        ac = st.columns(2)
        pb_xmin_str = ac[0].text_input("X min", value="0",  key="pb_xmin")
        pb_xmax_str = ac[1].text_input("X max", value="",   key="pb_xmax")
        pb_ymin_str = ac[0].text_input("Y min", value="0",  key="pb_ymin")
        pb_ymax_str = ac[1].text_input("Y max", value="",   key="pb_ymax")

        st.markdown("**Bland–Altman axes** (blank = auto)")
        bc = st.columns(2)
        ba_xmin_str = bc[0].text_input("X min", value="", key="ba_xmin")
        ba_xmax_str = bc[1].text_input("X max", value="", key="ba_xmax")
        ba_ymin_str = bc[0].text_input("Y min", value="", key="ba_ymin")
        ba_ymax_str = bc[1].text_input("Y max", value="", key="ba_ymax")

    def _pa(s):
        s = s.strip().replace(",", ".")
        if not s: return None
        try: return float(s)
        except: return None

    pb_x_min, pb_x_max = _pa(pb_xmin_str), _pa(pb_xmax_str)
    pb_y_min, pb_y_max = _pa(pb_ymin_str), _pa(pb_ymax_str)
    ba_x_min, ba_x_max = _pa(ba_xmin_str), _pa(ba_xmax_str)
    ba_y_min, ba_y_max = _pa(ba_ymin_str), _pa(ba_ymax_str)

    st.divider()

    # ── Bland–Altman mode ─────────────────────────────────────────────────────
    st.subheader("Bland–Altman Y-axis")
    ba_pct_diff = st.toggle("Show difference as % instead of absolute", value=False)

    st.divider()

    # ── Colours & legend ─────────────────────────────────────────────────────
    with st.expander("🎨 Graph colours & legend names"):
        st.markdown("**Regression plot**")
        pb_color_scatter    = st.color_picker("Scatter points",  "#2563EB", key="pb_cs")
        pb_color_identity   = st.color_picker("Identity line",   "#9CA3AF", key="pb_ci")
        pb_color_regression = st.color_picker("Regression line", "#DC2626", key="pb_cr")
        pb_legend_scatter    = st.text_input("Legend: scatter",    "Observations",     key="pb_ls")
        pb_legend_identity   = st.text_input("Legend: identity",   "Identity (y = x)", key="pb_li")
        pb_legend_regression = st.text_input("Legend: regression",
                                             reg_method.split(" ")[0] + " Regression", key="pb_lr")

        st.markdown("**Confidence interval band**")
        pb_show_ci   = st.toggle("Show 95% CI band", value=True, key="pb_show_ci")
        pb_color_ci  = st.color_picker("CI band colour", "#DC2626", key="pb_color_ci")
        pb_ci_alpha  = st.slider("CI transparency", 0.0, 1.0, 0.15, 0.01, key="pb_ci_alpha")
        pb_legend_ci = st.text_input("Legend: CI band", "95% CI", key="pb_lci")

        st.markdown("**Bland–Altman plot**")
        ba_color_scatter   = st.color_picker("Scatter points", "#2563EB", key="ba_cs")
        ba_color_mean      = st.color_picker("Mean bias line", "#DC2626", key="ba_cm")
        ba_color_loa       = st.color_picker("LoA lines",      "#F97316", key="ba_cl")
        ba_legend_scatter  = st.text_input("Legend: scatter",   "Difference", key="ba_ls")
        ba_label_mean      = st.text_input("Annotation: mean",  "Mean",       key="ba_lm")
        ba_label_loa_upper = st.text_input("Annotation: +LoA",  "+1,96 SD",   key="ba_lu")
        ba_label_loa_lower = st.text_input("Annotation: −LoA",  "−1,96 SD",   key="ba_ll")

    st.divider()
    st.caption("Passing & Bablok 1983 · Deming 1943 · Linnet 1990")


# ── Main area ──────────────────────────────────────────────────────────────────

method_label = reg_method
st.title(f"Method Comparison — {method_label}")

# ── Resolve data ───────────────────────────────────────────────────────────────

if load_error:
    st.error(f"Could not read file: {load_error}")
    st.stop()

if input_mode == "📂 Upload file":
    if uploaded_file is None:
        st.info("👈 Upload a CSV or Excel file in the sidebar to get started.")
        with st.expander("📄 Expected format"):
            st.dataframe(pd.DataFrame({
                "reference": [10.2, 15.7, 8.3],
                "candidate": [10.5, 16.1, 8.0],
            }), use_container_width=True)
        st.stop()

    if x_raw_loaded is None or y_raw_loaded is None:
        st.info("👈 Select the columns to use in the sidebar.")
        st.stop()

    x_raw = x_raw_loaded
    y_raw = y_raw_loaded

else:
    if not pasted_text or not pasted_text.strip():
        st.info("👈 Paste your data in the sidebar to get started.")
        st.stop()
    try:
        df_paste = parse_pasted(pasted_text)
    except ValueError as e:
        st.error(str(e)); st.stop()
    x_raw = df_paste["reference"].values
    y_raw = df_paste["candidate"].values
    st.success(f"✅ Parsed {len(df_paste)} rows from pasted data.")

# ── Data summary ───────────────────────────────────────────────────────────────

n_total   = len(x_raw)
n_missing = int(np.sum(~(np.isfinite(x_raw) & np.isfinite(y_raw))))
c1, c2, c3 = st.columns(3)
c1.metric("Total rows", n_total)
c2.metric("Missing / excluded", n_missing)
c3.metric("Valid pairs", n_total - n_missing)

# ── Analyze button ─────────────────────────────────────────────────────────────

if st.button("▶ Analyze", type="primary"):
    try:
        if reg_method == "Passing–Bablok":
            reg_res = passing_bablok(x_raw, y_raw)
        elif reg_method == "Deming (ordinary)":
            reg_res = deming(x_raw, y_raw, error_ratio=error_ratio)
        else:
            reg_res = weighted_deming(x_raw, y_raw, error_ratio=error_ratio)

        st.session_state["reg_res"]    = reg_res
        st.session_state["reg_method"] = reg_method
        st.session_state["stats"]      = summary_stats(x_raw, y_raw)
        st.session_state["x_raw"]      = x_raw.copy()
        st.session_state["y_raw"]      = y_raw.copy()
    except ValueError as e:
        st.error(f"Analysis failed: {e}"); st.stop()

if "reg_res" not in st.session_state:
    st.stop()

reg_res    = st.session_state["reg_res"]
stats      = st.session_state["stats"]
x_raw      = st.session_state["x_raw"]
y_raw      = st.session_state["y_raw"]
saved_method = st.session_state.get("reg_method", reg_method)

# ── Results table ──────────────────────────────────────────────────────────────

st.subheader(f"Results — {saved_method}")

results_df = pd.DataFrame([
    {"Statistic": "Slope",
     "Value": fmt(reg_res["slope"], decimals),
     "95% CI": f"[{fmt(reg_res['slope_lower'], decimals)} – {fmt(reg_res['slope_upper'], decimals)}]"},
    {"Statistic": "Intercept",
     "Value": fmt(reg_res["intercept"], decimals),
     "95% CI": f"[{fmt(reg_res['intercept_lower'], decimals)} – {fmt(reg_res['intercept_upper'], decimals)}]"},
    {"Statistic": "R²",            "Value": fmt(stats["r_squared"], decimals),  "95% CI": "—"},
    {"Statistic": "Pearson r",     "Value": fmt(stats["pearson_r"], decimals),  "95% CI": "—"},
    {"Statistic": "Bias",          "Value": fmt(stats["bias"], decimals),       "95% CI": "—"},
    {"Statistic": "LoA lower",     "Value": fmt(stats["loa_lower"], decimals),  "95% CI": "—"},
    {"Statistic": "LoA upper",     "Value": fmt(stats["loa_upper"], decimals),  "95% CI": "—"},
])
st.dataframe(results_df, use_container_width=True, hide_index=True)

# ── Plots ──────────────────────────────────────────────────────────────────────

col_pb, col_ba = st.columns(2)

with col_pb:
    fig_pb = make_regression_plot(
        x_raw, y_raw,
        slope=reg_res["slope"], intercept=reg_res["intercept"],
        slope_lower=reg_res["slope_lower"], slope_upper=reg_res["slope_upper"],
        intercept_lower=reg_res["intercept_lower"], intercept_upper=reg_res["intercept_upper"],
        r_squared=stats["r_squared"],
        x_label=x_label, y_label=y_label, title=pb_title,
        color_scatter=pb_color_scatter, color_identity=pb_color_identity,
        color_regression=pb_color_regression, color_ci=pb_color_ci,
        ci_alpha=pb_ci_alpha, show_ci=pb_show_ci,
        legend_scatter=pb_legend_scatter, legend_identity=pb_legend_identity,
        legend_regression=pb_legend_regression, legend_ci=pb_legend_ci,
        x_min=pb_x_min, x_max=pb_x_max, y_min=pb_y_min, y_max=pb_y_max,
        decimals=decimals,
    )
    st.plotly_chart(fig_pb, use_container_width=True)

with col_ba:
    fig_ba = make_bland_altman_plot(
        x_raw, y_raw,
        mean_diff=stats["mean_diff"], loa_lower=stats["loa_lower"], loa_upper=stats["loa_upper"],
        x_label=x_label, y_label=y_label, title=ba_title_input, pct_diff=ba_pct_diff,
        color_scatter=ba_color_scatter, color_mean=ba_color_mean, color_loa=ba_color_loa,
        legend_scatter=ba_legend_scatter, label_mean=ba_label_mean,
        label_loa_upper=ba_label_loa_upper, label_loa_lower=ba_label_loa_lower,
        x_min=ba_x_min, x_max=ba_x_max, y_min=ba_y_min, y_max=ba_y_max,
        decimals=decimals,
    )
    st.plotly_chart(fig_ba, use_container_width=True)

# ── Export ──────────────────────────────────────────────────────────────────────

st.subheader("Export")

with st.expander("⚙️ Image resolution & size", expanded=True):
    res_col, w_col, h_col = st.columns(3)
    dpi_label  = res_col.selectbox("Resolution", DPI_LABELS, index=1)
    img_width  = w_col.number_input("Width (px)",  400, 6000, 1400, 100)
    img_height = h_col.number_input("Height (px)", 300, 6000, 1040, 100)
    dpi = dpi_from_label(dpi_label)
    st.caption(
        f"Output: **{img_width} × {img_height} px** at **{dpi} dpi** — "
        f"≈ **{img_width/dpi*2.54:.1f} × {img_height/dpi*2.54:.1f} cm** printed. "
        "SVG scales without quality loss."
    )

_pb_kw = dict(
    slope=reg_res["slope"], intercept=reg_res["intercept"],
    slope_lower=reg_res["slope_lower"], slope_upper=reg_res["slope_upper"],
    intercept_lower=reg_res["intercept_lower"], intercept_upper=reg_res["intercept_upper"],
    r_squared=stats["r_squared"],
    x_label=x_label, y_label=y_label, title=pb_title,
    color_scatter=pb_color_scatter, color_identity=pb_color_identity,
    color_regression=pb_color_regression, color_ci=pb_color_ci,
    ci_alpha=pb_ci_alpha, show_ci=pb_show_ci,
    legend_scatter=pb_legend_scatter, legend_identity=pb_legend_identity,
    legend_regression=pb_legend_regression, legend_ci=pb_legend_ci,
    x_min=pb_x_min, x_max=pb_x_max, y_min=pb_y_min, y_max=pb_y_max,
    decimals=decimals,
)

_ba_kw = dict(
    mean_diff=stats["mean_diff"], loa_lower=stats["loa_lower"], loa_upper=stats["loa_upper"],
    x_label=x_label, y_label=y_label, title=ba_title_input, pct_diff=ba_pct_diff,
    color_scatter=ba_color_scatter, color_mean=ba_color_mean, color_loa=ba_color_loa,
    legend_scatter=ba_legend_scatter, label_mean=ba_label_mean,
    label_loa_upper=ba_label_loa_upper, label_loa_lower=ba_label_loa_lower,
    x_min=ba_x_min, x_max=ba_x_max, y_min=ba_y_min, y_max=ba_y_max,
    decimals=decimals,
)

for render_fn, kw, lbl, slug in [
    (render_pb_png, _pb_kw, "Regression plot", "reg"),
    (render_ba_png, _ba_kw, "Bland–Altman plot", "ba"),
]:
    st.markdown(f"**{lbl}**")
    c1, c2, _ = st.columns([1, 1, 2])
    mf1 = render_fn(x_raw, y_raw, dpi=dpi, width_px=int(img_width), height_px=int(img_height), **kw)
    mf2 = render_fn(x_raw, y_raw, dpi=dpi, width_px=int(img_width), height_px=int(img_height), **kw)
    c1.download_button(f"🖼 PNG ({dpi} dpi)", mpl_fig_to_png_bytes(mf1, dpi=dpi),
                       f"{slug}_{dpi}dpi.png", "image/png", key=f"dl_png_{slug}")
    c2.download_button("📐 SVG (vector)", mpl_fig_to_svg_bytes(mf2),
                       f"{slug}.svg", "image/svg+xml", key=f"dl_svg_{slug}")

st.divider()
st.markdown("**Results data & full report**")
r1, r2, _ = st.columns([1, 1, 2])
r1.download_button("📥 Results CSV", results_to_csv(reg_res, stats),
                   "results.csv", "text/csv", key="dl_csv")
r2.download_button("📄 HTML Report", build_html_report(reg_res, stats, fig_pb, fig_ba,
                   x_label=x_label, y_label=y_label),
                   "report.html", "text/html", key="dl_html")
