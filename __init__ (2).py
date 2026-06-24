"""
Unit Tests — Passing–Bablok Regression Tool
=============================================
Run with:  python -m pytest tests/ -v
"""

import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analysis.regression import passing_bablok
from analysis.statistics import r_squared, pearson_r, summary_stats


# ── Regression tests ──────────────────────────────────────────────────────────

class TestPassingBablok:

    def test_perfect_identity(self):
        """y = x  →  slope=1, intercept=0."""
        rng = np.random.default_rng(42)
        x = rng.uniform(1, 100, 50)
        y = x.copy()
        res = passing_bablok(x, y)
        assert abs(res["slope"] - 1.0) < 1e-6
        assert abs(res["intercept"] - 0.0) < 1e-6

    def test_known_slope_intercept(self):
        """y = 2x + 5  →  slope≈2, intercept≈5."""
        x = np.arange(1, 51, dtype=float)
        y = 2.0 * x + 5.0
        res = passing_bablok(x, y)
        assert abs(res["slope"] - 2.0) < 1e-4
        assert abs(res["intercept"] - 5.0) < 1e-4

    def test_nan_handling(self):
        """NaN values are silently removed; result is still finite."""
        x = np.array([1, 2, np.nan, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        y = np.array([2, 4, 6, np.nan, 10, 12, 14, 16, 18, 20], dtype=float)
        res = passing_bablok(x, y)
        assert res["n_excluded"] == 2
        assert np.isfinite(res["slope"])
        assert np.isfinite(res["intercept"])

    def test_duplicate_x_values(self):
        """Duplicate x values (undefined slopes) must not crash."""
        x = np.array([1, 1, 2, 3, 4, 5, 5, 6, 7, 8], dtype=float)
        y = np.array([2, 2.1, 4, 6, 8, 10, 10.1, 12, 14, 16], dtype=float)
        res = passing_bablok(x, y)
        assert np.isfinite(res["slope"])
        assert np.isfinite(res["intercept"])

    def test_ci_bounds_ordered(self):
        """CI lower must be ≤ estimate ≤ CI upper."""
        rng = np.random.default_rng(0)
        x = rng.uniform(0, 100, 40)
        y = 1.5 * x + 3.0 + rng.normal(0, 2, 40)
        res = passing_bablok(x, y)
        assert res["slope_lower"] <= res["slope"] <= res["slope_upper"]
        assert res["intercept_lower"] <= res["intercept"] <= res["intercept_upper"]

    def test_n_too_small_raises(self):
        """Fewer than 3 valid points should raise ValueError."""
        with pytest.raises(ValueError):
            passing_bablok([1.0, 2.0], [1.0, 2.0])

    def test_result_keys(self):
        """Result dict must contain all expected keys."""
        x = np.arange(1.0, 21.0)
        y = 1.2 * x + 0.5
        res = passing_bablok(x, y)
        expected_keys = {
            "slope", "slope_lower", "slope_upper",
            "intercept", "intercept_lower", "intercept_upper",
            "n", "n_excluded",
        }
        assert expected_keys == set(res.keys())


# ── Statistics tests ───────────────────────────────────────────────────────────

class TestStatistics:

    def test_r_squared_perfect(self):
        """Perfect linear relationship → R² = 1.0."""
        x = np.arange(1.0, 51.0)
        y = 3.0 * x - 7.0
        assert abs(r_squared(x, y) - 1.0) < 1e-10

    def test_pearson_r_range(self):
        """Pearson r is always in [-1, 1]."""
        rng = np.random.default_rng(7)
        x = rng.standard_normal(100)
        y = rng.standard_normal(100)
        r = pearson_r(x, y)
        assert -1.0 <= r <= 1.0

    def test_r_squared_equals_pearson_squared(self):
        """R² must equal pearson_r ** 2."""
        rng = np.random.default_rng(3)
        x = rng.uniform(0, 50, 60)
        y = 0.9 * x + rng.normal(0, 3, 60)
        assert abs(r_squared(x, y) - pearson_r(x, y) ** 2) < 1e-12

    def test_handles_pandas_series(self):
        """Functions accept pandas Series as well as numpy arrays."""
        import pandas as pd
        s_x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        s_y = pd.Series([2.0, 4.0, 6.0, 8.0, 10.0])
        assert abs(r_squared(s_x, s_y) - 1.0) < 1e-10

    def test_summary_stats_keys(self):
        """summary_stats returns all expected keys."""
        x = np.arange(1.0, 11.0)
        y = x + 0.5
        result = summary_stats(x, y)
        for key in ("pearson_r", "r_squared", "bias", "mean_diff",
                    "std_diff", "loa_lower", "loa_upper"):
            assert key in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
