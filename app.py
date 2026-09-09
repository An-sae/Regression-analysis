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
from analysis.data_loader import (
    load_long_format, match_two_files, get_common_analytes,
    find_duplicates, resolve_duplicates,
    extract_precision_replicates,
    build_matched_excel, build_precision_excel,
)

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


# ── CSV export helper ─────────────────────────────────────────────────────────
# Swedish/European Excel uses comma as the DECIMAL separator, so a
# comma-separated file cannot be parsed. We therefore write semicolon-separated
# files, prefixed with a UTF-8 BOM (so Excel detects the encoding and shows
# å/ä/ö correctly) and a "sep=;" hint line that Excel reads automatically.
CSV_SEP = ";"

def to_csv_bytes(df, index=False, index_label=None):
    """DataFrame -> semicolon-separated CSV bytes ready for st.download_button."""
    body = df.to_csv(sep=CSV_SEP, index=index, index_label=index_label)
    return ("\ufeff" + f"sep={CSV_SEP}\n" + body).encode("utf-8")

def text_to_csv_bytes(text):
    """Already-built CSV text (comma-separated) -> semicolon-separated bytes."""
    out = []
    for line in text.splitlines():
        # split on commas that are NOT inside quotes, then re-join with ';'
        parts, cur, inq = [], "", False
        for ch in line:
            if ch == '"':
                inq = not inq; cur += ch
            elif ch == "," and not inq:
                parts.append(cur); cur = ""
            else:
                cur += ch
        parts.append(cur)
        out.append(CSV_SEP.join(parts))
    return ("\ufeff" + f"sep={CSV_SEP}\n" + "\n".join(out) + "\n").encode("utf-8")
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


