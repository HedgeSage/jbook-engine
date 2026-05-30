#!/usr/bin/env python3
"""SVG lint: scan all chapter SVGs for common rendering issues."""
import re, sys, glob
from xml.etree import ElementTree as ET

CHAPTERS = "content/chapters/"


def parse_viewbox(svg_text: str):
    m = re.search(r'viewBox="([^"]+)"', svg_text)
    if not m:
        return None
    parts = m.group(1).split()
    if len(parts) != 4:
        return None
    return tuple(float(x) for x in parts)


def extract_svg_elements(svg_text: str):
    """Extract rect, line, text elements with rough bounding info."""
    rects = []
    lines = []
    texts = []
    # Parse rect
    for m in re.finditer(r'<rect[^>]*\bx="([^"]*)"\s+y="([^"]*)"\s+width="([^"]*)"\s+height="([^"]*)"[^>]*>', svg_text):
        x, y, w, h = float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))
        rects.append({"x": x, "y": y, "x2": x + w, "y2": y + h})
    # Parse lines (skip ultra-thin dashed theme lines, they're decorative)
    for m in re.finditer(r'<line[^>]*\bx1="([^"]*)"\s+y1="([^"]*)"\s+x2="([^"]*)"\s+y2="([^"]*)"[^>]*>', svg_text):
        attrs = m.group(0)
        # Skip theme lines: thin (≤1px) and dashed
        sw = re.search(r'stroke-width="([^"]*)"', attrs)
        dash = re.search(r'stroke-dasharray', attrs)
        if sw and float(sw.group(1)) <= 1 and dash:
            continue
        lines.append({
            "x1": float(m.group(1)), "y1": float(m.group(2)),
            "x2": float(m.group(3)), "y2": float(m.group(4))
        })
    # Parse text
    for m in re.finditer(r'<text[^>]*\bx="([^"]*)"\s+y="([^"]*)"[^>]*>(.*?)</text>', svg_text, re.DOTALL):
        x, y, content = float(m.group(1)), float(m.group(2)), m.group(3).strip()
        # Rough estimate: used only for flagging clear overflows
        # SVG fonts are typically 12-14px; ~8px per CJK char, ~6px per Latin
        cjk = sum(1 for c in content if ord(c) > 127)
        latin = len(content) - cjk - content.count(' ')
        est_w = cjk * 8 + latin * 6  # conservative estimate for small SVG fonts
        texts.append({"x": x, "y": y, "est_x2": x + est_w, "content": content[:30]})
    return rects, lines, texts


def line_crosses_rect(line: dict, rect: dict, margin: int = 8) -> bool:
    """Check if a line crosses the INTERIOR of a rect (not just touching the edge)."""
    inner = {
        "x": rect["x"] + margin,
        "y": rect["y"] + margin,
        "x2": rect["x2"] - margin,
        "y2": rect["y2"] - margin,
    }
    # If no interior region, skip
    if inner["x"] >= inner["x2"] or inner["y"] >= inner["y2"]:
        return False

    x1, y1, x2, y2 = line["x1"], line["y1"], line["x2"], line["y2"]

    # Check if either endpoint is inside inner rect
    if inner["x"] <= x1 <= inner["x2"] and inner["y"] <= y1 <= inner["y2"]:
        return True
    if inner["x"] <= x2 <= inner["x2"] and inner["y"] <= y2 <= inner["y2"]:
        return True

    # Check if line segment intersects inner rect edges
    def line_intersects_seg(lx1, ly1, lx2, ly2, sx1, sy1, sx2, sy2):
        def ccw(ax, ay, bx, by, cx, cy):
            return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax)
        return ccw(lx1, ly1, sx1, sy1, sx2, sy2) != ccw(lx2, ly2, sx1, sy1, sx2, sy2) and \
               ccw(lx1, ly1, lx2, ly2, sx1, sy1) != ccw(lx1, ly1, lx2, ly2, sx2, sy2)

    ix, iy, ix2, iy2 = inner["x"], inner["y"], inner["x2"], inner["y2"]
    for (sx1, sy1, sx2, sy2) in [
        (ix, iy, ix2, iy), (ix2, iy, ix2, iy2),
        (ix2, iy2, ix, iy2), (ix, iy2, ix, iy)
    ]:
        if line_intersects_seg(x1, y1, x2, y2, sx1, sy1, sx2, sy2):
            return True
    return False


def check_chapter(filepath: str) -> list[str]:
    """Check one chapter's SVGs and return issues."""
    issues = []
    with open(filepath) as f:
        content = f.read()
    # Find SVG blocks
    svgs = re.findall(r'<svg[^>]*>.*?</svg>', content, re.DOTALL)
    if not svgs:
        return issues

    chapter_name = filepath.replace("content/chapters/", "").replace(".md", "")
    for idx, svg_text in enumerate(svgs):
        prefix = f"{chapter_name}#{idx+1}"
        vb = parse_viewbox(svg_text)
        if not vb:
            issues.append(f"  {prefix}: missing or malformed viewBox")
            continue
        vb_x, vb_y, vb_w, vb_h = vb
        rects, lines, texts = extract_svg_elements(svg_text)

        # Check texts within viewBox (5px buffer from edges)
        for t in texts:
            if t["x"] < vb_x - 5 or t["y"] < vb_y - 5:
                issues.append(f"  {prefix}: text '{t['content']}' at ({t['x']},{t['y']}) outside viewBox left/top")
            if t["est_x2"] > vb_x + vb_w + max(20, vb_w * 0.05):
                issues.append(f"  {prefix}: text '{t['content'][:40]}' may overflow viewBox (est right {t['est_x2']:.0f} > {vb_x+vb_w:.0f})")

        # Check lines vs rects (skip lines fully contained within their parent rect,
        # and skip entire SVG if marked as intentional chart with <!-- svg:chart -->)
        if 'svg:chart' in svg_text.lower():
            continue  # skip line-rect checks for chart SVGs
        for line in lines:
            for rect in rects:
                # Skip: line is fully inside the rect (internal element like chart line)
                inner_margin = 8
                rx, ry = rect["x"] + inner_margin, rect["y"] + inner_margin
                rx2, ry2 = rect["x2"] - inner_margin, rect["y2"] - inner_margin
                if rx <= line["x1"] <= rx2 and ry <= line["y1"] <= ry2 and \
                   rx <= line["x2"] <= rx2 and ry <= line["y2"] <= ry2:
                    continue
                if line_crosses_rect(line, rect):
                    issues.append(
                        f"  {prefix}: line ({line['x1']:.0f},{line['y1']:.0f})→({line['x2']:.0f},{line['y2']:.0f}) "
                        f"crosses rect ({rect['x']:.0f},{rect['y']:.0f}){rect['x2']-rect['x']:.0f}x{rect['y2']-rect['y']:.0f}"
                    )
    return issues


def main():
    all_issues = {}
    for f in sorted(glob.glob(f"{CHAPTERS}*.md")):
        issues = check_chapter(f)
        if issues:
            all_issues[f.replace("content/chapters/", "")] = issues

    if not all_issues:
        print("✅ All SVGs pass basic checks")
        return 0

    print(f"⚠️  SVG issues found in {len(all_issues)} chapter(s):\n")
    for ch, issues in sorted(all_issues.items()):
        print(f"📄 {ch}:")
        for issue in issues:
            print(issue)
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
