"""
Statistics Helper Module
========================
Correlation and goodness-of-fit metrics for method-comparison studies.
"""

import numpy as np
from typing import Dict


def pearson_r(x, y) -> float:
    """Pearson correlation coefficient between x and y."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 2:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def r_squared(x, y) -> float:
    """Coefficient of determination (Pearson r²)."""
    r = pearson_r(x, y)
    return r ** 2


def bias(x, y) -> float:
    """Mean difference (y − x)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    return float(np.mean(y[mask] - x[mask]))


def limits_of_agreement(x, y) -> Dict[str, float]:
    """
    Bland–Altman limits of agreement.

    Returns
    -------
    dict: mean_diff, std_diff, loa_lower, loa_upper
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    diff = y[mask] - x[mask]
    mean_d = float(np.mean(diff))
    std_d = float(np.std(diff, ddof=1))
    return {
        "mean_diff": mean_d,
        "std_diff": std_d,
        "loa_lower": mean_d - 1.96 * std_d,
        "loa_upper": mean_d + 1.96 * std_d,
    }


def summary_stats(x, y) -> Dict[str, float]:
    """Aggregate all key statistics into one dict."""
    r2 = r_squared(x, y)
    loa = limits_of_agreement(x, y)
    return {
        "pearson_r": pearson_r(x, y),
        "r_squared": r2,
        "bias": bias(x, y),
        **loa,
    }
