"""Explicit application of refreshed suggestions as an unconfirmed context draft."""

from copy import deepcopy
from collections.abc import Iterable

from .models import (
    DEFAULT_BASIS, INTEREST_OPTIONS, PRESSURE_OPTIONS, RELATIONSHIP_OPTIONS,
    ArchivedAnswer, Assessment, Context,
)


SUGGESTED_FIELDS = {
    "role": "Professional role",
    "parties": "Relevant parties and roles",
    "decision": "Professional decision or activity",
    "relationship": "Relationships",
    "interests": "Financial interests and incentives",
    "pressure": "Reported pressure",
}
_DETAIL_FIELDS = {
    "relationship": "relationship_notes", "interests": "interests_notes", "pressure": "pressure_notes",
}


def apply_suggestions(
    assessment: Assessment, scenario: str, draft: Context,
    suggested: Context, selected_fields: Iterable[str],
) -> bool:
    """Apply only explicitly chosen suggestions; never confirm or keep stale answers.

    Other fields retain the user's submitted form values. Source records stay
    unconfirmed until the existing confirmation flow is completed. Phase 2/3
    dependency sync observes this change and preserves its own answer history.
    """
    selected = tuple(selected_fields)
    if not selected or any(field not in SUGGESTED_FIELDS for field in selected):
        raise ValueError("Choose the supported fields you want to replace.")
    if not scenario.strip():
        raise ValueError("Enter a scenario before applying suggestions.")
    updated = deepcopy(draft)
    for field in selected:
        setattr(updated, field, getattr(suggested, field))
        if field in _DETAIL_FIELDS:
            detail = _DETAIL_FIELDS[field]
            setattr(updated, detail, getattr(suggested, detail))
    updated.basis = DEFAULT_BASIS
    for value, options in (
        (updated.relationship, RELATIONSHIP_OPTIONS), (updated.interests, INTEREST_OPTIONS),
        (updated.pressure, PRESSURE_OPTIONS),
    ):
        if value not in options:
            raise ValueError("A context selection is not supported.")
    if assessment.scenario == scenario.strip() and assessment.context == updated:
        return False
    assessment.revision += 1
    for question_id, answer in assessment.answers.items():
        assessment.archive.append(ArchivedAnswer(
            question_id, answer, "Context suggestions changed; reconfirm the account.", assessment.revision,
        ))
    assessment.answers.clear()
    assessment.scenario = scenario.strip()
    assessment.context = updated
    assessment.confirmed = False
    return True
