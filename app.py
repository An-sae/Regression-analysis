"""
Confusion Matrix Plot
=====================
Colour = distance from identity diagonal.
Total (n = …) placed OUTSIDE the graph frame, bottom-right, in scientific style.
"""

import numpy as np
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ── helpers ───────────────────────────────────────────────────────────────────

def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _diagonal_points(n_bins, offset_cells, clamp_max):
    cols, rows = [], []
    for c in range(n_bins):
        r = c + offset_cells
        if 0 <= r < clamp_max:
            cols.append(c)
            rows.append(r)
    return cols, rows


def _zone_colour(dist_mm, colour_bands, base_rgb, white=(1.0, 1.0, 1.0)):
    if dist_mm > colour_bands:
        return white
    t = 1.0 - dist_mm / (colour_bands + 1)
    t = max(t, 0.30)
    return tuple(w * (1 - t) + d / 255 * t for w, d in zip(white, base_rgb))


def _auto_px(n_data_bins, dpi, cell_mm=6.0, margin_mm=30.0):
    mm_per_inch = 25.4
    cell_px   = int(cell_mm / mm_per_inch * dpi)
    margin_px = int(margin_mm / mm_per_inch * dpi)
    grid_px   = cell_px * n_data_bins
    total_px  = grid_px + margin_px * 2
    return total_px, cell_px


# ── Plotly interactive ────────────────────────────────────────────────────────

