"""Paketet får aldrig levereras med ett manifest som inte stämmer med filerna."""
import hashlib, json, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def test_manifest_matches_files():
    man = json.load(open(os.path.join(ROOT, "manifest.json"), encoding="utf-8"))
    from version import VERSION
    assert man["version"] == VERSION, "manifest.json gäller en annan version — kör skapa_manifest.py"
    for rel, digest in {**man["required"], **man["recommended"]}.items():
        p = os.path.join(ROOT, rel)
        assert os.path.exists(p), f"saknas: {rel}"
        assert hashlib.sha256(open(p, "rb").read()).hexdigest() == digest, \
            f"{rel} har ändrats efter att manifestet skapades — kör skapa_manifest.py"
