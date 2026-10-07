"""
Virtuella instrumentexporter för verifiering av filinläsning.

Efterliknar TYPISKA drag i exporter från Sysmex XN, Roche cobas och
LIS-pivottabeller. Inte leverantörernas faktiska format, som varierar med
konfiguration och programversion; egna exporter är det avgörande testet.

Varje fil skrivs från ett facit så att varje par kan kontrolleras.
"""
import io, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(20260922)
N = 30
IDS = [f"{12000 + i * 37:08d}" for i in range(N)]                  # t.ex. 00012037

# ── Facit: sant värde för instrument A (index 0) och B (index 1) ───────────
HEME = {  # namn: (min, max, decimaler)  — amerikanska enheter i XN-exporten
    "WBC": (2.0, 25.0, 2), "RBC": (3.0, 6.0, 2), "HGB": (8.0, 17.5, 1),
    "HCT": (25.0, 52.0, 1), "MCV": (72.0, 105.0, 1), "PLT": (40.0, 600.0, 0)}
CHEM = {"CRP": (0.4, 180.0, 1), "KREA": (45.0, 400.0, 0),
        "NA": (128.0, 150.0, 0), "K": (3.0, 5.8, 1)}
truth = {}
for grp in (HEME, CHEM):
    for an, (lo, hi, dp) in grp.items():
        a = np.round(rng.uniform(lo, hi, N), dp)
        b = np.round(a * rng.normal(1.01, 0.02, N) + rng.normal(0, (hi - lo) * 0.005, N), dp)
        truth[an] = {IDS[i]: (float(a[i]), float(b[i])) for i in range(N)}

# ── Sysmex XN, bred CSV: en rad per prov, en kolumn per parameter ──────────
XN_COLS = {"WBC": "WBC(10^3/uL)", "RBC": "RBC(10^6/uL)", "HGB": "HGB(g/dL)",
           "HCT": "HCT(%)", "MCV": "MCV(fL)", "PLT": "PLT(10^3/uL)"}
XN_MISSING = {(IDS[4], "PLT"): "----", (IDS[9], "WBC"): "----", (IDS[15], "PLT"): "++++"}

def sysmex_csv(side, name):
    head = ["Nickname", "Analyzer ID", "Date", "Time", "Rack", "Position", "Sample No.",
            "Sample Inf.", "Order Type", "Error(Func.)", "Error(Result)"]
    for an, col in XN_COLS.items():
        head += [col, f"{an}/M"]
    rows = [",".join(head)]
    def row(sid, t, vals, marks=""):
        r = [f"XN-{side}", f"XN-10^{side}", "2026/09/15", t, f"{1000 + len(rows)}", "1",
             f"{sid:>15}", "", "", "", ""]
        for an in XN_COLS:
            r += [vals[an], marks if an == "PLT" else ""]
        return ",".join(r)
    for k, sid in enumerate(IDS):
        vals = {}
        for an in XN_COLS:
            v = truth[an][sid][side]
            vals[an] = XN_MISSING.get((sid, an), f"{v:.{HEME[an][2]}f}")
        if k == 7:                                   # omkörning: första med fel
            bad = dict(vals); bad["HGB"] = "----"
            rows.append(row(sid, f"08:{k:02d}:00", bad, "*"))
        rows.append(row(sid, f"09:{k:02d}:00", vals))
    rows.append(row("QC-L1-XNCHECK", "07:55:00", {an: "1.00" for an in XN_COLS}))
    open(os.path.join(HERE, name), "w", encoding="utf-8").write("\n".join(rows) + "\n")

# ── Sysmex XN, bred Excel (andra instrumentet, samma rubriker) ──────────────
def sysmex_xlsx(side, name):
    recs = []
    for sid in IDS:
        r = {"Sample No.": sid, "Date": pd.Timestamp("2026-09-15"), "Rack": 2001, "Position": 3}
        for an, col in XN_COLS.items():
            r[col] = XN_MISSING.get((sid, an), truth[an][sid][side])
            r[f"{an}/M"] = ""
        recs.append(r)
    with pd.ExcelWriter(os.path.join(HERE, name), engine="openpyxl") as w:
        pd.DataFrame(recs).to_excel(w, sheet_name="XN Data", index=False)

# ── LIS-pivot, Excel: svenska NPU-namn, SI-enheter, tvåradig rubrik,
#    titel, summarader längst ned, ID som tal, text-tal i några celler ─────
LIS_HEME = {"WBC": ("B-LPK", "×10⁹/L", 1), "RBC": ("B-EPK", "×10¹²/L", 1),
            "HGB": ("B-Hb", "g/L", 10), "HCT": ("B-EVF", "", 0.01),
            "MCV": ("B-MCV", "fL", 1), "PLT": ("B-TPK", "×10⁹/L", 1)}
