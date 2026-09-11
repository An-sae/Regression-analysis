"""
Version and validation status.

WHY THIS FILE EXISTS
--------------------
For accredited laboratory use (ISO 15189:2022) every result must be
traceable to the exact software that produced it. This module provides a
single version string that is:

  - shown in the application sidebar
  - written into every exported CSV and Excel file
  - drawn onto every exported figure

CHANGE CONTROL
--------------
Increment VERSION whenever the calculation code changes, and record the
change in CHANGELOG below. Re-run tests/ and update VALIDATED_ON.

  MAJOR  incompatible change to how a result is calculated
  MINOR  new analysis or feature
  PATCH  bug fix or cosmetic change
"""

VERSION = "1.0.0"

# Date the full validation suite was last executed against the reference
# datasets (see Valideringsrapport.docx).
VALIDATED_ON = "2026-09-10"

# Short description shown next to the version in the application.
STATUS = "Validerad"


CHANGELOG = [
    ("1.0.0", "2026-09-10",
     "Första validerade versionen. Verifierad mot Bland & Altman 1986, "
     "Chesher 2008 (CLSI EP15-A3), sluten Deming-lösning och oberoende "
     "Passing–Bablok-implementation. Korrigerar tidigare fel i VME/ME-"
     "riktning, Passing–Bablok konfidensintervall och effektiva "
     "frihetsgrader."),
]


def version_string() -> str:
    """Short label for the user interface."""
    return f"v{VERSION}"


def stamp() -> str:
    """One-line provenance stamp for exported files and figures."""
    return (f"Method Comparison Tool v{VERSION} "
            f"(validerad {VALIDATED_ON})")


def full_header() -> str:
    """Multi-line header written at the top of exported data files."""
    return (f"# Method Comparison Tool v{VERSION}\n"
            f"# Validerad: {VALIDATED_ON}\n")
