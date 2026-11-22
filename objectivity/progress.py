"""Bounded, versioned JSON progress snapshots; no executable deserialization.

Only user accounts and workflow data are portable. Findings, reports, widget
state and derived evaluation signatures are deliberately excluded. Restoring a snapshot
revalidates its answers against the live conditional question banks and rebuilds
the signatures used by the existing invalidation logic.
"""

from copy import deepcopy
from dataclasses import asdict, dataclass, fields
import json
import re

from .address import (
    ACTION_OPTIONS, AddressHistory, AddressState, eligible_address_questions,
    save_address_answer, sync_address,
)
from .models import (
    DEFAULT_BASIS, INTEREST_OPTIONS, PRESSURE_OPTIONS, RELATIONSHIP_OPTIONS,
    Answer, ArchivedAnswer, Assessment, Context, ContextClarification,
)
from .questions import QUESTION_BANK, confirm_context, eligible_questions, next_question, save_answer
from .review import (
    REVIEW_QUESTIONS, ReviewState, eligible_review_questions, next_review_question,
    save_review_answer, sync_review,
)


FORMAT_NAME = "objectivity-ethics-assistant-progress"
FORMAT_VERSION = 2
LEGACY_FORMAT_VERSION = 1
RULES_VERSION = "objectivity-phases-1-3-v1"
MAX_PROGRESS_BYTES = 2 * 1024 * 1024
MAX_TEXT_LENGTH = 100_000
MAX_RECORDS = 2_000
MAX_ACTION_SLOTS = 100
MAX_SLOT_NUMBER = 100_000
MAX_DEPTH = 20
VIEWS = frozenset({"scenario", "context", "questions", "review", "address", "report"})
_ADDRESS_FIELDS = frozenset({
    "action", "implementation", "independence", "competence", "authority", "scope",
    "replacement", "obligations", "recipient", "response", "documentation", "timing",
    "prior_work", "effect", "evidence",
})
_ADDRESS_ID = re.compile(r"^(Familiarity|Intimidation|Self-interest):(0|[1-9][0-9]{0,5}):([a-z_]+)$")


class ProgressError(ValueError):
    """Saved data cannot safely be used with this application version."""


@dataclass
class ProgressSnapshot:
    assessment: Assessment
    review: ReviewState
    address: AddressState
    view: str
    warnings: tuple[str, ...] = ()


