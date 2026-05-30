#!/usr/bin/env python3
"""
Build engine for the CFA course site.
Reads course.yml + chapter markdown files, renders static HTML via Jinja2.

Architecture:
  content/course.yml          → course structure & metadata
  content/chapters/{id}.md    → chapter content (sections)
  engine/templates/*.html     → Jinja2 templates
  site/                       → output directory
  assets/                     → static assets (CSS, images)
"""

import subprocess
import sys
import re
import shutil
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
TEMPLATES = ROOT / "engine" / "templates"
SITE = ROOT / "site"
ASSETS = ROOT / "assets"

ASSET_PATH = "../"


def _git_short_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "dev"


def load_course() -> dict:
    with open(CONTENT / "course.yml") as f:
        return yaml.safe_load(f)


def load_chapter_content(chapter_id: str) -> dict[str, Any]:
    """Parse a chapter markdown file into structured data."""
    path = CONTENT / "chapters" / f"{chapter_id}.md"
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8")
    sections = _parse_sections(text)
    data: dict[str, Any] = {}

    # Scene
    if "Scene" in sections:
        data["scene"] = _md_to_html(sections["Scene"])

    # Diagram (SVG raw)
    if "Diagram" in sections:
        # Extract SVG between ```svg ... ``` or just raw SVG
        dia = sections["Diagram"]
        m = re.search(r"<svg[\s\S]*?</svg>", dia)
        if m:
            data["diagram"] = m.group(0)

    # Steps
    if "Steps" in sections:
        data["steps"] = _parse_list(sections["Steps"])

    # Explanations
    if "Explanations" in sections:
        data["explanations"] = _parse_explanations(sections["Explanations"])

    # Try block
    if "Try" in sections:
        data["try_block"] = _parse_try_block(sections["Try"])

    # Math block
    if "Math" in sections:
        data["math_block"] = _parse_math_block(sections["Math"])

    # Pitfalls
    if "Pitfalls" in sections:
        data["pitfalls"] = _parse_pitfalls(sections["Pitfalls"])

    # Takeaways
    if "Takeaways" in sections:
        data["takeaways"] = _parse_list(sections["Takeaways"])

    # Map note
    if "Map" in sections:
        data["map_note"] = sections["Map"].strip()

    # Forward hook
    if "ForwardHook" in sections:
        data["forward_hook"] = sections["ForwardHook"].strip()

    return data


def _parse_sections(text: str) -> dict[str, str]:
    """Split markdown by ## headers into section dict."""
    sections = {}
    # Split on ## headers (not ###)
    parts = re.split(r"\n## (.+)\n", text)
    # Handle parts[0] — the first section if it starts with ##
    if parts[0].startswith("## "):
        first = parts[0][3:].split("\n", 1)
        header = first[0].strip()
        body = first[1].strip() if len(first) > 1 else ""
        sections[header] = body
    # then alternating: header, body, header, body...
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections[header] = body
    return sections


def _md_to_html(text: str) -> str:
    """Simple markdown → HTML conversion (paragraphs, emphasis, strong)."""
    lines = text.strip().split("\n")
    result = []
    buf: list[str] = []

    def flush():
        nonlocal buf
        if buf:
            para = " ".join(buf).strip()
            para = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", para)
            para = re.sub(r"\*(.+?)\*", r"<em>\1</em>", para)
            # Avoid wrapping standalone HTML/SVG
            if para.startswith("<") and para.endswith(">"):
                result.append(para)
            else:
                result.append(f"<p>{para}</p>")
            buf = []

    for line in lines:
        stripped = line.strip()
        if stripped == "":
            flush()
        elif stripped.startswith("### "):
            flush()
            heading = stripped[4:]
            result.append(f"<h3>{heading}</h3>")
        else:
            buf.append(stripped)
    flush()
    return "\n".join(result)


def _parse_list(text: str) -> list[str]:
    """Parse bullet list items."""
    items = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:])
        elif line and not line.startswith("#"):
            items.append(line)
    return items


