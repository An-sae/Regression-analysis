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
        return repr(v)                              # full precision, decimalpunkt
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
        nxt = sum(1 for c in rows[i + 1] if c != "")
        if text_share >= 0.5 and nxt >= max(2, m - 1):
            return i
    return 0


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
        grid = pd.read_excel(io.BytesIO(raw), sheet_name=sh, header=None, dtype=object)
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
        d = e and ("." if e == "p" else ",") or dec
        if not e and ("," in num or "." in num):
            ambiguous += 1
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
            "ambiguous": ambiguous if (ev["p"] == 0 and ev["c"] == 0) else 0}
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
}


def canonical_analyte(name: str) -> str:
    s = str(name).upper().strip()
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
