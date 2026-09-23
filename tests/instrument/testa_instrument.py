"""
Helhetstest på virtuella instrumentexporter (Sysmex XN, cobas, LIS-pivot).

Programmets EGNA automatiska val används: filformat (långt/brett), kolumner,
Excel-blad och analyskoppling. Varje par kontrolleras mot facit.
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import numpy as np
import skapa_instrumentdata as G
from analysis.data_loader import load_long_format, list_analytes, match_two_files
from analysis.file_reader import guess_column, suggest_analyte, canonical_analyte
try:
    from analysis.file_reader import detect_layout, to_long, best_sheet
    NEW_API = True
except ImportError:
    NEW_API = False

CANON = {"LPK": "WBC", "EPK": "RBC", "HB": "HGB", "EVF": "HCT", "MCV": "MCV", "TPK": "PLT",
         "WBC": "WBC", "RBC": "RBC", "HGB": "HGB", "HCT": "HCT", "PLT": "PLT",
         "CRP": "CRP", "KREATININ": "KREA", "NATRIUM": "NA", "KALIUM": "K"}

def load(fname):
    raw = open(os.path.join(HERE, fname), "rb").read()
    sheet = best_sheet(raw, fname) if NEW_API else None
    df = load_long_format(raw, fname, sheet=sheet)
    info = {"sheet": df.attrs["read_info"].get("sheet"), "layout": "long"}
    if NEW_API:
        L = detect_layout(df)
        info["layout"] = L["layout"]
        if L["layout"] == "wide":
            df = to_long(df, L["id_col"], L["value_cols"])
            return df, dict(info, id=L["id_col"], an="Analysis", res="Result")
    cols = list(df.columns)
    return df, dict(info, id=guess_column(cols, "id"), an=guess_column(cols, "an"),
                    res=guess_column(cols, "res"))

def scenario(title, fa, side_a, fb, side_b, factor_b=None, expect_unit=None, legit=None):
    factor_b = factor_b or {}; expect_unit = expect_unit or {}; legit = legit or (lambda an, s: False)
    print(f"\n=== {title} ===")
    try:
        A, ca = load(fa); B, cb = load(fb)
    except Exception as e:
        print(f"  STOPP vid läsning: {str(e)[:90]}"); return 1
    print(f"  A: {ca['layout']}, blad={ca['sheet']}, kolumner {ca['id']}/{ca['an']}/{ca['res']}")
    print(f"  B: {cb['layout']}, blad={cb['sheet']}, kolumner {cb['id']}/{cb['an']}/{cb['res']}")
    if None in (ca["id"], ca["an"], ca["res"], cb["id"], cb["an"], cb["res"]):
        print("  STOPP: kolumnerna kunde inte identifieras"); return 1
    fails, n_an = 0, 0
    lb = list_analytes(B, cb["an"])
    for an_a in list_analytes(A, ca["an"]):
        key = CANON.get(canonical_analyte(an_a))
        if key is None:
            continue
        n_an += 1
        an_b, why = suggest_analyte(an_a, lb)
        if an_b is None or CANON.get(canonical_analyte(an_b)) != key:
            print(f"  {an_a:14} -> {an_b!s:14} FEL KOPPLING"); fails += 1; continue
        x, y, rep, sm = match_two_files(A, B, ca["id"], cb["id"], ca["an"], cb["an"],
                                        ca["res"], cb["res"], an_a, an_b)
        f = factor_b.get(key, 1.0)
        m = rep[rep["Match"] == "Matched"]; correct = wrong = 0; got = set()
        for sid, va, vb in zip(m["SampleID"], m.iloc[:, 2], m.iloc[:, 3]):
            if not (np.isfinite(va) and np.isfinite(vb)):
                continue
            s_ = str(sid).strip()
            nid = f"{int(float(s_)):08d}" if s_.replace(".", "").isdigit() else s_
            t = G.truth[key].get(nid)
            if t and abs(t[side_a] - va) < 1e-6 and abs(round(t[side_b] * f, 4) - vb) < 1e-6:
                correct += 1; got.add(nid)
            else:
                wrong += 1
        expect = {s for s in G.IDS if not legit(key, s)}
        missed = len(expect - got)
        uf = sm.get("unit_factor")
        unit_ok = (uf == expect_unit.get(key)) if key in expect_unit else uf in (None, 1)
        ok = wrong == 0 and missed == 0 and unit_ok
        fails += not ok
        print(f"  {an_a:14} -> {an_b:14} [{why:10}] rätt {correct:2}/{len(expect):2} fel {wrong} "
              f"saknas {missed:2} uteslutna {sm['excluded']:2} enhetsfaktor {uf!s:5} "
              f"{'GODKÄND' if ok else 'UNDERKÄND'}")
    if n_an == 0:
        print("  STOPP: inga analyser hittades"); return 1
    return fails

def run_all():
    G.sysmex_csv(0, "sysmex_xn_A.csv"); G.sysmex_xlsx(1, "sysmex_xn_B.xlsx")
    G.lis_pivot(1, "lis_pivot_hematologi.xlsx", G.LIS_HEME); G.lis_pivot(1, "lis_pivot_kemi.xlsx", G.LIS_CHEM)
    G.cobas_xlsx(0, "cobas_c503_A.xlsx"); G.cobas_csv(1, "cobas_c702_B.csv")
    xn_missing = lambda an, s: (s, an) in G.XN_MISSING
    crp_low = lambda an, s: an == "CRP" and (G.truth["CRP"][s][0] < 0.6 or G.truth["CRP"][s][1] < 0.6)
    F = 0
    F += scenario("H1 Sysmex XN CSV  mot  Sysmex XN Excel (brett/brett)",
                  "sysmex_xn_A.csv", 0, "sysmex_xn_B.xlsx", 1, legit=xn_missing)
    F += scenario("H2 Sysmex XN CSV (US-enheter)  mot  LIS-pivot Excel (NPU, SI-enheter)",
                  "sysmex_xn_A.csv", 0, "lis_pivot_hematologi.xlsx", 1,
                  factor_b={k: v[2] for k, v in G.LIS_HEME.items()},
                  expect_unit={"HGB": 10, "HCT": 0.01}, legit=xn_missing)
    F += scenario("C1 cobas Excel (3 blad, långt)  mot  cobas CSV (långt)",
                  "cobas_c503_A.xlsx", 0, "cobas_c702_B.csv", 1, legit=crp_low)
    F += scenario("C2 cobas Excel (långt)  mot  LIS-pivot kemi (brett)",
                  "cobas_c503_A.xlsx", 0, "lis_pivot_kemi.xlsx", 1,
                  legit=lambda an, s: an == "CRP" and G.truth["CRP"][s][0] < 0.6)
    return F

if __name__ == "__main__":
    F = run_all()
    print(f"\n{'ALLA GODKÄNDA' if F == 0 else f'{F} UNDERKÄNDA'}")
    sys.exit(1 if F else 0)
