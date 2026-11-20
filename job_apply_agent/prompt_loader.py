"""Parses prompts.md into named sections at run time.

The file is never hardcoded into the pipeline — edit prompts.md (headings
"Prompt for Resume:", "Prompt for Cover letter:", "Writing Style:") and the
next run picks up the change automatically.
"""
import re
from dataclasses import dataclass
from pathlib import Path

_SECTION_HEADS = {
    "resume": re.compile(r"^\s*Prompt for Resume:\s*$", re.IGNORECASE | re.MULTILINE),
    "cover_letter": re.compile(r"^\s*Prompt for Cover letter:\s*$", re.IGNORECASE | re.MULTILINE),
    "writing_style": re.compile(r"^\s*Writing Style:\s*$", re.IGNORECASE | re.MULTILINE),
}


@dataclass
class Prompts:
    resume: str
    cover_letter: str
    writing_style: str


def _find_all_heads(text: str) -> list[tuple[str, int, int]]:
    """Returns (section_name, heading_start, content_start) sorted by position."""
    hits = []
    for name, pattern in _SECTION_HEADS.items():
        m = pattern.search(text)
        if not m:
            raise ValueError(
                f"prompts.md is missing the expected heading for section '{name}' "
                f"(looked for something like '{pattern.pattern}')"
            )
        hits.append((name, m.start(), m.end()))
    hits.sort(key=lambda h: h[1])
    return hits


def load_prompts(path: Path) -> Prompts:
    """Parse one flow's prompts.md (each flow has its own; see profiles.py)."""
    text = path.read_text(encoding="utf-8")
    heads = _find_all_heads(text)

    sections: dict[str, str] = {}
    for i, (name, _start, content_start) in enumerate(heads):
        end = heads[i + 1][1] if i + 1 < len(heads) else len(text)
        sections[name] = text[content_start:end].strip()

    return Prompts(
        resume=sections["resume"],
        cover_letter=sections["cover_letter"],
        writing_style=sections["writing_style"],
    )
