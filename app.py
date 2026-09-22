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
from analysis.fourfold import (fourfold, fourfold_from_arrays,
                               check_prerequisites)
from plots.fourfold_plot import fourfold_html, build_fourfold_excel
from analysis.precision import compute_precision, precision_from_dataframe
from version import VERSION, VALIDATED_ON, version_string, stamp
from i18n import t, LANGUAGES, DEFAULT_LANG
from analysis.file_reader import (list_sheets, guess_column, suggest_analyte,
                                  parse_numeric as _parse_numeric)
from analysis.data_loader import (
    load_long_format, match_two_files, get_common_analytes,
    find_duplicates, list_analytes, MultipleResultsError,
    extract_precision_replicates,
    build_matched_excel, build_precision_excel,
)

st.set_page_config(page_title="Method Comparison Tool", page_icon="📊", layout="wide")


# ── Optional password protection ─────────────────────────────────────────────
# Active ONLY if .streamlit/secrets.toml exists and contains a "password" key.
# Running locally with no secrets.toml -> no password, nothing changes.
# Needed when the app is shared over a network (see DELNING.txt).
def _check_password() -> bool:
    try:
        expected = st.secrets["password"]
    except Exception:
        return True                      # no password configured
    if not expected:
        return True
    if st.session_state.get("_auth_ok"):
        return True

    st.markdown(t("### 🔒 Method Comparison Tool"))
    st.caption(t("Enter password to continue."))
    with st.form("login", clear_on_submit=False):
        pw = st.text_input(t("Password"), type="password")
        ok = st.form_submit_button("Logga in")
    if ok:
        # constant-time comparison
        import hmac
        if hmac.compare_digest(str(pw), str(expected)):
            st.session_state["_auth_ok"] = True
            st.rerun()
        else:
            st.error(t("Incorrect password."))
    st.stop()


_check_password()

# ── pure helpers ───────────────────────────────────────────────────────────────
def _num_col(series) -> np.ndarray:
    """Tal per kolumn: decimaltecken avgörs av hela kolumnen, flaggor och
    enheter skiljs av, '<' och '>' samt text blir NaN (analysis.file_reader)."""
    vals, _ = _parse_numeric(pd.Series(series).astype(object).where(
        pd.Series(series).notna(), "").astype(str).reset_index(drop=True))
    return vals["value"].values.astype(float)


def parse_pasted(text):
    """Klistrade data: två kolumner (tabb, semikolon eller mellanslag).
    Varje kolumn tolkas som helhet, så '1,234' läses rätt i en kolumn med
    decimalpunkt och '12,3 H' behåller sitt värde."""
    xs, ys = [], []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t") if "\t" in line else (
                line.split(";") if ";" in line else line.split(None, 1))
        if len(parts) < 2:
            continue
        xs.append(parts[0].strip()); ys.append(parts[1].strip())
    if not xs:
        raise ValueError("No numeric rows found.")
    x = _num_col(xs); y = _num_col(ys)
    ok = np.isfinite(x) & np.isfinite(y)
    if not ok.any():
        raise ValueError("No numeric rows found.")
    return pd.DataFrame({"reference": x[ok], "candidate": y[ok]})

def _step(n: int, label: str) -> None:
    """Numbered step heading in the sidebar: a filled circle with the digit
    drawn by CSS (not a Unicode ① glyph, which renders thin and off-baseline
    in the fallback font) followed by the translated label."""
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;'
        f'margin:6px 0 10px 0;">'
        f'<span style="display:inline-flex;align-items:center;'
        f'justify-content:center;min-width:24px;height:24px;border-radius:50%;'
        f'background:#1E40AF;color:#FFFFFF;font-weight:700;font-size:13px;'
        f'line-height:1;">{n}</span>'
        f'<span style="font-weight:600;font-size:1rem;color:inherit;">'
        f'{t(label)}</span></div>',
        unsafe_allow_html=True)


def _tdf(df):
    """Translate OUR generated tables for display: column headers, index,
    and text cells that are translation keys. "Day 3" / "Rep 2" style labels
    are translated word-wise. Not used on previews of the user's own file."""
    import re as _re

    def tr(x):
        if not isinstance(x, str):
            return x
        m = _re.fullmatch(r"(Day|Rep) (\d+)", x)
        if m:
            return f"{t(m.group(1))} {m.group(2)}"
        return t(x)

    out = df.copy()
    out.columns = [tr(c) for c in out.columns]
    if out.index.name:
        out.index.name = tr(out.index.name)
    # pandas >= 3 stores text as a dedicated string dtype, not object,
    # so test for "object OR string" rather than object alone.
    _is_txt = lambda x: (pd.api.types.is_object_dtype(x)
                         or pd.api.types.is_string_dtype(x))
    if _is_txt(out.index):
        out.index = [tr(i) for i in out.index]
    for c in out.columns:
        if _is_txt(out[c]):
            out[c] = out[c].map(tr)
    return out


def fmt(v, d): return f"{v:.{d}f}".replace(".","," )


# ── CSV export helper ─────────────────────────────────────────────────────────
# Swedish/European Excel uses comma as the DECIMAL separator, so a
# comma-separated file cannot be parsed. We therefore write semicolon-separated
# files, prefixed with a UTF-8 BOM (so Excel detects the encoding and shows
# å/ä/ö correctly) and a "sep=;" hint line that Excel reads automatically.
CSV_SEP = ";"

