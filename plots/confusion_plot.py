"""
Confusion Matrix Plot
=====================
Colour = distance from identity diagonal (not count).
Totalsumma = single number in the bottom-right corner only.
Image dimensions are auto-calculated from bin count and DPI.
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
    """Cell-centre (col, row) pairs for a diagonal shifted by offset_cells."""
    cols, rows = [], []
    for c in range(n_bins):
        r = c + offset_cells
        if 0 <= r < clamp_max:
            cols.append(c)
            rows.append(r)
    return cols, rows


def _zone_colour(dist_mm, colour_bands, base_rgb, white=(1.0, 1.0, 1.0)):
    """RGB for a cell at dist_mm from the diagonal."""
    if dist_mm > colour_bands:
        return white
    t = 1.0 - dist_mm / (colour_bands + 1)
    t = max(t, 0.30)   # minimum 0.30 so outermost band stays clearly visible
    return tuple(w * (1 - t) + d / 255 * t for w, d in zip(white, base_rgb))


def _auto_px(n_data_bins, dpi, cell_mm=6.0, margin_mm=30.0):
    """
    Compute a sensible image size in pixels.
    cell_mm: physical size of each grid cell in mm at the given DPI.
    margin_mm: extra margin for labels, title.
    """
    mm_per_inch = 25.4
    cell_px  = int(cell_mm / mm_per_inch * dpi)
    margin_px = int(margin_mm / mm_per_inch * dpi)
    # data grid = n_data_bins cells + 1 extra for the Totalsumma corner
    grid_px  = cell_px * (n_data_bins + 1)
    total_px = grid_px + margin_px * 2
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
    num_color_on_blue="#FFFFFF",
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

    # ── colour matrix: data cells only (n × n), NO corner mixed in ───────────
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

    fig = go.Figure()

    # ── Trace 1: data heatmap (n × n, full colour range 0–1) ─────────────────
    text_data = [[str(matrix[r, c]) if matrix[r, c] > 0 else ""
                  for c in range(n)] for r in range(n)]

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

    # ── Trace 2 (optional): corner cell as a separate 1×1 heatmap ────────────
    if show_totals:
        fig.add_trace(go.Heatmap(
            z=[[0.18]],
            x=["Σ"],
            y=["Totalsumma"],
            colorscale=[[0, "rgb(220,220,228)"], [1, "rgb(180,180,192)"]],
            showscale=False,
            zmin=0, zmax=1,
            xgap=1, ygap=1,
            hoverinfo="skip",
        ))

    # ── Annotations: data cells ───────────────────────────────────────────────
    annotations = []
    font_family = "Arial, sans-serif"
    for r in range(n):
        for c in range(n):
            v = matrix[r, c]
            if v == 0:
                continue
            txt_color = num_color_on_blue if z_colour[r, c] >= 0.35 else num_color_on_white
            txt = f"<b>{v}</b>" if num_bold else str(v)
            annotations.append(dict(
                x=x_labels_data[c], y=y_labels_data[r],
                text=txt,
                showarrow=False,
                font=dict(size=cell_font_size, color=txt_color, family=font_family),
            ))

    # Corner annotation
    if show_totals:
        txt = f"<b>{n_total}</b>" if num_bold else str(n_total)
        annotations.append(dict(
            x="Σ", y="Totalsumma",
            text=txt,
            showarrow=False,
            font=dict(size=cell_font_size + 2, color=num_color_on_white,
                      family=font_family),
        ))

    # ── Diagonal lines ────────────────────────────────────────────────────────
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

    # ── Layout ────────────────────────────────────────────────────────────────
    # Show totals column as an extra category on both axes
    x_all = x_labels_data + (["Σ"] if show_totals else [])
    y_all = y_labels_data + (["Totalsumma"] if show_totals else [])

    cell_px = max(24, min(42, 800 // max(len(x_all), 1)))
    fig_w   = cell_px * len(x_all) + 180
    fig_h   = cell_px * len(y_all) + 160

    fig.update_layout(
        title=dict(text=title, font=dict(size=15)),
        annotations=annotations,
        xaxis=dict(
            title=x_label, side="top",
            categoryorder="array", categoryarray=x_all,
            tickmode="array", tickvals=x_all, ticktext=x_all,
            tickfont=dict(size=10), showgrid=False, zeroline=False,
            constrain="domain",
        ),
        yaxis=dict(
            title=y_label, autorange="reversed",
            categoryorder="array", categoryarray=y_all,
            tickmode="array", tickvals=y_all, ticktext=y_all,
            tickfont=dict(size=10), showgrid=False, zeroline=False,
            scaleanchor="x", scaleratio=1,
        ),
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Inter, Arial, sans-serif"),
        legend=dict(orientation="h", y=-0.06, x=0),
        margin=dict(l=110, r=40, t=120, b=80),
        width=min(fig_w, 1100),
        height=min(fig_h + 120, 950),
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
    dark_rgb   = _hex_to_rgb(base_color)
    colour_bands = color_scale_max
    n_total    = int(matrix.sum())

    # ── display dimensions ────────────────────────────────────────────────────
    # Data grid = n × n; add 1 extra row+col if show_totals (corner only)
    nc_disp = n + 1 if show_totals else n
    nr_disp = n + 1 if show_totals else n

    x_labels = [str(int(b)) for b in x_bins] + ([""] if show_totals else [])
    y_labels = [str(int(b)) for b in y_bins] + (["Totalsumma"] if show_totals else [])

    # ── auto physical size: each data cell = 6 mm, corner cell same size ──────
    cell_mm    = 6.0      # mm per cell
    margin_mm  = 28.0     # mm for labels + title
    mm_per_in  = 25.4
    cell_in    = cell_mm / mm_per_in
    margin_in  = margin_mm / mm_per_in

    fig_w_in = cell_in * nc_disp + margin_in * 2
    fig_h_in = cell_in * nr_disp + margin_in * 2

    # Auto font size based on cell size in points
    cell_pt = cell_in * dpi / (dpi / 72)   # cell size in typographic points
    auto_fs = max(4, min(12, int(cell_pt * 0.35)))
    fs = cell_font_size if cell_font_size is not None else auto_fs

    # ── colour image ──────────────────────────────────────────────────────────
    white = (1.0, 1.0, 1.0)
    grey  = (0.88, 0.88, 0.92)

    img = np.ones((nr_disp, nc_disp, 3))
    for r in range(nr_disp):
        for c in range(nc_disp):
            is_corner = show_totals and r == n and c == n
            in_data   = r < n and c < n
            if is_corner:
                img[r, c] = grey
            elif in_data:
                dist_mm = abs(c - r) * step
                img[r, c] = _zone_colour(dist_mm, colour_bands, dark_rgb, white)
            # extra row/col cells (non-corner) stay white

    fig, ax = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=dpi)
    ax.imshow(img, aspect="equal", origin="upper",
              extent=[-0.5, nc_disp-0.5, nr_disp-0.5, -0.5],
              interpolation="none")

    # Grid lines — only around data + corner cell
    for i in range(nc_disp + 1):
        ax.axvline(i - 0.5, color="#CBD5E1", linewidth=0.35, zorder=2)
    for i in range(nr_disp + 1):
        ax.axhline(i - 0.5, color="#CBD5E1", linewidth=0.35, zorder=2)

    # Cell text
    for r in range(nr_disp):
        for c in range(nc_disp):
            is_corner = show_totals and r == n and c == n
            in_data   = r < n and c < n

            if is_corner:
                txt = str(n_total)
                fw = "bold" if num_bold else "normal"
                ax.text(c, r, txt,
                        ha="center", va="center",
                        fontsize=fs + 1, color=num_color_on_white,
                        fontweight=fw, zorder=5)
                continue

            if not in_data:
                continue

            v = matrix[r, c]
            if v == 0:
                continue

            dist_mm  = abs(c - r) * step
            on_colour = dist_mm <= colour_bands
            txt_col  = num_color_on_blue if on_colour else num_color_on_white
            fw = "bold" if num_bold else "normal"
            ax.text(c, r, str(v),
                    ha="center", va="center",
                    fontsize=fs, color=txt_col,
                    fontweight=fw, zorder=5)

    # Diagonal lines (data area only)
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
    ax.set_xticks(range(nc_disp))
    ax.set_xticklabels(x_labels,
                       fontsize=max(4, fs - 1),
                       rotation=90 if nc_disp > 22 else 0)
    ax.xaxis.set_label_position("top")
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", which="both", length=2, width=tick_lw)

    ax.set_yticks(range(nr_disp))
    ax.set_yticklabels(y_labels, fontsize=max(4, fs - 1))
    ax.tick_params(axis="y", which="both", length=2, width=tick_lw)

    ax.set_xlabel(x_label, fontsize=max(7, fs + 1), labelpad=6)
    ax.set_ylabel(y_label, fontsize=max(7, fs + 1), labelpad=6)
    ax.set_title(title, fontsize=max(9, fs + 3), fontweight="bold", pad=10)

    ax.set_xlim(-0.5, nc_disp - 0.5)
    ax.set_ylim(nr_disp - 0.5, -0.5)
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi,
                bbox_inches="tight", pad_inches=0.15, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