def _parse_explanations(text: str) -> list[dict]:
    """Parse explanations: ### 01 · Title \\n body..."""
    expls = []
    # Split on ### headers
    parts = re.split(r"\n### (.+)\n", text)
    # Handle parts[0] if it starts with ###
    if parts[0].startswith("### "):
        first = parts[0][4:].split("\n", 1)
        header = first[0].strip()
        body = first[1].strip() if len(first) > 1 else ""
        clean_header = re.sub(r"^\d+\s*[·•]\s*", "", header)
        expls.append({"heading": clean_header, "body": _md_to_html(body)})
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        # Try to strip number prefix
        clean_header = re.sub(r"^\d+\s*[·•]\s*", "", header)
        expls.append({"heading": clean_header, "body": _md_to_html(body)})
    return expls


def _parse_try_block(text: str) -> dict:
    """Parse try-it block: ### question \\n body..."""
    parts = re.split(r"\n### (.+)\n", text)
    question = ""
    body = ""
    if parts[0].startswith("### "):
        first = parts[0][4:].split("\n", 1)
        question = first[0].strip()
        body = first[1].strip() if len(first) > 1 else ""
    elif len(parts) > 1:
        question = parts[1].strip()
        body = parts[2].strip() if len(parts) > 2 else ""
    else:
        body = text.strip()
    return {"question": question, "body": _md_to_html(body)}


def _parse_math_block(text: str) -> dict:
    """Parse math block: ### heading \\n intuition \\n formula: ... \\n - sym: meaning"""
    lines = text.strip().split("\n")
    heading = ""
    intuition_lines = []
    formula = ""
    variables = []
    in_formula = False
    in_intuition = True

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("### "):
            heading = stripped[4:]
            continue
        if stripped.lower().startswith("formula:") or stripped.lower().startswith("公式:"):
            in_formula = True
            in_intuition = False
            formula = stripped.split(":", 1)[1].strip()
            continue
        if in_formula and stripped.startswith("- "):
            parts = stripped[2:].split(":", 1)
            if len(parts) == 2:
                variables.append({"symbol": parts[0].strip(), "meaning": parts[1].strip()})
            continue
        if in_intuition and stripped:
            intuition_lines.append(stripped)

    return {
        "heading": heading,
        "intuition": _md_to_html("\n".join(intuition_lines)),
        "formula": formula,
        "variables": variables,
    }


def _parse_pitfalls(text: str) -> list[dict]:
    """Parse pitfalls: ### 误区\n校正\n重要性"""
    pitfalls = []
    parts = re.split(r"\n### (.+)\n", text)
    # Handle parts[0] if it starts with ###
    if parts[0].startswith("### "):
        first = parts[0][4:].split("\n", 1)
        mistake = first[0].strip()
        body = first[1].strip() if len(first) > 1 else ""
        pitfalls.append(_parse_one_pitfall(mistake, body))
    for i in range(1, len(parts), 2):
        mistake = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        pitfalls.append(_parse_one_pitfall(mistake, body))
    return pitfalls


def _parse_one_pitfall(mistake: str, body: str) -> dict:
    body_lines = body.split("\n")
    correction = ""
    importance = ""
    for line in body_lines:
        s = line.strip()
        if s.startswith("校正") or s.startswith("纠正"):
            correction = re.sub(r"^[校正纠正]+[：:]?\s*", "", s)
        elif s.startswith("重要") or s.startswith("为什么"):
            importance = re.sub(r"^[重要为什么]+[性：:]?\s*", "", s)
        elif correction:
            importance = s
    return {"mistake": mistake, "correction": correction, "importance": importance}


# ── Build ──


