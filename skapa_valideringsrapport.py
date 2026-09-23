"""
Kontrollera språktäckningen genom att RENDERA appen.

Kör:  python kontrollera_sprak.py

Appen körs headless i svenskt läge via Streamlits AppTest, i flera
scenarier (alla analystyper, med och utan data). Alla texter som en
användare faktiskt ser samlas in: rubriker, etiketter, alternativ i
listor och radioknappar, flikar, bildtexter och meddelanden.

En text flaggas som oöversatt om den är en engelsk nyckel i i18n.SV som
har en svensk översättning, eller om den innehåller vanliga engelska ord.
Fackuttryck (Passing–Bablok, PPA, VME ...) räknas inte som fel.
"""
import re
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

from streamlit.testing.v1 import AppTest       # noqa: E402
from i18n import SV                            # noqa: E402

PASTE = "\n".join(f"{10+i*2}\t{11+i*2}" for i in range(20))
PREC = ("Dag 1\tDag 2\tDag 3\n2,01\t2,02\t1,99\n2,00\t2,03\t2,01\n"
        "1,98\t2,00\t2,02")

ENGLISH_WORDS = {
    "the", "and", "of", "to", "for", "with", "file", "files", "upload",
    "paste", "single", "two", "match", "by", "robust", "outliers",
    "choose", "load", "name", "your", "options", "results",
    "click", "select", "column", "columns", "rows", "reference", "candidate",
    "method", "methods", "analysis", "table", "day", "days", "value",
    "values", "enter", "show", "set", "leave", "blank", "automatic", "within",
    "between", "total", "plot", "download", "resolution", "title",
    "agreement", "error", "errors", "zone", "diameter", "matrix", "precision",
    "imprecision", "sample", "replicate", "replicates", "first", "no", "yes",
    "excluded", "points", "rows", "results", "matched", "used", "file", "header",
}
ALLOWED = {
    "passing–bablok", "deming", "bland–altman", "ppa", "npa", "opa", "vme",
    "me", "clsi", "eucast", "ep15-a3", "ep12-a2", "cv", "sd", "lr+", "lr−",
    "csv", "excel", "xlsx", "xls", "png", "svg", "html", "dpi", "id",
    "x", "y", "n", "min", "max", "λ", "kappa", "mcnemar", "mb",
}


CITATION = ("J Clin Chem", "Lancet", "Stat Med", "Clin Biochem Rev")
EN_OK_WITH_SWEDISH = {"Svenska", "Språk / Language"}


def looks_swedish(s):
    return (any(c in s for c in "åäöÅÄÖ") and s not in EN_OK_WITH_SWEDISH
            and not any(c in s for c in CITATION))


def looks_english(s):
    if s.lstrip().startswith("<"):        # raw HTML: its labels are checked separately
        return False
    if any(c in s for c in CITATION):
        return False
    if s in SV and SV[s] != s:
        return True
    if any(c in s for c in "åäöÅÄÖ"):
        return False
    words = [w for w in re.findall(r"[A-Za-z+\-–]+", s.lower()) if w not in ALLOWED]
    return any(w in ENGLISH_WORDS for w in words)


def collect(at):
    seen = set()

    def add(x):
        if isinstance(x, str) and x.strip():
            seen.add(x.strip())

    for kind in ("title", "header", "subheader", "markdown", "caption",
                 "info", "warning", "error", "success"):
        for el in getattr(at, kind, []):
            add(getattr(el, "value", None))
    for kind in ("radio", "selectbox", "multiselect"):
        for el in getattr(at, kind, []):
            add(el.label)
            for o in getattr(el, "options", []) or []:
                add(o)
    # table headers and text cells (row labels such as "Slope", "Antal:")
    for kind in ("dataframe", "table"):
        for el in getattr(at, kind, []):
            try:
                df = el.value
            except Exception:
                continue
            for c in list(df.columns) + [df.index.name]:
                add(str(c) if c is not None else None)
            for col in df.columns:
                for v in df[col].tolist():
                    if isinstance(v, str) and not re.fullmatch(r"[\d\s,.\-–%/()<>≤≥]+", v):
                        add(v)
    for kind in ("text_input", "text_area", "number_input", "slider",
                 "toggle", "checkbox", "button", "color_picker",
                 "expander", "tabs", "metric"):
        for el in getattr(at, kind, []):
            add(getattr(el, "label", None))
    return seen


def run(analysis, setup=None, lang="sv"):
    at = AppTest.from_file("app.py", default_timeout=120)
    at.session_state["_lang"] = lang
    at.run()
    at.selectbox(key="analysis_type").set_value(analysis).run()
    if setup:
        setup(at)
    return collect(at)


def paste(at):
    at.radio(key="imode").set_value("📋 Paste data").run()
    at.text_area(key="pa").input(PASTE).run()


def paste_and_analyze(at):
    paste(at)
    for b in at.button:
        if "Analy" in (b.label or ""):
            b.click().run()
            break


def fourfold(at):
    paste(at)
    at.text_input(key="ff_cr").input("20").run()
    at.text_input(key="ff_cc").input("20").run()


def precision(at):
    at.text_area(key="pr_paste").input(PREC).run()


SCENARIOS = [
    ("Passing–Bablok", None),
    ("Passing–Bablok", paste_and_analyze),
    ("Deming", paste_and_analyze),
    ("Confusion Matrix", paste),
    ("Precision Evaluation (EP15-A3)", precision),
    ("Fourfold table (qualitative)", fourfold),
]

if __name__ == "__main__":
    problems = {}
    for lang, test, label in (("sv", looks_english, "engelska i svenskt läge"),
                              ("en", looks_swedish, "svenska i engelskt läge")):
        total = 0
        print(f"--- {label} ---")
        for analysis, setup in SCENARIOS:
            name = f"{analysis}{' + data' if setup else ''}"
            try:
                texts = run(analysis, setup, lang)
            except Exception as e:
                print(f"  FEL i '{name}': {type(e).__name__}: {e}")
                problems.setdefault((label, "(renderingsfel)"), set()).add(name)
                continue
            total += len(texts)
            for x in texts:
                if test(x):
                    problems.setdefault((label, x), set()).add(name)
            print(f"  renderat: {name:44} {len(texts):4} texter")
        print(f"  totalt {total} synliga texter\n")
    print("=" * 70)
    print(f"PROBLEM: {len(problems)}")
    print("=" * 70)
    for (label, x) in sorted(problems):
        print(f'  [{label}] "{x[:60]}"')
    print()
    print("FULLSTÄNDIG TÄCKNING I BÅDA SPRÅKEN" if not problems else "ÅTGÄRD BEHÖVS")
    sys.exit(0 if not problems else 1)
