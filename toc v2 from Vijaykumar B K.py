"""
Extract a Table of Contents (TOC) from a "hierarchical" document-parser JSON
(the Docling-style export with top-level keys: document, sections, blocks).

For each heading block, this script collects all the non-heading content
blocks that fall underneath it (down to, but not including, the next
heading at the same or a shallower level) and keeps that mapping alongside
a nested TOC tree.

Two kinds of section IDs are produced:

  - docling_section_id: Docling's own section_id, straight from the input
    JSON's "sections" list (e.g. "s0006"). This is COARSE -- it only
    distinguishes the document's top-level chapters. Every subheading
    nested under a chapter shares its parent chapter's ID.

  - toc_id: generated fresh by this script, purely from the tree
    position (e.g. "S6", "S6.1", "S6.1.2"). This is FINE-GRAINED -- every
    single heading at every depth gets its own distinct ID. Use this as
    the join key when scoping/routing retrieval to a specific subsection.

Usage:
    Just edit INPUT_JSON_PATH / OUTPUT_JSON_PATH below and run:
        python toc.py
    (You can still optionally pass paths on the command line instead,
    if you ever want to: python toc.py <input.json> [output.json])

Output:
    A JSON file with:
      - "flat_toc":  a flat list of headings in document order, each with
                     its own direct content blocks (only text between it
                     and its next child/sibling heading), plus toc_id and
                     docling_section_id.
      - "toc_tree":  the same headings nested into a tree by heading_level,
                     each node's "content_all" containing ALL blocks that
                     live under it (including its subsections' blocks).
      - "block_id_to_toc_id": {block_id: toc_id} lookup table.
      - "heading_path_to_toc_id": {heading breadcrumb string: toc_id}
        lookup table -- use this when your chunks only carry a heading
        breadcrumb (e.g. "Section A > Section B") and no block_id.
"""

import json
import sys
from copy import deepcopy

# ---------------------------------------------------------------------------
# EDIT THESE TWO PATHS AND JUST RUN: python toc.py
# ---------------------------------------------------------------------------
INPUT_JSON_PATH = "/home/vijaykumar/Desktop/project2/hierarchical-processing/md/Cigna_Lumbar_Fusion_hierarchical.json"
OUTPUT_JSON_PATH = "/home/vijaykumar/Desktop/project2/hierarchical-processing/md/Lumbar_toc_output.json"
OUTPUT_TREE_TXT_PATH = "/home/vijaykumar/Desktop/project2/hierarchical-processing/md/toc_tree.txt"

# The text-tree RENDER only (the JSON always keeps the full, untouched
# hierarchy) -- tune these to cut down on noise:
FLATTEN_SECTION_KEYWORDS = ["reference"]  # any heading whose title contains
                                            # one of these (case-insensitive)
                                            # has its whole subtree flattened
                                            # to one level -- no more nesting.
                                            # Set to [] to disable.
MAX_TITLE_CHARS = 90     # truncate long heading titles (e.g. full citations)
                          # in the text tree. Set to None to disable.
SHOW_PAGE = True
SHOW_COUNTS = True
SHOW_TOC_ID = True       # show the generated [S6.1.2]-style id in the tree
# ---------------------------------------------------------------------------