def to_csv_bytes(df, index=False, index_label=None):
    """DataFrame -> semicolon-separated CSV bytes ready for st.download_button.
    A provenance line is prepended so the file can be traced to the exact
    software version that produced it (ISO 15189 traceability)."""
    body = df.to_csv(sep=CSV_SEP, index=index, index_label=index_label)
    prov = f"# {stamp()}\n"
    return ("\ufeff" + f"sep={CSV_SEP}\n" + prov + body).encode("utf-8")

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
    prov = f"# {stamp()}"
    return ("\ufeff" + f"sep={CSV_SEP}\n" + prov + "\n"
            + "\n".join(out) + "\n").encode("utf-8")
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

    st.markdown(t("**Filter rows (optional)**"))
    filter_col = st.selectbox(
        t("Filter by column"), ["— no filter —"] + cat_cols,
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
        st.warning(t("No values selected — using all rows."))
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
    def _col(c): return _num_col(df[c])
    return _col(xc), _col(yc)

def _read_csv(raw, hdr, xc, yc):
    kw=dict(header=0 if hdr else None, sep=None, engine="python")
    df=pd.read_csv(BytesIO(raw), decimal=",", **kw)
    if df.select_dtypes(include=[np.number]).shape[1]<2:
        df=pd.read_csv(BytesIO(raw), **kw)
    df.columns=[str(c) for c in df.columns]
    def _col(c): return _num_col(df[c])
    return _col(xc), _col(yc)


# ── Safe defaults for all sidebar variables (must be before the sidebar block) ─
_lf_mode="Single file (two columns)"
_lf_x_arr=_lf_y_arr=None
_lf_report_df=None
_lf_label_a="Method A"; _lf_label_b="Method B"
_lf_matched_xlsx=None; _lf_analyte="ALL"
_prlf_data_dict=None; _prlf_raw_df=None; _prlf_n_left=0
# Fyrfaltstabell safe defaults
ff_mode="agreement"; ff_cut_ref=None; ff_cut_cand=None
ff_pos_label="Positiv"; ff_neg_label="Negativ"; ff_conf=0.95
ff_analyte=""

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — widgets override the safe defaults above
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    # Sprakvaljare maste ligga forst sa att t() ger ratt sprak i resten
    _lang_name = st.selectbox(
        "Språk / Language", list(LANGUAGES.keys()),
        index=list(LANGUAGES.values()).index(
            st.session_state.get("_lang", DEFAULT_LANG)),
        key="_lang_picker")
    st.session_state["_lang"] = LANGUAGES[_lang_name]

    st.title(t("📊 Method Comparison"))

    # ══ STEP 1 ═════════════════════════════════════════════════════════════
    _step(1, "Choose your analysis")
    analysis_type = st.selectbox(
        t("Analysis type"), label_visibility="collapsed",
        options=["Passing–Bablok","Deming","Confusion Matrix",
                 "Precision Evaluation (EP15-A3)",
                 "Fourfold table (qualitative)"],
        key="analysis_type", format_func=t)

    _WHAT = {
        "Passing–Bablok": "Non-parametric regression · robust to outliers",
        "Deming": "Errors-in-both-variables regression",
        "Confusion Matrix": "Zone diameter agreement · EUCAST / CLSI",
        "Precision Evaluation (EP15-A3)": "Within-run & within-lab imprecision",
        "Fourfold table (qualitative)": "2×2 table for positive/negative methods",
    }
    st.caption(t(_WHAT[analysis_type]))

    if analysis_type == "Deming":
        with st.expander(t("⚙️ Deming options"), expanded=True):
            deming_weighted = st.toggle(
                t("Weighted Deming"), value=False, key="dw",
                help="On: errors proportional to concentration (constant CV). "
                     "Off: equal error variances.")
            error_ratio = st.number_input(
                t("Error ratio λ = Var(y)/Var(x)"), 0.01, 100.0, 1.0, 0.1, key="er",
                help="λ = 1 means both methods have equal imprecision.")
    else:
        deming_weighted = False
        error_ratio     = 1.0
    st.divider()

    _step(2, "Load your data")
    if analysis_type == "Precision Evaluation (EP15-A3)":
        st.caption(t("Upload or paste precision data in the main area →"))
        _x_sid=_y_sid=_sid_err=None; uploaded_file=pasted_text=None
        input_mode="📂 Upload file"
    else:
        if analysis_type in ("Passing–Bablok","Deming"):
            _lf_mode=st.radio(t("Data format"),
                ["Single file (two columns)","Two long-format files (match by ID)"],
                key="lf_mode",
                help="Long-format: one file per method with SampleID | Analysis | Result columns.", format_func=t)
        # (else already defaulted above)

        if _lf_mode=="Two long-format files (match by ID)":
            input_mode="📂 Upload file"; uploaded_file=pasted_text=None
            _x_sid=_y_sid=_sid_err=None
            st.markdown(t("**File A — Reference method**"))
            _uf_a=st.file_uploader(t("Upload reference file"),type=["csv","xlsx","xls"],key="lf_fa")
            st.markdown(t("**File B — Candidate method**"))
            _uf_b=st.file_uploader(t("Upload candidate file"),type=["csv","xlsx","xls"],key="lf_fb")
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
                        t("Header row"), ["Automatic", "No header"],
                        horizontal=True, key="lf_hdr", format_func=t,
                        help=t("Automatic finds the header row even when the export "
                               "starts with instrument or title rows."))
                    _auto = _lf_hdr_choice == "Automatic"

                    _sh_a = _sh_b = None
                    _sheets_a = list_sheets(_rb_a, _uf_a.name)
                    _sheets_b = list_sheets(_rb_b, _uf_b.name)
                    if len(_sheets_a) > 1:
                        _sh_a = st.selectbox(t("Sheet in file A"), _sheets_a, key="lf_sha")
                    if len(_sheets_b) > 1:
                        _sh_b = st.selectbox(t("Sheet in file B"), _sheets_b, key="lf_shb")

                    _lf_df_a = load_long_format(_rb_a, _uf_a.name, has_header=_auto, sheet=_sh_a)
                    _lf_df_b = load_long_format(_rb_b, _uf_b.name, has_header=_auto, sheet=_sh_b)
                    for _fl, _df in (("A", _lf_df_a), ("B", _lf_df_b)):
                        _ri = _df.attrs.get("read_info", {})
                        _src = (t("sheet {s}").format(s=_ri.get("sheet"))
                                if _ri.get("kind") == "Excel"
                                else f"{t(_ri.get('encoding', ''))} · {t(_ri.get('delimiter', ''))}")
                        _hdr = (t("header on row {h}").format(h=_ri.get("header_row"))
                                if _ri.get("header_row") else t("no header"))
                        st.caption(t("File {f}: {n} rows · {src} · {hdr}").format(
                            f=_fl, n=_ri.get("n_rows", len(_df)), src=_src, hdr=_hdr))

                    def _ix(opts, guess, fallback=0):
                        return opts.index(guess) if guess in opts else min(fallback, len(opts) - 1)

                    _cols_a, _cols_b = list(_lf_df_a.columns), list(_lf_df_b.columns)
                    st.markdown(t("**Column mapping — File A**"))
                    _ca2 = st.columns(3)
                    _id_a = _ca2[0].selectbox(t("Sample ID"), _cols_a,
                                              index=_ix(_cols_a, guess_column(_cols_a, "id")), key="lf_ida")
                    _ana_opts = ["N/A"] + _cols_a
                    _an_a = _ca2[1].selectbox(t("Analysis"), _ana_opts,
                                              index=_ix(_ana_opts, guess_column(_cols_a, "an")), key="lf_ana")
                    _rs_a = _ca2[2].selectbox(t("Result"), _cols_a,
                                              index=_ix(_cols_a, guess_column(_cols_a, "res"), 2), key="lf_rsa")
                    _lf_label_a = st.text_input(t("Label A"), t("Reference"), key="lf_la")
                    st.markdown(t("**Column mapping — File B**"))
                    _cb2 = st.columns(3)
                    _id_b = _cb2[0].selectbox(t("Sample ID"), _cols_b,
                                              index=_ix(_cols_b, guess_column(_cols_b, "id")), key="lf_idb")
                    _anb_opts = ["N/A"] + _cols_b
                    _an_b = _cb2[1].selectbox(t("Analysis"), _anb_opts,
                                              index=_ix(_anb_opts, guess_column(_cols_b, "an")), key="lf_anb")
                    _rs_b = _cb2[2].selectbox(t("Result"), _cols_b,
                                              index=_ix(_cols_b, guess_column(_cols_b, "res"), 2), key="lf_rsb")
                    _lf_label_b = st.text_input(t("Label B"), t("Candidate"), key="lf_lb")

                    # ── Which analysis in each file? ────────────────────────
                    _an_col_a = None if _an_a == "N/A" else _an_a
                    _an_col_b = None if _an_b == "N/A" else _an_b
                    _lf_an_a = _lf_an_b = None
                    if _an_col_a:
                        _lf_an_a = st.selectbox(t("Analysis in file A"),
                                                list_analytes(_lf_df_a, _an_col_a), key="lf_analyte_a")
                    if _an_col_b:
                        _list_b = list_analytes(_lf_df_b, _an_col_b)
                        _sug, _why = (suggest_analyte(_lf_an_a, _list_b) if _lf_an_a
                                      else (None, ""))
                        _lf_an_b = st.selectbox(
                            t("Analysis in file B"), _list_b,
                            index=_list_b.index(_sug) if _sug in _list_b else 0,
                            key=f"lf_analyte_b_{_lf_an_a}")
                        if _lf_an_a and _sug is None:
                            st.warning(t("No matching analysis name found in file B — "
                                         "choose it manually."))
                        elif _sug and _why != "exact" and _lf_an_b == _sug:
                            st.caption(t("Suggested pairing: {a} ↔ {b} — please check.")
                                       .format(a=_lf_an_a, b=_lf_an_b))
                    _lf_single = False
                    if _an_col_a is None or _an_col_b is None:
                        _lf_single = st.checkbox(
                            t("The file without an analysis column contains only one "
                              "analysis (repeated sample IDs are reruns)"), key="lf_single")

                    with st.expander(t("⚙️ Matching options")):
                        _lf_zeros = st.toggle(
                            t("Ignore leading zeros in numeric sample IDs"), value=True,
                            key="lf_zeros",
                            help=t("Excel removes leading zeros, so 0012345 in one file "
                                   "and 12345 in the other are treated as the same sample."))

                    # ── Reruns / duplicates ────────────────────────────────
                    _sm = "first_valid"
                    _dups_a = find_duplicates(_lf_df_a, _id_a, _an_col_a, _rs_a, _lf_zeros)
                    _dups_b = find_duplicates(_lf_df_b, _id_b, _an_col_b, _rs_b, _lf_zeros)
                    if (not _dups_a.empty or not _dups_b.empty) and \
                       (_an_col_a and _an_col_b or _lf_single):
                        st.warning(t("⚠️ Repeated results (reruns): file A {a} rows, "
                                     "file B {b} rows.").format(a=len(_dups_a), b=len(_dups_b)))
                        _DUP_LBL = {"first_valid": "Keep first valid", "last_valid": "Keep last valid",
                                    "mean": "Use mean", "first": "Keep first", "last": "Keep last"}
                        _sm = st.radio(t("Resolve duplicates"), list(_DUP_LBL),
                                       key="lf_dup", format_func=lambda v: t(_DUP_LBL[v]))

                    # ── Match ──────────────────────────────────────────────
                    _lf_x_arr, _lf_y_arr, _lf_report_df, _lf_sum = match_two_files(
                        _lf_df_a, _lf_df_b, _id_a, _id_b, _an_col_a, _an_col_b, _rs_a, _rs_b,
                        _lf_an_a or "ALL", _lf_an_b or "ALL", _lf_label_a, _lf_label_b,
                        ignore_leading_zeros=_lf_zeros, dup_strategy=_sm,
                        single_analyte=_lf_single)
                    _lf_analyte = ("ALL" if not (_lf_an_a or _lf_an_b) else
                                   (_lf_an_a or _lf_an_b) if _lf_an_a == _lf_an_b or not
                                   (_lf_an_a and _lf_an_b) else f"{_lf_an_a} ↔ {_lf_an_b}")

                    _s = _lf_sum
                    if _s["matched_ids"] == 0:
                        st.warning(t("⚠️ No matched pairs — check column mapping."))
                    else:
                        st.success(t("✅ {m} samples matched · {u} pairs used").format(
                            m=_s["matched_ids"], u=_s["used"]))
                        st.caption(t("Only in A: {a}  |  Only in B: {b}").format(
                            a=_s["only_a"], b=_s["only_b"]))
                    if _s["excluded"]:
                        _parts = []
                        for _k, _v in _s["excluded_reasons"].items():
                            _side, _rsn = _k.split(": ", 1)
                            _parts.append(f"{_side}: {t(_rsn)} × {_v}")
                        st.info(t("{n} matched samples not used:").format(n=_s["excluded"])
                                + " " + "; ".join(_parts))
                    for _fl in ("a", "b"):
                        if _s[f"sci_ids_{_fl}"]:
                            st.error(t("File {f}: {n} sample IDs are in scientific notation "
                                       "(e.g. 2,40915E+09) and cannot be matched. Export the "
                                       "IDs as text.").format(f=_fl.upper(), n=_s[f"sci_ids_{_fl}"]))
                        _p = _s[f"parse_{_fl}"]
                        if _p.get("ambiguous"):
                            st.warning(t("File {f}: {n} results such as 1,234 could be either "
                                         "a decimal or a thousands separator; read with "
                                         "decimal '{d}'. Check the values.").format(
                                f=_fl.upper(), n=_p["ambiguous"], d=_p["decimal"]))
                        if _p.get("conflict"):
                            st.warning(t("File {f}: the result column mixes decimal comma and "
                                         "decimal point; each value was read by its own "
                                         "format. Check the values.").format(f=_fl.upper()))
                    with st.expander(t("🔎 How the values were read")):
                        _pv_cols = ["SampleID", "Original A", _lf_label_a,
                                    "Original B", _lf_label_b, "Note"]
                        _pv = _lf_report_df[_lf_report_df["Match"] == "Matched"][_pv_cols]
                        _pv = _pv.sort_values("Note", ascending=False, kind="stable")
                        st.dataframe(_pv.head(200), hide_index=True, use_container_width=True)
                    _lf_matched_xlsx = build_matched_excel(
                        _lf_report_df, _lf_label_a, _lf_label_b, _lf_analyte)
                except MultipleResultsError:
                    st.error(t("Several results per sample ID but no analysis column is "
                               "selected, so results cannot be paired safely. Choose the "
                               "analysis column, or confirm that the file contains only "
                               "one analysis."))
                    _sid_err = "multiple"
                except Exception as _e:
                    st.error(f"{t('Matching error')}: {_e}")
                    _sid_err=str(_e)
        else:
            input_mode=st.radio(t("Input method"),["📂 Upload file","📋 Paste data"],key="imode", format_func=t)
            _x_sid=_y_sid=_sid_err=None; uploaded_file=pasted_text=None
            if input_mode=="📂 Upload file":
                uploaded_file=st.file_uploader(t("Upload CSV or Excel"),type=["csv","xlsx","xls"],key="fup")
                if uploaded_file is not None:
                    try:
                        fname=uploaded_file.name.lower()
                        if fname.endswith((".xlsx",".xls")):
                            import openpyxl
                            _rb=uploaded_file.read(); uploaded_file.seek(0)
                            _wb=openpyxl.load_workbook(BytesIO(_rb),read_only=True,data_only=True)
                            _sn=_wb.sheetnames; _wb.close()
                            _ss=st.selectbox(t("Sheet / tab"),_sn,key="ss")
                            _hc=st.radio(t("Header row?"),["Yes (first row)","No header"],horizontal=True,key="hx", format_func=t)
                            _hdr=_hc=="Yes (first row)"
                            _pv=pd.read_excel(BytesIO(_rb),sheet_name=_ss,header=0 if _hdr else None,nrows=5)
                            if not _hdr: _pv.columns=[f"Column {i+1}" for i in range(len(_pv.columns))]
                            else: _pv.columns=[str(c) for c in _pv.columns]
                            st.caption(t("Preview (first 5 rows):"))
                            st.dataframe(_pv,use_container_width=True)
                            _cols=list(_pv.columns)
                            if len(_cols)>=2:
                                _xc=st.selectbox(t("Reference column (x)"),_cols,0,key="xce")
                                _yc=st.selectbox(t("Candidate column (y)"),_cols,min(1,len(_cols)-1),key="yce")
                                _full=pd.read_excel(BytesIO(_rb),sheet_name=_ss,header=0 if _hdr else None)
                                if not _hdr: _full.columns=[f"Column {i+1}" for i in range(len(_full.columns))]
                                else: _full.columns=[str(c) for c in _full.columns]
                                _full=_apply_filter(_full,exclude_cols=[_xc,_yc],key_prefix="xe")
                                def _tonum(s): return _num_col(s)
                                _x_sid=_tonum(_full[_xc]); _y_sid=_tonum(_full[_yc])
                            else: _sid_err="Sheet needs at least 2 columns."
                        else:
                            _rb=uploaded_file.read(); uploaded_file.seek(0)
                            _hc=st.radio(t("Header row?"),["Yes (first row)","No header"],horizontal=True,key="hc", format_func=t)
                            _hdr=_hc=="Yes (first row)"
                            _pv=pd.read_csv(BytesIO(_rb),header=0 if _hdr else None,sep=None,engine="python",decimal=",")
                            if _pv.select_dtypes(include=[np.number]).shape[1]<2:
                                _pv=pd.read_csv(BytesIO(_rb),header=0 if _hdr else None,sep=None,engine="python")
                            if not _hdr: _pv.columns=[f"Column {i+1}" for i in range(len(_pv.columns))]
                            else: _pv.columns=[str(c) for c in _pv.columns]
                            st.caption(t("Preview (first 5 rows):"))
                            st.dataframe(_pv.head(),use_container_width=True)
                            _cols=list(_pv.columns)
                            _xc=st.selectbox(t("Reference column (x)"),_cols,0,key="xcc")
                            _yc=st.selectbox(t("Candidate column (y)"),_cols,min(1,len(_cols)-1),key="ycc")
                            _full=pd.read_csv(BytesIO(_rb),header=0 if _hdr else None,sep=None,engine="python",decimal=",")
                            if _full.select_dtypes(include=[np.number]).shape[1]<2:
                                _full=pd.read_csv(BytesIO(_rb),header=0 if _hdr else None,sep=None,engine="python")
                            if not _hdr: _full.columns=[f"Column {i+1}" for i in range(len(_full.columns))]
                            else: _full.columns=[str(c) for c in _full.columns]
                            _full=_apply_filter(_full,exclude_cols=[_xc,_yc],key_prefix="ce")
                            def _tonum(s): return _num_col(s)
                            _x_sid=_tonum(_full[_xc]); _y_sid=_tonum(_full[_yc])
                    except Exception as _e:
                        _sid_err=str(_e)
            else:
                st.markdown(t("Copy two columns from Excel and paste below."))
                pasted_text=st.text_area(t("Paste data here"),height=160,
                    placeholder="10,2\t10,5\n15,7\t16,1\n...",key="pa")

    _step(3, "Name your methods")
    x_label=st.text_input(t("Reference method (x-axis)"),t("Reference Method"),key="xl")
    y_label=st.text_input(t("Candidate method (y-axis)"),t("Candidate Method"),key="yl")
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
        _step(4, "Plot options")

        # -- Essentials: visible without opening anything ---------------------
        decimals = st.slider(t("Decimal places"), 1, 8, 2, key="dec")
        ba_pct_diff = st.toggle(
            t("Bland–Altman as % difference"), value=False, key="bap",
            help="Off: absolute difference (y − x). On: percentage of the mean.")

        # -- Titles ------------------------------------------------------------
        with st.expander(t("🏷️ Titles")):
            pb_title = st.text_input(
                t("Regression plot"), value="",
                placeholder="Leave blank for automatic title", key="pbt")
            ba_title_input = st.text_input(
                t("Bland–Altman plot"), value="",
                placeholder="Leave blank for automatic title", key="bat")

        # -- Axis ranges -------------------------------------------------------
        with st.expander(t("📐 Axis ranges")):
            st.caption(t("Leave any field blank for automatic scaling."))
            st.markdown(t("**Regression plot**"))
            _a=st.columns(2)
            pb_x_min=_pa(_a[0].text_input(t("X min"),"0",key="pxn"))
            pb_x_max=_pa(_a[1].text_input(t("X max"),"",key="pxx"))
            pb_y_min=_pa(_a[0].text_input(t("Y min"),"0",key="pyn"))
            pb_y_max=_pa(_a[1].text_input(t("Y max"),"",key="pyx"))
            st.markdown(t("**Bland–Altman plot**"))
            _b=st.columns(2)
            ba_x_min=_pa(_b[0].text_input(t("X min"),"",key="bxn"))
            ba_x_max=_pa(_b[1].text_input(t("X max"),"",key="bxx"))
            ba_y_min=_pa(_b[0].text_input(t("Y min"),"",key="byn"))
            ba_y_max=_pa(_b[1].text_input(t("Y max"),"",key="byx"))

        # -- Colours -----------------------------------------------------------
        with st.expander(t("🎨 Colours")):
            st.markdown(t("**Regression plot**"))
            _c1=st.columns(3)
            with _c1[0]:
                pb_color_scatter=st.color_picker(t("Points"),"#2563EB",key="pcs")
            with _c1[1]:
                pb_color_identity=st.color_picker(t("Identity"),"#9CA3AF",key="pci")
            with _c1[2]:
                pb_color_regression=st.color_picker(t("Fit"),"#DC2626",key="pcr")
            pb_show_ci  = st.toggle(t("Show 95% CI band"), value=True, key="psc")
            _c2=st.columns([1,2])
            with _c2[0]:
                pb_color_ci=st.color_picker(t("CI band"),"#DC2626",key="pcc")
            with _c2[1]:
                pb_ci_alpha=st.slider(t("CI transparency"),0.0,1.0,0.15,0.01,key="pca")

            st.markdown(t("**Bland–Altman plot**"))
            _c3=st.columns(3)
            with _c3[0]:
                ba_color_scatter=st.color_picker(t("Points"),"#2563EB",key="bcs")
            with _c3[1]:
                ba_color_mean=st.color_picker(t("Mean bias"),"#DC2626",key="bcm")
            with _c3[2]:
                ba_color_loa=st.color_picker(t("LoA"),"#F97316",key="bcl")

        # -- Legend & annotation text -----------------------------------------
        with st.expander(t("✏️ Legend & label text")):
            st.markdown(t("**Regression plot**"))
            pb_legend_scatter   =st.text_input(t("Points"),   "Observations",     key="pls")
            pb_legend_identity  =st.text_input(t("Identity"), "Identity (y = x)", key="pli")
            pb_legend_regression=st.text_input(t("Fit line"), "Regression",       key="plr")
            pb_legend_ci        =st.text_input(t("CI band"),  "95% CI",           key="plc")
            st.markdown(t("**Bland–Altman plot**"))
            ba_legend_scatter =st.text_input(t("Points"),     "Difference", key="bls")
            ba_label_mean     =st.text_input(t("Mean line"),  "Mean",       key="blm")
            ba_label_loa_upper=st.text_input(t("Upper LoA"),  "+1,96 SD",   key="blu")
            ba_label_loa_lower=st.text_input(t("Lower LoA"),  "−1,96 SD",   key="bll")

    elif analysis_type == "Confusion Matrix":
        _step(4, "Breakpoints")
        bp_system=st.selectbox(t("Breakpoint system"),["EUCAST","CLSI"],key="bps",
            help="Determines the S / I / R categories used for "
                 "categorical agreement, VME and ME.", format_func=t)
        st.caption(f"**{x_label}**")
        _bp1=st.columns(2)
        bp_s_x=_bp1[0].number_input(t("S ≥ (mm)"),value=20.0,step=0.5,key="bsx")
        bp_r_x=_bp1[1].number_input(t("R ≤ (mm)"),value=16.0,step=0.5,key="brx")
        st.caption(f"**{y_label}**")
        _bp2=st.columns(2)
        bp_s_y=_bp2[0].number_input(t("S ≥ (mm)"),value=20.0,step=0.5,key="bsy")
        bp_r_y=_bp2[1].number_input(t("R ≤ (mm)"),value=16.0,step=0.5,key="bry")
        st.divider()

        _step(5, "Matrix options")

        # -- Essentials --------------------------------------------------------
        cm_step=st.number_input(t("Step size (mm per cell)"),1,10,1,1,key="cms",
            help="1 = one cell per millimetre.")
        cm_ea_window =st.selectbox(t("Essential agreement band (± mm)"),[1,2,3],
            index=1,key="cea",
            help="Draws the dotted boundary lines either side of the diagonal.")

        # -- Layout ------------------------------------------------------------
        with st.expander(t("📐 Range & layout")):
            st.caption(t("Leave blank for automatic range."))
            _cc=st.columns(2)
            cm_x_min=_ca(_cc[0].text_input(t("X min"),"",placeholder="auto",key="cxn"))
            cm_x_max=_ca(_cc[1].text_input(t("X max"),"",placeholder="auto",key="cxx"))
            cm_y_min=_ca(_cc[0].text_input(t("Y min"),"",placeholder="auto",key="cyn"))
            cm_y_max=_ca(_cc[1].text_input(t("Y max"),"",placeholder="auto",key="cyx"))
            cm_show_diag  =st.toggle(t("Show diagonal lines"),value=True,key="csd")
            cm_show_totals=st.toggle(t("Show n = total (outside frame)"),
                                     value=True,key="cst")

        # -- Title -------------------------------------------------------------
        with st.expander(t("🏷️ Title")):
            cm_title=st.text_input(t("Matrix title"),
                "Zone Diameter Comparison Matrix",key="ctt")

        # -- Colours -----------------------------------------------------------
        with st.expander(t("🎨 Colours")):
            cm_base_color=st.color_picker(t("Matrix colour"),"#1D4ED8",key="cbc")
            cm_scale_max =st.slider(t("Coloured bands (mm from diagonal)"),
                1,10,2,key="csc",
                help="How far from perfect agreement the shading extends.")

        # -- Cell numbers ------------------------------------------------------
        with st.expander(t("🔢 Cell numbers")):
            cm_font_size=st.slider(t("Font size"),6,16,11,key="cfs")
            cm_num_bold =st.toggle(t("Bold"),value=True,key="cnbd")
            _nc=st.columns(2)
            with _nc[0]:
                cm_num_color_on_blue =st.color_picker(
                    t("On shaded cells"),"#1E3A5F",key="cnb")
            with _nc[1]:
                cm_num_color_on_white=st.color_picker(
                    t("On white cells"),"#1E3A5F",key="cnw")

    elif analysis_type == "Fourfold table (qualitative)":
        _step(4, "Fourfold table options")

        ff_analyte = st.text_input(t("Analysis / question"), value="",
            placeholder=t("e.g. hs-Troponin I, cut-off 26 ng/L"), key="ff_an")

        _m = st.radio(
            t("What is being compared?"),
            [t("Two methods against each other (no gold standard)"),
             t("Against a reference standard (gold standard exists)")],
            key="ff_mode_radio",
            help="Avgör om resultatet får kallas sensitivitet/specificitet "
                 "eller procentuell överensstämmelse.")
        ff_mode = "reference" if _m == t("Against a reference standard (gold standard exists)") else "agreement"

        if ff_mode == "reference":
            st.caption(t("Sensitivity, specificity and predictive values are reported. "
                       "Requires that the reference method truly is the "
                       "gold standard."))
        else:
            st.caption(t("PPA/NPA are reported. Sensitivity may not be claimed when "
                       "neither method is a gold standard (CLSI EP12-A2)."))

        with st.expander(t("⚖️ Cut-off values")):
            st.caption(t("Fill in if the data are quantitative and need splitting into "
                       "positive/negative. Leave blank if the data are already "
                       "positive/negative."))
            _c = st.columns(2)
            ff_cut_ref  = _pa(_c[0].text_input(t("Cut-off reference"), "", key="ff_cr"))
            ff_cut_cand = _pa(_c[1].text_input(t("Cut-off candidate"), "", key="ff_cc"))
            st.caption(t("Positive is defined as a value ≥ the cut-off."))

        with st.expander(t("🏷️ Result labels")):
            ff_pos_label = st.text_input(t("Positive result"), "Positiv", key="ff_pl")
            ff_neg_label = st.text_input(t("Negative result"), "Negativ", key="ff_nl")

        ff_conf = st.selectbox(t("Confidence level"), [0.95, 0.90, 0.99], index=0,
                               format_func=lambda v: f"{v:.0%}", key="ff_conf")

    else:   # Precision Evaluation (EP15-A3)
        _step(4, "Precision options")
        st.caption(t("EP15-A3 recommends 5 replicates × 5 days "
                   "(minimum 2 × 2)."))

        prec_decimals = st.slider(t("Decimal places"), 1, 6, 4, key="pr_dec")

        with st.expander(t("📊 Statistical settings")):
            prec_alpha = st.selectbox(t("Significance level (α)"),
                [0.05, 0.01], index=0,
                format_func=lambda v: f"{v:.0%}", key="pr_alpha",
                help="False-rejection rate for the chi-square verification.")
            prec_n_levels = st.number_input(t("Concentration levels tested (q)"),
                min_value=1, max_value=5, value=1, step=1, key="pr_q",
                help="Bonferroni correction for testing several levels at once.")

        with st.expander(t("🏭 Manufacturer claims (optional)")):
            st.caption(t("Enter the claimed SDs to run the chi-square "
                       "verification. Leave at 0 to skip."))
            _csr=st.number_input(t("Claimed repeatability SD (σr)"),
                                 min_value=0.0, value=0.0, step=0.001,
                                 format="%.4f", key="pr_csr")
            _csl=st.number_input(t("Claimed within-lab SD (σl)"),
                                 min_value=0.0, value=0.0, step=0.001,
                                 format="%.4f", key="pr_csl")
        prec_claimed_sr = _csr if _csr > 0 else None
        prec_claimed_sl = _csl if _csl > 0 else None

    st.divider()
    if st.button(t("↻ Reset all settings"), use_container_width=True,
                 help="Restores every option to its default. Your uploaded "
                      "file stays loaded."):
        _keep = {"lf_rb_a","lf_rb_b","lf_fname_a","lf_fname_b"}
        for _k in [k for k in st.session_state.keys() if k not in _keep]:
            del st.session_state[_k]
        st.rerun()

    st.caption(f"**{version_string()}** · validerad {VALIDATED_ON}")

    # Where is the app actually running? The privacy statement must match.
    #   browser : stlite/Pyodide - data never leaves the user's computer
    #   cloud   : Streamlit Community Cloud (apps live under /mount/src)
    #   local   : ordinary `streamlit run` on the user's own machine
    # MCT_DEPLOYMENT=cloud|local|browser overrides the detection.
    _dep = os.environ.get("MCT_DEPLOYMENT", "").strip().lower()
    if _dep not in ("cloud", "local", "browser"):
        if sys.platform == "emscripten":
            _dep = "browser"
        elif os.path.abspath(__file__).startswith("/mount/src"):
            _dep = "cloud"
        else:
            _dep = "local"

    if _dep == "cloud":
        st.warning(t("☁️ Web version — use anonymised or simulated data only."))
    with st.expander(t("🔒 Data protection"), expanded=(_dep == "cloud")):
        if _dep == "cloud":
            st.caption(t(
                "This web version runs on Streamlit Community Cloud, a public "
                "service operated by a US company. Files you upload are sent "
                "to and processed on servers outside the EU/EEA. The "
                "application saves nothing itself, but the data is still "
                "transferred and processed there.\n\n"
                "Never upload data that can be traced to an individual "
                "patient. Use simulated data, control material, or "
                "anonymised files: replace sample IDs with sequence numbers "
                "and dates with relative day numbers.\n\n"
                "For verification work on real patient samples, use the "
                "locally installed version."))
        elif _dep == "browser":
            st.caption(t(
                "This version runs entirely in your web browser. Files you "
                "open are processed on your own computer and are never sent "
                "to any server. Nothing is saved when you close the page.\n\n"
                "Still avoid data that can be traced to an individual "
                "patient unless your local routines allow it."))
        else:
            st.caption(t(
                "The application runs locally on this computer. No data is "
                "sent anywhere and the application stores nothing itself.\n\n"
                "Do not upload data that can be traced back to an individual "
                "patient. Use de-identified sample IDs and relative day "
                "numbers instead of dates."))

    with st.expander(t("📚 References")):
        st.caption(
            t("Passing & Bablok, *J Clin Chem Clin Biochem* 1983  \n"
            "Deming, *Statistical Adjustment of Data* 1943  \n"
            "Linnet, *Stat Med* 1990  \n"
            "Bland & Altman, *Lancet* 1986  \n"
            "CLSI EP15-A3 2014 · CLSI M52 · EUCAST v10.0"))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN AREA
