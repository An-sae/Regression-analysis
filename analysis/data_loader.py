"""
Data Loader — Long-format CSV matching and precision extraction
CLSI EP15-A3 compatible; matches SampleID x Analyte across two files.
"""
import io, numpy as np, pandas as pd
from typing import Dict, List, Optional, Tuple


def load_long_format(raw_bytes: bytes, fname: str,
                     has_header: bool = True) -> pd.DataFrame:
    """
    Read a long-format CSV/Excel file.

    has_header=True  -> first row is column names (default).
    has_header=False -> first row is DATA; columns are named
                        "Column 1", "Column 2", ... so nothing is lost.
    """
    fname_lower = fname.lower()
    _hdr = 0 if has_header else None
    try:
        if fname_lower.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(raw_bytes), header=_hdr)
        else:
            try:
                df = pd.read_csv(io.BytesIO(raw_bytes), sep=None, engine="python",
                                 decimal=",", header=_hdr)
                if df.select_dtypes(include=[np.number]).shape[1] == 0:
                    raise ValueError
            except Exception:
                df = pd.read_csv(io.BytesIO(raw_bytes), sep=None, engine="python",
                                 header=_hdr)
    except Exception as e:
        raise ValueError(f"Could not read file: {e}")

    if has_header:
        df.columns = [str(c).strip() for c in df.columns]
    else:
        df.columns = [f"Column {i+1}" for i in range(len(df.columns))]
    return df


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", ".").str.strip(), errors="coerce")


def find_duplicates(df, id_col, analysis_col, result_col) -> pd.DataFrame:
    counts = df.groupby([id_col, analysis_col])[result_col].transform("count")
    dups = df[counts > 1].copy()
    if not dups.empty:
        dups["_occurrence"] = dups.groupby([id_col, analysis_col]).cumcount() + 1
    return dups


def resolve_duplicates(df, id_col, analysis_col, result_col, strategy="first") -> pd.DataFrame:
    if strategy == "last":
        return df.drop_duplicates(subset=[id_col, analysis_col], keep="last")
    elif strategy == "mean":
        df = df.copy()
        df[result_col] = _coerce_numeric(df[result_col])
        return df.groupby([id_col, analysis_col], as_index=False)[result_col].mean()
    else:
        return df.drop_duplicates(subset=[id_col, analysis_col], keep="first")


def get_common_analytes(df_a, df_b, analysis_col_a, analysis_col_b) -> List[str]:
    set_a = set(df_a[analysis_col_a].dropna().astype(str).unique())
    set_b = set(df_b[analysis_col_b].dropna().astype(str).unique())
    return sorted(set_a & set_b)


def match_two_files(df_a, df_b, id_col_a, id_col_b, analysis_col_a, analysis_col_b,
                    result_col_a, result_col_b, selected_analyte,
                    label_a="Method A", label_b="Method B"):
    if selected_analyte != "ALL":
        df_a = df_a[df_a[analysis_col_a].astype(str) == selected_analyte].copy()
        df_b = df_b[df_b[analysis_col_b].astype(str) == selected_analyte].copy()

    df_a = df_a.copy(); df_b = df_b.copy()
    df_a[result_col_a] = _coerce_numeric(df_a[result_col_a])
    df_b[result_col_b] = _coerce_numeric(df_b[result_col_b])

    slim_a = df_a[[id_col_a, analysis_col_a, result_col_a]].rename(
        columns={id_col_a:"SampleID", analysis_col_a:"Analyte", result_col_a:label_a})
    slim_b = df_b[[id_col_b, analysis_col_b, result_col_b]].rename(
        columns={id_col_b:"SampleID", analysis_col_b:"Analyte", result_col_b:label_b})

    merged = pd.merge(slim_a, slim_b, on=["SampleID","Analyte"], how="outer", indicator=True)
    merged["Match"] = merged["_merge"].map({"both":"Matched","left_only":"Only in A","right_only":"Only in B"})
    merged = merged.drop(columns=["_merge"])

    matched = merged[merged["Match"] == "Matched"].copy()
    x_arr = matched[label_a].values.astype(float)
    y_arr = matched[label_b].values.astype(float)
    valid = np.isfinite(x_arr) & np.isfinite(y_arr)
    return x_arr[valid], y_arr[valid], merged


