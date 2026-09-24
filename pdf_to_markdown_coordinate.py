import json
from pathlib import Path
import re

import pymupdf


PDF_PATH = Path("/home/preetham/CIGNA/Data/Cigna_Lumbar_Fusion.pdf")
OUTPUT_PATH = Path("/home/preetham/CIGNA/OUTPUT_trail/Lumbar_Fusion.md")
JSON_OUTPUT_PATH = Path("/home/preetham/CIGNA/OUTPUT_trail/Lumbar_Fusion.json")

BULLET_LEVELS = {
    "•": 0,
    "◦": 1,
    "▪": 2,
}

DEFINITION_HEADINGS = {
    "Kellgren-Lawrence Grading System",
    "Knee Arthroplasty",
    "Knee Replacement",
}


def clean_text(value: str) -> str:
    value = value.replace("\u00ad", "")
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def markdown_cell(value: str) -> str:
    value = clean_text(value).replace("|", "\\|")
    return value.replace("\n", "<br>")


def table_markdown(table) -> str:
    rows = table.extract()
    if not rows:
        return ""

    width = max(len(row) for row in rows)
    normalized = [list(row) + [""] * (width - len(row)) for row in rows]
    output = [
        "| " + " | ".join(markdown_cell(cell or "") for cell in normalized[0]) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]

    for row in normalized[1:]:
        output.append("| " + " | ".join(markdown_cell(cell or "") for cell in row) + " |")

    return "\n".join(output)


def span_text(line: dict) -> str:
    return clean_text("".join(span.get("text", "") for span in line.get("spans", [])))


def block_is_heading(block: dict, text: str) -> bool:
    spans = [
        span
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip()
    ]
    if not spans or not text or len(text) > 130:
        return False

    largest_size = max(float(span.get("size", 0)) for span in spans)
    all_bold = all(
        "bold" in span.get("font", "").lower()
        or "black" in span.get("font", "").lower()
        for span in spans
    )
    if re.match(r"^(CMM\.SP\.|v\d)", text, re.IGNORECASE):
        return False

    return largest_size >= 13 or (all_bold and len(text.splitlines()) <= 2)


def line_is_subheading(line: dict, text: str) -> bool:
    spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
    if not spans or not text or len(text) > 100:
        return False

    all_bold = all(
        "bold" in span.get("font", "").lower()
        or "black" in span.get("font", "").lower()
        for span in spans
    )
    if not all_bold or text.startswith(tuple(BULLET_LEVELS)):
        return False

    return bool(
        re.match(
            r"^(Radiculopathy|Myelopathy|.*Pseudoarthrosis|"
            r"Unremitting Neck Pain|Failed Cervical Disc Arthroplasty Implant|"
            r"Malposition or Failure of Implant|Health Equity Considerations|"
            r"Not Medically Necessary|Experimental, Investigational, or Unproven)",
            text,
            re.IGNORECASE,
        )
    )


def definition_label(block: dict) -> str:
    """Get a bold definition label when it shares a line with body text."""

    if not block.get("lines"):
        return ""

    first_line = block["lines"][0]
    bold_spans = [
        span
        for span in first_line.get("spans", [])
        if span.get("text", "").strip()
        and (
            "bold" in span.get("font", "").lower()
            or "black" in span.get("font", "").lower()
        )
    ]
    label = clean_text("".join(span.get("text", "") for span in bold_spans))
    return label if label in DEFINITION_HEADINGS else ""


