"""
Method Comparison Tool
Four analysis types: Passing-Bablok | Deming | Confusion Matrix | Precision (EP15-A3)
Run with:  streamlit run app.py
"""
import sys, os
from io import BytesIO
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from analysis.regression import passing_bablok
from analysis.deming     import deming, weighted_deming
from analysis.statistics import summary_stats
from plots.regression_plot import make_regression_plot, make_bland_altman_plot
from analysis.export import results_to_csv, build_html_report, DPI_LABELS, dpi_from_label
from plots.mpl_export import (
    render_pb_png, render_ba_png, mpl_fig_to_png_bytes, mpl_fig_to_svg_bytes,
)
from analysis.confusion import build_count_matrix, essential_agreement, categorical_agreement
from plots.confusion_plot import make_confusion_plot, render_confusion_png
from analysis.precision import compute_precision, precision_from_dataframe

st.set_page_config(page_title="Method Comparison Tool", page_icon="📊", layout="wide")

# ── pure helpers ───────────────────────────────────────────────────────────────
def parse_pasted(text):
    rows = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line: continue
        parts = line.split("\t") if "\t" in line else (
                line.split(";")  if ";" in line else line.split())
        if len(parts) < 2: continue
        try:
            rows.append((float(parts[0].replace(",",".")),
                         float(parts[1].replace(",","."))))
        except ValueError:
            continue
    if not rows: raise ValueError("No numeric rows found.")
    return pd.DataFrame(rows, columns=["reference","candidate"])

def fmt(v, d): return f"{v:.{d}f}".replace(".","," )
def _pa(s):
    s=str(s).strip().replace(",",".")
    if not s: return None
    try:    return float(s)
    except: return None
def _ca(s):
    v=_pa(s); return None if v is None else int(v)

def _apply_filter(df, exclude_cols, key_prefix):
    """
    Show optional row-filter UI for categorical columns.
    Returns a filtered copy of df (or original if no filter applied).
    exclude_cols: column names already used as x/y (skip those).
    key_prefix: unique string to avoid widget key collisions.
    """
    # Find columns that are text/categorical and have reasonable cardinality.
    # Accept both 'object' and 'str' (StringDtype) dtypes.
    cat_cols = []
    for c in df.columns:
        if c in exclude_cols:
            continue
        try:
            is_text = (df[c].dtype == object or
                       pd.api.types.is_string_dtype(df[c]) or
                       str(df[c].dtype) in ("string","object"))
        except Exception:
            is_text = False
        if is_text:
            n_unique = df[c].nunique(dropna=True)
            if 1 < n_unique <= 200:
                cat_cols.append(c)

    if not cat_cols:
        return df   # nothing to filter on

    st.markdown("**Filter rows (optional)**")
    filter_col = st.selectbox(
        "Filter by column", ["— no filter —"] + cat_cols,
        key=f"{key_prefix}_fcol",
    )
    if filter_col == "— no filter —":
        return df

    unique_vals = sorted(df[filter_col].dropna().unique().tolist(), key=str)
    selected = st.multiselect(
        f"Keep rows where {filter_col} =",
        options=unique_vals,
        default=unique_vals,   # all selected by default — never crashes
        key=f"{key_prefix}_fval",
    )
    if not selected:
        st.warning("No values selected — using all rows.")
        return df

    filtered = df[df[filter_col].isin(selected)].copy()
    n_kept   = len(filtered)
    n_total  = len(df)
    preview  = ", ".join(str(v) for v in selected[:3])
    if len(selected) > 3:
        preview += f" … (+{len(selected)-3} more)"
    st.caption(f"Using **{n_kept}** of {n_total} rows — {filter_col}: {preview}")
    return filtered


    df=pd.read_excel(BytesIO(raw), sheet_name=sheet, header=0 if hdr else None)
    df.columns=[str(c) for c in df.columns]
    def _col(c): return pd.to_numeric(df[c].astype(str).str.replace(",","."),errors="coerce").values.astype(float)
    return _col(xc), _col(yc)

