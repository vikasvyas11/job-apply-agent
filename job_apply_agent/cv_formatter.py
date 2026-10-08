"""Turns the LLM's markdown-ish CV text into real Google Docs formatting:
a large centered name, a small centered contact line with working hyperlinks,
bold compact section headings, bold job/education titles, and bullet lines as
actual Docs bullet lists — matching the hand-made reference CV format rather
than dumping flat literal text. Typography and spacing are all set explicitly
(not via Google's default Heading styles) so the whole thing stays compact
enough to fit a two-page CV.

Depends on llm.py's CV prompt enforcing a fixed convention: entries are
"**Title** | Organisation, Location | Dates" (bold wraps only the title),
bullets start with "* ", section headings are plain ALL CAPS lines.
"""
import re
from dataclasses import dataclass, field

_SECTION_HEADING_RE = re.compile(r"^[A-Z0-9][A-Z0-9 &,./'-]*$")
_ENTRY_RE = re.compile(r"^\*\*(.+?)\*\*\s*(.*)$")
_BULLET_RE = re.compile(r"^[*-]\s+(.*)$")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_ESCAPE_RE = re.compile(r"\\([-+#_.!*])")


def _unescape_md(text: str) -> str:
    """Source CVs sometimes escape punctuation for markdown ("\\-", "\\+")
    the way resume-format.md does; strip that escaping so it doesn't show up
    as a literal backslash in the doc."""
    return _MD_ESCAPE_RE.sub(r"\1", text)


@dataclass
class LineSpec:
    text: str
    kind: str  # "name" | "contact" | "heading" | "entry" | "bullet" | "normal" | "blank"
    bold_len: int = 0
    links: list[tuple[int, int, str]] = field(default_factory=list)  # (start, end, url) local to this line


def _strip_md_links(text: str) -> tuple[str, list[tuple[int, int, str]]]:
    """Replaces "[label](url)" with just "label", returning the plain text and
    the (start, end, url) ranges of each label within that plain text."""
    out = []
    links = []
    pos = 0
    for m in _MD_LINK_RE.finditer(text):
        out.append(text[pos : m.start()])
        label_start = sum(len(s) for s in out)
        out.append(m.group(1))
        links.append((label_start, label_start + len(m.group(1)), m.group(2)))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out), links


def _is_section_heading(candidate: str) -> bool:
    if not candidate or len(candidate) > 60:
        return False
    if not any(c.isalpha() for c in candidate):
        return False
    if not _SECTION_HEADING_RE.match(candidate):
        return False
    return candidate == candidate.upper()


def parse_cv(raw_text: str) -> list[LineSpec]:
    specs: list[LineSpec] = []
    seen_name = False
    seen_contact = False

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            specs.append(LineSpec(text="", kind="blank"))
            continue

        if not seen_name:
            text, links = _strip_md_links(_unescape_md(line.replace("**", "").lstrip("#").strip()))
            specs.append(LineSpec(text=text, kind="name", links=links))
            seen_name = True
            continue
        if not seen_contact:
            text, links = _strip_md_links(_unescape_md(line.replace("**", "").strip()))
            specs.append(LineSpec(text=text, kind="contact", links=links))
            seen_contact = True
            continue

        heading_candidate = line.lstrip("#").strip().replace("**", "").strip()
        entry_match = _ENTRY_RE.match(line)
        bullet_match = _BULLET_RE.match(line)

        if _is_section_heading(heading_candidate):
            specs.append(LineSpec(text=_unescape_md(heading_candidate), kind="heading"))
        elif entry_match and "|" in entry_match.group(2):
            bold_part = _unescape_md(entry_match.group(1).strip().rstrip("|").strip())
            rest = _unescape_md(entry_match.group(2).strip().replace("**", "").lstrip("|").strip())
            full_text = f"{bold_part} | {rest}" if rest else bold_part
            specs.append(LineSpec(text=full_text, kind="entry", bold_len=len(bold_part)))
        elif not bullet_match and line.count("|") >= 2 and ":" not in line.split("|")[0]:
            # Model occasionally skips the ** bold markers on an entry line
            # (sampling variance) — fall back to bolding whatever comes
            # before the first "|" so the title still stands out visually.
            title_part, _, rest_part = line.partition("|")
            title_part = _unescape_md(title_part.replace("**", "").strip())
            rest_part = _unescape_md(rest_part.replace("**", "").strip())
            full_text = f"{title_part} | {rest_part}"
            specs.append(LineSpec(text=full_text, kind="entry", bold_len=len(title_part)))
        elif bullet_match:
            text, links = _strip_md_links(_unescape_md(bullet_match.group(1).replace("**", "").strip()))
            specs.append(LineSpec(text=text, kind="bullet", links=links))
        else:
            text, links = _strip_md_links(_unescape_md(line.replace("**", "").lstrip("#").strip()))
            specs.append(LineSpec(text=text, kind="normal", links=links))

    return _drop_blank_lines_before_headings(specs)