def build(env: Environment, course_data: dict):
    course = course_data["course"]
    course.setdefault("overview", None)
    course.setdefault("story_flow", None)
    course.setdefault("lenses", None)

    css_version = _git_short_hash()  # auto cache-bust per commit

    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "chapters").mkdir(exist_ok=True)
    (SITE / "modules").mkdir(exist_ok=True)

    # Copy assets: engine base styles.css + book overrides
    engine_css = ROOT / "engine" / "styles.css"  # from jbook-engine submodule
    if engine_css.exists():
        shutil.copy2(engine_css, SITE / "styles.css")
    # Book-specific assets (can override engine defaults)
    if ASSETS.exists():
        for f in ASSETS.iterdir():
            dest = SITE / f.name
            if f.is_file():
                shutil.copy2(f, dest)
            elif f.is_dir() and not (SITE / f.name).exists():
                shutil.copytree(f, dest)

    # Find prev/next helpers
    all_chapters = []
    for mod in course["modules"]:
        for ch in mod["chapters"]:
            all_chapters.append((mod, ch))

    # Build chapters
    for mod in course["modules"]:
        module_id = mod["id"]
        module_label = f"第{int(module_id) + 1}章"

        for ci, ch in enumerate(mod["chapters"]):
            chapter_id = ch["id"]
            chapter_data = load_chapter_content(chapter_id)

            # Merge YAML metadata with content data
            merged = {**ch, **chapter_data}
            # Ensure forward_hook from YAML is used if not in MD
            if "forward_hook" not in merged and ch.get("forward_hook"):
                merged["forward_hook"] = ch["forward_hook"]

            # Find prev/next
            prev_ch = mod["chapters"][ci - 1] if ci > 0 else None
            next_ch = mod["chapters"][ci + 1] if ci < len(mod["chapters"]) - 1 else None

            html = env.get_template("chapter.html").render(
                css_version=css_version,
                course=course,
                module=mod,
                module_id=module_id,
                module_label=module_label,
                chapter=merged,
                chapter_id=chapter_id,
                prev_chapter=prev_ch,
                next_chapter=next_ch,
                page_type="chapter",
                asset_path=ASSET_PATH,
            )

            out = SITE / "chapters" / f"{chapter_id}.html"
            out.write_text(html, encoding="utf-8")
            print(f"  ✓ chapters/{chapter_id}.html — {ch['title']}")

        # Build module overview
        mod_idx = next(i for i, m in enumerate(course["modules"]) if m["id"] == module_id)
        prev_module = course["modules"][mod_idx - 1] if mod_idx > 0 else None
        next_module = course["modules"][mod_idx + 1] if mod_idx < len(course["modules"]) - 1 else None

        html = env.get_template("module.html").render(
            css_version=css_version,
            course=course,
            module=mod,
            module_id=module_id,
            module_label=module_label,
            prev_module=prev_module,
            next_module=next_module,
            chapter_id=None,
            page_type="module",
            asset_path=ASSET_PATH,
        )
        (SITE / "modules" / f"{mod['slug']}.html").write_text(html, encoding="utf-8")
        print(f"  ✓ modules/{mod['slug']}.html — {mod['title']}")

    # Build index
    html = env.get_template("index.html").render(
        css_version=css_version,
        course=course,
        module_id=None,
        chapter_id=None,
        page_type="index",
        asset_path="",
    )
    (SITE / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ index.html")

    # Build concepts page (collect from all modules)
    all_concepts = []
    for mod in course["modules"]:
        for ch in mod["chapters"]:
            if ch.get("concepts"):
                for c in ch["concepts"]:
                    all_concepts.append({**c, "module": mod["title"], "chapter": ch["title"]})

    concepts_html = env.get_template("concepts.html").render(
        css_version=css_version,
        course=course, concepts=all_concepts, asset_path="",
        module_id=None, chapter_id=None, page_type="concepts",
    )
    (SITE / "concepts.html").write_text(concepts_html, encoding="utf-8")
    print(f"  ✓ concepts.html — {len(all_concepts)} concepts")

    # Build source-map page (CFA syllabus → course module mapping)
    source_map = _build_source_map(course)
    source_map_html = env.get_template("source-map.html").render(
        css_version=css_version,
        course=course, source_map=source_map, asset_path="",
        module_id=None, chapter_id=None, page_type="source-map",
    )
    (SITE / "source-map.html").write_text(source_map_html, encoding="utf-8")
    print(f"  ✓ source-map.html — {len(source_map)} modules")

    # SVG lint (warning only, non-blocking)
    _run_svg_lint()


def main():
    print("Building CFA course site...\n")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=False)
    course_data = load_course()

    # Inject overview, story_flow, lenses from content/index.md
    index_content_path = CONTENT / "index.md"
    if index_content_path.exists():
        index_md = index_content_path.read_text(encoding="utf-8")
        sections = _parse_sections(index_md)
        course = course_data["course"]
        if "Overview" in sections:
            course["overview"] = _md_to_html(sections["Overview"])
        if "StoryFlow" in sections:
            course["story_flow"] = sections["StoryFlow"].strip()
        if "Lenses" in sections:
            course["lenses"] = _parse_lenses(sections["Lenses"])

    build(env, course_data)
    print(f"\n✨ Done. Site at {SITE}/")