# ══════════════════════════════════════════════════════════════════════════════
method_label = ("Weighted Deming" if deming_weighted else "Deming") \
               if analysis_type=="Deming" else analysis_type
st.title(f"{t('Method Comparison')} — {t(method_label)}")

if _sid_err:
    st.error(f"Could not read file: {_sid_err}")
    st.stop()

# ── Resolve data ───────────────────────────────────────────────────────────────
def _get_data():
    if input_mode=="📂 Upload file":
        if uploaded_file is None:
            # ── Welcome / landing page ────────────────────────────────────────
            st.markdown(t("""
## Method Comparison Tool

A simple tool for comparing two analytical measurement methods in clinical microbiology and clinical chemistry.
👈 Select an analysis type in the sidebar, then upload your data or paste it directly.
"""))

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.markdown(t("""
**📈 Passing–Bablok**
Non-parametric regression — resistant to outliers, no assumptions about error distribution.
Slope, intercept and 95 % confidence intervals via the rank-based method.
"""))
            with col_b:
                st.markdown(t("""
**📉 Deming regression**
Accounts for measurement error in both methods.
Ordinary (equal variances) or weighted (proportional CV, Linnet 1990).
Confidence intervals via jackknife resampling.
"""))
            with col_c:
                st.markdown(t("""
**🔢 Confusion matrix**
Zone diameter agreement grid for disk diffusion comparison.
Essential agreement (±1/±2 mm), categorical agreement, VME and ME.
EUCAST and CLSI breakpoints supported.
"""))

            col_d, _ = st.columns([1, 2])
            with col_d:
                st.markdown(t("""
**🔬 Precision Evaluation (EP15-A3)**
Within-run (repeatability) and within-laboratory (total) SD and CV.
Chi-square verification against manufacturer claims.
Based on CLSI EP15-A3 (2014) — 5 replicates × 5 days recommended.
"""))

            st.divider()

            # ── Data format + references side by side ─────────────────────────
            fc1, fc2 = st.columns([3, 2])

            with fc1:
                st.markdown(t("**📄 Expected data format**"))

                _wt1, _wt2 = st.tabs([t("Regression / Confusion matrix"), t("Precision Evaluation")])

                with _wt1:
                    st.markdown(t("At least two numeric columns — one per method. "
                                "Extra columns (species, antibiotic, lab) can be used to filter rows."))
                    st.dataframe(_tdf(pd.DataFrame({
                        "Species":        ["E. coli","E. coli","K. pneumoniae","S. aureus"],
                        "Reference (mm)": [18, 20, 22, 24],
                        "Candidate (mm)": [19, 20, 23, 25],
                    })), use_container_width=True, hide_index=True)
                    st.caption(t("Accepted: Excel (.xlsx/.xls), CSV, or paste from Excel. "
                               "Comma or point as decimal. Header row optional."))

                with _wt2:
                    st.markdown(t("**One column per day, one row per replicate.** "
                                "EP15-A3 recommends 5 replicates × 5 days at ≥ 2 concentration levels."))
                    st.dataframe(_tdf(pd.DataFrame({
                        "Day 1": [2.015, 2.013, 1.963, 2.001, 1.998],
                        "Day 2": [2.019, 2.002, 1.979, 2.010, 1.995],
                        "Day 3": [2.025, 1.959, 2.000, 1.988, 2.005],
                        "Day 4": [1.972, 1.950, 1.973, 1.965, 1.980],
                        "Day 5": [1.981, 1.956, 1.957, 1.970, 1.975],
                    })), use_container_width=True, hide_index=True)
                    st.caption(t("Upload as Excel / CSV or paste directly from Excel. "
                               "Column headers become the day labels. Comma or point as decimal."))

                    st.markdown(t("**Example output:**"))
                    st.dataframe(_tdf(pd.DataFrame({
                        "Component":              ["Within-run (repeatability)",
                                                   "Between-day",
                                                   "Within-laboratory (total)"],
                        "SD":                     ["0,0235", "0,0116", "0,0262"],
                        "CV (%)":                 ["1,18",   "—",      "1,32"],
                        "Degrees of freedom":     ["10",     "4",      "12,8 (eff.)"],
                    })), use_container_width=True, hide_index=True)

            with fc2:
                st.markdown(t("**📚 Key references**"))
                st.markdown(t("""
- Passing & Bablok, *J Clin Chem Clin Biochem* 1983 — [DOI](https://doi.org/10.1515/cclm.1983.21.11.709)
- Linnet K, *Stat Med* 1990 — [DOI](https://doi.org/10.1002/sim.4780091210)
- Bland & Altman, *Lancet* 1986 — [DOI](https://doi.org/10.1016/S0140-6736(86)90837-8)
- CLSI EP15-A3, 2014 — Precision verification
- CLSI EP09c — Method comparison & bias estimation
- EUCAST Disk Diffusion Guide v10.0, 2023 — [eucast.org](https://www.eucast.org/ast_of_bacteria/disk_diffusion_methodology/)
- CLSI M52 — Verification of AST systems
- Chesher D, *Clin Biochem Rev* 2008 — [DOI](https://doi.org/10.3109/00365519809099610)
"""))
            return None, None

        if _x_sid is None or _y_sid is None:
            st.info(t("👈 Select the columns to use in the sidebar."))
            return None,None
        return _x_sid, _y_sid
    else:
        if not pasted_text or not pasted_text.strip():
            st.info(t("👈 Paste your data in the sidebar to get started."))
            return None,None
        try:
            _df=parse_pasted(pasted_text)
            st.success(t("✅ Parsed {n} rows.").format(n=len(_df)))
            return _df["reference"].values, _df["candidate"].values
        except ValueError as e:
            st.error(t(str(e))); return None,None

