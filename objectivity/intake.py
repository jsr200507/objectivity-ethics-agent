"""Progressive, source-only clarification before the existing assessment engine.

Extraction is a suggestion. This planner asks only about unresolved/weak fields,
accepts explicit uncertainty, and never interprets unrestricted answer text as
ethical evidence. The existing confirmation and question banks retain authority.
"""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re

from .context_suggestions import apply_suggestions
from .models import ArchivedAnswer, Assessment, ContextClarification
from .questions import confirm_context, eligible_questions, save_answer


PROVIDED = "Provided"
UNKNOWN = "I don't know yet"
NOT_APPLICABLE = "Not applicable"
FAMILY_RELATIONSHIP = "A family or other personal relationship"
SELF_INTEREST = "Me or my household"
FAMILY_INTEREST = "A family member (not an established benefit for me)"
ORGANISATION_INTEREST = "My organisation or firm"
BOTH_INTERESTS = "Both me/my household and my organisation"
ANOTHER_INTEREST = "Another person or organisation"
NO_INTEREST = "No financial interest is reported"
OTHER_INTEREST = "Other or unclear beneficiary"
OTHER_RELATIONSHIP = "Other relationship"
OTHER_PRESSURE = "Other reported influence"
INTAKE_IDS = ("role", "decision", "parties", "relationship", "interests", "beneficiary", "pressure")
TEXT_IDS = frozenset({"role", "decision", "parties", "beneficiary"})
OPTIONS_BY_ID = {
    **{id: (PROVIDED, UNKNOWN) for id in TEXT_IDS},
    "relationship": (
        "Professional relationship only", "Close personal relationship", FAMILY_RELATIONSHIP,
        "No relevant personal relationship", OTHER_RELATIONSHIP, UNKNOWN, NOT_APPLICABLE,
    ),
    "interests": (
        SELF_INTEREST, FAMILY_INTEREST, ORGANISATION_INTEREST, BOTH_INTERESTS,
        ANOTHER_INTEREST, NO_INTEREST, OTHER_INTEREST, UNKNOWN, NOT_APPLICABLE,
    ),
    "pressure": (
        "Reported pressure or threatened consequences", "No reported pressure",
        OTHER_PRESSURE, UNKNOWN, NOT_APPLICABLE,
    ),
}
_RELATIONSHIP_VALUES = {
    "Professional relationship only": "Professional relationship only",
    "Close personal relationship": "Close personal relationship",
    FAMILY_RELATIONSHIP: "Other", "No relevant personal relationship": "No relevant relationship",
    OTHER_RELATIONSHIP: "Other", UNKNOWN: "Unknown", NOT_APPLICABLE: "Not applicable",
}
_INTEREST_VALUES = {
    SELF_INTEREST: "Personal financial interest", FAMILY_INTEREST: "Other",
    ORGANISATION_INTEREST: "Commercial interest", BOTH_INTERESTS: "Both commercial and personal interests",
    ANOTHER_INTEREST: "Other", NO_INTEREST: "No known interest", OTHER_INTEREST: "Other",
    UNKNOWN: "Unknown", NOT_APPLICABLE: "Not applicable",
}
_PRESSURE_VALUES = {
    "Reported pressure or threatened consequences": "Reported pressure or threatened consequences",
    "No reported pressure": "No reported pressure", OTHER_PRESSURE: "Other",
    UNKNOWN: "Unknown", NOT_APPLICABLE: "Not applicable",
}
_FIELD_VALUES = {"relationship": _RELATIONSHIP_VALUES, "interests": _INTEREST_VALUES, "pressure": _PRESSURE_VALUES}
_DETAIL_FIELDS = {"relationship": "relationship_notes", "interests": "interests_notes", "pressure": "pressure_notes"}
_BENEFICIARY_CHOICES = {FAMILY_INTEREST, ANOTHER_INTEREST, OTHER_INTEREST}
_MAX_TEXT = 100_000


@dataclass(frozen=True)
class IntakeQuestion:
    id: str
    field: str
    prompt: str
    options: tuple[str, ...]
    why: str
    allow_not_applicable: bool = False