def _read_csv(raw, hdr, xc, yc):
    kw=dict(header=0 if hdr else None, sep=None, engine="python")
    df=pd.read_csv(BytesIO(raw), decimal=",", **kw)
    if df.select_dtypes(include=[np.number]).shape[1]<2:
        df=pd.read_csv(BytesIO(raw), **kw)
    df.columns=[str(c) for c in df.columns]
    def _col(c): return pd.to_numeric(df[c].astype(str).str.replace(",","."),errors="coerce").values.astype(float)
    return _col(xc), _col(yc)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — all variables always defined with safe defaults
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("📊 Method Comparison")
    st.divider()

    st.subheader("Analysis type")
    analysis_type = st.selectbox("Choose analysis",
        ["Passing–Bablok","Deming","Confusion Matrix","Precision Evaluation (EP15-A3)"],
        key="analysis_type")

    if analysis_type == "Deming":
        deming_weighted = st.toggle("Weighted Deming", value=False, key="dw")
        error_ratio     = st.number_input("Error ratio λ=Var(y)/Var(x)",
                                          0.01, 100.0, 1.0, 0.1, key="er")
    else:
        deming_weighted = False
        error_ratio     = 1.0
    st.divider()

    st.subheader("Data input")
    # Precision Evaluation has its own dedicated data input in the main area
    if analysis_type == "Precision Evaluation (EP15-A3)":
        st.caption("Upload or paste precision data in the main area →")
        _x_sid = _y_sid = _sid_err = None
        uploaded_file = pasted_text = None
        input_mode = "📂 Upload file"   # safe default, unused for precision
    else:
        input_mode = st.radio("Input method",["📂 Upload file","📋 Paste data"],key="imode")

        # Data-loading state
        _x_sid = _y_sid = _sid_err = None
        uploaded_file = pasted_text = None

        if input_mode == "📂 Upload file":
            uploaded_file = st.file_uploader("Upload CSV or Excel",
                                             type=["csv","xlsx","xls"], key="fup")
            if uploaded_file is not None:
                try:
                    fname = uploaded_file.name.lower()
                    if fname.endswith((".xlsx",".xls")):
                        import openpyxl
                        _rb = uploaded_file.read(); uploaded_file.seek(0)
                        _wb = openpyxl.load_workbook(BytesIO(_rb),read_only=True,data_only=True)
                        _sn = _wb.sheetnames; _wb.close()
                        _ss = st.selectbox("Sheet / tab", _sn, key="ss")
                        _hc = st.radio("Header row?",["Yes (first row)","No header"],
                                       horizontal=True, key="hx")
                        _hdr= _hc=="Yes (first row)"
                        _pv = pd.read_excel(BytesIO(_rb),sheet_name=_ss,
                                            header=0 if _hdr else None, nrows=5)
                        if not _hdr:
                            _pv.columns = [f"Column {i+1}" for i in range(len(_pv.columns))]
                        else:
                            _pv.columns=[str(c) for c in _pv.columns]
                        st.caption("Preview (first 5 rows):")
                        st.dataframe(_pv, use_container_width=True)
                        _cols=list(_pv.columns)
                        if len(_cols)>=2:
                            _xc=st.selectbox("Reference column (x)",_cols,0,key="xce")
                            _yc=st.selectbox("Candidate column (y)",_cols,min(1,len(_cols)-1),key="yce")
                            _full=pd.read_excel(BytesIO(_rb),sheet_name=_ss,
                                                header=0 if _hdr else None)
                            if not _hdr:
                                _full.columns = [f"Column {i+1}" for i in range(len(_full.columns))]
                            else:
                                _full.columns=[str(c) for c in _full.columns]
                            _full=_apply_filter(_full, exclude_cols=[_xc,_yc], key_prefix="xe")
                            def _tonum(s): return pd.to_numeric(s.astype(str).str.replace(",","."),errors="coerce").values.astype(float)
                            _x_sid=_tonum(_full[_xc])
                            _y_sid=_tonum(_full[_yc])
                        else:
                            _sid_err="Sheet needs at least 2 columns."
                    else:
                        _rb = uploaded_file.read(); uploaded_file.seek(0)
                        _hc = st.radio("Header row?",["Yes (first row)","No header"],
                                       horizontal=True, key="hc")
                        _hdr= _hc=="Yes (first row)"
                        _pv = pd.read_csv(BytesIO(_rb), header=0 if _hdr else None,
                                          sep=None, engine="python", decimal=",")
                        if _pv.select_dtypes(include=[np.number]).shape[1]<2:
                            _pv=pd.read_csv(BytesIO(_rb),header=0 if _hdr else None,
                                            sep=None,engine="python")
                        if not _hdr:
                            _pv.columns = [f"Column {i+1}" for i in range(len(_pv.columns))]
                        else:
                            _pv.columns=[str(c) for c in _pv.columns]
                        st.caption("Preview (first 5 rows):")
                        st.dataframe(_pv.head(), use_container_width=True)
                        _cols=list(_pv.columns)
                        _xc=st.selectbox("Reference column (x)",_cols,0,key="xcc")
                        _yc=st.selectbox("Candidate column (y)",_cols,min(1,len(_cols)-1),key="ycc")
                        _full=pd.read_csv(BytesIO(_rb), header=0 if _hdr else None,
                                          sep=None, engine="python", decimal=",")
                        if _full.select_dtypes(include=[np.number]).shape[1]<2:
                            _full=pd.read_csv(BytesIO(_rb),header=0 if _hdr else None,
                                              sep=None,engine="python")
                        if not _hdr:
                            _full.columns = [f"Column {i+1}" for i in range(len(_full.columns))]
                        else:
                            _full.columns=[str(c) for c in _full.columns]
                        _full=_apply_filter(_full, exclude_cols=[_xc,_yc], key_prefix="ce")
                        def _tonum(s): return pd.to_numeric(s.astype(str).str.replace(",","."),errors="coerce").values.astype(float)
                        _x_sid=_tonum(_full[_xc])
                        _y_sid=_tonum(_full[_yc])
                except Exception as e:
                    _sid_err=str(e)
        else:
            if analysis_type == "Precision Evaluation (EP15-A3)":
                st.info("Use the upload/paste section in the main area for precision data.")
                pasted_text = None
            else:
                st.markdown("Copy two columns from Excel and paste below.")
                pasted_text=st.text_area("Paste data here",height=160,
                                         placeholder="10,2\t10,5\n15,7\t16,1\n...",key="pa")

    st.subheader("Method names")
    x_label=st.text_input("Reference method","Reference Method",key="xl")
    y_label=st.text_input("Candidate method","Candidate Method",key="yl")
    st.divider()

    # ── Safe defaults for ALL branch-specific variables ───────────────────────
    pb_title="Passing–Bablok Method Comparison"; ba_title_input=""
    decimals=2
    pb_x_min=pb_x_max=pb_y_min=pb_y_max=None
    ba_x_min=ba_x_max=ba_y_min=ba_y_max=None
    ba_pct_diff=False
    pb_color_scatter="#2563EB"; pb_color_identity="#9CA3AF"
    pb_color_regression="#DC2626"; pb_color_ci="#DC2626"
    pb_ci_alpha=0.15; pb_show_ci=True
    pb_legend_scatter="Observations"; pb_legend_identity="Identity (y = x)"
    pb_legend_regression="Regression"; pb_legend_ci="95% CI"
    ba_color_scatter="#2563EB"; ba_color_mean="#DC2626"; ba_color_loa="#F97316"
    ba_legend_scatter="Difference"; ba_label_mean="Mean"
    ba_label_loa_upper="+1,96 SD"; ba_label_loa_lower="−1,96 SD"

    cm_step=1; cm_x_min=cm_x_max=cm_y_min=cm_y_max=None
    cm_ea_window=2; cm_scale_max=2; cm_base_color="#1D4ED8"
    cm_title="Zone Diameter Comparison Matrix"; cm_font_size=11
    cm_num_color_on_blue="#1E3A5F"; cm_num_color_on_white="#1E3A5F"
    cm_num_bold=True; cm_show_diag=True; cm_show_totals=True
    bp_system="EUCAST"; bp_s_x=bp_s_y=20.0; bp_r_x=bp_r_y=16.0

    # Precision safe defaults
    prec_alpha=0.05; prec_n_levels=1
    prec_claimed_sr=None; prec_claimed_sl=None
    prec_decimals=4

    # ── Override defaults with real widgets for active analysis ───────────────
    if analysis_type in ("Passing–Bablok","Deming"):
        _dt={
            "Passing–Bablok":"Passing–Bablok Method Comparison",
            "Deming":"Weighted Deming Method Comparison" if deming_weighted
                     else "Deming Method Comparison"
        }[analysis_type]
        st.subheader("Graph titles")
        pb_title      =st.text_input("Regression title",value="",
                                     placeholder="Leave blank for auto",key="pbt")
        ba_title_input=st.text_input("Bland–Altman title",value="",
                                     placeholder="Leave blank for auto",key="bat")
        st.divider()
        st.subheader("Decimal places")
        decimals=st.slider("Decimals",1,8,2,key="dec")
        st.divider()
        with st.expander("📐 Axis ranges"):
            st.markdown("**Regression** (blank=auto)")
            _a=st.columns(2)
            pb_x_min=_pa(_a[0].text_input("X min","0",key="pxn"))
            pb_x_max=_pa(_a[1].text_input("X max","",key="pxx"))
            pb_y_min=_pa(_a[0].text_input("Y min","0",key="pyn"))
            pb_y_max=_pa(_a[1].text_input("Y max","",key="pyx"))
            st.markdown("**Bland–Altman** (blank=auto)")
            _b=st.columns(2)
            ba_x_min=_pa(_b[0].text_input("X min","",key="bxn"))
            ba_x_max=_pa(_b[1].text_input("X max","",key="bxx"))
            ba_y_min=_pa(_b[0].text_input("Y min","",key="byn"))
            ba_y_max=_pa(_b[1].text_input("Y max","",key="byx"))
        st.divider()
        st.subheader("Bland–Altman Y-axis")
        ba_pct_diff=st.toggle("Show difference as %",value=False,key="bap")
        st.divider()
        with st.expander("🎨 Colours & legend names"):
            st.markdown("**Regression plot**")
            pb_color_scatter   =st.color_picker("Scatter points", "#2563EB",key="pcs")
            pb_color_identity  =st.color_picker("Identity line",  "#9CA3AF",key="pci")
            pb_color_regression=st.color_picker("Regression line","#DC2626",key="pcr")
            pb_legend_scatter  =st.text_input("Legend: scatter",   "Observations",    key="pls")
            pb_legend_identity =st.text_input("Legend: identity",  "Identity (y = x)",key="pli")
            pb_legend_regression=st.text_input("Legend: regression","Regression",     key="plr")
            st.markdown("**CI band**")
            pb_show_ci  =st.toggle("Show 95% CI band",value=True,key="psc")
            pb_color_ci =st.color_picker("CI colour","#DC2626",key="pcc")
            pb_ci_alpha =st.slider("CI transparency",0.0,1.0,0.15,0.01,key="pca")
            pb_legend_ci=st.text_input("Legend: CI","95% CI",key="plc")
            st.markdown("**Bland–Altman**")
            ba_color_scatter  =st.color_picker("Scatter points","#2563EB",key="bcs")
            ba_color_mean     =st.color_picker("Mean bias line","#DC2626",key="bcm")
            ba_color_loa      =st.color_picker("LoA lines",     "#F97316",key="bcl")
            ba_legend_scatter =st.text_input("Legend: scatter",  "Difference",key="bls")
            ba_label_mean     =st.text_input("Annotation: mean", "Mean",      key="blm")
            ba_label_loa_upper=st.text_input("Annotation: +LoA", "+1,96 SD",  key="blu")
            ba_label_loa_lower=st.text_input("Annotation: −LoA", "−1,96 SD",  key="bll")

    elif analysis_type == "Confusion Matrix":
        st.subheader("Matrix settings")
        cm_step=st.number_input("Step size (mm/cell)",1,10,1,1,key="cms")
        _cc=st.columns(2)
        cm_x_min=_ca(_cc[0].text_input("X min","",placeholder="auto",key="cxn"))
        cm_x_max=_ca(_cc[1].text_input("X max","",placeholder="auto",key="cxx"))
        cm_y_min=_ca(_cc[0].text_input("Y min","",placeholder="auto",key="cyn"))
        cm_y_max=_ca(_cc[1].text_input("Y max","",placeholder="auto",key="cyx"))
        cm_ea_window =st.selectbox("EA band (±mm)",[1,2,3],index=1,key="cea")
        cm_scale_max =st.slider("Colour bands (mm from diagonal)",1,10,2,key="csc")
        cm_base_color=st.color_picker("Matrix colour","#1D4ED8",key="cbc")
        cm_title     =st.text_input("Matrix title","Zone Diameter Comparison Matrix",key="ctt")
        cm_font_size =st.slider("Cell font size",6,16,11,key="cfs")
        st.markdown("**Number style**")
        cm_num_color_on_blue =st.color_picker("Colour on coloured cells","#1E3A5F",key="cnb")
        cm_num_color_on_white=st.color_picker("Colour on white cells",   "#1E3A5F",key="cnw")
        cm_num_bold  =st.toggle("Bold numbers",value=True,key="cnbd")
        cm_show_diag =st.toggle("Show diagonal lines",value=True,key="csd")
        cm_show_totals=st.toggle("Show n = total (outside frame)",value=True,key="cst")
        st.divider()
        st.subheader("Categorical agreement")
        bp_system=st.selectbox("Breakpoint system",["EUCAST","CLSI"],key="bps")
        _bp=st.columns(2)
        bp_s_x=_bp[0].number_input(f"S ≥ ({x_label})",value=20.0,step=0.5,key="bsx")
        bp_r_x=_bp[1].number_input(f"R ≤ ({x_label})",value=16.0,step=0.5,key="brx")
        bp_s_y=_bp[0].number_input(f"S ≥ ({y_label})",value=20.0,step=0.5,key="bsy")
        bp_r_y=_bp[1].number_input(f"R ≤ ({y_label})",value=16.0,step=0.5,key="bry")

    else:   # Precision Evaluation (EP15-A3)
        st.subheader("Precision settings")
        st.caption("Protocol: ≥ 2 replicates/day over ≥ 2 days. "
                   "EP15-A3 recommends 5 replicates × 5 days.")
        prec_decimals = st.slider("Decimal places in results", 1, 6, 4, key="pr_dec")
        prec_alpha    = st.selectbox("Significance level (α)",
                                     [0.05, 0.01], index=0,
                                     format_func=lambda v: f"{v:.0%}",
                                     key="pr_alpha")
        prec_n_levels = st.number_input("Number of levels tested (q)",
                                         min_value=1, max_value=5, value=1, step=1,
                                         key="pr_q",
                                         help="Used for Bonferroni correction of chi-square test. "
                                              "Set to the number of concentration levels you are testing simultaneously.")
        st.markdown("**Manufacturer claims (optional)**")
        st.caption("Enter manufacturer's claimed SDs to perform chi-square verification. Leave at 0 to skip.")
        _prc=st.columns(2)
        _csr=_prc[0].number_input("Claimed repeatability SD (σr)",
                                   min_value=0.0, value=0.0, step=0.001,
                                   format="%.4f", key="pr_csr")
        _csl=_prc[1].number_input("Claimed within-lab SD (σl)",
                                   min_value=0.0, value=0.0, step=0.001,
                                   format="%.4f", key="pr_csl")
        prec_claimed_sr = _csr if _csr > 0 else None
        prec_claimed_sl = _csl if _csl > 0 else None

    st.divider()
    st.caption("Passing & Bablok 1983 · Deming 1943 · Linnet 1990 · CLSI EP15-A3 2014")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN AREA
