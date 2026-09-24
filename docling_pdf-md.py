from pathlib import Path
import json
import re

from docling.document_converter import DocumentConverter


# ============================================================
# 1. CONFIGURATION
# ============================================================

PDF_PATH = Path(
    "/home/preetham/CIGNA/Data/Cigna_Knee Replacement Arthroplasty.pdf"
)

OUTPUT_DIR = Path(
    "/home/preetham/CIGNA/Chunks"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


MARKDOWN_OUTPUT = (
    OUTPUT_DIR
    / "Cigna_Knee_Replacement_Arthroplasty.md"
)

JSON_OUTPUT = (
    OUTPUT_DIR
    / "Cigna_Knee_Replacement_Arthroplasty.json"
)


# ============================================================
# 2. HEADING CLEANING
# ============================================================

def clean_heading_text(text):
    """
    Clean formatting from a heading.

    Examples:

        **### Heading**
        ### Heading
        **Heading**

    become:

        Heading
    """

    text = text.strip()

    # Remove surrounding bold markers
    text = re.sub(
        r"^\*\*(.*?)\*\*$",
        r"\1",
        text
    ).strip()

    # Remove Markdown heading markers
    text = re.sub(
        r"^#{1,6}\s*",
        "",
        text
    ).strip()

    return text


# ============================================================
# 3. EXTRACT HEADING INFORMATION
# ============================================================

def extract_heading(line):
    """
    Detect Markdown headings produced by Docling.

    Handles:

        # Heading
        ## Heading
        ### Heading

    and also malformed versions such as:

        **### Heading**
        **## Heading**

    Returns:

        (heading_level, heading_text)

    or None if the line is not a heading.
    """

    stripped = line.strip()

    if not stripped:
        return None


    # --------------------------------------------------------
    # Case 1:
    #
    # **### Heading**
    # --------------------------------------------------------

    match = re.match(
        r"^\*\*\s*(#{1,6})\s*(.*?)\s*\*\*$",
        stripped
    )

    if match:

        level = len(match.group(1))

        text = match.group(2)

        text = clean_heading_text(text)

        return level, text


    # --------------------------------------------------------
    # Case 2:
    #
    # ### Heading
    # --------------------------------------------------------

    match = re.match(
        r"^(#{1,6})\s+(.+?)\s*$",
        stripped
    )

    if match:

        level = len(match.group(1))

        text = match.group(2)

        text = clean_heading_text(text)

        return level, text


    return None


# ============================================================
# 4. DETECT MAJOR POLICY / SECTION IDENTIFIERS
# ============================================================

def is_major_section(text):
    """
    Detect whether a heading looks like a major structured
    section.

    This is intentionally generic.

    Examples it can recognize:

        CMM-601.8: Title
        ABC-123: Title
        POLICY-100.2: Title
        XYZ_123: Title
        1. Introduction
        2. Eligibility
        10. Clinical Criteria

    It does NOT contain any document-specific names.
    """

    text = text.strip()


    # --------------------------------------------------------
    # Pattern 1
    #
    # PREFIX-NUMBER:
    #
    # Examples:
    #
    # CMM-601.8:
    # ABC-123:
    # POLICY-100.2:
    # XYZ-1.2.3:
    #
    # --------------------------------------------------------

    if re.match(
        r"^[A-Z][A-Z0-9_-]*-\d+(?:\.\d+)*\s*:",
        text,
        re.IGNORECASE
    ):
        return True


    # --------------------------------------------------------
    # Pattern 2
    #
    # Numeric major section:
    #
    # 1. Introduction
    # 2. Eligibility
    #
    # --------------------------------------------------------

    if re.match(
        r"^\d+\.\s+\S",
        text
    ):
        return True


    return False


# ============================================================
# 5. DETECT SUBSECTION NUMBERING
# ============================================================

def get_numbering_depth(text):
    """
    Detect numbered hierarchy.

    Examples:

        1. Introduction       -> depth 1
        1.1 Eligibility       -> depth 2
        1.1.1 Requirements    -> depth 3

    Returns None if no numbering is detected.
    """

    text = text.strip()


    # --------------------------------------------------------
    # 1.1
    # 1.1.1
    # 1.1.1.1
    # --------------------------------------------------------

    match = re.match(
        r"^(\d+(?:\.\d+)+)\.?\s+",
        text
    )

    if match:

        numbering = match.group(1)

        return numbering.count(".") + 1


    # --------------------------------------------------------
    # 1.
    # --------------------------------------------------------

    match = re.match(
        r"^\d+\.\s+",
        text
    )

    if match:

        return 1


    # --------------------------------------------------------
    # A.
    # A.1
    # A.1.1
    # --------------------------------------------------------

    match = re.match(
        r"^([A-Z](?:\.\d+)*)\.?\s+",
        text
    )

    if match:

        numbering = match.group(1)

        return numbering.count(".") + 1


    return None


# ============================================================
# 6. NORMALIZE MARKDOWN HEADINGS
# ============================================================

def normalize_headings(markdown):
    """
    Convert Docling Markdown into a cleaner hierarchy.

    Target structure:

        ## Document title

        ## Major policy section

        ### Subsection

        #### Deeper subsection

    Important:

    - No document-specific names are hard-coded.
    - Normal paragraphs remain paragraphs.
    - Bullet points remain bullet points.
    - Tables remain unchanged.
    - Malformed headings such as **### Heading** are fixed.
    """

    lines = markdown.splitlines()

    output = []

    first_heading_found = False

    major_section_found = False

    previous_original_level = None

    current_major_depth = None


    for line in lines:

        heading_info = extract_heading(line)


        # ====================================================
        # NORMAL CONTENT
        # ====================================================

        if heading_info is None:

            output.append(line)

            continue


        original_level, heading_text = heading_info


        # ----------------------------------------------------
        # Empty heading
        # ----------------------------------------------------

        if not heading_text:

            continue


        # ====================================================
        # FIRST HEADING
        # ====================================================

        if not first_heading_found:

            output.append(
                f"## {heading_text}"
            )

            first_heading_found = True

            previous_original_level = original_level

            continue


        # ====================================================
        # MAJOR STRUCTURED SECTION
        #
        # Example:
        #
        # CMM-601.8: ...
        #
        # becomes:
        #
        # ## CMM-601.8: ...
        #
        # This is generic and not tied to CMM specifically.
        # ====================================================

        if is_major_section(heading_text):

            output.append(
                f"## {heading_text}"
            )

            major_section_found = True

            current_major_depth = (
                get_numbering_depth(heading_text)
            )

            previous_original_level = 2

            continue


        # ====================================================
        # NUMBERED SUBSECTION
        #
        # Example:
        #
        # ## 2. Eligibility
        # ### 2.1 Requirements
        # #### 2.1.1 Exceptions
        # ====================================================

        numbering_depth = get_numbering_depth(
            heading_text
        )


        if numbering_depth is not None:

            if numbering_depth == 1:

                new_level = 3

            else:

                new_level = min(
                    2 + numbering_depth,
                    6
                )

            output.append(
                f"{'#' * new_level} {heading_text}"
            )

            previous_original_level = new_level

            continue


        # ====================================================
        # NON-NUMBERED SUBSECTION
        #
        # If we are currently inside a major policy section,
        # normal headings become ###.
        #
        # Example:
        #
        # ## CMM-601.8: ...
        #
        # ### Failed Cervical Disc Arthroplasty Implant
        #
        # ### Unremitting Neck Pain
        # ====================================================

        if major_section_found:

            # -----------------------------------------------
            # If Docling originally identified this as a
            # deeper heading, preserve that depth.
            #
            # Otherwise make it a subsection.
            # -----------------------------------------------

            if original_level >= 4:

                new_level = min(
                    original_level,
                    6
                )

            else:

                new_level = 3


            output.append(
                f"{'#' * new_level} {heading_text}"
            )

            previous_original_level = new_level

            continue


        # ====================================================
        # FALLBACK FOR DOCUMENTS WITHOUT STRUCTURED IDs
        # ====================================================

        if original_level <= 2:

            new_level = 3

        elif original_level == 3:

            new_level = 3

        else:

            new_level = min(
                original_level,
                6
            )


        output.append(
            f"{'#' * new_level} {heading_text}"
        )

        previous_original_level = new_level


    return "\n".join(output)


# ============================================================
# 7. DOCLING PDF CONVERSION
# ============================================================

print("=" * 60)
print("DOCLING PDF CONVERSION")
print("=" * 60)

print(
    f"Input PDF:\n{PDF_PATH}"
)

print()


converter = DocumentConverter()

result = converter.convert(
    str(PDF_PATH)
)

print("PDF converted successfully.")


# ============================================================
# 8. GET DOCLING DOCUMENT
# ============================================================

doc = result.document

print(
    "Docling document loaded."
)


# ============================================================
# 9. EXPORT MARKDOWN
# ============================================================

print()
print("=" * 60)
print("EXPORTING MARKDOWN")
print("=" * 60)

markdown = doc.export_to_markdown()

print(
    "Original Markdown generated."
)


# ============================================================
# 10. FIX HEADING HIERARCHY
# ============================================================

print(
    "Normalizing heading hierarchy..."
)

markdown = normalize_headings(
    markdown
)

print(
    "Heading hierarchy normalized."
)


# ============================================================
# 11. SAVE MARKDOWN
# ============================================================

markdown_path = MARKDOWN_OUTPUT

markdown_path.write_text(
    markdown,
    encoding="utf-8"
)

print()
print(
    f"Markdown saved to:\n{markdown_path}"
)


# ============================================================
# 12. EXPORT FULL DOCLING JSON
# ============================================================

print()
print("=" * 60)
print("EXPORTING DOCLING JSON")
print("=" * 60)

json_data = doc.model_dump(
    mode="json"
)


with open(
    JSON_OUTPUT,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        json_data,
        f,
        indent=2,
        ensure_ascii=False
    )


print(
    f"JSON saved to:\n{JSON_OUTPUT}"
)


# ============================================================
# 13. PRINT FINAL MARKDOWN
# ============================================================

print()
print("=" * 60)
print("FINAL MARKDOWN")
print("=" * 60)

print()

print(markdown)


# ============================================================
# 14. FINAL STATUS
# ============================================================

print()
print("=" * 60)
print("DONE")
print("=" * 60)

print()
print(
    f"Markdown:\n{markdown_path}"
)

print()
print(
    f"JSON:\n{JSON_OUTPUT}"
)