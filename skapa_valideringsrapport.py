"""
Kör valideringssviten och skapar Valideringsrapport.docx.

Kör från programmappen:      python skapa_valideringsrapport.py

Rapporten innehåller de faktiska värden som beräknades vid körningen,
inte förskrivna siffror. Kör om den efter varje kodändring.
"""
import sys, os, json, subprocess, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from scipy.stats import norm

from version import VERSION, VALIDATED_ON
from analysis.regression import passing_bablok
from analysis.deming import deming
from analysis.statistics import summary_stats
from analysis.precision import compute_precision
from analysis.confusion import categorical_agreement

results = []          # (område, storhet, referens, beräknat, tolerans, utfall)


def check(area, name, got, ref, tol, ref_src):
    ok = abs(float(got) - float(ref)) <= tol
    results.append(dict(area=area, name=name, ref=ref, got=float(got),
                        tol=tol, ok=ok, src=ref_src))
    return ok


# ── 1. Bland–Altman: Bland & Altman, Lancet 1986 (PEFR, n=17) ───────────────
lg = np.array([494,395,516,434,476,557,413,442,650,433,417,656,267,478,178,423,427], float)
mn = np.array([512,430,520,428,500,600,364,380,658,445,432,626,260,477,259,350,451], float)
s = summary_stats(mn, lg)
SRC1 = "Bland & Altman, Lancet 1986;327:307-310"
check("Bland-Altman", "Medelskillnad (L/min)",      s["mean_diff"], -2.1,  0.05, SRC1)
check("Bland-Altman", "SD för skillnader (L/min)",  s["std_diff"],  38.8,  0.05, SRC1)
check("Bland-Altman", "Nedre överensstämmelsegräns", s["loa_lower"], -78.1, 0.1, SRC1)
check("Bland-Altman", "Övre överensstämmelsegräns",  s["loa_upper"],  73.9, 0.1, SRC1)

# ── 2. Precision: Chesher 2008 / CLSI EP15-A3 (kalcium, 5 dagar × 3) ────────
d = {"Dag 1": [2.015, 2.013, 1.963], "Dag 2": [2.019, 2.002, 1.979],
     "Dag 3": [2.025, 1.959, 2.000], "Dag 4": [1.972, 1.950, 1.973],
     "Dag 5": [1.981, 1.956, 1.957]}
r = compute_precision(d, alpha=0.05, n_levels=2, claimed_sr=0.022, claimed_sl=0.024)
SRC2 = "Chesher D, Clin Biochem Rev 2008;29(Suppl i):S23-S26"
check("Precision", "Repeterbarhet Sr (mmol/L)",   r["sr"],          0.023,    0.0005, SRC2)
check("Precision", "Total imprecision Sl (mmol/L)", r["sl"],        0.026,    0.0005, SRC2)
check("Precision", "Medelvärde (mmol/L)",          r["grand_mean"], 1.984,    0.001,  SRC2)
check("Precision", "Varians dagmedelvärden",       r["s_day2"],     0.000318, 1e-6,   SRC2)
check("Precision", "Frihetsgrader inom serie",     r["df_within"],  10,       0,      SRC2)
check("Precision", "Effektiva frihetsgrader T",    r["T"],          12.1,     0.05,   SRC2)
check("Precision", "Chi-två kritiskt värde",       r["chi2_crit_r"],20.48,    0.01,   SRC2)
check("Precision", "Verifieringsvärde Sr",         r["verif_sr"],   0.031,    0.0005, SRC2)

# ── 3. Deming mot ortogonal regression (SVD) ────────────────────────────────
rng = np.random.default_rng(11)
worst = 0.0
for _ in range(50):
    n = int(rng.integers(15, 60))
    x = rng.uniform(1, 100, n); y = 1.1 * x + 3 + rng.normal(0, 5, n)
    A = np.column_stack([x - x.mean(), y - y.mean()])
    *_, Vt = np.linalg.svd(A)
    worst = max(worst, abs(deming(x, y, error_ratio=1.0)["slope"] - (-Vt[-1][0] / Vt[-1][1])))
check("Deming", "Största avvikelse mot SVD, lutning (50 dataset)",
      worst, 0.0, 1e-10, "Total least squares via singulärvärdesuppdelning")

