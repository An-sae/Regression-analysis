"""pytest: filinläsning och matchning ska klara alla fällor och helhetstestet."""
import os, subprocess, sys
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "filinlasning")

def _run(script):
    r = subprocess.run([sys.executable, script], cwd=HERE, capture_output=True, text=True, timeout=900)
    return r.stdout

def test_alla_fallor_ok():
    out = _run("testa_filinlasning.py")
    rows = [l for l in out.splitlines() if l[:1] == "F" and l[1:3].isdigit()]
    assert len(rows) == 28 and all(l.split()[1] == "OK" for l in rows), out

def test_helhet_flera_analyser():
    assert "ALLA GODKÄNDA" in _run("testa_helhet.py")

def test_precision_rundtur_skala_uteslutning():
    assert "ALLA GODKÄNDA" in _run("testa_ovrigt.py")
