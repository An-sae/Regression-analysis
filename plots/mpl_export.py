"""
Matplotlib Export Module
========================
Renders publication-quality PNG and SVG figures using matplotlib.
Completely independent of kaleido — works on any platform.
"""

import io
import textwrap
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ── helpers ───────────────────────────────────────────────────────────────────

def _hex_to_rgba_mpl(hex_color: str, alpha: float):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r / 255, g / 255, b / 255, alpha


def _wrap_label(text: str, max_chars: int = 40) -> str:
    return "\n".join(textwrap.wrap(text, max_chars))


def _fig_size(width_px: int, height_px: int, dpi: int):
    return width_px / dpi, height_px / dpi


def _eq_str(slope, intercept, r_squared, n, decimals, fmt_fn):
    """Build equation string handling negative intercept correctly."""
    sl  = fmt_fn(slope)
    r2  = fmt_fn(r_squared)
    if intercept < 0:
        ic = f"− {fmt_fn(abs(intercept))}"
    else:
        ic = f"+ {fmt_fn(intercept)}"
    return f"y = {sl}x {ic}\nR² = {r2}\nn = {n}"


# ── Passing–Bablok plot ───────────────────────────────────────────────────────

def render_pb_png(
    x, y,
    slope, intercept,
    slope_lower, slope_upper,
    intercept_lower, intercept_upper,
    r_squared,
    x_label="Reference Method",
    y_label="Candidate Method",
    title="Passing–Bablok Method Comparison",
    color_scatter="#2563EB",
    color_identity="#9CA3AF",
    color_regression="#DC2626",
    color_ci="#DC2626",
    ci_alpha=0.15,
    show_ci=True,
    legend_scatter="Observations",
    legend_identity="Identity (y = x)",
    legend_regression="PB Regression",
    legend_ci="95% CI",
    x_min=0, x_max=None,
    y_min=0, y_max=None,
    decimals=4,
    dpi=300,
    width_px=1400,
    height_px=1040,
    fmt_fn=None,
):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)

    data_max = float(max(x.max(), y.max())) * 1.05
    x_min = float(x_min) if x_min is not None else 0.0
    x_max = float(x_max) if x_max is not None else data_max
    y_min = float(y_min) if y_min is not None else 0.0
    y_max = float(y_max) if y_max is not None else data_max

    xx = np.linspace(x_min, x_max, 300)

    fig, ax = plt.subplots(figsize=_fig_size(width_px, height_px, dpi), dpi=dpi)

    if show_ci:
        candidates = np.array([
            slope_lower * xx + intercept_lower,
            slope_lower * xx + intercept_upper,
            slope_upper * xx + intercept_lower,
            slope_upper * xx + intercept_upper,
        ])
        ci_lo = candidates.min(axis=0)
        ci_hi = candidates.max(axis=0)
        ci_rgba = _hex_to_rgba_mpl(color_ci, ci_alpha)
        ax.fill_between(xx, ci_lo, ci_hi,
                        color=ci_rgba[:3], alpha=ci_rgba[3],
                        label=legend_ci, zorder=1)

    ax.plot(xx, xx, color=color_identity, linewidth=1.5,
            linestyle="--", label=legend_identity, zorder=2)
    ax.plot(xx, slope * xx + intercept, color=color_regression,
            linewidth=2.5, label=legend_regression, zorder=3)

    sc = _hex_to_rgba_mpl(color_scatter, 0.75)
    ax.scatter(x, y, color=sc[:3], alpha=sc[3], s=40, linewidths=0.5,
               edgecolors="white", label=legend_scatter, zorder=4)

    def _f(v):
        return f"{v:.{decimals}f}".replace(".", ",")

    eq = _eq_str(slope, intercept, r_squared, n, decimals, _f)
    ax.text(0.04, 0.97, eq,
            transform=ax.transAxes, verticalalignment="top",
            fontsize=10, fontweight="bold", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="#9CA3AF", linewidth=1.2, alpha=0.92))

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_xlabel(_wrap_label(x_label), fontsize=11, labelpad=8)
    ax.set_ylabel(_wrap_label(y_label), fontsize=11, labelpad=8)
    ax.set_title(title or "Passing–Bablok Method Comparison",
                 fontsize=13, fontweight="bold", pad=12)
    ax.legend(loc="lower right", fontsize=9, framealpha=0.9)
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")
    ax.grid(True, color="#EEEEEE", linewidth=0.8, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)

    fig.subplots_adjust(left=0.12, right=0.97, top=0.92, bottom=0.12)
    return fig


# ── Bland–Altman plot ─────────────────────────────────────────────────────────

