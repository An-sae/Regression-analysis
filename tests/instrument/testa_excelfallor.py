"""
Isolerade Excelfällor: fil A är en ren CSV, fil B en Excelfil där EN egenskap
ändras åt gången. Programmets automatiska val används; varje par mot facit.
"""
import os, sys, io, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
import numpy as np, pandas as pd, openpyxl
from analysis.data_loader import load_long_format, list_analytes, match_two_files
from analysis.file_reader import (guess_column, suggest_analyte, canonical_analyte,
                                  detect_layout, to_long, best_sheet)

rng = np.random.default_rng(11); N = 20
IDS = [f"{7000 + i * 13:07d}" for i in range(N)]                  # ledande nollor
TRUTH = {"NA": np.round(rng.uniform(128, 150, N), 0), "HB": np.round(rng.uniform(90, 170, N), 0),
         "EVF": np.round(rng.uniform(0.30, 0.50, N), 3)}
TB = {k: np.round(v * rng.normal(1.01, 0.01, N), 3 if k == "EVF" else 1) for k, v in TRUTH.items()}
A_CSV = ("Sample ID;Test;Result\n" + "".join(
    f"{s};{k};{str(TRUTH[k][i]).replace('.', ',')}\n" for k in TRUTH for i, s in enumerate(IDS))).encode()
NAMES_WIDE = {"NA": "P-Natrium", "HB": "B-Hb", "EVF": "B-EVF"}

def wb_bytes(build):
    wb = openpyxl.Workbook(); build(wb); b = io.BytesIO(); wb.save(b); return b.getvalue()

def wide_rows(ws, r0=1, c0=1, text_every=0, id_int=False):
    heads = ["Provnummer"] + list(NAMES_WIDE.values())
    for j, h in enumerate(heads): ws.cell(row=r0, column=c0 + j, value=h)
    for i, s in enumerate(IDS):
        ws.cell(row=r0 + 1 + i, column=c0, value=int(s) if id_int else s)
        for j, k in enumerate(NAMES_WIDE, 1):
            v = float(TB[k][i])
            ws.cell(row=r0 + 1 + i, column=c0 + j,
                    value=(str(v).replace(".", ",") if text_every and i % text_every == 0 else v))
    return r0 + 1 + N

TRAPS = []
def trap(tid, title):
    def d(fn): TRAPS.append((tid, title, fn)); return fn
    return d

@trap("X01", "Baslinje: långt format i Excel")
def _():
    def b(wb):
        ws = wb.active; ws.append(["Sample ID", "Test", "Result"])
        for k in TRUTH:
            for i, s in enumerate(IDS): ws.append([s, k, float(TB[k][i])])
    return wb_bytes(b), set()

@trap("X02", "Testkoden 'NA' (natrium) i Excel")
def _(): return TRAPS[0][2]()                       # samma fil; NA måste överleva

@trap("X03", "Informationsblad före resultatbladet")
def _():
    def b(wb):
        info = wb.active; info.title = "Info"; info.append(["Instrument", "cobas pro"])
        ws = wb.create_sheet("Results"); ws.append(["Sample ID", "Test", "Result"])
        for k in TRUTH:
            for i, s in enumerate(IDS): ws.append([s, k, float(TB[k][i])])
    return wb_bytes(b), set()

@trap("X04", "Brett: titelrader och enhetsrad under rubriken")
def _():
    def b(wb):
        ws = wb.active; ws["A1"] = "Resultatlista"; wide_rows(ws, r0=4)
        ws.insert_rows(5)                            # enhetsrad direkt under rubriken
        for j, u in enumerate(["", "mmol/L", "g/L", ""]): ws.cell(row=5, column=1 + j, value=u or None)
    return wb_bytes(b), set()

@trap("X05", "Brett: summarader längst ned (Medelvärde, SD, Antal, Min, Max)")
def _():
    def b(wb):
        ws = wb.active; r = wide_rows(ws)
        for lab in ("Medelvärde", "SD", "Antal", "Min", "Max"):
            ws.cell(row=r + 1, column=1, value=lab)
            for j in range(2, 5): ws.cell(row=r + 1, column=j, value=1.0)
            r += 1
    return wb_bytes(b), set()

@trap("X06", "Brett: tal lagrade som text ('0,411') blandat med riktiga tal")
def _():
    def b(wb): wide_rows(wb.active, text_every=3)
    return wb_bytes(b), set()

