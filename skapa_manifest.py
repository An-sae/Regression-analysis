"""
Skapa manifest.json: kontrollsumma (SHA-256) för varje fil programmet behöver.

Körs vid paketering. Programmet jämför vid start sina filer mot manifestet
och talar om exakt vilka filer som saknas, ligger fel eller skiljer sig
från den validerade versionen.
"""
import hashlib, json, os
from version import VERSION, VALIDATED_ON

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIRED = [
    "app.py", "version.py", "i18n.py", "requirements.txt",
    "analysis/__init__.py", "analysis/regression.py", "analysis/deming.py",
    "analysis/statistics.py", "analysis/confusion.py", "analysis/precision.py",
    "analysis/export.py", "analysis/data_loader.py", "analysis/file_reader.py",
    "analysis/fourfold.py",
    "plots/__init__.py", "plots/regression_plot.py", "plots/confusion_plot.py",
    "plots/mpl_export.py", "plots/fourfold_plot.py",
]
RECOMMENDED = [".streamlit/config.toml"]


def sha(path):
    return hashlib.sha256(open(os.path.join(HERE, path), "rb").read()).hexdigest()


if __name__ == "__main__":
    m = {"version": VERSION, "validated_on": VALIDATED_ON,
         "required": {p: sha(p) for p in REQUIRED},
         "recommended": {p: sha(p) for p in RECOMMENDED if os.path.exists(os.path.join(HERE, p))}}
    json.dump(m, open(os.path.join(HERE, "manifest.json"), "w"), indent=1)
    print(f"manifest.json skriven för version {VERSION}: {len(m['required'])} obligatoriska filer")