def _parse_lenses(text: str) -> list[dict]:
    lenses = []
    # Ensure leading newline: _parse_sections may have .strip()'d it away
    if not text.startswith("\n"):
        text = "\n" + text
    parts = re.split(r"\n### (.+)\n", text)
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        # Strip emoji/icon prefix from title (already handled separately)
        title = re.sub(r"^[📊⚠️🧠💰💡📈]\s*", "", title)
        # Detect theme
        theme = "cash"
        if "风险" in title:
            theme = "risk"
        elif "决策" in title or "判断" in title:
            theme = "decision"
        # Extract emoji
        emoji = "📊"
        if "风险" in title:
            emoji = "⚠️"
        elif "决策" in title or "判断" in title:
            emoji = "🧠"
        lenses.append({"title": title, "description": body, "emoji": emoji, "theme": theme})
    return lenses


def _build_source_map(course: dict) -> list[dict]:
    """Build syllabus mapping: CFA topic → lecture videos → course module."""
    return [
        {
            "topic": "Portfolio Management",
            "links": [
                {"label": "L1", "url": "https://www.youtube.com/watch?v=EiPDSsIgas4", "title": "Introduction to Risk Management - CFA Level 1 Learning Module 6 Full Lecture 2026"},
                {"label": "L2", "url": "https://www.youtube.com/watch?v=ruSR76jRrEI", "title": "Behavioral Biases of Individuals - CFA Level 1 Behavioral Finance Full Lecture 2026"},
                {"label": "L3", "url": "https://www.youtube.com/watch?v=UqMEgz5W0zo", "title": "Basics of Portfolio Planning and Construction - CFA Level 1 Portfolio Management Full Lecture 2026"},
                {"label": "L4", "url": "https://www.youtube.com/watch?v=QIVebk8B_Pc", "title": "Portfolio Management: An Overview - CFA Level 1 Portfolio Management Full Lecture 2026"},
                {"label": "L5", "url": "https://www.youtube.com/watch?v=HTytCATw-hU", "title": "Capital Market Theory, CML, CAPM, SML & Beta - CFA Level 1 Portfolio Management 2026"},
                {"label": "L6", "url": "https://www.youtube.com/watch?v=zOykE6RslpU", "title": "Introduction to Portfolio Management, Diversification, Efficient Frontier & CAL - CFA Level 1 2026"},
            ],
            "course_position": "模块 10",
            "approach": "从开头移到结尾，作为整合层",
        },
        {
            "topic": "Alternative Investments",
            "links": [
                {"label": "L7", "url": "https://www.youtube.com/watch?v=L2YyF9BKmRE", "title": "The Introduction of Digital Assets - Module 7- ALTERNATIVE-CFA® Level I 2026"},
                {"label": "L8", "url": "https://www.youtube.com/watch?v=cmd7rP_fT2E", "title": "Hedge Funds - Module 6- ALTERNATIVE-CFA® Level I 2026"},
                {"label": "L9", "url": "https://www.youtube.com/watch?v=dLaazU0yuhI", "title": "Natural Resources - Module 5- ALTERNATIVE-CFA® Level I 2025 (and 2026)"},
                {"label": "L10", "url": "https://www.youtube.com/watch?v=RbfIjqUe9Hg", "title": "Real Estate and Infrastructure - Module 4- ALTERNATIVE-CFA® Level I 2026"},
                {"label": "L11", "url": "https://www.youtube.com/watch?v=_MvgPs_-o6U", "title": "Investments in Private Capital Equity and Debt - Module 3- ALTERNATIVE-CFA® Level I 2026"},
                {"label": "L12", "url": "https://www.youtube.com/watch?v=BPYS1CFG1uM", "title": "Alternative Investment and Performance Returns - Module 2- ALTERNATIVE-CFA® Level I 2025 (and 2026)"},
                {"label": "L13", "url": "https://www.youtube.com/watch?v=-6DttehnLDg", "title": "Alternative Investment Features Methods Structures-Module 1-ALTERNATIVE-CFA® Level I 2026"},
            ],
            "course_position": "模块 9",
            "approach": "按资产结构、流动性和组合角色重排",
        },
        {
            "topic": "Equity Investments",
            "links": [
                {"label": "L14", "url": "https://www.youtube.com/watch?v=yivBQJe3ttg", "title": "Equity Valuation: Concepts and Basic Tools - Module 8 - EQUITY - CFA® Level I 2026"},
                {"label": "L15", "url": "https://www.youtube.com/watch?v=NNyMenVV6pk", "title": "Company Analysis: Forecasting - Module 7 - EQUITY - CFA® Level I 2026"},
                {"label": "L16", "url": "https://www.youtube.com/watch?v=N6DlJoOWAQk", "title": "Industry and Competitive Analysis - Module 6 - EQUITY - CFA® Level I 2026"},
                {"label": "L17", "url": "https://www.youtube.com/watch?v=d1Gtxrx7R60", "title": "Company Analysis Past and Present - Module 5 - EQUITY - CFA® Level I 2026"},
                {"label": "L18", "url": "https://www.youtube.com/watch?v=xQY71yCiqn8", "title": "Overview of Equity Securities - Module 4 - EQUITY - CFA® Level I 2026"},
                {"label": "L19", "url": "https://www.youtube.com/watch?v=vdoXPDaR6-g", "title": "Market Efficiency - Module 3 - EQUITY - CFA® Level I 2026"},
                {"label": "L20", "url": "https://www.youtube.com/watch?v=OEt_Bm-0I_A", "title": "Security Market Indexes - Module 2 - EQUITY - CFA® Level I 2026"},
                {"label": "L21", "url": "https://www.youtube.com/watch?v=AOtoOS4WsHI", "title": "Market Organization and Structure - Module 1 - EQUITY - CFA® Level I 2026"},
            ],
            "course_position": "模块 3、6",
            "approach": "市场机制前置，股票估值后置",
        },
        {
            "topic": "Derivatives",
            "links": [
                {"label": "L22", "url": "https://www.youtube.com/watch?v=xfQRmnRIZNM", "title": "Valuing a Derivative Using Binomial Model - Module 10- Derivatives - CFA® Level I 2026"},
                {"label": "L24", "url": "https://www.youtube.com/watch?v=De3KgOIxOJk", "title": "Option Replication Using Put Call Parity - Module 9- Derivatives - CFA® Level I 2026"},
                {"label": "L25", "url": "https://www.youtube.com/watch?v=Dp6Nl_WnNvA", "title": "Pricing and Valuation of Options - Module 8 - Derivatives - CFA® Level I 2026"},
                {"label": "L26", "url": "https://www.youtube.com/watch?v=I5xvmxZqb10", "title": "Pricing and Valuation of Swaps - Module 7 - Derivatives - CFA® Level I 2026"},
                {"label": "L27", "url": "https://www.youtube.com/watch?v=n9Gq3TYwaks", "title": "Pricing and Valuation of Futures Contracts - Module 6 - Derivatives - CFA® Level I 2026"},
                {"label": "L28", "url": "https://www.youtube.com/watch?v=IsUZKP4UTME", "title": "Pricing and Valuation of Forward Contracts - Module 5 - Derivatives - CFA® Level I 2026"},
                {"label": "L29", "url": "https://www.youtube.com/watch?v=hAGXgqaOWhg", "title": "Arbitrage, Replication, Cost of Carry - Module 4 Derivatives -CFA® Level I 2026"},
                {"label": "L30", "url": "https://www.youtube.com/watch?v=p9frqJtkJ0g", "title": "Derivative Benefits Risks Issuer Investor - Module 3 - Derivatives - CFA® Level I 2026"},
                {"label": "L31", "url": "https://www.youtube.com/watch?v=CAY-Q8tHSY4", "title": "Forward Commitment and Contingent Claim - Module 2 - Derivatives - CFA® Level I 2026"},
                {"label": "L32", "url": "https://www.youtube.com/watch?v=k9kQ1avOHvg", "title": "Derivative Instrument and Market Features - Module 1 - Derivatives - CFA® Level I 2026"},
            ],
            "course_position": "模块 8",
            "approach": "按风险转移、无套利和复制关系重排",
        },
        {
            "topic": "Financial Statement Analysis",
            "links": [
                {"label": "L23", "url": "https://www.youtube.com/watch?v=z9Qu4U1OW5E", "title": "Introduction to Financial Statement Analysis - Part 2 - Module 1 - FSA- CFA® Level I 2025 (and 2026)"},
                {"label": "L52", "url": "https://www.youtube.com/watch?v=d4Y1MBhv7KE", "title": "Introduction to Financial Statement Modeling - Last Module 12 - FSA - CFA® Level I 2025 (and 2026)"},
                {"label": "L53", "url": "https://www.youtube.com/watch?v=fjr24CNyQkA", "title": "Financial Analysis Techniques - Module 11 - FSA - CFA® Level I 2025 (and 2026)"},
                {"label": "L54", "url": "https://www.youtube.com/watch?v=unzrPjQPAtA", "title": "Financial Reporting Quality - Module 10 - FSA - CFA® Level I 2025 (and 2026)"},
                {"label": "L55", "url": "https://www.youtube.com/watch?v=JhA_XWAHsdI", "title": "Income Taxes - Module 9 - FSA - CFA® Level I 2025 (and 2026)"},
                {"label": "L56", "url": "https://www.youtube.com/watch?v=pqj4j57RZ6U", "title": "Topics in Long Term Liabilities and Equity - Module 8 - FSA - CFA® Level I 2025 (and 2026)"},
                {"label": "L57", "url": "https://www.youtube.com/watch?v=rapZrX93J8A", "title": "Analysis of Long Term Assets - Module 7 - FSA - CFA® Level I 2025 (and 2026)"},
                {"label": "L58", "url": "https://www.youtube.com/watch?v=MSbeebN1cMY", "title": "Analysis of Inventories - Module 6 - FSA - CFA® Level I 2025 (and 2026)"},
                {"label": "L59", "url": "https://www.youtube.com/watch?v=cmAuHg_bgAg", "title": "Analyzing Statement of Cash Flows II - Module 5 - FSA - CFA® Level I 2025 (and 2026)"},
                {"label": "L60", "url": "https://www.youtube.com/watch?v=BaLPqL2_hps", "title": "Cash Flow Statements - Module 4 - FSA - CFA® Level I 2025 (and 2026)"},
                {"label": "L61", "url": "https://www.youtube.com/watch?v=PqQOtNPHZiU", "title": "Analyzing Balance Sheets - Module 3 - FSA - CFA® Level I 2025 (and 2026)"},
                {"label": "L62", "url": "https://www.youtube.com/watch?v=HpZ7-nKVBjM", "title": "Analyzing Income Statements - Module 2 - FSA- CFA® Level I 2025 (and 2026)"},
                {"label": "L63", "url": "https://www.youtube.com/watch?v=nZ_TviK9IWY", "title": "Introduction to Financial Statement Analysis - Module 1 - FSA- CFA® Level I 2025 (and 2026)"},
            ],
            "course_position": "模块 5",
            "approach": "与企业经营合并",
        },
        {
            "topic": "Fixed Income",
            "links": [
                {"label": "L33", "url": "https://www.youtube.com/watch?v=q-da_tXJhfI", "title": "Mortgage-Backed Security (MBS) Instrument - Module 19 - FIXED INCOME-CFA® Level I 2026"},
                {"label": "L34", "url": "https://www.youtube.com/watch?v=QcEae2T-JjI", "title": "Asset Backed Security ABS Instrument - Module 18 - FIXED INCOME-CFA® Level I 2026"},
                {"label": "L35", "url": "https://www.youtube.com/watch?v=8-HM0Jdtn6U", "title": "Fixed Income Securitization - Module 17 - FIXED INCOME - CFA® Level I 2026"},
                {"label": "L36", "url": "https://www.youtube.com/watch?v=gdEg4Z9PGZ4", "title": "Credit Analysis for Corporate Issuers - Module 16 - FIXED INCOME - CFA® Level I 2026"},
                {"label": "L37", "url": "https://www.youtube.com/watch?v=c5vcO3SvuT4", "title": "Credit Analysis for Government Issuers - Module 15 - FIXED INCOME- CFA® Level I 2026"},
                {"label": "L38", "url": "https://www.youtube.com/watch?v=cbhJWQN62Oo", "title": "Credit Risk - Module 14 - FIXED INCOME- CFA® Level I 2026"},
                {"label": "L39", "url": "https://www.youtube.com/watch?v=VWSWTLd65_g", "title": "Curve Based and Empirical fixed income Risk - Module 13 - FIXED INCOME- CFA® Level I 2026"},
                {"label": "L40", "url": "https://www.youtube.com/watch?v=P2u9ZCajCfo", "title": "Yield Based Bond Convexity - Module 12 - FIXED INCOME- CFA® Level I 2026"},
                {"label": "L41", "url": "https://www.youtube.com/watch?v=odqDOu46XXI", "title": "Yield Based Bond Duration Measures - Module 11 - FIXED INCOME- CFA® Level I 2026"},
                {"label": "L42", "url": "https://www.youtube.com/watch?v=A7Cp7vIqLk0", "title": "Interest Rate Risk and Return - Module 10 - FIXED INCOME- CFA® Level I 2026"},
                {"label": "L43", "url": "https://www.youtube.com/watch?v=3HLsos4y058", "title": "Term Structure of Interest Rates Spot - Module 9 - FIXED INCOME -CFA® Level I 2026"},
                {"label": "L44", "url": "https://www.youtube.com/watch?v=L8lWJHAHJ_E", "title": "Yield Spread Measures Floating Rate Instrument - Module 8-FIXED INCOME- CFA® Level I 2026"},
                {"label": "L45", "url": "https://www.youtube.com/watch?v=1wwonPQquwQ", "title": "Yield Spread Measures for Fixed Rate Bonds - Module 7 - FIXED INCOME- CFA® Level I 2026"},
                {"label": "L46", "url": "https://www.youtube.com/watch?v=9VV4x8SyZGc", "title": "Fixed-Income Bond Valuation:Prices - Module 6 - FIXED INCOME- CFA® Level I 2026"},
                {"label": "L47", "url": "https://www.youtube.com/watch?v=Azer2zvukok", "title": "Fixed Income Markets for Government Issuers - Module 5 - FIXED INCOME- CFA® Level I 2026"},
                {"label": "L48", "url": "https://www.youtube.com/watch?v=ebpoOsWhvsU", "title": "Fixed Income Markets for Corporate Issuers - Module 4 - FIXED INCOME- CFA® Level I 2026"},
                {"label": "L49", "url": "https://www.youtube.com/watch?v=MXgD9Mtu9Es", "title": "Fixed Income Issuance and Trading - Module 3 - FIXED INCOME- CFA® Level I 2026"},
                {"label": "L50", "url": "https://www.youtube.com/watch?v=9qqm6LMrwbg", "title": "Fixed Income Cash Flows and Types - Module 2 - FIXED INCOME- CFA® Level I 2026"},
                {"label": "L51", "url": "https://www.youtube.com/watch?v=R4EHHWFiZ6s", "title": "Fixed Income Instrument Features - Module 1 - FIXED INCOME- CFA® Level I 2026"},
            ],
            "course_position": "模块 7",
            "approach": "从债券合同到证券化完整展开",
        },
        {
            "topic": "Corporate Issuers",
            "links": [
                {"label": "L64", "url": "https://www.youtube.com/watch?v=7RxzgYXmMk8", "title": "Business Models - Module 7 - Corporate Issuer - CFA® Level I 2026"},
                {"label": "L65", "url": "https://www.youtube.com/watch?v=6jBkrUMqdIA", "title": "Capital Structure - Module 6 - Corporate Issuer - CFA® Level I 2026"},
                {"label": "L66", "url": "https://www.youtube.com/watch?v=8T87fLNFdMc", "title": "Capital Investments and Capital Allocation - Module 5 -Corporate Issuer - CFA® Level I 2026"},
                {"label": "L67", "url": "https://www.youtube.com/watch?v=4hs4nbBLBBY", "title": "Working Capital and Liquidity - Module 4 - Corporate Issuer - CFA® Level I 2026"},
                {"label": "L68", "url": "https://www.youtube.com/watch?v=xd37XWohe1g", "title": "Corporate Governance - Module 3 - Corporate Issuer - CFA® Level I 2026"},
                {"label": "L69", "url": "https://www.youtube.com/watch?v=Uox_LKJIhQ0", "title": "Investors and stakeholders - Module 2 - Corporate Issuer - CFA® Level I 2026"},
                {"label": "L70", "url": "https://www.youtube.com/watch?v=pgagMoipGOg", "title": "Organizational Forms, Corporate Issuer - Module 1 - Corporate Issuer - CFA® Level I 2026"},
            ],
            "course_position": "模块 5",
            "approach": "与 FSA 共同构成企业现金流机器",
        },
        {
            "topic": "Economics",
            "links": [
                {"label": "L71", "url": "https://www.youtube.com/watch?v=BnmzfQcOZBk", "title": "Exchange Rate Calculations - Last Module 8 - Economics - CFA® Level I 2026"},
                {"label": "L72", "url": "https://www.youtube.com/watch?v=P-d0NQ8aANo", "title": "Currency Exchange Rates - Module 7 - Economics - CFA® Level I 2026"},
                {"label": "L73", "url": "https://www.youtube.com/watch?v=sMg0IMb0qg4", "title": "International Trade - Module 6 - Economics - CFA® Level I 2026"},
                {"label": "L74", "url": "https://www.youtube.com/watch?v=rIvNm4Mz8cE", "title": "Introduction to Geopolitics - Module 5 - Economics - CFA® Level I 2026"},
                {"label": "L75", "url": "https://www.youtube.com/watch?v=xVVPn5ETShg", "title": "Monetary Policy - Module 4 - Economics - CFA® Level I 2026"},
                {"label": "L76", "url": "https://www.youtube.com/watch?v=8OJ5G_h5rIY", "title": "Fiscal Policy - Module 3 - Economics - CFA® Level I 2026"},
                {"label": "L77", "url": "https://www.youtube.com/watch?v=R1PHRsWMEB8", "title": "Understanding Business Cycle - Module 2 - Economics - CFA® Level I 2026"},
                {"label": "L78", "url": "https://www.youtube.com/watch?v=27rnAR8RaPo", "title": "Firms and Market Structure - Module 1 - Economics - CFA® Level I 2026"},
            ],
            "course_position": "模块 3、4",
            "approach": "市场结构前置，其余作为宏观环境",
        },
        {
            "topic": "Quantitative Methods",
            "links": [
                {"label": "L79", "url": "https://www.youtube.com/watch?v=CdyOnW62Y90", "title": "Introduction to Big Data Techniques - Module 11 - Quant. Methods - CFA® Level I 2026"},
                {"label": "L80", "url": "https://www.youtube.com/watch?v=2H6K4Z18oOs", "title": "Simple Linear Regression - Module 10 - Quantitative Methods - CFA® Level I 2026"},
                {"label": "L81", "url": "https://www.youtube.com/watch?v=kLAJxQeXM1w", "title": "Parametric and Non-Parametric Tests of Independence - Module 9 - QM - CFA® Level I 2026"},
                {"label": "L82", "url": "https://www.youtube.com/watch?v=UrahqsmrelM", "title": "Hypothesis Testing - Module 8 - Quantitative Methods - CFA® Level I 2026"},
                {"label": "L83", "url": "https://www.youtube.com/watch?v=bOTnePllDz0", "title": "Estimation and Inference - Module 7 - Quantitative Methods - CFA® Level I 2026"},
                {"label": "L84", "url": "https://www.youtube.com/watch?v=e9qAm36NPXc", "title": "Simulation Methods - Module 6 - Quantitative Methods - CFA® Level I 2026"},
                {"label": "L85", "url": "https://www.youtube.com/watch?v=Y0l9zhcaqzM", "title": "Portfolio Mathematics - Module 5 - Quantitative Methods - CFA® Level I 2026"},
                {"label": "L86", "url": "https://www.youtube.com/watch?v=is4WGA4-M7w", "title": "Probability Trees and Conditional Expectations - Module 4 - Quant. M. - CFA® Level I 2026"},
                {"label": "L87", "url": "https://www.youtube.com/watch?v=EVqA4DbJlyA", "title": "Statistical Measures of Asset Returns - Module 3 - Quant. Methods - CFA® Level I 2026"},
                {"label": "L88", "url": "https://www.youtube.com/watch?v=WusTmWUWtr0", "title": "Time Value of Money in Finance - Module 2 - Quantitative Methods - CFA® Level I 2026"},
                {"label": "L89", "url": "https://www.youtube.com/watch?v=lFrxwyBJ6qs", "title": "Rates and Returns - Module 1 - Quantitative Methods - CFA® Level I 2026"},
            ],
            "course_position": "模块 2、10",
            "approach": "拆成基础工具、数据工具和组合工具",
        },
    ]


def _run_svg_lint():
    """Run SVG lint as a non-blocking check."""
    import subprocess
    from pathlib import Path
    lint_path = Path(__file__).parent / "svg_lint.py"
    if not lint_path.exists():
        return
    result = subprocess.run(["python3", str(lint_path)], capture_output=True, text=True)
    if result.returncode == 0:
        print("  ✅ SVG lint: all clear")
    else:
        issue_count = result.stdout.count("crosses rect") + result.stdout.count("overflow")
        print(f"  ⚠️  SVG lint: {issue_count} potential issues (see `python3 engine/svg_lint.py`)")


if __name__ == "__main__":
    main()
