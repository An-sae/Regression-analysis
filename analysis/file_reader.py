"""
file_reader — robust inläsning av instrument- och LIS-exporter.

Grundprincip: ALLT läses som text. Ingen automatisk typtolkning från pandas,
eftersom den är orsaken till de allvarligaste felen:
  * prov-ID blir heltal i en fil och text i en annan (krasch vid matchning)
  * ledande nollor försvinner
  * '1,786' tolkas som 1.786 när filen i övrigt har decimalpunkt

Tal tolkas därefter per KOLUMN, utifrån bevis från samtliga värden i
kolumnen, inte per värde.

Verifierad med testa_filinlasning.py (28 isolerade fällor + tre
exportliknande filer). Se Verifieringsrapport_filinlasning.
"""
import csv
import difflib
import io
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ════════════════════════════════════════════════════════════════════════════
# 1. Läsa filen till en tabell av text
# ════════════════════════════════════════════════════════════════════════════
_SPACES = "\u00a0\u202f\u2009\u2007"          # hårda och smala mellanslag


def _decode(raw: bytes) -> Tuple[str, str]:
    """Pröva UTF-8 (med och utan BOM) och därefter Windows-1252."""
    for enc in ("utf-8-sig", "utf-8"):
        try:
            txt = raw.decode(enc)
            return txt, ("UTF-8 with BOM" if raw.startswith(b"\xef\xbb\xbf") else "UTF-8")
        except UnicodeDecodeError:
            pass
    return raw.decode("cp1252", errors="replace"), "Windows-1252"


def _clean_cell(v) -> str:
    """Excel-värde eller CSV-fält -> text, utan artefakter."""
    if v is None:
        return ""
    if isinstance(v, float):
        if np.isnan(v):
            return ""
        if v.is_integer() and abs(v) < 1e15:        # 2409150101.0 -> '2409150101'
            return str(int(v))
        r = repr(v)                                 # full precision, decimalpunkt
        # Exakt tre decimaler ('1.234') kan förväxlas med tusentalsavgränsare.
        # En avslutande nolla ändrar inte värdet men gör tolkningen entydig.
        if "." in r and "e" not in r.lower() and len(r.split(".")[1]) == 3:
            r += "0"
        return r
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if hasattr(v, "isoformat"):
        return v.isoformat(sep=" ") if hasattr(v, "hour") else v.isoformat()
    s = str(v).replace("\ufeff", "")
    for ch in _SPACES:
        s = s.replace(ch, " ")
    return s.strip()


def _looks_numeric(s: str) -> bool:
    return bool(re.fullmatch(r"[<>≤≥]?\s*[+-]?[\d\s.,']+", s)) and any(c.isdigit() for c in s)


def _find_header(rows: List[List[str]]) -> int:
    """
    Rubrikraden = första raden som (a) har lika många fält som tabellens
    vanligaste radlängd, (b) till minst hälften består av text som inte är tal,
    och (c) följs av en rad med samma längd. Metadata- och titelrader
    ovanför har färre fält och hoppas därmed över.
    """
    lens = [sum(1 for c in r if c != "") for r in rows]
    if not lens:
        return 0
    modal = Counter(l for l in lens if l >= 2).most_common(1)
    if not modal:
        return 0
    m = modal[0][0]
    for i, r in enumerate(rows[:-1]):
        filled = [c for c in r if c != ""]
        if len(filled) < max(2, m - 1):
            continue
        text_share = sum(not _looks_numeric(c) for c in filled) / len(filled)
        # nästa rad med full bredd får ligga upp till tre rader ned
        # (t.ex. en enhetsrad direkt under rubrikraden)
        nxt = max((sum(1 for c in rows[j] if c != "") for j in range(i + 1, min(i + 4, len(rows)))),
                  default=0)
        if text_share >= 0.5 and nxt >= max(2, m - 1):
            return i
    return 0


def _is_unit_row(header: List[str], row: List[str]) -> bool:
    """Raden under rubriken innehåller enheter: första cellen tom och minst
    hälften av de ifyllda cellerna är text som inte är tal."""
    filled = [c for c in row if c != ""]
    return (bool(filled) and row[0] == "" and len(filled) < len([h for h in header if h])
            and sum(not _looks_numeric(c) for c in filled) / len(filled) >= 0.5)