def extract_precision_replicates(df, id_col, result_col, sample_id,
                                  sort_col=None, analysis_col=None,
                                  analyte=None, n_per_day=5,
                                  group_col=None):
    """
    group_col : if given, rows are grouped by the DISTINCT VALUES of this column
                (e.g. a Date column) -> one day per value. This is the correct
                approach when the file records the real run date, because the
                number of replicates per day may vary between analytes.
                When None, rows are sliced every `n_per_day` in sort order.
    """
    mask = df[id_col].astype(str).str.strip() == str(sample_id).strip()
    sub = df[mask].copy()
    if analysis_col and analyte and analyte not in ("ALL", "", None):
        sub = sub[sub[analysis_col].astype(str).str.strip() == str(analyte).strip()]
    if sub.empty:
        raise ValueError(f"No rows found for SampleID = '{sample_id}'.")
    if sort_col and sort_col in sub.columns:
        try:
            sub[sort_col] = pd.to_datetime(sub[sort_col], infer_datetime_format=True)
        except Exception:
            pass
        sub = sub.sort_values(sort_col)
    sub = sub.reset_index(drop=True)
    sub[result_col] = _coerce_numeric(sub[result_col])
    sub = sub.dropna(subset=[result_col]).reset_index(drop=True)
    # ── Group by a real day/date column ──────────────────────────────────────
    if group_col is not None and group_col in sub.columns:
        _keys = sub[group_col]
        if pd.api.types.is_datetime64_any_dtype(_keys):
            _keys = _keys.dt.date
        sub = sub.copy()
        sub["_daykey"] = _keys.astype(str)
        _order = list(dict.fromkeys(sub["_daykey"]))   # preserve sorted order
        data_dict, counts = {}, []
        for i, k in enumerate(_order, start=1):
            vals = sub.loc[sub["_daykey"] == k, result_col].tolist()
            data_dict[f"Day {i}"] = vals
            counts.append(len(vals))
        if len(data_dict) < 2:
            raise ValueError(
                f"Only {len(data_dict)} distinct value(s) in '{group_col}' — "
                "need at least 2 days.")
        if min(counts) < 2:
            raise ValueError("Each day needs at least 2 replicates.")
        if min(counts) != max(counts):
            # Balance the design by truncating to the smallest day
            m = min(counts)
            data_dict = {k: v[:m] for k, v in data_dict.items()}
        sub["Day"] = sub["_daykey"].map(
            {k: f"Day {i}" for i, k in enumerate(_order, start=1)})
        sub = sub.drop(columns=["_daykey"])
        return data_dict, sub, 0

    # ── Otherwise: slice every n_per_day rows in sort order ──────────────────
    if len(sub) < n_per_day:
        raise ValueError(f"Only {len(sub)} valid results — need at least {n_per_day} (n_per_day).")
    n_complete = len(sub) // n_per_day
    sub["Day"] = [f"Day {i // n_per_day + 1}" if i < n_complete * n_per_day else "Incomplete"
                  for i in range(len(sub))]
    sub_complete = sub[sub["Day"] != "Incomplete"].copy()
    data_dict = {}
    for d in range(n_complete):
        lbl = f"Day {d+1}"
        vals = sub_complete.iloc[d*n_per_day:(d+1)*n_per_day][result_col].tolist()
        data_dict[lbl] = vals
    n_leftover = len(sub) % n_per_day
    return data_dict, sub_complete, n_leftover