if analysis_type == "Precision Evaluation (EP15-A3)":
    x_raw = y_raw = np.array([1.0, 2.0])  # dummy — precision has its own input
elif _lf_mode == "Two long-format files (match by ID)":
    if _sid_err:
        st.error(f"Could not match files: {_sid_err}")
        st.stop()
    if _lf_x_arr is None or len(_lf_x_arr) == 0:
        st.info(t("👈 Upload both files and configure the column mapping in the sidebar."))
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
    _c1.metric(t("Total rows"),n_tot)
    _c2.metric(t("Missing / excluded"),n_mis)
    _c3.metric(t("Valid pairs"),n_tot-n_mis)


# ══════════════════════════════════════════════════════════════════════════════
# BRANCH A — Regression
# ══════════════════════════════════════════════════════════════════════════════
if analysis_type in ("Passing–Bablok","Deming"):

    # ── Analyze: store the FULL dataset; exclusions are applied afterwards ────
    if st.button(t("▶ Analyze"), type="primary"):
        st.session_state["x_all"]      = x_raw.copy()
        st.session_state["y_all"]      = y_raw.copy()
        st.session_state["reg_method"] = method_label
        st.session_state["excl_multi"] = []
        st.session_state["reg_ready"]  = True

    if not st.session_state.get("reg_ready"):
        st.info(t("👆 Click **Analyze** to run the regression."))
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
        if st.button(t("↺ Restore all points"), key="restore_all_err"):
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

    st.subheader(f"{t('Results')} — {t(st.session_state.get('reg_method', method_label))}")
    st.dataframe(_tdf(pd.DataFrame([
        {"Statistic":"Slope","Value":fmt(rr["slope"],decimals),
         "95% CI":f"[{fmt(rr['slope_lower'],decimals)} – {fmt(rr['slope_upper'],decimals)}]"},
        {"Statistic":"Intercept","Value":fmt(rr["intercept"],decimals),
         "95% CI":f"[{fmt(rr['intercept_lower'],decimals)} – {fmt(rr['intercept_upper'],decimals)}]"},
        {"Statistic":"R²",        "Value":fmt(ss["r_squared"],decimals),"95% CI":"—"},
        {"Statistic":"Pearson r", "Value":fmt(ss["pearson_r"],decimals),"95% CI":"—"},
        {"Statistic":"Bias",      "Value":fmt(ss["bias"],decimals),     "95% CI":"—"},
        {"Statistic":"LoA lower", "Value":fmt(ss["loa_lower"],decimals),"95% CI":"—"},
        {"Statistic":"LoA upper", "Value":fmt(ss["loa_upper"],decimals),"95% CI":"—"},
    ])),use_container_width=True,hide_index=True)

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

    st.caption(t("💡 Click a point, or drag a box/lasso, to exclude it from both "
               "plots and all statistics."))

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
    with st.expander(t("🗑 Excluded points ({n})").format(n=len(_excl)), expanded=bool(_excl)):
        _opts = list(range(_n_all))
        def _lbl(i):
            return f"#{i+1}:  {fmt(float(_x_all[i]),decimals)} / {fmt(float(_y_all[i]),decimals)}"
        # No `default=` — the widget's session_state key IS the source of truth,
        # so a rerun from any other button cannot wipe the exclusions.
        _picked = st.multiselect(
            t("Excluded from analysis (add or remove here)"),
            options=_opts, format_func=_lbl, key="excl_multi")
        if set(_picked) != _excl:
            st.rerun()
        # Callback: runs BEFORE the widgets are created on the next run, which
        # is the only point where a widget's own session_state key may change.
        def _restore_all():
            st.session_state["excl_multi"] = []
        if _excl:
            st.button(t("↺ Restore all points"), key="restore_all", on_click=_restore_all)

    st.subheader(t("Export"))
    with st.expander(t("⚙️ Image resolution"),expanded=True):
        _dl=st.selectbox(t("Resolution"),DPI_LABELS,index=1,key="rdpi")
        _dp=dpi_from_label(_dl)
        _iw=int(180/25.4*_dp); _ih=int(130/25.4*_dp)
        st.caption(f"Auto: **{_iw}×{_ih} px** at **{_dp} dpi** ≈ 18×13 cm.")

    fig_pb=make_regression_plot(_x,_y,**_pkw)
    fig_ba=make_bland_altman_plot(_x,_y,**_bkw)

    for _rfn,_kw,_lbl,_slg in [
        (render_pb_png,_pkw,"Regression plot","reg"),
        (render_ba_png,_bkw,"Bland–Altman plot","ba"),
    ]:
        st.markdown(f"**{t(_lbl)}**")
        _e1,_e2,_=st.columns([1,1,2])
        _e1.download_button(f"🖼 PNG ({_dp} dpi)",
            mpl_fig_to_png_bytes(_rfn(_x,_y,dpi=_dp,width_px=_iw,height_px=_ih,**_kw),dpi=_dp),
            f"{_slg}_{_dp}dpi.png","image/png",key=f"png_{_slg}")
        _e2.download_button(t("📐 SVG"),
            mpl_fig_to_svg_bytes(_rfn(_x,_y,dpi=_dp,width_px=_iw,height_px=_ih,**_kw)),
            f"{_slg}.svg","image/svg+xml",key=f"svg_{_slg}")

    st.divider()
    st.markdown(t("**Results data & full report**"))
    _f1,_f2,_=st.columns([1,1,2])
    _csv_txt = results_to_csv(rr,ss)
    _csv_txt += (f"\nPoints used,{len(_kept)}\nPoints excluded,{len(_excl)}\n"
                 f"Total points,{_n_all}\n")
    if _excl:
        _csv_txt += ("Excluded point numbers,"
                     + " ".join(str(i+1) for i in sorted(_excl)) + "\n")
    _f1.download_button(t("📥 Results CSV"), text_to_csv_bytes(_csv_txt),
                        "results.csv", "text/csv", key="rcsv")
    _f2.download_button(t("📄 HTML Report"),
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
        for _k2, _ridx in enumerate(_m_idx):
            if not (np.isfinite(_va[_k2]) and np.isfinite(_vb[_k2])):
                _rep_out.at[_ridx, "Status"] = "Not used"

        _xlsx_out = build_matched_excel(
            _rep_out, _lf_label_a, _lf_label_b, _lf_analyte)

        st.markdown(t("**Matched pairs data**"))
        _fx1,_fx2,_=st.columns([1,1,2])
        _fx1.download_button(
            t("📊 Download matched pairs (Excel)"),
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
    st.subheader(t("Zone Diameter Confusion Matrix"))
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
    _m1.metric(t("EA ±1 mm"), f"{ea['ea_1mm']:.1f}%",f"{ea['n_ea1']}/{ea['n']}")
    _m2.metric(t("EA ±2 mm"), f"{ea['ea_2mm']:.1f}%",f"{ea['n_ea2']}/{ea['n']}")
    _m3.metric(t("Categorical Agr."),f"{ca['ca']:.1f}%",f"{ca['n_ca']}/{ca['n']}")
    _m4.metric(t("VME (R→S)"), f"{ca['vme']:.1f}%",
               f"{ca['n_vme']} of {ca['n_r_ref']} R",delta_color="inverse",
               help="Very major error = false susceptibility. Reference "
                    "resistant, candidate susceptible. Percentage of "
                    "RESISTANT isolates. CLSI/FDA limit 1.5–3 %.")
    _m5.metric(t("ME (S→R)"),  f"{ca['me']:.1f}%",
               f"{ca['n_me']} of {ca['n_s_ref']} S",delta_color="inverse",
               help="Major error = false resistance. Reference susceptible, "
                    "candidate resistant. Percentage of SUSCEPTIBLE isolates. "
                    "CLSI/FDA limit 3 %.")
    if ca["n_minor"]>0:
        st.caption(t("Minor errors: {n} ({p} %)").format(n=ca['n_minor'], p=fmt(ca['minor_e'], 1)))

    with st.expander(t("ℹ️ Acceptability thresholds")):
        st.markdown(t("""
| Metric | EUCAST | CLSI |
|---|---|---|
| Essential Agreement ±2 mm | ≥ 90 % | ≥ 90 % |
| Categorical Agreement | ≥ 90 % | ≥ 90 % |
| Very major error (false susceptible, R→S) | ≤ 3 % of **R** isolates | ≤ 1.5 % of **R** |
| Major error (false resistant, S→R) | ≤ 3 % of **S** isolates | ≤ 3 % of **S** |
*EUCAST Disk Diffusion v10.0; CLSI M52.*"""))

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

    st.subheader(t("Export matrix"))
    with st.expander(t("⚙️ Export resolution"),expanded=True):
        _cdl=st.selectbox(t("Resolution"),DPI_LABELS,index=1,key="cdpi")
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
    _d2.download_button(t("📥 Matrix CSV"),
                        to_csv_bytes(_mdf, index=True),
                        "confusion_matrix.csv","text/csv",key="ccsv")


# ══════════════════════════════════════════════════════════════════════════════
# BRANCH D — Fyrfältstabell (kvalitativa metoder)
# ══════════════════════════════════════════════════════════════════════════════
elif analysis_type == "Fourfold table (qualitative)":

    st.subheader(t("Fourfold table") + (f" — {ff_analyte}" if ff_analyte else ""))

    # Data kan vara redan binära eller kvantitativa med beslutsgräns
    _need_cut = (ff_cut_ref is None or ff_cut_cand is None)
    _is_num = np.all(np.isfinite(x_raw)) and np.all(np.isfinite(y_raw))

    if _is_num and _need_cut:
        st.info(t("The data are quantitative. Set cut-off values in the sidebar "
                "under **Cut-off values** to split into positive/negative."))
        st.stop()

    try:
        _cells = fourfold_from_arrays(
            x_raw, y_raw,
            cutoff_ref=ff_cut_ref, cutoff_cand=ff_cut_cand)
        _ff = fourfold(**_cells, mode=ff_mode, conf=float(ff_conf))
    except Exception as _e:
        st.error(f'{t("Could not build the table")}: {_e}')
        st.stop()

    _warn = check_prerequisites(_ff, t=t)

    # ── Färgad 2×2-tabell ────────────────────────────────────────────────────
    st.markdown(
        fourfold_html(_ff, ref_name=x_label, cand_name=y_label,
                      pos_label=ff_pos_label, neg_label=ff_neg_label, t=t),
        unsafe_allow_html=True)

    # ── Resultat i en samlad tabell ───────────────────────────────────────────
    st.markdown("")

    def _p1(v):  return f"{v:.1f}".replace(".", ",") + " %"
    def _p2(v):  return f"{v:.2f}".replace(".", ",")
    def _p3(v):  return f"{v:.3f}".replace(".", ",")
    def _ciw(t, f=_p1):
        return f"{f(t[0]).replace(' %','')}–{f(t[1])}"

    _KI = f"{int(_ff['conf']*100)} % KI"

    if ff_mode == "reference":
        _rows = [
            (t("Sensitivity"), _p1(_ff["ppa"]), _ciw(_ff["ppa_ci"]),
             f"{_ff['tp']} / {_ff['n_ref_pos']}"),
            (t("Specificity"), _p1(_ff["npa"]), _ciw(_ff["npa_ci"]),
             f"{_ff['tn']} / {_ff['n_ref_neg']}"),
            (t("Positive predictive value (PPV)"), _p1(_ff["ppv"]), _ciw(_ff["ppv_ci"]),
             f"{_ff['tp']} / {_ff['n_cand_pos']}"),
            (t("Negative predictive value (NPV)"), _p1(_ff["npv"]), _ciw(_ff["npv_ci"]),
             f"{_ff['tn']} / {_ff['n_cand_neg']}"),
            (t("Correctly classified"), _p1(_ff["opa"]), _ciw(_ff["opa_ci"]),
             f"{_ff['tp']+_ff['tn']} / {_ff['n']}"),
            (t("Prevalence in the material"), _p1(_ff["prevalence"]),
             _ciw(_ff["prevalence_ci"]), f"{_ff['n_ref_pos']} / {_ff['n']}"),
            (t("Positive likelihood ratio (LR+)"), _p2(_ff["lr_pos"]), "", ""),
            (t("Negative likelihood ratio (LR−)"), _p2(_ff["lr_neg"]), "", ""),
        ]
        _head = (t("Sensitivity"), _ff["ppa"], _ff["ppa_ci"],
                 t("Specificity"), _ff["npa"], _ff["npa_ci"])
    else:
        _rows = [
            (t("Positive percent agreement (PPA)"), _p1(_ff["ppa"]), _ciw(_ff["ppa_ci"]),
             f"{_ff['tp']} / {_ff['n_ref_pos']}"),
            (t("Negative percent agreement (NPA)"), _p1(_ff["npa"]), _ciw(_ff["npa_ci"]),
             f"{_ff['tn']} / {_ff['n_ref_neg']}"),
            (t("Overall percent agreement (OPA)"), _p1(_ff["opa"]), _ciw(_ff["opa_ci"]),
             f"{_ff['tp']+_ff['tn']} / {_ff['n']}"),
        ]
        _head = ("PPA", _ff["ppa"], _ff["ppa_ci"],
                 "NPA", _ff["npa"], _ff["npa_ci"])

    _rows += [
        (t("Cohen's kappa"), _p3(_ff["kappa"]), _ciw(_ff["kappa_ci"], _p3),
         t(_ff["kappa_tolkning"])),
        (t("McNemar test (p)"),
         ("< 0,001" if _ff["mcnemar_p"] < 0.001 else _p3(_ff["mcnemar_p"])),
         t(_ff["mcnemar_metod"]),
         t("systematic difference") if _ff["mcnemar_p"] < 0.05 else t("none detected")),
    ]

    # Två nyckeltal överst, resten i tabellen under
    _h1, _h2 = st.columns(2)
    _h1.metric(_head[0], _p1(_head[1]), f"{_ciw(_head[2])} {_KI}")
    _h2.metric(_head[3], _p1(_head[4]), f"{_ciw(_head[5])} {_KI}")

    st.dataframe(
        _tdf(pd.DataFrame(_rows, columns=[t("Measure"), t("Value"), _KI, t("Count / interpretation")])),
        use_container_width=True, hide_index=True)

    if _warn:
        with st.expander(f'{t("⚠️ Points to consider")} ({len(_warn)})', expanded=True):
            for _w in _warn:
                st.caption("• " + _w)

    with st.expander(t("ℹ️ Interpretation")):
        st.markdown(t("""
**Which measures apply** — if neither method can be considered a gold
standard, sensitivity and specificity may not be claimed. Positive and
negative percent agreement (PPA/NPA) are reported instead. This is the
explicit recommendation of CLSI EP12-A2 and the FDA.

**Confidence intervals** — calculated with the Wilson score method, which
gives sensible limits even at 0 % and 100 % where the ordinary method
fails. The width reflects how many samples were included, not how good
the method is.

**Cohen's kappa** — agreement corrected for that which arises by chance
alone. The interpretation thresholds are arbitrary conventions.

**McNemar test** — tests whether the disagreements are systematically
skewed, that is whether one method more often gives a positive result
than the other. Only the discordant cells contribute. A low p-value means
a systematic difference, not necessarily a clinically important one.

**Predictive values** apply only at the prevalence of the material
examined and cannot be transferred to a population with a different
prevalence.
"""))

    # ── Export ───────────────────────────────────────────────────────────────
    st.divider()
    st.subheader(t("Export"))
    _ff_xl = build_fourfold_excel(
        _ff, ref_name=x_label, cand_name=y_label, analyte=ff_analyte,
        pos_label=ff_pos_label, neg_label=ff_neg_label, warnings=_warn, t=t)
    _e1,_e2,_ = st.columns([1,1,2])
    _e1.download_button(
        t("📊 Download fourfold table (Excel)"), _ff_xl,
        f"fyrfaltstabell{('_'+ff_analyte.replace(' ','_')) if ff_analyte else ''}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="ff_xl")
    _ff_rows = [
        ["Sant positiva (TP)", _ff["tp"]], ["Falskt positiva (FP)", _ff["fp"]],
        ["Falskt negativa (FN)", _ff["fn"]], ["Sant negativa (TN)", _ff["tn"]],
        ["Antal totalt", _ff["n"]],
        ["PPA/Sensitivitet (%)", fmt(_ff["ppa"],1)],
        ["NPA/Specificitet (%)", fmt(_ff["npa"],1)],
        ["OPA (%)", fmt(_ff["opa"],1)],
        ["Cohens kappa", fmt(_ff["kappa"],3)],
        ["McNemar p", fmt(_ff["mcnemar_p"],4)],
    ]
    _e2.download_button(
        t("📥 Results (CSV)"),
        to_csv_bytes(pd.DataFrame(_ff_rows, columns=["Mått","Värde"])),
        "fyrfaltstabell.csv", "text/csv", key="ff_csv")


# ══════════════════════════════════════════════════════════════════════════════
# BRANCH C — Precision Evaluation (EP15-A3)
# ══════════════════════════════════════════════════════════════════════════════
else:
    st.subheader(t("Precision Evaluation — CLSI EP15-A3"))

    _pr_tab1, _pr_tab2, _pr_tab3 = st.tabs([
        t("📂 Wide format (columns = days)"),
        t("📋 Paste wide format"),
        t("🔍 Long format (search by Sample ID)"),
    ])

    _pr_data_dict = None
    _prlf_raw_df  = None
    _prlf_sample_id = ""; _prlf_analyte_sel = ""

    with _pr_tab1:
        st.caption(t("Each column = one day, each row = one replicate. Column headers = day names."))
        _pr_file = st.file_uploader(t("Upload Excel or CSV"),type=["csv","xlsx","xls"],key="pr_file")
        if _pr_file is not None:
            try:
                _pr_rb = _pr_file.read()
                if _pr_file.name.lower().endswith((".xlsx",".xls")):
                    _pr_df = pd.read_excel(BytesIO(_pr_rb), header=0)
                else:
                    _pr_df = pd.read_csv(BytesIO(_pr_rb), sep=None, engine="python")
                _pr_df.columns = [f"Column {i+1}" if str(c).strip().lstrip("-").isdigit()
                                   else str(c) for i,c in enumerate(_pr_df.columns)]
                st.caption(t("Preview — {r} replicates × {d} days (all rows shown):")
                           .format(r=len(_pr_df), d=len(_pr_df.columns)))
                st.dataframe(_pr_df, use_container_width=True)
                _pr_data_dict = precision_from_dataframe(_pr_df)
            except Exception as _e:
                st.error(f"Could not read file: {_e}")

    with _pr_tab2:
        st.markdown(t("Copy from Excel (columns = days) and paste below."))
        _pr_paste = st.text_area(t("Paste here"), height=180,
            placeholder="Day 1\tDay 2\tDay 3\tDay 4\tDay 5\n2,015\t2,019\t2,025\t1,972\t1,981",
            key="pr_paste")
        if _pr_paste and _pr_paste.strip():
            try:
                from io import StringIO as _SIO
                _pr_df2 = pd.read_csv(_SIO(_pr_paste), sep="\t", decimal=",")
                if _pr_df2.shape[1] < 2:
                    _pr_df2 = pd.read_csv(_SIO(_pr_paste), sep="\t")
                _pr_df2.columns = [str(c) for c in _pr_df2.columns]
                st.caption(t("Preview — {r} replicates × {d} days (all rows shown):")
                           .format(r=len(_pr_df2), d=len(_pr_df2.columns)))
                st.dataframe(_pr_df2, use_container_width=True)
                _pr_data_dict = precision_from_dataframe(_pr_df2)
            except Exception as _e:
                st.error(f"Could not parse: {_e}")

    with _pr_tab3:
        st.markdown(
            t("Upload a long-format file with **SampleID | Analysis | Result** columns. "
            "Search for a Sample ID and split results into days automatically."))
        _lf_pr_file = st.file_uploader(t("Upload long-format file"),
                                        type=["csv","xlsx","xls"], key="lf_pr_file")
        if _lf_pr_file is not None:
            try:
                _lf_pr_rb  = _lf_pr_file.read()
                _pr_hdr_choice = st.radio(
                    t("Header row?"), ["Yes (first row)", "No header"],
                    horizontal=True, key="lf_pr_hdr",
                    help="Choose 'No header' if the very first row is already data.", format_func=t)
                _pr_has_hdr = _pr_hdr_choice == "Yes (first row)"
                _lf_pr_df  = load_long_format(_lf_pr_rb, _lf_pr_file.name,
                                              has_header=_pr_has_hdr)
                if not _pr_has_hdr:
                    st.caption(t("Columns named Column 1, Column 2 … — first row kept as data."))
                _lf_pr_cols= list(_lf_pr_df.columns)
                _lfc=st.columns(3)
                _lf_pr_id_col  =_lfc[0].selectbox(t("Sample ID column"),_lf_pr_cols,key="lf_pr_id")
                _lf_pr_res_col =_lfc[1].selectbox(t("Result column"),_lf_pr_cols,
                                                    index=min(2,len(_lf_pr_cols)-1),key="lf_pr_res")
                _lf_pr_sort_col=_lfc[2].selectbox(t("Sort by (run order/date)"),
                                                    ["N/A"]+_lf_pr_cols,key="lf_pr_sort")
                _lf_pr_sort=None if _lf_pr_sort_col=="N/A" else _lf_pr_sort_col
                _an_cols=[c for c in _lf_pr_cols if c not in [_lf_pr_id_col,_lf_pr_res_col]]
                _lf_pr_an_col=st.selectbox(t("Analysis"),
                                            ["N/A"]+_an_cols,key="lf_pr_an")
                _lf_pr_analyte=None
                if _lf_pr_an_col != "N/A":
                    _an_avail=sorted(_lf_pr_df[_lf_pr_an_col].dropna().astype(str).unique())
                    _lf_pr_analyte=st.selectbox(t("Select analyte"),_an_avail,key="lf_pr_analyte_sel")
                    _prlf_analyte_sel=_lf_pr_analyte or ""
                _all_ids=sorted(_lf_pr_df[_lf_pr_id_col].dropna().astype(str).unique())
                _prlf_sample_id=st.selectbox(t("Select Sample ID"),_all_ids,key="lf_pr_sid")
                # How are days defined?
                _pr_grp_mode = st.radio(
                    t("How are days defined?"),
                    ["Group by a date / day column", "Split every N results"],
                    key="lf_pr_grpmode",
                    help="If your file has a Date column, grouping by it is "
                         "safer — the number of replicates per day can differ "
                         "between analytes.", format_func=t)
                _lf_pr_group = None
                _lf_pr_n = 5
                if _pr_grp_mode == "Group by a date / day column":
                    _grp_opts = [c for c in _lf_pr_cols if c != _lf_pr_res_col]
                    _dflt = 0
                    for _i, _c in enumerate(_grp_opts):
                        if "date" in str(_c).lower() or "day" in str(_c).lower():
                            _dflt = _i; break
                    _lf_pr_group = st.selectbox(t("Day column"), _grp_opts,
                                                index=_dflt, key="lf_pr_grpcol")
                else:
                    _lf_pr_n=st.number_input(t("Results per day (n)"),
                                              min_value=2,max_value=50,
                                              value=5,step=1,key="lf_pr_n")
                _prev_mask=_lf_pr_df[_lf_pr_id_col].astype(str)==_prlf_sample_id
                if _lf_pr_analyte and _lf_pr_an_col != "N/A":
                    _prev_mask&=_lf_pr_df[_lf_pr_an_col].astype(str)==_lf_pr_analyte
                st.caption(t("Preview — {n} rows for this sample:").format(n=int(_prev_mask.sum())))
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
                _nrep = len(next(iter(_prlf_dd.values())))
                if _prlf_nl > 0 and _lf_pr_group:
                    st.warning(t("⚠️ {n} result(s) not used: the calculation requires the "
                                 "same number of replicates every day, so each day was "
                                 "limited to its first {m} results. They are marked in "
                                 "the raw data.").format(n=_prlf_nl, m=_nrep))
                elif _prlf_nl > 0:
                    st.warning(t("⚠️ {n} trailing result(s) excluded (incomplete day).")
                               .format(n=_prlf_nl))
                st.success(t("✅ {d} days × {r} replicates ready.").format(
                    d=len(_prlf_dd), r=_nrep))
            except Exception as _e:
                st.error(f"{t('Error')}: {_e}")

    if _pr_data_dict is None:
        st.info(t("Choose a data source above to begin the precision analysis."))
        st.stop()

    # Validate
    _pr_days = list(_pr_data_dict.keys())
    _pr_ns   = [len(v) for v in _pr_data_dict.values()]
    if len(_pr_days) < 2:
        st.error(t("Need at least 2 days of data.")); st.stop()
    if min(_pr_ns) < 2:
        st.error(t("Need at least 2 replicates per day.")); st.stop()
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
    st.subheader(t("Precision Results"))
    _di1,_di2,_di3,_di4 = st.columns(4)
    _di1.metric(t("Grand mean"),    _pf(_pr["grand_mean"]))
    _di2.metric(t("Days"),          str(_pr["D"]))
    _di3.metric(t("Replicates / day"), str(_pr["n"]))
    _di4.metric(t("Total measurements"), str(_pr["D"] * _pr["n"]))

    st.divider()

    # ── Two large headline boxes ──────────────────────────────────────────────
    _h1, _h2 = st.columns(2)
    with _h1:
        st.markdown("""
<div style="background:#EFF6FF;border-radius:12px;padding:20px 24px;border:1px solid #BFDBFE">
<p style="margin:0;font-size:0.78rem;color:#1E40AF;font-weight:600;letter-spacing:0.05em">{h}</p>
<p style="margin:4px 0 0;font-size:2rem;font-weight:700;color:#1E3A5F">CV = {cv} %</p>
<p style="margin:2px 0 0;font-size:1.1rem;color:#2563EB">SD = {sd}</p>
<p style="margin:8px 0 0;font-size:0.75rem;color:#64748B">df = {df} &nbsp;|&nbsp; {p}</p>
</div>
""".format(sd=_pf(_pr["sr"]), cv=_pf(_pr["cv_r"]), df=_pr["df_within"],
           h=t("WITHIN-RUN (REPEATABILITY)"), p=t("Protocol: CLSI EP15-A3")),
        unsafe_allow_html=True)

    with _h2:
        st.markdown("""
<div style="background:#F0FDF4;border-radius:12px;padding:20px 24px;border:1px solid #BBF7D0">
<p style="margin:0;font-size:0.78rem;color:#166534;font-weight:600;letter-spacing:0.05em">{h}</p>
<p style="margin:4px 0 0;font-size:2rem;font-weight:700;color:#14532D">CV = {cv} %</p>
<p style="margin:2px 0 0;font-size:1.1rem;color:#16A34A">SD = {sd}</p>
<p style="margin:8px 0 0;font-size:0.75rem;color:#64748B">{e} = {df} &nbsp;|&nbsp; {i}</p>
</div>
""".format(sd=_pf(_pr["sl"]), cv=_pf(_pr["cv_l"]), df=f"{_pr['T']:.1f}",
           h=t("WITHIN-LABORATORY (TOTAL IMPRECISION)"), e=t("eff. df"),
           i=t("Includes between-day variation")),
        unsafe_allow_html=True)

    if _pr["sb2"] <= 0:
        st.info(
            t("**Between-day variance estimated as zero**, so the within-run "
              "and within-laboratory figures are identical. This is a valid "
              "ANOVA result, not an error: the scatter between day means "
              "(s²day = {a}) is smaller than what within-run noise alone "
              "would produce (S²r/n = {b}), so the negative variance "
              "component is truncated to zero (CLSI EP15-A3). It usually "
              "means there is no detectable day-to-day effect — check that "
              "your days are grouped correctly.")
            .format(a=f"{_pr['s_day2']:.6g}",
                    b=f"{_pr['sr2']/_pr['n']:.6g}"))

    # ── Simple pooled SD/CV, shown beneath the CLSI figures ──────────────────
    st.markdown("")
    st.markdown("""
<div style="background:#F8FAFC;border-radius:12px;padding:16px 24px;
            border:1px solid #E2E8F0;border-left:4px solid #94A3B8">
<p style="margin:0;font-size:0.78rem;color:#475569;font-weight:600;letter-spacing:0.05em">
{h}</p>
<p style="margin:4px 0 0;font-size:1.5rem;font-weight:700;color:#334155">
CV = {cv} %</p>
<p style="margin:2px 0 0;font-size:1rem;color:#64748B">SD = {sd}</p>
<p style="margin:8px 0 0;font-size:0.75rem;color:#64748B">
df = {df} &nbsp;|&nbsp; {o}</p>
</div>
""".format(cv=_pf(_pr["pooled_cv"]), sd=_pf(_pr["pooled_sd"]), df=_pr["pooled_df"],
           h=t("TOTAL IMPRECISION — SIMPLE POOLED CALCULATION "
               "(all {nm} results as one set)").format(nm=_pr["n_total_meas"]),
           o=t("ordinary SD of every measurement, day structure ignored")),
        unsafe_allow_html=True)

    with st.expander(t("ℹ️ Why does this differ from the CLSI value?")):
        st.markdown(t("""
The **CLSI within-laboratory SD** separates the data into a within-run and a
between-day component and adds them on the variance scale
(Sl² = Sr² + Sb²). The **simple pooled SD** ignores the day structure and
treats all {n} results as a single sample.

The two are related exactly, in expectation, by

E[s²pooled] = Sr² + **{f}** × Sb²  where the factor is (D−1)n / (Dn−1)

So the simple calculation shrinks the between-day component by
**{p} %** with your design of {D} days × {r} replicates. Consequences:

- If there is **no** day-to-day effect (Sb² = 0) the two agree closely.
- If a real day effect exists, the pooled value is **biased low** and
  understates the imprecision a clinician would encounter between days.
- The gap narrows as the number of days increases.

Report the **CLSI value** for method validation and verification against a
manufacturer's claim. The pooled figure is provided for reference and for
comparison with sources that use the simplified approach.
""").format(n=_pr['n_total_meas'], f=f"{_pr['pooled_shrink']:.4f}",
            p=f"{100*(1-_pr['pooled_shrink']):.1f}", D=_pr['D'], r=_pr['n']))

    st.markdown("")   # spacer

    # ── Sammanfattning i laboratoriets tabellformat ───────────────────────────
    st.markdown(t("**Sammanfattning**"))
    def _pct(v): return f"{v:.1f}".replace(".", ",") + "%"
    _summary_df = pd.DataFrame({
        (_prlf_analyte_sel or t("Analysis")): [
            t("Count:"), t("Mean:"), "SD:", "CV%:", "Min:", "Max:",
            t("Within-run precision CV%:"), t("Total imprecision CV%:")],
        (_prlf_sample_id or t("Control")): [
            str(_pr["n_total_meas"]),
            _pf(_pr["grand_mean"]),
            _pf(_pr["pooled_sd"]),
            _pct(_pr["pooled_cv"]),
            _pf(_pr["overall_min"]),
            _pf(_pr["overall_max"]),
            _pct(_pr["cv_r"]),
            _pct(_pr["cv_l"]),
        ],
    })
    st.dataframe(_summary_df, use_container_width=False, hide_index=True)
    st.caption(t("SD and CV% refer to all {n} measurements pooled. Within-run "
                 "precision and total imprecision according to CLSI EP15-A3. "
                 "Design: {D} days × {r} replicates.")
               .format(n=_pr['n_total_meas'], D=_pr['D'], r=_pr['n']))

    # ── Full breakdown table ──────────────────────────────────────────────────
    with st.expander(t("📊 Full variance component breakdown"), expanded=False):
        st.dataframe(_tdf(pd.DataFrame([
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
        ])), use_container_width=True, hide_index=True)

    # ── Verification against manufacturer claims ──────────────────────────────
    if prec_claimed_sr is not None or prec_claimed_sl is not None:
        st.markdown(t("**Chi-square verification (EP15-A3 §2.4.3)**"))
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
        st.dataframe(_tdf(pd.DataFrame(_vrows)), use_container_width=True, hide_index=True)

    # ── Per-day summary ───────────────────────────────────────────────────────
    with st.expander(t("📋 Per-day summary")):
        _day_df = pd.DataFrame(_pr["day_summary"])
        for _col in ["Mean","SD","CV (%)","Min","Max"]:
            _day_df[_col] = _day_df[_col].map(_pf)
        st.dataframe(_tdf(_day_df), use_container_width=True, hide_index=True)

    # ── Outliers ──────────────────────────────────────────────────────────────
    if _pr["outliers"]:
        st.warning(
            f"⚠️ {len(_pr['outliers'])} potential outlier(s) detected "
            "(|deviation| > 3.5 × Sᵣ). Investigate before accepting results.")
        _ol_df = pd.DataFrame(_pr["outliers"])
        _ol_df["Deviation / Sᵣ"] = _ol_df["Deviation / Sr"].map(lambda v: f"{v:.2f}")
        _ol_df = _ol_df.drop(columns=["Deviation / Sr"])
        st.dataframe(_tdf(_ol_df), use_container_width=True, hide_index=True)

    # ── Export — journal-style table ──────────────────────────────────────────
    st.divider()
    st.subheader(t("Export"))

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
        {"Day": t("Within-run (repeatability)") + "ᵃ",
         **{f"Rep {i+1}": "" for i in range(_n_reps)},
         "Mean": "", "SD": _pf(_pr["sr"]), "CV (%)": _pf(_pr["cv_r"])},
        {"Day": t("Within-laboratory (total)") + "ᵇ",
         **{f"Rep {i+1}": "" for i in range(_n_reps)},
         "Mean": "", "SD": _pf(_pr["sl"]), "CV (%)": _pf(_pr["cv_l"])},
        {"Day": t("Simple pooled (all results)") + "ᵈ",
         **{f"Rep {i+1}": "" for i in range(_n_reps)},
         "Mean": "", "SD": _pf(_pr["pooled_sd"]), "CV (%)": _pf(_pr["pooled_cv"])},
    ]
    if prec_claimed_sr is not None:
        _footer.append({
            "Day": t("Manufacturer claim — repeatability") + "ᶜ",
            **{f"Rep {i+1}": "" for i in range(_n_reps)},
            "Mean": "", "SD": _pf(prec_claimed_sr),
            "CV (%)": "Pass" if _pr["pass_sr"] else "Fail",
        })
    if prec_claimed_sl is not None:
        _footer.append({
            "Day": t("Manufacturer claim — within-laboratory") + "ᶜ",
            **{f"Rep {i+1}": "" for i in range(_n_reps)},
            "Mean": "", "SD": _pf(prec_claimed_sl),
            "CV (%)": "Pass" if _pr["pass_sl"] else "Fail",
        })

    _footer_df = pd.DataFrame(_footer, columns=_all_cols)
    _full_jdf  = pd.concat([_jdf, _footer_df], ignore_index=True)

    # Footnotes
    _footnotes = [
        t("ᵃ Within-run SD (Sᵣ) = {sd}, CV% = {cv} (df = {df}; CLSI EP15-A3).")
        .format(sd=_pf(_pr['sr']), cv=_pf(_pr['cv_r']), df=_pr['df_within']),
        t("ᵇ Within-laboratory SD (Sₗ) = {sd}, CV% = {cv} (effective df = {df}; "
          "includes between-day variation).")
        .format(sd=_pf(_pr['sl']), cv=_pf(_pr['cv_l']), df=f"{_pr['T']:.1f}"),
        t("  Grand mean = {m}, D = {D} days, n = {n} replicates/day.")
        .format(m=_pf(_pr['grand_mean']), D=_pr['D'], n=_pr['n']),
        t("ᵈ Ordinary SD of all {n} results, day structure ignored (df = {df}). "
          "Shown for reference; it shrinks the between-day component by a "
          "factor {f} and is therefore biased low when a day effect exists.")
        .format(n=_pr['n_total_meas'], df=_pr['pooled_df'],
                f=f"{_pr['pooled_shrink']:.3f}"),
    ]
    if prec_claimed_sr is not None or prec_claimed_sl is not None:
        _footnotes.append(
            t("ᶜ Chi-square verification (α = {a}, q = {q}); Pass if observed "
              "SD ≤ verification value.")
            .format(a=f"{float(prec_alpha):.0%}", q=prec_n_levels))

    # Preview in app
    st.caption(t("Journal-style precision table — days as rows, replicates as columns, "
               "precision summary in footer:"))
    st.dataframe(_tdf(_full_jdf.set_index("Day")), use_container_width=True)

    for _fn in _footnotes:
        st.caption(_fn)

    # Build download: table + footnotes as trailing rows
    _fn_rows = [{"Day": fn, **{c: "" for c in _all_cols if c != "Day"}}
                for fn in _footnotes]
    _dl_df = pd.concat(
        [_full_jdf, pd.DataFrame(_fn_rows, columns=_all_cols)],
        ignore_index=True
    ).set_index("Day")
    _dl_df = _tdf(_dl_df)          # download follows the interface language

    st.download_button(
        t("📥 Download journal table (CSV)"),
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
            t=t,
        )
        st.download_button(
            t("📊 Download Excel (raw data + summary)"),
            _pr_xlsx,
            "precision_results.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pr_xl",
        )
    except Exception as _e:
        st.caption(f"Excel export unavailable: {_e}")
