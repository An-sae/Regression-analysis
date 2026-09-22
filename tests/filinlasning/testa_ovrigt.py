"""
Övriga verifieringar av dataflödet.

 P  Precision ur långt format: tidsstämplar, ojämnt antal replikat, midnatt
 R  Rundtur: nedladdad Excel med matchade par läses in igen -> samma par
 S  Skala: 20 000 prov × 3 analyser per fil (60 000 rader)
 U  Uteslutning av punkter: rätt punkt bort, statistik räknas om korrekt
"""
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.abspath(_os.path.join(_HERE, "..", ".."))
import sys, io, time, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, _ROOT)
import numpy as np, pandas as pd
from analysis.data_loader import (load_long_format, match_two_files,
                                  extract_precision_replicates, build_matched_excel)
from analysis.precision import compute_precision
from analysis.regression import passing_bablok

fails = 0
def check(name, cond, detail=""):
    global fails
    fails += not cond
    print(f"  {'OK ' if cond else 'FEL'} {name}{('  — ' + str(detail)) if detail and not cond else ''}")

# ── P: precision ur instrumentexport ────────────────────────────────────────
print("P) Precision ur långt format (Roche-lik export, kontrollmaterial PCCC1)")
rng = np.random.default_rng(3)
truth_days = {}
lines = ["Instrument;cobas pro c 503", "Export;2026-09-20", "",
         "Sample ID;Test;Result;Unit;Result Date/Time"]
plan = [("2026-09-15", ["08:01", "10:15", "13:30", "16:45", "23:58"]),   # sista 2 min före midnatt
        ("2026-09-16", ["00:03", "09:00", "12:00", "15:00", "18:00"]),   # första 3 min efter
        ("2026-09-17", ["07:30", "11:30", "14:30", "17:30", "20:30"]),
        ("2026-09-18", ["08:00", "12:00", "16:00", "20:00"]),             # bara 4 replikat
        ("2026-09-19", ["06:00", "09:00", "12:00", "15:00", "18:00"])]
for d, times in plan:
    vals = list(np.round(rng.normal(4.98, 0.08, len(times)) + rng.normal(0, 0.05), 2))
    truth_days[d] = vals
    for tm, v in zip(times, vals):
        lines.append(f"PCCC1;CRP4;{str(v).replace('.', ',')};mg/L;{d} {tm}")
        lines.append(f"PCCC1;CREJ2;{str(round(v * 17, 1)).replace('.', ',')};µmol/L;{d} {tm}")  # annan analys
        lines.append(f"2409{rng.integers(100000, 999999)};CRP4;12,3;mg/L;{d} {tm}")          # patientprov
raw = ("\n".join(lines) + "\n").encode("cp1252")
df = load_long_format(raw, "precision.csv")
dd, sub, left = extract_precision_replicates(df, "Sample ID", "Result", "PCCC1",
                                             sort_col="Result Date/Time", analysis_col="Test",
                                             analyte="CRP4", group_col="Result Date/Time")
check("fem dagar bildas (23:58 och 00:03 hamnar på rätt dag)", len(dd) == 5, list(dd))
check("balanserad design: 5 dagar × 4 (EP15 kräver lika många per dag)",
      [len(v) for v in dd.values()] == [4, 4, 4, 4, 4], [len(v) for v in dd.values()])
check("4 resultat redovisas som ej använda (inte tyst borta)", left == 4, left)
check("rätt rader markerade: de senaste per dag", int((~sub["Used"]).sum()) == 4
      and set(sub.loc[~sub["Used"], "Result Date/Time"].dt.strftime("%H:%M")) == {"23:58", "18:00", "20:30"})
exp = compute_precision({k: v[:4] for k, v in truth_days.items()})
got = compute_precision(dd)
check("Sr identisk med facit", abs(got["sr"] - exp["sr"]) < 1e-12, (got["sr"], exp["sr"]))
check("Sl identisk med facit", abs(got["sl"] - exp["sl"]) < 1e-12, (got["sl"], exp["sl"]))
check("endast CRP4 och endast PCCC1 läses (24 rader)", len(sub) == 24, len(sub))

# ── R: rundtur via nedladdad Excel ──────────────────────────────────────────
print("\nR) Rundtur: matchade par -> Excel -> inläsning")
D = _HERE + "/"
A = load_long_format(open(D + "roche_cobas_lik.csv", "rb").read(), "roche_cobas_lik.csv")
B = load_long_format(open(D + "abbott_alinity_lik.csv", "rb").read(), "abbott_alinity_lik.csv")
x, y, rep, sm = match_two_files(A, B, "Sample ID", "SID", "Test", "Assay", "Result", "Result",
                                "FERR4", "Ferritin", "Roche", "Abbott")
