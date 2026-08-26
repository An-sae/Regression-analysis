# Method Comparison Tool

A professional, self-contained web application for analytical method comparison in clinical microbiology and clinical chemistry. Implements three complementary analysis workflows, all accessible from a single sidebar.

---

## Features at a glance

| Module | What it does |
|---|---|
| **Passing–Bablok regression** | Non-parametric, rank-based method comparison — resistant to outliers and non-normality |
| **Deming regression** | Error-in-both-variables regression; ordinary (equal variances) or weighted (proportional CV) |
| **Confusion matrix** | Zone diameter agreement matrix with essential agreement, categorical agreement, VME and ME |
| **Bland–Altman plot** | Bias and limits of agreement; absolute or percentage difference on y-axis |
| **Data filtering** | Filter rows by any categorical column (e.g. organism, antibiotic, lab site) before analysis |
| **Export** | High-resolution PNG (150 / 300 / 600 dpi) and SVG (vector) for all plots; CSV and HTML report |

---

## Quick start

```bash
# 1. Install dependencies (once)
pip install -r requirements.txt

# 2. Launch
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## Project structure

```
pb_tool/
├── app.py                        # Streamlit application — single entry point
├── requirements.txt
├── README.md
│
├── analysis/
│   ├── regression.py             # Passing–Bablok algorithm
│   ├── deming.py                 # Deming & weighted Deming regression
│   ├── statistics.py             # Pearson r, R², bias, Bland–Altman LoA
│   ├── confusion.py              # Count matrix, EA, CA, VME, ME
│   └── export.py                 # CSV, HTML report, DPI helpers
│
├── plots/
│   ├── regression_plot.py        # Interactive Plotly regression & BA plots
│   ├── confusion_plot.py         # Interactive Plotly confusion matrix
│   └── mpl_export.py             # Matplotlib static PNG/SVG export
│
├── tests/
│   └── test_regression.py        # Unit tests
│
└── data/
    └── sample.csv                # Example dataset