@trap("X07", "Brett: sammanslagen grupprubrik ovanför rubrikraden")
def _():
    def b(wb):
        ws = wb.active; ws["B1"] = "Kemi och hematologi"; ws.merge_cells("B1:D1"); wide_rows(ws, r0=2)
    return wb_bytes(b), set()

@trap("X08", "Brett: tabellen börjar i kolumn C, tomma rader emellan")
def _():
    def b(wb):
        ws = wb.active; wide_rows(ws, r0=3, c0=3)
        ws.insert_rows(10); ws.insert_rows(15)
    return wb_bytes(b), set()

@trap("X09", "Formelceller utan sparade värden (fil skapad av annat program)")
def _():
    legit = set()
    def b(wb):
        ws = wb.active; wide_rows(ws)
        for i in (2, 5):
            ws.cell(row=2 + i, column=3, value=f"=A{2 + i}*0"); legit.add(("HB", IDS[i]))
    return wb_bytes(b), legit

@trap("X10", "Prov-ID lagrade som tal (ledande nollor förlorade)")
def _():
    def b(wb): wide_rows(wb.active, id_int=True)
    return wb_bytes(b), set()

@trap("X11", "Dubblerade kolumnrubriker ('Result' två gånger)")
def _():
    def b(wb):
        ws = wb.active; ws.append(["Sample ID", "Test", "Result", "Result"])
        for k in TRUTH:
            for i, s in enumerate(IDS): ws.append([s, k, float(TB[k][i]), "ref"])
    return wb_bytes(b), set()

@trap("X12", "Mycket bred Sysmex-lik fil: 60 kolumner, textflaggor, forskningsparametrar")
def _():
    def b(wb):
        ws = wb.active
        heads = ["Sample No.", "Date", "Time", "Rack", "IP Message"] + list(NAMES_WIDE.values()) + \
                [f"[{p}]" for p in range(52)]
        ws.append(heads)
        for i, s in enumerate(IDS):
            ws.append([s, "2026-09-15", "08:00", 1001 + i, "Blasts?" if i % 4 == 0 else ""] +
                      [float(TB[k][i]) for k in NAMES_WIDE] + list(np.round(rng.uniform(0, 5, 52), 2)))
    return wb_bytes(b), set()

def load(raw, name):
    df = load_long_format(raw, name, sheet=best_sheet(raw, name))
    L = detect_layout(df)
    if L["layout"] == "wide":
        return to_long(df, L["id_col"], L["value_cols"]), L["id_col"], "Analysis", "Result"
    c = list(df.columns)
    return df, guess_column(c, "id"), guess_column(c, "an"), guess_column(c, "res")

CANON = {"NA": "NA", "NATRIUM": "NA", "HB": "HB", "EVF": "EVF"}
fails = 0
A, ia, aa, ra = load(A_CSV, "a.csv")
for tid, title, fn in TRAPS:
    raw, legit = fn()
    try:
        B, ib, ab, rb = load(raw, "b.xlsx")
        correct = wrong = 0; seen = set(); lb = list_analytes(B, ab)
        for an_a in list_analytes(A, aa):
            an_b, _ = suggest_analyte(an_a, lb)
            if an_b is None: continue
            x, y, rep, sm = match_two_files(A, B, ia, ib, aa, ab, ra, rb, an_a, an_b)
            k = CANON[an_a]; m = rep[rep["Match"] == "Matched"]
            for sid, va, vb in zip(m["SampleID"], m.iloc[:, 2], m.iloc[:, 3]):
                if not (np.isfinite(va) and np.isfinite(vb)): continue
                i = [int(s) for s in IDS].index(int(float(str(sid).strip())))
                if abs(TRUTH[k][i] - va) < 1e-9 and abs(TB[k][i] - vb) < 1e-9:
                    correct += 1; seen.add((k, IDS[i]))
                else:
                    wrong += 1
        expected = {(k, s) for k in TRUTH for s in IDS} - legit
        missed = len(expected - seen)
        ok = wrong == 0 and missed == 0
        res = f"rätt {correct:2}/{len(expected)}  fel {wrong}  saknas {missed}"
    except Exception as e:
        ok, res = False, f"FEL: {str(e)[:70]}"
    fails += not ok
    print(f"  {tid} {'OK ' if ok else 'FEL'} {title:62} {res}")
print(f"\n{'ALLA GODKÄNDA' if not fails else f'{fails} FEL'}")
sys.exit(1 if fails else 0)
