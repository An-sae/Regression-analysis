"""
Språkhantering / Language handling
==================================

Engelska används som nyckel. Saknas en översättning visas nyckeln, vilket
gör att gränssnittet aldrig går sönder av en glömd sträng.

Fackuttryck översätts INTE: Passing–Bablok, Deming, Bland–Altman,
PPA, NPA, OPA, VME, ME, CLSI, EUCAST, CV, SD, LR+, LR−.

Lägg till nya strängar i SV nedan. Kör  python kontrollera_sprak.py
för att se vilka som saknar översättning.
"""

import streamlit as st

LANGUAGES = {"Svenska": "sv", "English": "en"}
DEFAULT_LANG = "sv"


# Last language seen inside a script run. Used ONLY when t() is called
# outside a script run (e.g. by Streamlit's test harness re-invoking a
# format_func). Inside a run, each user's own session state always wins,
# so concurrent users on a server never affect each other.
_last_lang = DEFAULT_LANG


def get_lang() -> str:
    global _last_lang
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        in_run = get_script_run_ctx(suppress_warning=True) is not None
    except Exception:
        in_run = True
    if not in_run:
        return _last_lang
    lang = st.session_state.get("_lang", DEFAULT_LANG)
    _last_lang = lang
    return lang


def t(text: str) -> str:
    """Översätt en sträng. Okänd sträng returneras oförändrad."""
    if get_lang() == "en":
        return text
    return SV.get(text, text)


