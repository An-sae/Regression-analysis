"""
Verifiering av filinläsning och matchning på prov-ID.

Princip
-------
Ett facit (sanna parvisa värden) genereras. Fil A skrivs alltid rent.
Fil B skrivs i en variant per "fälla" där EN sak ändras åt gången, så att
varje fel kan härledas till exakt en orsak. Filerna läses med programmets
egna funktioner (load_long_format, find_duplicates, resolve_duplicates,
get_common_analytes, match_two_files) med de kolumnval en användare gör.

Allvarlighetsgrad
-----------------
KRITISK   fel värde eller fel par går tyst in i analysen
ALLVARLIG par försvinner tyst (användaren får inget besked)
MÅTTLIG   användaren stoppas med fel/varning, måste förbehandla filen
OK        korrekt resultat, eller korrekt och tydligt redovisat
"""
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.abspath(_os.path.join(_HERE, "..", ".."))
import sys, io, time, json, numpy as np, pandas as pd
sys.path.insert(0, _ROOT)
from analysis.data_loader import (load_long_format, find_duplicates,
                                  get_common_analytes, match_two_files)

rng = np.random.default_rng(20260922)
OUT = _os.path.join(_HERE, "genererade_filer")
import os; os.makedirs(OUT, exist_ok=True)

# ── Facit ────────────────────────────────────────────────────────────────
N = 40
ids = [f"{2409150100 + i:010d}" for i in range(1, N + 1)]
for k in (3, 11, 27):                                    # ledande nollor
    ids[k] = f"{9150100 + k:010d}"                       # t.ex. 0009150103
ANALYTES = {"CRP": (0.8, 250, 1), "Kreatinin": (40, 600, 0), "Ferritin": (8, 2400, 1)}
truth = {}
for an, (lo, hi, dp) in ANALYTES.items():
    a = np.round(np.exp(rng.uniform(np.log(lo), np.log(hi), N)), dp)
    b = np.round(a * rng.normal(1.03, 0.04, N) + rng.normal(0, lo * 0.1, N), dp)
    truth[an] = {ids[i]: (float(a[i]), float(b[i])) for i in range(N)}

def long_df(side, names=None):
    names = names or {an: an for an in ANALYTES}
    rows = []
    for an in ANALYTES:
        for sid in ids:
            v = truth[an][sid][0 if side == "A" else 1]
            rows.append({"Provnummer": sid, "Analys": names[an], "Resultat": v,
                         "Enhet": {"CRP": "mg/L", "Kreatinin": "µmol/L", "Ferritin": "µg/L"}[an]})
    return pd.DataFrame(rows)

def num_sv(v, dp):
    return f"{v:.{dp}f}".replace(".", ",")

def write_csv(df, sep=";", dec=",", enc="utf-8", pre="", quote=False):
    d = df.copy()
    dp = {an: ANALYTES[an][2] for an in ANALYTES}
    if dec == ",":
        d["Resultat"] = [num_sv(v, 2) if isinstance(v, float) else v for v in d["Resultat"]]
    else:
        d["Resultat"] = [f"{v:.2f}" if isinstance(v, float) else v for v in d["Resultat"]]
    s = d.to_csv(sep=sep, index=False, quoting=1 if quote else 0)
    return (pre + s).encode(enc)

def write_xlsx(df, startrow=0, title=None):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Export", index=False, startrow=startrow)
        if title:
            w.sheets["Export"].cell(row=1, column=1, value=title)
    return buf.getvalue()

FILE_A = write_csv(long_df("A"))           # referensfil: ; och decimalkomma

# ── Fällor: (id, rubrik, funktion som returnerar (bytes, filnamn, mapping,
#     legitimt uteslutna {(analys, id)}), förväntat beteende) ─────────────
TRAPS = []
def trap(tid, title, expect):
    def deco(fn):
        TRAPS.append((tid, title, expect, fn)); return fn
    return deco

M = dict(id="Provnummer", an="Analys", res="Resultat")