def render_block(block: dict) -> str:
    source_lines = [
        (line, span_text(line))
        for line in block.get("lines", [])
    ]
    source_lines = [(line, text) for line, text in source_lines if text]
    lines = [text for _, text in source_lines]
    if not lines:
        return ""

    label = definition_label(block)
    if label:
        first_line = block["lines"][0]
        body_parts = [
            span.get("text", "")
            for span in first_line.get("spans", [])
            if not (
                "bold" in span.get("font", "").lower()
                or "black" in span.get("font", "").lower()
            )
        ]
        body_lines = [clean_text("".join(body_parts))] if body_parts else []
        body_lines.extend(lines[1:])
        return f"### {label}\n\n" + "\n".join(line for line in body_lines if line)

    text = " ".join(lines)
    if text in DEFINITION_HEADINGS:
        return f"### {text}"

    if block_is_heading(block, text):
        return f"## {text}"

    output = []
    pending_bullet = None

    for source_line, line in source_lines:
        if line_is_subheading(source_line, line):
            output.append(f"## {line}")
            continue

        bullet = next((symbol for symbol in BULLET_LEVELS if line.startswith(symbol)), None)
        if bullet:
            content = line[len(bullet):].strip()
            indent = "  " * BULLET_LEVELS[bullet]
            if content:
                output.append(f"{indent}- {content}")
            else:
                pending_bullet = (indent, len(output))
            continue

        if pending_bullet:
            indent, index = pending_bullet
            if index < len(output):
                output[index] = f"{indent}- {line}"
            else:
                output.append(f"{indent}- {line}")
            pending_bullet = None
        else:
            output.append(line)

    return "\n".join(output)


def block_overlaps_table(block: dict, table_bbox) -> bool:
    rect = pymupdf.Rect(block["bbox"])
    table_rect = pymupdf.Rect(table_bbox)
    return rect.intersects(table_rect)


def render_page(page: pymupdf.Page) -> str:
    page_dict = page.get_text("dict", sort=True)
    blocks = [block for block in page_dict.get("blocks", []) if block.get("type") == 0]
    items = []

    try:
        tables = page.find_tables().tables
    except (AttributeError, RuntimeError):
        tables = []

    for table in tables:
        items.append((table.bbox[1], table_markdown(table)))

    for block in blocks:
        block_width = block["bbox"][2] - block["bbox"][0]
        block_height = block["bbox"][3] - block["bbox"][1]
        if block_height > block_width * 3:
            continue
        if any(block_overlaps_table(block, table.bbox) for table in tables):
            continue
        rendered = render_block(block)
        if rendered:
            items.append((block["bbox"][1], rendered))

    items.sort(key=lambda item: item[0])
    merged = []

    for y_position, text in items:
        if (
            merged
            and text.startswith("## ")
            and merged[-1][1].startswith("## ")
            and y_position - merged[-1][0] < 45
        ):
            merged[-1] = (
                y_position,
                f"{merged[-1][1]} {text[3:]}"
            )
        else:
            merged.append((y_position, text))

    return "\n\n".join(text for _, text in merged)


def extract_page_data(page: pymupdf.Page, page_number: int) -> dict:
    """Return structured data using the same coordinate-aware extraction path."""

    page_markdown = render_page(page)
    headings = [
        line[3:].strip()
        for line in page_markdown.splitlines()
        if line.startswith("## ")
    ]

    try:
        tables = page.find_tables().tables
    except (AttributeError, RuntimeError):
        tables = []

    table_rows = [
        [[clean_text(cell or "") for cell in row] for row in table.extract()]
        for table in tables
    ]

    return {
        "page": page_number,
        "raw_text": page.get_text("text", sort=True),
        "markdown": page_markdown,
        "headings": headings,
        "tables": table_rows,
    }


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(PDF_PATH)
    pages = []
    structured_pages = []

    for page_number, page in enumerate(document, start=1):
        page_data = extract_page_data(page, page_number)
        structured_pages.append(page_data)
        pages.append(
            f"<!-- PDF page {page_number} / {len(document)} -->\n\n"
            f"{page_data['markdown']}"
        )

    OUTPUT_PATH.write_text("\n\n---\n\n".join(pages) + "\n", encoding="utf-8")
    JSON_OUTPUT_PATH.write_text(
        json.dumps(
            {
                "source": str(PDF_PATH),
                "page_count": len(document),
                "pages": structured_pages,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Wrote {JSON_OUTPUT_PATH}")
    print(f"Pages: {len(document)}")


if __name__ == "__main__":
    main()