def _pick_delimiter(text: str) -> str:
    """Välj den avgränsare som ger flest rader med samma, största fältantal."""
    lines = [l for l in text.splitlines() if l.strip()][:400]
    best, best_score = ";", -1
    for d in (";", "\t", ",", "|"):
        counts = Counter(len(r) for r in csv.reader(lines, delimiter=d))
        n_fields, n_rows = max(counts.items(), key=lambda kv: (kv[1] * (kv[0] > 1), kv[0]))
        score = n_rows * (n_fields > 1) * min(n_fields, 20)
        if score > best_score:
            best, best_score = d, score
    return best


def list_sheets(raw: bytes, fname: str) -> List[str]:
    if not fname.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return []
    try:
        return list(pd.ExcelFile(io.BytesIO(raw)).sheet_names)
    except Exception:
        return []


def best_sheet(raw: bytes, fname: str) -> Optional[str]:
    """Excel: välj bladet med flest rader som har minst två ifyllda celler.
    Ett inledande informations- eller titelblad väljs därmed inte."""
    sheets = list_sheets(raw, fname)
    if len(sheets) < 2:
        return sheets[0] if sheets else None
    best, best_n = sheets[0], -1
    for sh in sheets:
        try:
            g = pd.read_excel(io.BytesIO(raw), sheet_name=sh, header=None, dtype=object,
                              keep_default_na=False, na_filter=False)
        except Exception:
            continue
        n = int(sum(sum(1 for v in r if str(v).strip() != "") >= 2 for r in g.itertuples(index=False)))
        if n > best_n:
            best, best_n = sh, n
    return best


def read_table(raw: bytes, fname: str, sheet: Optional[str] = None,
               header_row="auto") -> Tuple[pd.DataFrame, Dict]:
    """
    Läs CSV/TXT/Excel till en DataFrame där ALLA celler är text.

    header_row: "auto" (hitta rubrikraden), None (ingen rubrik) eller ett
                0-baserat radnummer.
    Returnerar (df, info) där info beskriver hur filen tolkades.
    """
    info = {"file": fname}
    low = fname.lower()
    if low.endswith((".xlsx", ".xlsm", ".xls")):
        sheets = list_sheets(raw, fname)
        sh = sheet if sheet in sheets else (sheets[0] if sheets else 0)
        grid = pd.read_excel(io.BytesIO(raw), sheet_name=sh, header=None, dtype=object,
                             keep_default_na=False, na_filter=False)   # 'NA' = natrium
        rows = [[_clean_cell(v) for v in r] for r in grid.itertuples(index=False)]
        info.update(kind="Excel", sheet=sh, sheets=sheets, encoding="—", delimiter="—")
    else:
        text, enc = _decode(raw)
        delim = _pick_delimiter(text)
        rows = [[_clean_cell(c) for c in r]
                for r in csv.reader(io.StringIO(text), delimiter=delim)]
        info.update(kind="Text", encoding=enc,
                    delimiter={";": "semicolon", ",": "comma", "\t": "tab", "|": "|"}[delim])

    rows = [r for r in rows if any(c != "" for c in r)]            # tomma rader bort
    if not rows:
        raise ValueError("The file contains no data.")
    if header_row == "auto":
        h = _find_header(rows)
    elif header_row is None:
        h = None
    else:
        h = int(header_row)

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    if h is None:
        cols = [f"Column {i + 1}" for i in range(width)]
        body = rows
    else:
        cols, seen = [], Counter()
        for i, c in enumerate(rows[h]):
            name = c.strip().strip('"').strip() or f"Column {i + 1}"
            seen[name] += 1
            cols.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
        body = rows[h + 1:]
        if body and _is_unit_row(rows[h], body[0]):           # 'B-Hb' / 'g/L'
            cols = [f"{c} ({u})" if u else c for c, u in zip(cols, body[0])]
            body = body[1:]
    df = pd.DataFrame(body, columns=cols, dtype=object)
    # helt tomma kolumner utan namn tas bort
    drop = [c for c in df.columns if c.startswith("Column ") and h is not None
            and (df[c] == "").all()]
    df = df.drop(columns=drop)
    info.update(header_row=None if h is None else h + 1, n_rows=len(df),
                skipped_above=0 if h is None else h)
    return df, info


