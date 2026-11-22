"""Evidence-linked local suggestions for editable, unconfirmed context.

Mention grammars and conditional rules recognise explicit English wording. They
neither verify the account nor infer ethical findings from an unrestricted story.
"""

from dataclasses import dataclass

from .extraction_entities import extract_entities
from .extraction_signals import extract_signals
from .models import Context


MAX_SCENARIO_LENGTH = 100_000
_FIELDS = ("role", "parties", "decision", "relationship", "interests", "pressure")


@dataclass(frozen=True)
class ExtractionResult:
    context: Context
    evidence: dict[str, tuple[str, ...]]
    limitations: tuple[str, ...]


def extract_context(scenario: str) -> ExtractionResult:
    """Suggest supported context; confirmation remains an explicit UI operation."""
    if not isinstance(scenario, str):
        raise TypeError("Scenario must be text.")
    if len(scenario) > MAX_SCENARIO_LENGTH:
        return ExtractionResult(
            Context(role="Unknown", parties="Unknown", decision="Unknown"),
            {field: () for field in _FIELDS},
            ("The scenario exceeds the local extraction length limit. Complete the editable fields manually.",),
        )
    entities = extract_entities(scenario)
    signals = extract_signals(scenario, user_role=entities.role)
    context = Context(
        role=entities.role, parties=entities.parties, decision=entities.decision,
        relationship=signals.relationship, relationship_notes=signals.relationship_notes,
        interests=signals.interests, interests_notes=signals.interests_notes,
        pressure=signals.pressure, pressure_notes=signals.pressure_notes,
    )
    evidence = {
        field: tuple(dict.fromkeys((*entities.evidence.get(field, ()), *signals.evidence.get(field, ()))))
        for field in _FIELDS
    }
    limitations = tuple(dict.fromkeys((
        "Suggestions reflect scenario wording and are not independently verified. Review and confirm every field.",
        "Local English rules can miss paraphrases, attribution and context; Unknown means the rules could not establish a reliable suggestion.",
        *entities.limitations, *signals.limitations,
    )))
    return ExtractionResult(context, evidence, limitations)