@trap("F01", "Baslinje: samma format som fil A", "Alla 120 par korrekta")
def _(): return write_csv(long_df("B")), "b.csv", M, set()

@trap("F02", "Kommaseparerad med decimalpunkt (typ Abbott)", "Alla par korrekta")
def _(): return write_csv(long_df("B"), sep=",", dec="."), "b.csv", M, set()

@trap("F03", "Tabbseparerad, decimalkomma", "Alla par korrekta")
def _(): return write_csv(long_df("B"), sep="\t"), "b.txt.csv", M, set()

@trap("F04", "Citattecken runt alla fält, kommaseparerad", "Alla par korrekta")
def _(): return write_csv(long_df("B"), sep=",", dec=".", quote=True), "b.csv", M, set()

@trap("F05", "UTF-8 med BOM (vanligt från Excel)", "Alla par korrekta")
def _(): return write_csv(long_df("B"), enc="utf-8-sig"), "b.csv", M, set()

@trap("F06", "Windows-1252 (µ i enhet)", "Läses korrekt eller tydligt fel")
def _(): return write_csv(long_df("B"), enc="cp1252"), "b.csv", M, set()

@trap("F07", "Tre metadatarader ovanför rubrikraden (instrumentexport)",
      "Rubrikraden hittas, eller tydligt fel")
def _():
    pre = "Instrument;cobas pro c 503\nExport;2026-09-15 07:12\n;\n"
    return write_csv(long_df("B"), pre=pre), "b.csv", M, set()

@trap("F08", "Mellanslag före/efter prov-ID", "Matchas som samma prov")
def _():
    d = long_df("B"); d["Provnummer"] = [f" {s} " if i % 3 == 0 else s + " "
                                         for i, s in enumerate(d["Provnummer"])]
    return write_csv(d), "b.csv", M, set()

@trap("F09", "Excel: prov-ID lagrat som tal (ledande nollor förlorade)",
      "Matchas mot textID med nollor")
def _():
    d = long_df("B"); d["Provnummer"] = d["Provnummer"].astype("int64")
    return write_xlsx(d), "b.xlsx", M, set()

@trap("F10", "Excel: prov-ID som flyttal (123.0, tom cell i kolumnen)",
      "Matchas; tom rad ignoreras")
def _():
    d = long_df("B"); d["Provnummer"] = d["Provnummer"].astype(float)
    d = pd.concat([d, pd.DataFrame([{"Provnummer": np.nan, "Analys": "CRP",
                                     "Resultat": 5.0, "Enhet": "mg/L"}])])
    return write_xlsx(d), "b.xlsx", M, set()

@trap("F11", "Excel: rubrikrad på rad 3 (titel ovanför)",
      "Rubrikraden hittas, eller tydligt fel")
def _(): return write_xlsx(long_df("B"), startrow=2, title="Resultatlista LIS"), "b.xlsx", M, set()

@trap("F12", "Kvalificerare '<0,6' och '>2000'", "Utesluts OCH redovisas")
def _():
    d = long_df("B").astype({"Resultat": object}); ex = set()
    for i in d.index[(d["Analys"] == "CRP")][:4]:
        d.at[i, "Resultat"] = "<0,6"; ex.add(("CRP", d.at[i, "Provnummer"]))
    for i in d.index[(d["Analys"] == "Ferritin")][:2]:
        d.at[i, "Resultat"] = ">2000"; ex.add(("Ferritin", d.at[i, "Provnummer"]))
    return write_csv(d), "b.csv", M, ex

@trap("F13", "Flagga i resultatfältet '12,3 H'", "Värdet läses, flaggan ignoreras")
def _():
    d = long_df("B").astype({"Resultat": object})
    for i in d.index[:10]:
        d.at[i, "Resultat"] = num_sv(d.at[i, "Resultat"], 2) + " H"
    return write_csv(d), "b.csv", M, set()

