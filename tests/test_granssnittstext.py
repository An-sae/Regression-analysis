"""pytest: gränssnittets texter ska vara skrivna som av en människa (v2.2.2).

Inga dekorativa emojier i appen eller översättningarna, och inga långa
tankstreck (—) i svenska texter. Tillåtet: ✓ i Systemstatus (installationen
kontrolleras mot den), pilar och matematiska tecken som ↔ → × ± ≤ ≥.
"""
import os, re, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-✒✔-➿⬀-⯿"
                   "ℹ↺↻▶️]")


def _strings(path):
    """Alla strängliteraler i en Python-fil (kommentarer räknas inte)."""
    import ast
    tree = ast.parse(open(path, encoding="utf-8").read())
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            yield n.lineno, n.value


def test_inga_emojier_i_granssnittet():
    hits = []
    for f in ("app.py", "ui/two_file.py", "i18n.py"):
        for ln, s in _strings(os.path.join(ROOT, f)):
            if EMOJI.search(s):
                hits.append(f"{f}:{ln} {s[:60]!r}")
    assert not hits, "\n".join(hits)


def test_inga_langa_tankstreck_i_svenska_texter():
    from i18n import SV
    hits = [v[:70] for v in SV.values() if "—" in v]
    assert not hits, hits