# ── 3b. Deming mot publicerat facit (NCSS kap. 303 ex. 5/6 = R mcr) ─────────
from analysis.deming import weighted_deming
Xn = np.array([7, 8.3, 10.5, 9, 5.1, 8.2, 10.2, 10.3, 7.1, 5.9])
Yn = np.array([7.9, 8.2, 9.6, 9, 6.5, 7.3, 10.2, 10.6, 6.3, 5.2])
SRC3b = "NCSS kap. 303 ex. 5-6 (identiskt med R-paketet mcr)"
dm = deming(Xn, Yn, error_ratio=0.25)          # NCSS lambda 4 = appens 0.25
check("Deming", "Lutning, NCSS ex. 5",             dm["slope"],           1.0011942, 5e-8, SRC3b)
check("Deming", "Lutning nedre KI, NCSS ex. 5",    dm["slope_lower"],     0.5695632, 5e-8, SRC3b)
check("Deming", "Lutning övre KI, NCSS ex. 5",     dm["slope_upper"],     1.4328253, 5e-8, SRC3b)
check("Deming", "Intercept, NCSS ex. 5",           dm["intercept"],      -0.0897449, 5e-8, SRC3b)
wd = weighted_deming(Xn, Yn, error_ratio=0.25)
check("Deming", "Viktad lutning, NCSS ex. 6",      wd["slope"],           1.0312280, 5e-8, SRC3b)
check("Deming", "Viktad lutning nedre KI, ex. 6",  wd["slope_lower"],     0.5234374, 5e-8, SRC3b)
check("Deming", "Viktad lutning övre KI, ex. 6",   wd["slope_upper"],     1.5390186, 5e-8, SRC3b)
check("Deming", "Viktat intercept, NCSS ex. 6",    wd["intercept"],      -0.3283761, 5e-8, SRC3b)

# ── 3c. Fyrfältstabell mot FDA 2007 (öppen källa) ───────────────────────────
from analysis.fourfold import fourfold
SRC3c = "FDA 2007, Statistical Guidance ... Diagnostic Tests, tabell 2 och 4"
f2 = fourfold(tp=44, fp=1, fn=7, tn=168, mode="reference")
check("Fyrfältstabell", "Sensitivitet 44/51 (%)",  f2["ppa"], 86.3, 0.05, SRC3c)
check("Fyrfältstabell", "Sensitivitet nedre KI",   f2["ppa_ci"][0], 74.3, 0.05, SRC3c)
check("Fyrfältstabell", "Sensitivitet övre KI",    f2["ppa_ci"][1], 93.2, 0.05, SRC3c)
check("Fyrfältstabell", "Specificitet 168/169 (%)", f2["npa"], 99.4, 0.05, SRC3c)
check("Fyrfältstabell", "Specificitet nedre KI",   f2["npa_ci"][0], 96.7, 0.05, SRC3c)
check("Fyrfältstabell", "Specificitet övre KI",    f2["npa_ci"][1], 99.9, 0.05, SRC3c)
f4 = fourfold(tp=40, fp=5, fn=4, tn=171, mode="agreement")
check("Fyrfältstabell", "PPA 40/44 (%)",           f4["ppa"], 90.9, 0.05, SRC3c)
check("Fyrfältstabell", "PPA KI nedre/övre",       f4["ppa_ci"][0], 78.8, 0.05, SRC3c)
check("Fyrfältstabell", "PPA KI övre",             f4["ppa_ci"][1], 96.4, 0.05, SRC3c)
check("Fyrfältstabell", "NPA 171/176 (%)",         f4["npa"], 97.2, 0.05, SRC3c)
check("Fyrfältstabell", "NPA KI nedre",            f4["npa_ci"][0], 93.5, 0.05, SRC3c)
check("Fyrfältstabell", "NPA KI övre",             f4["npa_ci"][1], 98.8, 0.05, SRC3c)
check("Fyrfältstabell", "OPA 211/220 (%)",         f4["opa"], 95.9, 0.05, SRC3c)
check("Fyrfältstabell", "OPA KI nedre",            f4["opa_ci"][0], 92.4, 0.05, SRC3c)
check("Fyrfältstabell", "OPA KI övre",             f4["opa_ci"][1], 97.8, 0.05, SRC3c)

