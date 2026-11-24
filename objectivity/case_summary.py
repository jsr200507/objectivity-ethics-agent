"""Concise presentation of the recorded account before ethical evaluation.

This is a projection of source records, not another extraction or reasoning
engine. Detailed values, provenance and history stay in the case ledger.
"""
from dataclasses import dataclass
import re

from .case_model import CaseFact, CaseState, ReasoningSnapshot
from .understanding import _authority_kind, _valuation_provider_ids


@dataclass(frozen=True)
class SummarySection:
    title: str
    items: tuple[str, ...]
    uncertain: bool = False


_MAX_ITEMS = 4
_MAX_DETAIL = 240
_UNCERTAINTY_LABELS = {
    "role": "Your professional role",
    "decision": "The professional decision or activity",
    "decision_responsibility": "Your responsibility for the decision",
    "participation": "Participation in the relevant work",
    "relationship_active": "The current relevance of personal ties",
    "interest_connection": "The connection between the interest and this decision",
    "commercial_dependence": "The extent of commercial dependence",
    "work_changed": "Whether work has already changed in response to influence",
    "prior_work_affected": "Whether earlier work was affected",
}


def _compact(text: str, limit: int = _MAX_DETAIL) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _items(values) -> tuple[str, ...]:
    unique = tuple(dict.fromkeys(_compact(value) for value in values if value))
    if len(unique) <= _MAX_ITEMS:
        return unique
    return unique[:_MAX_ITEMS] + (
        f"{len(unique) - _MAX_ITEMS} further reported details are available in detailed review.",
    )


def _label(case: CaseState, actor_id: str) -> str:
    return next((actor.label for actor in case.actors if actor.id == actor_id), "Party not established")


def _described(fact: CaseFact, detail: str | None = None) -> str:
    detail = _compact(fact.value if detail is None else detail)
    if fact.status == "unknown":
        return "Not known" if detail.casefold() in {"unknown", "not known", ""} else detail + " (uncertain)"
    if fact.status == "disputed":
        return detail + " (disputed account)"
    if fact.status == "denied":
        return detail + " (explicitly denied)"
    return detail


def _pressure_detail(fact: CaseFact) -> str:
    # Only omit a repeated introductory clause. The retained wording is still
    # the user's recorded pressure, never a newly inferred threat or consequence.
    text = fact.value
    verb = re.search(r"\b(?:has\s+asked|asks?|asked|says?|said|warns?|warned|tells?|told|instructs?|instructed|threatens?|threatened|claims?|believes?|reports?|denies|denied)\b", text, re.I)
    if verb and not re.search(r"\b(?:not|never|no|without|unclear|whether|might|could|alleged|allegedly|disputed)\b", text[:verb.start()], re.I):
        text = text[verb.start():]
    return _described(fact, text)