_QUESTIONS = {
    q.id: q for q in (
        IntakeQuestion("role", "role", "What is your professional role in this situation?", (),
            "The local rules could not establish a sufficiently clear role. Your own wording is enough; it does not need to match a recognised job title."),
        IntakeQuestion("decision", "decision", "What professional decision or activity are you being asked to make or change?", (),
            "The activity needs clarification. Describe the judgement, work or information-sharing decision, including a requested change if one is reported."),
        IntakeQuestion("parties", "parties", "Who is involved, and what is each person's or organisation's role?", (),
            "The rules found no clear party list or only broad titles. Include decision makers, relevant family or business connections, and people receiving or being denied information. Do not guess a missing role."),
        IntakeQuestion("relationship", "relationship", "Which relationship with someone involved could be relevant to your judgement?", OPTIONS_BY_ID["relationship"],
            "The relationship is not established clearly enough. A family tie does not by itself establish closeness, and a professional title does not rule out other ties."),
        IntakeQuestion("interests", "interests", "Whose financial benefit or interest could be affected by this decision?", OPTIONS_BY_ID["interests"],
            "The financial connection or its beneficiary is unclear. Distinguish your own or household benefit, a family member's benefit, the organisation's interest and another person's benefit. Career incentives do not automatically imply money."),
        IntakeQuestion("beneficiary", "interests", "Who receives that benefit, and what is the financial interest?", (),
            "You identified a family member or another beneficiary. Name their role and interest if known, such as a sister's supplier shares or a director's consulting fee. These details remain your reported account, not a benefit automatically attributed to you."),
        IntakeQuestion("pressure", "pressure", "Has anyone asked you to change, withhold or favour professional work, or suggested consequences?", OPTIONS_BY_ID["pressure"],
            "The rules could not reliably classify reported influence. A request can matter without an explicit threat, but neither a request nor a claim establishes misconduct or a completed change to work."),
    )
}


def question_for_field(field: str) -> IntakeQuestion:
    """Return an editable question even when its current suggestion is populated."""
    if field not in _QUESTIONS:
        raise ValueError("Choose a supported context topic.")
    return _QUESTIONS[field]


def clarification_fingerprint(assessment: Assessment, question_id: str) -> str:
    """Bind a source answer to its scenario, field and relevant core context."""
    question = question_for_field(question_id)
    field = question.field
    context = assessment.context
    payload = {"scenario": assessment.scenario, "field": field, "value": getattr(context, field)}
    if field in _DETAIL_FIELDS:
        payload["notes"] = getattr(context, _DETAIL_FIELDS[field])
        payload["core"] = [context.role, context.decision, context.parties]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _expected_value(question_id: str, record: ContextClarification) -> str:
    if question_id in TEXT_IDS:
        return "Unknown" if record.choice == UNKNOWN else record.detail.strip()
    return _FIELD_VALUES[question_id][record.choice]


def validate_clarification(
    assessment: Assessment, question_id: str, record: ContextClarification,
    *, check_fingerprint: bool = True,
) -> bool:
    """Validate source metadata without trusting any imported conclusion."""
    if question_id not in INTAKE_IDS or not isinstance(record, ContextClarification):
        return False
    if not all(isinstance(value, str) for value in (record.choice, record.detail, record.fingerprint)):
        return False
    if record.choice not in OPTIONS_BY_ID[question_id] or len(record.detail) > _MAX_TEXT:
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", record.fingerprint):
        return False
    if record.choice == PROVIDED and not record.detail.strip():
        return False
    if question_id == "beneficiary":
        primary = assessment.context_clarifications.get("interests")
        if primary is None or primary.choice not in _BENEFICIARY_CHOICES:
            return False
        if not validate_clarification(assessment, "interests", primary, check_fingerprint=check_fingerprint):
            return False
        if assessment.context.interests != "Other":
            return False
        if assessment.context.interests_notes != _notes("interests", primary.choice, primary.detail, record):
            return False
    elif getattr(assessment.context, question_for_field(question_id).field) != _expected_value(question_id, record):
        return False
    if question_id in _DETAIL_FIELDS:
        beneficiary = assessment.context_clarifications.get("beneficiary") if question_id == "interests" else None
        if beneficiary is not None and record.choice not in _BENEFICIARY_CHOICES:
            return False
        if getattr(assessment.context, _DETAIL_FIELDS[question_id]) != _notes(question_id, record.choice, record.detail, beneficiary):
            return False
    return not check_fingerprint or record.fingerprint == clarification_fingerprint(assessment, question_id)


def is_current_clarification(assessment: Assessment, question_id: str) -> bool:
    record = assessment.context_clarifications.get(question_id)
    return record is not None and validate_clarification(assessment, question_id, record)