LIS_CHEM = {"CRP": ("P-CRP", "mg/L", 1), "KREA": ("P-Kreatinin", "µmol/L", 1),
            "NA": ("P-Natrium", "mmol/L", 1), "K": ("P-Kalium", "mmol/L", 1)}

def lis_pivot(side, name, spec):
    buf = []
    cols = ["Provnummer", "Provtagningsdatum"] + [v[0] for v in spec.values()]
    units = ["", ""] + [v[1] for v in spec.values()]
    body = []
    for k, sid in enumerate(IDS):
        r = [int(sid), pd.Timestamp("2026-09-15")]
        for an, (_, _, f) in spec.items():
            v = round(truth[an][sid][side] * f, 4)
            r.append(str(v).replace(".", ",") if k % 6 == 0 else v)   # tal lagrat som text
        body.append(r)
    means = ["Medelvärde", ""] + [round(float(np.mean([truth[an][s][side] * f for s in IDS])), 2)
                                   for an, (_, _, f) in spec.items()]
    sds = ["SD", ""] + [round(float(np.std([truth[an][s][side] * f for s in IDS])), 2)
                         for an, (_, _, f) in spec.items()]
    grid = ([["Resultatlista, LIS", ""] + [""] * len(spec), [""] * len(cols), cols, units]
            + body + [[""] * len(cols), means, sds])
    with pd.ExcelWriter(os.path.join(HERE, name), engine="openpyxl") as w:
        pd.DataFrame(grid).to_excel(w, sheet_name="Rapport", index=False, header=False)

# ── cobas, lång Excel med flera blad (info först, resultat, QC) ─────────────
COBAS = {"CRP": "CRP4", "KREA": "CREJ2", "NA": "NA", "K": "K"}
def cobas_xlsx(side, name):
    rows = []
    for sid in IDS:
        for an, code in COBAS.items():
            v = truth[an][sid][side]
            rows.append({"Sample ID": sid, "Test": code,
                         "Result": ("<0.30" if an == "CRP" and v < 0.6 else v),
                         "Unit": {"CRP": "mg/L", "KREA": "µmol/L", "NA": "mmol/L", "K": "mmol/L"}[an],
                         "Flag": "H" if an == "CRP" and v > 5 else ""})
    info = pd.DataFrame({"Fält": ["Instrument", "Programvara", "Exporterad"],
                         "Värde": ["cobas pro c 503", "04-01", "2026-09-15 07:12"]})
    qc = pd.DataFrame({"Control": ["PCCC1", "PCCC2"], "Test": ["CRP4", "CRP4"], "Result": [4.98, 49.2]})
    with pd.ExcelWriter(os.path.join(HERE, name), engine="openpyxl") as w:
        info.to_excel(w, sheet_name="Info", index=False)
        df = pd.DataFrame(rows)
        df.to_excel(w, sheet_name="Results", index=False, startrow=2)
        w.sheets["Results"].cell(row=1, column=1, value="cobas pro — Result list")
        qc.to_excel(w, sheet_name="QC", index=False)

# ── cobas, lång CSV (semikolon, decimalkomma, Windows-1252) ─────────────────
def cobas_csv(side, name):
    L = ["Instrument;cobas pro c 503", "Export;2026-09-15", "",
         "Sample ID;Test;Result;Unit;Flag"]
    for sid in IDS:
        for an, code in COBAS.items():
            v = truth[an][sid][side]
            txt = "<0,30" if (an == "CRP" and v < 0.6) else f"{v}".replace(".", ",")
            L.append(f"{sid};{code};{txt};{'µmol/L' if an == 'KREA' else 'mmol/L'};")
    open(os.path.join(HERE, name), "wb").write(("\n".join(L) + "\n").encode("cp1252"))

if __name__ == "__main__":
    sysmex_csv(0, "sysmex_xn_A.csv")
    sysmex_xlsx(1, "sysmex_xn_B.xlsx")
    lis_pivot(1, "lis_pivot_hematologi.xlsx", LIS_HEME)
    lis_pivot(1, "lis_pivot_kemi.xlsx", LIS_CHEM)
    cobas_xlsx(0, "cobas_c503_A.xlsx")
    cobas_csv(1, "cobas_c702_B.csv")
    print("skrivna:", sorted(f for f in os.listdir(HERE) if f.endswith((".csv", ".xlsx"))))
