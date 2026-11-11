"""Tiny SVG bar charts (standard library only), for the evaluation report."""

from __future__ import annotations

from html import escape

PALETTE = {"flakelab": "#1F8A7A", "reruns": "#8A97A6", "fail": "#C23A50"}


def grouped_bars(
    title: str,
    categories: list[str],
    series: list[tuple[str, list[float], str]],
    value_format: str = "{:.0%}",
    max_value: float | None = None,
    width: int = 760,
) -> str:
    """Horizontal grouped bars. series: (name, values, colour)."""
    bar_h, gap, group_gap = 14, 3, 14
    label_w, right_pad, top = 250, 70, 56
    group_h = len(series) * (bar_h + gap) + group_gap
    height = top + len(categories) * group_h + 20
    vmax = max_value or max((v for _, vals, _ in series for v in vals), default=1) or 1
    plot_w = width - label_w - right_pad
    out = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'font-family="Segoe UI, system-ui, sans-serif" font-size="12" role="img" '
            f'aria-label="{escape(title)}">'
        ),
        f'<rect width="{width}" height="{height}" fill="#fff"/>',
        (
            f'<text x="16" y="24" font-size="15" font-weight="600" fill="#17212B">'
            f"{escape(title)}</text>"
        ),
    ]
    lx = label_w
    for name, _, colour in series:
        out.append(f'<rect x="{lx}" y="34" width="10" height="10" rx="2" fill="{colour}"/>')
        out.append(f'<text x="{lx + 14}" y="43" fill="#5B6977">{escape(name)}</text>')
        lx += 14 + 7 * len(name) + 24
    y = top
    for ci, cat in enumerate(categories):
        out.append(
            f'<text x="{label_w - 8}" y="{y + bar_h}" text-anchor="end" fill="#17212B">'
            f"{escape(cat)}</text>"
        )
        for name, vals, colour in series:
            v = vals[ci]
            w = 0 if v is None else max(1.5, plot_w * v / vmax)
            out.append(
                f'<rect x="{label_w}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="2" '
                f'fill="{colour}"><title>{escape(name)}: {v}</title></rect>'
            )
            text = "n/a" if v is None else value_format.format(v)
            out.append(
                f'<text x="{label_w + w + 6:.1f}" y="{y + bar_h - 3}" fill="#5B6977">{text}</text>'
            )
            y += bar_h + gap
        y += group_gap
    out.append("</svg>")
    return "\n".join(out)
