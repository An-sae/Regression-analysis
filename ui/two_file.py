"""
Tvåfilsflödet: två exporter in, matchade par ut.

Utbrutet ur app.py (v2.2.0) för att det viktigaste arbetsflödet ska gå att
läsa, testa och ändra för sig. All beräkning sker i analysis/*; här finns
bara gränssnittet. Widgetnycklarna är oförändrade mot v2.1.0.
"""
import numpy as np
import streamlit as st

from analysis.data_loader import (load_long_format, match_two_files, find_duplicates,
                                  list_analytes, MultipleResultsError, build_matched_excel)
from analysis.file_reader import (list_sheets, best_sheet, guess_column, suggest_analyte,
                                  detect_layout, to_long, WIDE_AN, WIDE_RES)
from analysis.overview import suggested_pairs, compare_all, build_overview_excel

DUP_LBL = {"first_valid": "Keep first valid", "last_valid": "Keep last valid",
           "mean": "Use mean", "first": "Keep first", "last": "Keep last"}
LAYOUT_LBL = {"auto": "Automatic", "long": "Long: one row per result",
              "wide": "Wide: one column per analysis"}


def _ix(opts, guess, fallback=0):
    return opts.index(guess) if guess in opts else min(fallback, len(opts) - 1)


def _read(t, uf, fl, auto):
    """Läs en uppladdad fil (bytes cachas mellan omkörningar)."""
    k = fl.lower()
    if st.session_state.get(f"lf_fname_{k}") != uf.name or f"lf_rb_{k}" not in st.session_state:
        st.session_state[f"lf_rb_{k}"] = uf.read()
        st.session_state[f"lf_fname_{k}"] = uf.name
    raw = st.session_state[f"lf_rb_{k}"]
    sheets, sh = list_sheets(raw, uf.name), None
    if len(sheets) > 1:
        sh = st.selectbox(t(f"Sheet in file {fl}"), sheets,
                          index=sheets.index(best_sheet(raw, uf.name)), key=f"lf_sh{k}")
    return load_long_format(raw, uf.name, has_header=auto, sheet=sh)


def _columns(t, fl, df, layout_choice):
    """Kolumnval för en fil. Returnerar (lång tabell, id, analyskolumn|None, resultat, layout)."""
    k = fl.lower()
    cols = list(df.columns)
    L = detect_layout(df)
    layout = L["layout"] if layout_choice == "auto" else layout_choice
    st.markdown(t(f"**Column mapping — File {fl}**"))
    if layout == "wide":
        id_col = st.selectbox(t("Sample ID"), cols,
                              index=_ix(cols, L["id_col"] or guess_column(cols, "id")),
                              key=f"lf_id{k}")
        cand = [c for c in cols if c != id_col]
        default = [c for c in L["numeric_cols"] if c in cand]
        with st.expander(t("Result columns: {n} selected").format(
                n=len(st.session_state.get(f"lf_vc{k}", default)))):
            vcols = st.multiselect(t("One column per analysis"), cand, default=default,
                                   key=f"lf_vc{k}")
        if not vcols:
            raise ValueError(t("Choose at least one result column in file {f}.").format(f=fl))
        return to_long(df, id_col, vcols), id_col, WIDE_AN, WIDE_RES, layout
    c3 = st.columns(3)
    id_col = c3[0].selectbox(t("Sample ID"), cols, index=_ix(cols, guess_column(cols, "id")),
                             key=f"lf_id{k}")
    an_opts = ["N/A"] + cols
    an = c3[1].selectbox(t("Analysis"), an_opts, index=_ix(an_opts, guess_column(cols, "an")),
                         key=f"lf_an{k}")
    res = c3[2].selectbox(t("Result"), cols, index=_ix(cols, guess_column(cols, "res"), 2),
                          key=f"lf_rs{k}")
    return df, id_col, (None if an == "N/A" else an), res, layout