# ── Safe defaults for all sidebar variables (must be before the sidebar block) ─
_lf_mode="Single file (two columns)"
_lf_x_arr=_lf_y_arr=None
_lf_report_df=None
_lf_label_a="Method A"; _lf_label_b="Method B"
_lf_matched_xlsx=None; _lf_analyte="ALL"
_prlf_data_dict=None; _prlf_raw_df=None; _prlf_n_left=0

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — widgets override the safe defaults above
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("📊 Method Comparison")

    # ══ STEP 1 ═════════════════════════════════════════════════════════════
    st.markdown("##### ① &nbsp;Choose your analysis")
    analysis_type = st.selectbox(
        "Analysis type", label_visibility="collapsed",
        options=["Passing–Bablok","Deming","Confusion Matrix",
                 "Precision Evaluation (EP15-A3)"],
        key="analysis_type")

    _WHAT = {
        "Passing–Bablok": "Non-parametric regression · robust to outliers",
        "Deming": "Errors-in-both-variables regression",
        "Confusion Matrix": "Zone diameter agreement · EUCAST / CLSI",
        "Precision Evaluation (EP15-A3)": "Within-run & within-lab imprecision",
    }
    st.caption(_WHAT[analysis_type])

    if analysis_type == "Deming":
        with st.expander("⚙️ Deming options", expanded=True):
            deming_weighted = st.toggle(
                "Weighted Deming", value=False, key="dw",
                help="On: errors proportional to concentration (constant CV). "
                     "Off: equal error variances.")
            error_ratio = st.number_input(
                "Error ratio λ = Var(y)/Var(x)", 0.01, 100.0, 1.0, 0.1, key="er",
                help="λ = 1 means both methods have equal imprecision.")
    else:
        deming_weighted = False
        error_ratio     = 1.0
    st.divider()

    st.markdown("##### ② &nbsp;Load your data")
    if analysis_type == "Precision Evaluation (EP15-A3)":
        st.caption("Upload or paste precision data in the main area →")
        _x_sid=_y_sid=_sid_err=None; uploaded_file=pasted_text=None
        input_mode="📂 Upload file"
    else:
        if analysis_type in ("Passing–Bablok","Deming"):
            _lf_mode=st.radio("Data format",
                ["Single file (two columns)","Two long-format files (match by ID)"],
                key="lf_mode",
                help="Long-format: one file per method with SampleID | Analysis | Result columns.")
        # (else already defaulted above)

        if _lf_mode=="Two long-format files (match by ID)":
            input_mode="📂 Upload file"; uploaded_file=pasted_text=None
            _x_sid=_y_sid=_sid_err=None
            st.markdown("**File A — Reference method**")
            _uf_a=st.file_uploader("Upload reference file",type=["csv","xlsx","xls"],key="lf_fa")
            st.markdown("**File B — Candidate method**")
            _uf_b=st.file_uploader("Upload candidate file",type=["csv","xlsx","xls"],key="lf_fb")
            if _uf_a is not None and _uf_b is not None:
                try:
                    # Cache bytes in session state so re-runs don't hit empty file objects
                    if "lf_rb_a" not in st.session_state or \
                       st.session_state.get("lf_fname_a") != _uf_a.name:
                        st.session_state["lf_rb_a"]    = _uf_a.read()
                        st.session_state["lf_fname_a"] = _uf_a.name
                    if "lf_rb_b" not in st.session_state or \
                       st.session_state.get("lf_fname_b") != _uf_b.name:
                        st.session_state["lf_rb_b"]    = _uf_b.read()
                        st.session_state["lf_fname_b"] = _uf_b.name

                    _rb_a = st.session_state["lf_rb_a"]
                    _rb_b = st.session_state["lf_rb_b"]
                    _lf_hdr_choice = st.radio(
                        "Header row? (applies to both files)",
                        ["Yes (first row)", "No header"],
                        horizontal=True, key="lf_hdr",
                        help="Choose 'No header' if the very first row is already data — "
                             "otherwise that row would be lost.")
                    _lf_has_hdr = _lf_hdr_choice == "Yes (first row)"
                    _lf_df_a=load_long_format(_rb_a, _uf_a.name, has_header=_lf_has_hdr)
                    _lf_df_b=load_long_format(_rb_b, _uf_b.name, has_header=_lf_has_hdr)
                    if not _lf_has_hdr:
                        st.caption("Columns named Column 1, Column 2 … — first row kept as data.")
                    st.markdown("**Column mapping — File A**")
                    _ca2=st.columns(3)
                    _id_a =_ca2[0].selectbox("Sample ID",list(_lf_df_a.columns),key="lf_ida")
                    _an_a =_ca2[1].selectbox("Analysis",["N/A"]+list(_lf_df_a.columns),key="lf_ana")
                    _rs_a =_ca2[2].selectbox("Result",list(_lf_df_a.columns),
                                              index=min(2,len(_lf_df_a.columns)-1),key="lf_rsa")
                    _lf_label_a=st.text_input("Label A","Reference",key="lf_la")
                    st.markdown("**Column mapping — File B**")
                    _cb2=st.columns(3)
                    _id_b =_cb2[0].selectbox("Sample ID",list(_lf_df_b.columns),key="lf_idb")
                    _an_b =_cb2[1].selectbox("Analysis",["N/A"]+list(_lf_df_b.columns),key="lf_anb")
                    _rs_b =_cb2[2].selectbox("Result",list(_lf_df_b.columns),
                                              index=min(2,len(_lf_df_b.columns)-1),key="lf_rsb")
                    _lf_label_b=st.text_input("Label B","Candidate",key="lf_lb")

                    # Analysis column handling
                    _no_analysis=(_an_a=="N/A" or _an_b=="N/A")
                    if _no_analysis:
                        _lf_df_a=_lf_df_a.copy(); _lf_df_a["__analyte__"]="ALL"
                        _lf_df_b=_lf_df_b.copy(); _lf_df_b["__analyte__"]="ALL"
                        _an_a="__analyte__"; _an_b="__analyte__"
                        _lf_analyte="ALL"
                        st.caption("All rows treated as one analyte.")
                    else:
                        _common=get_common_analytes(_lf_df_a,_lf_df_b,_an_a,_an_b)
                        if _common:
                            _lf_analyte=st.selectbox("Analyte to compare",_common,key="lf_analyte")
                        else:
                            st.warning("No common analytes found in both files.")
                            _lf_analyte="ALL"

                    # Duplicate detection
                    _dups_a=find_duplicates(_lf_df_a,_id_a,_an_a,_rs_a)
                    _dups_b=find_duplicates(_lf_df_b,_id_b,_an_b,_rs_b)
                    if not _dups_a.empty or not _dups_b.empty:
                        st.warning(f"⚠️ Duplicates: File A {len(_dups_a)} rows, "
                                   f"File B {len(_dups_b)} rows.")
                        _dup_s=st.radio("Resolve duplicates",
                                        ["Keep first","Keep last","Use mean"],key="lf_dup")
                        _sm={"Keep first":"first","Keep last":"last","Use mean":"mean"}[_dup_s]
                        _lf_df_a=resolve_duplicates(_lf_df_a,_id_a,_an_a,_rs_a,_sm)
                        _lf_df_b=resolve_duplicates(_lf_df_b,_id_b,_an_b,_rs_b,_sm)

                    # Run matching
                    _lf_x_arr,_lf_y_arr,_lf_report_df=match_two_files(
                        _lf_df_a,_lf_df_b,_id_a,_id_b,_an_a,_an_b,_rs_a,_rs_b,
                        _lf_analyte,_lf_label_a,_lf_label_b)
                    _nm=int((_lf_report_df["Match"]=="Matched").sum())
                    _na=int((_lf_report_df["Match"]=="Only in A").sum())
                    _nb=int((_lf_report_df["Match"]=="Only in B").sum())
                    if _nm==0:
                        st.warning("⚠️ No matched pairs — check column mapping.")
                    else:
                        st.success(f"✅ {_nm} matched pairs ready.")
                        st.caption(f"Only in A: {_na}  |  Only in B: {_nb}")
                    _lf_matched_xlsx=build_matched_excel(
                        _lf_report_df,_lf_label_a,_lf_label_b,_lf_analyte)
                except Exception as _e:
                    st.error(f"Matching error: {_e}")
                    _sid_err=str(_e)
        else:
            input_mode=st.radio("Input method",["📂 Upload file","📋 Paste data"],key="imode")
            _x_sid=_y_sid=_sid_err=None; uploaded_file=pasted_text=None
            if input_mode=="📂 Upload file":
                uploaded_file=st.file_uploader("Upload CSV or Excel",type=["csv","xlsx","xls"],key="fup")
                if uploaded_file is not None:
                    try:
                        fname=uploaded_file.name.lower()
                        if fname.endswith((".xlsx",".xls")):
                            import openpyxl
                            _rb=uploaded_file.read(); uploaded_file.seek(0)
                            _wb=openpyxl.load_workbook(BytesIO(_rb),read_only=True,data_only=True)
                            _sn=_wb.sheetnames; _wb.close()
                            _ss=st.selectbox("Sheet / tab",_sn,key="ss")
                            _hc=st.radio("Header row?",["Yes (first row)","No header"],horizontal=True,key="hx")
                            _hdr=_hc=="Yes (first row)"
                            _pv=pd.read_excel(BytesIO(_rb),sheet_name=_ss,header=0 if _hdr else None,nrows=5)
                            if not _hdr: _pv.columns=[f"Column {i+1}" for i in range(len(_pv.columns))]
                            else: _pv.columns=[str(c) for c in _pv.columns]
                            st.caption("Preview (first 5 rows):")
                            st.dataframe(_pv,use_container_width=True)
                            _cols=list(_pv.columns)
                            if len(_cols)>=2:
                                _xc=st.selectbox("Reference column (x)",_cols,0,key="xce")
                                _yc=st.selectbox("Candidate column (y)",_cols,min(1,len(_cols)-1),key="yce")
                                _full=pd.read_excel(BytesIO(_rb),sheet_name=_ss,header=0 if _hdr else None)
                                if not _hdr: _full.columns=[f"Column {i+1}" for i in range(len(_full.columns))]
                                else: _full.columns=[str(c) for c in _full.columns]
                                _full=_apply_filter(_full,exclude_cols=[_xc,_yc],key_prefix="xe")
                                def _tonum(s): return pd.to_numeric(s.astype(str).str.replace(",","."),errors="coerce").values.astype(float)
                                _x_sid=_tonum(_full[_xc]); _y_sid=_tonum(_full[_yc])
                            else: _sid_err="Sheet needs at least 2 columns."
                        else:
                            _rb=uploaded_file.read(); uploaded_file.seek(0)
                            _hc=st.radio("Header row?",["Yes (first row)","No header"],horizontal=True,key="hc")
                            _hdr=_hc=="Yes (first row)"
                            _pv=pd.read_csv(BytesIO(_rb),header=0 if _hdr else None,sep=None,engine="python",decimal=",")
                            if _pv.select_dtypes(include=[np.number]).shape[1]<2:
                                _pv=pd.read_csv(BytesIO(_rb),header=0 if _hdr else None,sep=None,engine="python")
                            if not _hdr: _pv.columns=[f"Column {i+1}" for i in range(len(_pv.columns))]
                            else: _pv.columns=[str(c) for c in _pv.columns]
                            st.caption("Preview (first 5 rows):")
                            st.dataframe(_pv.head(),use_container_width=True)
                            _cols=list(_pv.columns)
                            _xc=st.selectbox("Reference column (x)",_cols,0,key="xcc")
                            _yc=st.selectbox("Candidate column (y)",_cols,min(1,len(_cols)-1),key="ycc")
                            _full=pd.read_csv(BytesIO(_rb),header=0 if _hdr else None,sep=None,engine="python",decimal=",")
                            if _full.select_dtypes(include=[np.number]).shape[1]<2:
                                _full=pd.read_csv(BytesIO(_rb),header=0 if _hdr else None,sep=None,engine="python")
                            if not _hdr: _full.columns=[f"Column {i+1}" for i in range(len(_full.columns))]
                            else: _full.columns=[str(c) for c in _full.columns]
                            _full=_apply_filter(_full,exclude_cols=[_xc,_yc],key_prefix="ce")
                            def _tonum(s): return pd.to_numeric(s.astype(str).str.replace(",","."),errors="coerce").values.astype(float)
                            _x_sid=_tonum(_full[_xc]); _y_sid=_tonum(_full[_yc])
                    except Exception as _e:
                        _sid_err=str(_e)
            else:
                st.markdown("Copy two columns from Excel and paste below.")
                pasted_text=st.text_area("Paste data here",height=160,
                    placeholder="10,2\t10,5\n15,7\t16,1\n...",key="pa")

    st.markdown("##### ③ &nbsp;Name your methods")
    x_label=st.text_input("Reference method (x-axis)","Reference Method",key="xl")
    y_label=st.text_input("Candidate method (y-axis)","Candidate Method",key="yl")
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
        st.markdown("##### ④ &nbsp;Plot options")

        # -- Essentials: visible without opening anything ---------------------
        decimals = st.slider("Decimal places", 1, 8, 2, key="dec")
        ba_pct_diff = st.toggle(
            "Bland–Altman as % difference", value=False, key="bap",
            help="Off: absolute difference (y − x). On: percentage of the mean.")

        # -- Titles ------------------------------------------------------------
        with st.expander("🏷️ Titles"):
            pb_title = st.text_input(
                "Regression plot", value="",
                placeholder="Leave blank for automatic title", key="pbt")
            ba_title_input = st.text_input(
                "Bland–Altman plot", value="",
                placeholder="Leave blank for automatic title", key="bat")

        # -- Axis ranges -------------------------------------------------------
        with st.expander("📐 Axis ranges"):
            st.caption("Leave any field blank for automatic scaling.")
            st.markdown("**Regression plot**")
            _a=st.columns(2)
            pb_x_min=_pa(_a[0].text_input("X min","0",key="pxn"))
            pb_x_max=_pa(_a[1].text_input("X max","",key="pxx"))
            pb_y_min=_pa(_a[0].text_input("Y min","0",key="pyn"))
            pb_y_max=_pa(_a[1].text_input("Y max","",key="pyx"))
            st.markdown("**Bland–Altman plot**")
            _b=st.columns(2)
            ba_x_min=_pa(_b[0].text_input("X min","",key="bxn"))
            ba_x_max=_pa(_b[1].text_input("X max","",key="bxx"))
            ba_y_min=_pa(_b[0].text_input("Y min","",key="byn"))
            ba_y_max=_pa(_b[1].text_input("Y max","",key="byx"))

        # -- Colours -----------------------------------------------------------
        with st.expander("🎨 Colours"):
            st.markdown("**Regression plot**")
            _c1=st.columns(3)
            with _c1[0]:
                pb_color_scatter=st.color_picker("Points","#2563EB",key="pcs")
            with _c1[1]:
                pb_color_identity=st.color_picker("Identity","#9CA3AF",key="pci")
            with _c1[2]:
                pb_color_regression=st.color_picker("Fit","#DC2626",key="pcr")
            pb_show_ci  = st.toggle("Show 95% CI band", value=True, key="psc")
            _c2=st.columns([1,2])
            with _c2[0]:
                pb_color_ci=st.color_picker("CI band","#DC2626",key="pcc")
            with _c2[1]:
                pb_ci_alpha=st.slider("CI transparency",0.0,1.0,0.15,0.01,key="pca")

            st.markdown("**Bland–Altman plot**")
            _c3=st.columns(3)
            with _c3[0]:
                ba_color_scatter=st.color_picker("Points","#2563EB",key="bcs")
            with _c3[1]:
                ba_color_mean=st.color_picker("Mean bias","#DC2626",key="bcm")
            with _c3[2]:
                ba_color_loa=st.color_picker("LoA","#F97316",key="bcl")

        # -- Legend & annotation text -----------------------------------------
        with st.expander("✏️ Legend & label text"):
            st.markdown("**Regression plot**")
            pb_legend_scatter   =st.text_input("Points",   "Observations",     key="pls")
            pb_legend_identity  =st.text_input("Identity", "Identity (y = x)", key="pli")
            pb_legend_regression=st.text_input("Fit line", "Regression",       key="plr")
            pb_legend_ci        =st.text_input("CI band",  "95% CI",           key="plc")
            st.markdown("**Bland–Altman plot**")
            ba_legend_scatter =st.text_input("Points",     "Difference", key="bls")
            ba_label_mean     =st.text_input("Mean line",  "Mean",       key="blm")
            ba_label_loa_upper=st.text_input("Upper LoA",  "+1,96 SD",   key="blu")
            ba_label_loa_lower=st.text_input("Lower LoA",  "−1,96 SD",   key="bll")

    elif analysis_type == "Confusion Matrix":
        st.markdown("##### ④ &nbsp;Breakpoints")
        bp_system=st.selectbox("Breakpoint system",["EUCAST","CLSI"],key="bps",
            help="Determines the S / I / R categories used for "
                 "categorical agreement, VME and ME.")
        st.caption(f"**{x_label}**")
        _bp1=st.columns(2)
        bp_s_x=_bp1[0].number_input("S ≥ (mm)",value=20.0,step=0.5,key="bsx")
        bp_r_x=_bp1[1].number_input("R ≤ (mm)",value=16.0,step=0.5,key="brx")
        st.caption(f"**{y_label}**")
        _bp2=st.columns(2)
        bp_s_y=_bp2[0].number_input("S ≥ (mm)",value=20.0,step=0.5,key="bsy")
        bp_r_y=_bp2[1].number_input("R ≤ (mm)",value=16.0,step=0.5,key="bry")
        st.divider()

        st.markdown("##### ⑤ &nbsp;Matrix options")

        # -- Essentials --------------------------------------------------------
        cm_step=st.number_input("Step size (mm per cell)",1,10,1,1,key="cms",
            help="1 = one cell per millimetre.")
        cm_ea_window =st.selectbox("Essential agreement band (± mm)",[1,2,3],
            index=1,key="cea",
            help="Draws the dotted boundary lines either side of the diagonal.")

        # -- Layout ------------------------------------------------------------
        with st.expander("📐 Range & layout"):
            st.caption("Leave blank for automatic range.")
            _cc=st.columns(2)
            cm_x_min=_ca(_cc[0].text_input("X min","",placeholder="auto",key="cxn"))
            cm_x_max=_ca(_cc[1].text_input("X max","",placeholder="auto",key="cxx"))
            cm_y_min=_ca(_cc[0].text_input("Y min","",placeholder="auto",key="cyn"))
            cm_y_max=_ca(_cc[1].text_input("Y max","",placeholder="auto",key="cyx"))
            cm_show_diag  =st.toggle("Show diagonal lines",value=True,key="csd")
            cm_show_totals=st.toggle("Show n = total (outside frame)",
                                     value=True,key="cst")

        # -- Title -------------------------------------------------------------
        with st.expander("🏷️ Title"):
            cm_title=st.text_input("Matrix title",
                "Zone Diameter Comparison Matrix",key="ctt")

        # -- Colours -----------------------------------------------------------
        with st.expander("🎨 Colours"):
            cm_base_color=st.color_picker("Matrix colour","#1D4ED8",key="cbc")
            cm_scale_max =st.slider("Coloured bands (mm from diagonal)",
                1,10,2,key="csc",
                help="How far from perfect agreement the shading extends.")

        # -- Cell numbers ------------------------------------------------------
        with st.expander("🔢 Cell numbers"):
            cm_font_size=st.slider("Font size",6,16,11,key="cfs")
            cm_num_bold =st.toggle("Bold",value=True,key="cnbd")
            _nc=st.columns(2)
            with _nc[0]:
                cm_num_color_on_blue =st.color_picker(
                    "On shaded cells","#1E3A5F",key="cnb")
            with _nc[1]:
                cm_num_color_on_white=st.color_picker(
                    "On white cells","#1E3A5F",key="cnw")

    else:   # Precision Evaluation (EP15-A3)
        st.markdown("##### ④ &nbsp;Precision options")
        st.caption("EP15-A3 recommends 5 replicates × 5 days "
                   "(minimum 2 × 2).")

        prec_decimals = st.slider("Decimal places", 1, 6, 4, key="pr_dec")

        with st.expander("📊 Statistical settings"):
            prec_alpha = st.selectbox("Significance level (α)",
                [0.05, 0.01], index=0,
                format_func=lambda v: f"{v:.0%}", key="pr_alpha",
                help="False-rejection rate for the chi-square verification.")
            prec_n_levels = st.number_input("Concentration levels tested (q)",
                min_value=1, max_value=5, value=1, step=1, key="pr_q",
                help="Bonferroni correction for testing several levels at once.")

        with st.expander("🏭 Manufacturer claims (optional)"):
            st.caption("Enter the claimed SDs to run the chi-square "
                       "verification. Leave at 0 to skip.")
            _csr=st.number_input("Claimed repeatability SD (σr)",
                                 min_value=0.0, value=0.0, step=0.001,
                                 format="%.4f", key="pr_csr")
            _csl=st.number_input("Claimed within-lab SD (σl)",
                                 min_value=0.0, value=0.0, step=0.001,
                                 format="%.4f", key="pr_csl")
        prec_claimed_sr = _csr if _csr > 0 else None
        prec_claimed_sl = _csl if _csl > 0 else None

    st.divider()
    if st.button("↻ Reset all settings", use_container_width=True,
                 help="Restores every option to its default. Your uploaded "
                      "file stays loaded."):
        _keep = {"lf_rb_a","lf_rb_b","lf_fname_a","lf_fname_b"}
        for _k in [k for k in st.session_state.keys() if k not in _keep]:
            del st.session_state[_k]
        st.rerun()

    with st.expander("📚 References"):
        st.caption(
            "Passing & Bablok, *J Clin Chem Clin Biochem* 1983  \n"
            "Deming, *Statistical Adjustment of Data* 1943  \n"
            "Linnet, *Stat Med* 1990  \n"
            "Bland & Altman, *Lancet* 1986  \n"
            "CLSI EP15-A3 2014 · CLSI M52 · EUCAST v10.0")


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
    x_raw = y_raw = np.array([1.0, 2.0])  # dummy — precision has its own input