```

---

## Detailed feature reference

### Analysis types

#### 1. Passing–Bablok regression
- Non-parametric, distribution-free regression suitable for method comparison
- Slope and intercept estimated from the median of all pairwise slopes
- 95 % confidence intervals via the Passing–Bablok rank-based method
- Resistant to outliers and does not assume normal error distribution

#### 2. Deming regression
- Accounts for measurement error in **both** methods (errors-in-variables model)
- **Ordinary Deming**: assumes constant, equal error variances (λ = 1); equivalent to orthogonal regression
- **Weighted Deming**: assumes errors proportional to concentration (constant CV model); weights ∝ 1/(x² + y²/λ); standard approach for clinical chemistry (Linnet 1990)
- Error ratio λ = Var(y_error) / Var(x_error) is user-specified; for proportional errors use λ = (CV_candidate / CV_reference)²
- Confidence intervals via jackknife resampling

#### 3. Confusion matrix (zone diameter comparison)
- Visual comparison of zone diameters from two measurement methods (e.g. digital caliper vs. ruler)
- Each cell shows the count of isolates where reference method = x mm and candidate method = y mm
- **Colour encodes distance from the identity diagonal** — not count: darkest = exact agreement, fading to white at the user-defined EA boundary
- Diagonal boundary lines mark exact agreement (solid) and the EA window (dotted)
- *n* = total shown outside the frame in scientific italic notation

### Agreement statistics (confusion matrix)

| Metric | Definition |
|---|---|
| **Essential Agreement ±1 mm** | % of isolates where \|x − y\| ≤ 1 mm |
| **Essential Agreement ±2 mm** | % of isolates where \|x − y\| ≤ 2 mm |
| **Categorical Agreement** | % of isolates assigned the same S/I/R category by both methods |
| **Very Major Error (VME)** | Reference = S, candidate = R; expressed as % of S isolates |
| **Major Error (ME)** | Reference = R, candidate = S; expressed as % of R isolates |

Breakpoints for categorical classification are entered per method (separate S and R thresholds for x and y) and support both EUCAST and CLSI systems.

**EUCAST / CLSI acceptability criteria:**

| Metric | EUCAST threshold | CLSI threshold |
|---|---|---|
| Essential Agreement ±2 mm | ≥ 90 % | ≥ 90 % |
| Categorical Agreement | ≥ 90 % | ≥ 90 % |
| Very Major Error | ≤ 3 % of S isolates | ≤ 1.5 % |
| Major Error | ≤ 3 % of R isolates | ≤ 3 % |

### Bland–Altman plot
- Y-axis: absolute difference (y − x) **or** percentage difference ((y − x) / mean × 100 %)
- Displays mean bias (red solid line) and ±1.96 SD limits of agreement (orange dashed)
- Dotted reference line at zero

### Data input
- **Upload**: CSV or Excel (.xlsx / .xls)
  - Sheet/tab selector for multi-sheet workbooks
  - Header row toggle (yes / no)
  - Column selectors for x and y
  - **Row filter**: if the file contains text columns (e.g. organism name, antibiotic, lab site), an optional multi-select filter appears automatically — deselect values to exclude them before analysis
- **Paste**: copy two columns directly from Excel and paste; accepts comma or point as decimal separator, tab or semicolon as column separator; header rows are auto-skipped

### Customisation
- Method names (x-axis and y-axis labels)
- Graph titles (regression plot and Bland–Altman plot separately)
- Decimal places (1–8, applies to results table and plot annotations)
- Axis min/max for all four plots independently
- Colour pickers for scatter points, regression line, identity line, CI band, Bland–Altman lines
- Legend names for every series
- CI band transparency slider
- Confusion matrix: colour band width, base colour, cell font size, number colour (on coloured cells and on white cells separately), bold toggle

### Export
- **PNG**: 150 / 300 / 600 dpi; dimensions auto-calculated so every cell/point is physically the same size regardless of resolution
- **SVG**: resolution-independent vector file; insert via Insert → Pictures in Word, PowerPoint, or Excel
- **HTML report**: self-contained interactive file with both plots (Plotly) and a statistics table
- **Results CSV**: all numerical results including CI bounds
- **Confusion matrix CSV**: raw count matrix

---

## Running tests

```bash
python -m pytest tests/ -v
# or without pytest:
python tests/test_regression.py
```

---

## References

1. **Passing H, Bablok W.** A new biometrical procedure for testing the equality of measurements from two different analytical methods. *J Clin Chem Clin Biochem.* 1983;21(11):709–720. https://doi.org/10.1515/cclm.1983.21.11.709

2. **Deming WE.** *Statistical Adjustment of Data.* New York: Wiley; 1943.

3. **Linnet K.** Estimation of the linear relationship between the measurements of two methods with proportional errors. *Stat Med.* 1990;9(12):1463–1473. https://doi.org/10.1002/sim.4780091210

4. **Bland JM, Altman DG.** Statistical methods for assessing agreement between two methods of clinical measurement. *Lancet.* 1986;327(8476):307–310. https://doi.org/10.1016/S0140-6736(86)90837-8

5. **EUCAST.** Disk diffusion method for antimicrobial susceptibility testing. *EUCAST Disk Diffusion Implementation Guide v10.0.* 2023. https://www.eucast.org/ast_of_bacteria/disk_diffusion_methodology/

6. **CLSI.** Verification of Commercial Microbial Identification and Antimicrobial Susceptibility Testing Systems; Approved Standard. *CLSI document M52.* Wayne, PA: Clinical and Laboratory Standards Institute; 2015.

7. **CLSI.** Method Comparison and Bias Estimation Using Patient Samples; Approved Guideline. *CLSI document EP09c.* Wayne, PA: Clinical and Laboratory Standards Institute; 2018.

8. **Carstensen B.** Comparing Clinical Measurement Methods: A Practical Guide. Chichester: Wiley; 2010.

---

## License

MIT

---

## Precision Evaluation (EP15-A3)

### Overview

Estimates repeatability (within-run) and within-laboratory (total) imprecision following **CLSI EP15-A3** (2014). Computes SD and CV for both components and optionally performs a chi-square verification test against manufacturer-claimed values.

### Protocol

- **Recommended design**: 5 replicates per day × 5 days at ≥ 2 concentration levels
- **Minimum**: 2 replicates per day × 2 days

### Statistics

| Statistic | Symbol | Formula |
|---|---|---|
| Within-run SD | Sᵣ | √[ Σ_d Σ_r (x_dr − x̄_d)² / D(n−1) ] |
| Between-day SD | S_b | √[ max(0, s_day² − Sᵣ²/n) ] |
| Within-laboratory SD | S_l | √( Sᵣ² + S_b² ) |
| Verification value (Sᵣ) | — | σᵣ × √[ χ²(1−α/q, df) / df ] |

### Data format

One **column per day**, one **row per replicate**. Column headers are used as day labels.

```
Day 1    Day 2    Day 3    Day 4    Day 5
2.015    2.019    2.025    1.972    1.981
2.013    2.002    1.959    1.950    1.956
1.963    1.979    2.000    1.973    1.957
2.001    2.010    1.988    1.965    1.970
1.998    1.995    2.005    1.980    1.975
```

Upload as Excel / CSV or paste directly from Excel. Comma or point accepted as decimal.

### References

- CLSI EP15-A3. *User Verification of Precision and Estimation of Bias; Approved Guideline — Third Edition.* Wayne, PA: CLSI; 2014.
- Chesher D. Evaluating Assay Precision. *Clin Biochem Rev.* 2008;29(Suppl i):S23–S26.
