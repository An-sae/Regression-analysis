"""
Method Comparison Tool — crash-proof rewrite
Three analysis types: Passing-Bablok | Deming | Confusion Matrix
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

def _read_excel(raw, sheet, hdr, xc, yc):
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
        ["Passing–Bablok","Deming","Confusion Matrix"], key="analysis_type")

    if analysis_type == "Deming":
        deming_weighted = st.toggle("Weighted Deming", value=False, key="dw")
        error_ratio     = st.number_input("Error ratio λ=Var(y)/Var(x)",
                                          0.01, 100.0, 1.0, 0.1, key="er")
    else:
        deming_weighted = False
        error_ratio     = 1.0
    st.divider()

    st.subheader("Data input")
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
                    _pv.columns=[str(c) for c in _pv.columns]
                    st.caption("Preview (first 5 rows):")
                    st.dataframe(_pv, use_container_width=True)
                    _cols=list(_pv.columns)
                    if len(_cols)>=2:
                        _xc=st.selectbox("Reference column (x)",_cols,0,key="xce")
                        _yc=st.selectbox("Candidate column (y)",_cols,min(1,len(_cols)-1),key="yce")
                        _x_sid,_y_sid=_read_excel(_rb,_ss,_hdr,_xc,_yc)
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
                    _pv.columns=[str(c) for c in _pv.columns]
                    st.caption("Preview (first 5 rows):")
                    st.dataframe(_pv.head(), use_container_width=True)
                    _cols=list(_pv.columns)
                    _xc=st.selectbox("Reference column (x)",_cols,0,key="xcc")
                    _yc=st.selectbox("Candidate column (y)",_cols,min(1,len(_cols)-1),key="ycc")
                    _x_sid,_y_sid=_read_csv(_rb,_hdr,_xc,_yc)
            except Exception as e:
                _sid_err=str(e)
    else:
        st.markdown("Copy two columns from Excel and paste below.")
        pasted_text=st.text_area("Paste data here",height=160,
                                 placeholder="10,2\t10,5\n15,7\t16,1\n...",key="pa")
    st.divider()

    st.subheader("Method names")
    x_label=st.text_input("Reference method","Reference Method",key="xl")
    y_label=st.text_input("Candidate method","Candidate Method",key="yl")
    st.divider()

    # ── Safe defaults for ALL branch-specific variables ───────────────────────
    pb_title="Passing–Bablok Method Comparison"; ba_title_input=""
    decimals=4
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

    # ── Override defaults with real widgets for active analysis ───────────────
    if analysis_type in ("Passing–Bablok","Deming"):
        _dt={
            "Passing–Bablok":"Passing–Bablok Method Comparison",
            "Deming":"Weighted Deming Method Comparison" if deming_weighted
                     else "Deming Method Comparison"
        }[analysis_type]
        st.subheader("Graph titles")
        pb_title      =st.text_input("Regression title",value=_dt,key="pbt")
        ba_title_input=st.text_input("Bland–Altman title",value="",
                                     placeholder="Leave blank for auto",key="bat")
        st.divider()
        st.subheader("Decimal places")
        decimals=st.slider("Decimals",1,8,4,key="dec")
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

    else:   # Confusion Matrix
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

    st.divider()
    st.caption("Passing & Bablok 1983 · Deming 1943 · Linnet 1990")


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
            st.info("👈 Upload a CSV or Excel file in the sidebar.")
            with st.expander("📄 Expected format"):
                st.dataframe(pd.DataFrame({"reference":[10.2,15.7,8.3],
                                           "candidate":[10.5,16.1,8.0]}),
                             use_container_width=True)
            return None,None
        if _x_sid is None or _y_sid is None:
            st.info("👈 Select the columns to use in the sidebar.")
            return None,None
        return _x_sid, _y_sid
    else:
        if not pasted_text or not pasted_text.strip():
            st.info("👈 Paste your data in the sidebar.")
            return None,None
        try:
            _df=parse_pasted(pasted_text)
            st.success(f"✅ Parsed {len(_df)} rows.")
            return _df["reference"].values, _df["candidate"].values
        except ValueError as e:
            st.error(str(e)); return None,None

x_raw, y_raw = _get_data()
if x_raw is None:
    st.stop()

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
    _pkw=dict(slope=rr["slope"],intercept=rr["intercept"],
              slope_lower=rr["slope_lower"],slope_upper=rr["slope_upper"],
              intercept_lower=rr["intercept_lower"],intercept_upper=rr["intercept_upper"],
              r_squared=ss["r_squared"],x_label=x_label,y_label=y_label,title=pb_title,
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
else:
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