elif _lf_mode == "Two long-format files (match by ID)":
    if _sid_err:
        st.error(f"Could not match files: {_sid_err}")
        st.stop()
    if _lf_x_arr is None or len(_lf_x_arr) == 0:
        st.info("👈 Upload both files and configure the column mapping in the sidebar.")
        st.stop()
    if len(_lf_x_arr) < 3:
        st.error(f"Only {len(_lf_x_arr)} matched pair(s) — need at least 3 for regression.")
        st.stop()
    x_raw  = _lf_x_arr
    y_raw  = _lf_y_arr
    x_label = _lf_label_a
    y_label  = _lf_label_b
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

    # ── Analyze: store the FULL dataset; exclusions are applied afterwards ────
    if st.button("▶ Analyze", type="primary"):
        st.session_state["x_all"]      = x_raw.copy()
        st.session_state["y_all"]      = y_raw.copy()
        st.session_state["reg_method"] = method_label
        st.session_state["excl_multi"] = []
        st.session_state["reg_ready"]  = True

    if not st.session_state.get("reg_ready"):
        st.info("👆 Click **Analyze** to run the regression.")
        st.stop()

    _x_all = st.session_state["x_all"]
    _y_all = st.session_state["y_all"]
    _n_all = len(_x_all)

    # Exclusions live in ONE place: the multiselect widget's session_state key.
    # Reading/writing that key everywhere avoids the widget resetting them on rerun.
    if st.session_state.get("excl_n") != _n_all:
        st.session_state["excl_multi"] = []
        st.session_state["excl_n"] = _n_all
    st.session_state.setdefault("excl_multi", [])

    _excl = {i for i in st.session_state["excl_multi"] if 0 <= i < _n_all}
    _kept = [i for i in range(_n_all) if i not in _excl]

    if len(_kept) < 3:
        st.error(f"Only {len(_kept)} point(s) remain — need at least 3. "
                 "Restore some points below.")
        if st.button("↺ Restore all points", key="restore_all_err"):
            st.session_state["excl_multi"] = []
            st.rerun()
        st.stop()

    _x = _x_all[_kept]
    _y = _y_all[_kept]

    # ── Recompute on the kept points (cached by exclusion signature) ──────────
    _sig = (analysis_type, deming_weighted, float(error_ratio),
            tuple(sorted(_excl)), _n_all)
    if st.session_state.get("reg_sig") != _sig:
        try:
            if analysis_type=="Passing–Bablok":
                _r=passing_bablok(_x,_y)
            elif deming_weighted:
                _r=weighted_deming(_x,_y,error_ratio=error_ratio)
            else:
                _r=deming(_x,_y,error_ratio=error_ratio)
            st.session_state["reg_res"] = _r
            st.session_state["stats"]   = summary_stats(_x,_y)
            st.session_state["reg_sig"] = _sig
        except ValueError as e:
            st.error(f"Analysis failed: {e}")
            st.stop()

    rr=st.session_state["reg_res"]
    ss=st.session_state["stats"]

    if _excl:
        st.info(f"**{len(_excl)} point(s) excluded** — "
                f"statistics and both plots use the remaining {len(_kept)} of {_n_all}.")

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

    def _scatter_trace_idx(fig):
        """Index of the first markers-only trace (the data points)."""
        for i, tr in enumerate(fig.data):
            if getattr(tr, "mode", None) == "markers":
                return i
        return 0

    def _handle_selection(event, fig, kept):
        """Map selected trace positions back to original indices and exclude them."""
        try:
            pts = event.selection["points"]
        except Exception:
            return False
        if not pts:
            return False
        s_idx = _scatter_trace_idx(fig)
        newly = set()
        for p in pts:
            if p.get("curve_number") != s_idx:
                continue
            pos = p.get("point_index")
            if pos is not None and 0 <= pos < len(kept):
                newly.add(kept[pos])
        current = {i for i in st.session_state.get("excl_multi", [])}
        if newly and not newly.issubset(current):
            st.session_state["excl_multi"] = sorted(current | newly)
            return True
        return False

    _fig_pb_live = make_regression_plot(_x,_y,**_pkw)
    _fig_ba_live = make_bland_altman_plot(_x,_y,**_bkw)

    st.caption("💡 Click a point, or drag a box/lasso, to exclude it from both "
               "plots and all statistics.")

    with _cp:
        _ev_pb = st.plotly_chart(
            _fig_pb_live, use_container_width=True,
            on_select="rerun", selection_mode=("points","box","lasso"),
            key="sel_pb")
    with _cb:
        _ev_ba = st.plotly_chart(
            _fig_ba_live, use_container_width=True,
            on_select="rerun", selection_mode=("points","box","lasso"),
            key="sel_ba")

    _changed = False
    if _ev_pb is not None:
        _changed |= _handle_selection(_ev_pb, _fig_pb_live, _kept)
    if _ev_ba is not None:
        _changed |= _handle_selection(_ev_ba, _fig_ba_live, _kept)
    if _changed:
        st.rerun()

    # ── Manual exclusion list (fallback + undo) ───────────────────────────────
    with st.expander(f"🗑 Excluded points ({len(_excl)})", expanded=bool(_excl)):
        _opts = list(range(_n_all))
        def _lbl(i):
            return f"#{i+1}:  {fmt(float(_x_all[i]),decimals)} / {fmt(float(_y_all[i]),decimals)}"
        # No `default=` — the widget's session_state key IS the source of truth,
        # so a rerun from any other button cannot wipe the exclusions.
        _picked = st.multiselect(
            "Excluded from analysis (add or remove here)",
            options=_opts, format_func=_lbl, key="excl_multi")
        if set(_picked) != _excl:
            st.rerun()
        if _excl and st.button("↺ Restore all points", key="restore_all"):
            st.session_state["excl_multi"] = []
            st.rerun()

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
    _csv_txt = results_to_csv(rr,ss)
    _csv_txt += (f"\nPoints used,{len(_kept)}\nPoints excluded,{len(_excl)}\n"
                 f"Total points,{_n_all}\n")
    if _excl:
        _csv_txt += ("Excluded point numbers,"
                     + " ".join(str(i+1) for i in sorted(_excl)) + "\n")
    _f1.download_button("📥 Results CSV", text_to_csv_bytes(_csv_txt),
                        "results.csv", "text/csv", key="rcsv")
    _f2.download_button("📄 HTML Report",
        build_html_report(rr,ss,fig_pb,fig_ba,x_label=x_label,y_label=y_label),
        "report.html","text/html",key="rhtml")

    # ── Matched pairs Excel — rebuilt here so it reflects exclusions ──────────
    if _lf_mode=="Two long-format files (match by ID)" and _lf_report_df is not None:
        _rep_out = _lf_report_df.copy()
        _rep_out["Status"] = ""
        # Matched rows, after dropping NaN pairs, line up positionally with
        # _x_all / _y_all — tag each one Included or Excluded.
        _m_idx = _rep_out.index[_rep_out["Match"] == "Matched"].tolist()
        _va = pd.to_numeric(_rep_out.loc[_m_idx, _lf_label_a], errors="coerce").values
        _vb = pd.to_numeric(_rep_out.loc[_m_idx, _lf_label_b], errors="coerce").values
        _ok = [_m_idx[k] for k in range(len(_m_idx))
               if np.isfinite(_va[k]) and np.isfinite(_vb[k])]
        for _pos, _ridx in enumerate(_ok):
            if _pos < _n_all:
                _rep_out.at[_ridx, "Status"] = (
                    "Excluded" if _pos in _excl else "Included")

        _xlsx_out = build_matched_excel(
            _rep_out, _lf_label_a, _lf_label_b, _lf_analyte)

        st.markdown("**Matched pairs data**")
        _fx1,_fx2,_=st.columns([1,1,2])
        _fx1.download_button(
            "📊 Download matched pairs (Excel)",
            _xlsx_out,
            f"matched_pairs_{_lf_analyte}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="lf_dl_xlsx",
        )
        _fx2.caption(
            f"Analyte: **{_lf_analyte}** — Sheet 1 matched pairs with "
            f"Included/Excluded status, Sheet 2 only in {_lf_label_a}, "
            f"Sheet 3 only in {_lf_label_b}"
        )


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
    _m4.metric("VME (R→S)", f"{ca['vme']:.1f}%",
               f"{ca['n_vme']} of {ca['n_r_ref']} R",delta_color="inverse",
               help="Very major error = false susceptibility. Reference "
                    "resistant, candidate susceptible. Percentage of "
                    "RESISTANT isolates. CLSI/FDA limit 1.5–3 %.")
    _m5.metric("ME (S→R)",  f"{ca['me']:.1f}%",
               f"{ca['n_me']} of {ca['n_s_ref']} S",delta_color="inverse",
               help="Major error = false resistance. Reference susceptible, "
                    "candidate resistant. Percentage of SUSCEPTIBLE isolates. "
                    "CLSI/FDA limit 3 %.")
    if ca["n_minor"]>0:
        st.caption(f"Minor errors: {ca['n_minor']} ({ca['minor_e']:.1f}%)")

    with st.expander("ℹ️ Acceptability thresholds"):
        st.markdown("""
| Metric | EUCAST | CLSI |
|---|---|---|
| Essential Agreement ±2 mm | ≥ 90 % | ≥ 90 % |
| Categorical Agreement | ≥ 90 % | ≥ 90 % |
| Very major error (false susceptible, R→S) | ≤ 3 % of **R** isolates | ≤ 1.5 % of **R** |
| Major error (false resistant, S→R) | ≤ 3 % of **S** isolates | ≤ 3 % of **S** |
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
    _d2.download_button("📥 Matrix CSV",
                        to_csv_bytes(_mdf, index=True),
                        "confusion_matrix.csv","text/csv",key="ccsv")


# ══════════════════════════════════════════════════════════════════════════════
# BRANCH C — Precision Evaluation (EP15-A3)
# ══════════════════════════════════════════════════════════════════════════════
else:
    st.subheader("Precision Evaluation — CLSI EP15-A3")

    _pr_tab1, _pr_tab2, _pr_tab3 = st.tabs([
        "📂 Wide format (columns = days)",
        "📋 Paste wide format",
        "🔍 Long format (search by Sample ID)",
    ])

    _pr_data_dict = None
    _prlf_raw_df  = None
    _prlf_sample_id = ""; _prlf_analyte_sel = ""

    with _pr_tab1:
        st.caption("Each column = one day, each row = one replicate. Column headers = day names.")
        _pr_file = st.file_uploader("Upload Excel or CSV",type=["csv","xlsx","xls"],key="pr_file")
        if _pr_file is not None:
            try:
                _pr_rb = _pr_file.read()
                if _pr_file.name.lower().endswith((".xlsx",".xls")):
                    _pr_df = pd.read_excel(BytesIO(_pr_rb), header=0)
                else:
                    _pr_df = pd.read_csv(BytesIO(_pr_rb), sep=None, engine="python")
                _pr_df.columns = [f"Column {i+1}" if str(c).strip().lstrip("-").isdigit()
                                   else str(c) for i,c in enumerate(_pr_df.columns)]
                st.caption(f"Preview — {len(_pr_df)} replicates × "
                           f"{len(_pr_df.columns)} days (all rows shown):")
                st.dataframe(_pr_df, use_container_width=True)
                _pr_data_dict = precision_from_dataframe(_pr_df)
            except Exception as _e:
                st.error(f"Could not read file: {_e}")

    with _pr_tab2:
        st.markdown("Copy from Excel (columns = days) and paste below.")
        _pr_paste = st.text_area("Paste here", height=180,
            placeholder="Day 1\tDay 2\tDay 3\tDay 4\tDay 5\n2,015\t2,019\t2,025\t1,972\t1,981",
            key="pr_paste")
        if _pr_paste and _pr_paste.strip():
            try:
                from io import StringIO as _SIO
                _pr_df2 = pd.read_csv(_SIO(_pr_paste), sep="\t", decimal=",")
                if _pr_df2.shape[1] < 2:
                    _pr_df2 = pd.read_csv(_SIO(_pr_paste), sep="\t")
                _pr_df2.columns = [str(c) for c in _pr_df2.columns]
                st.caption(f"Preview — {len(_pr_df2)} replicates × "
                           f"{len(_pr_df2.columns)} days (all rows shown):")
                st.dataframe(_pr_df2, use_container_width=True)
                _pr_data_dict = precision_from_dataframe(_pr_df2)
            except Exception as _e:
                st.error(f"Could not parse: {_e}")

    with _pr_tab3:
        st.markdown(
            "Upload a long-format file with **SampleID | Analysis | Result** columns. "
            "Search for a Sample ID and split results into days automatically.")
        _lf_pr_file = st.file_uploader("Upload long-format file",
                                        type=["csv","xlsx","xls"], key="lf_pr_file")
        if _lf_pr_file is not None:
            try:
                _lf_pr_rb  = _lf_pr_file.read()
                _pr_hdr_choice = st.radio(
                    "Header row?", ["Yes (first row)", "No header"],
                    horizontal=True, key="lf_pr_hdr",
                    help="Choose 'No header' if the very first row is already data.")
                _pr_has_hdr = _pr_hdr_choice == "Yes (first row)"
                _lf_pr_df  = load_long_format(_lf_pr_rb, _lf_pr_file.name,
                                              has_header=_pr_has_hdr)
                if not _pr_has_hdr:
                    st.caption("Columns named Column 1, Column 2 … — first row kept as data.")
                _lf_pr_cols= list(_lf_pr_df.columns)
                _lfc=st.columns(3)
                _lf_pr_id_col  =_lfc[0].selectbox("Sample ID column",_lf_pr_cols,key="lf_pr_id")
                _lf_pr_res_col =_lfc[1].selectbox("Result column",_lf_pr_cols,
                                                    index=min(2,len(_lf_pr_cols)-1),key="lf_pr_res")
                _lf_pr_sort_col=_lfc[2].selectbox("Sort by (run order/date)",
                                                    ["N/A"]+_lf_pr_cols,key="lf_pr_sort")
                _lf_pr_sort=None if _lf_pr_sort_col=="N/A" else _lf_pr_sort_col
                _an_cols=[c for c in _lf_pr_cols if c not in [_lf_pr_id_col,_lf_pr_res_col]]
                _lf_pr_an_col=st.selectbox("Analysis",
                                            ["N/A"]+_an_cols,key="lf_pr_an")
                _lf_pr_analyte=None
                if _lf_pr_an_col != "N/A":
                    _an_avail=sorted(_lf_pr_df[_lf_pr_an_col].dropna().astype(str).unique())
                    _lf_pr_analyte=st.selectbox("Select analyte",_an_avail,key="lf_pr_analyte_sel")
                    _prlf_analyte_sel=_lf_pr_analyte or ""
                _all_ids=sorted(_lf_pr_df[_lf_pr_id_col].dropna().astype(str).unique())
                _prlf_sample_id=st.selectbox("Select Sample ID",_all_ids,key="lf_pr_sid")
                # How are days defined?
                _pr_grp_mode = st.radio(
                    "How are days defined?",
                    ["Group by a date / day column", "Split every N results"],
                    key="lf_pr_grpmode",
                    help="If your file has a Date column, grouping by it is "
                         "safer — the number of replicates per day can differ "
                         "between analytes.")
                _lf_pr_group = None
                _lf_pr_n = 5
                if _pr_grp_mode == "Group by a date / day column":
                    _grp_opts = [c for c in _lf_pr_cols if c != _lf_pr_res_col]
                    _dflt = 0
                    for _i, _c in enumerate(_grp_opts):
                        if "date" in str(_c).lower() or "day" in str(_c).lower():
                            _dflt = _i; break
                    _lf_pr_group = st.selectbox("Day column", _grp_opts,
                                                index=_dflt, key="lf_pr_grpcol")
                else:
                    _lf_pr_n=st.number_input("Results per day (n)",
                                              min_value=2,max_value=50,
                                              value=5,step=1,key="lf_pr_n")
                _prev_mask=_lf_pr_df[_lf_pr_id_col].astype(str)==_prlf_sample_id
                if _lf_pr_analyte and _lf_pr_an_col != "N/A":
                    _prev_mask&=_lf_pr_df[_lf_pr_an_col].astype(str)==_lf_pr_analyte
                st.caption(f"Preview — {_prev_mask.sum()} rows for this sample:")
                st.dataframe(_lf_pr_df[_prev_mask].head(10),use_container_width=True)
                _prlf_dd,_prlf_raw_df,_prlf_nl=extract_precision_replicates(
                    _lf_pr_df,_lf_pr_id_col,_lf_pr_res_col,_prlf_sample_id,
                    sort_col=_lf_pr_sort,
                    analysis_col=_lf_pr_an_col if _lf_pr_an_col!="N/A" else None,
                    analyte=_lf_pr_analyte,
                    n_per_day=int(_lf_pr_n),
                    group_col=_lf_pr_group,
                )
                _pr_data_dict=_prlf_dd
                if _prlf_nl>0:
                    st.warning(f"⚠️ {_prlf_nl} trailing result(s) excluded (incomplete day).")
                _nrep = len(next(iter(_prlf_dd.values())))
                st.success(f"✅ {len(_prlf_dd)} days × {_nrep} replicates ready.")
            except Exception as _e:
                st.error(f"Error: {_e}")

    if _pr_data_dict is None:
        st.info("Choose a data source above to begin the precision analysis.")
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

    if _pr["sb2"] <= 0:
        st.info(
            "**Between-day variance estimated as zero**, so the within-run and "
            "within-laboratory figures are identical. This is a valid ANOVA "
            "result, not an error: the scatter between day means "
            f"(s²day = {_pr['s_day2']:.6g}) is smaller than what within-run "
            f"noise alone would produce (S²r/n = {_pr['sr2']/_pr['n']:.6g}), "
            "so the negative variance component is truncated to zero "
            "(CLSI EP15-A3). It usually means there is no detectable "
            "day-to-day effect — check that your days are grouped correctly.")

    # ── Simple pooled SD/CV, shown beneath the CLSI figures ──────────────────
    st.markdown("")
    st.markdown("""
<div style="background:#F8FAFC;border-radius:12px;padding:16px 24px;
            border:1px solid #E2E8F0;border-left:4px solid #94A3B8">
<p style="margin:0;font-size:0.78rem;color:#475569;font-weight:600;letter-spacing:0.05em">
TOTAL IMPRECISION — SIMPLE POOLED CALCULATION (all {nm} results as one set)</p>
<p style="margin:4px 0 0;font-size:1.5rem;font-weight:700;color:#334155">
CV = {cv} %</p>
<p style="margin:2px 0 0;font-size:1rem;color:#64748B">SD = {sd}</p>
<p style="margin:8px 0 0;font-size:0.75rem;color:#64748B">
df = {df} &nbsp;|&nbsp; ordinary SD of every measurement, day structure ignored</p>
</div>
""".format(nm=_pr["n_total_meas"], cv=_pf(_pr["pooled_cv"]),
           sd=_pf(_pr["pooled_sd"]), df=_pr["pooled_df"]),
        unsafe_allow_html=True)

    with st.expander("ℹ️ Why does this differ from the CLSI value?"):
        st.markdown(f"""
The **CLSI within-laboratory SD** separates the data into a within-run and a
between-day component and adds them on the variance scale
(Sl² = Sr² + Sb²). The **simple pooled SD** ignores the day structure and
treats all {_pr['n_total_meas']} results as a single sample.

The two are related exactly, in expectation, by

E[s²pooled] = Sr² + **{_pr['pooled_shrink']:.4f}** × Sb²  where the factor is (D−1)n / (Dn−1)

So the simple calculation shrinks the between-day component by
**{100*(1-_pr['pooled_shrink']):.1f} %** with your design of
{_pr['D']} days × {_pr['n']} replicates. Consequences:

- If there is **no** day-to-day effect (Sb² = 0) the two agree closely.
- If a real day effect exists, the pooled value is **biased low** and
  understates the imprecision a clinician would encounter between days.
- The gap narrows as the number of days increases.

Report the **CLSI value** for method validation and verification against a
manufacturer's claim. The pooled figure is provided for reference and for
comparison with sources that use the simplified approach.
""")

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
            {"Component": "Simple pooled (all results)",
             "SD":     _pf(_pr["pooled_sd"]),
             "CV (%)": _pf(_pr["pooled_cv"]),
             "Variance (SD²)": _pf(_pr["pooled_sd"]**2),
             "df":     str(_pr["pooled_df"])},
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
        {"Day": "Simple pooled (all results)ᵈ",
         **{f"Rep {i+1}": "" for i in range(_n_reps)},
         "Mean": "", "SD": _pf(_pr["pooled_sd"]), "CV (%)": _pf(_pr["pooled_cv"])},
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
        f"ᵈ Ordinary SD of all {_pr['n_total_meas']} results, day structure "
        f"ignored (df = {_pr['pooled_df']}). Shown for reference; it shrinks "
        f"the between-day component by a factor "
        f"{_pr['pooled_shrink']:.3f} and is therefore biased low when a "
        f"day effect exists.",
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
        to_csv_bytes(_dl_df, index=True),
        "precision_journal_table.csv",
        "text/csv",
        key="pr_journal_csv",
    )

    # Excel download — includes raw replicates + summary sheet
    # Available when data came from long-format search (has _prlf_raw_df)
    # or always from the data dict
    try:
        _pr_raw_for_xl = _prlf_raw_df if _prlf_raw_df is not None else pd.DataFrame(
            {day: pd.Series(vals) for day, vals in _pr_data_dict.items()}
        )
        _pr_xlsx = build_precision_excel(
            _pr_raw_for_xl, _pr,
            sample_id=_prlf_sample_id or "—",
            analyte=_prlf_analyte_sel or "—",
            decimals=prec_decimals,
        )
        st.download_button(
            "📊 Download Excel (raw data + summary)",
            _pr_xlsx,
            "precision_results.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pr_xl",
        )
    except Exception as _e:
        st.caption(f"Excel export unavailable: {_e}")