def two_file_sidebar(t) -> dict:
    """Hela tvåfilsflödet i sidomenyn. Returnerar resultat och sammanhang."""
    out = dict(x=None, y=None, report=None, label_a="Method A", label_b="Method B",
               analyte="ALL", matched_xlsx=None, error=None, ctx=None)
    st.markdown(t("**File A — Reference method**"))
    uf_a = st.file_uploader(t("Upload reference file"), type=["csv", "xlsx", "xls", "txt"], key="lf_fa")
    st.markdown(t("**File B — Candidate method**"))
    uf_b = st.file_uploader(t("Upload candidate file"), type=["csv", "xlsx", "xls", "txt"], key="lf_fb")
    if uf_a is None or uf_b is None:
        return out
    try:
        auto = st.radio(t("Header row"), ["Automatic", "No header"], horizontal=True,
                        key="lf_hdr", format_func=t,
                        help=t("Automatic finds the header row even when the export "
                               "starts with instrument or title rows.")) == "Automatic"
        df_a, df_b = _read(t, uf_a, "A", auto), _read(t, uf_b, "B", auto)

        with st.expander(t("⚙️ Matching options")):
            lay_a = st.selectbox(t("Layout of file A"), list(LAYOUT_LBL), key="lf_lay_a",
                                 format_func=lambda v: t(LAYOUT_LBL[v]))
            lay_b = st.selectbox(t("Layout of file B"), list(LAYOUT_LBL), key="lf_lay_b",
                                 format_func=lambda v: t(LAYOUT_LBL[v]))
            zeros = st.toggle(t("Ignore leading zeros in numeric sample IDs"), value=True,
                              key="lf_zeros",
                              help=t("Excel removes leading zeros, so 0012345 in one file "
                                     "and 12345 in the other are treated as the same sample."))
            factor = st.number_input(t("Conversion factor for file B"), min_value=0.0,
                                     value=1.0, step=0.1, format="%g", key="lf_factor",
                                     help=t("Multiplies every result in file B, e.g. 0.1 "
                                            "to convert g/L to g/dL. 1 = no conversion."))

        A, id_a, an_a, rs_a, la = _columns(t, "A", df_a, lay_a)
        out["label_a"] = st.text_input(t("Label A"), t("Reference"), key="lf_la")
        B, id_b, an_b, rs_b, lb = _columns(t, "B", df_b, lay_b)
        out["label_b"] = st.text_input(t("Label B"), t("Candidate"), key="lf_lb")

        for fl, df, lay, AL, anc in (("A", df_a, la, A, an_a), ("B", df_b, lb, B, an_b)):
            ri = df.attrs.get("read_info", {})
            src = (t("sheet {s}").format(s=ri.get("sheet")) if ri.get("kind") == "Excel"
                   else f"{t(ri.get('encoding', ''))} · {t(ri.get('delimiter', ''))}")
            hdr = (t("header on row {h}").format(h=ri.get("header_row"))
                   if ri.get("header_row") else t("no header"))
            fmt = (t("wide, {n} analyses").format(n=AL[WIDE_AN].nunique())
                   if lay == "wide" else t("long"))
            st.caption(t("File {f}: {n} rows · {src} · {hdr}").format(
                f=fl, n=ri.get("n_rows", len(df)), src=src, hdr=hdr) + f" · {fmt}")

        # ── Analys i respektive fil ────────────────────────────────────────
        an_sel_a = an_sel_b = None
        if an_a:
            an_sel_a = st.selectbox(t("Analysis in file A"), list_analytes(A, an_a), key="lf_analyte_a")
        if an_b:
            lst_b = list_analytes(B, an_b)
            sug, why = suggest_analyte(an_sel_a, lst_b) if an_sel_a else (None, "")
            an_sel_b = st.selectbox(t("Analysis in file B"), lst_b,
                                    index=lst_b.index(sug) if sug in lst_b else 0,
                                    key=f"lf_analyte_b_{an_sel_a}")
            if an_sel_a and sug is None:
                st.warning(t("No matching analysis name found in file B — choose it manually."))
            elif sug and why != "exact" and an_sel_b == sug:
                st.caption(t("Suggested pairing: {a} ↔ {b} — please check.").format(a=an_sel_a, b=an_sel_b))
        single = False
        if an_a is None or an_b is None:
            single = st.checkbox(t("The file without an analysis column contains only one "
                                   "analysis (repeated sample IDs are reruns)"), key="lf_single")

        # ── Omkörningar ────────────────────────────────────────────────────
        dup = "first_valid"
        d_a = find_duplicates(A, id_a, an_a, rs_a, zeros)
        d_b = find_duplicates(B, id_b, an_b, rs_b, zeros)
        if (not d_a.empty or not d_b.empty) and (an_a and an_b or single):
            st.warning(t("⚠️ Repeated results (reruns): file A {a} rows, file B {b} rows.")
                       .format(a=len(d_a), b=len(d_b)))
            dup = st.radio(t("Resolve duplicates"), list(DUP_LBL), key="lf_dup",
                           format_func=lambda v: t(DUP_LBL[v]))

        # ── Matchning ──────────────────────────────────────────────────────
        x, y, rep, s = match_two_files(A, B, id_a, id_b, an_a, an_b, rs_a, rs_b,
                                       an_sel_a or "ALL", an_sel_b or "ALL",
                                       out["label_a"], out["label_b"],
                                       ignore_leading_zeros=zeros, dup_strategy=dup,
                                       single_analyte=single)
        if factor and factor != 1.0:
            y = y * factor
            rep[out["label_b"]] = rep[out["label_b"]] * factor
        out.update(x=x, y=y, report=rep)
        out["analyte"] = ("ALL" if not (an_sel_a or an_sel_b) else
                          (an_sel_a or an_sel_b) if an_sel_a == an_sel_b or not (an_sel_a and an_sel_b)
                          else f"{an_sel_a} ↔ {an_sel_b}")
        _report_messages(t, s, factor)
        with st.expander(t("🔎 How the values were read")):
            pv = rep[rep["Match"] == "Matched"][["SampleID", "Original A", out["label_a"],
                                                 "Original B", out["label_b"], "Note"]]
            st.dataframe(pv.sort_values("Note", ascending=False, kind="stable").head(200),
                         hide_index=True, use_container_width=True)
        out["matched_xlsx"] = build_matched_excel(rep, out["label_a"], out["label_b"], out["analyte"])
        out["ctx"] = dict(A=A, B=B, id_a=id_a, id_b=id_b, an_a=an_a, an_b=an_b, rs_a=rs_a,
                          rs_b=rs_b, zeros=zeros, dup=dup, label_a=out["label_a"],
                          label_b=out["label_b"])
    except MultipleResultsError:
        st.error(t("Several results per sample ID but no analysis column is selected, so "
                   "results cannot be paired safely. Choose the analysis column, or confirm "
                   "that the file contains only one analysis."))
        out["error"] = "multiple"
    except Exception as e:
        st.error(f"{t('Matching error')}: {e}")
        out["error"] = str(e)
    return out