# ══════════════════════════════════════════════════════════════════════════════
method_label = ("Weighted Deming" if deming_weighted else "Deming") \
               if analysis_type=="Deming" else analysis_type
st.title(f"Method Comparison — {method_label}")

if _sid_err:
    st.error(f"Could not read file: {_sid_err}")
    st.stop()

# ── Resolve data ───────────────────────────────────────────────────────────────
def _get_data():
    if input_mode=="📂 Upload file":
        if uploaded_file is None:
            # ── Welcome / landing page ────────────────────────────────────────
            st.markdown("""
## Method Comparison Tool

A simple tool for comparing two analytical measurement methods in clinical microbiology and clinical chemistry.
👈 Select an analysis type in the sidebar, then upload your data or paste it directly.
""")

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.markdown("""
**📈 Passing–Bablok**
Non-parametric regression — resistant to outliers, no assumptions about error distribution.
Slope, intercept and 95 % confidence intervals via the rank-based method.
""")
            with col_b:
                st.markdown("""
**📉 Deming regression**
Accounts for measurement error in both methods.
Ordinary (equal variances) or weighted (proportional CV, Linnet 1990).
Confidence intervals via jackknife resampling.
""")
            with col_c:
                st.markdown("""
**🔢 Confusion matrix**
Zone diameter agreement grid for disk diffusion comparison.
Essential agreement (±1/±2 mm), categorical agreement, VME and ME.
EUCAST and CLSI breakpoints supported.
""")

            col_d, _ = st.columns([1, 2])
            with col_d:
                st.markdown("""
**🔬 Precision Evaluation (EP15-A3)**
Within-run (repeatability) and within-laboratory (total) SD and CV.
Chi-square verification against manufacturer claims.
Based on CLSI EP15-A3 (2014) — 5 replicates × 5 days recommended.
""")

            st.divider()

            # ── Data format + references side by side ─────────────────────────
            fc1, fc2 = st.columns([3, 2])

            with fc1:
                st.markdown("**📄 Expected data format**")

                _wt1, _wt2 = st.tabs(["Regression / Confusion matrix", "Precision Evaluation"])

                with _wt1:
                    st.markdown("At least two numeric columns — one per method. "
                                "Extra columns (species, antibiotic, lab) can be used to filter rows.")
                    st.dataframe(pd.DataFrame({
                        "Species":        ["E. coli","E. coli","K. pneumoniae","S. aureus"],
                        "Reference (mm)": [18, 20, 22, 24],
                        "Candidate (mm)": [19, 20, 23, 25],
                    }), use_container_width=True, hide_index=True)
                    st.caption("Accepted: Excel (.xlsx/.xls), CSV, or paste from Excel. "
                               "Comma or point as decimal. Header row optional.")

                with _wt2:
                    st.markdown("**One column per day, one row per replicate.** "
                                "EP15-A3 recommends 5 replicates × 5 days at ≥ 2 concentration levels.")
                    st.dataframe(pd.DataFrame({
                        "Day 1": [2.015, 2.013, 1.963, 2.001, 1.998],
                        "Day 2": [2.019, 2.002, 1.979, 2.010, 1.995],
                        "Day 3": [2.025, 1.959, 2.000, 1.988, 2.005],
                        "Day 4": [1.972, 1.950, 1.973, 1.965, 1.980],
                        "Day 5": [1.981, 1.956, 1.957, 1.970, 1.975],
                    }), use_container_width=True, hide_index=True)
                    st.caption("Upload as Excel / CSV or paste directly from Excel. "
                               "Column headers become the day labels. Comma or point as decimal.")

                    st.markdown("**Example output:**")
                    st.dataframe(pd.DataFrame({
                        "Component":              ["Within-run (repeatability)",
                                                   "Between-day",
                                                   "Within-laboratory (total)"],
                        "SD":                     ["0,0235", "0,0116", "0,0262"],
                        "CV (%)":                 ["1,18",   "—",      "1,32"],
                        "Degrees of freedom":     ["10",     "4",      "12,8 (eff.)"],
                    }), use_container_width=True, hide_index=True)

            with fc2:
                st.markdown("**📚 Key references**")
                st.markdown("""
- Passing & Bablok, *J Clin Chem Clin Biochem* 1983 — [DOI](https://doi.org/10.1515/cclm.1983.21.11.709)
- Linnet K, *Stat Med* 1990 — [DOI](https://doi.org/10.1002/sim.4780091210)
- Bland & Altman, *Lancet* 1986 — [DOI](https://doi.org/10.1016/S0140-6736(86)90837-8)
- CLSI EP15-A3, 2014 — Precision verification
- CLSI EP09c — Method comparison & bias estimation
- EUCAST Disk Diffusion Guide v10.0, 2023 — [eucast.org](https://www.eucast.org/ast_of_bacteria/disk_diffusion_methodology/)
- CLSI M52 — Verification of AST systems
- Chesher D, *Clin Biochem Rev* 2008 — [DOI](https://doi.org/10.3109/00365519809099610)
""")
            return None, None

        if _x_sid is None or _y_sid is None:
            st.info("👈 Select the columns to use in the sidebar.")
            return None,None
        return _x_sid, _y_sid
    else:
        if not pasted_text or not pasted_text.strip():
            st.info("👈 Paste your data in the sidebar to get started.")
            return None,None
        try:
            _df=parse_pasted(pasted_text)
            st.success(f"✅ Parsed {len(_df)} rows.")
            return _df["reference"].values, _df["candidate"].values
        except ValueError as e:
            st.error(str(e)); return None,None