# ════════════════════════════════════════════════════════════════════════════
# 2. Prov-ID
# ════════════════════════════════════════════════════════════════════════════
_SCI = re.compile(r"^[+-]?\d+([.,]\d+)?E[+-]?\d+$", re.I)


def normalize_ids(series: pd.Series, ignore_leading_zeros: bool = True
                  ) -> Tuple[pd.Series, pd.Series]:
    """
    Returnerar (nyckel, vetenskaplig_notation_mask).
    Nyckeln: trimmad, versaler, '123.0' -> '123', valfritt utan ledande nollor.
    ID i vetenskaplig notation (2,40915E+09) går inte att återskapa och
    flaggas i stället för att matchas.
    """
    s = series.fillna("").astype(str).map(_clean_cell).str.upper()
    s = s.str.replace(r"\s+", " ", regex=True)
    sci = s.map(lambda v: bool(_SCI.match(v)))
    s = s.str.replace(r"^(\d+)\.0+$", r"\1", regex=True)
    if ignore_leading_zeros:
        s = s.map(lambda v: (v.lstrip("0") or "0") if v.isdigit() else v)
    s = s.where(~sci, "")
    return s, sci


# ════════════════════════════════════════════════════════════════════════════
# 3. Tal — tolkas per kolumn
# ════════════════════════════════════════════════════════════════════════════
_NUM = re.compile(r"^(?P<q><=|>=|[<>≤≥])?\s*(?P<num>[+-]?\d[\d\s'.,]*)(?P<rest>.*)$")
_TEXT_NA = {"", "NA", "N/A", "NAN", "-", "--", "---", "NONE", "NULL", "."}


_SCI_NUM = re.compile(r"^(?P<q><=|>=|[<>≤≥])?\s*(?P<num>[+-]?\d+(?:[.,]\d+)?[eE][+-]?\d+)(?P<rest>.*)$")


def _split(v: str):
    """-> (kvalificerare, talsträng, resttext) eller (None, None, text)."""
    s = _clean_cell(v)
    m = _SCI_NUM.match(s)                           # 1e-05, 1,5E-3 (Excel, instrument)
    if m:
        return m.group("q"), m.group("num").replace(",", "."), m.group("rest").strip()
    m = _NUM.match(s)
    if not m:
        return None, None, s
    num = m.group("num").rstrip(" .,'")
    rest = m.group("rest") + m.group("num")[len(num):]
    num = re.sub(r"[\s']", "", num)
    return m.group("q"), num, rest.strip()


def _evidence(num: str) -> str:
    """Vad säger en enskild talsträng om decimaltecknet? 'p', 'c' eller ''."""
    if "e" in num.lower():
        return ""                                   # redan normaliserad i _split
    if "." in num and "," in num:
        return "p" if num.rfind(".") > num.rfind(",") else "c"
    for sep, tag in ((".", "p"), (",", "c")):
        if sep in num:
            parts = num.split(sep)
            if len(parts) > 2:                        # 1,234,567 -> sep är tusental
                return "c" if sep == "." else "p"
            if len(parts[1]) != 3:                    # 12,3 / 0,60 / 12.50
                return tag
            if parts[0].lstrip("+-") in ("0", ""):    # 0,411: aldrig tusental
                return tag
    return ""                                          # 1,234 / 1.234 / 123 = tvetydigt


