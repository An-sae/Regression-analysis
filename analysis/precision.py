"""
Precision Evaluation Module — CLSI EP15-A3 (2014)
===================================================
User verification of repeatability (within-run) and within-laboratory
(total) imprecision for quantitative laboratory measurement procedures.

Protocol (EP15-A3 §2):
    - 5 replicates per day over 5 days (minimum)
    - At least 2 concentration levels
    - Data entered as one column per day

Statistics computed
-------------------
Within-run (repeatability) SD and CV
    sr = sqrt( sum_d sum_r (x_dr - x̄_d)² / D(n-1) )

Between-day variance
    sb² = max(0,  (s_day² - sr²/n) )          [variance components]
    where s_day² = sum_d (x̄_d - x̄)² / (D-1)

Within-laboratory (total) SD and CV
    sl = sqrt( sr² + sb² )                      [EP15-A3 eq. B-5]

Effective degrees of freedom (Welch-Satterthwaite) for sl:
    T = (sr²/n  +  sb²)² /
        ( (sr²/n)² / (D(n-1))  +  sb⁴ / (D-1) )

Chi-square verification (EP15-A3 §2.4.3):
    If claimed SD σ is provided, compute verification value:
        V_r  = σ_r  × sqrt( χ²(1-α/q, v_r)  / v_r  )
        V_l  = σ_l  × sqrt( χ²(1-α/q, T)    / T    )
    Pass if observed SD ≤ verification value.

References
----------
CLSI EP15-A3. User Verification of Precision and Estimation of Bias;
Approved Guideline—Third Edition. Wayne, PA: CLSI; 2014.

Chesher D. Evaluating Assay Precision.
Clin Biochem Rev. 2008;29(Suppl i):S23–S26.
"""

import numpy as np
from typing import Dict, List, Optional
from scipy.stats import chi2