if analysis_type == "Precision Evaluation (EP15-A3)":
    x_raw = y_raw = np.array([1.0, 2.0])  # dummy — precision branch has its own upload
else:
    x_raw, y_raw = _get_data()
    if x_raw is None:
        st.stop()

if analysis_type != "Precision Evaluation (EP15-A3)":
    n_tot=len(x_raw)
    n_mis=int(np.sum(~(np.isfinite(x_raw)&np.isfinite(y_raw))))
    _c1,_c2,_c3=st.columns(3)
    _c1.metric("Total rows",n_tot)
    _c2.metric("Missing / excluded",n_mis)
    _c3.metric("Valid pairs",n_tot-n_mis)


# ══════════════════════════════════════════════════════════════════════════════
# BRANCH A — Regression
# ══════════════════════════════════════════════════════════════════════════════
if analysis_type in ("Passing–Bablok","Deming"):

    if st.button("▶ Analyze", type="primary"):
        try:
            if analysis_type=="Passing–Bablok":
                _r=passing_bablok(x_raw,y_raw)
            elif deming_weighted:
                _r=weighted_deming(x_raw,y_raw,error_ratio=error_ratio)
            else:
                _r=deming(x_raw,y_raw,error_ratio=error_ratio)
            st.session_state.update({
                "reg_res":_r, "reg_method":method_label,
                "stats":summary_stats(x_raw,y_raw),
                "x_raw":x_raw.copy(), "y_raw":y_raw.copy(),
            })
        except ValueError as e:
            st.error(f"Analysis failed: {e}")

    if "reg_res" not in st.session_state:
        st.info("👆 Click **Analyze** to run the regression.")
        st.stop()

    rr=st.session_state["reg_res"]
    ss=st.session_state["stats"]
    _x=st.session_state["x_raw"]
    _y=st.session_state["y_raw"]

    st.subheader(f"Results — {st.session_state.get('reg_method',method_label)}")
    st.dataframe(pd.DataFrame([
        {"Statistic":"Slope","Value":fmt(rr["slope"],decimals),
         "95% CI":f"[{fmt(rr['slope_lower'],decimals)} – {fmt(rr['slope_upper'],decimals)}]"},
        {"Statistic":"Intercept","Value":fmt(rr["intercept"],decimals),
         "95% CI":f"[{fmt(rr['intercept_lower'],decimals)} – {fmt(rr['intercept_upper'],decimals)}]"},
        {"Statistic":"R²",        "Value":fmt(ss["r_squared"],decimals),"95% CI":"—"},
        {"Statistic":"Pearson r", "Value":fmt(ss["pearson_r"],decimals),"95% CI":"—"},
        {"Statistic":"Bias",      "Value":fmt(ss["bias"],decimals),     "95% CI":"—"},
        {"Statistic":"LoA lower", "Value":fmt(ss["loa_lower"],decimals),"95% CI":"—"},
        {"Statistic":"LoA upper", "Value":fmt(ss["loa_upper"],decimals),"95% CI":"—"},
    ]),use_container_width=True,hide_index=True)

    _cp,_cb=st.columns(2)
    # Auto-title from method name when user leaves title blank
    _auto_reg_title = {
        "Passing–Bablok": "Passing–Bablok Method Comparison",
        "Deming": "Weighted Deming Method Comparison" if deming_weighted else "Deming Method Comparison",
    }[analysis_type]
    _resolved_pb_title = pb_title if pb_title.strip() else _auto_reg_title
    _pkw=dict(slope=rr["slope"],intercept=rr["intercept"],
              slope_lower=rr["slope_lower"],slope_upper=rr["slope_upper"],
              intercept_lower=rr["intercept_lower"],intercept_upper=rr["intercept_upper"],
              r_squared=ss["r_squared"],x_label=x_label,y_label=y_label,title=_resolved_pb_title,
              color_scatter=pb_color_scatter,color_identity=pb_color_identity,
              color_regression=pb_color_regression,color_ci=pb_color_ci,
              ci_alpha=pb_ci_alpha,show_ci=pb_show_ci,
              legend_scatter=pb_legend_scatter,legend_identity=pb_legend_identity,
              legend_regression=pb_legend_regression,legend_ci=pb_legend_ci,
              x_min=pb_x_min,x_max=pb_x_max,y_min=pb_y_min,y_max=pb_y_max,decimals=decimals)
    _bkw=dict(mean_diff=ss["mean_diff"],loa_lower=ss["loa_lower"],loa_upper=ss["loa_upper"],
              x_label=x_label,y_label=y_label,title=ba_title_input,pct_diff=ba_pct_diff,
              color_scatter=ba_color_scatter,color_mean=ba_color_mean,color_loa=ba_color_loa,
              legend_scatter=ba_legend_scatter,label_mean=ba_label_mean,
              label_loa_upper=ba_label_loa_upper,label_loa_lower=ba_label_loa_lower,
              x_min=ba_x_min,x_max=ba_x_max,y_min=ba_y_min,y_max=ba_y_max,decimals=decimals)

    with _cp:
        st.plotly_chart(make_regression_plot(_x,_y,**_pkw),use_container_width=True)
    with _cb:
        fig_ba=make_bland_altman_plot(_x,_y,**_bkw)
        st.plotly_chart(fig_ba,use_container_width=True)

    st.subheader("Export")
    with st.expander("⚙️ Image resolution",expanded=True):
        _dl=st.selectbox("Resolution",DPI_LABELS,index=1,key="rdpi")
        _dp=dpi_from_label(_dl)
        _iw=int(180/25.4*_dp); _ih=int(130/25.4*_dp)
        st.caption(f"Auto: **{_iw}×{_ih} px** at **{_dp} dpi** ≈ 18×13 cm.")

    fig_pb=make_regression_plot(_x,_y,**_pkw)
    fig_ba=make_bland_altman_plot(_x,_y,**_bkw)

    for _rfn,_kw,_lbl,_slg in [
        (render_pb_png,_pkw,"Regression plot","reg"),
        (render_ba_png,_bkw,"Bland–Altman plot","ba"),
    ]:
        st.markdown(f"**{_lbl}**")
        _e1,_e2,_=st.columns([1,1,2])
        _e1.download_button(f"🖼 PNG ({_dp} dpi)",
            mpl_fig_to_png_bytes(_rfn(_x,_y,dpi=_dp,width_px=_iw,height_px=_ih,**_kw),dpi=_dp),
            f"{_slg}_{_dp}dpi.png","image/png",key=f"png_{_slg}")
        _e2.download_button("📐 SVG",
            mpl_fig_to_svg_bytes(_rfn(_x,_y,dpi=_dp,width_px=_iw,height_px=_ih,**_kw)),
            f"{_slg}.svg","image/svg+xml",key=f"svg_{_slg}")

    st.divider()
    st.markdown("**Results data & full report**")
    _f1,_f2,_=st.columns([1,1,2])
    _f1.download_button("📥 Results CSV",results_to_csv(rr,ss),"results.csv","text/csv",key="rcsv")
    _f2.download_button("📄 HTML Report",
        build_html_report(rr,ss,fig_pb,fig_ba,x_label=x_label,y_label=y_label),
        "report.html","text/html",key="rhtml")