def parse_numeric(series: pd.Series, default_decimal: str = ",") -> Tuple[pd.DataFrame, Dict]:
    """
    Tolka en resultatkolumn.

    Returnerar en DataFrame med kolumnerna
        value      float (NaN om ej användbart)
        qualifier  '<', '>', ... eller ''
        flag       text efter talet, t.ex. 'H' eller 'mg/L'
        reason     '' om användbart, annars 'empty', 'text', 'below', 'above'
    samt info om vilket decimaltecken som valdes och hur säkert valet var.
    """
    parts = [_split(v) for v in series.tolist()]
    ev = Counter(_evidence(p[1]) for p in parts if p[1])
    dec = "." if ev["p"] > ev["c"] else "," if ev["c"] > ev["p"] else default_decimal
    conflict = min(ev["p"], ev["c"])
    ambiguous = 0
    out = []
    for raw, (q, num, rest) in zip(series.tolist(), parts):
        if num is None:
            txt = _clean_cell(raw)
            out.append((np.nan, "", txt, "empty" if txt.upper() in _TEXT_NA else "text"))
            continue
        e = _evidence(num)
        if e:
            d = "." if e == "p" else ","
        elif "," in num or "." in num:
            # Tvetydigt värde: avgörs av hur SAMMA tecken används i kolumnen.
            sep = "," if "," in num else "."
            own = ev["c"] if sep == "," else ev["p"]      # sep som decimal på annat håll
            other = ev["p"] if sep == "," else ev["c"]    # andra tecknet som decimal
            if own:
                d = sep                                   # t.ex. '3,460' bland '155,0'
            elif other:
                d = "." if sep == "," else ","            # '1,786' bland '12.50' -> tusental
            else:
                d = dec; ambiguous += 1
        else:
            d = dec
        th = "," if d == "." else "."
        try:
            val = (float(num) if "e" in num.lower()
                   else float(num.replace(th, "").replace(d, ".")))
        except ValueError:
            out.append((np.nan, q or "", rest, "text")); continue
        if q in ("<", "<=", "≤"):
            out.append((np.nan, q, rest, "below"))
        elif q in (">", ">=", "≥"):
            out.append((np.nan, q, rest, "above"))
        else:
            out.append((val, "", rest, ""))
    df = pd.DataFrame(out, columns=["value", "qualifier", "flag", "reason"],
                      index=series.index)
    info = {"decimal": dec, "evidence_point": ev["p"], "evidence_comma": ev["c"],
            "conflict": conflict,
            "ambiguous": ambiguous}
    return df, info


# ════════════════════════════════════════════════════════════════════════════
# 4. Kolumn- och analysförslag
# ════════════════════════════════════════════════════════════════════════════
_COL_HINTS = {
    "id":  ["sample id", "sampleid", "sid", "provnummer", "provnr", "prov-id", "prov id",
            "prov", "sample no", "sample", "specimen id", "specimen", "barcode", "id"],
    "an":  ["test", "assay name", "assay", "analys", "analysis", "test code", "testkod",
            "analyte", "parameter", "method"],
    "res": ["result", "resultat", "value", "värde", "result value", "conc", "concentration"],
}


def guess_column(columns: List[str], kind: str) -> Optional[str]:
    low = {c: c.lower().strip() for c in columns}
    for hint in _COL_HINTS[kind]:
        for c, l in low.items():
            if l == hint:
                return c
    for hint in _COL_HINTS[kind]:
        for c, l in low.items():
            if hint in l and not (kind == "id" and "date" in l):
                return c
    return None


_ALIAS = {
    "CREJ": "KREATININ", "CREA": "KREATININ", "CREAT": "KREATININ", "CREATININE": "KREATININ",
    "KREA": "KREATININ", "CRE": "KREATININ",
    "FERR": "FERRITIN", "FER": "FERRITIN",
    "TNTHS": "TNT", "HSTNT": "TNT", "TROPONINT": "TNT", "TROPT": "TNT",
    "TNIHS": "TNI", "HSTNI": "TNI", "TROPONINI": "TNI", "HSTROPI": "TNI",
    "GLUC": "GLUKOS", "GLU": "GLUKOS", "GLUCOSE": "GLUKOS",
    "NA": "NATRIUM", "SODIUM": "NATRIUM", "K": "KALIUM", "POTASSIUM": "KALIUM",
    "ALBU": "ALBUMIN", "ALB": "ALBUMIN", "TSH": "TSH", "FT4": "FT4", "FT3": "FT3",
    # hematologi: instrumentnamn <-> svenska NPU-kortnamn
    "WBC": "LPK", "LEUKOCYTER": "LPK", "LEUKOCYTES": "LPK", "LPK": "LPK",
    "RBC": "EPK", "ERYTROCYTER": "EPK", "ERYTHROCYTES": "EPK", "EPK": "EPK",
    "HGB": "HB", "HB": "HB", "HEMOGLOBIN": "HB", "HAEMOGLOBIN": "HB",
    "HCT": "EVF", "EVF": "EVF", "HEMATOKRIT": "EVF", "HAEMATOCRIT": "EVF",
    "PLT": "TPK", "TPK": "TPK", "TROMBOCYTER": "TPK", "PLATELETS": "TPK",
    "NATRIUM": "NATRIUM", "KALIUM": "KALIUM",
}


