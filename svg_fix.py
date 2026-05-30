#!/usr/bin/env python3
"""SVG auto-fixer: post-process SVG to correct common layout issues.

Canonical fixes:
  1. Text overflow → expand viewBox (via text-anchor + font-size estimate)
  2. Line crossing rect interior → trim endpoint to rect edge
  3. Nested rect overlap → shift inner rects (minor)

Run standalone or via build pipeline.
"""

import re, sys, glob, math, copy
from pathlib import Path
from xml.etree import ElementTree as ET


# ── Text width estimation (conservative, with font-size awareness) ──

def _text_bbox(text: str, x: float, y: float, font_size: float, text_anchor: str = "start") -> tuple:
    """Estimate bounding box of a <text> element.  Returns (min_x, min_y, max_x, max_y)."""
    # Character widths at given font_size
    # CJK chars ~ 0.8 × font_size, Latin ~ 0.55 × font_size
    cjk = sum(1 for c in text if ord(c) > 127)
    latin = max(0, len(text) - cjk - text.count(' '))
    est_w = (cjk * 0.8 + latin * 0.55) * font_size

    if text_anchor == "middle":
        min_x = x - est_w / 2
        max_x = x + est_w / 2
    elif text_anchor == "end":
        min_x = x - est_w
        max_x = x
    else:
        min_x = x
        max_x = x + est_w

    min_y = y - font_size * 0.85
    max_y = y + font_size * 0.25
    return (min_x, min_y, max_x, max_y)


# ── Core fix functions ──

def _expand_viewbox_for_text(svg_text: str) -> str:
    """Expand viewBox if any <text> element overflows."""
    text_pattern = re.compile(
        r'<text[^>]*\bx="([^"]*)"\s+y="([^"]*)"'
        r'(?:[^>]*\bfont-size="([^"]*)")?'
        r'(?:[^>]*\btext-anchor="([^"]*)")?[^>]*>'
        r'(.*?)</text>',
        re.DOTALL
    )

    viewbox_match = re.search(r'viewBox="([^"]+)"', svg_text)
    if not viewbox_match:
        return svg_text

    vb = [float(x) for x in viewbox_match.group(1).split()]
    vb_x, vb_y, vb_w, vb_h = vb[0], vb[1], vb[2], vb[3]
    changed = False

    for m in text_pattern.finditer(svg_text):
        x = float(m.group(1))
        y = float(m.group(2))
        fs = float(m.group(3)) if m.group(3) else 12.0
        ta = m.group(4) if m.group(4) else "start"
        content = m.group(5).strip()
        if not content:
            continue

        min_x, min_y, max_x, max_y = _text_bbox(content, x, y, fs, ta)

        overflows = False
        if min_x < vb_x - 5:
            vb[2] += (vb_x - min_x) + 10
            vb[0] = min_x - 10
            overflows = True
        if max_x > vb_x + vb_w + 5:
            vb[2] = max_x - vb_x + 10
            overflows = True
        if min_y < vb_y - 5:
            vb[3] += (vb_y - min_y) + 10
            vb[1] = min_y - 10
            overflows = True
        if max_y > vb_y + vb_h + 5:
            vb[3] = max_y - vb_y + 10
            overflows = True

        if overflows:
            changed = True

    if changed:
        new_vb = f'{vb[0]:.0f} {vb[1]:.0f} {vb[2]:.0f} {vb[3]:.0f}'
        svg_text = svg_text.replace(viewbox_match.group(1), new_vb)
    return svg_text


def _trim_lines_to_rect_edges(svg_text: str) -> str:
    """Trim lines so endpoints don't penetrate rect interiors."""
    rect_pattern = re.compile(
        r'<rect[^>]*\bx="([^"]*)"\s+y="([^"]*)"\s+width="([^"]*)"\s+height="([^"]*)"[^>]*>'
    )
    line_pattern = re.compile(
        r'<line[^>]*\bx1="([^"]*)"\s+y1="([^"]*)"\s+x2="([^"]*)"\s+y2="([^"]*)"[^>]*>'
    )

    rects = []
    for m in rect_pattern.finditer(svg_text):
        x = float(m.group(1))
        y = float(m.group(2))
        w = float(m.group(3))
        h = float(m.group(4))
        rects.append({"x": x, "y": y, "x2": x + w, "y2": y + h})

    if not rects:
        return svg_text

    def _clip_endpoint(px: float, py: float, rect: dict, margin: float = 6.0) -> tuple | None:
        """If point (px,py) is inside rect interior, slide it to nearest rect edge."""
        inner_x, inner_y = rect["x"] + margin, rect["y"] + margin
        inner_x2, inner_y2 = rect["x2"] - margin, rect["y2"] - margin
        if inner_x >= inner_x2 or inner_y >= inner_y2:
            return None  # rect too small
        if not (inner_x <= px <= inner_x2 and inner_y <= py <= inner_y2):
            return None  # not inside

        # Find nearest edge
        dist_left = abs(px - inner_x)
        dist_right = abs(px - inner_x2)
        dist_top = abs(py - inner_y)
        dist_bottom = abs(py - inner_y2)

        nearest = min(dist_left, dist_right, dist_top, dist_bottom)
        if nearest == dist_left:
            return (inner_x - 1, py)
        elif nearest == dist_right:
            return (inner_x2 + 1, py)
        elif nearest == dist_top:
            return (px, inner_y - 1)
        else:
            return (px, inner_y2 + 1)

    def _fix_line(line_match) -> str:
        original = line_match.group(0)
        x1 = float(line_match.group(1))
        y1 = float(line_match.group(2))
        x2 = float(line_match.group(3))
        y2 = float(line_match.group(4))

        # Skip thin dashed theme lines
        sw_match = re.search(r'stroke-width="([^"]*)"', original)
        dash_match = re.search(r'stroke-dasharray', original)
        if sw_match and dash_match and float(sw_match.group(1)) <= 1:
            return original

        changed = False
        for rect in rects:
            new_p1 = _clip_endpoint(x1, y1, rect)
            if new_p1:
                x1, y1 = new_p1
                changed = True
            new_p2 = _clip_endpoint(x2, y2, rect)
            if new_p2:
                x2, y2 = new_p2
                changed = True

        if changed:
            new_line = original
            new_line = re.sub(r'x1="[^"]*"', f'x1="{x1:.1f}"', new_line)
            new_line = re.sub(r'y1="[^"]*"', f'y1="{y1:.1f}"', new_line)
            new_line = re.sub(r'x2="[^"]*"', f'x2="{x2:.1f}"', new_line)
            new_line = re.sub(r'y2="[^"]*"', f'y2="{y2:.1f}"', new_line)
            return new_line
        return original

    # Process lines from longest to shortest (avoid substring collisions)
    matches = list(line_pattern.finditer(svg_text))
    matches.sort(key=lambda m: len(m.group(0)), reverse=True)
    for m in matches:
        fixed = _fix_line(m)
        if fixed != m.group(0):
            svg_text = svg_text.replace(m.group(0), fixed)
    return svg_text


