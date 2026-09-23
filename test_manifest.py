"""pytest: virtuella instrumentexporter, Excelfällor, översikt och gränssnitt."""
import os, subprocess, sys
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instrument")

def _ok(script):
    r = subprocess.run([sys.executable, script], cwd=HERE, capture_output=True, text=True, timeout=1200)
    assert "ALLA GODKÄNDA" in r.stdout, r.stdout[-3000:]

def test_instrumentscenarier():  _ok("testa_instrument.py")
def test_excelfallor():          _ok("testa_excelfallor.py")
def test_oversikt_identisk():    _ok("testa_oversikt.py")
def test_granssnitt_brett():     _ok("testa_granssnitt_instrument.py")