def strip_unit(name: str) -> str:
    """'HGB(g/dL)' -> 'HGB', 'B-Hb (g/L)' -> 'B-Hb', 'WBC [10^9/L]' -> 'WBC'."""
    return re.sub(r"\s*[\(\[][^\)\]]*[\)\]]\s*$", "", str(name)).strip()


def canonical_analyte(name: str) -> str:
    s = strip_unit(name).upper().strip()
    s = re.sub(r"^(P|S|B|U|FP|PT|CSF|SE|PL|SR|HB)\s*[-_ ]\s*", "", s)   # NPU-prefix 'P-'
    s = re.sub(r"[^A-Z0-9ÅÄÖ]", "", s)
    s = re.sub(r"(?<=[A-ZÅÄÖ])\d+$", "", s)                          # CRP4 -> CRP
    return _ALIAS.get(s, s)


def suggest_analyte(name_a: str, candidates_b: List[str]) -> Tuple[Optional[str], str]:
    """Föreslå motsvarande analys i fil B. Returnerar (namn, grund)."""
    if name_a in candidates_b:
        return name_a, "exact"
    ca = canonical_analyte(name_a)
    for b in candidates_b:
        if canonical_analyte(b) == ca:
            return b, "normalised"
    best = difflib.get_close_matches(ca, [canonical_analyte(b) for b in candidates_b],
                                     n=1, cutoff=0.8)
    if best:
        for b in candidates_b:
            if canonical_analyte(b) == best[0]:
                return b, "similar"
    return None, ""



# ════════════════════════════════════════════════════════════════════════════
# 5. Långt eller brett format
# ════════════════════════════════════════════════════════════════════════════
# Kolumner som beskriver provet eller körningen, inte ett analysresultat.
_META = re.compile(
    r"(date|datum|time|tid\b|klockslag|rack|pos(ition)?\b|seq|sekvens|analy[sz]er|instrument|"
    r"nickname|order|error|mode|mark|flag|flagga|abnormal|suspect|/m$|info|comment|"
    r"kommentar|remark|patient|age|ålder|sex|kön|operator|user|status|lot|unit|enhet)",
    re.I)


def detect_layout(df: pd.DataFrame) -> Dict:
    """
    Avgör om tabellen är lång (en rad per resultat: ID, analys, resultat) eller
    bred (en rad per prov, en kolumn per analys, som Sysmex XN och LIS-pivot).

    Returnerar {"layout", "id_col", "an_col", "res_col", "value_cols"}.
    """
    cols = list(df.columns)
    id_col = guess_column(cols, "id")
    an_col, res_col = guess_column(cols, "an"), guess_column(cols, "res")

    def num_share(c):
        v = df[c].astype(str).str.strip()
        v = v[v != ""]
        if len(v) < 3:
            return 0.0
        p, _ = parse_numeric(v.reset_index(drop=True))
        ok = p["value"].notna() | p["reason"].isin(["below", "above"])
        return float(ok.mean())

    value_cols = [c for c in cols
                  if c != id_col and not _META.search(str(c)) and num_share(c) >= 0.6]
    long_ok = (an_col is not None and res_col is not None and an_col != res_col
               and num_share(res_col) >= 0.5)
    layout = "long" if long_ok or len(value_cols) < 2 else "wide"
    return {"layout": layout, "id_col": id_col, "an_col": an_col if layout == "long" else None,
            "res_col": res_col if layout == "long" else None,
            "value_cols": value_cols if layout == "wide" else [],
            "numeric_cols": value_cols}            # alltid, för manuellt val av brett format


WIDE_AN, WIDE_RES = "Analysis", "Result"


def to_long(df: pd.DataFrame, id_col: str, value_cols: List[str]) -> pd.DataFrame:
    """Brett -> långt: en rad per (prov, analys). Kolumnrubriken blir analysnamnet,
    inklusive eventuell enhet, t.ex. 'HGB(g/dL)'."""
    if not value_cols:
        raise ValueError("No result columns selected.")
    out = df[[id_col] + list(value_cols)].melt(id_vars=[id_col], var_name=WIDE_AN,
                                                value_name=WIDE_RES)
    out[WIDE_AN] = out[WIDE_AN].astype(str).str.strip()
    out.attrs["read_info"] = dict(df.attrs.get("read_info", {}), layout="wide",
                                  wide_columns=len(value_cols))
    return out.reset_index(drop=True)
