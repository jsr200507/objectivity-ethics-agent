"""Concise Objectivity reports from a single current assessment snapshot.

All source records remain attributed user accounts. No report wording upgrades
an action's implementation or effectiveness, and no generated verdict is stored.
"""
from copy import deepcopy
import re

from .case_actions import assess_actions
from .case_model import CaseFact, CaseState, ReasoningSnapshot
from .case_reasoning import ACCEPTABLE, reason_case
from .case_questions import plan_questions
from .case_preliminary import QUESTION_LABELS, preliminary_assessment


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


def _structured_detail(fact: CaseFact) -> str:
    """A bare Yes/No is not intelligible evidence without its meaning."""
    labels = {
        'participation': 'Participation in the relevant work',
        'decision_responsibility': 'Professional involvement',
        'relationship_active': 'Current personal ties relevant to the decision',
        'interest_connection': 'Decision outcome affects the reported interest',
        'commercial_dependence': 'Commercial dependence',
        'work_changed': 'Professional work already changed in response to influence',
        'prior_work_affected': 'Earlier professional work affected',
        **QUESTION_LABELS,
    }
    label = labels.get(fact.predicate)
    return f'{label}: {fact.value}' if label else fact.value


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
        **QUESTION_LABELS,
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
    plan = plan_questions(case, snapshot)
    addressed = assess_actions(case, snapshot)
    facts = {fact.id: fact for fact in _active_facts(case)}
    threat_labels = _threat_labels(case, snapshot)
    evaluation_by_id = {evaluation.threat_id: evaluation for evaluation in snapshot.evaluations}
    residual_by_id = {outcome.threat_id: outcome for outcome in addressed.outcomes}
    action_evaluations = {action.action_id: action for action in addressed.actions}
    acceptable_ids = {outcome.threat_id for outcome in addressed.outcomes if outcome.status == ACCEPTABLE}
    all_acceptable = bool(snapshot.threats) and len(acceptable_ids) == len(snapshot.threats)
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
            speaker = fact.attribution if fact.attribution in {actor.id for actor in case.actors} else fact.subject
            attribution = _label(case, speaker)
            lines += [_escaped(f"{attribution}: {fact.value}") + " — reported claim, not verified evidence.", ""]
    lines += ["## B. Identified potential Objectivity threats", "", "**IDENTIFY — Relevant circumstances and supporting evidence**", ""]
    if not snapshot.threats:
        lines += [
            "No potential threat is supported by the currently recognised source information. Missing or unrecognised information may limit that result; it is not assurance that threats are absent.", "",
        ]
    for threat in snapshot.threats:
        lines += ["### " + _escaped(threat_labels[threat.id]), "", _escaped(threat.mechanism), ""]
        shown_sources = set()
        for fact_id in threat.evidence_ids:
            fact = facts.get(fact_id)
            if fact is None:
                continue
            value = (fact.excerpt or _structured_detail(fact)) if fact.source == 'scenario' else _structured_detail(fact)
            if value in shown_sources:
                continue
            shown_sources.add(value)
            subject = _label(case, fact.subject)
            lines += [f"**{_escaped(subject)} — {_escaped(_fact_status(fact))}:**", "", _quote(value), ""]
            if fact.source != 'scenario' and fact.excerpt and fact.excerpt != value:
                lines += ["Earlier source wording, retained for context rather than confirmation of the correction:", "", _quote(fact.excerpt), ""]
        if threat.uncertainty:
            lines += ["**Remaining uncertainty:**", "", *_paragraphs(threat.uncertainty), ""]
    if snapshot.threats:
        lines += ["These are potential sources of influence, not proof of impaired Objectivity, misconduct or a violation.", ""]
    lines += ["## C. Threat evaluation", "", "**EVALUATE — Preliminary threat significance before safeguards**", "",
        "This is a preliminary assessment of possible influences, not a final residual-acceptability decision.", ""]
    for threat in snapshot.threats:
        evaluation = evaluation_by_id.get(threat.id)
        if evaluation is None:
            lines += [_escaped(threat_labels[threat.id]) + ": evaluation is not established.", ""]
            continue
        preliminary = preliminary_assessment(case, snapshot, threat, plan)
        lines += [f"**{_escaped(threat_labels[threat.id])}: {_escaped(preliminary.significance)}**", "", *_paragraphs(preliminary.factors), ""]
        if preliminary.gaps:
            lines += ["Material information affecting the preliminary evaluation:", "", *_paragraphs(preliminary.gaps), ""]
    if snapshot.interactions:
        lines += ["**Combined influences:**", "", *_paragraphs(snapshot.interactions), ""]
    if not snapshot.threats:
        lines += ["There is no threat-specific significance conclusion on the current record.", ""]
    lines += ["## D. Reasonable and informed third party assessment", "",
        "This applies a hypothetical reasonable and informed third party's perspective to the recorded circumstances. No actual independent third party has reviewed this assessment.", ""]
    for threat in snapshot.threats:
        evaluation = evaluation_by_id.get(threat.id)
        if evaluation:
            # The mechanism and literal evidence are already set out in B;
            # retain the conditional test without repeating the narrative.
            test = preliminary_assessment(case, snapshot, threat, plan).third_party
            lines += [f"**{_escaped(threat_labels[threat.id])}:** {_escaped(test)}", ""]
    lines += ["The effect of existing conditions and recorded actions is reassessed in the residual findings below.", ""]
    lines += ["## E. Actions taken and proposed", "", "**ADDRESS — Existing actions, proposed measures and recommended responses**", ""]
    if acceptable_ids:
        lines += ["**Existing conditions supporting acceptability:**", ""]
        for threat in snapshot.threats:
            if threat.id in acceptable_ids:
                evaluation = evaluation_by_id[threat.id]
                protective = next((item for item in reversed(evaluation.reasoning) if 'no additional safeguard is indicated' in item), '')
                lines += ["**" + _escaped(threat_labels[threat.id]) + ":** " +
                    _escaped(protective or 'The specific circumstances supporting this acceptable-level finding are recorded in C; no additional safeguard is indicated on that basis.') + "", ""]
    if not case.actions:
        if all_acceptable:
            lines += ["No action has been recorded. This assessment relies on the existing circumstances above; it does not imply that an unrecorded safeguard was implemented.", ""]
        else:
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
    outstanding = [threat_labels[threat.id] for threat in snapshot.threats if threat.id not in acceptable_ids]
    if outstanding:
        lines += [_escaped("Further response remains relevant to: " + "; ".join(outstanding)) +
            ". The prioritised next steps in H are recommendations, not completed safeguards unless implementation and outcome evidence are recorded above.", ""]
    lines += ["## F. Safeguard effectiveness", ""]
    for action in case.actions:
        evaluation = action_evaluations.get(action.id)
        if evaluation:
            lines += [f"**{_escaped(action.description)} — {_escaped(evaluation.status)}**", "", *_paragraphs(evaluation.reasoning), ""]
            optional = all_acceptable or bool(action.threat_ids) and all(id in acceptable_ids for id in action.threat_ids)
            if optional:
                lines += ["This action is not relied upon for the acceptable-level finding. Its implementation status does not itself establish effectiveness, and additional safeguard evidence is not required for that finding.", ""]
            if action.evidence_detail.strip():
                lines += ["Reported supporting records:", "", _quote(action.evidence_detail), "",
                    "The records are described by the user; this application has not authenticated them.", ""]
            if evaluation.gaps and not optional:
                lines += ["Evidence or coverage still needed:", "", *_paragraphs(evaluation.gaps), ""]
        else:
            lines += [_escaped(action.description) + ": effectiveness is not established on the current record.", ""]
    if not case.actions:
        if all_acceptable:
            lines += ["No new safeguard's effectiveness is relied upon. The acceptable-level finding rests on the recorded existing conditions, rather than an assumed completed action.", ""]
        else:
            lines += ["No action effectiveness can be established from an unspecified action history.", ""]
    lines += ["Implementation alone does not establish effectiveness. Disclosure, escalation and documentation are not automatically sufficient safeguards. Any supported effectiveness remains conditional on the recorded evidence.", "",
        "## G. Residual threats", ""]
    for threat in snapshot.threats:
        residual = residual_by_id.get(threat.id)
        if residual:
            action_reasons = {item for result in action_evaluations.values() for item in result.reasoning}
            initial_reasons = set(evaluation_by_id[threat.id].reasoning) if threat.id in acceptable_ids else set()
            reasons = [item for item in residual.reasoning if item not in action_reasons | initial_reasons]
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
        # Structured recommendations come first; unresolved action-history
        # checks remain visible after the measures, not as the opening advice.
        for number, recommendation in enumerate(addressed.recommendations, 1):
            lines += [f"### {number}. {_escaped(recommendation.target)}", ""]
            if recommendation.remit:
                lines += [f"**Role and authority context:** {_escaped(recommendation.remit)}", ""]
            lines += [f"**Primary:** {_escaped(recommendation.primary)}", ""]
            if recommendation.context:
                lines += [f"**Case-specific context:** {_escaped(recommendation.context)}", ""]
            lines += [f"**Alternative:** {_escaped(recommendation.alternative)}", "",
                      f"**Supporting evidence:** {_escaped(recommendation.supporting)}", ""]
        other_steps = [step for step in steps if "Primary: " not in step]
        for number, step in enumerate(other_steps, len(addressed.recommendations) + 1):
            lines += [f"{number}. {_escaped(step)}", ""]
    else:
        lines += ["Maintain the recorded protections, reconsider the assessment when material circumstances change, and resolve any limitations before relying on a professional conclusion.", ""]

    lines += ["## I. Overall ethical conclusion and limitations", "", _escaped(addressed.conclusion), ""]
    uncertainties = tuple(dict.fromkeys(
        [_uncertainty_description(case, fact) for fact in facts.values() if fact.status in {"unknown", "disputed"}]
        + ['Step 2 question limit leaves unresolved: ' + question.prompt for question in plan.deferred]
        + list(addressed.unknowns) + list(snapshot.limitations) + list(case.limitations)
    ))
    if uncertainties:
        lines += ["**Remaining limitations and uncertainties:**", "", *_paragraphs(uncertainties), ""]
    if not case.reviewed:
        lines += ["The source account remains awaiting user review; no positive conclusion should rely on unreviewed material assumptions.", ""]
    if case.legacy_records:
        lines += ["Earlier source records and answer history remain available in saved progress. Unmapped historical records are not treated as current evidence or conclusions.", ""]
    lines += [
        "**Scope:** This assessment addresses Objectivity only and supports professional judgment. Ethical findings, safeguard effectiveness and conclusions are determined by the rule-based engine. Optional AI assistance can suggest source information for review or organise approved report wording; it cannot verify facts or issue ethical clearance. This application provides no independent fact verification, professional validation or certified ethical opinion. User confirmation and reported external checking are not verification performed by this application. Separate audit-independence or other professional requirements may require their own assessment.", "",
    ]
    return "\n".join(lines).rstrip() + "\n"
