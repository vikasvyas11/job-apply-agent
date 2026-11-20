"""Application profiles: which *flow* (Data Science, Growth, Software Dev) and
which *region* (UK, India) a run uses.

A flow is a complete, separate set of content: its own master CV, project notes,
cover letter reference and prompts, in content/<flow>/. A run uses exactly one
flow, so a Growth application can never pick up Software Dev bullets or talking
points; the other flows' files are simply never read.

A region fills the {{LOCATION}} and {{PHONE}} placeholders in the CV's contact
line. Region details live in local_settings.json (set on the Setup page), not in
code, so no personal data is hardcoded.
"""
from dataclasses import dataclass
from pathlib import Path

from job_apply_agent import config, local_settings

# key -> label shown in the UI. The key is also the folder name under content/.
FLOWS: dict[str, str] = {
    "data": "Data Science",
    "growth": "Growth",
    "software": "Software Dev",
}
DEFAULT_FLOW = "data"

CONTENT_FILES = ("resume.md", "project_notes.md", "coverletter_reference.md", "prompts.md")

LOCATION_TOKEN = "{{LOCATION}}"
PHONE_TOKEN = "{{PHONE}}"


@dataclass(frozen=True)
class Region:
    key: str
    location: str
    phone: str


@dataclass(frozen=True)
class Profile:
    flow: str
    region: str

    def __post_init__(self) -> None:
        if self.flow not in FLOWS:
            raise ValueError(f"Unknown flow {self.flow!r}; expected one of {sorted(FLOWS)}")
        if self.region not in regions():
            raise ValueError(f"Unknown region {self.region!r}; expected one of {sorted(regions())}")

    @property
    def flow_label(self) -> str:
        return FLOWS[self.flow]

    @property
    def content_dir(self) -> Path:
        return flow_dir(self.flow)

    @property
    def resume_file(self) -> Path:
        return self.content_dir / "resume.md"

    @property
    def project_notes_file(self) -> Path:
        return self.content_dir / "project_notes.md"

    @property
    def cover_letter_reference_file(self) -> Path:
        return self.content_dir / "coverletter_reference.md"

    @property
    def prompts_file(self) -> Path:
        return self.content_dir / "prompts.md"

    def render(self, text: str) -> str:
        """Fill the region placeholders. A placeholder whose value is not set is
        removed together with its " | " separator, so the contact line never
        shows a literal {{PHONE}} or a dangling bar."""
        region = regions()[self.region]
        for token, value in ((LOCATION_TOKEN, region.location), (PHONE_TOKEN, region.phone)):
            if value:
                text = text.replace(token, value)
            else:
                text = text.replace(f"{token} | ", "").replace(f" | {token}", "").replace(token, "")
        return text


def flow_dir(flow: str) -> Path:
    # Resolved on every call (not cached) so tests can point config.CONTENT_DIR elsewhere.
    return config.CONTENT_DIR / flow


def regions() -> dict[str, Region]:
    raw = local_settings.load()["regions"]
    return {
        key: Region(key=key, location=str(value.get("location", "")), phone=str(value.get("phone", "")))
        for key, value in raw.items()
    }


def default_region() -> str:
    return next(iter(regions()), "")
