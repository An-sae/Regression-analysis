"""
Passing–Bablok Regression Module
=================================
Implements the Passing–Bablok rank-based method-comparison regression.

Reference:
    Passing H, Bablok W. A new biometrical procedure for testing the equality
    of measurements from two different analytical methods. J Clin Chem Clin
    Biochem. 1983;21(11):709-720.
"""

import numpy as np
from typing import Tuple, Dict


def passing_bablok(
    x: np.ndarray,
    y: np.ndarray,
    ci: float = 0.95,
) -> Dict[str, float]:
    """
    Compute Passing–Bablok regression of y on x.

    Parameters
    ----------
    x : array-like
        Reference method measurements.
    y : array-like
        Candidate method measurements.
    ci : float
        Confidence interval level (default 0.95 → 95 % CI).

    Returns
    -------
    dict with keys:
        slope, slope_lower, slope_upper,
        intercept, intercept_lower, intercept_upper,
        n, n_excluded
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    # Remove NaN rows
    mask = np.isfinite(x) & np.isfinite(y)
    n_excluded = int(np.sum(~mask))
    x, y = x[mask], y[mask]
    n = len(x)

    if n < 3:
        raise ValueError(f"Need at least 3 valid observations; got {n}.")

    # Compute all pairwise slopes S_ij = (y_j - y_i) / (x_j - x_i) for j > i
    slopes = []
    for i in range(n):
        for j in range(i + 1, n):
            dx = x[j] - x[i]
            if dx == 0.0:
                # Undefined slope — skip (vertical pair)
                continue
            s = (y[j] - y[i]) / dx
            slopes.append(s)

    slopes = np.sort(np.array(slopes, dtype=float))
    m = len(slopes)

    if m == 0:
        raise ValueError("All x values are identical; slope is undefined.")

    # Count slopes < -1 (K in the original paper)
    K = int(np.sum(slopes < -1.0))

    # Median slope (adjusted index per Passing–Bablok)
    if m % 2 == 1:
        slope = slopes[(m - 1) // 2 + K]
    else:
        mid = m // 2
        slope = 0.5 * (slopes[mid - 1 + K] + slopes[mid + K])

    # Intercept
    intercept = float(np.median(y - slope * x))

    # 95 % CI via rank-based method
    z = _z_score(ci)
    w = z * np.sqrt(n * (n - 1) * (2 * n + 5) / 18.0)

    M1 = int(np.round((m - w) / 2.0))
    M2 = m - M1 + 1

    # Clamp indices
    M1 = max(0, min(M1, m - 1))
    M2 = max(0, min(M2, m - 1))

    slope_lower = float(slopes[M1 + K])
    slope_upper = float(slopes[M2 + K])

    intercept_lower = float(np.median(y - slope_upper * x))
    intercept_upper = float(np.median(y - slope_lower * x))

    return {
        "slope": float(slope),
        "slope_lower": slope_lower,
        "slope_upper": slope_upper,
        "intercept": float(intercept),
        "intercept_lower": intercept_lower,
        "intercept_upper": intercept_upper,
        "n": n,
        "n_excluded": n_excluded,
    }


def _z_score(ci: float) -> float:
    """Return the z-score for a two-tailed confidence interval."""
    from scipy.stats import norm
    alpha = 1.0 - ci
    return float(norm.ppf(1.0 - alpha / 2.0))