@trap("F14", "Tusentalsavgränsare '1 234,5' (mellanslag)", "Rätt värde läses")
def _():
    d = long_df("B").astype({"Resultat": object})
    for i in d.index:
        v = d.at[i, "Resultat"]
        if isinstance(v, float) and v >= 1000:
            d.at[i, "Resultat"] = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return write_csv(d), "b.csv", M, set()

@trap("F15", "Tusentalsavgränsare '1,234.50' i fil med decimalpunkt",
      "Rätt värde läses")
def _():
    d = long_df("B").astype({"Resultat": object})
    for i in d.index:
        v = d.at[i, "Resultat"]
        d.at[i, "Resultat"] = f"{v:,.2f}" if v >= 1000 else f"{v:.2f}"
    return write_csv(d, sep=";", dec="."), "b.csv", M, set()

@trap("F16", "Textresultat: 'Error', '---', 'NA', tomt", "Utesluts OCH redovisas")
def _():
    d = long_df("B").astype({"Resultat": object}); ex = set()
    for i, txt in zip(d.index[40:44], ["Error", "---", "NA", ""]):
        d.at[i, "Resultat"] = txt; ex.add((d.at[i, "Analys"], d.at[i, "Provnummer"]))
    return write_csv(d), "b.csv", M, ex

@trap("F17", "Omkörning: första raden 'Error', sista giltig (strategi: första)",
      "Giltigt värde används, eller tydlig varning")
def _():
    d = long_df("B").astype({"Resultat": object})
    extra = []
    for i in d.index[:3]:
        r = d.loc[i].copy(); r["Resultat"] = "Error"; extra.append(r)
    d = pd.concat([pd.DataFrame(extra), d], ignore_index=True)
    return write_csv(d), "b.csv", dict(M, dup="first_valid"), set()

@trap("F18", "Dubbletter med olika värden, strategi 'medelvärde'",
      "Medelvärdet används")
def _():
    d = long_df("B"); extra = []
    for i in d.index[:3]:
        r = d.loc[i].copy(); r["Resultat"] = r["Resultat"] + 2.0; extra.append(r)
    d = pd.concat([d, pd.DataFrame(extra)], ignore_index=True)
    return write_csv(d), "b.csv", dict(M, dup="mean", dup_shift=1.0), set()

@trap("F19", "QC-prov och okända prov endast i fil B", "Redovisas som 'Endast i B'")
def _():
    d = long_df("B")
    qc = pd.DataFrame([{"Provnummer": "QC_LOW", "Analys": "CRP", "Resultat": 5.1, "Enhet": "mg/L"},
                       {"Provnummer": "QC_HIGH", "Analys": "CRP", "Resultat": 98.0, "Enhet": "mg/L"}])
    return write_csv(pd.concat([d, qc])), "b.csv", M, set()

@trap("F20", "Olika analysnamn i filerna ('CRP4' mot 'CRP')", "Användaren kan koppla ihop")
def _():
    d = long_df("B", names={"CRP": "CRP4", "Kreatinin": "CREJ2", "Ferritin": "FERR4"})
    return write_csv(d), "b.csv", M, set()

@trap("F21", "Analyskolumn 'N/A' fast filen har tre analyser",
      "Stoppas eller varnas; får inte para fel analyser")
def _(): return write_csv(long_df("B")), "b.csv", dict(M, an="N/A", expect_stop=True), set()

@trap("F22", "Enhet i resultatfältet '12,3 mg/L'", "Värdet läses")
def _():
    d = long_df("B").astype({"Resultat": object})
    for i in d.index[:10]:
        d.at[i, "Resultat"] = num_sv(d.at[i, "Resultat"], 2) + " mg/L"
    return write_csv(d), "b.csv", M, set()

@trap("F23", "Tomma rader och kolumner i slutet", "Ignoreras")
def _():
    d = long_df("B"); d["Unnamed"] = ""
    b = write_csv(d) + b";;;;\n;;;;\n"
    return b, "b.csv", M, set()

@trap("F24", "Prov-ID i vetenskaplig notation från Excel (2,40915E+09)",
      "Upptäcks och varnas (ursprungligt ID går inte att återskapa)")