def compute_precision(
    data: Dict[str, List[float]],
    alpha: float = 0.05,
    n_levels: int = 1,
    claimed_sr: Optional[float] = None,
    claimed_sl: Optional[float] = None,
) -> Dict:
    """
    Compute EP15-A3 precision statistics from replicate data.

    Parameters
    ----------
    data : dict
        Keys = day labels (e.g. "Day 1"), values = list of replicate results.
        All days must have the same number of replicates.
    alpha : float
        False-rejection rate (default 0.05 → 95 % verification).
    n_levels : int
        Number of concentration levels tested simultaneously (for chi-square
        Bonferroni correction: q = n_levels). Default 1.
    claimed_sr : float or None
        Manufacturer's claimed repeatability SD.
    claimed_sl : float or None
        Manufacturer's claimed within-laboratory SD.

    Returns
    -------
    dict with all precision statistics and verification results.
    """
    # ── parse data ─────────────────────────────────────────────────────────────
    day_labels = list(data.keys())
    D = len(day_labels)                      # number of days
    matrix = np.array([data[k] for k in day_labels], dtype=float)  # D × n
    n = matrix.shape[1]                      # replicates per day

    if D < 2:
        raise ValueError("Need at least 2 days of data.")
    if n < 2:
        raise ValueError("Need at least 2 replicates per day.")

    # ── outlier flag (EP15-A3: |x - x̄_d| > 3.5 × sr_preliminary) ─────────────
    # We flag but do not auto-remove; the user sees the flag in the output.
    day_means = matrix.mean(axis=1)          # shape (D,)
    grand_mean = matrix.mean()

    # ── within-run variance ────────────────────────────────────────────────────
    # Sr² = Σ_d Σ_r (x_dr - x̄_d)² / D(n-1)
    deviations_from_day_mean = matrix - day_means[:, np.newaxis]
    ss_within = np.sum(deviations_from_day_mean ** 2)
    df_within  = D * (n - 1)
    sr2 = ss_within / df_within
    sr  = float(np.sqrt(sr2))

    # ── between-day variance ───────────────────────────────────────────────────
    # s_day² = Σ_d (x̄_d - x̄)² / (D-1)
    ss_between = np.sum((day_means - grand_mean) ** 2)
    df_between  = D - 1
    s_day2 = ss_between / df_between

    # Variance component for between-day: sb² = max(0, s_day² - sr²/n)
    sb2 = max(0.0, s_day2 - sr2 / n)
    sb  = float(np.sqrt(sb2))

    # ── within-laboratory (total) SD ───────────────────────────────────────────
    sl2 = sr2 + sb2
    sl  = float(np.sqrt(sl2))

    # ── CVs ───────────────────────────────────────────────────────────────────
    cv_r = float(sr / grand_mean * 100) if grand_mean != 0 else float("nan")
    cv_l = float(sl / grand_mean * 100) if grand_mean != 0 else float("nan")

    # ── effective degrees of freedom for sl (Welch-Satterthwaite) ─────────────
    # T = (sr²/n + sb²)² / ( (sr²/n)²/D(n-1) + sb⁴/(D-1) )
    term1 = sr2 / n
    term2 = sb2
    numer  = (term1 + term2) ** 2
    denom_t1 = term1 ** 2 / df_within if df_within > 0 else 0
    denom_t2 = sb2 ** 2 / df_between if (df_between > 0 and sb2 > 0) else 0
    T = float(numer / (denom_t1 + denom_t2)) if (denom_t1 + denom_t2) > 0 else float(df_within)

    # ── chi-square verification (EP15-A3 §2.4.3) ──────────────────────────────
    q = n_levels
    chi2_crit_r = chi2.ppf(1 - alpha / q, df=df_within)
    chi2_crit_l = chi2.ppf(1 - alpha / q, df=max(1, T))

    verif_sr = verif_sl = None
    pass_sr  = pass_sl  = None

    if claimed_sr is not None and claimed_sr > 0:
        verif_sr = float(claimed_sr * np.sqrt(chi2_crit_r / df_within))
        pass_sr  = bool(sr <= verif_sr)

    if claimed_sl is not None and claimed_sl > 0:
        verif_sl = float(claimed_sl * np.sqrt(chi2_crit_l / max(1, T)))
        pass_sl  = bool(sl <= verif_sl)

    # ── per-day summary ────────────────────────────────────────────────────────
    day_summary = []
    for i, lbl in enumerate(day_labels):
        reps = matrix[i]
        day_summary.append({
            "Day":        lbl,
            "n":          n,
            "Mean":       float(reps.mean()),
            "SD":         float(reps.std(ddof=1)) if n > 1 else 0.0,
            "CV (%)":     float(reps.std(ddof=1) / reps.mean() * 100)
                          if (n > 1 and reps.mean() != 0) else 0.0,
            "Min":        float(reps.min()),
            "Max":        float(reps.max()),
        })

    # ── outlier detection (|deviation| > 3.5 × sr) ────────────────────────────
    outliers = []
    if sr > 0:
        for i, lbl in enumerate(day_labels):
            for j, val in enumerate(matrix[i]):
                if abs(val - day_means[i]) > 3.5 * sr:
                    outliers.append({
                        "Day": lbl,
                        "Replicate": j + 1,
                        "Value": float(val),
                        "Day mean": float(day_means[i]),
                        "Deviation / Sr": float(abs(val - day_means[i]) / sr),
                    })

    return {
        # Core statistics
        "grand_mean":   float(grand_mean),
        "D":            D,
        "n":            n,
        "df_within":    df_within,
        "df_between":   df_between,
        "T":            T,

        # Within-run (repeatability)
        "sr":           sr,
        "sr2":          float(sr2),
        "cv_r":         cv_r,

        # Between-day
        "sb":           sb,
        "sb2":          float(sb2),
        "s_day2":       float(s_day2),

        # Within-laboratory (total)
        "sl":           sl,
        "sl2":          float(sl2),
        "cv_l":         cv_l,

        # Verification
        "alpha":        alpha,
        "q":            q,
        "chi2_crit_r":  float(chi2_crit_r),
        "chi2_crit_l":  float(chi2_crit_l),
        "claimed_sr":   claimed_sr,
        "claimed_sl":   claimed_sl,
        "verif_sr":     verif_sr,
        "verif_sl":     verif_sl,
        "pass_sr":      pass_sr,
        "pass_sl":      pass_sl,

        # Detail
        "day_summary":  day_summary,
        "day_means":    day_means.tolist(),
        "outliers":     outliers,
    }


def precision_from_dataframe(df, decimal_sep=",") -> Dict[str, List[float]]:
    """
    Convert a DataFrame where each column = one day's replicates into
    the dict format expected by compute_precision().
    Handles comma decimals and drops NaN rows per column independently.
    """
    result = {}
    for col in df.columns:
        series = df[col].astype(str).str.replace(",", ".").str.strip()
        vals = []
        for v in series:
            try:
                f = float(v)
                if np.isfinite(f):
                    vals.append(f)
            except ValueError:
                continue
        if vals:
            result[str(col)] = vals
    return result