def build_matched_excel(report_df, label_a="Method A", label_b="Method B", analyte="") -> bytes:
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment
    from openpyxl.utils.dataframe import dataframe_to_rows
    GREEN     = PatternFill("solid", fgColor="D1FAE5")   # included
    RED       = PatternFill("solid", fgColor="FECACA")   # excluded
    YELLOW    = PatternFill("solid", fgColor="FEF3C7")   # unmatched
    HDR_FILL  = PatternFill("solid", fgColor="1E40AF")
    HDR_FONT  = Font(color="FFFFFF", bold=True)
    RED_FONT  = Font(color="991B1B", bold=True)          # dark red, bold
    GREEN_FONT= Font(color="065F46")                     # dark green

    def _sheet(ws, df, fill, title, status_aware=False):
        """status_aware: colour each row by its Status column
           (Excluded -> red, otherwise green) instead of one flat fill."""
        ws.title = title
        if df.empty:
            ws.append([f"No rows: {title}"]); return

        cols = list(df.columns)
        status_i = cols.index("Status") + 1 if (status_aware and "Status" in cols) else None

        for ri, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
            ws.append(row)
            if ri == 1:
                for cell in ws[ri]:
                    cell.fill = HDR_FILL
                    cell.font = HDR_FONT
                    cell.alignment = Alignment(horizontal="center")
                continue

            row_fill, row_font = fill, None
            if status_i is not None:
                val = ws.cell(row=ri, column=status_i).value
                if str(val).strip().lower() == "excluded":
                    row_fill, row_font = RED, RED_FONT
                else:
                    row_fill, row_font = GREEN, GREEN_FONT

            for cell in ws[ri]:
                cell.fill = row_fill
                if row_font is not None:
                    cell.font = row_font

        ws.freeze_panes = "A2"
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(
                max(len(str(c.value or "")) for c in col) + 4, 40)

    wb = openpyxl.Workbook()
    matched = report_df[report_df["Match"]=="Matched"].drop(columns=["Match"])
    only_a  = report_df[report_df["Match"]=="Only in A"].drop(columns=[label_b,"Match"], errors="ignore")
    only_b  = report_df[report_df["Match"]=="Only in B"].drop(columns=[label_a,"Match"], errors="ignore")
    _sheet(wb.active, matched, GREEN, "Matched pairs", status_aware=True)
    _sheet(wb.create_sheet("Only in A"), only_a,  YELLOW, "Only in A")
    _sheet(wb.create_sheet("Only in B"), only_b,  YELLOW, "Only in B")
    buf = io.BytesIO(); wb.save(buf); buf.seek(0); return buf.read()


def build_precision_excel(raw_df, pr_results, sample_id, analyte, decimals=4) -> bytes:
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment
    from openpyxl.utils.dataframe import dataframe_to_rows
    HDR_FILL = PatternFill("solid", fgColor="1E40AF")
    HDR_FONT = Font(color="FFFFFF", bold=True)
    BLUE     = PatternFill("solid", fgColor="EFF6FF")
    GREEN    = PatternFill("solid", fgColor="ECFDF5")

    def _f(v): return f"{v:.{decimals}f}".replace(".",",")

    wb = openpyxl.Workbook()
    ws1 = wb.active; ws1.title = "Raw replicates"
    for ri, row in enumerate(dataframe_to_rows(raw_df, index=False, header=True), 1):
        ws1.append(row)
        for cell in ws1[ri]:
            if ri==1: cell.fill=HDR_FILL; cell.font=HDR_FONT; cell.alignment=Alignment(horizontal="center")
            else: cell.fill=BLUE
    for col in ws1.columns:
        ws1.column_dimensions[col[0].column_letter].width=18

    ws2 = wb.create_sheet("Precision summary")
    rows2 = [
        ["Sample ID", sample_id], ["Analyte", analyte],
        ["Grand mean", _f(pr_results["grand_mean"])],
        ["Days (D)", str(pr_results["D"])],
        ["Replicates/day (n)", str(pr_results["n"])], [],
        ["Within-run SD (Sr)", _f(pr_results["sr"])],
        ["Within-run CV (%)", _f(pr_results["cv_r"])],
        ["Between-day SD (Sb)", _f(pr_results["sb"])],
        ["Within-lab SD (Sl)", _f(pr_results["sl"])],
        ["Within-lab CV (%)", _f(pr_results["cv_l"])], [],
        ["Simple pooled SD (all results)", _f(pr_results.get("pooled_sd", 0))],
        ["Simple pooled CV (%)", _f(pr_results.get("pooled_cv", 0))],
        ["Pooled df", str(pr_results.get("pooled_df", ""))], [],
        ["Reference", "CLSI EP15-A3 (2014)"],
    ]
    for ri, row in enumerate(rows2, 1):
        ws2.append(row)
        if row:
            ws2[ri][0].font = Font(bold=True)
            for cell in ws2[ri]: cell.fill = GREEN
    ws2.column_dimensions["A"].width=30; ws2.column_dimensions["B"].width=22

    buf = io.BytesIO(); wb.save(buf); buf.seek(0); return buf.read()
