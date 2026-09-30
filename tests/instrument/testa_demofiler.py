"""Demofilerna i data/demo (Sysmex XN-1000 mot XN-2000) i appens gränssnitt, svenska och engelska.

Förväntade antal par och omkörning enligt demofilernas facit. [v2.2.1]"""
import os, sys, re, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
from streamlit.testing.v1 import AppTest


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


def run(lang):
    os.environ.update(UI_ROOT=ROOT, UI_FILE_A=os.path.join(ROOT, "data/demo/Sysmex_XN-1000_radata.xlsx"),
                      UI_FILE_B=os.path.join(ROOT, "data/demo/Sysmex_XN-2000_radata.xlsx"))
    at = AppTest.from_function(app_with_files, default_timeout=300)
    at.session_state["_lang"] = lang; at.run()
    at.radio(key="lf_mode").set_value("Two long-format files (match by ID)").run()
    return at


def texts(at):
    return [e.value for k in ("success", "info", "warning", "error", "caption") for e in getattr(at, k)]


fails = 0
def check(name, ok, detail=""):
    global fails; fails += not ok
    print(f"  {'OK ' if ok else 'FEL'} {name}" + ("" if ok else f"  — {str(detail)[:400]}"))


print("1) Svenska")
at = run("sv"); T = texts(at)
check("inga undantag", not at.exception, [e.value for e in at.exception])
check("ingen installationsvarning", not any("skiljer sig från validerad" in x for x in T),
      [x for x in T if "validerad" in x])
check("fil A: brett, 11 analyser", any("Fil A" in x and "brett, 11 analyser" in x for x in T), T)
check("fil B: brett, 11 analyser", any("Fil B" in x and "brett, 11 analyser" in x for x in T), T)
opts = at.selectbox(key="lf_analyte_a").options
check("11 analyser att välja", len(opts) == 11, opts)
EXP = {"PLT(10^9/L)": 77, "HGB(g/L)": 78, "WBC(10^9/L)": 77}
for an, n in EXP.items():
    at.selectbox(key="lf_analyte_a").set_value(an).run(); T = texts(at)
    b = [s for s in at.selectbox if s.key and s.key.startswith("lf_analyte_b_")][0].value
    check(f"{an}: paras med {b}, {n} par används", b == an and any(f"{n} par används" in x for x in T),
          [x for x in T if "par" in x])
    if an == "PLT(10^9/L)":
        check("omkörning redovisas som 1 prov i fil B, med prov-ID",
              any("fil A 0 prov, fil B 1 prov" in x for x in T) and any("9260121" in x for x in T),
              [x for x in T if "Upprepade" in x or "omkörn" in x.lower()])
        print("     meddelanden:", *[x[:160] for x in T if any(w in x for w in ("par", "bara", "omkör", "dubbl", "++++", "QC"))], sep="\n       ")

at.button(key="ov_run").click().run()
check("översikt utan undantag", not at.exception, [e.value for e in at.exception])
tabs = [d.value for d in at.dataframe if d.value.shape[0] == 11 and "Anmärkning" in d.value.columns]
check("översiktstabell med 11 analyser", bool(tabs), [d.value.shape for d in at.dataframe])
if tabs:
    ov = tabs[0]
    n = dict(zip(ov.iloc[:, 0], ov["Par som används"]))
    check("par per analys enligt facit", all(n[k] == (77 if k.split("(")[0] in ("WBC", "PLT", "NEUT#", "LYMPH#") else 78) for k in n), n)
check("Excel-nedladdning finns", any(d.key == "ov_dl" for d in at.get("download_button")))

print("\n2) Engelska")
at = run("en"); T = texts(at)
check("inga undantag", not at.exception, [e.value for e in at.exception])
check("engelsk formatbeskrivning 'wide, 11 analyses'", sum("wide, 11 analyses" in x for x in T) >= 2, T)
own = [x for x in T if any(c in re.sub(r"\([^)]*\)", "", x) for c in "åäöÅÄÖ")]
check("inga svenska texter", not own, own)

print(f"\n{'ALLA GODKÄNDA' if not fails else f'{fails} FEL'}")
sys.exit(1 if fails else 0)
