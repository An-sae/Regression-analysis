"""
Helhetstest: två flera-analys-exporter in, programmets EGNA förslag för
kolumner och analyskoppling används utan manuell korrigering, varje par
kontrolleras mot facit.
"""
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.abspath(_os.path.join(_HERE, "..", ".."))
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, _ROOT); sys.path.insert(0, _HERE)
import numpy as np
import testa_filinlasning as T
from analysis.data_loader import load_long_format, list_analytes, match_two_files
from analysis.file_reader import guess_column, suggest_analyte, canonical_analyte

F = {"Roche (cobas-lik)": ("roche_cobas_lik.csv", 0),      # 0 = metod A-värden i facit
     "Abbott (Alinity-lik)": ("abbott_alinity_lik.csv", 1),
     "LIS (Excel)": ("lis_export_lik.xlsx", 0)}

def legit_excluded(name, an, sid):
    """Vilka par ska uteslutas enligt hur exportfilerna byggdes?"""
    if name.startswith("Roche") and an == "CRP" and T.truth["CRP"][sid][0] < 0.6:
        return "under mätområde"
    if name.startswith("Abbott") and an == "Ferritin" and sid == T.ids[9]:
        return "Error"
    return None

total_fail = 0
for na, nb in [("Roche (cobas-lik)", "Abbott (Alinity-lik)"),
               ("Roche (cobas-lik)", "LIS (Excel)"),
               ("Abbott (Alinity-lik)", "LIS (Excel)")]:
    fa, ia = F[na]; fb, ib = F[nb]
    A = load_long_format(open(f"{_HERE}/{fa}", "rb").read(), fa)
    B = load_long_format(open(f"{_HERE}/{fb}", "rb").read(), fb)
    cA = {k: guess_column(list(A.columns), k) for k in ("id", "an", "res")}
    cB = {k: guess_column(list(B.columns), k) for k in ("id", "an", "res")}
    print(f"\n=== {na}  mot  {nb} ===")
    print(f"  lästes: A {A.attrs['read_info']['encoding']}, rubrik rad {A.attrs['read_info']['header_row']}"
          f" | B {B.attrs['read_info']['encoding']}, rubrik rad {B.attrs['read_info']['header_row']}")
    print(f"  kolumnförslag A {cA}  B {cB}")
    lb = list_analytes(B, cB["an"])
    for an_a in list_analytes(A, cA["an"]):
        an_b, why = suggest_analyte(an_a, lb)
        if an_b is None:
            print(f"  {an_a:12} -> (inget förslag)"); continue
        x, y, rep, sm = match_two_files(A, B, cA["id"], cB["id"], cA["an"], cB["an"],
                                        cA["res"], cB["res"], an_a, an_b)
        canon = canonical_analyte(an_a)
        truth_an = {"CRP": "CRP", "KREATININ": "Kreatinin", "FERRITIN": "Ferritin"}.get(canon)
        if truth_an is None:                   # QC-rad eller liknande
            print(f"  {an_a:12} -> {an_b:10} (ingen analys i facit)"); continue
        m = rep[rep["Match"] == "Matched"]
        correct = wrong = 0; used_ids = set()
        for sid, va, vb in zip(m["SampleID"], m.iloc[:, 2], m.iloc[:, 3]):
            if not (np.isfinite(va) and np.isfinite(vb)):
                continue
            nid = T.norm_id(sid); t = T.truth[truth_an].get(nid)
            if t and abs(t[ia] - va) < 1e-6 and abs(t[ib] - vb) < 1e-6:
                correct += 1; used_ids.add(nid)
            else:
                wrong += 1
        expect = {s for s in T.ids if not (legit_excluded(na, truth_an, s) or legit_excluded(nb, truth_an, s))}
        missed = len(expect - used_ids)
        n_legit = len(T.ids) - len(expect)
        ok = wrong == 0 and missed == 0 and sm["excluded"] == n_legit
        total_fail += not ok
        print(f"  {an_a:12} -> {an_b:10} [{why:10}] rätt {correct:2}/{len(expect):2}  fel {wrong}  saknas {missed}"
              f"  uteslutna {sm['excluded']} (förv. {n_legit}) {sm['excluded_reasons'] or ''}"
              f"  endast A/B {sm['only_a']}/{sm['only_b']}   {'GODKÄND' if ok else 'UNDERKÄND'}")
print(f"\n{'ALLA GODKÄNDA' if total_fail == 0 else f'{total_fail} UNDERKÄNDA'}")
