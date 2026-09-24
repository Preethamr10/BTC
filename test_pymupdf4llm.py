import json
import re
from pathlib import Path
import pymupdf4llm


# ============================================================
# INPUT / OUTPUT
# ============================================================

PDF_PATH = Path(
    "/home/preetham/CIGNA/Data/Cigna_ACDF.pdf"
)

OUTPUT_DIR = Path(
    "/home/preetham/CIGNA/OUTPUT_trail"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


def promote_section_headings(markdown: str) -> str:
    """Turn standalone bold section labels into visible Markdown headings."""

    lines = []

    for line in markdown.splitlines():
        if line.startswith("    "):
            line = line[4:]

        match = re.fullmatch(r"(\s*)\*\*([^*]+)\*\*(\s*)", line)

        if match:
            label = match.group(2).strip()

            if (
                label
                and not any(character in label for character in ".():/<>")
                and not label.lower().startswith("v")
            ):
                line = f"{match.group(1)}### **{label}**{match.group(3)}"

        lines.append(line)

    return "\n".join(lines)


# ============================================================
# STEP 1: PDF -> MARKDOWN
# ============================================================

print("Converting PDF to Markdown...")

pymupdf4llm.use_layout(False)

page_chunks = pymupdf4llm.to_markdown(
    str(PDF_PATH),
    page_chunks=True,
    page_separators=False
)

markdown_pages = []

for page_number, chunk in enumerate(page_chunks, start=1):
    page_text = chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
    page_text = promote_section_headings(page_text).strip()
    markdown_pages.append(
        f"<!-- PDF page {page_number} / {len(page_chunks)} -->\n\n{page_text}"
    )

md_text = "\n\n---\n\n".join(markdown_pages) + "\n"



# ============================================================
# STEP 2: SAVE MARKDOWN
# ============================================================

OUTPUT_MD = OUTPUT_DIR / "Cigna_ACDF.md"
OUTPUT_JSON = OUTPUT_DIR / "Cigna_ACDF.json"

OUTPUT_MD.write_text(
    md_text,
    encoding="utf-8"
)


# ============================================================
# STEP 3: PDF -> JSON
# ============================================================

print("Converting PDF to JSON...")

pymupdf4llm.use_layout(True)

json_data = pymupdf4llm.to_json(
    str(PDF_PATH)
)

if isinstance(json_data, str):
    json_data = json.loads(json_data)

with OUTPUT_JSON.open("w", encoding="utf-8") as json_file:
    json.dump(
        json_data,
        json_file,
        ensure_ascii=False,
        indent=2
    )


# ============================================================
# STEP 3: SHOW BASIC INFORMATION
# ============================================================

print()
print("=" * 60)
print("DONE")
print("=" * 60)

print(f"PDF     : {PDF_PATH}")
print(f"Markdown: {OUTPUT_MD}")
print(f"JSON    : {OUTPUT_JSON}")

print()
print("Markdown length:", len(md_text), "characters")

print()
print("First 3000 characters:")
print("-" * 60)

print(md_text[:3000])

print("-" * 60)