"""Installationskontroll: fem sätt en uppladdning kan gå fel, renderat i appen."""
import os, shutil, sys, warnings, tempfile
warnings.filterwarnings("ignore")
from streamlit.testing.v1 import AppTest
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", ".."))
_VERSION = open(os.path.join(SRC, "version.py"), encoding="utf-8").read().split('VERSION = "')[1].split('"')[0]
def scenario(name, mutate):
    d = tempfile.mkdtemp(); root = os.path.join(d, "app")
    shutil.copytree(SRC, root, ignore=shutil.ignore_patterns("tests", "__pycache__", "*.docx", ".pytest_cache"))
    mutate(root)
    cwd = os.getcwd(); os.chdir(root); sys.path.insert(0, root)
    for m in [m for m in list(sys.modules) if m.split(".")[0] in ("analysis","plots","version","i18n")]:
        del sys.modules[m]
    at = AppTest.from_file(os.path.join(root, "app.py"), default_timeout=120); at.run()
    os.chdir(cwd); sys.path.remove(root)
    msgs = [e.value for e in at.error] + [w.value for w in at.warning]
    infos = [i.value for i in at.info]
    scenario.infos = infos
    stat = [x for x in at.expander if "Systemstatus" in (x.label or "")]
    scenario.status = [c.value for c in stat[0].caption] if stat else None
    exc = [str(e.value)[:80] for e in at.exception]
    return msgs, exc, len(at.selectbox) > 0
fails = 0
def check(name, ok, detail=""):
    global fails; fails += not ok
    print(f"  {'OK ' if ok else 'FEL'} {name}" + (f"  — {detail}" if not ok else ""))

print("1) Komplett installation")
m, e, ui = scenario("komplett", lambda r: None)
check("appen startar, inga fel, ingen varning", ui and not e and not m, (m, e))
check("systemstatus visar ✓ validerad version", scenario.status and any("✓" in x and _VERSION in x for x in scenario.status), scenario.status)

print("2) file_reader.py uppladdad i huvudmappen i stället för analysis/")
m, e, ui = scenario("fel mapp", lambda r: shutil.move(f"{r}/analysis/file_reader.py", f"{r}/file_reader.py"))
check("tydligt stopp som namnger analysis/file_reader.py",
      any("analysis/file_reader.py" in x and "ofullständig" in x for x in m) and not e, (m[:1], e))

print("3) Delvis uppdatering: gammal data_loader.py (v2.0.0) kvar i GitHub")
m, e, ui = scenario("gammal fil", lambda r: shutil.copy(os.path.join(HERE, "data_loader_v200.py"), f"{r}/analysis/data_loader.py"))
check("tydligt besked som namnger analysis/data_loader.py, ingen krasch",
      any("analysis/data_loader.py" in x and "passar inte ihop" in x for x in m) and not e, (m[:1], e))

print("4) .streamlit/config.toml saknas (dold mapp ej uppladdad)")
m, e, ui = scenario("config saknas", lambda r: os.remove(f"{r}/.streamlit/config.toml"))
m_info = m
check("ingen banner för slutanvändaren", ui and not e and not any("config.toml" in x for x in m + scenario.infos), (m, scenario.infos))
check("uppgiften finns i den hopfällda Systemstatus-panelen", scenario.status and any("config.toml" in x and "påverkas inte" in x for x in scenario.status), scenario.status)

print("5) En fil ändrad lokalt (avvikelse från validerad version)")
m, e, ui = scenario("ändrad", lambda r: open(f"{r}/analysis/deming.py","a").write("\n# lokal ändring\n"))
check("appen fungerar men varnar och namnger deming.py", ui and any("analysis/deming.py" in x for x in m) and not e, (m, e))
print("\nALLA GODKÄNDA" if not fails else f"\n{fails} FEL")