rep2 = rep.copy(); rep2["Status"] = ""
xl = build_matched_excel(rep2, "Roche", "Abbott", "FERR4 ↔ Ferritin")
back = load_long_format(xl, "matched.xlsx", sheet="Matched pairs")
bx = pd.to_numeric(back["Roche"], errors="coerce").values
by = pd.to_numeric(back["Abbott"], errors="coerce").values
ok = np.isfinite(bx) & np.isfinite(by)
check("alla använda par återfinns", ok.sum() == len(x), (ok.sum(), len(x)))
check("värdena identiska", np.allclose(np.sort(bx[ok]), np.sort(x)) and np.allclose(np.sort(by[ok]), np.sort(y)))
check("uteslutet par finns med och har orsak", (back["Note"].astype(str).str.contains("text result")).sum() == 1)
check("originaltext bevarad ('Error')", (back["Original B"].astype(str) == "Error").sum() == 1)

# ── S: skala ────────────────────────────────────────────────────────────────
print("\nS) Skala: 60 000 rader per fil")
n = 20000
ids = [f"{2400000000 + i}" for i in range(n)]
vals = np.round(rng.lognormal(3, 1, n), 2)
def big(sep, dec, jitter):
    rows = ["Sample ID;Test;Result".replace(";", sep)]
    for an, f in (("CRP", 1), ("KREA", 17), ("FERR", 9)):
        for i, v in zip(ids, vals * f * jitter):
            s = f"{v:.2f}".replace(".", dec)
            rows.append(sep.join([i, an, s]))
    return ("\n".join(rows) + "\n").encode()
t0 = time.time()
A = load_long_format(big(";", ",", 1.0), "a.csv"); B = load_long_format(big(",", ".", 1.02), "b.csv")
t1 = time.time()
x, y, rep, sm = match_two_files(A, B, "Sample ID", "Sample ID", "Test", "Test", "Result", "Result", "FERR", "FERR")
t2 = time.time()
check(f"läsning {t1 - t0:.1f} s, matchning {t2 - t1:.1f} s (< 60 s totalt)", (t2 - t0) < 60)
exp_x = np.array([float(f"{v:.2f}") for v in vals * 9])          # samma avrundning som filen
exp_y = np.array([float(f"{v:.2f}") for v in vals * 9 * 1.02])
check("20 000 par, alla 40 000 värden exakt rätt",
      len(x) == n and np.abs(x - exp_x).max() == 0 and np.abs(y - exp_y).max() == 0)

# ── U: uteslutning av punkter via gränssnittet ──────────────────────────────
print("\nU) Uteslutning av punkter (klistrade data, Passing–Bablok)")
from streamlit.testing.v1 import AppTest
xs = np.round(np.linspace(10, 200, 25), 1); ys = np.round(xs * 1.05 + rng.normal(0, 3, 25), 1)
ys[7] = ys[7] + 60                                          # tydlig avvikare
paste = "\n".join(f"{a}\t{b}".replace(".", ",") for a, b in zip(xs, ys))
at = AppTest.from_file(_os.path.join(_ROOT, "app.py"), default_timeout=180)
at.session_state["_lang"] = "sv"; at.run()
at.radio(key="imode").set_value("📋 Paste data").run()
at.text_area(key="pa").input(paste).run()
at.slider(key="dec").set_value(6).run()                  # 6 decimaler i tabellen
[b.click().run() for b in at.button if "Analy" in (b.label or "")][:1]
def slope_shown(at):
    for d in at.dataframe:
        v = d.value
        if v.shape[1] >= 2 and v.iloc[:, 0].astype(str).str.contains("Lutning|Slope").any():
            r = v[v.iloc[:, 0].astype(str).str.contains("Lutning|Slope")].iloc[0, 1]
            return float(str(r).replace(",", ".").replace("−", "-"))
    return None
s_all = slope_shown(at)
check("lutning med alla punkter = passing_bablok", s_all is not None and
      abs(s_all - passing_bablok(xs, ys)["slope"]) < 5e-6, (s_all, passing_bablok(xs, ys)["slope"]))
at.multiselect(key="excl_multi").set_value([7]).run()
s_ex = slope_shown(at)
keep = np.ones(25, bool); keep[7] = False
ref = passing_bablok(xs[keep], ys[keep])["slope"]
check("punkt 8 utesluten -> lutning räknas om korrekt", s_ex is not None and abs(s_ex - ref) < 5e-6, (s_ex, ref))
check("inga undantag", len(at.exception) == 0, [e.value for e in at.exception])
at.button(key="restore_all").click().run()
check("återställ -> tillbaka till alla punkter", abs(slope_shown(at) - s_all) < 1e-9)

print(f"\n{'ALLA GODKÄNDA' if fails == 0 else f'{fails} FEL'}")