def sync_intake(assessment: Assessment) -> tuple[str, ...]:
    """Discard stale answer metadata; retain the source Context and other histories."""
    removed = []
    for question_id in list(assessment.context_clarifications):
        if not is_current_clarification(assessment, question_id):
            assessment.context_clarifications.pop(question_id)
            removed.append(question_id)
    return tuple(removed)


def _missing(value: str) -> bool:
    return not value.strip() or value.strip().casefold() == "unknown"


def _weak_parties(value: str) -> bool:
    if _missing(value):
        return True
    counterparts = [piece.strip().casefold() for piece in value.split(";") if not piece.strip().lower().startswith("you —")]
    return not counterparts or all(piece in {"director", "manager", "supervisor", "company", "firm", "team", "client", "supplier"} for piece in counterparts)


def intake_questions(assessment: Assessment) -> tuple[IntakeQuestion, ...]:
    """Return only applicable gaps, in priority order; no fixed mandatory checklist."""
    if assessment.confirmed:
        return ()
    context = assessment.context
    result = []
    for field in ("role", "decision", "parties", "relationship", "interests", "pressure"):
        if is_current_clarification(assessment, field):
            continue
        value = getattr(context, field)
        needed = _missing(value)
        if field == "parties": needed = _weak_parties(value)
        if field == "relationship" and value == "Other" and not context.relationship_notes.strip(): needed = True
        if field in {"interests", "pressure"} and value == "Other": needed = True
        if needed: result.append(_QUESTIONS[field])
    primary = assessment.context_clarifications.get("interests")
    if (
        primary is not None and is_current_clarification(assessment, "interests")
        and primary.choice in _BENEFICIARY_CHOICES and not primary.detail.strip()
        and not is_current_clarification(assessment, "beneficiary")
    ):
        position = next((i for i, q in enumerate(result) if q.id == "pressure"), len(result))
        result.insert(position, _QUESTIONS["beneficiary"])
    return tuple(result)


def next_intake_question(assessment: Assessment) -> IntakeQuestion | None:
    pending = intake_questions(assessment)
    return pending[0] if pending else None


def _notes(field: str, choice: str, detail: str, beneficiary: ContextClarification | None = None) -> str:
    if field == "relationship":
        labels = {
            FAMILY_RELATIONSHIP: "A family or other personal relationship is reported; personal closeness is not established.",
            "No relevant personal relationship": "No relevant personal relationship is reported by the user.",
            OTHER_RELATIONSHIP: "The user reports another relationship; its significance remains to be clarified.",
            UNKNOWN: "The relationship is not known from the user's current account.",
        }
        base = labels.get(choice, choice + ".")
    elif field == "interests":
        labels = {
            SELF_INTEREST: "A financial interest of the user or their household is reported.",
            FAMILY_INTEREST: "A family member's financial interest is reported; a financial benefit for the user or household is not established.",
            ORGANISATION_INTEREST: "An organisational or firm financial interest is reported; a personal benefit is not assumed.",
            BOTH_INTERESTS: "Both a user/household financial interest and an organisational interest are reported.",
            ANOTHER_INTEREST: "Another person's or organisation's financial interest is reported; a personal benefit for the user is not established.",
            NO_INTEREST: "The user reports no known financial interest in the current account.",
            OTHER_INTEREST: "The financial interest or its beneficiary remains unclear in the user's account.",
            UNKNOWN: "Financial interests are not known from the user's current account.",
        }
        base = labels.get(choice, choice + ".")
    else:
        labels = {
            "Reported pressure or threatened consequences": "The user reports a request or other influence affecting professional work. This does not establish an explicit threat, misconduct or a completed change.",
            "No reported pressure": "The user reports no pressure in the current account.",
            OTHER_PRESSURE: "The user reports another influence; its nature and significance remain to be clarified.",
            UNKNOWN: "Reported pressure or consequences are not known from the user's current account.",
        }
        base = labels.get(choice, choice + ".")
    if detail.strip(): base += " User explanation: " + detail.strip()
    if beneficiary is not None:
        if beneficiary.choice == UNKNOWN:
            base += " Specific beneficiary or interest details are not known from the user's account."
        else:
            base += " Reported beneficiary and interest: " + beneficiary.detail.strip()
    return base


