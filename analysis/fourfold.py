"""
Fyrfältstabell (2×2) för kvalitativa metoder
=============================================

Två användningsfall, med olika terminologi:

  A) REFERENSSTANDARD ("facit" finns)
     Kandidatmetoden jämförs mot ett referenstest som anses ge sant
     tillstånd. Rapportera SENSITIVITET och SPECIFICITET, samt
     prediktiva värden och likelihood-kvoter.

  B) METODJÄMFÖRELSE (inget facit)
     Två metoder jämförs mot varandra där ingen kan anses vara
     sanningen. Då får sensitivitet INTE hävdas. Rapportera i stället
     POSITIV och NEGATIV PROCENTUELL ÖVERENSSTÄMMELSE (PPA/NPA).

Detta är CLSI EP12-A2:s och FDA:s uttryckliga rekommendation. PPA/NPA
har samma formler som sensitivitet/specificitet men gör inga anspråk på
att beskriva sant sjukdomstillstånd.

Konfidensintervall beräknas med Wilsons score-metod, som rekommenderas
för proportioner och fungerar även vid 0 % och 100 %, där den vanliga
Wald-metoden ger meningslösa intervall.

Referenser
----------
CLSI EP12-A2. User Protocol for Evaluation of Qualitative Test
  Performance. Wayne, PA: CLSI; 2008.
FDA. Statistical Guidance on Reporting Results from Studies Evaluating
  Diagnostic Tests. 2007.
Wilson EB. J Am Stat Assoc. 1927;22:209-212.
Cohen J. Educ Psychol Meas. 1960;20:37-46.
Bossuyt PM et al. STARD 2015. BMJ. 2015;351:h5527.
"""

from typing import Dict, Optional, Tuple

import numpy as np
from scipy.stats import norm, binomtest, chi2


# ── Konfidensintervall för proportion ────────────────────────────────────────

