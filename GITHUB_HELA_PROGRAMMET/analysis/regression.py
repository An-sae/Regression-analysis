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

    # ── Pairwise slopes S_ij = (y_j - y_i)/(x_j - x_i) for j > i ─────────────
    # Handling of degenerate pairs follows Passing & Bablok (1983):
    #   x_i == x_j and y_i == y_j  ->  0/0, excluded entirely
    #   x_i == x_j and y_i <  y_j  ->  +infinity, represented by +L
    #   x_i == x_j and y_i >  y_j  ->  -infinity, represented by -L
    #   s_ij == -1                 ->  excluded (keeps x/y interchangeable)
    # L is arbitrary; it only has to sort beyond every finite slope.
    L = 1.0e6
    slopes = []
    for i in range(n):
        for j in range(i + 1, n):
            dx = x[j] - x[i]
            dy = y[j] - y[i]
            if dx == 0.0 and dy == 0.0:
                continue                      # identical points: 0/0
            elif dx == 0.0:
                s = L if dy > 0 else -L       # vertical pair
            else:
                s = dy / dx
            if s == -1.0:
                continue                      # excluded by the method
            slopes.append(s)

    slopes = np.sort(np.array(slopes, dtype=float))
    N = len(slopes)

    if N == 0:
        raise ValueError("No usable pairwise slopes; slope is undefined.")

    # K = number of slopes below -1 (the offset that makes x and y
    # interchangeable — Passing & Bablok 1983)
    K = int(np.sum(slopes < -1.0))

    # ── Shifted median ───────────────────────────────────────────────────────
    # N odd  = 2m+1 -> the (m+1+K)-th smallest      -> 0-based index m+K
    # N even = 2m   -> mean of (m+K)-th & (m+1+K)-th -> 0-based m+K-1, m+K
    def _at(rank0):
        return slopes[max(0, min(rank0, N - 1))]

    if N % 2 == 1:
        _m = (N - 1) // 2
        slope = _at(_m + K)
    else:
        _m = N // 2
        slope = 0.5 * (_at(_m - 1 + K) + _at(_m + K))

    # Intercept: median of (y_i - b*x_i)
    intercept = float(np.median(y - slope * x))

    # ── Rank-based confidence interval ───────────────────────────────────────
    # c  = z * sqrt( n(n-1)(2n+5) / 18 )
    # M1 = round((N - c)/2)      M2 = N - M1 + 1        (both 1-based RANKS)
    # b_lower = (M1+K)-th smallest      b_upper = (M2+K)-th smallest
    # Ranks are 1-based, so subtract 1 to index the sorted array.
    z = _z_score(ci)
    c = z * np.sqrt(n * (n - 1) * (2 * n + 5) / 18.0)

    M1 = int(np.round((N - c) / 2.0))
    M2 = N - M1 + 1

    slope_lower = float(_at(M1 + K - 1))
    slope_upper = float(_at(M2 + K - 1))

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
