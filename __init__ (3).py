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

VERSION = "2.2.0"

# Date the full validation suite was last executed against the reference
# datasets (see Valideringsrapport.docx).
VALIDATED_ON = "2026-09-22"

# Short description shown next to the version in the application.
STATUS = "Validerad"


CHANGELOG = [
    ("2.2.0", "2026-09-22",
     "Brett format: filer med en kolumn per analys (Sysmex XN, LIS-pivot) "
     "identifieras och läses automatiskt. Analysnamn kopplas mellan instrument "
     "och svenska NPU-namn (WBC <-> B-LPK, HGB <-> B-Hb, PLT <-> B-TPK m.fl.), "
     "enheter i rubriker ignoreras vid kopplingen. Ny översikt: alla kopplade "
     "analyser jämförs i en körning med samma validerade funktioner som den "
     "enskilda analysen (resultat bit för bit identiska), med Excelexport. "
     "Enhetsskillnad mellan filerna (t.ex. g/dL mot g/L) upptäcks och varnas; "
     "valfri omräkningsfaktor för fil B. Excel: 'NA' (natrium) läses inte längre "
     "som saknat värde; bladet med data väljs automatiskt; enhetsrad under "
     "rubriken hanteras; summarader (Medelvärde, SD, Antal ...) ignoreras och "
     "redovisas; Excel-tal och text-tal i samma kolumn tolkas rätt ('0,411'). "
     "Stöd för .xls (xlrd tillagd i requirements.txt). Tvåfilsflödet utbrutet ur "
     "app.py till ui/two_file.py. Verifierad med tests/instrument (4 "
     "instrumentscenarier, 12 Excelfällor, översikt, gränssnitt)."),
    ("2.1.0", "2026-09-22",
     "Ny filinläsning (analysis/file_reader.py): alla celler läses som text; "
     "kodning (UTF-8, BOM, Windows-1252), avgränsare, rubrikrad och Excel-blad "
     "identifieras automatiskt. Tal tolkas per kolumn så att decimaltecknet "
     "avgörs av hela kolumnen: '1,786' i en fil med decimalpunkt läses nu som "
     "1786 (tidigare 1,786). Kvalificerare (<, >), flaggor och enheter skiljs "
     "av; '<' och '>' utesluts och redovisas. Prov-ID normaliseras (mellanslag, "
     "versaler, 123.0, valfritt ledande nollor); ID i vetenskaplig notation "
     "flaggas. Analyser kopplas mellan filer (CRP4 <-> CRP <-> P-CRP) med "
     "förslag som användaren bekräftar. Analyskolumn N/A på en fil med flera "
     "resultat per prov stoppas (tidigare parades olika analyser ihop). "
     "Omkörningar: 'behåll första giltiga' som standard. Antal matchade, "
     "använda och uteslutna par redovisas med orsak. Samma säkra taltolkning "
     "i enfils- och klistra-in-läget. Precision: trunkering till balanserad "
     "design redovisas och markeras. Knappen 'Återställ alla punkter' "
     "kraschade och är rättad. Verifierad med tests/filinlasning (28 fällor, "
     "helhetstest, gränssnittstest, precision, rundtur, skala, uteslutning)."),
    ("2.0.0", "2026-09-21",
     "Viktad Deming ersatt med Linnet (1993) iterativt omviktad algoritm "
     "(vikter från skattade sanna värden, jackknife där hela anpassningen "
     "upprepas). Tidigare version använde vikter 1/(x²+y²/λ) utan iteration "
     "och ett oviktat intercept i jackknife. Resultat för viktad Deming "
     "ändras; tidigare viktade Deming-analyser bör köras om. Verifierad mot "
     "NCSS kap. 303 ex. 6 / R mcr: samtliga sex publicerade värden "
     "återges med 7 decimaler."),
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