def wilson_ci(k: int, n: int, conf: float = 0.95) -> Tuple[float, float]:
    """
    Wilsons score-intervall för en proportion k/n, returnerat i procent.

    Till skillnad från Wald-intervallet ger Wilson rimliga gränser även
    när k = 0 eller k = n, vilket är vanligt vid utvärdering av bra
    kvalitativa tester.
    """
    if n <= 0:
        return (float("nan"), float("nan"))
    z = norm.ppf(1 - (1 - conf) / 2)
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = (z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    lo = max(0.0, centre - half)
    hi = min(1.0, centre + half)
    return (lo * 100, hi * 100)


def _pct(k: int, n: int) -> float:
    return float(k / n * 100) if n > 0 else float("nan")


# ── Huvudberäkning ───────────────────────────────────────────────────────────

def fourfold(
    tp: int, fp: int, fn: int, tn: int,
    mode: str = "agreement",          # "agreement" | "reference"
    conf: float = 0.95,
) -> Dict:
    """
    Beräkna samtliga mått från en fyrfältstabell.

    Cellernas betydelse (rad = kandidatmetod, kolumn = referens/jämförelse):

                        Referens +    Referens −
        Kandidat +          tp            fp
        Kandidat −          fn            tn

    mode = "reference"  -> sensitivitet/specificitet + prediktiva värden
    mode = "agreement"  -> PPA/NPA/OPA (inget facit antas)
    """
    tp, fp, fn, tn = int(tp), int(fp), int(fn), int(tn)
    n = tp + fp + fn + tn
    if n == 0:
        raise ValueError("Tabellen är tom.")

    n_ref_pos = tp + fn          # antal positiva enligt referens/jämförelse
    n_ref_neg = fp + tn
    n_cand_pos = tp + fp
    n_cand_neg = fn + tn

    # --- Kärnmått (samma formler, olika namn beroende på läge) --------------
    ppa = _pct(tp, n_ref_pos)                 # = sensitivitet om facit finns
    npa = _pct(tn, n_ref_neg)                 # = specificitet om facit finns
    opa = _pct(tp + tn, n)                    # total överensstämmelse

    ppa_ci = wilson_ci(tp, n_ref_pos, conf)
    npa_ci = wilson_ci(tn, n_ref_neg, conf)
    opa_ci = wilson_ci(tp + tn, n, conf)

    out = {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": n,
        "n_ref_pos": n_ref_pos, "n_ref_neg": n_ref_neg,
        "n_cand_pos": n_cand_pos, "n_cand_neg": n_cand_neg,
        "mode": mode, "conf": conf,
        "ppa": ppa, "ppa_ci": ppa_ci,
        "npa": npa, "npa_ci": npa_ci,
        "opa": opa, "opa_ci": opa_ci,
    }

    # --- Endast meningsfullt när ett facit finns ----------------------------
    if mode == "reference":
        ppv = _pct(tp, n_cand_pos)
        npv = _pct(tn, n_cand_neg)
        out.update({
            "ppv": ppv, "ppv_ci": wilson_ci(tp, n_cand_pos, conf),
            "npv": npv, "npv_ci": wilson_ci(tn, n_cand_neg, conf),
            "prevalence": _pct(n_ref_pos, n),
            "prevalence_ci": wilson_ci(n_ref_pos, n, conf),
        })
        # Likelihood-kvoter
        sens, spec = ppa / 100, npa / 100
        out["lr_pos"] = float(sens / (1 - spec)) if spec < 1 else float("inf")
        out["lr_neg"] = float((1 - sens) / spec) if spec > 0 else float("inf")

    # --- Cohens kappa (överensstämmelse korrigerad för slumpen) -------------
    po = (tp + tn) / n
    pe = ((n_cand_pos * n_ref_pos) + (n_cand_neg * n_ref_neg)) / (n * n)
    kappa = (po - pe) / (1 - pe) if pe < 1 else float("nan")
    # Standardfel enligt Fleiss för binär kappa
    if 0 < pe < 1:
        se_k = np.sqrt(po * (1 - po) / (n * (1 - pe) ** 2))
        z = norm.ppf(1 - (1 - conf) / 2)
        k_ci = (float(kappa - z * se_k), float(kappa + z * se_k))
    else:
        k_ci = (float("nan"), float("nan"))
    out["kappa"] = float(kappa)
    out["kappa_ci"] = k_ci
    out["kappa_tolkning"] = _kappa_label(kappa)

    # --- McNemars test (systematisk skillnad mellan metoderna) --------------
    # Endast de diskordanta cellerna bär information.
    b, c = fp, fn
    if b + c == 0:
        out.update({"mcnemar_p": 1.0, "mcnemar_metod": "inga diskordanta par",
                    "mcnemar_stat": 0.0})
    elif b + c < 25:
        # Exakt binomialtest rekommenderas vid få diskordanta par
        p = binomtest(b, b + c, 0.5).pvalue
        out.update({"mcnemar_p": float(p), "mcnemar_metod": "exakt binomialtest",
                    "mcnemar_stat": float(b)})
    else:
        stat = (abs(b - c) - 1) ** 2 / (b + c)     # kontinuitetskorrigerad
        out.update({"mcnemar_p": float(1 - chi2.cdf(stat, 1)),
                    "mcnemar_metod": "chi-två med kontinuitetskorrektion",
                    "mcnemar_stat": float(stat)})

    return out


def _kappa_label(k: float) -> str:
    """Landis & Koch 1977, med brasklapp: gränserna är godtyckliga."""
    if not np.isfinite(k):
        return "kan ej beräknas"
    if k < 0.00: return "sämre än slumpen"
    if k < 0.21: return "obetydlig"
    if k < 0.41: return "svag"
    if k < 0.61: return "måttlig"
    if k < 0.81: return "god"
    return "mycket god"


# ── Bygg tabellen från data ──────────────────────────────────────────────────

def fourfold_from_arrays(
    ref, cand,
    positive_label=None,
    cutoff_ref: Optional[float] = None,
    cutoff_cand: Optional[float] = None,
    direction: str = ">=",
) -> Dict[str, int]:
    """
    Skapa cellantalen från två arrayer.

    Antingen är värdena redan binära (text eller 0/1) och positive_label
    anger vad som räknas som positivt, eller så är de kvantitativa och
    dikotomiseras med hjälp av en beslutsgräns (cutoff).
    """
    ref = np.asarray(ref)
    cand = np.asarray(cand)
    if len(ref) != len(cand):
        raise ValueError("Metoderna har olika antal värden.")

    def _binarise(a, cutoff):
        if cutoff is not None:
            v = np.asarray(a, dtype=float)
            return (v >= cutoff) if direction == ">=" else (v <= cutoff)
        if positive_label is not None:
            return np.array([str(x).strip().lower()
                             == str(positive_label).strip().lower() for x in a])
        # fall back: vanliga positiva beteckningar
        pos = {"1", "pos", "positiv", "positive", "+", "ja", "yes",
               "true", "påvisad", "reaktiv"}
        return np.array([str(x).strip().lower() in pos for x in a])

    r = _binarise(ref, cutoff_ref)
    c = _binarise(cand, cutoff_cand)
    keep = ~(np.array([x is None for x in ref]) | np.array([x is None for x in cand]))
    r, c = r[keep], c[keep]

    return {
        "tp": int(np.sum(c & r)),
        "fp": int(np.sum(c & ~r)),
        "fn": int(np.sum(~c & r)),
        "tn": int(np.sum(~c & ~r)),
    }


# ── Krav på studieupplägg ────────────────────────────────────────────────────

def check_prerequisites(res: Dict) -> list:
    """
    Returnerar en lista med varningar om studieupplägget är otillräckligt.
    Baserat på CLSI EP12-A2 och FDA:s vägledning.
    """
    w = []
    n = res["n"]
    if n < 40:
        w.append(f"Endast {n} prov. CLSI EP12 rekommenderar minst 50 prov, "
                 "helst 100–200 vid verifiering.")
    if res["n_ref_pos"] < 10:
        w.append(f"Endast {res['n_ref_pos']} positiva prov. Konfidensintervallet "
                 "för PPA/sensitivitet blir mycket brett.")
    if res["n_ref_neg"] < 10:
        w.append(f"Endast {res['n_ref_neg']} negativa prov. Konfidensintervallet "
                 "för NPA/specificitet blir mycket brett.")
    lo, hi = res["ppa_ci"]
    if np.isfinite(hi - lo) and (hi - lo) > 20:
        w.append(f"Konfidensintervallet för PPA spänner {hi-lo:.0f} "
                 "procentenheter. Fler positiva prov behövs för en säker "
                 "skattning.")
    lo, hi = res["npa_ci"]
    if np.isfinite(hi - lo) and (hi - lo) > 20:
        w.append(f"Konfidensintervallet för NPA spänner {hi-lo:.0f} "
                 "procentenheter. Fler negativa prov behövs.")
    if res["mode"] == "reference":
        p = res.get("prevalence", float("nan"))
        if np.isfinite(p) and not (20 <= p <= 80):
            w.append(f"Andelen positiva i materialet är {p:.0f} %. Prediktiva "
                     "värden gäller endast vid denna prevalens och ska inte "
                     "överföras till en klinisk population med annan prevalens.")
    return w
