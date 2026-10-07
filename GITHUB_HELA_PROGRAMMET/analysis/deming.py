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


def _wdeming_fit(x, y, lam_n, tol=1e-12, max_iter=100):
    """
    Linnet (1993) iteratively re-weighted Deming regression, as documented in
    NCSS chapter 303 and implemented in the R package mcr.

    lam_n = Var(error in x) / Var(error in y)   (NCSS / mcr convention)

    Weights w_i = 1 / ((X^_i + lam_n*Y^_i) / (1 + lam_n))^2 are computed from
    the ESTIMATED TRUE VALUES and the fit is iterated until the coefficients
    converge. The first iteration is unweighted.
    """
    n = len(x)
    w = np.ones(n)
    b0 = b1 = None
    for _ in range(max_iter):
        xw = np.sum(w * x) / np.sum(w)
        yw = np.sum(w * y) / np.sum(w)
        u = np.sum(w * (x - xw) ** 2)
        q = np.sum(w * (y - yw) ** 2)
        p = np.sum(w * (x - xw) * (y - yw))
        if p == 0:
            raise ValueError("Weighted covariance is zero; slope is undefined.")
        nb1 = ((lam_n * q - u) +
               np.sqrt((u - lam_n * q) ** 2 + 4 * lam_n * p ** 2)) / (2 * lam_n * p)
        nb0 = yw - nb1 * xw
        if b1 is not None and abs(nb1 - b1) < tol and abs(nb0 - b0) < tol:
            return nb0, nb1
        b0, b1 = nb0, nb1
        d = y - (b0 + b1 * x)
        xh = x + lam_n * b1 * d / (1 + lam_n * b1 ** 2)
        yh = y - d / (1 + lam_n * b1 ** 2)
        denom_w = (xh + lam_n * yh) / (1 + lam_n)
        if np.any(denom_w == 0):
            raise ValueError("Estimated true value of zero; weights undefined.")
        w = 1.0 / denom_w ** 2
    return b0, b1


def weighted_deming(
    x: np.ndarray,
    y: np.ndarray,
    error_ratio: float = 1.0,
    ci: float = 0.95,
) -> Dict[str, float]:
    """
    Weighted Deming regression for proportional (constant-CV) errors,
    Linnet (1993). Iteratively re-weighted; jackknife confidence intervals
    with N - 2 degrees of freedom (CLSI EP09-A3 Appendix H).

    Verified against the published NCSS/R-mcr example (NCSS ch. 303,
    Example 6): all six reported values reproduced to 7 decimals.

    Parameters
    ----------
    x           : reference method values
    y           : candidate method values
    error_ratio : lambda = Var(error in y) / Var(error in x)   (this app's
                  convention; NCSS and mcr use the reciprocal).
    ci          : confidence level (default 0.95)
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    mask = np.isfinite(x) & np.isfinite(y) & (x != 0) & (y != 0)
    n_excluded = int(np.sum(~mask))
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3:
        raise ValueError(f"Need at least 3 valid observations; got {n}.")

    lam_n = 1.0 / float(error_ratio)      # convert to NCSS/mcr convention

    intercept, slope = _wdeming_fit(x, y, lam_n)

    # Jackknife: the COMPLETE iterative fit is repeated leaving out each pair
    jk = np.array([_wdeming_fit(np.delete(x, i), np.delete(y, i), lam_n)
                   for i in range(n)])
    se_intercept = np.sqrt((n - 1) / n * np.sum((jk[:, 0] - jk[:, 0].mean()) ** 2))
    se_slope     = np.sqrt((n - 1) / n * np.sum((jk[:, 1] - jk[:, 1].mean()) ** 2))

    t_crit = float(t_dist.ppf(1 - (1.0 - ci) / 2, df=n - 2))

    return {
        "slope":           float(slope),
        "slope_lower":     float(slope - t_crit * se_slope),
        "slope_upper":     float(slope + t_crit * se_slope),
        "intercept":       float(intercept),
        "intercept_lower": float(intercept - t_crit * se_intercept),
        "intercept_upper": float(intercept + t_crit * se_intercept),
        "n":          n,
        "n_excluded": n_excluded,
    }