def _drop_blank_lines_before_headings(specs: list[LineSpec]) -> list[LineSpec]:
    """Belt-and-suspenders: the CV prompt already asks the model not to leave
    a blank line before a section heading, but it doesn't always comply —
    strip any it left in, since that's exactly the "extra gap before each
    section" look this format needs to avoid, and it also costs vertical
    space that matters for fitting the CV on two pages."""
    out: list[LineSpec] = []
    for spec in specs:
        if spec.kind == "heading":
            while out and out[-1].kind == "blank":  # a run of blanks, not just the last one
                out.pop()
        out.append(spec)
    return out


# Google's built-in HEADING_1/HEADING_2 named styles carry generous default
# spacing (often 15-20pt above) intended for long-form documents, which reads
# as "extra gaps before every section" on a CV and eats into the two-page
# budget. So every paragraph here uses NORMAL_TEXT and gets its visual weight
# from explicit font size/bold plus small, deliberate paragraph spacing —
# full control instead of inheriting a preset meant for something else.
_ALIGNMENT = {
    "name": "CENTER",
    "contact": "CENTER",
}
_FONT_SIZE_PT = {
    "name": 17,
    "contact": 9.5,
    "heading": 11.5,
    "entry": 10.5,
    "bullet": 10.5,
    "normal": 10.5,
}
_BOLD_WHOLE_LINE = {"name", "heading"}
# (spaceAbove, spaceBelow) in points, applied to the whole paragraph.
# Headings get a visibly larger gap above them than any other spacing here —
# that's deliberate breathing room between sections, not the same thing as
# the blank-line-before-a-heading that gets stripped in parse_cv (that was
# always dead space that ate into the two-page budget for nothing; this is
# controlled, so it's kept small enough elsewhere to still fit two pages).
_SPACING_PT = {
    "name": (0, 2),
    "contact": (0, 6),
    "heading": (14, 3),
    "entry": (4, 0),
    "bullet": (0, 0),
    "normal": (0, 3),
    "blank": (0, 0),
}


def build_tab_content(tab_id: str, base_index: int, specs: list[LineSpec]) -> tuple[str, list[dict]]:
    """Returns (plain_text_to_insert, style_requests) for one tab. Caller is
    responsible for the deleteContentRange + insertText requests; style
    requests here assume that text has already landed at base_index."""
    full_text = "\n".join(s.text for s in specs) + "\n"

    requests: list[dict] = []
    bullet_run_start = None
    bullet_run_end = None
    cursor = base_index

    for spec in specs:
        start, end = cursor, cursor + len(spec.text)

        if spec.kind != "bullet" and bullet_run_start is not None:
            requests.append(_bullet_request(tab_id, bullet_run_start, bullet_run_end))
            bullet_run_start = bullet_run_end = None

        if spec.kind == "blank":
            cursor = end + 1
            continue

        style_end = max(end, start + 1)
        space_above, space_below = _SPACING_PT.get(spec.kind, (0, 4))
        paragraph_style: dict = {
            "namedStyleType": "NORMAL_TEXT",
            "spaceAbove": {"magnitude": space_above, "unit": "PT"},
            "spaceBelow": {"magnitude": space_below, "unit": "PT"},
        }
        fields = ["namedStyleType", "spaceAbove", "spaceBelow"]
        if spec.kind in _ALIGNMENT:
            paragraph_style["alignment"] = _ALIGNMENT[spec.kind]
            fields.append("alignment")
        requests.append(
            {
                "updateParagraphStyle": {
                    "range": {"tabId": tab_id, "startIndex": start, "endIndex": style_end},
                    "paragraphStyle": paragraph_style,
                    "fields": ",".join(fields),
                }
            }
        )

        if end > start:
            requests.append(
                {
                    "updateTextStyle": {
                        "range": {"tabId": tab_id, "startIndex": start, "endIndex": end},
                        "textStyle": {
                            "fontSize": {"magnitude": _FONT_SIZE_PT.get(spec.kind, 10.5), "unit": "PT"},
                            **({"bold": True} if spec.kind in _BOLD_WHOLE_LINE else {}),
                        },
                        "fields": "fontSize" + (",bold" if spec.kind in _BOLD_WHOLE_LINE else ""),
                    }
                }
            )

        if spec.kind == "entry" and spec.bold_len > 0:
            requests.append(
                {
                    "updateTextStyle": {
                        "range": {"tabId": tab_id, "startIndex": start, "endIndex": start + spec.bold_len},
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }
                }
            )

        for link_start, link_end, url in spec.links:
            requests.append(
                {
                    "updateTextStyle": {
                        "range": {
                            "tabId": tab_id,
                            "startIndex": start + link_start,
                            "endIndex": start + link_end,
                        },
                        "textStyle": {"link": {"url": url}},
                        "fields": "link",
                    }
                }
            )

        if spec.kind == "bullet":
            if bullet_run_start is None:
                bullet_run_start = start
            bullet_run_end = end

        cursor = end + 1

    if bullet_run_start is not None:
        requests.append(_bullet_request(tab_id, bullet_run_start, bullet_run_end))

    return full_text, requests


def _bullet_request(tab_id: str, start: int, end: int) -> dict:
    return {
        "createParagraphBullets": {
            "range": {"tabId": tab_id, "startIndex": start, "endIndex": end},
            "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
        }
    }