def _():
    d = long_df("B"); d["Provnummer"] = [f"{float(s):.5E}".replace(".", ",") for s in d["Provnummer"]]
    return write_csv(d), "b.csv", dict(M, expect_sci=True), {(an, s) for an in ANALYTES for s in ids}

@trap("F25", "Små bokstäver i alfanumeriska ID ('ab123' mot 'AB123')",
      "Matchas som samma prov")
def _():
    global FILE_A_ALNUM
    d = long_df("B"); d["Provnummer"] = ["ab" + s for s in d["Provnummer"]]
    return write_csv(d), "b.csv", dict(M, alnumA=True), set()

@trap("F26", "Alfanumeriska ID med mellanslag ('AB150103 ')", "Matchas som samma prov")
def _():
    d = long_df("B"); d["Provnummer"] = ["AB" + s + " " for s in d["Provnummer"]]
    return write_csv(d), "b.csv", dict(M, alnumA=True), set()

@trap("F27", "Tusental med komma utan decimaler '1,234' (decimalpunkt-fil)",
      "Rätt värde (1234) läses, ALDRIG 1,234")
def _():
    d = long_df("B").astype({"Resultat": object})
    for i in d.index:
        v = d.at[i, "Resultat"]
        d.at[i, "Resultat"] = f"{round(v):,}" if v >= 1000 else f"{v:.2f}"
    # facit måste följa den avrundning som filen innehåller
    return write_csv(d, sep=";", dec="."), "b.csv", dict(M, round_big=True), set()

@trap("F28", "Europeisk tusentalspunkt '1.234,50' (decimalkomma-fil)", "Rätt värde läses")
def _():
    d = long_df("B").astype({"Resultat": object})
    for i in d.index:
        v = d.at[i, "Resultat"]
        if v >= 1000:
            d.at[i, "Resultat"] = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return write_csv(d), "b.csv", M, set()

# ── Körning och poängsättning ──────────────────────────────────────────────
def norm_id(s):
    s = str(s).strip().upper()
    if s.startswith("AB") and s[2:].isdigit():          # alfanumeriska testfall
        s = s[2:]
    try:
        return f"{int(float(s.replace(',', '.'))):010d}" if s.replace(",", "").replace(".", "").replace("E+", "").isdigit() or "E+" in s else s
    except Exception:
        return s