# ══════════════════════════════════════════════════════════════════════════════
# BRANCH B — Confusion Matrix
# ══════════════════════════════════════════════════════════════════════════════
elif analysis_type == "Confusion Matrix":
    st.subheader("Zone Diameter Confusion Matrix")
    try:
        matrix,x_bins,y_bins=build_count_matrix(
            x_raw,y_raw,step=int(cm_step),
            x_min=cm_x_min,x_max=cm_x_max,y_min=cm_y_min,y_max=cm_y_max)
    except Exception as e:
        st.error(f"Could not build matrix: {e}"); st.stop()

    ea=essential_agreement(x_raw,y_raw)
    ca=categorical_agreement(x_raw,y_raw,
                             s_breakpoint_x=bp_s_x,r_breakpoint_x=bp_r_x,
                             s_breakpoint_y=bp_s_y,r_breakpoint_y=bp_r_y)

    st.markdown(f"**{bp_system}** — "
                f"{x_label}: S≥{bp_s_x:.1f}/R≤{bp_r_x:.1f} mm | "
                f"{y_label}: S≥{bp_s_y:.1f}/R≤{bp_r_y:.1f} mm")

    _m1,_m2,_m3,_m4,_m5=st.columns(5)
    _m1.metric("EA ±1 mm", f"{ea['ea_1mm']:.1f}%",f"{ea['n_ea1']}/{ea['n']}")
    _m2.metric("EA ±2 mm", f"{ea['ea_2mm']:.1f}%",f"{ea['n_ea2']}/{ea['n']}")
    _m3.metric("Categorical Agr.",f"{ca['ca']:.1f}%",f"{ca['n_ca']}/{ca['n']}")
    _m4.metric("VME (S→R)",f"{ca['vme']:.1f}%",
               f"{ca['n_vme']} of {ca['n_s_ref']} S",delta_color="inverse")
    _m5.metric("ME (R→S)", f"{ca['me']:.1f}%",
               f"{ca['n_me']} of {ca['n_r_ref']} R",delta_color="inverse")
    if ca["n_minor"]>0:
        st.caption(f"Minor errors: {ca['n_minor']} ({ca['minor_e']:.1f}%)")

    with st.expander("ℹ️ Acceptability thresholds"):
        st.markdown("""
| Metric | EUCAST | CLSI |
|---|---|---|
| Essential Agreement ±2 mm | ≥ 90 % | ≥ 90 % |
| Categorical Agreement | ≥ 90 % | ≥ 90 % |
| Very Major Error | ≤ 3 % of S | ≤ 1.5 % |
| Major Error | ≤ 3 % of R | ≤ 3 % |
*EUCAST Disk Diffusion v10.0; CLSI M52.*""")

    st.divider()

    _ckw=dict(x_label=f"{x_label} (mm)",y_label=f"{y_label} (mm)",title=cm_title,
              color_scale_max=int(cm_scale_max),base_color=cm_base_color,
              step=int(cm_step),ea_window=int(cm_ea_window),
              show_diagonal_lines=cm_show_diag,show_totals=cm_show_totals,
              cell_font_size=int(cm_font_size),
              num_color_on_blue=cm_num_color_on_blue,
              num_color_on_white=cm_num_color_on_white,num_bold=cm_num_bold)

    st.plotly_chart(make_confusion_plot(matrix,x_bins,y_bins,**_ckw),
                    use_container_width=True)

    st.subheader("Export matrix")
    with st.expander("⚙️ Export resolution",expanded=True):
        _cdl=st.selectbox("Resolution",DPI_LABELS,index=1,key="cdpi")
        _cdp=dpi_from_label(_cdl)
        _nb=len(x_bins)
        _cw=int((_nb*6/25.4+28/25.4*2)*_cdp)
        st.caption(f"Auto: **{_cw}×{_cw} px** at **{_cdp} dpi** — each cell=6 mm printed.")

    _d1,_d2,_=st.columns([1,1,2])
    _d1.download_button(f"🖼 PNG ({_cdp} dpi)",
        render_confusion_png(matrix,x_bins,y_bins,dpi=_cdp,**_ckw),
        f"confusion_{_cdp}dpi.png","image/png",key="cpng")

    _mdf=pd.DataFrame(matrix,
                      index=[str(int(b)) for b in y_bins],
                      columns=[str(int(b)) for b in x_bins])
    _mdf.index.name=f"{y_label}\\{x_label}"
    _d2.download_button("📥 Matrix CSV",_mdf.to_csv(),
                        "confusion_matrix.csv","text/csv",key="ccsv")


