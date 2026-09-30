"""
Rubrikradsfällor i breda instrumentexporter (Sysmex XN-typ).

Bakgrund (v2.2.1): i en XN-export följdes rubrikraden av QC-rader med många
tomma flaggkolumner, och längre ned fanns en misslyckad körning där alla
resultat var '----'. Programmet hoppade då över den riktiga rubriken och tog
den misslyckade raden som rubrik. Varje fall nedan ska ge rubrik på rad 1
och exakt rätt analyskolumner.
"""
import os, sys, io, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
import numpy as np, openpyxl
from analysis.data_loader import load_long_format
from analysis.file_reader import detect_layout, best_sheet

PARAMS = ["WBC(10^9/L)", "RBC(10^12/L)", "HGB(g/L)", "HCT(%)", "MCV(fL)", "MCH(pg)",
          "MCHC(g/L)", "PLT(10^9/L)", "RDW-CV(%)", "NEUT#(10^9/L)", "LYMPH#(10^9/L)"]
META = ["Nickname", "Analyzer ID", "Date", "Time", "Rack", "Position", "Sample No.",
        "Sample Inf.", "Measurement Mode", "Patient ID", "Error(Func.)", "Error(Result)",
        "WBC Abnormal", "PLT Abnormal", "IP Message"]
HEAD = META + [x for p in PARAMS for x in (p, p.split("(")[0] + "/M")]
rng = np.random.default_rng(3)


def row(sid, vals, mode="WB", err="", ip="", flagged=False):
    r = {"Nickname": "XN-X", "Analyzer ID": "XN^1", "Date": "2026/09/28", "Time": "08:00:00",
         "Rack": 5001, "Position": 1, "Sample No.": sid, "Measurement Mode": mode,
         "Error(Func.)": err, "Error(Result)": err, "IP Message": ip}
    if flagged:                    # flaggade prov fyller fler celler än QC-rader
        r.update({"IP Message": "Leukocytosis", "WBC Abnormal": 1})
    for p, v in zip(PARAMS, vals):
        r[p] = v
    return [r.get(h, "") for h in HEAD]


def build(qc_first=True, failed_at=None, code="----", n=25, id_int=False):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "XN Data"; ws.append(HEAD)
    if qc_first:
        for l in ("L1", "L2", "L3"):
            ws.append(row(f"QC-XN-{l}", [5.0, 4.5, 135, 40.1, 89.0, 30.0, 335, 230, 13.5, 3.0, 1.5],
                          mode="QC"))
    for i in range(n):
        sid = f"0926{i + 101:04d}"
        sid = int(sid) if id_int else sid
        if failed_at is not None and i == failed_at:
            ws.append(row(sid, [code] * len(PARAMS), err="1", ip="Sampling Error"))
        vals = [round(float(rng.uniform(2, 20)), 2), round(float(rng.uniform(3, 6)), 2),
                int(rng.uniform(90, 170)), round(float(rng.uniform(30, 50)), 1),
                round(float(rng.uniform(75, 100)), 1), round(float(rng.uniform(26, 34)), 1),
                int(rng.uniform(320, 350)), int(rng.uniform(20, 600)),
                round(float(rng.uniform(12, 16)), 1), round(float(rng.uniform(1, 9)), 2),
                round(float(rng.uniform(0.5, 4)), 2)]
        ws.append(row(sid, vals, flagged=i % 3 != 0))
    b = io.BytesIO(); wb.save(b); return b.getvalue()


CASES = [
    ("R01", "QC-rader med tomma flaggkolumner direkt under rubriken", dict()),
    ("R02", "…och en misslyckad körning med '----' längre ned", dict(failed_at=12)),
    ("R03", "…misslyckad körning med '++++'", dict(failed_at=12, code="++++")),
    ("R04", "Misslyckad körning direkt under rubriken, inga QC-rader", dict(qc_first=False, failed_at=0)),
    ("R05", "Sample No. som tal + misslyckad körning", dict(failed_at=5, id_int=True)),
]

fails = 0
def check(name, ok, detail=""):
    global fails; fails += not ok
    print(f"  {'OK ' if ok else 'FEL'} {name}" + ("" if ok else f"  — {str(detail)[:300]}"))

for cid, title, kw in CASES:
    raw = build(**kw)
    df = load_long_format(raw, "xn.xlsx", sheet=best_sheet(raw, "xn.xlsx"))
    info = df.attrs.get("read_info", {})
    lay = detect_layout(df)
    check(f"{cid} {title}: rubrik rad {info.get('header_row')}, ID '{lay['id_col']}', "
          f"{len(lay['value_cols'])} analyser",
          info.get("header_row") == 1 and lay["id_col"] == "Sample No."
          and lay["value_cols"] == PARAMS, (info, lay))

# Demofilerna som följer med programmet (data/demo) ska läsas rätt
demo = os.path.join(ROOT, "data", "demo")
for f in ("Sysmex_XN-1000_radata.xlsx", "Sysmex_XN-2000_radata.xlsx"):
    p = os.path.join(demo, f)
    if not os.path.exists(p):
        check(f"demofil {f} finns", False, p); continue
    raw = open(p, "rb").read()
    df = load_long_format(raw, f, sheet=best_sheet(raw, f))
    lay = detect_layout(df)
    check(f"demofil {f}: rubrik rad {df.attrs['read_info'].get('header_row')}, "
          f"{len(lay['value_cols'])} analyser",
          df.attrs["read_info"].get("header_row") == 1 and len(lay["value_cols"]) == 11
          and lay["id_col"] == "Sample No.", lay)

print(f"\n{'ALLA GODKÄNDA' if not fails else f'{fails} FEL'}")
sys.exit(1 if fails else 0)
