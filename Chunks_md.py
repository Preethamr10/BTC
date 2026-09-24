from pathlib import Path
import json
import re

from docling.document_converter import DocumentConverter
from hierarchical.postprocessor import ResultPostprocessor


# ============================================================
# PATHS
# ============================================================

PDF_FILE = Path(
    "/home/preetham/CIGNA/Data/Cigna_ACDF.pdf"
)
MD_FILE = Path(
    "/home/preetham/BC_NEW/data/Stage_2_output/11_BrightCare_Comprehensive_Prior_Authorization_Manual.md"
)

OUTPUT_FILE = Path(
    "/home/preetham/BC_NEW/data/Stage_2_output/Chunks/11_BrightCare_Comprehensive_Prior_Authorization_Manual_chunks.json"
)

MAX_CHARS = 5000


# ============================================================
# DOCUMENT METADATA
# ============================================================

DOCUMENT_NAME = "BrightCare Comprehensive Benefits Policy - Silver 250"
DOCUMENT_TYPE = "Benefits Policy"
PLAN = "Silver 250"
YEAR = 2026
SOURCE_FILE = PDF_FILE.name


# ============================================================
# HEADING PATTERN
# ============================================================

HEADING_PATTERN = re.compile(
    r"^(#{1,6})\s+(.+?)\s*$"
)


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = text.lower()

    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"`(.*?)`", r"\1", text)

    text = re.sub(r"\|", " ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# DETECT CONTENT TYPE
# ============================================================

def detect_content_type(content):

    lines = content.splitlines()

    has_table = any(
        "|" in line
        for line in lines
    )

    has_text = any(
        line.strip() and "|" not in line
        for line in lines
    )

    if has_table and has_text:
        return "mixed"

    if has_table:
        return "table"

    return "paragraph"


# ============================================================
# LOAD PDF WITH DOCLING
# FOR PAGE INFORMATION
# ============================================================

print("=" * 60)
print("LOADING PDF FOR PAGE INFORMATION")
print("=" * 60)

converter = DocumentConverter()

result = converter.convert(
    str(PDF_FILE)
)

original_doc = result.document

postprocessor = ResultPostprocessor(
    result,
    source=str(PDF_FILE)
)

postprocessor.process()

print("PDF loaded.")
print("Page information collected.")


# ============================================================
# BUILD PAGE TEXT MAP
# ============================================================

page_items = []

for item, level in original_doc.iterate_items():

    page_number = None

    if item.prov:

        for prov in item.prov:

            if getattr(
                prov,
                "page_no",
                None
            ):
                page_number = prov.page_no
                break

    if page_number is None:
        continue

    text = ""

    if hasattr(item, "text") and item.text:
        text = item.text

    elif hasattr(
        item,
        "export_to_markdown"
    ):
        try:
            text = item.export_to_markdown()
        except Exception:
            text = ""

    if text:

        page_items.append(
            {
                "page_number": page_number,
                "text": normalize_text(text),
            }
        )


print(
    f"Collected {len(page_items)} "
    "items with page information."
)


# ============================================================
# READ MARKDOWN
# ============================================================

if not MD_FILE.exists():

    raise FileNotFoundError(
        f"Markdown file not found:\n{MD_FILE}"
    )

markdown = MD_FILE.read_text(
    encoding="utf-8"
)

lines = markdown.splitlines()


# ============================================================
# FIND PAGE NUMBERS
# ============================================================

def get_page_numbers(content):

    normalized_chunk = normalize_text(
        content
    )

    if not normalized_chunk:
        return []

    pages = set()

    for item in page_items:

        item_text = item["text"]

        if not item_text:
            continue

        if (
            len(item_text) >= 20
            and item_text in normalized_chunk
        ):
            pages.add(
                item["page_number"]
            )

        elif len(normalized_chunk) >= 40:

            sample = normalized_chunk[:100]

            if (
                len(sample) >= 30
                and sample in item_text
            ):
                pages.add(
                    item["page_number"]
                )

    return sorted(pages)


# ============================================================
# SPLIT LARGE CONTENT
# ============================================================

def split_large_content(content):

    if len(content) <= MAX_CHARS:
        return [content]

    lines = content.splitlines()

    chunks = []
    current = []

    for line in lines:

        proposed = "\n".join(
            current + [line]
        )

        if len(proposed) <= MAX_CHARS:

            current.append(line)

        else:

            if current:
                chunks.append(
                    "\n".join(current).strip()
                )

            current = [line]

    if current:
        chunks.append(
            "\n".join(current).strip()
        )

    return [
        chunk
        for chunk in chunks
        if chunk.strip()
    ]


# ============================================================
# CHUNK MARKDOWN
# ============================================================

chunks = []

section_stack = []

current_heading = None
current_heading_level = None
current_content = []


def save_current_chunk():

    global current_heading
    global current_heading_level
    global current_content

    content = "\n".join(
        current_content
    ).strip()

    if not content and not current_heading:
        return

    if current_heading:

        chunk_content = (
            f"{current_heading}\n\n"
            f"{content}"
        ).strip()

    else:

        chunk_content = content

    if not chunk_content:
        return

    content_parts = split_large_content(
        chunk_content
    )

    for part in content_parts:

        pages = get_page_numbers(
            part
        )

        content_type = detect_content_type(
            part
        )

        section = (
            section_stack[-1]
            if section_stack
            else None
        )

        chunk = {

            "chunk_id": (
                f"C{len(chunks) + 1:04d}"
            ),

            "section_path":
                section_stack.copy(),

            "heading":
                current_heading,

            "heading_level":
                current_heading_level,

            "content":
                part,

            "page_number":
                pages[0]
                if pages
                else None,

            "page_numbers":
                pages,

            "metadata": {

                "document_name":
                    DOCUMENT_NAME,

                "document_type":
                    DOCUMENT_TYPE,

                "plan":
                    PLAN,

                "year":
                    YEAR,

                "source_file":
                    SOURCE_FILE,

                "section":
                    section,

                "content_type":
                    content_type
            }
        }

        chunks.append(chunk)

    current_heading = None
    current_heading_level = None
    current_content = []


# ============================================================
# PROCESS MARKDOWN
# ============================================================

for line in lines:

    heading_match = HEADING_PATTERN.match(
        line
    )

    if heading_match:

        save_current_chunk()

        hashes = heading_match.group(1)

        heading_text = (
            heading_match
            .group(2)
            .strip()
        )

        level = len(hashes)

        while len(section_stack) >= level:
            section_stack.pop()

        section_stack.append(
            heading_text
        )

        current_heading = line

        current_heading_level = level

    else:

        current_content.append(line)


# ============================================================
# SAVE FINAL CHUNK
# ============================================================

save_current_chunk()


# ============================================================
# SAVE JSON
# ============================================================

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        chunks,
        f,
        indent=2,
        ensure_ascii=False
    )


# ============================================================
# SUMMARY
# ============================================================

print("\n" + "=" * 60)
print("CHUNKING COMPLETE")
print("=" * 60)

print(
    f"Markdown input : {MD_FILE}"
)

print(
    f"Chunks created : {len(chunks)}"
)

print(
    f"Output file    : {OUTPUT_FILE}"
)

print("\nChunk information:")

for chunk in chunks:

    print(
        f"{chunk['chunk_id']} | "
        f"Page: {chunk['page_numbers']} | "
        f"Type: {chunk['metadata']['content_type']} | "
        f"Section: {chunk['metadata']['section']}"
    )

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)