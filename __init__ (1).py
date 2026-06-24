"""
Regression Plot Module
======================
Generates publication-quality Passing–Bablok and Bland–Altman plots using Plotly.
"""

import numpy as np


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert a #RRGGBB hex colour to an rgba() CSS string."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.2f})"


def make_regression_plot(
    x,
    y,
    slope: float,
    intercept: float,
    slope_lower: float,
    slope_upper: float,
    intercept_lower: float,
    intercept_upper: float,
    r_squared: float,
    x_label: str = "Reference Method",
    y_label: str = "Candidate Method",
    title: str = "Passing–Bablok Method Comparison",
    # Colours
    color_scatter: str = "#2563EB",
    color_identity: str = "#9CA3AF",
    color_regression: str = "#DC2626",
    color_ci: str = "#DC2626",
    ci_alpha: float = 0.15,
    show_ci: bool = True,
    # Legend names
    legend_scatter: str = "Observations",
    legend_identity: str = "Identity (y = x)",
    legend_regression: str = "PB Regression",
    legend_ci: str = "95% CI",
    # Axis ranges — None means auto
    x_min: float = 0,
    x_max: float = None,
    y_min: float = 0,
    y_max: float = None,
    # Formatting
    decimals: int = 4,
):
    import plotly.graph_objects as go

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)

    # Resolve axis limits
    data_max = float(max(x.max(), y.max())) * 1.05
    x_min = float(x_min) if x_min is not None else 0.0
    x_max = float(x_max) if x_max is not None else data_max
    y_min = float(y_min) if y_min is not None else 0.0
    y_max = float(y_max) if y_max is not None else data_max

    x_line = np.linspace(x_min, x_max, 200)

    # PB regression line and CI band
    # The CI band is the envelope of the four corner lines (all combinations of
    # slope_lower/upper × intercept_lower/upper), which gives the correct
    # hyperbolic-shaped band for the Passing–Bablok method.
    y_pb = slope * x_line + intercept
    y_id = x_line

    y_ci_candidates = np.array([
        slope_lower * x_line + intercept_lower,
        slope_lower * x_line + intercept_upper,
        slope_upper * x_line + intercept_lower,
        slope_upper * x_line + intercept_upper,
    ])
    y_ci_low  = y_ci_candidates.min(axis=0)
    y_ci_high = y_ci_candidates.max(axis=0)

    def fmt(v):
        return f"{v:.{decimals}f}".replace(".", ",")

    # Show "y = mx − b" when intercept is negative, "y = mx + b" when positive
    if intercept < 0:
        intercept_str = f"− {fmt(abs(intercept))}"
    else:
        intercept_str = f"+ {fmt(intercept)}"

    # Bold equation box
    eq_text = (
        f"<b>y = {fmt(slope)}x {intercept_str}</b><br>"
        f"<b>R² = {fmt(r_squared)}</b><br>"
        f"<b>n = {n}</b>"
    )

    fig = go.Figure()

    # CI shaded band (add before lines so it sits underneath)
    if show_ci:
        ci_fill_color = _hex_to_rgba(color_ci, ci_alpha)
        ci_line_color = _hex_to_rgba(color_ci, 0.0)  # invisible border lines

        # Lower boundary (invisible, fills upward)
        fig.add_trace(go.Scatter(
            x=x_line, y=y_ci_low,
            mode="lines",
            line=dict(color=ci_line_color, width=0),
            showlegend=False,
            hoverinfo="skip",
            name="_ci_lower",
        ))
        # Upper boundary — fill to previous trace
        fig.add_trace(go.Scatter(
            x=x_line, y=y_ci_high,
            mode="lines",
            line=dict(color=ci_line_color, width=0),
            fill="tonexty",
            fillcolor=ci_fill_color,
            name=legend_ci,
            hoverinfo="skip",
        ))

    # Scatter points
    fig.add_trace(go.Scatter(
        x=x, y=y,
        mode="markers",
        name=legend_scatter,
        marker=dict(color=color_scatter, size=7, opacity=0.75,
                    line=dict(width=0.5, color="white")),
    ))

    # Identity line
    fig.add_trace(go.Scatter(
        x=x_line, y=y_id,
        mode="lines",
        name=legend_identity,
        line=dict(color=color_identity, width=1.5, dash="dash"),
    ))

    # PB regression line
    fig.add_trace(go.Scatter(
        x=x_line, y=y_pb,
        mode="lines",
        name=legend_regression,
        line=dict(color=color_regression, width=2.5),
    ))

    # Bold equation annotation box
    fig.add_annotation(
        x=0.04, y=0.97,
        xref="paper", yref="paper",
        text=eq_text,
        showarrow=False,
        align="left",
        bgcolor="rgba(255,255,255,0.90)",
        bordercolor="#9CA3AF",
        borderwidth=1.5,
        borderpad=10,
        font=dict(size=13, family="Courier New, monospace", color="#111827"),
    )

    fig.update_layout(
        title=dict(text=title, font=dict(size=16)),
        xaxis=dict(
            title=x_label,
            range=[x_min, x_max],
            showgrid=True,
            gridcolor="#F3F4F6",
            zeroline=True,
            zerolinecolor="#D1D5DB",
        ),
        yaxis=dict(
            title=y_label,
            range=[y_min, y_max],
            showgrid=True,
            gridcolor="#F3F4F6",
            zeroline=True,
            zerolinecolor="#D1D5DB",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(family="Inter, Arial, sans-serif"),
        margin=dict(l=60, r=30, t=80, b=60),
        height=520,
    )

    return fig


def make_bland_altman_plot(
    x,
    y,
    mean_diff: float,
    loa_lower: float,
    loa_upper: float,
    x_label: str = "Reference Method",
    y_label: str = "Candidate Method",
    # Y-axis mode
    pct_diff: bool = False,
    # Custom title — empty string means auto-generate
    title: str = "",
    # Colours
    color_scatter: str = "#2563EB",
    color_mean: str = "#DC2626",
    color_loa: str = "#F97316",
    # Annotation labels
    legend_scatter: str = "Difference",
    label_mean: str = "Mean",
    label_loa_upper: str = "+1,96 SD",
    label_loa_lower: str = "−1,96 SD",
    # Axis ranges — None means auto
    x_min: float = None,
    x_max: float = None,
    y_min: float = None,
    y_max: float = None,
    # Formatting
    decimals: int = 4,
):
    import plotly.graph_objects as go

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]

    means = (x + y) / 2.0

    if pct_diff:
        with np.errstate(divide="ignore", invalid="ignore"):
            diffs = np.where(means != 0, (y - x) / means * 100.0, np.nan)
        valid = np.isfinite(diffs)
        mean_d = float(np.mean(diffs[valid]))
        std_d  = float(np.std(diffs[valid], ddof=1))
        loa_lo = mean_d - 1.96 * std_d
        loa_hi = mean_d + 1.96 * std_d
        y_axis_title = f"Difference (%) ({y_label} − {x_label}) / mean × 100"
        pct_suffix = " %"
    else:
        diffs  = y - x
        mean_d = mean_diff
        loa_lo = loa_lower
        loa_hi = loa_upper
        y_axis_title = f"Difference ({y_label} − {x_label})"
        pct_suffix = ""

    def fmt(v):
        return f"{v:.{decimals}f}".replace(".", ",")

    means_clean = means[np.isfinite(diffs)]
    diffs_clean = diffs[np.isfinite(diffs)]

    x_pad = (means_clean.max() - means_clean.min()) * 0.08
    resolved_x_min = float(x_min) if x_min is not None else float(means_clean.min()) - x_pad
    resolved_x_max = float(x_max) if x_max is not None else float(means_clean.max()) + x_pad

    y_pad = (diffs_clean.max() - diffs_clean.min()) * 0.15
    resolved_y_min = float(y_min) if y_min is not None else float(diffs_clean.min()) - y_pad
    resolved_y_max = float(y_max) if y_max is not None else float(diffs_clean.max()) + y_pad

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=means, y=diffs,
        mode="markers",
        name=legend_scatter,
        marker=dict(color=color_scatter, size=7, opacity=0.75,
                    line=dict(width=0.5, color="white")),
    ))

    fig.add_hline(
        y=mean_d,
        line=dict(color=color_mean, width=2),
        annotation_text=f"{label_mean}: {fmt(mean_d)}{pct_suffix}",
        annotation_position="right",
        annotation_font=dict(color=color_mean, size=11),
    )

    fig.add_hline(
        y=loa_hi,
        line=dict(color=color_loa, width=1.5, dash="dash"),
        annotation_text=f"{label_loa_upper}: {fmt(loa_hi)}{pct_suffix}",
        annotation_position="right",
        annotation_font=dict(color=color_loa, size=11),
    )

    fig.add_hline(
        y=loa_lo,
        line=dict(color=color_loa, width=1.5, dash="dash"),
        annotation_text=f"{label_loa_lower}: {fmt(loa_lo)}{pct_suffix}",
        annotation_position="right",
        annotation_font=dict(color=color_loa, size=11),
    )

    fig.add_hline(y=0, line=dict(color="#9CA3AF", width=1, dash="dot"))

    fig.update_layout(
        title=dict(
            text=title if title else ("Bland–Altman Plot" + (" (% difference)" if pct_diff else "")),
            font=dict(size=16),
        ),
        xaxis=dict(
            title=f"Mean of {x_label} and {y_label}",
            range=[resolved_x_min, resolved_x_max],
            showgrid=True, gridcolor="#F3F4F6", zeroline=False,
        ),
        yaxis=dict(
            title=y_axis_title,
            range=[resolved_y_min, resolved_y_max],
            showgrid=True, gridcolor="#F3F4F6", zeroline=False,
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
        font=dict(family="Inter, Arial, sans-serif"),
        margin=dict(l=60, r=160, t=80, b=60),
        height=520,
    )

    return fig
