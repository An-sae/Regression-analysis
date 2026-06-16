"""
Deming Regression Module
========================
Implements ordinary Deming regression and weighted Deming regression
for method-comparison studies.

References:
    Deming WE. Statistical Adjustment of Data. 1943.
    Linnet K. Estimation of the linear relationship between the measurements
    of two methods with proportional errors. Stat Med. 1990;9(12):1463-1473.
"""

import numpy as np
from typing import Dict
from scipy.stats import t as t_dist


def deming(
    x: np.ndarray,
    y: np.ndarray,
    error_ratio: float = 1.0,
    ci: float = 0.95,
) -> Dict[str, float]:
    """
    Ordinary Deming regression.

    Assumes the ratio of measurement error variances (Var_y / Var_x) is
    constant and equal to `error_ratio` (lambda).  When lambda = 1 the
    method is equivalent to orthogonal regression.

    Parameters
    ----------
    x           : reference method values
    y           : candidate method values
    error_ratio : lambda = Var(y_error) / Var(x_error).
                  1.0 = equal error variances (default / orthogonal).
                  Use e.g. (CV_y/CV_x)^2 for proportional errors.
    ci          : confidence interval level (default 0.95)

    Returns
    -------
    dict with slope, slope_lower, slope_upper,
              intercept, intercept_lower, intercept_upper,
              n, n_excluded
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    mask = np.isfinite(x) & np.isfinite(y)
    n_excluded = int(np.sum(~mask))
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3:
        raise ValueError(f"Need at least 3 valid observations; got {n}.")

    lam = float(error_ratio)

    x_bar = np.mean(x)
    y_bar = np.mean(y)
    sxx = np.var(x, ddof=1)
    syy = np.var(y, ddof=1)
    sxy = np.cov(x, y, ddof=1)[0, 1]

    # Deming slope (Linnet 1990 formula)
    slope = ((syy - lam * sxx) +
             np.sqrt((syy - lam * sxx) ** 2 + 4 * lam * sxy ** 2)) / (2 * sxy)
    intercept = y_bar - slope * x_bar

    # Jackknife CIs (robust, no distributional assumption)
    slope_jk    = np.empty(n)
    intercept_jk = np.empty(n)
    for i in range(n):
        xi = np.delete(x, i)
        yi = np.delete(y, i)
        sxx_i = np.var(xi, ddof=1)
        syy_i = np.var(yi, ddof=1)
        sxy_i = np.cov(xi, yi, ddof=1)[0, 1]
        if sxy_i == 0:
            slope_jk[i] = slope
        else:
            slope_jk[i] = (
                (syy_i - lam * sxx_i) +
                np.sqrt((syy_i - lam * sxx_i) ** 2 + 4 * lam * sxy_i ** 2)
            ) / (2 * sxy_i)
        intercept_jk[i] = np.mean(yi) - slope_jk[i] * np.mean(xi)

    alpha = 1.0 - ci
    t_crit = float(t_dist.ppf(1 - alpha / 2, df=n - 2))

    se_slope     = np.std(slope_jk,     ddof=1) * np.sqrt((n - 1) ** 2 / n)
    se_intercept = np.std(intercept_jk, ddof=1) * np.sqrt((n - 1) ** 2 / n)

    return {
        "slope":           float(slope),
        "slope_lower":     float(slope)     - t_crit * se_slope,
        "slope_upper":     float(slope)     + t_crit * se_slope,
        "intercept":       float(intercept),
        "intercept_lower": float(intercept) - t_crit * se_intercept,
        "intercept_upper": float(intercept) + t_crit * se_intercept,
        "n":          n,
        "n_excluded": n_excluded,
    }


def weighted_deming(
    x: np.ndarray,
    y: np.ndarray,
    error_ratio: float = 1.0,
    ci: float = 0.95,
) -> Dict[str, float]:
    """
    Weighted Deming regression (Linnet 1990).

    Weights are proportional to 1 / (x² + y²/lambda), which accounts for
    the fact that measurement imprecision is proportional to concentration
    (constant CV model). This is the standard approach for clinical chemistry.

    Parameters
    ----------
    x           : reference method values
    y           : candidate method values
    error_ratio : lambda = (CV_y / CV_x)^2.  Default 1.0 (equal CVs).
    ci          : confidence interval level (default 0.95)
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    mask = np.isfinite(x) & np.isfinite(y) & (x != 0) & (y != 0)
    n_excluded = int(np.sum(~mask))
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3:
        raise ValueError(f"Need at least 3 valid observations; got {n}.")

    lam = float(error_ratio)

    # Weights: w_i = 1 / (x_i^2 + y_i^2 / lambda)   [Linnet 1990, eq. 3]
    w = 1.0 / (x ** 2 + y ** 2 / lam)
    w /= w.sum()   # normalise so they sum to 1

    x_bar = np.sum(w * x)
    y_bar = np.sum(w * y)
    sxx = np.sum(w * (x - x_bar) ** 2)
    syy = np.sum(w * (y - y_bar) ** 2)
    sxy = np.sum(w * (x - x_bar) * (y - y_bar))

    denom = 2 * sxy
    if denom == 0:
        raise ValueError("Weighted covariance is zero; slope is undefined.")

    slope = ((syy - lam * sxx) +
             np.sqrt((syy - lam * sxx) ** 2 + 4 * lam * sxy ** 2)) / denom
    intercept = y_bar - slope * x_bar

    # Jackknife CIs
    slope_jk    = np.empty(n)
    intercept_jk = np.empty(n)
    for i in range(n):
        xi = np.delete(x, i)
        yi = np.delete(y, i)
        wi = np.delete(w, i)
        wi /= wi.sum()
        xb = np.sum(wi * xi)
        yb = np.sum(wi * yi)
        sxx_i = np.sum(wi * (xi - xb) ** 2)
        syy_i = np.sum(wi * (yi - yb) ** 2)
        sxy_i = np.sum(wi * (xi - xb) * (yi - yb))
        if sxy_i == 0:
            slope_jk[i] = slope
        else:
            slope_jk[i] = (
                (syy_i - lam * sxx_i) +
                np.sqrt((syy_i - lam * sxx_i) ** 2 + 4 * lam * sxy_i ** 2)
            ) / (2 * sxy_i)
        intercept_jk[i] = np.mean(yi) - slope_jk[i] * np.mean(xi)

    alpha = 1.0 - ci
    t_crit = float(t_dist.ppf(1 - alpha / 2, df=n - 2))

    se_slope     = np.std(slope_jk,     ddof=1) * np.sqrt((n - 1) ** 2 / n)
    se_intercept = np.std(intercept_jk, ddof=1) * np.sqrt((n - 1) ** 2 / n)

    return {
        "slope":           float(slope),
        "slope_lower":     float(slope)     - t_crit * se_slope,
        "slope_upper":     float(slope)     + t_crit * se_slope,
        "intercept":       float(intercept),
        "intercept_lower": float(intercept) - t_crit * se_intercept,
        "intercept_upper": float(intercept) + t_crit * se_intercept,
        "n":          n,
        "n_excluded": n_excluded,
    }
