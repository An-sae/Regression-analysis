"""Översikten ska ge EXAKT samma resultat som varje analys vald enskilt."""
import os, sys, io, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import numpy as np, openpyxl
import testa_instrument as TI
from analysis.overview import suggested_pairs, compare_all, build_overview_excel
from analysis.data_loader import match_two_files
from analysis.regression import passing_bablok
from analysis.deming import deming, weighted_deming
from analysis.statistics import summary_stats

fails = 0
def check(name, ok, detail=""):
    global fails; fails += not ok
    print(f"  {'OK ' if ok else 'FEL'} {name}" + (f"  — {detail}" if not ok else ""))

TI.run_all.__globals__["G"].sysmex_csv(0, "sysmex_xn_A.csv")   # säkerställ filerna
TI.G.lis_pivot(1, "lis_pivot_hematologi.xlsx", TI.G.LIS_HEME)
TI.G.cobas_xlsx(0, "cobas_c503_A.xlsx"); TI.G.lis_pivot(1, "lis_pivot_kemi.xlsx", TI.G.LIS_CHEM)

for title, fa, fb in [("Sysmex XN mot LIS hematologi", "sysmex_xn_A.csv", "lis_pivot_hematologi.xlsx"),
                      ("cobas mot LIS kemi", "cobas_c503_A.xlsx", "lis_pivot_kemi.xlsx")]:
    print(f"\n{title}")
    A, ca = TI.load(fa); B, cb = TI.load(fb)
    pairs = suggested_pairs(A, ca["an"], B, cb["an"])
    check(f"alla analyser föreslås ({len(pairs)})", len(pairs) == (6 if "Sysmex" in title else 4))
    for method, kw in (("Passing–Bablok", {}), ("Deming", {"error_ratio": 1.0}),
                       ("Deming", {"error_ratio": 1.0, "weighted": True})):
        ov, det = compare_all(A, B, ca["id"], cb["id"], ca["an"], cb["an"], ca["res"], cb["res"],
                              pairs, method=method, **kw)
        worst = 0.0
        for _, r in ov.iterrows():
            x, y, _, _ = match_two_files(A, B, ca["id"], cb["id"], ca["an"], cb["an"],
                                         ca["res"], cb["res"], r["Analysis A"], r["Analysis B"])
            ref = (passing_bablok(x, y) if method == "Passing–Bablok" else
                   weighted_deming(x, y, 1.0) if kw.get("weighted") else deming(x, y, 1.0))
            st = summary_stats(x, y)
            for got, exp in ((r["Slope"], ref["slope"]), (r["Intercept"], ref["intercept"]),
                             (r["Slope 95% CI"][0], ref["slope_lower"]), (r["Slope 95% CI"][1], ref["slope_upper"]),
                             (r["Mean bias"], st["mean_diff"]), (r["r"], st["pearson_r"])):
                worst = max(worst, abs(got - exp))
        name = method + (" viktad" if kw.get("weighted") else "")
        check(f"{name:22} identisk med enskild analys (största skillnad {worst:.0e})", worst == 0.0)
    warn = ov[ov["Note"].str.contains("unit difference")]["Analysis A"].tolist()
    if "Sysmex" in title:
        check(f"enhetsvarning för HGB och HCT: {warn}", sorted(warn) == ["HCT(%)", "HGB(g/dL)"])
    xl = build_overview_excel(ov, det, stamp="test")
    wb = openpyxl.load_workbook(io.BytesIO(xl))
    check(f"Excel: översikt + {len(det)} analysflikar", len(wb.sheetnames) == len(det) + 1, wb.sheetnames)

print("\nALLA GODKÄNDA" if not fails else f"\n{fails} FEL")
sys.exit(1 if fails else 0)