def load_data(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_flat_toc(blocks):
    """
    Walk blocks in reading order. Every 'heading' block starts a new TOC
    node. Every subsequent non-heading block is attached to the *current*
    (most recent) heading as direct content, until the next heading block
    appears.

    Returns a flat list of dicts:
        {
          "block_id", "heading_level", "title", "page",
          "heading_path", "docling_section_id", "section_title",
          "content": [ {block_id, type, page, text}, ... ]  # direct children only
        }
    """
    blocks_sorted = sorted(blocks, key=lambda b: b.get("reading_order", 0))

    flat_toc = []
    current_node = None

    for b in blocks_sorted:
        if b.get("type") == "heading":
            node = {
                "block_id": b["block_id"],
                "heading_level": b.get("heading_level"),
                "title": b.get("text", "").strip(),
                "page": b.get("page"),
                "heading_path": b.get("heading_path", []),
                # Docling's own section_id -- COARSE, only distinguishes
                # top-level chapters. See module docstring.
                "docling_section_id": b.get("section_id"),
                "section_title": b.get("section_title"),
                "content": [],  # direct (non-heading) content only
            }
            flat_toc.append(node)
            current_node = node
        else:
            # Content block: attach to whichever heading currently "owns" it.
            if current_node is not None:
                current_node["content"].append(
                    {
                        "block_id": b.get("block_id"),
                        "type": b.get("type"),
                        "page": b.get("page"),
                        "text": b.get("text", ""),
                    }
                )
            # If there's content before the first heading, it's simply
            # dropped from the TOC mapping (front-matter with no heading).

    return flat_toc


def build_toc_tree(flat_toc):
    """
    Turn the flat, level-tagged TOC into a nested tree using heading_level
    as depth. Each node additionally gets "content_all": the union of its
    own direct content plus all content belonging to its descendants
    (i.e. "everything under this header").

    Returns a list of root nodes (the top-level headings).
    """
    tree_nodes = []
    # stack holds (level, node) pairs representing the current open path
    stack = []

    for flat_node in flat_toc:
        node = deepcopy(flat_node)
        node["children"] = []
        node["content_all"] = list(node["content"])  # start with own content

        level = node["heading_level"] if node["heading_level"] is not None else 1

        # Pop stack until we find a parent with a smaller level
        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            parent = stack[-1][1]
            parent["children"].append(node)
        else:
            tree_nodes.append(node)

        stack.append((level, node))

    # Now propagate content_all up: every node's content_all should also
    # include all descendants' content, in document order.
    def collect_all_content(node):
        combined = list(node["content"])
        for child in node["children"]:
            combined.extend(collect_all_content(child))
        node["content_all"] = combined
        return combined

    for root in tree_nodes:
        collect_all_content(root)

    return tree_nodes


def prune_matching_subtrees(tree_nodes, keywords):
    """
    For any node whose title contains one of `keywords` (case-insensitive
    substring match), remove its entire subtree -- the heading itself
    still appears in the TOC, but with nothing nested underneath it.

    This only touches matching branches (e.g. "References (CMM-601)");
    every other branch keeps its true, full hierarchy untouched.

    Mutates and returns tree_nodes.
    """
    if not keywords:
        return tree_nodes

    keywords_lower = [k.lower() for k in keywords]

    def _matches(node):
        title_lower = node["title"].lower()
        return any(kw in title_lower for kw in keywords_lower)

    def _walk(nodes):
        for node in nodes:
            if _matches(node):
                node["children"] = []
                # content_all is left as-is (still reflects everything
                # that was under this heading) -- drop the next line if
                # you'd rather it only show the heading's own content:
                # node["content_all"] = list(node["content"])
            else:
                _walk(node["children"])

    _walk(tree_nodes)
    return tree_nodes


def assign_toc_ids(tree_nodes):
    """
    Assign a stable, human-readable flat ID to every heading node
    based on its order in the document (S0, S1, S2, etc.).

    Mutates tree_nodes in place, adding a "toc_id" key to every node.
    Also returns a flat dict {block_id: toc_id} so you can look up any
    node's ID by its block_id.
    """
    block_id_to_toc_id = {}
    counter = [0]

    def _walk(nodes):
        for node in nodes:
            toc_id = f"S{counter[0]}"
            counter[0] += 1
            node["toc_id"] = toc_id
            block_id_to_toc_id[node["block_id"]] = toc_id
            _walk(node["children"])

    _walk(tree_nodes)
    return block_id_to_toc_id


def build_heading_path_lookup(flat_toc):
    """
    Build {heading_path_string: toc_id}, where heading_path_string is the
    ancestor-title breadcrumb joined with " > " -- the same format a
    Markdown-based chunker's heading-context builder typically produces
    for each chunk's "section" field. Use this as the join key when your
    chunks/embeddings only carry a heading breadcrumb and no block_id.

    Must be called after assign_toc_ids() has stamped "toc_id" onto each
    flat_toc node.
    """
    lookup = {}
    for node in flat_toc:
        path_str = " > ".join(node.get("heading_path") or [])
        if path_str:
            lookup[path_str] = node["toc_id"]
    return lookup


def summarize_tree(tree_nodes, indent=0):
    """Pretty-print the TOC hierarchy with content block counts."""
    lines = []
    for node in tree_nodes:
        prefix = "  " * indent + ("- " if indent else "")
        lines.append(
            f"{prefix}[L{node['heading_level']}] {node['title']} "
            f"(p.{node['page']}, {node['block_id']}, "
            f"{len(node['content'])} direct / {len(node['content_all'])} total blocks)"
        )
        lines.extend(summarize_tree(node["children"], indent + 1))
    return lines


def render_text_tree(
    tree_nodes,
    show_counts=True,
    show_page=True,
    show_toc_id=True,
    max_title_chars=None,
):
    """
    Render the TOC tree as a classic ASCII tree, like the Unix `tree`
    command:

        Document Title
        ├── [S1] CMM-601.1: General Guidelines (p.3)
        │   ├── [S1.1] Application of Guideline (p.4)
        │   └── [S1.2] General Guidelines (p.4)
        │       └── [S1.2.1] Health Equity Considerations (p.5)
        └── [S2] CMM-601.2: Osteotomy (p.6)
            └── [S2.1] Anterior Osteotomy or Vertebral Column Resection (p.7)

    - max_title_chars: long titles (e.g. full citation text used as a
      heading) get truncated with "..." for readability. None = no cap.

    Returns a single string (join of all lines).
    """
    lines = []

    def _fmt_title(title):
        if max_title_chars is not None and len(title) > max_title_chars:
            return title[: max_title_chars - 3].rstrip() + "..."
        return title

    def _walk(nodes, prefix):
        for i, node in enumerate(nodes):
            is_last = i == len(nodes) - 1
            connector = "└── " if is_last else "├── "

            label = _fmt_title(node["title"])
            if show_toc_id and node.get("toc_id"):
                label = f"{node['toc_id']} | {label}"

            lines.append(prefix + connector + label)

            child_prefix = prefix + ("    " if is_last else "│   ")
            _walk(node["children"], child_prefix)

    _walk(tree_nodes, "")
    return "\n".join(lines)


def fix_cigna_hierarchy(flat_toc):
    """
    Applies domain-specific rules to fix the hierarchy for Cigna policies
    where Docling fails to infer the correct heading levels.
    """
    for node in flat_toc:
        title = node["title"].strip()
        title_lower = title.lower()
        
        # Level 1
        if "cigna medical coverage" in title_lower or title.startswith("CMM-") or title_lower in ["arthroplasty", "cigna commercial"]:
            node["heading_level"] = 1
            
        # Level 2
        elif title_lower in [
            "effective date: august 04, 2026", "instructions for use", "table of contents",
            "definitions", "general guidelines", "partial knee replacement",
            "total knee replacement", "revision of knee replacement",
            "arthroscopic or open abrasion arthroplasty procedures of the patella (without prosthesis), femoral condyles, or tibial plateau",
            "codes (cmm-311)", "references (cmm-311)", "codes (cmm-609)", "references (cmm-609)",
            "codes (cmm-601)", "references (cmm-601)"
        ]:
            node["heading_level"] = 2
            
        # Level 3
        elif "indications" in title_lower or "guideline page" in title_lower or "focal articular resurfacing" == title_lower or "kellgren-lawrence" in title_lower or "knee arthroplasty" == title_lower or "knee replacement" == title_lower or "non-indications" in title_lower or "nonindications" in title_lower or "application of guideline" in title_lower or "health equity considerations" in title_lower or title_lower.startswith("general guidelines."):
            node["heading_level"] = 3
            
        # Level 4
        elif "cmm.jt.df" in title_lower or "not medically necessary" in title_lower or "experimental" in title_lower or "fracture of" in title_lower or "osteoarthritis" in title_lower or "unicompartmental" in title_lower:
            node["heading_level"] = 4
            
        # Level 5
        elif "outerbridge classification" in title_lower or "non-surgical management" in title_lower:
            node["heading_level"] = 5
            
        # Special case for the second "Definitions" or "General Guidelines"
        if title_lower == "definitions" and node.get("page", 0) > 3:
            node["heading_level"] = 3
        if title_lower == "general guidelines" and node.get("page", 0) > 7:
            node["heading_level"] = 3


def main():
    # Command-line args (if given) override the hardcoded paths above.
    input_path = sys.argv[1] if len(sys.argv) > 1 else INPUT_JSON_PATH
    output_path = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_JSON_PATH
    tree_txt_path = sys.argv[3] if len(sys.argv) > 3 else OUTPUT_TREE_TXT_PATH

    data = load_data(input_path)
    blocks = data.get("blocks", [])

    flat_toc = build_flat_toc(blocks)
    fix_cigna_hierarchy(flat_toc)
    toc_tree = build_toc_tree(flat_toc)
    prune_matching_subtrees(toc_tree, FLATTEN_SECTION_KEYWORDS)
    block_id_to_toc_id = assign_toc_ids(toc_tree)

    # Stamp the same toc_id onto the flat list too, keyed by block_id,
    # so flat_toc and toc_tree agree on every node's ID.
    for node in flat_toc:
        node["toc_id"] = block_id_to_toc_id.get(node["block_id"])

    heading_path_to_toc_id = build_heading_path_lookup(flat_toc)

    output = {
        "document_source": data.get("document", {}).get("source"),
        "total_pages": data.get("document", {}).get("total_pages"),
        "flat_toc": flat_toc,
        "toc_tree": toc_tree,
        "block_id_to_toc_id": block_id_to_toc_id,
        "heading_path_to_toc_id": heading_path_to_toc_id,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    text_tree = render_text_tree(
        toc_tree,
        show_counts=SHOW_COUNTS,
        show_page=SHOW_PAGE,
        show_toc_id=SHOW_TOC_ID,
        max_title_chars=MAX_TITLE_CHARS,
    )
    doc_title = data.get("document", {}).get("source", "Document")
    with open(tree_txt_path, "w", encoding="utf-8") as f:
        f.write(f"{doc_title}\n")
        f.write(text_tree)
        f.write("\n")

    print(f"Extracted {len(flat_toc)} headings.")
    print(f"Saved TOC + mapping (JSON) -> {output_path}")
    print(f"Saved TOC text tree        -> {tree_txt_path}\n")
    print("Tree preview:")
    print(doc_title)
    print(text_tree)


if __name__ == "__main__":
    main()