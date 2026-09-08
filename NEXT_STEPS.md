# Next Steps — Method Comparison Tool

---

## Immediate Priorities

### 1. Fix dead code — remove `_read_excel()` (BUG-001)
Remove the unused function at app.py lines 110–113. Verify nothing calls it (grep confirms: zero calls).

### 2. Add session state caching to precision branch (LIMITATION-002)
Store `_pr_data_dict` and `_pr` in `st.session_state` after first calculation, keyed to a hash of the uploaded file bytes. This prevents re-processing on every widget change. Pattern already exists in the regression branch.

### 3. Unify decimal place defaults (BUG-003)
Change the precision branch `prec_decimals` slider default from 4 to 2 to match the regression branch convention.

---

## Short-Term Improvements

### 4. Add tests for Deming, confusion matrix, and precision (BUG-004)
Add to `tests/test_regression.py` or create separate files:
- `tests/test_deming.py` — verify known slope/intercept for simple linear data; jackknife CI bounds
- `tests/test_confusion.py` — verify EA, CA, VME/ME counts against manually calculated values
- `tests/test_precision.py` — reproduce Chesher 2008 Table 1 (Sr ≈ 0.0235, Sl ≈ 0.0262) exactly

### 5. Vectorise Passing–Bablok for large datasets (BUG-002)
Replace the O(n²) Python double-loop with numpy vectorisation:
```python
diffs_y = y[:, None] - y[None, :]
diffs_x = x[:, None] - x[None, :]
mask = diffs_x != 0
slopes = np.sort((diffs_y[mask] / diffs_x[mask]))
```
Keep the existing loop as fallback for very small n. Benchmark threshold: n > 200.

### 6. Clean up dead kaleido code in `export.py` (TECHNICAL-DEBT-002)
Delete `fig_to_png_bytes()`, `fig_to_svg_bytes()`, `_sanitize_fig()`, `_strip_html_tags()`. These are never called.

### 7. Add Streamlit password protection
Implement simple access control for the public deployment using Streamlit secrets:
```python
# In app.py, near the top:
import hmac
def check_password():
    ...
if not check_password():
    st.stop()
```
See Streamlit docs for the canonical pattern. Store password in `.streamlit/secrets.toml` (local) and Streamlit Cloud secrets (deployed).

---

## Future Features

### 8. Multiple concentration levels for precision
EP15-A3 requires testing at ≥ 2 concentration levels. The current precision module handles one level at a time. A future version could accept multiple sheets/levels and report results side by side, with the chi-square Bonferroni correction (`n_levels` parameter) automatically set.

### 9. Deming regression CI using parametric formula
Currently uses jackknife resampling for Deming CIs. The parametric formula from Linnet 1990 could be implemented as an alternative — faster and the standard approach.

### 10. Bland–Altman regression (Passing–Bablok on differences)
Some journals request a regression of (y−x) on (x+y)/2 to test for proportional bias. Could be added as an option within the Bland–Altman tab.

### 11. Export both plots as a combined single PDF
Users paste into Word individually. A combined PDF with both plots on one page would simplify submission to journals.

### 12. Multi-language support
The application uses Swedish number conventions (comma decimals) but the UI is in English. Supporting Swedish UI text would benefit the primary user group.

### 13. Interpretive guidance text
After showing results, add a brief automatic interpretation: e.g. "Slope 95% CI includes 1.0 → no proportional bias detected" or "EA ±2 mm = 94% (above 90% threshold — PASS)". This would reduce the need for the user to consult references.

---

## Existing Requirements to Preserve (Not Recommendations)

The following were explicitly requested during development and must be maintained:

- Comma as decimal separator in all numeric output
- Downloaded images auto-sized from DPI (no manual pixel entry)
- Confusion matrix colour = distance from diagonal, not count
- n = total shown outside the matrix frame in italic
- Regression session state survives sidebar widget changes
- No kaleido dependency (crashes on target Windows environment)
- BA plot: y-axis = "Difference" or "Difference (%)", x-axis = "Mean"
- Precision output leads with CV (bold/large), SD (smaller)
- Journal-style precision export (days as rows, replicates + stats as columns)

