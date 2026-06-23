"""
Confusion Matrix & Agreement Statistics for Zone Diameter Comparison
=====================================================================
Clinical microbiology method comparison following EUCAST/CLSI guidelines.

Key metrics:
  - Essential Agreement (EA): percentage of isolates where the two methods
    agree within ±1 mm and ±2 mm respectively.
  - Categorical Agreement (CA): percentage of isolates that receive the same
    S/I/R category from both methods.
  - Very Major Error (VME): reference S → candidate R
  - Major Error (ME): reference R → candidate S
  - Minor Error (mE): any error involving I

References:
  EUCAST Disk Diffusion Method v10.0
  CLSI M52 — Verification of Commercial Microbial Identification and
              Antimicrobial Susceptibility Testing Systems
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
import pandas as pd


# ── Cell count matrix ─────────────────────────────────────────────────────────

def build_count_matrix(
    x: np.ndarray,
    y: np.ndarray,
    step: int = 1,
    x_min: Optional[int] = None,
    x_max: Optional[int] = None,
    y_min: Optional[int] = None,
    y_max: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Build a count matrix where cell[i, j] = number of isolates where
    reference method = x_bins[j] and candidate method = y_bins[i].

    Parameters
    ----------
    x, y   : raw measurement arrays (zone diameters in mm)
    step   : bin width in mm (1 = each mm is a cell)
    x_min, x_max, y_min, y_max : axis limits (None = auto from data)

    Returns
    -------
    matrix  : 2D int array  (shape: n_y_bins × n_x_bins)
    x_bins  : 1D array of x bin centres
    y_bins  : 1D array of y bin centres
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]

    # Round to nearest step
    x_r = np.round(x / step).astype(int) * step
    y_r = np.round(y / step).astype(int) * step

    # Force identical axis range so both axes are symmetric and square
    if x_min is not None and y_min is not None:
        lo = int(min(x_min, y_min))
    elif x_min is not None:
        lo = int(min(x_min, int(y_r.min())))
    elif y_min is not None:
        lo = int(min(y_min, int(x_r.min())))
    else:
        lo = int(min(x_r.min(), y_r.min()))

    if x_max is not None and y_max is not None:
        hi = int(max(x_max, y_max))
    elif x_max is not None:
        hi = int(max(x_max, int(y_r.max())))
    elif y_max is not None:
        hi = int(max(y_max, int(x_r.max())))
    else:
        hi = int(max(x_r.max(), y_r.max()))

    # Snap lo/hi to step grid
    lo = int(np.floor(lo / step) * step)
    hi = int(np.ceil(hi  / step) * step)

    bins = np.arange(lo, hi + step, step)   # identical for both axes
    x_bins = bins
    y_bins = bins

    matrix = np.zeros((len(y_bins), len(x_bins)), dtype=int)

    for xi, yi in zip(x_r, y_r):
        if lo <= xi <= hi and lo <= yi <= hi:
            col = int((xi - lo) / step)
            row = int((yi - lo) / step)
            if 0 <= row < len(y_bins) and 0 <= col < len(x_bins):
                matrix[row, col] += 1

    return matrix, x_bins, y_bins


# ── Essential agreement ───────────────────────────────────────────────────────

def essential_agreement(x: np.ndarray, y: np.ndarray) -> Dict[str, float]:
    """
    Compute essential agreement at ±1 mm and ±2 mm.
    Returns percentages and counts.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)
    if n == 0:
        return {"ea_1mm": 0.0, "ea_2mm": 0.0, "n_ea1": 0, "n_ea2": 0, "n": 0}

    diff = np.abs(x - y)
    n_ea1 = int(np.sum(diff <= 1))
    n_ea2 = int(np.sum(diff <= 2))
    return {
        "ea_1mm": n_ea1 / n * 100,
        "ea_2mm": n_ea2 / n * 100,
        "n_ea1":  n_ea1,
        "n_ea2":  n_ea2,
        "n":      n,
    }


# ── Categorical agreement ─────────────────────────────────────────────────────

def _classify(value: float, s_bp: float, r_bp: float,
              system: str = "EUCAST") -> str:
    """
    Classify a zone diameter as S, I, or R.

    EUCAST: S ≥ s_bp,  R ≤ r_bp,  I = between
    CLSI:   S ≥ s_bp,  R ≤ r_bp,  I = between  (same logic, different BPs)
    """
    if np.isnan(value):
        return "?"
    if value >= s_bp:
        return "S"
    if value <= r_bp:
        return "R"
    return "I"


def categorical_agreement(
    x: np.ndarray,
    y: np.ndarray,
    s_breakpoint_x: float,
    r_breakpoint_x: float,
    s_breakpoint_y: float,
    r_breakpoint_y: float,
) -> Dict:
    """
    Compute categorical agreement and error rates.

    Breakpoints may differ between x and y if the two methods use
    different criteria (uncommon but possible).

    Returns
    -------
    dict with ca (%), vme (%), me (%), minor_e (%), and counts.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)

    if n == 0:
        return {k: 0 for k in
                ["ca", "vme", "me", "minor_e", "n_ca", "n_vme", "n_me",
                 "n_minor", "n", "n_s_ref", "n_r_ref"]}

    cats_x = np.array([_classify(v, s_breakpoint_x, r_breakpoint_x) for v in x])
    cats_y = np.array([_classify(v, s_breakpoint_y, r_breakpoint_y) for v in y])

    agree = cats_x == cats_y
    n_ca  = int(np.sum(agree))

    # Very major error: reference S, candidate R
    n_vme = int(np.sum((cats_x == "S") & (cats_y == "R")))
    # Major error: reference R, candidate S
    n_me  = int(np.sum((cats_x == "R") & (cats_y == "S")))
    # Minor errors: everything else that disagrees
    n_min = int(np.sum(~agree)) - n_vme - n_me

    n_s_ref = int(np.sum(cats_x == "S"))
    n_r_ref = int(np.sum(cats_x == "R"))

    denom_vme = n_s_ref if n_s_ref > 0 else 1
    denom_me  = n_r_ref if n_r_ref > 0 else 1

    return {
        "ca":       n_ca / n * 100,
        "vme":      n_vme / denom_vme * 100,
        "me":       n_me  / denom_me  * 100,
        "minor_e":  n_min / n * 100,
        "n_ca":     n_ca,
        "n_vme":    n_vme,
        "n_me":     n_me,
        "n_minor":  n_min,
        "n":        n,
        "n_s_ref":  n_s_ref,
        "n_r_ref":  n_r_ref,
    }