def save_intake_answer(
    assessment: Assessment, question_id: str, choice: str = "", detail: str = "",
) -> None:
    """Save a user's structured clarification as an unconfirmed source draft."""
    question = question_for_field(question_id)
    if not isinstance(choice, str) or not isinstance(detail, str) or len(detail) > _MAX_TEXT:
        raise ValueError("Enter a supported answer within the text limit.")
    detail = detail.strip()
    if question_id in TEXT_IDS and not choice: choice = PROVIDED
    if choice not in OPTIONS_BY_ID[question_id]:
        raise ValueError("Choose one of the available clarification answers.")
    if choice == PROVIDED and not detail:
        raise ValueError("Enter the detail, or explicitly choose that you do not know yet.")
    if question_id == "beneficiary":
        primary = assessment.context_clarifications.get("interests")
        if primary is None or not is_current_clarification(assessment, "interests") or primary.choice not in _BENEFICIARY_CHOICES:
            raise ValueError("Clarify whose financial interest is involved first.")
    previous_record = assessment.context_clarifications.get(question_id)
    if (
        previous_record is not None and is_current_clarification(assessment, question_id)
        and previous_record.choice == choice and previous_record.detail == detail
    ):
        return
    updated = deepcopy(assessment.context)
    if question_id == "beneficiary":
        primary = assessment.context_clarifications["interests"]
        supplied = ContextClarification(choice, detail)
        updated.interests_notes = _notes("interests", primary.choice, primary.detail, supplied)
    elif question_id in TEXT_IDS:
        setattr(updated, question.field, "Unknown" if choice == UNKNOWN else detail)
    else:
        setattr(updated, question.field, _FIELD_VALUES[question_id][choice])
        setattr(updated, _DETAIL_FIELDS[question.field], _notes(question.field, choice, detail))
    if len(getattr(updated, question.field)) > _MAX_TEXT or (
        question.field in _DETAIL_FIELDS and len(getattr(updated, _DETAIL_FIELDS[question.field])) > _MAX_TEXT
    ):
        raise ValueError("The clarification is too long to save safely; shorten the explanation.")
    prior = dict(assessment.context_clarifications)
    if question_id == "interests": prior.pop("beneficiary", None)
    changed = apply_suggestions(assessment, assessment.scenario, assessment.context, updated, [question.field])
    if not changed:
        # An explicit source correction still requires the user to review again,
        # even if it repeats the currently stored field value.
        assessment.revision += 1
        for saved_id, answer in assessment.answers.items():
            assessment.archive.append(ArchivedAnswer(
                saved_id, answer, "Context clarification changed; reconfirm the account.", assessment.revision,
            ))
        assessment.answers.clear()
        assessment.confirmed = False
    assessment.context_clarifications = prior
    # Core changes invalidate dependent snapshots; notes edits remain topic-local.
    if question_id != "beneficiary": sync_intake(assessment)
    assessment.context_clarifications[question_id] = ContextClarification(
        choice, detail, clarification_fingerprint(assessment, question_id),
    )
    if question_id == "beneficiary":
        assessment.context_clarifications["interests"] = ContextClarification(
            primary.choice, primary.detail, clarification_fingerprint(assessment, "interests"),
        )


def confirm_intake(assessment: Assessment) -> None:
    """Confirm source data, then reuse only equivalent explicit structured answers."""
    sync_intake(assessment)
    if next_intake_question(assessment) is not None:
        raise ValueError("Clarify the active detail, or explicitly record that it is not known, before confirming.")
    confirm_context(assessment, assessment.scenario, assessment.context)
    seeds = {}
    for field, relevance in (("pressure", "pressure_relevance"), ("relationship", "relationship_relevance"), ("interests", "interest_relevance")):
        if not is_current_clarification(assessment, field): continue
        choice = assessment.context_clarifications[field].choice
        if choice == UNKNOWN:
            seeds[relevance] = "Unknown"
        elif field == "relationship" and choice == FAMILY_RELATIONSHIP:
            seeds[relevance] = "Possibly relevant"
        elif field == "relationship" and choice == OTHER_RELATIONSHIP:
            seeds[relevance] = "Other"
        elif field == "interests" and choice in _BENEFICIARY_CHOICES:
            seeds[relevance] = "Other"
        elif field == "pressure" and choice == OTHER_PRESSURE:
            seeds[relevance] = "Other"
    for question_id, choice in seeds.items():
        available = {q.id for q in eligible_questions(assessment)}
        if question_id in available and question_id not in assessment.answers:
            save_answer(assessment, question_id, choice, "Recorded explicitly during context clarification; not independently verified.")