def _object(value, keys: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ProgressError(f"{label} has missing or unsupported fields.")
    return value


def _text(value, label: str, limit: int = MAX_TEXT_LENGTH) -> str:
    if type(value) is not str or len(value) > limit:
        raise ProgressError(f"{label} must be text within the supported length limit.")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ProgressError(f"{label} contains invalid Unicode text.") from error
    return value


def _integer(value, label: str, maximum: int = 1_000_000_000) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ProgressError(f"{label} must be a supported non-negative integer.")
    return value


def _list(value, label: str, maximum: int = MAX_RECORDS) -> list:
    if type(value) is not list or len(value) > maximum:
        raise ProgressError(f"{label} has an unsupported number or type of records.")
    return value


def _answer(value) -> Answer:
    value = _object(value, {"choice", "explanation"}, "An answer")
    return Answer(_text(value["choice"], "An answer choice", 1_000), _text(value["explanation"], "An answer explanation"))


def _answers(value, bank=None) -> dict[str, Answer]:
    if type(value) is not dict or len(value) > MAX_RECORDS:
        raise ProgressError("The active answers have an unsupported structure or size.")
    result = {}
    for id, raw_answer in value.items():
        _text(id, "A question identifier", 200)
        if bank is not None and id not in bank:
            raise ProgressError("A saved question is not supported by this rules version.")
        answer = _answer(raw_answer)
        if bank is not None and answer.choice not in bank[id].options:
            raise ProgressError("A saved answer choice is incompatible with the current questions.")
        result[id] = answer
    return result


def _context_clarifications(value, assessment: Assessment, warnings: list[str]) -> dict[str, ContextClarification]:
    """Validate source answers; stale metadata never settles an edited context.

    These tokens only bind a submitted clarification to the account it described.
    They do not authenticate a fact or act as an ethical conclusion.
    """
    from .intake import (
        INTAKE_IDS, OPTIONS_BY_ID, clarification_fingerprint, validate_clarification,
    )

    if type(value) is not dict or len(value) > len(INTAKE_IDS):
        raise ProgressError("Context clarification progress has an unsupported structure or size.")
    candidates = {}
    for id, raw_record in value.items():
        if _text(id, "A context clarification identifier", 100) not in INTAKE_IDS:
            raise ProgressError("A context clarification is not supported by this application version.")
        raw_record = _object(raw_record, {"choice", "detail", "fingerprint"}, "A context clarification")
        choice = _text(raw_record["choice"], "A context clarification choice", 1_000)
        detail = _text(raw_record["detail"], "A context clarification explanation")
        fingerprint = _text(raw_record["fingerprint"], "A context clarification source token", 64)
        if choice not in OPTIONS_BY_ID[id] or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
            raise ProgressError("A context clarification has an incompatible choice or source token.")
        candidates[id] = ContextClarification(choice, detail, fingerprint)
    # Filter source bindings first, then validate dependencies in question
    # order. JSON key order cannot preserve a beneficiary whose primary source
    # answer was invalidated by an edit.
    records = {
        id: record for id, record in candidates.items()
        if record.fingerprint == clarification_fingerprint(assessment, id)
    }
    stale = len(records) != len(candidates)
    assessment.context_clarifications = records
    for id in INTAKE_IDS:
        if id not in records:
            continue
        if id == "beneficiary" and "interests" in candidates and "interests" not in records:
            records.pop(id)
            stale = True
            continue
        record = records[id]
        if not validate_clarification(assessment, id, record, check_fingerprint=False):
            raise ProgressError("A context clarification contradicts the recorded context.")
    if stale:
        warnings.append("Some context clarification responses described an earlier account and must be reconsidered.")
    return records


def _address_id(id: str) -> tuple[str, int, str]:
    match = _ADDRESS_ID.fullmatch(_text(id, "An Address question identifier", 200))
    if not match or match[3] not in _ADDRESS_FIELDS or int(match[2]) > MAX_SLOT_NUMBER:
        raise ProgressError("An Address question is not supported by this rules version.")
    return match[1], int(match[2]), match[3]


def _history(value, bank, revision: int) -> list[ArchivedAnswer]:
    result = []
    for record in _list(value, "Superseded answers"):
        record = _object(record, {"question_id", "answer", "reason", "revision"}, "A superseded answer")
        id = _text(record["question_id"], "A superseded question", 200)
        if id not in bank:
            raise ProgressError("A superseded question is incompatible with this rules version.")
        answer = _answer(record["answer"])
        if answer.choice not in bank[id].options:
            raise ProgressError("A superseded answer choice is incompatible with this rules version.")
        result.append(ArchivedAnswer(
            id, answer, _text(record["reason"], "A history reason", 2_000),
            _integer(record["revision"], "A history revision", revision),
        ))
    return result


def _address_history(value, revision: int) -> list[AddressHistory]:
    result = []
    for record in _list(value, "Superseded Address answers"):
        record = _object(record, {"question_id", "prompt", "answer", "reason", "revision"}, "A superseded Address answer")
        _address_id(record["question_id"])
        result.append(AddressHistory(
            record["question_id"], _text(record["prompt"], "A historical Address question", 2_000),
            _answer(record["answer"]), _text(record["reason"], "An Address history reason", 2_000),
            _integer(record["revision"], "An Address history revision", revision),
        ))
    return result


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProgressError("Progress JSON contains duplicate object fields.")
        result[key] = value
    return result


def _no_constant(_value):
    raise ProgressError("Progress JSON contains a non-standard numeric value.")


def _check_depth(value, depth=0) -> None:
    if depth > MAX_DEPTH:
        raise ProgressError("Progress JSON is nested too deeply.")
    if isinstance(value, dict):
        for key, item in value.items():
            _text(key, "A JSON field name", MAX_TEXT_LENGTH)
            _check_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_depth(item, depth + 1)
    elif isinstance(value, str):
        _text(value, "Progress text")


def _decode(data: str | bytes) -> dict:
    if type(data) not in (str, bytes):
        raise ProgressError("Import a JSON text file, not an executable or serialized Python object.")
    try:
        raw = data.encode("utf-8", errors="strict") if isinstance(data, str) else data
        if len(raw) > MAX_PROGRESS_BYTES:
            raise ProgressError("Progress file exceeds the 2 MiB size limit.")
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_no_constant)
        _check_depth(value)
    except ProgressError:
        raise
    except (UnicodeError, ValueError, RecursionError, OverflowError) as error:
        raise ProgressError("Saved progress is not valid supported UTF-8 JSON.") from error
    return _object(value, {"format", "schema_version", "rules_version", "assessment", "review", "address", "view"}, "The progress document")


