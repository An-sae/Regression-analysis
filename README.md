# Deming and Passing–Bablok Regression Tool

A professional, self-contained web application for method-comparison studies using **Passing–Bablok and Deming regression** — a robust, non-parametric technique endorsed by CLSI EP09 for evaluating analytical method equivalence.

## Features

| Feature | Detail |
|---|---|
| **Regression** | Passing–Bablok and Deming slope & intercept with 95 % rank-based CIs |
| **Correlation** | Pearson r, R², Bland–Altman bias & limits of agreement |
| **Plot** | Interactive Plotly scatter with identity line, regression line, and annotation box |
| **Export** | CSV results, PNG figure, self-contained HTML report |
| **Interface** | Streamlit web app — no coding required |

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Launch the app
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Usage

1. Upload a **CSV** or **Excel** file containing two numeric columns.
2. Select which column is the **reference method** and which is the **candidate method**.
3. Click **Analyze**.
4. Download results as CSV, PNG, or an HTML report.

## Project Structure

```
pb_tool/
├── app.py                    # Streamlit application entry point
├── requirements.txt
├── analysis/
│   ├── regression.py         # Passing–Bablok algorithm
│   ├── statistics.py         # Pearson r, R², bias, LoA
│   └── export.py             # CSV / PNG / HTML export
├── plots/
│   └── regression_plot.py    # Plotly figure factory
├── tests/
│   └── test_regression.py    # Unit tests
└── data/
    └── sample.csv            # Example data
```

## Running Tests

```bash
python -m pytest tests/ -v
# or without pytest:
python tests/test_regression.py
```

## Statistical Reference

Passing H, Bablok W. *A new biometrical procedure for testing the equality of measurements from two different analytical methods.* J Clin Chem Clin Biochem. 1983;21(11):709–720.

## License

MIT
