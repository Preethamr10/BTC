from pathlib import Path
import re
from collections import Counter

from docling.document_converter import DocumentConverter


# ============================================================
# CONFIGURATION
# ============================================================

PDF_PATH = Path(
    "/Users/preethamramachandra/Desktop/PA/PA/Data/Cigna_Knee Replacement Arthroplasty.pdf"
)

OUTPUT_DIR = Path(
    "/Users/preethamramachandra/Desktop/PA/PA/ooouuuttt"
)

OUTPUT_FILE = OUTPUT_DIR / "structured_document.md"


# ============================================================
# BASIC TEXT CLEANING
# ============================================================

def normalize_text(text: str) -> str:
    """
    Normalize whitespace while preserving the actual wording.
    """

    if not text:
        return ""

    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")

    # Normalize repeated spaces.
    text = re.sub(r"[ \t]+", " ", text)

    # Remove spaces around line boundaries.
    text = re.sub(r" *\n *", "\n", text)

    return text.strip()


def is_page_number(text: str) -> bool:
    """
    Detect simple page-number-only lines.
    """

    text = text.strip()

    if not text:
        return False

    patterns = [
        r"^\d+$",
        r"^page\s+\d+$",
        r"^\d+\s+of\s+\d+$",
        r"^page\s+\d+\s+of\s+\d+$",
    ]

    return any(re.match(pattern, text, re.IGNORECASE) for pattern in patterns)


# ============================================================
# HEADER / FOOTER DETECTION
# ============================================================

def find_repeated_lines(lines, minimum_occurrences=3):
    """
    Find lines repeated multiple times.

    These are candidates for PDF headers/footers.

    We deliberately don't remove them automatically unless
    they look like obvious repeated page furniture.
    """

    normalized = []

    for line in lines:
        line = normalize_text(line)

        if line:
            normalized.append(line)

    counter = Counter(normalized)

    repeated = {
        line
        for line, count in counter.items()
        if count >= minimum_occurrences
    }

    return repeated


def looks_like_page_furniture(text: str) -> bool:
    """
    Detect obvious page-number/header/footer artifacts.

    This is intentionally conservative.
    """

    text = text.strip()

    if not text:
        return True

    if is_page_number(text):
        return True

    return False


# ============================================================
# HEADING UTILITIES
# ============================================================

def clean_heading(text: str) -> str:
    """
    Clean heading text without changing its meaning.
    """

    text = normalize_text(text)

    # Remove accidental trailing heading punctuation.
    text = text.rstrip()

    return text


def heading_level_from_element(item, default_level=2):
    """
    Get heading level from a Docling item.

    Docling versions can expose heading information slightly
    differently, so this function is deliberately defensive.
    """

    level = None

    # Try common attributes.
    for attribute in [
        "level",
        "heading_level",
        "depth",
    ]:
        if hasattr(item, attribute):
            value = getattr(item, attribute)

            if isinstance(value, int):
                level = value
                break

    if level is None:
        return default_level

    # Markdown heading levels should remain sensible.
    return max(1, min(level, 6))


# ============================================================
# LIST HANDLING
# ============================================================

def render_list_item(text: str, indent_level=0, ordered=False, number=None):
    """
    Render a single Markdown list item.
    """

    indent = "    " * indent_level

    if ordered:
        prefix = f"{number}. "
    else:
        prefix = "- "

    return f"{indent}{prefix}{text}"


# ============================================================
# TABLE HANDLING
# ============================================================

def escape_table_cell(value: str) -> str:
    """
    Make text safe inside a Markdown table.
    """

    value = normalize_text(value)

    # Escape Markdown table separator.
    value = value.replace("|", "\\|")

    # Convert line breaks to <br>.
    value = value.replace("\n", "<br>")

    return value


def table_to_markdown(table):
    """
    Convert a Docling table object to Markdown.

    Uses Docling's table dataframe representation when available.
    """

    try:
        dataframe = table.export_to_dataframe()
    except Exception:
        dataframe = None

    if dataframe is None:
        return None

    if dataframe.empty:
        return None

    headers = [
        escape_table_cell(str(column))
        for column in dataframe.columns
    ]

    output = []

    output.append(
        "| " + " | ".join(headers) + " |"
    )

    output.append(
        "| " + " | ".join("---" for _ in headers) + " |"
    )

    for _, row in dataframe.iterrows():

        values = []

        for value in row:
            if value is None:
                value = ""

            values.append(
                escape_table_cell(str(value))
            )

        output.append(
            "| " + " | ".join(values) + " |"
        )

    return "\n".join(output)