def make_confusion_plot(
    matrix, x_bins, y_bins,
    x_label="Reference Method (mm)",
    y_label="Candidate Method (mm)",
    title="Zone Diameter Comparison",
    color_scale_max=2,
    base_color="#1D4ED8",
    step=1,
    ea_window=2,
    show_diagonal_lines=True,
    show_totals=True,
    cell_font_size=11,
    num_color_on_blue="#1E3A5F",
    num_color_on_white="#1E3A5F",
    num_bold=True,
):
    import plotly.graph_objects as go

    n = len(x_bins)
    n_total = int(matrix.sum())
    dark_rgb = _hex_to_rgb(base_color)
    colour_bands = color_scale_max

    x_labels_data = [str(int(b)) for b in x_bins]
    y_labels_data = [str(int(b)) for b in y_bins]

    # ── colour matrix: n × n data only ───────────────────────────────────────
    z_colour = np.zeros((n, n), dtype=float)
    for r in range(n):
        for c in range(n):
            dist_mm = abs(c - r) * step
            if dist_mm <= colour_bands:
                t = 1.0 - dist_mm / (colour_bands + 1)
                z_colour[r, c] = max(t, 0.35)

    colorscale = [
        [0.0, "rgb(255,255,255)"],
        [1.0, f"rgb({dark_rgb[0]},{dark_rgb[1]},{dark_rgb[2]})"],
    ]

    text_data = [[str(matrix[r, c]) if matrix[r, c] > 0 else ""
                  for c in range(n)] for r in range(n)]

    fig = go.Figure()

    # Data heatmap — pure n × n, no corner cell mixed in
    fig.add_trace(go.Heatmap(
        z=z_colour,
        x=x_labels_data,
        y=y_labels_data,
        colorscale=colorscale,
        showscale=False,
        zmin=0, zmax=1,
        xgap=1, ygap=1,
        hovertemplate="x=%{x}<br>y=%{y}<br>n=%{text}<extra></extra>",
        text=text_data,
    ))

    # Cell count annotations
    annotations = []
    fw_tag = "<b>" if num_bold else ""
    fw_end = "</b>" if num_bold else ""
    for r in range(n):
        for c in range(n):
            v = matrix[r, c]
            if v == 0:
                continue
            txt_color = num_color_on_blue if z_colour[r, c] >= 0.35 else num_color_on_white
            annotations.append(dict(
                x=x_labels_data[c], y=y_labels_data[r],
                text=f"{fw_tag}{v}{fw_end}",
                showarrow=False,
                font=dict(size=cell_font_size, color=txt_color,
                          family="Arial, sans-serif"),
            ))

    # Total: placed in paper coordinates outside the plot frame, bottom-right
    if show_totals:
        annotations.append(dict(
            x=1.0, y=-0.04,
            xref="paper", yref="paper",
            text=f"<i>n</i> = {n_total}",
            showarrow=False,
            xanchor="right", yanchor="top",
            font=dict(size=cell_font_size + 1, color="#374151",
                      family="Arial, sans-serif"),
        ))

    # Diagonal lines
    if show_diagonal_lines:
        for ea_off, color, dash, lw, name, show_leg in [
            (0,           "#1E3A5F", "solid", 1.5, "Exact agreement",  True),
            ( ea_window,  "#6B7280", "dot",   1.0, f"±{ea_window} mm", True),
            (-ea_window,  "#6B7280", "dot",   1.0, f"±{ea_window} mm", False),
        ]:
            off_cells = ea_off // step
            cols_idx, rows_idx = _diagonal_points(n, off_cells, n)
            if not cols_idx:
                continue
            fig.add_trace(go.Scatter(
                x=[x_labels_data[c] for c in cols_idx],
                y=[y_labels_data[r] for r in rows_idx],
                mode="lines", name=name, showlegend=show_leg,
                line=dict(color=color, width=lw, dash=dash),
                hoverinfo="skip",
            ))

    cell_px = max(24, min(42, 800 // max(n, 1)))
    fig_w   = cell_px * n + 180
    fig_h   = cell_px * n + 180

    fig.update_layout(
        title=dict(text=title, font=dict(size=15)),
        annotations=annotations,
        xaxis=dict(
            title=x_label, side="top",
            categoryorder="array", categoryarray=x_labels_data,
            tickmode="array", tickvals=x_labels_data, ticktext=x_labels_data,
            tickfont=dict(size=10), showgrid=False, zeroline=False,
            constrain="domain",
        ),
        yaxis=dict(
            title=y_label, autorange="reversed",
            categoryorder="array", categoryarray=y_labels_data,
            tickmode="array", tickvals=y_labels_data, ticktext=y_labels_data,
            tickfont=dict(size=10), showgrid=False, zeroline=False,
            scaleanchor="x", scaleratio=1,
        ),
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Inter, Arial, sans-serif"),
        legend=dict(orientation="h", y=-0.08, x=0),
        margin=dict(l=110, r=40, t=120, b=80),
        width=min(fig_w, 1100),
        height=min(fig_h, 950),
    )
    return fig


# ── Matplotlib static export ──────────────────────────────────────────────────

def render_confusion_png(
    matrix, x_bins, y_bins,
    x_label="Reference Method (mm)",
    y_label="Candidate Method (mm)",
    title="Zone Diameter Comparison",
    color_scale_max=2,
    base_color="#1D4ED8",
    step=1,
    ea_window=2,
    show_diagonal_lines=True,
    show_totals=True,
    cell_font_size=None,
    num_color_on_blue="#1E3A5F",
    num_color_on_white="#1E3A5F",
    num_bold=True,
    dpi=300,
):
    n = len(x_bins)
    dark_rgb     = _hex_to_rgb(base_color)
    colour_bands = color_scale_max
    n_total      = int(matrix.sum())

    x_labels = [str(int(b)) for b in x_bins]
    y_labels = [str(int(b)) for b in y_bins]

    # ── auto physical size ────────────────────────────────────────────────────
    cell_mm   = 6.0
    margin_mm = 28.0
    mm_per_in = 25.4
    cell_in   = cell_mm / mm_per_in
    margin_in = margin_mm / mm_per_in

    # Pure n × n grid — no extra cell for totals
    fig_w_in = cell_in * n + margin_in * 2
    fig_h_in = cell_in * n + margin_in * 2 + 0.25  # tiny extra for n= caption

    cell_pt = cell_in * 72   # points
    auto_fs = max(4, min(12, int(cell_pt * 0.35)))
    fs = cell_font_size if cell_font_size is not None else auto_fs

    # ── colour image ──────────────────────────────────────────────────────────
    white = (1.0, 1.0, 1.0)
    img   = np.ones((n, n, 3))
    for r in range(n):
        for c in range(n):
            dist_mm = abs(c - r) * step
            img[r, c] = _zone_colour(dist_mm, colour_bands, dark_rgb, white)

    fig, ax = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=dpi)
    ax.imshow(img, aspect="equal", origin="upper",
              extent=[-0.5, n - 0.5, n - 0.5, -0.5],
              interpolation="none")

    # Grid lines
    for i in range(n + 1):
        ax.axvline(i - 0.5, color="#CBD5E1", linewidth=0.35, zorder=2)
        ax.axhline(i - 0.5, color="#CBD5E1", linewidth=0.35, zorder=2)

    # Cell text
    fw = "bold" if num_bold else "normal"
    for r in range(n):
        for c in range(n):
            v = matrix[r, c]
            if v == 0:
                continue
            dist_mm   = abs(c - r) * step
            on_colour = dist_mm <= colour_bands
            txt_col   = num_color_on_blue if on_colour else num_color_on_white
            ax.text(c, r, str(v),
                    ha="center", va="center",
                    fontsize=fs, color=txt_col,
                    fontweight=fw, zorder=5)

    # Diagonal lines
    if show_diagonal_lines:
        for ea_off, ls, lw, col in [
            (0,           "-",  1.2, "#1E3A5F"),
            ( ea_window,  ":",  0.8, "#6B7280"),
            (-ea_window,  ":",  0.8, "#6B7280"),
        ]:
            off_cells = ea_off // step
            cols_idx, rows_idx = _diagonal_points(n, off_cells, n)
            if cols_idx:
                ax.plot(cols_idx, rows_idx,
                        color=col, linewidth=lw, linestyle=ls,
                        zorder=3, solid_capstyle="round")

    # Axes — x on top
    tick_lw = max(0.3, fs * 0.06)
    ax.set_xticks(range(n))
    ax.set_xticklabels(x_labels,
                       fontsize=max(4, fs - 1),
                       rotation=90 if n > 22 else 0)
    ax.xaxis.set_label_position("top")
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", which="both", length=2, width=tick_lw)

    ax.set_yticks(range(n))
    ax.set_yticklabels(y_labels, fontsize=max(4, fs - 1))
    ax.tick_params(axis="y", which="both", length=2, width=tick_lw)

    ax.set_xlabel(x_label, fontsize=max(7, fs + 1), labelpad=6)
    ax.set_ylabel(y_label, fontsize=max(7, fs + 1), labelpad=6)
    ax.set_title(title, fontsize=max(9, fs + 3), fontweight="bold", pad=10)

    ax.set_xlim(-0.5, n - 0.5)
    ax.set_ylim(n - 0.5, -0.5)
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    # ── n = total: outside the frame, bottom-right, italic scientific style ──
    if show_totals:
        fig.text(
            0.98, 0.01,
            f"$n = {n_total}$",
            ha="right", va="bottom",
            fontsize=max(7, fs + 1),
            color="#374151",
            transform=fig.transFigure,
            style="italic",
        )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi,
                bbox_inches="tight", pad_inches=0.18, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