# ── Svenska översättningar, nyckel = engelsk originaltext ────────────────────
SV = {
    # --- Rubriker och navigation ---------------------------------------------
    "📊 Method Comparison": "📊 Metodjämförelse",
    "##### ① &nbsp;Choose your analysis": "##### ① &nbsp;Välj analys",
    "##### ② &nbsp;Load your data": "##### ② &nbsp;Ladda in data",
    "##### ③ &nbsp;Name your methods": "##### ③ &nbsp;Namnge metoderna",
    "##### ④ &nbsp;Plot options": "##### ④ &nbsp;Diagraminställningar",
    "##### ④ &nbsp;Breakpoints": "##### ④ &nbsp;Brytpunkter",
    "##### ⑤ &nbsp;Matrix options": "##### ⑤ &nbsp;Matrisinställningar",
    "##### ④ &nbsp;Precision options": "##### ④ &nbsp;Precisionsinställningar",
    "Analysis type": "Analystyp",
    "Language": "Språk",

    # --- Analysbeskrivningar --------------------------------------------------
    "Non-parametric regression · robust to outliers":
        "Icke-parametrisk regression · tål extremvärden",
    "Errors-in-both-variables regression":
        "Regression med mätfel i båda metoderna",
    "Zone diameter agreement · EUCAST / CLSI":
        "Överensstämmelse för zondiametrar · EUCAST / CLSI",
    "Within-run & within-lab imprecision":
        "Inomserie- och totalimprecision",
    "2×2-tabell för positiv/negativ-metoder":
        "2×2-tabell för positiv/negativ-metoder",

    # --- Deming ---------------------------------------------------------------
    "⚙️ Deming options": "⚙️ Deming-inställningar",
    "Weighted Deming": "Viktad Deming",
    "Error ratio λ = Var(y)/Var(x)": "Felkvot λ = Var(y)/Var(x)",
    "On: errors proportional to concentration (constant CV). "
    "Off: equal error variances.":
        "På: mätfelet är proportionellt mot koncentrationen (konstant CV). "
        "Av: lika stora felvarianser.",
    "λ = 1 means both methods have equal imprecision.":
        "λ = 1 betyder att båda metoderna har lika stor imprecision.",

    # --- Datainläsning --------------------------------------------------------
    "Data format": "Dataformat",
    "Single file (two columns)": "En fil (två kolumner)",
    "Two long-format files (match by ID)":
        "Två filer i långt format (matcha på prov-ID)",
    "Input method": "Inmatningssätt",
    "📂 Upload file": "📂 Ladda upp fil",
    "📋 Paste data": "📋 Klistra in data",
    "Upload CSV or Excel": "Ladda upp CSV eller Excel",
    "Sheet / tab": "Blad / flik",
    "Header row?": "Rubrikrad?",
    "Yes (first row)": "Ja (första raden)",
    "No header": "Ingen rubrik",
    "Preview (first 5 rows):": "Förhandsvisning (första 5 raderna):",
    "Reference column (x)": "Referenskolumn (x)",
    "Candidate column (y)": "Kandidatkolumn (y)",
    "Copy two columns from Excel and paste below.":
        "Kopiera två kolumner från Excel och klistra in nedan.",
    "Paste data here": "Klistra in data här",
    "**File A — Reference method**": "**Fil A — Referensmetod**",
    "**File B — Candidate method**": "**Fil B — Kandidatmetod**",
    "Upload reference file": "Ladda upp referensfil",
    "Upload candidate file": "Ladda upp kandidatfil",
    "Header row? (applies to both files)":
        "Rubrikrad? (gäller båda filerna)",
    "**Column mapping — File A**": "**Kolumnval — Fil A**",
    "**Column mapping — File B**": "**Kolumnval — Fil B**",
    "Sample ID": "Prov-ID",
    "Analysis": "Analys",
    "Result": "Resultat",
    "Label A": "Namn på A",
    "Label B": "Namn på B",
    "Analyte to compare": "Analyt att jämföra",
    "Resolve duplicates": "Hantera dubbletter",
    "Keep first": "Behåll första",
    "Keep last": "Behåll sista",
    "Use mean": "Använd medelvärde",
    "All rows treated as one analyte.":
        "Alla rader behandlas som en och samma analys.",
    "No common analytes found in both files.":
        "Inga gemensamma analyter i båda filerna.",
    "Columns named Column 1, Column 2 … — first row kept as data.":
        "Kolumnerna heter Kolumn 1, Kolumn 2 … — första raden behålls som data.",
    "**Filter rows (optional)**": "**Filtrera rader (valfritt)**",
    "Filter by column": "Filtrera på kolumn",
    "— no filter —": "— inget filter —",
    "No values selected — using all rows.":
        "Inga värden valda — alla rader används.",

    # --- Metodnamn ------------------------------------------------------------
    "Reference method (x-axis)": "Referensmetod (x-axel)",
    "Candidate method (y-axis)": "Kandidatmetod (y-axel)",
    "Reference Method": "Referensmetod",
    "Candidate Method": "Kandidatmetod",

    # --- Diagraminställningar -------------------------------------------------
    "Decimal places": "Antal decimaler",
    "Bland–Altman as % difference": "Bland–Altman som %-skillnad",
    "Off: absolute difference (y − x). On: percentage of the mean.":
        "Av: absolut skillnad (y − x). På: procent av medelvärdet.",
    "🏷️ Titles": "🏷️ Rubriker",
    "Regression plot": "Regressionsdiagram",
    "Bland–Altman plot": "Bland–Altman-diagram",
    "Leave blank for automatic title": "Lämna tomt för automatisk rubrik",
    "📐 Axis ranges": "📐 Axelgränser",
    "Leave any field blank for automatic scaling.":
        "Lämna fältet tomt för automatisk skalning.",
    "**Regression plot**": "**Regressionsdiagram**",
    "**Bland–Altman plot**": "**Bland–Altman-diagram**",
    "X min": "X min", "X max": "X max", "Y min": "Y min", "Y max": "Y max",
    "🎨 Colours": "🎨 Färger",
    "Points": "Punkter", "Identity": "Identitetslinje", "Fit": "Anpassad linje",
    "Show 95% CI band": "Visa 95 % KI-band",
    "CI band": "KI-band", "CI transparency": "KI-genomskinlighet",
    "Mean bias": "Systematiskt fel", "LoA": "Överensstämmelsegränser",
    "✏️ Legend & label text": "✏️ Text i förklaring och etiketter",
    "Fit line": "Anpassad linje", "Mean line": "Medellinje",
    "Upper LoA": "Övre gräns", "Lower LoA": "Undre gräns",
    "Observations": "Observationer", "Identity (y = x)": "Identitet (y = x)",
    "Regression": "Regression", "Difference": "Skillnad", "Mean": "Medelvärde",

    # --- Resultat -------------------------------------------------------------
    "Total rows": "Antal rader",
    "Missing / excluded": "Saknade / uteslutna",
    "Valid pairs": "Giltiga par",
    "▶ Analyze": "▶ Analysera",
    "👆 Click **Analyze** to run the regression.":
        "👆 Klicka på **Analysera** för att köra regressionen.",
    "Statistic": "Storhet", "Value": "Värde",
    "Slope": "Lutning", "Intercept": "Intercept",
    "Bias": "Systematiskt fel",
    "LoA lower": "Undre överensstämmelsegräns",
    "LoA upper": "Övre överensstämmelsegräns",
    "Export": "Export",
    "⚙️ Image resolution": "⚙️ Bildupplösning",
    "Resolution": "Upplösning",
    "📐 SVG": "📐 SVG",
    "**Results data & full report**": "**Resultatdata och fullständig rapport**",
    "📥 Results CSV": "📥 Resultat (CSV)",
    "📄 HTML Report": "📄 HTML-rapport",
    "**Matched pairs data**": "**Matchade par**",
    "📊 Download matched pairs (Excel)":
        "📊 Ladda ner matchade par (Excel)",
    "↺ Restore all points": "↺ Återställ alla punkter",
    "Excluded from analysis (add or remove here)":
        "Uteslutna ur analysen (lägg till eller ta bort här)",
    "💡 Click a point, or drag a box/lasso, to exclude it from both "
    "plots and all statistics.":
        "💡 Klicka på en punkt, eller dra en ruta eller lasso, för att "
        "utesluta den ur båda diagrammen och all statistik.",

    # --- Konfusionsmatris -----------------------------------------------------
    "Zone Diameter Confusion Matrix": "Konfusionsmatris för zondiametrar",
    "Breakpoint system": "Brytpunktssystem",
    "S ≥ (mm)": "S ≥ (mm)", "R ≤ (mm)": "R ≤ (mm)",
    "Step size (mm per cell)": "Stegstorlek (mm per cell)",
    "Essential agreement band (± mm)": "Band för essential agreement (± mm)",
    "📐 Range & layout": "📐 Område och utseende",
    "Leave blank for automatic range.": "Lämna tomt för automatiskt område.",
    "Show diagonal lines": "Visa diagonallinjer",
    "Show n = total (outside frame)": "Visa n = totalt (utanför ramen)",
    "🏷️ Title": "🏷️ Rubrik",
    "Matrix title": "Matrisrubrik",
    "Matrix colour": "Matrisfärg",
    "Coloured bands (mm from diagonal)": "Färgade band (mm från diagonalen)",
    "🔢 Cell numbers": "🔢 Siffror i cellerna",
    "Font size": "Teckenstorlek", "Bold": "Fet stil",
    "On shaded cells": "På färgade celler", "On white cells": "På vita celler",
    "Export matrix": "Exportera matris",
    "⚙️ Export resolution": "⚙️ Upplösning vid export",
    "📥 Matrix CSV": "📥 Matris (CSV)",
    "ℹ️ Acceptability thresholds": "ℹ️ Acceptanskriterier",
    "Categorical Agr.": "Kategoriöverensstämmelse",

    # --- Precision ------------------------------------------------------------
    "Precision Evaluation — CLSI EP15-A3":
        "Precisionsvärdering — CLSI EP15-A3",
    "📂 Wide format (columns = days)": "📂 Brett format (kolumn = dag)",
    "📋 Paste wide format": "📋 Klistra in brett format",
    "🔍 Long format (search by Sample ID)":
        "🔍 Långt format (sök på prov-ID)",
    "Each column = one day, each row = one replicate. "
    "Column headers = day names.":
        "Varje kolumn = en dag, varje rad = ett replikat. "
        "Kolumnrubrikerna blir dagbeteckningar.",
    "Upload Excel or CSV": "Ladda upp Excel eller CSV",
    "Copy from Excel (columns = days) and paste below.":
        "Kopiera från Excel (kolumner = dagar) och klistra in nedan.",
    "Paste here": "Klistra in här",
    "Upload long-format file": "Ladda upp fil i långt format",
    "Sample ID column": "Kolumn med prov-ID",
    "Result column": "Kolumn med resultat",
    "Sort by (run order/date)": "Sortera efter (körordning/datum)",
    "Select analyte": "Välj analyt",
    "Select Sample ID": "Välj prov-ID",
    "How are days defined?": "Hur definieras dagarna?",
    "Group by a date / day column": "Gruppera efter datum- eller dagkolumn",
    "Split every N results": "Dela upp var N:te resultat",
    "Day column": "Dagkolumn",
    "Results per day (n)": "Antal resultat per dag (n)",
    "Precision Results": "Precisionsresultat",
    "Grand mean": "Medelvärde", "Days": "Dagar",
    "Replicates / day": "Replikat per dag",
    "Total measurements": "Antal mätningar",
    "**Sammanfattning**": "**Sammanfattning**",
    "📊 Full variance component breakdown":
        "📊 Fullständig uppdelning av varianskomponenter",
    "📋 Per-day summary": "📋 Sammanställning per dag",
    "📊 Statistical settings": "📊 Statistiska inställningar",
    "Significance level (α)": "Signifikansnivå (α)",
    "Concentration levels tested (q)": "Antal testade nivåer (q)",
    "🏭 Manufacturer claims (optional)":
        "🏭 Tillverkarens påstående (valfritt)",
    "Claimed repeatability SD (σr)": "Påstådd repeterbarhet SD (σr)",
    "Claimed within-lab SD (σl)": "Påstådd totalimprecision SD (σl)",
    "📥 Download journal table (CSV)":
        "📥 Ladda ner tabell i tidskriftsformat (CSV)",
    "📊 Download Excel (raw data + summary)":
        "📊 Ladda ner Excel (rådata och sammanfattning)",
    "Component": "Komponent", "df": "Frihetsgrader",

    # --- Övrigt ---------------------------------------------------------------
    "↻ Reset all settings": "↻ Återställ alla inställningar",
    "📚 References": "📚 Referenser",
    "🔒 Dataskydd": "🔒 Dataskydd",
    "👈 Upload a CSV or Excel file in the sidebar.":
        "👈 Ladda upp en CSV- eller Excel-fil i menyn.",
    "👈 Select the columns to use in the sidebar.":
        "👈 Välj vilka kolumner som ska användas i menyn.",
    "👈 Paste your data in the sidebar.":
        "👈 Klistra in dina data i menyn.",
    "📄 Expected data format": "📄 Förväntat dataformat",
    "📚 Key references": "📚 Viktiga referenser",
    # --- Startsidan -----------------------------------------------------------
    "\n## Method Comparison Tool\n\nA simple tool for comparing two analytical "
    "measurement methods in clinical microbiology and clinical chemistry.\n"
    "👈 Select an analysis type in the sidebar, then upload your data or paste it directly.\n":
        "\n## Metodjämförelse\n\nEtt enkelt verktyg för att jämföra två "
        "analysmetoder inom klinisk mikrobiologi och klinisk kemi.\n"
        "👈 Välj analys i menyn till vänster och ladda sedan upp eller klistra in dina data.\n",

    "\n**📈 Passing–Bablok**\nNon-parametric regression — resistant to outliers, "
    "no assumptions about error distribution.\nSlope, intercept and 95 % confidence "
    "intervals via the rank-based method.\n":
        "\n**📈 Passing–Bablok**\nIcke-parametrisk regression — tål extremvärden "
        "och kräver inga antaganden om felens fördelning.\nLutning, intercept och "
        "95 % konfidensintervall med rangbaserad metod.\n",

    "\n**📉 Deming regression**\nAccounts for measurement error in both methods.\n"
    "Ordinary (equal variances) or weighted (proportional CV, Linnet 1990).\n"
    "Confidence intervals via jackknife resampling.\n":
        "\n**📉 Deming-regression**\nTar hänsyn till mätfel i båda metoderna.\n"
        "Oviktad (lika varians) eller viktad (proportionell CV, Linnet 1990).\n"
        "Konfidensintervall med jackknife.\n",

    "\n**🔢 Confusion matrix**\nZone diameter agreement grid for disk diffusion "
    "comparison.\nEssential agreement (±1/±2 mm), categorical agreement, VME and ME.\n"
    "EUCAST and CLSI breakpoints supported.\n":
        "\n**🔢 Konfusionsmatris**\nRutnät för överensstämmelse mellan zondiametrar "
        "vid diskdiffusion.\nEssential agreement (±1/±2 mm), kategoriöverensstämmelse, "
        "VME och ME.\nBrytpunkter enligt EUCAST och CLSI.\n",

    "\n**🔬 Precision Evaluation (EP15-A3)**\nWithin-run (repeatability) and "
    "within-laboratory (total) SD and CV.\nChi-square verification against "
    "manufacturer claims.\nBased on CLSI EP15-A3 (2014) — 5 replicates × 5 days recommended.\n":
        "\n**🔬 Precisionsvärdering (EP15-A3)**\nInomserieprecision (repeterbarhet) "
        "och totalimprecision som SD och CV.\nVerifiering mot tillverkarens påstående "
        "med chi-två-test.\nEnligt CLSI EP15-A3 (2014) — 5 replikat × 5 dagar rekommenderas.\n",

    "**📄 Expected data format**": "**📄 Förväntat dataformat**",
    "**📚 Key references**": "**📚 Viktiga referenser**",
    "**Example output:**": "**Exempel på resultat:**",

    "At least two numeric columns — one per method. Extra columns (species, "
    "antibiotic, lab) can be used to filter rows.":
        "Minst två numeriska kolumner — en per metod. Ytterligare kolumner "
        "(art, antibiotikum, laboratorium) kan användas för att filtrera rader.",
    "Accepted: Excel (.xlsx/.xls), CSV, or paste from Excel. Comma or point "
    "as decimal. Header row optional.":
        "Accepteras: Excel (.xlsx/.xls), CSV eller inklistring från Excel. "
        "Komma eller punkt som decimaltecken. Rubrikrad valfri.",
    "**One column per day, one row per replicate.** EP15-A3 recommends 5 "
    "replicates × 5 days at ≥ 2 concentration levels.":
        "**En kolumn per dag, en rad per replikat.** EP15-A3 rekommenderar "
        "5 replikat × 5 dagar på minst 2 koncentrationsnivåer.",
    "Upload as Excel / CSV or paste directly from Excel. Column headers become "
    "the day labels. Comma or point as decimal.":
        "Ladda upp som Excel eller CSV, eller klistra in direkt från Excel. "
        "Kolumnrubrikerna blir dagbeteckningar. Komma eller punkt som decimaltecken.",

    # --- Meddelanden ----------------------------------------------------------
    "### 🔒 Method Comparison Tool": "### 🔒 Metodjämförelse",
    "Upload or paste precision data in the main area →":
        "Ladda upp eller klistra in precisionsdata i huvudfönstret →",
    "Choose a data source above to begin the precision analysis.":
        "Välj en datakälla ovan för att påbörja precisionsanalysen.",
    "👈 Paste your data in the sidebar to get started.":
        "👈 Klistra in dina data i menyn för att komma igång.",
    "👈 Upload both files and configure the column mapping in the sidebar.":
        "👈 Ladda upp båda filerna och välj kolumner i menyn.",
    "⚠️ No matched pairs — check column mapping.":
        "⚠️ Inga matchade par — kontrollera kolumnvalen.",
    "Need at least 2 days of data.": "Minst 2 dagar krävs.",
    "Need at least 2 replicates per day.": "Minst 2 replikat per dag krävs.",

    # --- Precision -------------------------------------------------------------
    "EP15-A3 recommends 5 replicates × 5 days (minimum 2 × 2).":
        "EP15-A3 rekommenderar 5 replikat × 5 dagar (minst 2 × 2).",
    "Enter the claimed SDs to run the chi-square verification. Leave at 0 to skip.":
        "Ange tillverkarens SD-värden för att göra chi-två-verifieringen. "
        "Lämna 0 för att hoppa över.",
    "**Chi-square verification (EP15-A3 §2.4.3)**":
        "**Chi-två-verifiering (EP15-A3 §2.4.3)**",
    "Journal-style precision table — days as rows, replicates as columns, "
    "precision summary in footer:":
        "Precisionstabell i tidskriftsformat — dagar som rader, replikat som "
        "kolumner, precisionsmått i fotraden:",
    "ℹ️ Why does this differ from the CLSI value?":
        "ℹ️ Varför skiljer sig detta från CLSI-värdet?",
    "Upload a long-format file with **SampleID | Analysis | Result** columns. "
    "Search for a Sample ID and split results into days automatically.":
        "Ladda upp en fil i långt format med kolumnerna **Prov-ID | Analys | "
        "Resultat**. Sök på ett prov-ID så delas resultaten upp i dagar automatiskt.",

    # --- Fyrfältstabell --------------------------------------------------------
    "Konfidensgrad": "Konfidensgrad",
    "Positivt utfall": "Positivt utfall",
    "Negativt utfall": "Negativt utfall",
    "ℹ️ Tolkning": "ℹ️ Tolkning",
    # --- Acceptanskriterier (konfusionsmatris) --------------------------------
    "\n| Metric | EUCAST | CLSI |\n|---|---|---|\n"
    "| Essential Agreement \u00b12 mm | \u2265 90 % | \u2265 90 % |\n"
    "| Categorical Agreement | \u2265 90 % | \u2265 90 % |\n"
    "| Very major error (false susceptible, R\u2192S) | \u2264 3 % of **R** isolates | \u2264 1.5 % of **R** |\n"
    "| Major error (false resistant, S\u2192R) | \u2264 3 % of **S** isolates | \u2264 3 % of **S** |\n"
    "*EUCAST Disk Diffusion v10.0; CLSI M52.*":
        "\n| M\u00e5tt | EUCAST | CLSI |\n|---|---|---|\n"
        "| Essential agreement \u00b12 mm | \u2265 90 % | \u2265 90 % |\n"
        "| Kategori\u00f6verensst\u00e4mmelse | \u2265 90 % | \u2265 90 % |\n"
        "| Mycket allvarligt fel (falskt k\u00e4nslig, R\u2192S) | \u2264 3 % av **R**-isolaten | \u2264 1,5 % av **R** |\n"
        "| Allvarligt fel (falskt resistent, S\u2192R) | \u2264 3 % av **S**-isolaten | \u2264 3 % av **S** |\n"
        "*EUCAST Disk Diffusion v10.0; CLSI M52.*",
    "**Between-day variance estimated as zero**, so the within-run "
    "and within-laboratory figures are identical. This is a valid "
    "ANOVA result, not an error: the scatter between day means "
    "(s\u00b2day = {a}) is smaller than what within-run noise alone "
    "would produce (S\u00b2r/n = {b}), so the negative variance "
    "component is truncated to zero (CLSI EP15-A3). It usually "
    "means there is no detectable day-to-day effect \u2014 check that "
    "your days are grouped correctly.":
        "**Variationen mellan dagar skattas till noll**, d\u00e4rf\u00f6r blir "
        "inomserieprecisionen och totalimprecisionen identiska. Detta \u00e4r "
        "ett giltigt ANOVA-resultat och inget fel: spridningen mellan "
        "dagarnas medelv\u00e4rden (s\u00b2dag = {a}) \u00e4r mindre \u00e4n vad slumpen "
        "inom serien ensam ger upphov till (S\u00b2r/n = {b}). Den negativa "
        "varianskomponenten s\u00e4tts d\u00e5 till noll enligt CLSI EP15-A3. "
        "Det betyder oftast att ingen m\u00e4tbar dageffekt finns \u2014 "
        "kontrollera att dagindelningen \u00e4r korrekt.",
    # --- Fyrfältstabell (femte analysen) --------------------------------------
    "Fourfold table (qualitative)": "Fyrfältstabell (kvalitativ)",
    "2×2 table for positive/negative methods":
        "2×2-tabell för positiv/negativ-metoder",
    "##### ④ &nbsp;Fourfold table options":
        "##### ④ &nbsp;Fyrfältsinställningar",
    "Fourfold table": "Fyrfältstabell",
    "Analysis / question": "Analys / frågeställning",
    "e.g. hs-Troponin I, cut-off 26 ng/L":
        "t.ex. hs-Troponin I, beslutsgräns 26 ng/L",
    "What is being compared?": "Vad jämförs?",
    "Two methods against each other (no gold standard)":
        "Två metoder mot varandra (inget facit)",
    "Against a reference standard (gold standard exists)":
        "Mot en referensstandard (facit finns)",
    "Sensitivity, specificity and predictive values are reported. "
    "Requires that the reference method truly is the gold standard.":
        "Sensitivitet, specificitet och prediktiva värden redovisas. "
        "Kräver att referensmetoden verkligen utgör facit.",
    "PPA/NPA are reported. Sensitivity may not be claimed when "
    "neither method is a gold standard (CLSI EP12-A2).":
        "PPA/NPA redovisas. Sensitivitet får inte hävdas när ingen "
        "metod är facit (CLSI EP12-A2).",
    "⚖️ Cut-off values": "⚖️ Beslutsgränser",
    "Fill in if the data are quantitative and need splitting into "
    "positive/negative. Leave blank if the data are already "
    "positive/negative.":
        "Fyll i om data är kvantitativa och ska delas upp i "
        "positiv/negativ. Lämna tomt om data redan är positiv/negativ.",
    "Cut-off reference": "Gräns referens",
    "Cut-off candidate": "Gräns kandidat",
    "Positive is defined as a value ≥ the cut-off.":
        "Positivt definieras som värde ≥ gränsen.",
    "🏷️ Result labels": "🏷️ Benämningar",
    "Positive result": "Positivt utfall",
    "Negative result": "Negativt utfall",
    "Confidence level": "Konfidensgrad",
    "The data are quantitative. Set cut-off values in the sidebar "
    "under **Cut-off values** to split into positive/negative.":
        "Data är kvantitativa. Ange beslutsgränser i menyn under "
        "**Beslutsgränser** för att dela upp i positiv/negativ.",
    "Could not build the table": "Kunde inte bygga tabellen",
    "⚠️ Points to consider": "⚠️ Att beakta",
    "ℹ️ Interpretation": "ℹ️ Tolkning",

    # Mått
    "Sensitivity": "Sensitivitet",
    "Specificity": "Specificitet",
    "Positive predictive value (PPV)": "Positivt prediktivt värde (PPV)",
    "Negative predictive value (NPV)": "Negativt prediktivt värde (NPV)",
    "Positive predictive value": "Positivt prediktivt värde",
    "Negative predictive value": "Negativt prediktivt värde",
    "Correctly classified": "Korrekt klassificerade",
    "Prevalence in the material": "Prevalens i materialet",
    "Positive likelihood ratio (LR+)": "Likelihood-kvot positiv (LR+)",
    "Negative likelihood ratio (LR−)": "Likelihood-kvot negativ (LR−)",
    "Positive percent agreement (PPA)": "Positiv procentuell överensstämmelse (PPA)",
    "Negative percent agreement (NPA)": "Negativ procentuell överensstämmelse (NPA)",
    "Overall percent agreement (OPA)": "Total procentuell överensstämmelse (OPA)",
    "Cohen's kappa": "Cohens kappa",
    "McNemar test (p)": "McNemars test (p)",
    "McNemar test (p-value)": "McNemars test (p-värde)",
    "systematic difference": "systematisk skillnad",
    "none detected": "ingen påvisad",
    "Measure": "Mått",
    "Count / interpretation": "Antal / tolkning",
    "Count": "Antal",
    "Results": "Resultat",
    "Total": "Summa",
    "CI": "KI",
    "True positive": "Sant positiv",
    "False positive": "Falskt positiv",
    "False negative": "Falskt negativ",
    "True negative": "Sant negativ",
    "Green = agreement": "Grön = överensstämmelse",
    "Red = disagreement": "Röd = avvikelse",
    "Points to consider": "Att beakta",

    # Tolkningstexten
    "\n**Which measures apply** \u2014 if neither method can be considered a gold\n"
    "standard, sensitivity and specificity may not be claimed. Positive and\n"
    "negative percent agreement (PPA/NPA) are reported instead. This is the\n"
    "explicit recommendation of CLSI EP12-A2 and the FDA.\n\n"
    "**Confidence intervals** \u2014 calculated with the Wilson score method, which\n"
    "gives sensible limits even at 0 % and 100 % where the ordinary method\n"
    "fails. The width reflects how many samples were included, not how good\n"
    "the method is.\n\n"
    "**Cohen's kappa** \u2014 agreement corrected for that which arises by chance\n"
    "alone. The interpretation thresholds are arbitrary conventions.\n\n"
    "**McNemar test** \u2014 tests whether the disagreements are systematically\n"
    "skewed, that is whether one method more often gives a positive result\n"
    "than the other. Only the discordant cells contribute. A low p-value means\n"
    "a systematic difference, not necessarily a clinically important one.\n\n"
    "**Predictive values** apply only at the prevalence of the material\n"
    "examined and cannot be transferred to a population with a different\n"
    "prevalence.\n":
        "\n**Vilka mått som gäller** \u2014 om ingen av metoderna kan anses utgöra\n"
        "facit får sensitivitet och specificitet inte hävdas. Då redovisas\n"
        "positiv och negativ procentuell överensstämmelse (PPA/NPA). Detta är\n"
        "CLSI EP12-A2:s och FDA:s uttryckliga rekommendation.\n\n"
        "**Konfidensintervall** \u2014 beräknade med Wilsons score-metod, som ger\n"
        "rimliga gränser även vid 0 % och 100 % där den vanliga metoden\n"
        "misslyckas. Bredden speglar hur många prov som ingår, inte hur bra\n"
        "metoden är.\n\n"
        "**Cohens kappa** \u2014 överensstämmelse korrigerad för den som uppstår\n"
        "av en ren slump. Gränserna för tolkning är godtyckliga konventioner.\n\n"
        "**McNemars test** \u2014 prövar om avvikelserna är systematiskt\n"
        "snedfördelade, det vill säga om den ena metoden oftare ger positivt\n"
        "än den andra. Endast de diskordanta cellerna bidrar. Ett lågt\n"
        "p-värde innebär en systematisk skillnad, inte nödvändigtvis en\n"
        "kliniskt betydelsefull sådan.\n\n"
        "**Prediktiva värden** gäller endast vid prevalensen i det undersökta\n"
        "materialet och kan inte överföras till en population med annan\n"
        "prevalens.\n",
    # --- Inloggning och dataskydd ---------------------------------------------
    "Enter password to continue.": "Ange lösenord för att fortsätta.",
    "Password": "Lösenord",
    "Log in": "Logga in",
    "Incorrect password.": "Fel lösenord.",
    "🔒 Data protection": "🔒 Dataskydd",
    "The application runs locally on this computer. No data is sent "
    "anywhere and the application stores nothing itself.\n\n"
    "Do not upload data that can be traced back to an individual "
    "patient. Use de-identified sample IDs and relative day numbers "
    "instead of dates.":
        "Programmet körs lokalt på denna dator. Inga uppgifter skickas "
        "någon annanstans och programmet sparar ingenting själv.\n\n"
        "Ladda inte upp uppgifter som går att härleda till en enskild "
        "patient. Använd avidentifierade prov-ID och relativa dagnummer "
        "i stället för datum.",
    # --- Dataskydd per driftmiljö ---------------------------------------------
    "☁️ Web version — use anonymised or simulated data only.":
        "☁️ Webbversion — använd endast avidentifierade eller simulerade data.",
    "This web version runs on Streamlit Community Cloud, a public "
    "service operated by a US company. Files you upload are sent "
    "to and processed on servers outside the EU/EEA. The "
    "application saves nothing itself, but the data is still "
    "transferred and processed there.\n\n"
    "Never upload data that can be traced to an individual "
    "patient. Use simulated data, control material, or "
    "anonymised files: replace sample IDs with sequence numbers "
    "and dates with relative day numbers.\n\n"
    "For verification work on real patient samples, use the "
    "locally installed version.":
        "Denna webbversion körs på Streamlit Community Cloud, en publik "
        "tjänst som drivs av ett amerikanskt företag. Filer du laddar upp "
        "skickas till och behandlas på servrar utanför EU/EES. Programmet "
        "sparar ingenting själv, men uppgifterna överförs och behandlas "
        "ändå där.\n\n"
        "Ladda aldrig upp uppgifter som går att härleda till en enskild "
        "patient. Använd simulerade data, kontrollmaterial eller "
        "avidentifierade filer: ersätt prov-ID med löpnummer och datum "
        "med relativa dagnummer.\n\n"
        "Använd den lokalt installerade versionen för verifiering på "
        "riktiga patientprov.",
    "This version runs entirely in your web browser. Files you "
    "open are processed on your own computer and are never sent "
    "to any server. Nothing is saved when you close the page.\n\n"
    "Still avoid data that can be traced to an individual "
    "patient unless your local routines allow it.":
        "Denna version körs helt i din webbläsare. Filer du öppnar "
        "behandlas på din egen dator och skickas aldrig till någon "
        "server. Ingenting sparas när du stänger sidan.\n\n"
        "Undvik ändå uppgifter som går att härleda till en enskild "
        "patient om inte era lokala rutiner tillåter det.",
    # --- Tillagt vid granskning av synliga texter ------------------------------
    'Choose your analysis':
        'Välj analys',
    'Load your data':
        'Ladda in data',
    'Name your methods':
        'Namnge metoderna',
    'Plot options':
        'Diagraminställningar',
    'Breakpoints':
        'Brytpunkter',
    'Matrix options':
        'Matrisinställningar',
    'Fourfold table options':
        'Fyrfältsinställningar',
    'Precision options':
        'Precisionsinställningar',
    'Method Comparison':
        'Metodjämförelse',
    'Confusion Matrix':
        'Konfusionsmatris',
    'Precision Evaluation (EP15-A3)':
        'Precisionsvärdering (EP15-A3)',
    'Precision Evaluation':
        'Precisionsvärdering',
    'Regression / Confusion matrix':
        'Regression / Konfusionsmatris',
    'Reference':
        'Referens',
    'Candidate':
        'Kandidat',
    '📊 Download fourfold table (Excel)':
        '📊 Ladda ner fyrfältstabell (Excel)',
    '📥 Results (CSV)':
        '📥 Resultat (CSV)',
    'Preview — {r} replicates × {d} days (all rows shown):':
        'Förhandsvisning — {r} replikat × {d} dagar (alla rader visas):',
    'Preview — {n} rows for this sample:':
        'Förhandsvisning — {n} rader för detta prov:',
    'WITHIN-RUN (REPEATABILITY)':
        'INOMSERIEPRECISION (REPETERBARHET)',
    'Protocol: CLSI EP15-A3':
        'Protokoll: CLSI EP15-A3',
    'WITHIN-LABORATORY (TOTAL IMPRECISION)':
        'TOTALIMPRECISION (INOM LABORATORIET)',
    'eff. df':
        'eff. frihetsgrader',
    'Includes between-day variation':
        'Inkluderar variation mellan dagar',
    'TOTAL IMPRECISION — SIMPLE POOLED CALCULATION (all {nm} results as one set)':
        'TOTALIMPRECISION — ENKEL SAMMANSLAGEN BERÄKNING (alla {nm} resultat som ett material)',
    'ordinary SD of every measurement, day structure ignored':
        'vanlig SD över alla mätningar, dagindelningen ignoreras',
    'Within-run (repeatability)':
        'Inomserieprecision (repeterbarhet)',
    'Within-laboratory (total)':
        'Totalimprecision (inom laboratoriet)',
    'Simple pooled (all results)':
        'Enkel sammanslagning (alla resultat)',
    'Manufacturer claim — repeatability':
        'Tillverkarens påstående — repeterbarhet',
    'Manufacturer claim — within-laboratory':
        'Tillverkarens påstående — totalimprecision',
    'ᵃ Within-run SD (Sᵣ) = {sd}, CV% = {cv} (df = {df}; CLSI EP15-A3).':
        'ᵃ Inomserie-SD (Sᵣ) = {sd}, CV% = {cv} (frihetsgrader = {df}; CLSI EP15-A3).',
    'ᵇ Within-laboratory SD (Sₗ) = {sd}, CV% = {cv} (effective df = {df}; includes between-day variation).':
        'ᵇ Total-SD inom laboratoriet (Sₗ) = {sd}, CV% = {cv} (effektiva frihetsgrader = {df}; inkluderar variation mellan dagar).',
    '  Grand mean = {m}, D = {D} days, n = {n} replicates/day.':
        '  Medelvärde = {m}, D = {D} dagar, n = {n} replikat/dag.',
    'ᵈ Ordinary SD of all {n} results, day structure ignored (df = {df}). Shown for reference; it shrinks the between-day component by a factor {f} and is therefore biased low when a day effect exists.':
        'ᵈ Vanlig SD över alla {n} resultat, dagindelningen ignoreras (frihetsgrader = {df}). Visas som referens; den krymper dagkomponenten med faktorn {f} och underskattar därför imprecisionen när en dageffekt finns.',
    'ᶜ Chi-square verification (α = {a}, q = {q}); Pass if observed SD ≤ verification value.':
        'ᶜ Chi-två-verifiering (α = {a}, q = {q}); godkänd om observerad SD ≤ verifieringsvärdet.',
    "\nThe **CLSI within-laboratory SD** separates the data into a within-run and a\nbetween-day component and adds them on the variance scale\n(Sl² = Sr² + Sb²). The **simple pooled SD** ignores the day structure and\ntreats all {n} results as a single sample.\n\nThe two are related exactly, in expectation, by\n\nE[s²pooled] = Sr² + **{f}** × Sb²  where the factor is (D−1)n / (Dn−1)\n\nSo the simple calculation shrinks the between-day component by\n**{p} %** with your design of {D} days × {r} replicates. Consequences:\n\n- If there is **no** day-to-day effect (Sb² = 0) the two agree closely.\n- If a real day effect exists, the pooled value is **biased low** and\n  understates the imprecision a clinician would encounter between days.\n- The gap narrows as the number of days increases.\n\nReport the **CLSI value** for method validation and verification against a\nmanufacturer's claim. The pooled figure is provided for reference and for\ncomparison with sources that use the simplified approach.\n":
        '\n**CLSI:s totalimprecision** delar upp data i en komponent inom serie och en\nmellan dagar, och adderar dem på variansskalan (Sl² = Sr² + Sb²). Den\n**enkla sammanslagna SD:n** ignorerar dagindelningen och behandlar alla\n{n} resultat som ett enda material.\n\nDe två hänger ihop exakt, i förväntan, enligt\n\nE[s²sammanslagen] = Sr² + **{f}** × Sb²  där faktorn är (D−1)n / (Dn−1)\n\nDen enkla beräkningen krymper alltså dagkomponenten med **{p} %** med ditt\nupplägg på {D} dagar × {r} replikat. Konsekvenser:\n\n- Finns **ingen** dageffekt (Sb² = 0) stämmer de två väl överens.\n- Finns en verklig dageffekt blir det sammanslagna värdet **för lågt** och\n  underskattar den imprecision som uppstår mellan dagar.\n- Skillnaden minskar ju fler dagar som ingår.\n\nRapportera **CLSI-värdet** vid metodvalidering och verifiering mot\ntillverkarens påstående. Det sammanslagna värdet visas som referens och\nför jämförelse med källor som använt den förenklade metoden.\n',
    'No numeric rows found.':
        'Inga numeriska rader hittades.',
    'The table is empty.':
        'Tabellen är tom.',
    'The methods have different numbers of values.':
        'Metoderna har olika antal värden.',
    'cannot be calculated':
        'kan ej beräknas',
    'worse than chance':
        'sämre än slumpen',
    'slight':
        'obetydlig',
    'fair':
        'svag',
    'moderate':
        'måttlig',
    'substantial':
        'god',
    'almost perfect':
        'mycket god',
    'no discordant pairs':
        'inga diskordanta par',
    'exact binomial test':
        'exakt binomialtest',
    'chi-square with continuity correction':
        'chi-två med kontinuitetskorrektion',
    'Only {n} samples. CLSI EP12 recommends at least 50 samples, preferably 100–200 for verification.':
        'Endast {n} prov. CLSI EP12 rekommenderar minst 50 prov, helst 100–200 vid verifiering.',
    'Only {n} positive samples. The confidence interval for PPA/sensitivity will be very wide.':
        'Endast {n} positiva prov. Konfidensintervallet för PPA/sensitivitet blir mycket brett.',
    'Only {n} negative samples. The confidence interval for NPA/specificity will be very wide.':
        'Endast {n} negativa prov. Konfidensintervallet för NPA/specificitet blir mycket brett.',
    'The confidence interval for PPA spans {w} percentage points. More positive samples are needed for a reliable estimate.':
        'Konfidensintervallet för PPA spänner {w} procentenheter. Fler positiva prov behövs för en säker skattning.',
    'The confidence interval for NPA spans {w} percentage points. More negative samples are needed.':
        'Konfidensintervallet för NPA spänner {w} procentenheter. Fler negativa prov behövs.',
    'The proportion of positives in the material is {p} %. Predictive values apply only at this prevalence and must not be transferred to a clinical population with a different prevalence.':
        'Andelen positiva i materialet är {p} %. Prediktiva värden gäller endast vid denna prevalens och ska inte överföras till en klinisk population med annan prevalens.',
    'Sensitivity and specificity assume that the reference method is the gold standard for the true condition.':
        'Sensitivitet och specificitet förutsätter att referensmetoden utgör facit för sant tillstånd.',
    'Predictive values apply only at the prevalence in this material and cannot be transferred to a population with a different prevalence.':
        'Prediktiva värden gäller endast vid prevalensen i detta material och kan inte överföras till en population med annan prevalens.',
    'Neither method is assumed to be a gold standard. Percent agreement is therefore reported rather than sensitivity and specificity (CLSI EP12-A2, FDA 2007).':
        'Ingen av metoderna antas utgöra facit. Därför redovisas procentuell överensstämmelse och inte sensitivitet och specificitet (CLSI EP12-A2, FDA 2007).',
    'Confidence intervals calculated with the Wilson score method.':
        'Konfidensintervall beräknade med Wilsons score-metod.',
    "McNemar's test assesses whether the methods differ systematically; only discordant pairs contribute.":
        'McNemars test prövar om metoderna skiljer sig systematiskt åt; endast diskordanta par bidrar.',
    "Cohen's kappa describes agreement corrected for chance.":
        'Cohens kappa beskriver överensstämmelse korrigerad för slumpen.',
    '✅ Parsed {n} rows.': '✅ {n} rader inlästa.',
    'Minor errors: {n} ({p} %)': 'Mindre fel: {n} ({p} %)',
    'Count:': 'Antal:',
    'Mean:': 'MV:',
    'Within-run precision CV%:': 'Inomserieprecision CV%:',
    'Total imprecision CV%:': 'Totalimprecision CV%:',
    'Control': 'Kontroll',
    'SD and CV% refer to all {n} measurements pooled. Within-run precision and total imprecision according to CLSI EP15-A3. Design: {D} days × {r} replicates.': 'SD och CV% avser samtliga {n} mätningar sammanslagna. Inomserieprecision och totalimprecision enligt CLSI EP15-A3. Upplägg: {D} dagar × {r} replikat.',
    'Raw replicates': 'Rådata',
    'Summary': 'Sammanfattning',
    'Design: {D} days x {n} replicates ({N} measurements)': 'Upplägg: {D} dagar x {n} replikat ({N} mätningar)',
    'SD and CV% refer to all measurements pooled.': 'SD och CV% avser samtliga mätningar sammanslagna.',
    'Within-run precision and total imprecision according to CLSI EP15-A3.': 'Inomserieprecision och totalimprecision enligt CLSI EP15-A3.',
    '95% CI': '95 % KI',
    'Degrees of freedom': 'Frihetsgrader',
    'Variance (SD²)': 'Varians (SD²)',
    'Day': 'Dag',
    'Rep': 'Rep',
    'Within-run (Sᵣ)': 'Inomserie (Sᵣ)',
    'Between-day (Sᵦ)': 'Mellan dagar (Sᵦ)',
    'Within-laboratory / Total (Sₗ)': 'Totalimprecision (Sₗ)',
    'Between-day': 'Mellan dagar',
    'Reference (mm)': 'Referens (mm)',
    'Candidate (mm)': 'Kandidat (mm)',
    'Species': 'Art',
    'Replicate': 'Replikat',
    'Day mean': 'Dagmedelvärde',
    'Claimed SD': 'Påstådd SD',
    'Observed SD': 'Observerad SD',
    'Verification value': 'Verifieringsvärde',
    'Verdict': 'Utfall',
    '✅  PASS': '✅  GODKÄND',
    '❌  FAIL': '❌  UNDERKÄND',
    # --- Filinläsning v2.1 ---
    'Header row': 'Rubrikrad',
    'Automatic': 'Automatisk',
    'Automatic finds the header row even when the export starts with instrument or title rows.': 'Automatisk hittar rubrikraden även när exporten börjar med instrument- eller titelrader.',
    'Sheet in file A': 'Blad i fil A',
    'Sheet in file B': 'Blad i fil B',
    'sheet {s}': 'blad {s}',
    'header on row {h}': 'rubrik på rad {h}',
    'no header': 'ingen rubrikrad',
    'File {f}: {n} rows · {src} · {hdr}': 'Fil {f}: {n} rader · {src} · {hdr}',
    'semicolon': 'semikolon',
    'comma': 'komma',
    'tab': 'tabb',
    'UTF-8 with BOM': 'UTF-8 med BOM',
    'Analysis in file A': 'Analys i fil A',
    'Analysis in file B': 'Analys i fil B',
    'No matching analysis name found in file B — choose it manually.': 'Ingen motsvarande analys hittades i fil B — välj den manuellt.',
    'Suggested pairing: {a} ↔ {b} — please check.': 'Föreslagen koppling: {a} ↔ {b} — kontrollera.',
    'The file without an analysis column contains only one analysis (repeated sample IDs are reruns)': 'Filen utan analyskolumn innehåller bara en analys (upprepade prov-ID är omkörningar)',
    '⚙️ Matching options': '⚙️ Matchningsinställningar',
    'Ignore leading zeros in numeric sample IDs': 'Bortse från ledande nollor i numeriska prov-ID',
    'Excel removes leading zeros, so 0012345 in one file and 12345 in the other are treated as the same sample.': 'Excel tar bort ledande nollor, så 0012345 i den ena filen och 12345 i den andra behandlas som samma prov.',
    '⚠️ Repeated results (reruns): file A {a} rows, file B {b} rows.': '⚠️ Upprepade resultat (omkörningar): fil A {a} rader, fil B {b} rader.',
    'Keep first valid': 'Behåll första giltiga',
    'Keep last valid': 'Behåll sista giltiga',
    '✅ {m} samples matched · {u} pairs used': '✅ {m} prov matchade · {u} par används',
    'Only in A: {a}  |  Only in B: {b}': 'Endast i A: {a}  |  Endast i B: {b}',
    '{n} matched samples not used:': '{n} matchade prov används inte:',
    'below measuring range': 'under mätområdet',
    'above measuring range': 'över mätområdet',
    'text result': 'textresultat',
    'no result': 'inget resultat',
    'File {f}: {n} sample IDs are in scientific notation (e.g. 2,40915E+09) and cannot be matched. Export the IDs as text.': 'Fil {f}: {n} prov-ID är i vetenskaplig notation (t.ex. 2,40915E+09) och kan inte matchas. Exportera prov-ID som text.',
    "File {f}: {n} results such as 1,234 could be either a decimal or a thousands separator; read with decimal '{d}'. Check the values.": "Fil {f}: {n} resultat som 1,234 kan vara både decimal- och tusentalsavgränsare; lästa med decimaltecken '{d}'. Kontrollera värdena.",
    'File {f}: the result column mixes decimal comma and decimal point; each value was read by its own format. Check the values.': 'Fil {f}: resultatkolumnen blandar decimalkomma och decimalpunkt; varje värde lästes efter sitt eget format. Kontrollera värdena.',
    '🔎 How the values were read': '🔎 Så tolkades värdena',
    'Several results per sample ID but no analysis column is selected, so results cannot be paired safely. Choose the analysis column, or confirm that the file contains only one analysis.': 'Flera resultat per prov-ID men ingen analyskolumn är vald, så resultaten kan inte paras säkert. Välj analyskolumnen, eller bekräfta att filen bara innehåller en analys.',
    'Matching error': 'Fel vid matchning',
    '⚠️ {n} result(s) not used: the calculation requires the same number of replicates every day, so each day was limited to its first {m} results. They are marked in the raw data.': '⚠️ {n} resultat används inte: beräkningen kräver lika många replikat varje dag, så varje dag begränsades till sina {m} första resultat. De är markerade i rådata.',
    '⚠️ {n} trailing result(s) excluded (incomplete day).': '⚠️ {n} resultat i slutet uteslutna (ofullständig dag).',
    '✅ {d} days × {r} replicates ready.': '✅ {d} dagar × {r} replikat klara.',
    'Error': 'Fel',
    '🗑 Excluded points ({n})': '🗑 Uteslutna punkter ({n})',
    'These files differ from validated version {v}: {f}. Results are not covered by the validation until it is repeated.':
        'Dessa filer skiljer sig från validerad version {v}: {f}. Resultaten omfattas inte av valideringen förrän den upprepats.',
}