def _restore_answers(assessment, raw, available, save, archive, warning: str, warnings: list[str]):
    pending = dict(raw)
    while pending:
        applicable = {q.id: q for q in available()}
        selected = next((id for id in pending if id in applicable), None)
        if selected is None:
            for id, answer in pending.items():
                archive(id, answer)
            warnings.append(warning)
            return
        answer = pending.pop(selected)
        if answer.choice not in applicable[selected].options:
            raise ProgressError("A saved answer is incompatible with its current conditional question.")
        save(selected, answer)


def _import_progress(data: str | bytes) -> ProgressSnapshot:
    """Validate and reconstruct a snapshot without touching any existing session."""
    root = _decode(data)
    if (
        root["format"] != FORMAT_NAME or type(root["schema_version"]) is not int
        or root["schema_version"] not in {LEGACY_FORMAT_VERSION, FORMAT_VERSION}
    ):
        raise ProgressError("This progress file uses an unsupported format or schema version.")
    if root["rules_version"] != RULES_VERSION:
        raise ProgressError("This progress file requires a different assessment rules version.")
    view = _text(root["view"], "The workflow stage", 40)
    if view not in VIEWS:
        raise ProgressError("The saved workflow stage is not supported.")
    assessment_fields = {"scenario", "context", "confirmed", "answers", "archive", "revision"}
    if root["schema_version"] == FORMAT_VERSION:
        assessment_fields.add("context_clarifications")
    raw_assessment = _object(root["assessment"], assessment_fields, "The assessment")
    revision = _integer(raw_assessment["revision"], "The assessment revision")
    scenario = _text(raw_assessment["scenario"], "The scenario")
    if type(raw_assessment["confirmed"]) is not bool:
        raise ProgressError("Context confirmation must be true or false.")
    raw_context = _object(raw_assessment["context"], {f.name for f in fields(Context)}, "The context")
    context = Context(**{key: _text(value, "A context field") for key, value in raw_context.items()})
    if (
        context.relationship not in RELATIONSHIP_OPTIONS or context.interests not in INTEREST_OPTIONS
        or context.pressure not in PRESSURE_OPTIONS or context.basis != DEFAULT_BASIS
    ):
        raise ProgressError("The context has incompatible choices or an unsupported evidence status.")
    phase_one = _answers(raw_assessment["answers"], QUESTION_BANK)
    assessment = Assessment(scenario=scenario, context=deepcopy(context))
    if raw_assessment["confirmed"]:
        try:
            confirm_context(assessment, scenario, context)
        except ValueError as error:
            raise ProgressError("Confirmed progress must include a scenario, role, parties and professional decision.") from error
    assessment.archive = _history(raw_assessment["archive"], QUESTION_BANK, revision)
    warnings: list[str] = []
    assessment.context_clarifications = _context_clarifications(
        raw_assessment.get("context_clarifications", {}), assessment, warnings,
    )
    _restore_answers(
        assessment, phase_one, lambda: eligible_questions(assessment),
        lambda id, answer: save_answer(assessment, id, answer.choice, answer.explanation),
        lambda id, answer: assessment.archive.append(ArchivedAnswer(id, answer, "Restored answer is no longer applicable to the current context.", revision)),
        "Some clarification answers no longer apply and were retained in superseded history.", warnings,
    )
    raw_review = _object(root["review"], {"answers", "archive"}, "The evaluation progress")
    review = ReviewState(archive=_history(raw_review["archive"], REVIEW_QUESTIONS, revision))
    sync_review(assessment, review)
    phase_two = _answers(raw_review["answers"], REVIEW_QUESTIONS)
    _restore_answers(
        assessment, phase_two, lambda: eligible_review_questions(assessment, review),
        lambda id, answer: save_review_answer(assessment, review, id, answer.choice, answer.explanation),
        lambda id, answer: review.archive.append(ArchivedAnswer(id, answer, "Restored evaluation answer is no longer applicable.", revision)),
        "Some evaluation answers no longer apply and were retained in superseded history.", warnings,
    )
    raw_address = _object(root["address"], {"answers", "archive", "extra_slots", "next_slot", "prompts"}, "The Address progress")
    address = AddressState(archive=_address_history(raw_address["archive"], revision))
    sync_address(assessment, review, address)
    extra_slots = []
    for item in _list(raw_address["extra_slots"], "Supporting actions", MAX_ACTION_SLOTS):
        if type(item) is not list or len(item) != 2 or item[0] not in ACTION_OPTIONS:
            raise ProgressError("A supporting action has an incompatible structure.")
        slot = _integer(item[1], "A supporting action slot", MAX_SLOT_NUMBER)
        if slot == 0 or any(existing_slot == slot for _, existing_slot in extra_slots):
            raise ProgressError("A supporting action slot is duplicated or invalid.")
        extra_slots.append((item[0], slot))
    next_slot = _integer(raw_address["next_slot"], "The next supporting action slot", MAX_SLOT_NUMBER + 1)
    if next_slot < 1 or any(slot >= next_slot for _, slot in extra_slots):
        raise ProgressError("The supporting action sequence is inconsistent.")
    phase_three = _answers(raw_address["answers"])
    if type(raw_address["prompts"]) is not dict or len(raw_address["prompts"]) > MAX_RECORDS:
        raise ProgressError("Saved Address question labels have an unsupported structure.")
    prompts = {}
    for id, prompt in raw_address["prompts"].items():
        _address_id(id)
        prompts[id] = _text(prompt, "A saved Address question label", 2_000)
    known_slots = {(kind, 0) for kind in ACTION_OPTIONS} | set(extra_slots)
    for id in phase_three:
        kind, slot, _ = _address_id(id)
        if (kind, slot) not in known_slots:
            raise ProgressError("An Address answer refers to a missing supporting action.")
    address.extra_slots = extra_slots
    address.next_slot = next_slot
    _restore_answers(
        assessment, phase_three, lambda: eligible_address_questions(assessment, review, address),
        lambda id, answer: save_address_answer(assessment, review, address, id, answer.choice, answer.explanation),
        lambda id, answer: address.archive.append(AddressHistory(id, prompts.get(id, "Earlier action question"), answer, "Restored action answer is no longer applicable.", revision)),
        "Some action answers no longer apply and were retained in superseded history.", warnings,
    )
    # Imported labels never define a question or finding. Current answered labels
    # must match the engine (supporting-action creation has its own known label).
    for question in eligible_address_questions(assessment, review, address):
        if question.id not in address.answers or question.id not in prompts:
            continue
        kind, slot, field_name = _address_id(question.id)
        allowed = {question.prompt}
        if field_name == "action" and slot > 0:
            allowed.add(f"Additional action for the potential {kind.lower()} threat")
        if prompts[question.id] not in allowed:
            raise ProgressError("A saved active Address question label is incompatible with the rules.")
    # Historical labels are inactive data, never interpreted evidence. Preserve
    # their original spelling, including the known supporting-action label.
    address.prompts = {**address.prompts, **prompts}
    active_kinds = {q.id.split(":", 1)[0] for q in eligible_address_questions(assessment, review, address)}
    address.extra_slots = [(kind, slot) for kind, slot in address.extra_slots if kind in active_kinds]
    assessment.revision = revision
    # Rebuild current dependency signatures; imported signatures are never accepted.
    sync_review(assessment, review)
    sync_address(assessment, review, address)
    has_account = bool(
        scenario.strip() or assessment.confirmed or context != Context()
        or assessment.answers or assessment.archive or review.answers or review.archive
        or address.answers or address.archive or address.extra_slots
    )
    if view == "scenario" and has_account:
        # The entry screen's sample loader intentionally starts a new account.
        # Restoring an existing case there would bypass replacement confirmation.
        view = "context"
        warnings.append("The saved entry stage was moved to context review to preserve the existing assessment.")
    elif not assessment.confirmed and view not in {"scenario", "context"}:
        view = "context" if has_account else "scenario"
        warnings.append("The saved stage was moved back to context confirmation.")
    elif next_question(assessment) is not None and view in {"review", "address", "report"}:
        view = "questions"
        warnings.append("The saved stage was moved back to unanswered clarification questions.")
    elif next_review_question(assessment, review) is not None and view in {"address", "report"}:
        view = "review"
        warnings.append("The saved stage was moved back to unanswered evaluation questions.")
    return ProgressSnapshot(assessment, review, address, view, tuple(dict.fromkeys(warnings)))


