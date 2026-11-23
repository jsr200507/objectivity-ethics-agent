"""Concise Objectivity reports from a single current assessment snapshot.

All source records remain attributed user accounts. No report wording upgrades
an action's implementation or effectiveness, and no generated verdict is stored.
"""
from copy import deepcopy
import re

from .case_actions import assess_actions
from .case_model import CaseFact, CaseState, ReasoningSnapshot
from .case_reasoning import reason_case


_SOURCE_WORDING = {
    "scenario": "Reported scenario", "user": "Recorded user account", "legacy": "Retained earlier account",
}
_REFERENCE = re.compile(r"\b(?:answer|review|context)\.([A-Za-z_][A-Za-z0-9_]*)\b")


def _natural(text: str) -> str:
    """Never expose old engine provenance keys as professional report wording."""
    return _REFERENCE.sub(lambda match: match[1].replace("_", " "), str(text))


def _escaped(text: str) -> str:
    text = _natural(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_{}\[\]()#+.!|~\-])", r"\\\1", text)


def _quote(text: str) -> str:
    return "\n".join("> " + _escaped(line) for line in text.splitlines()) if text else "> Not supplied."


def _paragraphs(items) -> list[str]:
    return ["- " + _escaped(item) for item in dict.fromkeys(item for item in items if item)]


def _label(case: CaseState, actor_id: str) -> str:
    actor = next((actor for actor in case.actors if actor.id == actor_id), None)
    return actor.label if actor else "An unspecified party"


def _active_facts(case: CaseState) -> tuple[CaseFact, ...]:
    return tuple(fact for fact in case.facts if fact.status != "withdrawn")


def _decision(case: CaseState, decision_id: str = "decision") -> str:
    decisions = [fact.value for fact in _active_facts(case)
                 if fact.predicate == "decision" and fact.decision_id == decision_id and fact.status == "reported"]
    return "; ".join(dict.fromkeys(decisions)) or "the professional decision under review"


def _threat_labels(case: CaseState, snapshot: ReasoningSnapshot) -> dict[str, str]:
    labels = {}
    kinds = [threat.kind for threat in snapshot.threats]
    seen = {}
    for threat in snapshot.threats:
        seen[threat.kind] = seen.get(threat.kind, 0) + 1
        # Same-category sources remain distinct without displaying internal IDs.
        suffix = f" — source {seen[threat.kind]}" if kinds.count(threat.kind) > 1 else ""
        labels[threat.id] = threat.kind + suffix
    return labels


def _fact_status(fact: CaseFact) -> str:
    if fact.status == "unknown":
        return "Explicitly unknown in the recorded account"
    if fact.status == "disputed":
        return "Disputed or conflicting account"
    if fact.status == "denied":
        return "An explicit absence or denial is reported"
    if fact.predicate == "claim":
        return "Reported claim; its underlying truth is not established"
    review = "; acknowledged by the user" if fact.reviewed else "; awaiting user review"
    return _SOURCE_WORDING.get(fact.source, "Recorded account") + review + "; not independently verified"


def _uncertainty_description(case: CaseState, fact: CaseFact) -> str:
    actor = _label(case, fact.subject)
    labels = {
        "role": "The professional role", "decision": "The professional decision",
        "participation": f"{actor}'s participation in the relevant work",
        "decision_responsibility": f"{actor}'s decision-making responsibility",
        "relationship_active": f"Current personal ties involving {actor}",
        "interest_connection": f"The connection of {actor}'s interest to the decision",
        "commercial_dependence": f"{actor}'s commercial dependence",
        "work_changed": "Whether the professional work changed in response to influence",
        "prior_work_affected": "Whether earlier professional work was affected",
    }
    subject = labels.get(fact.predicate, f"Information concerning {actor}")
    if fact.status == "disputed":
        return f"{subject} is disputed: {fact.value}"
    if fact.value.strip().casefold() not in {"unknown", "not known", ""}:
        return f"{subject} remains uncertain: {fact.value}"
    return subject + " remains unknown."


def build_case_report(case: CaseState) -> str:
    """Recompute nine professional sections; do not mutate or trust old conclusions."""
    case = deepcopy(case)
    snapshot = reason_case(case)
    addressed = assess_actions(case, snapshot)
    facts = {fact.id: fact for fact in _active_facts(case)}
    threat_labels = _threat_labels(case, snapshot)
    evaluation_by_id = {evaluation.threat_id: evaluation for evaluation in snapshot.evaluations}
    residual_by_id = {outcome.threat_id: outcome for outcome in addressed.outcomes}
    action_evaluations = {action.action_id: action for action in addressed.actions}
    status = "Conditional assessment" if case.reviewed else "Provisional assessment — account awaiting user review"
    lines = [
        "# Objectivity Ethical Assessment Report", "", "**Objectivity Ethics Assistant**", "",
        f"**Revision:** {case.revision} · **Status:** {_escaped(status)}", "",
        "This report reflects the current recorded account. Regenerate it after material changes; an earlier download does not update automatically.", "",
        "Source accounts are not independently verified by this application.", "",
        "## A. Scenario summary", "",
    ]
    roles = [fact for fact in facts.values() if fact.predicate == "role" and fact.status == "reported"]
    if roles:
        lines += [_escaped("Professional role: " + "; ".join(dict.fromkeys(fact.value for fact in roles))) + ".", ""]
    lines += [_escaped("Professional activity: " + _decision(case)) + ".", ""]
    if case.actors:
        actors = []
        for actor in case.actors:
            if actor.role and actor.role.casefold() != actor.label.casefold():
                actors.append(f"{actor.label} ({actor.role})")
            else:
                actors.append(actor.label)
        lines += [_escaped("Recorded parties: " + "; ".join(dict.fromkeys(actors))) + ".", ""]
    if not any(fact.predicate == "decision" and fact.status == "reported" for fact in facts.values()):
        lines += ["The professional activity has not been established sufficiently for a complete assessment.", ""]
        if case.scenario.strip():
            excerpt = case.scenario.strip()
            if len(excerpt) > 600:
                excerpt = excerpt[:600].rstrip() + "… [The complete account remains in saved progress.]"
            lines += ["**Reported context requiring clarification:**", "", _quote(excerpt), ""]
    # Assertions such as anticipated recovery must stay attributed claims.
    claims = [fact for fact in facts.values() if fact.predicate == "claim"]
    if claims:
        lines += ["**Claims distinct from established circumstances:**", ""]
        for fact in claims:
            attribution = _label(case, fact.attribution or fact.subject)
            lines += [_escaped(f"{attribution}: {fact.value}") + " — reported claim, not verified evidence.", ""]
    lines += ["## B. Identified potential Objectivity threats", ""]
    if not snapshot.threats:
        lines += [
            "No potential threat is supported by the currently recognised source information. Missing or unrecognised information may limit that result; it is not assurance that threats are absent.", "",
        ]
    for threat in snapshot.threats:
        lines += ["### " + _escaped(threat_labels[threat.id]), "", _escaped(threat.mechanism), ""]
        for fact_id in threat.evidence_ids:
            fact = facts.get(fact_id)
            if fact is None:
                continue
            value = (fact.excerpt or fact.value) if fact.source == 'scenario' else fact.value
            subject = _label(case, fact.subject)
            lines += [f"**{_escaped(subject)} — {_escaped(_fact_status(fact))}:**", "", _quote(value), ""]
            if fact.source != 'scenario' and fact.excerpt and fact.excerpt != value:
                lines += ["Earlier source wording, retained for context rather than confirmation of the correction:", "", _quote(fact.excerpt), ""]
        if threat.uncertainty:
            lines += ["**Remaining uncertainty:**", "", *_paragraphs(threat.uncertainty), ""]
    if snapshot.threats:
        lines += ["These are potential sources of influence, not proof of impaired Objectivity, misconduct or a violation.", ""]
    lines += ["## C. Threat evaluation", ""]
    for threat in snapshot.threats:
        evaluation = evaluation_by_id.get(threat.id)
        if evaluation is None:
            lines += [_escaped(threat_labels[threat.id]) + ": evaluation is not established.", ""]
            continue
        reasons = [item for item in evaluation.reasoning if item != threat.mechanism]
        lines += [f"**{_escaped(threat_labels[threat.id])}: {_escaped(evaluation.outcome)}**", "", *_paragraphs(reasons), ""]
        if evaluation.material_gaps:
            lines += ["Material information affecting the initial evaluation:", "", *_paragraphs(evaluation.material_gaps), ""]
    if snapshot.interactions:
        lines += ["**Combined influences:**", "", *_paragraphs(snapshot.interactions), ""]
    if not snapshot.threats:
        lines += ["There is no threat-specific acceptability conclusion on the current record.", ""]
    lines += ["## D. Reasonable and informed third party assessment", "",
        "This applies a hypothetical reasonable and informed third party's perspective to the recorded circumstances. No actual independent third party has reviewed this assessment.", ""]
    for threat in snapshot.threats:
        evaluation = evaluation_by_id.get(threat.id)
        if evaluation:
            # The mechanism and literal evidence are already set out in B;
            # retain the conditional test without repeating the narrative.
            test = evaluation.third_party.replace(threat.mechanism + ' ', '')
            lines += [f"**{_escaped(threat_labels[threat.id])}:** {_escaped(test)}", ""]
    if addressed.third_party:
        lines += ["**After considering recorded actions:** " + _escaped(addressed.third_party), ""]
    lines += ["## E. Actions taken and proposed", ""]
    if not case.actions:
        lines += [
            "The account does not establish what relevant action has already been taken or proposed. This does not mean that no action was taken.", "",
        ]
    for action in case.actions:
        label = "Implemented (reported)" if action.stage == "Implemented" else action.stage
        linked = [threat_labels[id] for id in action.threat_ids if id in threat_labels]
        coverage = "; ".join(linked) or "Coverage of current threats needs clarification"
        lines += ["### " + _escaped(action.description), "",
            f"**Recorded stage:** {_escaped(label)}. **Coverage:** {_escaped(coverage)}.", ""]
        if action.excerpt:
            lines += ["Reported source:", "", _quote(action.excerpt), ""]
        if action.stage == "Planned":
            lines += ["This is a proposal, request or work in progress; completed implementation and effectiveness are not established.", ""]
        if action.stage == "Not Taken":
            lines += ["The user explicitly reports that this relevant action has not been taken.", ""]
    lines += ["## F. Safeguard effectiveness", ""]
    for action in case.actions:
        evaluation = action_evaluations.get(action.id)
        if evaluation:
            lines += [f"**{_escaped(action.description)} — {_escaped(evaluation.status)}**", "", *_paragraphs(evaluation.reasoning), ""]
            if action.evidence_detail.strip():
                lines += ["Reported supporting records:", "", _quote(action.evidence_detail), "",
                    "The records are described by the user; this application has not authenticated them.", ""]
            if evaluation.gaps:
                lines += ["Evidence or coverage still needed:", "", *_paragraphs(evaluation.gaps), ""]
        else:
            lines += [_escaped(action.description) + ": effectiveness is not established on the current record.", ""]
    if not case.actions:
        lines += ["No action effectiveness can be established from an unspecified action history.", ""]
    lines += ["Implementation alone does not establish effectiveness. Disclosure, escalation and documentation are not automatically sufficient safeguards. Any supported effectiveness remains conditional on the recorded evidence.", "",
        "## G. Residual threats", ""]
    for threat in snapshot.threats:
        residual = residual_by_id.get(threat.id)
        if residual:
            action_reasons = {item for result in action_evaluations.values() for item in result.reasoning}
            reasons = [item for item in residual.reasoning if item not in action_reasons]
            lines += [f"**{_escaped(threat_labels[threat.id])}: {_escaped(residual.status)}**", "", *_paragraphs(reasons), ""]
            if residual.unknowns:
                lines += ["Unresolved information:", "", *_paragraphs(residual.unknowns), ""]
        else:
            lines += [_escaped(threat_labels[threat.id]) + ": residual acceptability is not established.", ""]
    if not snapshot.threats:
        lines += ["Residual protection cannot be inferred merely from the absence of a supported threat finding.", ""]
    lines += ["## H. Prioritised next steps", ""]
    steps = tuple(dict.fromkeys(step for step in addressed.next_steps if step))
    if steps:
        lines += [f"{number}. {_escaped(step)}" for number, step in enumerate(steps, 1)] + [""]
    else:
        lines += ["Maintain the recorded protections, reconsider the assessment when material circumstances change, and resolve any limitations before relying on a professional conclusion.", ""]
    lines += ["## I. Overall ethical conclusion and limitations", "", _escaped(addressed.conclusion), ""]
    uncertainties = tuple(dict.fromkeys(
        [_uncertainty_description(case, fact) for fact in facts.values() if fact.status in {"unknown", "disputed"}]
        + list(addressed.unknowns) + list(snapshot.limitations) + list(case.limitations)
    ))
    if uncertainties:
        lines += ["**Remaining limitations and uncertainties:**", "", *_paragraphs(uncertainties), ""]
    if not case.reviewed:
        lines += ["The source account remains awaiting user review; no positive conclusion should rely on unreviewed material assumptions.", ""]
    if case.legacy_records:
        lines += ["Earlier source records and answer history remain available in saved progress. Unmapped historical records are not treated as current evidence or conclusions.", ""]
    lines += [
        "**Scope:** This rule-based assistant addresses Objectivity only and supports professional judgment. It provides no generative AI, independent fact verification, professional validation or certified ethical opinion. User confirmation and reported external checking are not verification performed by this application. Separate audit-independence or other professional requirements may require their own assessment.", "",
    ]
    return "\n".join(lines).rstrip() + "\n"
