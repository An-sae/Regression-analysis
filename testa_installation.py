"""Gränssnittstest: Sysmex XN (brett) mot LIS-pivot (brett, NPU, SI), renderat i appen."""
import os, sys, io, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from streamlit.testing.v1 import AppTest
import skapa_instrumentdata as G

def app_with_files():
    import io, os, runpy, streamlit as st
    files = {"lf_fa": os.environ["UI_FILE_A"], "lf_fb": os.environ["UI_FILE_B"]}
    class _Up(io.BytesIO):
        def __init__(self, p):
            super().__init__(open(p, "rb").read()); self.name = os.path.basename(p)
    _orig = st.file_uploader
    st.file_uploader = lambda label, *a, key=None, **k: _Up(files[key]) if key in files else _orig(label, *a, key=key, **k)
    os.chdir(os.environ["UI_ROOT"])
    runpy.run_path(os.path.join(os.environ["UI_ROOT"], "app.py"), run_name="__main__")

def run(fa, fb, lang="sv"):
    os.environ.update(UI_ROOT=ROOT, UI_FILE_A=os.path.join(HERE, fa), UI_FILE_B=os.path.join(HERE, fb))
    at = AppTest.from_function(app_with_files, default_timeout=300)
    at.session_state["_lang"] = lang; at.run()
    at.radio(key="lf_mode").set_value("Two long-format files (match by ID)").run()
    return at

def texts(at):
    return [e.value for k in ("success", "info", "warning", "error", "caption") for e in getattr(at, k)]

fails = 0
def check(name, ok, detail=""):
    global fails; fails += not ok
    print(f"  {'OK ' if ok else 'FEL'} {name}" + (f"  — {str(detail)[:220]}" if not ok else ""))

G.sysmex_csv(0, "sysmex_xn_A.csv"); G.lis_pivot(1, "lis_pivot_hematologi.xlsx", G.LIS_HEME)
print("1) Sysmex XN mot LIS-pivot, endast förval")
at = run("sysmex_xn_A.csv", "lis_pivot_hematologi.xlsx"); T = texts(at)
check("inga undantag", not at.exception, [e.value for e in at.exception])
check("fil A identifieras som brett format med 6 analyser", any("Fil A" in x and "brett, 6 analyser" in x for x in T), T)
check("fil B: blad Rapport, brett, 6 analyser", any("Fil B" in x and "blad Rapport" in x and "brett, 6" in x for x in T), T)
aa = at.selectbox(key="lf_analyte_a").options
check("analyser i A är Sysmex-kolumnerna", "HGB(g/dL)" in aa and "PLT(10^3/uL)" in aa, aa)

at.selectbox(key="lf_analyte_a").set_value("HGB(g/dL)").run(); T = texts(at)
b = [s for s in at.selectbox if s.key and s.key.startswith("lf_analyte_b_")][0].value
check(f"HGB(g/dL) paras med {b}", b == "B-Hb (g/L)")
check("enhetsvarning ×10", any("ungefär 10 gånger" in x for x in T), T)
check("30 par används", any("30 par används" in x for x in T), T)
check("summarader redovisas", any("summarader" in x and "Medelvärde" in x for x in T), T)
at.number_input(key="lf_factor").set_value(0.1).run(); T = texts(at)
check("omräkningsfaktor 0,1 -> ingen enhetsvarning", not any("gånger" in x for x in T), T)

print("\n2) Översikt över alla analyser")
at.number_input(key="lf_factor").set_value(1.0).run()
exp = [e for e in at.expander if "Alla analyser" in (e.label or "")]
check("panelen 'Alla analyser i filerna' visas", bool(exp), [e.label for e in at.expander])
at.button(key="ov_run").click().run()
check("inga undantag efter körning", not at.exception, [e.value for e in at.exception])
tabs = [d.value for d in at.dataframe if d.value.shape[0] == 6 and "Anmärkning" in d.value.columns]
check("översiktstabell med 6 analyser", bool(tabs), [d.value.shape for d in at.dataframe])
if tabs:
    ov = tabs[0]; cols = list(ov.columns)
    check("kolumner översatta (Lutning 95 % KI, Anmärkning)", "Lutning 95 % KI" in cols and "Anmärkning" in cols, cols)
    note = ov[ov.iloc[:, 0].astype(str).str.startswith("HGB")]["Anmärkning"].iloc[0]
    check(f"HGB-raden flaggar enhetsskillnad: '{note}'", "enhetsskillnad ×10" in note)
check("Excel-nedladdning finns", any(d.key == "ov_dl" for d in at.get("download_button")),
      [getattr(d, "key", None) for d in at.get("download_button")])

print("\n3) Engelskt läge: inga svenska texter")
at = run("sysmex_xn_A.csv", "lis_pivot_hematologi.xlsx", "en"); T = texts(at)
import re
own = [x for x in T if any(c in re.sub(r"\([^)]*\)", "", x) for c in "åäöÅÄÖ")]   # (…) = citerat ur filen
check("inga svenska texter (utöver filernas egna namn)", not own, own)
check("engelsk formatbeskrivning", any("wide, 6 analyses" in x for x in T), T)

print(f"\n{'ALLA GODKÄNDA' if not fails else f'{fails} FEL'}")
sys.exit(1 if fails else 0)