def _report_messages(t, s, factor):
    if s["matched_ids"] == 0:
        st.warning(t("⚠️ No matched pairs — check column mapping."))
    else:
        st.success(t("✅ {m} samples matched · {u} pairs used").format(m=s["matched_ids"], u=s["used"]))
        st.caption(t("Only in A: {a}  |  Only in B: {b}").format(a=s["only_a"], b=s["only_b"]))
    if s["excluded"]:
        parts = []
        for k_, v_ in s["excluded_reasons"].items():
            side, rsn = k_.split(": ", 1)
            parts.append(f"{side}: {t(rsn)} × {v_}")
        st.info(t("{n} matched samples not used:").format(n=s["excluded"]) + " " + "; ".join(parts))
    n_sum = s.get("summary_rows_a", 0) + s.get("summary_rows_b", 0)
    if n_sum:
        st.caption(t("{n} summary rows ignored ({ex}).").format(
            n=n_sum, ex=", ".join(s.get("summary_ids", [])[:3])))
    if s.get("unit_factor") and (not factor or factor == 1.0):
        st.warning(t("The results in file B are about {f} times those in file A. Check the "
                     "units (e.g. g/L against g/dL); a conversion factor can be set under "
                     "⚙️ Matching options.").format(f=f"{s['unit_factor']:g}".replace(".", ",")))
    for fl in ("a", "b"):
        if s[f"sci_ids_{fl}"]:
            st.error(t("File {f}: {n} sample IDs are in scientific notation (e.g. 2,40915E+09) "
                       "and cannot be matched. Export the IDs as text.").format(
                f=fl.upper(), n=s[f"sci_ids_{fl}"]))
        p = s[f"parse_{fl}"]
        if p.get("ambiguous"):
            st.warning(t("File {f}: {n} results such as 1,234 could be either a decimal or a "
                         "thousands separator; read with decimal '{d}'. Check the values.").format(
                f=fl.upper(), n=p["ambiguous"], d=p["decimal"]))
        if p.get("conflict"):
            st.warning(t("File {f}: the result column mixes decimal comma and decimal point; "
                         "each value was read by its own format. Check the values.").format(f=fl.upper()))