def render_ba_png(
    x, y,
    mean_diff, loa_lower, loa_upper,
    x_label="Reference Method",
    y_label="Candidate Method",
    title="",
    pct_diff=False,
    color_scatter="#2563EB",
    color_mean="#DC2626",
    color_loa="#F97316",
    legend_scatter="Difference",
    label_mean="Mean",
    label_loa_upper="+1,96 SD",
    label_loa_lower="−1,96 SD",
    x_min=None, x_max=None,
    y_min=None, y_max=None,
    decimals=4,
    dpi=300,
    width_px=1400,
    height_px=1040,
):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]

    means = (x + y) / 2.0

    if pct_diff:
        with np.errstate(divide="ignore", invalid="ignore"):
            diffs = np.where(means != 0, (y - x) / means * 100.0, np.nan)
        valid  = np.isfinite(diffs)
        mean_d = float(np.mean(diffs[valid]))
        std_d  = float(np.std(diffs[valid], ddof=1))
        loa_lo = mean_d - 1.96 * std_d
        loa_hi = mean_d + 1.96 * std_d
        y_title  = "Difference (%)"
        auto_title = ("Bland–Altman Plot (% difference)\n"
                      f"({y_label} − {x_label}) / mean × 100")
        suffix = " %"
    else:
        diffs  = y - x
        mean_d = mean_diff
        loa_lo = loa_lower
        loa_hi = loa_upper
        y_title    = f"Difference\n({y_label} − {x_label})"
        auto_title = "Bland–Altman Plot"
        suffix = ""

    ba_title = title if title else auto_title

    def _f(v):
        return f"{v:.{decimals}f}".replace(".", ",")

    means_c = means[np.isfinite(diffs)]
    diffs_c = diffs[np.isfinite(diffs)]

    x_pad  = (means_c.max() - means_c.min()) * 0.08
    rx_min = float(x_min) if x_min is not None else float(means_c.min()) - x_pad
    rx_max = float(x_max) if x_max is not None else float(means_c.max()) + x_pad

    y_pad  = (diffs_c.max() - diffs_c.min()) * 0.25   # extra headroom for upper label
    ry_min = float(y_min) if y_min is not None else float(diffs_c.min()) - y_pad
    ry_max = float(y_max) if y_max is not None else float(diffs_c.max()) + y_pad

    fig, ax = plt.subplots(figsize=_fig_size(width_px, height_px, dpi), dpi=dpi)

    sc = _hex_to_rgba_mpl(color_scatter, 0.75)
    ax.scatter(means, diffs, color=sc[:3], alpha=sc[3], s=40,
               linewidths=0.5, edgecolors="white", zorder=3)

    # Labels placed inside the axes at 97% of x range, anchored above/below the line
    x_range = rx_max - rx_min
    label_x = rx_min + x_range * 0.97

    for y_val, color, style, lw, lbl, va in [
        (mean_d, color_mean, "-",   2.0, f"{label_mean}: {_f(mean_d)}{suffix}",      "bottom"),
        (loa_hi, color_loa,  "--", 1.5, f"{label_loa_upper}: {_f(loa_hi)}{suffix}", "top"),
        (loa_lo, color_loa,  "--", 1.5, f"{label_loa_lower}: {_f(loa_lo)}{suffix}", "bottom"),
        (0,      "#9CA3AF",  ":",  1.0, "",                                           "bottom"),
    ]:
        ax.axhline(y_val, color=color, linestyle=style, linewidth=lw, zorder=2)
        if lbl:
            ax.text(label_x, y_val, lbl,
                    va=va, ha="right",
                    fontsize=9, fontweight="bold",
                    color=color, zorder=5,
                    bbox=dict(boxstyle="round,pad=0.2",
                              facecolor="white", edgecolor="none", alpha=0.80))

    ax.set_xlim(rx_min, rx_max)
    ax.set_ylim(ry_min, ry_max)
    ax.set_xlabel(_wrap_label(f"Mean of {x_label} and {y_label}"),
                  fontsize=11, labelpad=8)
    ax.set_ylabel(y_title, fontsize=11, labelpad=8)
    ax.set_title(ba_title, fontsize=13, fontweight="bold", pad=12)
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")
    ax.grid(True, color="#EEEEEE", linewidth=0.8, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)

    fig.subplots_adjust(left=0.14, right=0.97, top=0.88, bottom=0.14)
    return fig


# ── bytes helpers ─────────────────────────────────────────────────────────────

def mpl_fig_to_png_bytes(fig, dpi: int = 300) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi,
                bbox_inches="tight", pad_inches=0.2,
                facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def mpl_fig_to_svg_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="svg",
                bbox_inches="tight", pad_inches=0.2,
                facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