def run(tid, title, expect, fn):
    from analysis.data_loader import MultipleResultsError, list_analytes
    from analysis.file_reader import suggest_analyte
    b, fname, mp, legit = fn()
    open(f"{OUT}/{tid}_{fname.replace('/', '_')}", "wb").write(b)
    fa = FILE_A
    if mp.get("alnumA"):
        da = long_df("A"); da["Provnummer"] = ["AB" + s for s in da["Provnummer"]]
        fa = write_csv(da)
    res = dict(id=tid, title=title, expect=expect, read_error=None, blocked=None,
               correct=0, wrong=0, missed=0, legit=len(legit), used=0, excluded=0,
               reasons={}, only_a=0, only_b=0, sci=0, note="")
    t0 = time.time()
    try:
        A = load_long_format(fa, "a.csv"); B = load_long_format(b, fname)
    except Exception as e:
        res["read_error"] = str(e)[:140]; res["sev"] = "MÅTTLIG"; return res
    miss = [c for c in (mp["id"], mp["res"]) + (() if mp["an"] == "N/A" else (mp["an"],))
            if c not in B.columns]
    if miss:
        res["blocked"] = f"Kolumn saknas i fil B: {miss}; läste {list(B.columns)[:4]}"
        res["sev"] = "MÅTTLIG"; return res
    an_col_b = None if mp["an"] == "N/A" else mp["an"]
    an_col_a = None if mp["an"] == "N/A" else mp["an"]
    if an_col_b is None:
        pairs = [(None, None)]
    else:
        la, lb = list_analytes(A, an_col_a), list_analytes(B, an_col_b)
        pairs = [(x, suggest_analyte(x, lb)[0]) for x in la]
        pairs = [(x, y) for x, y in pairs if y is not None]
        if not pairs:
            res["blocked"] = "Inga analyser kunde kopplas"; res["sev"] = "MÅTTLIG"; return res
    seen = set()
    for an_a, an_b in pairs:
        try:
            x, y, rep, sm = match_two_files(A, B, mp["id"], mp["id"], an_col_a, an_col_b,
                                            mp["res"], mp["res"], an_a, an_b,
                                            dup_strategy=mp.get("dup", "first_valid"))
        except MultipleResultsError as e:
            res["blocked"] = "Tydligt stopp: " + str(e)[:90]
            res["sev"] = "OK" if mp.get("expect_stop") else "MÅTTLIG"; return res
        except Exception as e:
            res["blocked"] = "Krasch: " + str(e)[:90]; res["sev"] = "MÅTTLIG"; return res
        res["used"] += sm["used"]; res["excluded"] += sm["excluded"]
        res["only_a"] += sm["only_a"]; res["only_b"] += sm["only_b"]
        res["sci"] += sm["sci_ids_b"]
        for k, v in sm["excluded_reasons"].items():
            res["reasons"][k] = res["reasons"].get(k, 0) + v
        m = rep[rep["Match"] == "Matched"]
        for sid, a_, b_ in zip(m["SampleID"], m.iloc[:, 2], m.iloc[:, 3]):
            if not (np.isfinite(a_) and np.isfinite(b_)):
                continue
            nid = norm_id(sid)
            hit = [k for k in ANALYTES if nid in truth[k] and abs(truth[k][nid][0] - a_) < 1e-6]
            an_true = hit[0] if hit else None
            exp_b = None
            if an_true:
                exp_b = truth[an_true][nid][1]
                if mp.get("round_big") and exp_b >= 1000:
                    exp_b = float(round(exp_b))
                if mp.get("dup_shift") and nid in ids[:3] and an_true == "CRP":
                    exp_b += mp["dup_shift"]
            if an_true and exp_b is not None and abs(exp_b - b_) < 1e-6:
                res["correct"] += 1; seen.add((an_true, nid))
            else:
                res["wrong"] += 1
    expected = {(an, s) for an in ANALYTES for s in ids} - {(a, norm_id(s)) for a, s in legit}
    res["missed"] = len(expected - seen)
    res["time_s"] = round(time.time() - t0, 3)
    reported_ok = (res["used"] == res["correct"] + res["wrong"])
    if res["wrong"] > 0:
        res["sev"] = "KRITISK"
    elif mp.get("expect_stop"):
        res["sev"] = "KRITISK"                               # borde ha stoppats
    elif mp.get("expect_sci"):
        res["sev"] = "OK" if res["sci"] > 0 else "ALLVARLIG"  # måste flaggas
    elif res["missed"] > 0:
        res["sev"] = "ALLVARLIG"
    elif not reported_ok or res["excluded"] != res["legit"]:
        res["sev"] = "BRIST"
    else:
        res["sev"] = "OK"
    return res

if __name__ == "__main__":
    out = [run(*t) for t in TRAPS]
    json.dump(out, open(f"{OUT}/resultat.json", "w"), ensure_ascii=False, indent=1, default=str)
    open(f"{OUT}/A_referens.csv", "wb").write(FILE_A)
    for r in out:
        tag = r["sev"]
        extra = r.get("read_error") or r.get("blocked") or ""
        print(f"{r['id']} {tag:9} rätt={r['correct']:3} fel={r['wrong']:3} saknas={r['missed']:3} "
              f"används={r['used']:3} uteslutna={r['excluded']:2}/{r['legit']:<3} "
              f"endastA/B={r['only_a']}/{r['only_b']}  {r['title'][:44]}  {extra[:55]} "
              f"{'; '.join(f'{k}×{v}' for k, v in r['reasons'].items())}")
