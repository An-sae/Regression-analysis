"""
Gränssnittstest av tvåfilsflödet med riktiga exportliknande filer.

Streamlits testverktyg kan inte simulera uppladdning. Därför ersätts
st.file_uploader i testet med en stubbe som returnerar filerna, och den
OFÖRÄNDRADE app.py körs. Testet kontrollerar vad användaren faktiskt ser.
"""
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.abspath(_os.path.join(_HERE, "..", ".."))
import sys, warnings
warnings.filterwarnings("ignore")
from streamlit.testing.v1 import AppTest


def app_with_files():
    import io, os, runpy, streamlit as st
    files = {"lf_fa": os.environ["UI_FILE_A"], "lf_fb": os.environ["UI_FILE_B"]}

    class _Up(io.BytesIO):
        def __init__(self, path):
            super().__init__(open(path, "rb").read()); self.name = os.path.basename(path)

    _orig = st.file_uploader
    def _fake(label, *a, key=None, **k):
        return _Up(files[key]) if key in files else _orig(label, *a, key=key, **k)
    st.file_uploader = _fake
    os.chdir(os.environ["UI_ROOT"])
    runpy.run_path(os.path.join(os.environ["UI_ROOT"], "app.py"), run_name="__main__")


def run(file_a, file_b, lang="sv", setup=None):
    import os
    os.environ["UI_ROOT"] = _ROOT; os.environ["UI_FILE_A"] = file_a; os.environ["UI_FILE_B"] = file_b
    at = AppTest.from_function(app_with_files, default_timeout=180)
    at.session_state["_lang"] = lang
    at.run()
    at.radio(key="lf_mode").set_value("Two long-format files (match by ID)").run()
    if setup:
        setup(at)
    return at


def texts(at):
    out = []
    for kind in ("success", "info", "warning", "error", "caption"):
        out += [f"[{kind}] {e.value}" for e in getattr(at, kind)]
    return out


D = _HERE + "/"
fails = 0
def check(name, cond, detail=""):
    global fails
    fails += not cond
    print(f"  {'OK ' if cond else 'FEL'} {name}{('  — ' + detail) if detail and not cond else ''}")

if __name__ == "__main__":
    print("1) Roche-lik mot Abbott-lik, svenska, endast förvalda val")
    at = run(D + "roche_cobas_lik.csv", D + "abbott_alinity_lik.csv")
    T = texts(at)
    check("inga undantag", len(at.exception) == 0, str([e.value for e in at.exception])[:200])
    check("fil A: Windows-1252, rubrik rad 4",
          any("Fil A" in x and "Windows-1252" in x and "rad 4" in x for x in T))
    check("fil B: UTF-8 med BOM, komma", any("Fil B" in x and "UTF-8 med BOM" in x and "komma" in x for x in T))
    check("kolumner förvalda (Sample ID / SID)",
          at.selectbox(key="lf_ida").value == "Sample ID" and at.selectbox(key="lf_idb").value == "SID")
    sa = at.selectbox(key="lf_analyte_a").value
    sb = [s for s in at.selectbox if s.key and s.key.startswith("lf_analyte_b_")][0].value
    check(f"analyskoppling förvald: {sa} ↔ {sb}", (sa, sb) == ("CREJ2", "Creat2"))
    check("förslag visas som 'kontrollera'", any("Föreslagen koppling" in x for x in T))
    check("omkörningar varnas", any("Upprepade resultat" in x for x in T))
    check("antal visas korrekt: 40 matchade, 40 används",
          any("40 prov matchade" in x and "40 par används" in x for x in T), str(T)[:300])
    check("strategi 'första giltiga' förvald", at.radio(key="lf_dup").value == "first_valid")

    print("\n2) Byt analys i A till FERR4 -> B följer med, uteslutning redovisas")
    at.selectbox(key="lf_analyte_a").set_value("FERR4").run()
    T = texts(at)
    sb = [s for s in at.selectbox if s.key and s.key.startswith("lf_analyte_b_")][0].value
    check(f"B föreslås: {sb}", sb == "Ferritin")
    check("39 par används, 1 uteslutet med orsak",
          any("39 par används" in x for x in T) and any("textresultat" in x for x in T), str(T)[:300])

    print("\n3) Samma i engelskt läge: inga svenska ord")
    at = run(D + "roche_cobas_lik.csv", D + "abbott_alinity_lik.csv", lang="en")
    T = texts(at)
    sv = [x for x in T if any(c in x for c in "åäöÅÄÖ")]
    check("inga svenska texter", not sv, str(sv)[:200])
    check("engelska antal", any("40 samples matched" in x for x in T))

    print("\n4) Analyskolumn N/A på flera-analysfil -> tydligt stopp")
    def na(at):
        at.selectbox(key="lf_ana").set_value("N/A").run()
    at = run(D + "roche_cobas_lik.csv", D + "abbott_alinity_lik.csv", setup=na)
    T = texts(at)
    check("tydligt felmeddelande, inga par", any("Flera resultat per prov-ID" in x for x in T), str(T)[:200])
    check("inga undantag", len(at.exception) == 0)

    print("\n5) Roche-lik mot LIS-Excel")
    at = run(D + "roche_cobas_lik.csv", D + "lis_export_lik.xlsx")
    T = texts(at)
    check("LIS: blad och rubrikrad 2", any("Fil B" in x and "blad Resultat" in x and "rad 2" in x for x in T))
    sb = [s for s in at.selectbox if s.key and s.key.startswith("lf_analyte_b_")][0].value
    check(f"koppling CREJ2 ↔ {sb}", sb == "P-Kreatinin")
    check("40 par", any("40 par används" in x for x in T), str(T)[:200])

    print("\n6) Analys körs hela vägen: Passing–Bablok på matchade par")
    at = run(D + "roche_cobas_lik.csv", D + "abbott_alinity_lik.csv")
    for b in at.button:
        if "Analy" in (b.label or ""):
            b.click().run(); break
    check("inga undantag efter analys", len(at.exception) == 0, str([e.value for e in at.exception])[:200])
    check("resultattabell visas", len(at.dataframe) > 0)

    print(f"\n{'ALLA GODKÄNDA' if fails == 0 else f'{fails} FEL'}")
    sys.exit(1 if fails else 0)