def summarise_case(case: CaseState, snapshot: ReasoningSnapshot | None = None) -> tuple[SummarySection, ...]:
    """Return six bounded, editable-summary sections without mutating sources.

    Review of these suggestions confirms the account, not the truth of events.
    No source excerpts, source IDs, answer keys or verification claims are added.
    """
    if snapshot is None:
        from .case_reasoning import reason_case
        snapshot = reason_case(case)
    facts = [fact for fact in case.facts if fact.status != "withdrawn"]
    grouped = {predicate: [fact for fact in facts if fact.predicate == predicate]
               for predicate in {fact.predicate for fact in facts}}

    role = grouped.get("role", [])
    decision = grouped.get("decision", [])
    professional = ["Role: " + _described(fact) for fact in role]
    professional += ["Decision: " + _described(fact, fact.value.split(";", 1)[0]) for fact in decision]
    if not role:
        professional.append("Professional role not yet established.")
    if not decision:
        professional.append("Professional decision not yet established.")
    restrictions = []
    for fact in grouped.get('context', []):
        authority = _authority_kind(fact.value)
        if not authority:
            continue
        label, absent = authority
        detail = f'{_label(case, fact.subject)} — {label}'
        if absent and fact.status == 'reported':
            detail += ' explicitly not held (reported)'
        elif fact.status == 'reported':
            detail += ' (reported)'
        detail += ': ' + _described(fact)
        (restrictions if absent else professional).append(detail)
    # Material restrictions remain visible even when ordinary context reaches
    # the normal item cap. Their polarity is stated before compacted detail.
    professional_items = tuple(dict.fromkeys(_compact(item) for item in restrictions)) + _items(professional)

    party_names = [_compact(actor.label, 80) for actor in case.actors if actor.id != "user"]
    people = ["Relevant parties: " + "; ".join(party_names)] if party_names else []
    for fact in facts:
        if fact.predicate in {"close_relationship", "family_relationship", "professional_relationship"}:
            target = " with " + _label(case, fact.object_id) if fact.object_id else ""
            people.append(f"{_label(case, fact.subject)}{target}: {_described(fact)}")
        elif fact.predicate == "employment":
            target = " at " + _label(case, fact.object_id) if fact.object_id else ""
            people.append(f"{_label(case, fact.subject)}{target}: {_described(fact)}")
    if not people:
        people.append("Relevant parties or relationships have not yet been established.")
    valuation_work = any(re.search(r'\bvaluations?\b', fact.value, re.I)
                         for fact in decision if fact.status == 'reported')
    provider_links = [f for f in grouped.get('professional_relationship', []) if f.status == 'reported' and f.object_id]
    recorded_providers = any(
        f.subject in _valuation_provider_ids(f.value, {a.id: a for a in case.actors})
        for f in grouped.get('claim', []) if f.status == 'reported'
    )
    if valuation_work and not provider_links and not recorded_providers:
        people.append('Valuation provider not identified in the account.')

    interests = [f"{_label(case, fact.subject)}: {_described(fact)}" for fact in grouped.get("interest", [])]
    # A reported promotion/job consequence need not imply a financial benefit.
    career_terms = set()
    for fact in grouped.get("pressure", []):
        if fact.status not in {"reported", "disputed"}:
            continue
        for match in re.finditer(r"\b(?:promotion|career|job\s+security|dismissal|demotion)\b", fact.value, re.I):
            career_terms.add(match.group().lower())
    if career_terms:
        interests.append("Career-related influence mentioned: " + ", ".join(sorted(career_terms)) + ". See the reported pressure below; a financial benefit is not assumed.")
    if not interests:
        interests.append("No financial, commercial or career interest is established in the recognised information; this does not establish that none exists.")

    pressure = [f"{_label(case, fact.subject)}: {_pressure_detail(fact)}" for fact in grouped.get("pressure", [])]
    if not pressure:
        pressure.append("No specific pressure is established in the recognised information; review any missing influence.")

    uncertainties = []
    if not role:
        uncertainties.append("Your professional role has not been captured.")
    if not decision:
        uncertainties.append("The professional decision or activity has not been captured.")
    for fact in facts:
        if fact.status in {"unknown", "disputed"}:
            title = _UNCERTAINTY_LABELS.get(fact.predicate, "Information concerning " + _label(case, fact.subject))
            party = " — " + _label(case, fact.subject) if fact.subject != "user" else ""
            state = " is disputed." if fact.status == "disputed" else " remains unknown."
            uncertainties.append(title + party + state)
    for question in snapshot.questions:
        title = _UNCERTAINTY_LABELS.get(question.predicate, "Relevant professional context")
        party = " — " + _label(case, question.subject) if question.subject != "user" else ""
        uncertainties.append(title + party + " needs clarification.")
    for fact in grouped.get("claim", []):
        uncertainties.append(f"{_label(case, fact.subject)}'s claim remains unverified: {_described(fact)}")
    if not uncertainties:
        uncertainties.append("No further material clarification is currently identified by these local rules. The account is not independently verified.")

    actions = []
    stages = {
        "Unknown": "implementation not established",
        "Not Taken": "reported as not taken",
        "Planned": "planned or requested; not completed",
        "Implemented": "implemented according to the account; effectiveness requires assessment",
    }
    for action in case.actions:
        actions.append(f"{_label(case, action.actor_id)}: {_compact(action.description, 150)} — {stages.get(action.stage, 'status not established')}")
    if not actions:
        actions.append("No steps to address the Objectivity concern were mentioned; this does not establish that none have been taken.")

    return (
        SummarySection("Professional role and decision", professional_items, not role or not decision or any(f.status in {"unknown", "disputed"} for f in (*role, *decision))),
        SummarySection("People and relationships", _items(people), not party_names),
        SummarySection("Financial, commercial and career interests", _items(interests), any(f.status in {"unknown", "disputed"} for f in grouped.get("interest", []))),
        SummarySection("Reported pressure or influence", _items(pressure), any(f.status in {"unknown", "disputed"} for f in grouped.get("pressure", []))),
        SummarySection("Material uncertainties", _items(uncertainties), bool(snapshot.questions) or any(f.status in {"unknown", "disputed"} for f in facts) or not role or not decision or bool(grouped.get("claim"))),
        SummarySection("Actions already mentioned", _items(actions), any(a.stage == "Unknown" for a in case.actions)),
    )