# ══════════════════════════════════════════════════════════════════════════════
# BRANCH C — Precision Evaluation (EP15-A3)
# ══════════════════════════════════════════════════════════════════════════════
else:
    st.subheader("Precision Evaluation — CLSI EP15-A3")
    st.markdown("Upload or paste data where **each column = one day** and each row = one replicate.")

    # For precision, data_raw is not needed — we need a wide-format table.
    # Offer a dedicated upload here, independent of the main data input.
    st.markdown("---")
    _pr_tab1, _pr_tab2 = st.tabs(["📂 Upload precision file", "📋 Paste precision data"])

    _pr_data_dict = None   # will hold {day_label: [values]}

    with _pr_tab1:
        _pr_file = st.file_uploader(
            "Upload Excel or CSV (columns = days, rows = replicates)",
            type=["csv","xlsx","xls"], key="pr_file")
        if _pr_file is not None:
            try:
                _pr_fname = _pr_file.name.lower()
                _pr_rb = _pr_file.read()
                if _pr_fname.endswith((".xlsx",".xls")):
                    _pr_df = pd.read_excel(BytesIO(_pr_rb), header=0)
                else:
                    _pr_df = pd.read_csv(BytesIO(_pr_rb), sep=None, engine="python")
                _pr_df.columns = [str(c) for c in _pr_df.columns]
                # Rename columns that look like integers to "Column N"
                _pr_df.columns = [
                    f"Column {i+1}" if c.strip().lstrip("-").isdigit() else c
                    for i, c in enumerate(_pr_df.columns)
                ]
                st.caption("Preview:")
                st.dataframe(_pr_df.head(), use_container_width=True)
                _pr_data_dict = precision_from_dataframe(_pr_df)
            except Exception as e:
                st.error(f"Could not read file: {e}")

    with _pr_tab2:
        st.markdown(
            "Paste your data — **columns = days, rows = replicates**. "
            "Separate columns with tabs (copy/paste from Excel works directly). "
            "First row = day names (header).")
        _pr_paste = st.text_area(
            "Paste here", height=180,
            placeholder="Day 1\tDay 2\tDay 3\tDay 4\tDay 5\n"
                        "2,015\t2,019\t2,025\t1,972\t1,981\n"
                        "2,013\t2,002\t1,959\t1,950\t1,956\n"
                        "1,963\t1,979\t2,000\t1,973\t1,957",
            key="pr_paste")
        if _pr_paste and _pr_paste.strip():
            try:
                from io import StringIO
                _pr_df2 = pd.read_csv(StringIO(_pr_paste), sep="\t", decimal=",")
                if _pr_df2.shape[1] < 2:
                    _pr_df2 = pd.read_csv(StringIO(_pr_paste), sep="\t")
                _pr_df2.columns = [str(c) for c in _pr_df2.columns]
                st.caption("Preview:")
                st.dataframe(_pr_df2.head(), use_container_width=True)
                _pr_data_dict = precision_from_dataframe(_pr_df2)
            except Exception as e:
                st.error(f"Could not parse pasted data: {e}")

    if _pr_data_dict is None:
        st.info("Upload or paste your replicate data above to run the precision analysis.")
        st.stop()

    # Validate
    _pr_days = list(_pr_data_dict.keys())
    _pr_ns   = [len(v) for v in _pr_data_dict.values()]
    if len(_pr_days) < 2:
        st.error("Need at least 2 days of data."); st.stop()
    if min(_pr_ns) < 2:
        st.error("Need at least 2 replicates per day."); st.stop()
    if max(_pr_ns) != min(_pr_ns):
        st.warning(
            f"Days have different numbers of replicates ({min(_pr_ns)}–{max(_pr_ns)}). "
            "Truncating to the minimum to ensure a balanced design.")
        _pr_min_n = min(_pr_ns)
        _pr_data_dict = {k: v[:_pr_min_n] for k, v in _pr_data_dict.items()}

    # Run analysis
    try:
        _pr = compute_precision(
            _pr_data_dict,
            alpha=float(prec_alpha),
            n_levels=int(prec_n_levels),
            claimed_sr=prec_claimed_sr,
            claimed_sl=prec_claimed_sl,
        )
    except Exception as e:
        st.error(f"Precision calculation failed: {e}"); st.stop()

    def _pf(v): return f"{v:.{prec_decimals}f}".replace(".", ",")

    # ── Study design banner ───────────────────────────────────────────────────
    st.divider()
    st.subheader("Precision Results")
    _di1,_di2,_di3,_di4 = st.columns(4)
    _di1.metric("Grand mean",    _pf(_pr["grand_mean"]))
    _di2.metric("Days",          str(_pr["D"]))
    _di3.metric("Replicates / day", str(_pr["n"]))
    _di4.metric("Total measurements", str(_pr["D"] * _pr["n"]))

    st.divider()

    # ── Two large headline boxes ──────────────────────────────────────────────
    _h1, _h2 = st.columns(2)
    with _h1:
        st.markdown("""
<div style="background:#EFF6FF;border-radius:12px;padding:20px 24px;border:1px solid #BFDBFE">
<p style="margin:0;font-size:0.78rem;color:#1E40AF;font-weight:600;letter-spacing:0.05em">WITHIN-RUN (REPEATABILITY)</p>
<p style="margin:4px 0 0;font-size:2rem;font-weight:700;color:#1E3A5F">CV = {cv} %</p>
<p style="margin:2px 0 0;font-size:1.1rem;color:#2563EB">SD = {sd}</p>
<p style="margin:8px 0 0;font-size:0.75rem;color:#64748B">df = {df} &nbsp;|&nbsp; Protocol: CLSI EP15-A3</p>
</div>
""".format(sd=_pf(_pr["sr"]), cv=_pf(_pr["cv_r"]), df=_pr["df_within"]),
        unsafe_allow_html=True)

    with _h2:
        st.markdown("""
<div style="background:#F0FDF4;border-radius:12px;padding:20px 24px;border:1px solid #BBF7D0">
<p style="margin:0;font-size:0.78rem;color:#166534;font-weight:600;letter-spacing:0.05em">WITHIN-LABORATORY (TOTAL IMPRECISION)</p>
<p style="margin:4px 0 0;font-size:2rem;font-weight:700;color:#14532D">CV = {cv} %</p>
<p style="margin:2px 0 0;font-size:1.1rem;color:#16A34A">SD = {sd}</p>
<p style="margin:8px 0 0;font-size:0.75rem;color:#64748B">eff. df = {df} &nbsp;|&nbsp; Includes between-day variation</p>
</div>
""".format(sd=_pf(_pr["sl"]), cv=_pf(_pr["cv_l"]), df=f"{_pr['T']:.1f}"),
        unsafe_allow_html=True)

    st.markdown("")   # spacer

    # ── Full breakdown table ──────────────────────────────────────────────────
    with st.expander("📊 Full variance component breakdown", expanded=True):
        st.dataframe(pd.DataFrame([
            {"Component": "Within-run (Sᵣ)",
             "SD":     _pf(_pr["sr"]),
             "CV (%)": _pf(_pr["cv_r"]),
             "Variance (SD²)": _pf(_pr["sr2"]),
             "df":     str(_pr["df_within"])},
            {"Component": "Between-day (Sᵦ)",
             "SD":     _pf(_pr["sb"]),
             "CV (%)": "—",
             "Variance (SD²)": _pf(_pr["sb2"]),
             "df":     str(_pr["df_between"])},
            {"Component": "Within-laboratory / Total (Sₗ)",
             "SD":     _pf(_pr["sl"]),
             "CV (%)": _pf(_pr["cv_l"]),
             "Variance (SD²)": _pf(_pr["sl2"]),
             "df":     f"{_pr['T']:.1f} (eff.)"},
        ]), use_container_width=True, hide_index=True)

    # ── Verification against manufacturer claims ──────────────────────────────
    if prec_claimed_sr is not None or prec_claimed_sl is not None:
        st.markdown("**Chi-square verification (EP15-A3 §2.4.3)**")
        st.caption(f"α = {float(prec_alpha):.0%},  q = {prec_n_levels} level(s).  "
                   "Pass if observed SD ≤ verification value.")
        _vrows = []
        if prec_claimed_sr is not None:
            _vrows.append({
                "Component":         "Within-run (Sᵣ)",
                "Claimed SD":        _pf(prec_claimed_sr),
                "Observed SD":       _pf(_pr["sr"]),
                "Verification value":_pf(_pr["verif_sr"]),
                "Verdict":           "✅  PASS" if _pr["pass_sr"] else "❌  FAIL",
            })
        if prec_claimed_sl is not None:
            _vrows.append({
                "Component":         "Within-laboratory (Sₗ)",
                "Claimed SD":        _pf(prec_claimed_sl),
                "Observed SD":       _pf(_pr["sl"]),
                "Verification value":_pf(_pr["verif_sl"]),
                "Verdict":           "✅  PASS" if _pr["pass_sl"] else "❌  FAIL",
            })
        st.dataframe(pd.DataFrame(_vrows), use_container_width=True, hide_index=True)

    # ── Per-day summary ───────────────────────────────────────────────────────
    with st.expander("📋 Per-day summary"):
        _day_df = pd.DataFrame(_pr["day_summary"])
        for _col in ["Mean","SD","CV (%)","Min","Max"]:
            _day_df[_col] = _day_df[_col].map(_pf)
        st.dataframe(_day_df, use_container_width=True, hide_index=True)

    # ── Outliers ──────────────────────────────────────────────────────────────
    if _pr["outliers"]:
        st.warning(
            f"⚠️ {len(_pr['outliers'])} potential outlier(s) detected "
            "(|deviation| > 3.5 × Sᵣ). Investigate before accepting results.")
        _ol_df = pd.DataFrame(_pr["outliers"])
        _ol_df["Deviation / Sᵣ"] = _ol_df["Deviation / Sr"].map(lambda v: f"{v:.2f}")
        _ol_df = _ol_df.drop(columns=["Deviation / Sr"])
        st.dataframe(_ol_df, use_container_width=True, hide_index=True)

    # ── Export — journal-style table ──────────────────────────────────────────
    st.divider()
    st.subheader("Export")

    _day_keys = list(_pr_data_dict.keys())
    _n_reps   = _pr["n"]
    _day_summ = {s["Day"]: s for s in _pr["day_summary"]}

    # Column headers: Day | Rep 1 | Rep 2 … | Mean | SD | CV (%)
    _rep_cols = [f"Rep {i+1}" for i in range(_n_reps)]
    _all_cols = ["Day"] + _rep_cols + ["Mean", "SD", "CV (%)"]

    # One row per day
    _jrows = []
    for _dk in _day_keys:
        _vals = _pr_data_dict[_dk]
        _s    = _day_summ[_dk]
        _row  = {"Day": _dk}
        for _ri in range(_n_reps):
            _row[f"Rep {_ri+1}"] = _pf(_vals[_ri]) if _ri < len(_vals) else "—"
        _row["Mean"]    = _pf(_s["Mean"])
        _row["SD"]      = _pf(_s["SD"])
        _row["CV (%)"]  = _pf(_s["CV (%)"])
        _jrows.append(_row)

    _jdf = pd.DataFrame(_jrows, columns=_all_cols)

    # Precision summary footer rows (span Day column; values in Mean col for alignment)
    _footer = [
        {"Day": "Within-run (repeatability)ᵃ",
         **{f"Rep {i+1}": "" for i in range(_n_reps)},
         "Mean": "", "SD": _pf(_pr["sr"]), "CV (%)": _pf(_pr["cv_r"])},
        {"Day": "Within-laboratory (total)ᵇ",
         **{f"Rep {i+1}": "" for i in range(_n_reps)},
         "Mean": "", "SD": _pf(_pr["sl"]), "CV (%)": _pf(_pr["cv_l"])},
    ]
    if prec_claimed_sr is not None:
        _footer.append({
            "Day": "Manufacturer claim — repeatabilityᶜ",
            **{f"Rep {i+1}": "" for i in range(_n_reps)},
            "Mean": "", "SD": _pf(prec_claimed_sr),
            "CV (%)": "Pass" if _pr["pass_sr"] else "Fail",
        })
    if prec_claimed_sl is not None:
        _footer.append({
            "Day": "Manufacturer claim — within-laboratoryᶜ",
            **{f"Rep {i+1}": "" for i in range(_n_reps)},
            "Mean": "", "SD": _pf(prec_claimed_sl),
            "CV (%)": "Pass" if _pr["pass_sl"] else "Fail",
        })

    _footer_df = pd.DataFrame(_footer, columns=_all_cols)
    _full_jdf  = pd.concat([_jdf, _footer_df], ignore_index=True)

    # Footnotes
    _footnotes = [
        f"ᵃ Within-run SD (Sᵣ) = {_pf(_pr['sr'])}, CV% = {_pf(_pr['cv_r'])} "
        f"(df = {_pr['df_within']}; CLSI EP15-A3).",
        f"ᵇ Within-laboratory SD (Sₗ) = {_pf(_pr['sl'])}, CV% = {_pf(_pr['cv_l'])} "
        f"(effective df = {_pr['T']:.1f}; includes between-day variation).",
        f"  Grand mean = {_pf(_pr['grand_mean'])}, "
        f"D = {_pr['D']} days, n = {_pr['n']} replicates/day.",
    ]
    if prec_claimed_sr is not None or prec_claimed_sl is not None:
        _footnotes.append(
            f"ᶜ Chi-square verification (α = {float(prec_alpha):.0%}, "
            f"q = {prec_n_levels}); Pass if observed SD ≤ verification value."
        )

    # Preview in app
    st.caption("Journal-style precision table — days as rows, replicates as columns, "
               "precision summary in footer:")
    st.dataframe(_full_jdf.set_index("Day"), use_container_width=True)

    for _fn in _footnotes:
        st.caption(_fn)

    # Build download: table + footnotes as trailing rows
    _fn_rows = [{"Day": fn, **{c: "" for c in _all_cols if c != "Day"}}
                for fn in _footnotes]
    _dl_df = pd.concat(
        [_full_jdf, pd.DataFrame(_fn_rows, columns=_all_cols)],
        ignore_index=True
    ).set_index("Day")

    st.download_button(
        "📥 Download journal table (CSV)",
        _dl_df.to_csv(),
        "precision_journal_table.csv",
        "text/csv",
        key="pr_journal_csv",
    )
