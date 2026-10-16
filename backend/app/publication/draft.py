"""Turn a submitted lesson-order edit into a validated draft revision (V0-007).

Pure and deterministic: it maps the client's *intent* (an ordered list of
section ids plus scripts) onto the package's lesson order, and refuses anything
that is not a strict re-arrangement of it.

The safety property this buys is the acceptance criterion "edits create draft
data, not mutate published package": the draft inherits every structural field
(``scene_id``, ``scene_step_id``, ``safe_markers``, ``type``) from the package
under review, so a client can only reorder and re-script. It can neither point a
section at a scene that is not in the package nor smuggle a new one in, and the
package itself is never written (``DEC-CONTENT-005``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from app.common.errors import AppError, ErrorCode
from app.publication.models import DraftSection
from app.publication.review import ReviewSection

#: Stable issue codes (the API returns them alongside ``INVALID_REQUEST``).
ISSUE_EMPTY_DRAFT = "EMPTY_DRAFT"
ISSUE_UNKNOWN_SECTION = "UNKNOWN_SECTION"
ISSUE_DUPLICATE_SECTION = "DUPLICATE_SECTION"
ISSUE_MISSING_SECTION = "MISSING_SECTION"
ISSUE_INVALID_SCRIPT = "INVALID_SCRIPT"
ISSUE_REVISION_CONFLICT = "REVISION_CONFLICT"


class DraftError(AppError):
    """A draft edit is not a valid revision of this package's lesson order.

    ``issue_code`` carries the precise classification; ``INVALID_REQUEST`` (+400)
    is the stable code, or ``409`` for a conflicting revision. This mirrors the
    fidelity/package validators, which carry their detail in ``issue_code``
    rather than growing ``ErrorCode``.
    """

    code = ErrorCode.INVALID_REQUEST

    def __init__(
        self, message: str, *, issue_code: str = ISSUE_EMPTY_DRAFT, http_status: int = 400
    ) -> None:
        super().__init__(message)
        self.issue_code = issue_code
        self.http_status = http_status


@dataclass(frozen=True)
class SectionInput:
    """What a client may say about one section: its id and (optionally) a script."""

    section_id: str
    script: Optional[str] = None


@dataclass(frozen=True)
class DraftDiff:
    """How the draft differs from the package's fallback lesson order."""

    sections: int
    reordered: int
    scripts_edited: int
    sections_removed: int = 0
    sections_added: int = 0

    @property
    def is_identical(self) -> bool:
        return self.reordered == 0 and self.scripts_edited == 0

    def to_dict(self) -> dict[str, int]:
        return {
            "sections": self.sections,
            "reordered": self.reordered,
            "scripts_edited": self.scripts_edited,
            "sections_removed": self.sections_removed,
            "sections_added": self.sections_added,
        }


def _clean_script(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DraftError("a script must be a string", issue_code=ISSUE_INVALID_SCRIPT)
    # Canonical: an all-whitespace script means "no script", so "" and "  " are
    # the same draft and a rebuild is idempotent.
    return value.strip() or None


def resolve_draft_sections(
    lesson_order: Sequence[ReviewSection], submitted: Iterable[SectionInput]
) -> tuple[tuple[DraftSection, ...], DraftDiff]:
    """Validate ``submitted`` against ``lesson_order`` and resolve a revision.

    ``submitted`` is ordered: position *is* the new lesson order. ``script=None``
    inherits the package's script (so a client can reorder without restating
    scripts); an explicit string replaces it.
    """

    base = {section.section_id: section for section in lesson_order}
    inputs = list(submitted)
    if not inputs:
        raise DraftError(
            "a draft must keep the lesson order's sections; none were submitted",
            issue_code=ISSUE_EMPTY_DRAFT,
        )

    resolved: list[DraftSection] = []
    seen: set[str] = set()
    for index, item in enumerate(inputs):
        section_id = (item.section_id or "").strip()
        if not section_id:
            raise DraftError(
                f"section #{index + 1} has no section_id", issue_code=ISSUE_UNKNOWN_SECTION
            )
        if section_id not in base:
            raise DraftError(
                f"section {section_id!r} is not part of this package's lesson order",
                issue_code=ISSUE_UNKNOWN_SECTION,
            )
        if section_id in seen:
            raise DraftError(
                f"section {section_id!r} appears more than once", issue_code=ISSUE_DUPLICATE_SECTION
            )
        seen.add(section_id)

        source = base[section_id]
        script = source.script if item.script is None else _clean_script(item.script)
        resolved.append(
            DraftSection(
                order=index,
                section_id=section_id,
                type=source.type,
                scene_id=source.scene_id,
                scene_step_id=source.scene_step_id,
                safe_markers=source.safe_markers,
                script=script,
            )
        )

    missing = [sid for sid in base if sid not in seen]
    if missing:
        raise DraftError(
            f"the draft removes {len(missing)} section(s) of the lesson order; "
            "editing may only reorder or re-script (corrections create new versions)",
            issue_code=ISSUE_MISSING_SECTION,
        )

    reordered = sum(
        1
        for index, section in enumerate(resolved)
        if lesson_order[index].section_id != section.section_id
    )
    scripts_edited = sum(
        1
        for section in resolved
        if section.script != base[section.section_id].script
    )
    return (
        tuple(resolved),
        DraftDiff(sections=len(resolved), reordered=reordered, scripts_edited=scripts_edited),
    )


__all__ = [
    "ISSUE_DUPLICATE_SECTION",
    "ISSUE_EMPTY_DRAFT",
    "ISSUE_INVALID_SCRIPT",
    "ISSUE_MISSING_SECTION",
    "ISSUE_REVISION_CONFLICT",
    "ISSUE_UNKNOWN_SECTION",
    "DraftDiff",
    "DraftError",
    "SectionInput",
    "resolve_draft_sections",
]