def overview_panel(t, ctx, method, error_ratio, weighted, decimals, stamp, tdf):
    """Huvudytan: jämför alla kopplade analyser i en körning."""
    if not ctx or ctx["an_a"] is None or ctx["an_b"] is None:
        return
    with st.expander(t("📋 All analyses in the files"), expanded=False):
        pairs = suggested_pairs(ctx["A"], ctx["an_a"], ctx["B"], ctx["an_b"])
        st.caption(t("{n} analyses in file A have a matching analysis in file B. Check the "
                     "pairing, then run the overview with the current method ({m}).").format(
            n=len(pairs), m=t(method)))
        if not pairs:
            return
        import pandas as pd
        lst_b = list_analytes(ctx["B"], ctx["an_b"])
        edited = st.data_editor(
            pd.DataFrame({t("Include"): True, t("Analysis A"): [p[0] for p in pairs],
                          t("Analysis B"): [p[1] for p in pairs],
                          t("Pairing"): [t(p[2]) for p in pairs]}),
            column_config={t("Analysis B"): st.column_config.SelectboxColumn(options=lst_b, required=True),
                           t("Analysis A"): st.column_config.TextColumn(disabled=True),
                           t("Pairing"): st.column_config.TextColumn(disabled=True)},
            hide_index=True, use_container_width=True, key="ov_map")
        chosen = [(r[t("Analysis A")], r[t("Analysis B")], "manual")
                  for _, r in edited.iterrows() if r[t("Include")]]
        if st.button(t("▶ Run overview"), key="ov_run", disabled=not chosen):
            bar = st.progress(0.0)
            ov, det = compare_all(ctx["A"], ctx["B"], ctx["id_a"], ctx["id_b"], ctx["an_a"],
                                  ctx["an_b"], ctx["rs_a"], ctx["rs_b"], chosen, method=method,
                                  error_ratio=error_ratio, weighted=weighted,
                                  ignore_leading_zeros=ctx["zeros"], dup_strategy=ctx["dup"],
                                  label_a=ctx["label_a"], label_b=ctx["label_b"],
                                  progress=lambda i, n, a: bar.progress((i + 1) / n, text=a))
            bar.empty()
            st.session_state["ov_result"] = (ov, det, method)
        res = st.session_state.get("ov_result")
        if res:
            ov, det, m_used = res
            show = ov.copy()
            f = lambda v: "" if v is None or (isinstance(v, float) and np.isnan(v)) \
                else f"{v:.{decimals}f}".replace(".", ",")
            for c in ("Slope", "Intercept", "Mean bias", "Mean bias (%)", "r"):
                show[c] = show[c].map(f)
            for c in ("Slope 95% CI", "Intercept 95% CI"):
                show[c] = show[c].map(lambda v: "" if not v else f"{f(v[0])} – {f(v[1])}")
            show = show.drop(columns=["Pairing"])
            show["Note"] = show["Note"].map(
                lambda v: "; ".join(_t_note(p, t) for p in v.split("; ")) if v else v)
            st.caption(t("Method: {m}").format(m=t(m_used)))
            st.dataframe(tdf(show), hide_index=True, use_container_width=True)
            st.download_button(t("📊 Download overview (Excel)"),
                               build_overview_excel(ov, det, t=t, decimals=decimals, stamp=stamp),
                               "oversikt_alla_analyser.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="ov_dl")


def _t_note(p, t):
    from analysis.overview import _t_note as tn
    return tn(p, t)