def _balance_viewbox_padding(svg_text: str) -> str:
    """Ensure 5% padding around all visible elements."""
    viewbox_match = re.search(r'viewBox="([^"]+)"', svg_text)
    if not viewbox_match:
        return svg_text

    vb = [float(x) for x in viewbox_match.group(1).split()]
    vb_x, vb_y, vb_w, vb_h = vb[0], vb[1], vb[2], vb[3]

    # Find all coordinates in SVG
    coords = set()
    for m in re.finditer(r'[xy](\d)="(-?\d+\.?\d*)"', svg_text):
        coords.add(float(m.group(2)))
    for m in re.finditer(r'width="(-?\d+\.?\d*)"', svg_text):
        coords.add(float(m.group(1)))
    for m in re.finditer(r'height="(-?\d+\.?\d*)"', svg_text):
        coords.add(float(m.group(1)))

    # Estimate content bounds
    all_x, all_y, all_w, all_h = [], [], [], []
    for m in re.finditer(r'<(?:rect|text|circle|ellipse)[^>]*>', svg_text):
        attrs = m.group(0)
        xm = re.search(r'\bx="([^"]*)"', attrs)
        ym = re.search(r'\by="([^"]*)"', attrs)
        if xm and ym:
            all_x.append(float(xm.group(1)))
            all_y.append(float(ym.group(1)))
        wm = re.search(r'\bwidth="([^"]*)"', attrs)
        hm = re.search(r'\bheight="([^"]*)"', attrs)
        if xm and wm:
            all_w.append(float(xm.group(1)) + float(wm.group(1)))
        if ym and hm:
            all_h.append(float(ym.group(1)) + float(hm.group(1)))

    if not all_x:
        return svg_text

    min_x = min(all_x)
    max_x = max(all_w + all_x) if all_w else max(all_x)
    min_y = min(all_y)
    max_y = max(all_h + all_y) if all_h else max(all_y)

    pad = 0.05
    needed_vb_x = min_x - (max_x - min_x) * pad
    needed_vb_y = min_y - (max_y - min_y) * pad
    needed_vb_w = (max_x - min_x) * (1 + pad * 2)
    needed_vb_h = (max_y - min_y) * (1 + pad * 2)

    if (needed_vb_x < vb_x or needed_vb_y < vb_y or
        needed_vb_w > vb_w * 1.05 or needed_vb_h > vb_h * 1.05):
        new_vb = f'{needed_vb_x:.0f} {needed_vb_y:.0f} {needed_vb_w:.0f} {needed_vb_h:.0f}'
        svg_text = svg_text.replace(viewbox_match.group(1), new_vb)
    return svg_text


# ── Pipeline ──

def fix_svg(svg_text: str) -> str:
    """Apply all fixes. Returns fixed SVG (or original if nothing to fix)."""
    svg_text = _expand_viewbox_for_text(svg_text)
    svg_text = _trim_lines_to_rect_edges(svg_text)
    svg_text = _balance_viewbox_padding(svg_text)
    return svg_text


def fix_chapter(filepath: str) -> bool:
    """Fix all SVGs in a chapter markdown file. Returns True if changes made."""
    with open(filepath) as f:
        content = f.read()

    changed = False
    for svg_match in re.finditer(r'<svg[^>]*>.*?</svg>', content, re.DOTALL):
        original = svg_match.group(0)
        fixed = fix_svg(original)
        if fixed != original:
            content = content.replace(original, fixed)
            changed = True

    if changed:
        with open(filepath, 'w') as f:
            f.write(content)
    return changed


def main():
    import argparse
    p = argparse.ArgumentParser(description="Auto-fix common SVG layout issues")
    p.add_argument("files", nargs="*", help="Markdown files or globs to fix")
    p.add_argument("--all", action="store_true", help="Fix all chapters in content/chapters/")
    args = p.parse_args()

    if args.all:
        files = sorted(glob.glob("content/chapters/*.md"))
    elif args.files:
        files = []
        for pattern in args.files:
            files.extend(glob.glob(pattern))
    else:
        p.print_help()
        return 1

    fixed_count = 0
    for f in files:
        if fix_chapter(f):
            print(f"  Fixed: {f}")
            fixed_count += 1

    if fixed_count:
        print(f"\n✅ Auto-fixed {fixed_count} chapter(s)")
    else:
        print("✅ No issues to fix")
    return 0


if __name__ == "__main__":
    sys.exit(main())