# ============================================================
# TEXT BLOCK HANDLING
# ============================================================

def merge_broken_lines(text: str) -> str:
    """
    Merge lines that were broken by PDF extraction.

    We only merge lines when there is strong evidence that
    the break is an extraction artifact.

    Existing paragraph boundaries are otherwise preserved.
    """

    if not text:
        return ""

    lines = text.splitlines()

    if len(lines) <= 1:
        return text.strip()

    result = []

    current = ""

    for line in lines:

        line = line.strip()

        if not line:
            if current:
                result.append(current)
                current = ""

            result.append("")

            continue

        if not current:
            current = line
            continue

        # If previous line ends with punctuation, keep a boundary.
        if re.search(r"[.!?:;)]$", current):
            result.append(current)
            current = line
            continue

        # If current line begins with a bullet/number, keep separate.
        if re.match(
            r"^([-*•]|\d+[.)])\s+",
            line
        ):
            result.append(current)
            current = line
            continue

        # Otherwise merge the extraction line.
        current += " " + line

    if current:
        result.append(current)

    return "\n".join(result).strip()


# ============================================================
# INLINE MARKDOWN
# ============================================================

def preserve_basic_emphasis(text: str) -> str:
    """
    Preserve basic emphasis where possible.

    This function intentionally does not try to invent
    emphasis that wasn't represented by the parser.
    """

    text = text.replace("\u2022", "•")

    return text


# ============================================================
# ELEMENT TYPE DETECTION
# ============================================================

def get_item_type(item):
    """
    Determine the type of a Docling document item.

    Different Docling versions may expose slightly different
    class names, so detection is defensive.
    """

    class_name = item.__class__.__name__.lower()

    if "table" in class_name:
        return "table"

    if "list" in class_name:
        return "list"

    if "title" in class_name:
        return "title"

    if "heading" in class_name:
        return "heading"

    if "text" in class_name:
        return "text"

    return "text"


# ============================================================
# LIST TEXT DETECTION
# ============================================================

def detect_list_item(text):
    """
    Detect whether a line is already formatted like a list item.

    Returns:

        (is_list, ordered, number, content)
    """

    text = text.strip()

    # Bullet
    match = re.match(
        r"^[-*•]\s+(.*)$",
        text
    )

    if match:
        return True, False, None, match.group(1)

    # Numbered
    match = re.match(
        r"^(\d+)[.)]\s+(.*)$",
        text
    )

    if match:
        return True, True, int(match.group(1)), match.group(2)

    return False, False, None, text


# ============================================================
# MARKDOWN RENDERER
# ============================================================

class MarkdownRenderer:

    def __init__(self):
        self.output = []

    def add(self, text=""):
        self.output.append(text)

    def blank_line(self):
        if self.output and self.output[-1] != "":
            self.output.append("")

    def heading(self, text, level):
        text = clean_heading(text)

        if not text:
            return

        self.blank_line()

        self.add(
            f"{'#' * level} {text}"
        )

        self.blank_line()

    def paragraph(self, text):

        text = normalize_text(text)

        if not text:
            return

        text = merge_broken_lines(text)

        text = preserve_basic_emphasis(text)

        self.blank_line()

        self.add(text)

        self.blank_line()

    def table(self, markdown_table):

        if not markdown_table:
            return

        self.blank_line()

        self.add(markdown_table)

        self.blank_line()

    def finish(self):

        # Remove excessive blank lines.
        result = "\n".join(self.output)

        result = re.sub(
            r"\n{3,}",
            "\n\n",
            result
        )

        return result.strip() + "\n"


# ============================================================
# DOCX / DOCLING ITEM EXTRACTION
# ============================================================

def extract_document_items(document):
    """
    Extract document items in reading order.

    Docling provides document.iterate_items() for walking
    through structured document content.
    """

    try:
        items = list(
            document.iterate_items()
        )

        return items

    except Exception as exc:

        raise RuntimeError(
            "Unable to iterate through Docling document items. "
            f"Details: {exc}"
        )


