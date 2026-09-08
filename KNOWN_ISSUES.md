# Known Issues — Method Comparison Tool

---

## BUG-001 — Dead code: `_read_excel()` function never called

**What happens:** `_read_excel()` is defined at app.py lines 110–113 but is never called anywhere. The actual Excel loading happens inline inside the sidebar try/except block.

**Where:** app.py lines 110–113

**Possible cause:** Function was left over from an earlier refactor when data loading was extracted to a helper, then the helper was inlined again but the definition was not removed.

**Urgency:** Low — cosmetic only. Does not affect functionality.

**Workaround:** None needed. The code works correctly without it.

---

## BUG-002 — Passing–Bablok O(n²) performance

**What happens:** For large datasets (n > 500 pairs), the pairwise slope computation in `passing_bablok()` becomes noticeably slow (seconds). At n = 1000 it may take 10–30 seconds.

**Where:** `analysis/regression.py`, the double for-loop computing all pairwise slopes.

**Possible cause:** The algorithm is inherently O(n²) — this is fundamental to the Passing–Bablok method. The current implementation uses a Python loop rather than a vectorised approach.

**Urgency:** Medium — clinical datasets are usually < 200 samples so this rarely matters in practice.

**Workaround:** Vectorise using `np.subtract.outer()` or similar. The sorted slopes array could be computed as:
```python
diffs_y = y[:, None] - y[None, :]
diffs_x = x[:, None] - x[None, :]
mask = diffs_x != 0
slopes = np.sort((diffs_y[mask] / diffs_x[mask]))
```

---

## BUG-003 — Decimal places inconsistency between branches

**What happens:** The regression branch `decimals` slider defaults to 2. The precision branch `prec_decimals` slider defaults to 4. These are completely independent controls. If a user switches between analysis types, the decimal places will differ.

**Where:** app.py line 288 (regression: `st.slider("Decimals",1,8,2,key="dec")`) vs line 361 (precision: `st.slider("Decimal places in results", 1, 6, 4, key="pr_dec")`).

**Urgency:** Low — cosmetic inconsistency.

**Workaround:** None needed. Change precision default to 2 to match if desired.

---

## BUG-004 — No unit tests for Deming, confusion matrix, or precision

**What happens:** `tests/test_regression.py` contains 8 tests for Passing–Bablok only. Deming regression, confusion matrix statistics, and precision calculations have no automated test coverage.

**Where:** `tests/test_regression.py`

**Urgency:** Medium — changes to these modules carry higher risk.

**Workaround:** Manual testing. The Chesher 2008 paper provides reference values for precision verification (Sr ≈ 0.0235, Sl ≈ 0.0262 for Table 1 data).

---

## LIMITATION-001 — Confusion matrix always requires two-column data format

**What happens:** The confusion matrix uses the same x/y data columns as the regression analysis. There is no way to input pre-aggregated count data (e.g. a matrix that already exists).

**Urgency:** Low — the current workflow (raw replicate data → auto-build matrix) is correct for clinical use.

---

## LIMITATION-002 — Precision branch has no session state

**What happens:** Every sidebar widget change re-renders the precision branch and re-reads/re-parses the uploaded file. If the user uploaded a file, then changes the decimal places slider, the file is re-processed from the beginning.

**Urgency:** Low — precision files are small and processing is fast.

**Workaround:** Add session state caching for the parsed `_pr_data_dict` and `_pr` results, similar to how regression results are cached.

---

## LIMITATION-003 — GitHub Actions wake script requires manual STREAMLIT_URL setup

**What happens:** The `.github/workflows/keep_awake.yml` workflow fails silently if the `STREAMLIT_URL` repository variable is not set.

**Where:** `.github/scripts/wake_streamlit.py` line 7.

**Urgency:** Medium — app will sleep without this.

**Workaround:** Set the variable at GitHub repository Settings → Variables → Actions → New repository variable → Name: `STREAMLIT_URL`, Value: the full Streamlit app URL.

---

## LIMITATION-004 — No password / authentication

**What happens:** The app is publicly accessible on Streamlit Community Cloud. Anyone with the URL can use it.

**Urgency:** Depends on data sensitivity. No patient-identifiable data should be uploaded to the public deployment.

**Workaround:** Streamlit Community Cloud supports simple password protection via `st.secrets` — not currently implemented.

---

## TECHNICAL-DEBT-001 — Heavily procedural app.py

**What happens:** `app.py` is 996 lines of linear procedural code. All sidebar logic, data loading, and main area rendering is in a single file with underscore-prefixed local variables throughout.

**Impact:** Adding new features requires careful reading of the variable scoping and defaults pattern. Refactoring into pages or separate modules would improve maintainability.

**Urgency:** Low — the current structure works and is stable.

---

## TECHNICAL-DEBT-002 — `export.py` contains unused kaleido functions

**What happens:** `fig_to_png_bytes()`, `fig_to_svg_bytes()`, `_sanitize_fig()`, and `_strip_html_tags()` in `export.py` are never called in the running application (kaleido was abandoned). They remain as dead code.

**Urgency:** Low — can be safely deleted if desired.