# ── 4. Passing–Bablok mot oberoende implementation ─────────────────────────
def pb_ref(x, y, ci=0.95, L=1e6):
    x = np.asarray(x, float); y = np.asarray(y, float); n = len(x); S = []
    for i in range(n):
        for j in range(i + 1, n):
            dx = x[j] - x[i]; dy = y[j] - y[i]
            if dx == 0 and dy == 0:  continue
            s_ = (L if dy > 0 else -L) if dx == 0 else dy / dx
            if s_ == -1:             continue
            S.append(s_)
    S = np.sort(np.array(S)); N = len(S); k = int((S < -1).sum())
    at = lambda q: S[max(0, min(q, N - 1))]
    b = at((N - 1) // 2 + k) if N % 2 else 0.5 * (at(N // 2 - 1 + k) + at(N // 2 + k))
    z = norm.ppf(1 - (1 - ci) / 2); c = z * np.sqrt(n * (n - 1) * (2 * n + 5) / 18)
    m1 = int(round((N - c) / 2)); m2 = N - m1 + 1
    return b, float(np.median(y - b * x)), at(m1 + k - 1), at(m2 + k - 1)

w = [0.0] * 4
for t in range(80):
    n = int(rng.integers(12, 45))
    x = rng.uniform(5, 100, n); y = 1.05 * x + 2 + rng.normal(0, 4, n)
    if t % 7 == 0:  x[1] = x[0]; y[1] = y[0] + 3      # bundna x-värden
    if t % 11 == 0: x[2] = x[3]; y[2] = y[3]          # identiska punkter
    a1 = passing_bablok(x, y); rb, ra, rl, ru = pb_ref(x, y)
    for i, (p, q) in enumerate([(a1["slope"], rb), (a1["intercept"], ra),
                                (a1["slope_lower"], rl), (a1["slope_upper"], ru)]):
        w[i] = max(w[i], abs(p - q))
SRC4 = "Passing & Bablok, J Clin Chem Clin Biochem 1983;21:709-720"
for nm, v in zip(["lutning", "intercept", "KI nedre", "KI övre"], w):
    check("Passing-Bablok", f"Största avvikelse {nm} (80 dataset)", v, 0.0, 1e-12, SRC4)

# ── 5. Konfusionsmatris ─────────────────────────────────────────────────────
xc = np.array([25,22,10,12,25,10,18,25,10,18], float)
yc = np.array([26,21,11,25,10,12,18,24,11,25], float)
ca = categorical_agreement(xc, yc, 20, 16, 20, 16)
SRC5 = "CLSI M52 / EUCAST; handberäknat referensexempel"
check("Konfusionsmatris", "Kategoriöverensstämmelse (%)", ca["ca"],  70.0, 1e-9, SRC5)
check("Konfusionsmatris", "VME (%) - 1 av 4 R-isolat",    ca["vme"], 25.0, 1e-9, SRC5)
check("Konfusionsmatris", "ME (%) - 1 av 4 S-isolat",     ca["me"],  25.0, 1e-9, SRC5)
c2 = categorical_agreement(np.array([10., 10.]), np.array([25., 25.]), 20, 16, 20, 16)
check("Konfusionsmatris", "Riktning: referens R -> kandidat S ger VME",
      c2["n_vme"], 2, 0, SRC5)
c3 = categorical_agreement(np.array([25., 25.]), np.array([10., 10.]), 20, 16, 20, 16)
check("Konfusionsmatris", "Riktning: referens S -> kandidat R ger ME",
      c3["n_me"], 2, 0, SRC5)

# ── 6. Enhetstester ─────────────────────────────────────────────────────────
try:
    p = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                       capture_output=True, text=True, timeout=300)
    unit_line = [l for l in p.stdout.splitlines() if "passed" in l or "failed" in l]
    unit = unit_line[-1].strip() if unit_line else "kunde inte köras"
    unit_ok = p.returncode == 0
except Exception as e:
    unit, unit_ok = f"kunde inte köras ({e})", False

n_ok = sum(1 for x in results if x["ok"])
n_all = len(results)
all_ok = (n_ok == n_all) and unit_ok

print(f"\n{'OMRÅDE':18}{'STORHET':44}{'BERÄKNAT':>14}{'REFERENS':>12}  UTFALL")
print("-" * 100)
for x in results:
    print(f"{x['area']:18}{x['name']:44}{x['got']:>14.6g}{x['ref']:>12}  "
          f"{'GODKÄND' if x['ok'] else 'UNDERKÄND'}")
print("-" * 100)
print(f"{n_ok}/{n_all} godkända. Enhetstester: {unit}")
print(f"SAMLAT UTFALL: {'GODKÄND' if all_ok else 'UNDERKÄND'}\n")

json.dump(dict(version=VERSION, validated_on=VALIDATED_ON,
               run_at=datetime.datetime.now().isoformat(timespec="seconds"),
               python=sys.version.split()[0],
               n_ok=n_ok, n_all=n_all, unit=unit, all_ok=all_ok,
               results=results),
          open("valideringsresultat.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("Resultat sparade i valideringsresultat.json")
sys.exit(0 if all_ok else 1)