# ============================================================
# GENERIC STRUCTURE RECONSTRUCTION
# ============================================================

def render_document(document):

    renderer = MarkdownRenderer()

    items = extract_document_items(document)

    print(f"Found {len(items)} document items")

    for index, item in enumerate(items, start=1):

        item_type = get_item_type(item)

        # ----------------------------------------------------
        # TABLE
        # ----------------------------------------------------

        if item_type == "table":

            markdown_table = table_to_markdown(item)

            if markdown_table:
                renderer.table(markdown_table)

            continue

        # ----------------------------------------------------
        # TEXT / TITLE / HEADING
        # ----------------------------------------------------

        text = ""

        if hasattr(item, "text"):
            text = item.text

        if not text:
            continue

        text = normalize_text(text)

        if not text:
            continue

        # Skip obvious page numbers.
        if looks_like_page_furniture(text):
            continue

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        if item_type == "title":

            renderer.heading(
                text,
                1
            )

            continue

        # ----------------------------------------------------
        # HEADING
        # ----------------------------------------------------

        if item_type == "heading":

            level = heading_level_from_element(
                item,
                default_level=2
            )

            renderer.heading(
                text,
                level
            )

            continue

        # ----------------------------------------------------
        # LIST
        # ----------------------------------------------------

        if item_type == "list":

            is_list, ordered, number, content = (
                detect_list_item(text)
            )

            if is_list:

                renderer.blank_line()

                renderer.add(
                    render_list_item(
                        content,
                        indent_level=0,
                        ordered=ordered,
                        number=number
                    )
                )

                continue

            renderer.paragraph(text)

            continue

        # ----------------------------------------------------
        # NORMAL TEXT
        # ----------------------------------------------------

        renderer.paragraph(text)

    return renderer.finish()


# ============================================================
# VALIDATION
# ============================================================

def validate_markdown(markdown_text: str):

    lines = markdown_text.splitlines()

    stats = {
        "total_lines": len(lines),
        "headings": 0,
        "tables": 0,
        "bullet_lines": 0,
        "numbered_lines": 0,
        "paragraph_lines": 0,
    }

    for line in lines:

        stripped = line.strip()

        if re.match(r"^#{1,6}\s+", stripped):
            stats["headings"] += 1

        elif stripped.startswith("|"):
            stats["tables"] += 1

        elif re.match(r"^[-*]\s+", stripped):
            stats["bullet_lines"] += 1

        elif re.match(r"^\d+\.\s+", stripped):
            stats["numbered_lines"] += 1

        elif stripped:
            stats["paragraph_lines"] += 1

    return stats


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("GENERIC PDF → STRUCTURED MARKDOWN")
    print("=" * 70)

    print()
    print(f"Input PDF : {PDF_PATH}")
    print(f"Output    : {OUTPUT_FILE}")
    print()

    if not PDF_PATH.exists():

        raise FileNotFoundError(
            f"PDF file does not exist:\n{PDF_PATH}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # STEP 1: CONVERT PDF
    # --------------------------------------------------------

    print("1. Converting PDF with Docling...")

    converter = DocumentConverter()

    result = converter.convert(
        str(PDF_PATH)
    )

    document = result.document

    print("   PDF conversion completed.")

    # --------------------------------------------------------
    # STEP 2: RENDER STRUCTURED MARKDOWN
    # --------------------------------------------------------

    print()
    print("2. Building structured Markdown...")

    markdown = render_document(
        document
    )

    # --------------------------------------------------------
    # STEP 3: WRITE OUTPUT
    # --------------------------------------------------------

    print()
    print("3. Writing Markdown...")

    OUTPUT_FILE.write_text(
        markdown,
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # STEP 4: VALIDATE
    # --------------------------------------------------------

    print()
    print("4. Validating output...")

    stats = validate_markdown(
        markdown
    )

    print()
    print("Validation:")
    print("-" * 40)

    for key, value in stats.items():

        print(
            f"{key:20}: {value}"
        )

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)
    print()
    print(
        f"Markdown saved to:\n{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()