def import_progress(data: str | bytes) -> ProgressSnapshot:
    """Parse invalid input into a bounded error, never a partial live-session change."""
    try:
        return _import_progress(data)
    except ProgressError:
        raise
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, RecursionError, OverflowError) as error:
        raise ProgressError("Saved progress contains an invalid or incompatible data structure.") from error


def _export_progress(assessment: Assessment, review: ReviewState, address: AddressState, view: str) -> str:
    """Create deterministic JSON from copied state, excluding all derived verdicts."""
    assessment, review, address = deepcopy((assessment, review, address))
    from .intake import sync_intake

    sync_intake(assessment)
    sync_review(assessment, review)
    sync_address(assessment, review, address)
    root = {
        "format": FORMAT_NAME, "schema_version": FORMAT_VERSION, "rules_version": RULES_VERSION,
        "assessment": asdict(assessment),
        "review": {"answers": {id: asdict(answer) for id, answer in review.answers.items()}, "archive": [asdict(record) for record in review.archive]},
        "address": {
            "answers": {id: asdict(answer) for id, answer in address.answers.items()},
            "archive": [asdict(record) for record in address.archive],
            "extra_slots": address.extra_slots, "next_slot": address.next_slot, "prompts": address.prompts,
        },
        "view": view,
    }
    try:
        result = json.dumps(root, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(result.encode("utf-8", errors="strict")) > MAX_PROGRESS_BYTES:
            raise ProgressError("Progress exceeds the 2 MiB size limit; retain a report and reduce unneeded data.")
        # Apply the same safe schema/compatibility checks used on restoration.
        import_progress(result)
        return result
    except ProgressError:
        raise
    except (TypeError, UnicodeError, ValueError, RecursionError, OverflowError) as error:
        raise ProgressError("This session cannot be exported as supported progress JSON.") from error


def export_progress(assessment: Assessment, review: ReviewState, address: AddressState, view: str) -> str:
    """Return only a validated snapshot; malformed live state is not saveable."""
    try:
        return _export_progress(assessment, review, address, view)
    except ProgressError:
        raise
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, UnicodeError, RecursionError, OverflowError) as error:
        raise ProgressError("This session cannot be exported as supported progress JSON.") from error
