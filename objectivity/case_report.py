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


def _recommendation_lines(recommendation):
    """Render the same typed fields used by the Step 3 safeguard card."""
    return [
        "**Primary safeguard:** " + _escaped(recommendation.primary), "",
        "**Case-specific application:**", "", *_paragraphs(recommendation.considerations), "",
        "**Alternative safeguard:** " + _escaped(recommendation.alternative), "",
        "**Supporting actions and evidence:**", "",
        *_paragraphs(recommendation.supporting_actions or (recommendation.supporting,)), "",
    ]


def _action_lines(case, action, evaluation, labels, *, previously_shown="", optional=False):
    """Keep implementation, attribution and assessed effectiveness separate."""
    label = "Implemented (reported)" if action.stage == "Implemented" else action.stage
    coverage = "; ".join(labels[id] for id in action.threat_ids if id in labels)
    lines = ["**Action:** " + _escaped(action.description), "",
             f"**Recorded stage:** {_escaped(label)} · **Reported actor:** {_escaped(_label(case, action.actor_id))}", "",
             "**Coverage:** " + _escaped(coverage or "Coverage of current threats needs clarification") + ".", ""]
    if action.stage == "Planned":
        lines += ["This is a proposal, request or work in progress; completed implementation and effectiveness are not established.", ""]
    elif action.stage == "Not Taken":
        lines += ["The user explicitly reports that this relevant action has not been taken.", ""]
    if previously_shown:
        lines += [f"Source and implementation evidence: see {previously_shown}. The coverage and residual position for this threat remain separate.", ""]
    elif action.excerpt:
        lines += ["Reported action source:", "", _quote(action.excerpt), ""]
    if evaluation:
        lines += ["**Effectiveness assessment:** " + _escaped(evaluation.status), ""]
        if not previously_shown:
            lines += [*_paragraphs(evaluation.reasoning), ""]
            if action.evidence_detail.strip():
                lines += ["**Reported supporting records:**", "", _quote(action.evidence_detail), "",
                          "The records are described by the user; this application has not authenticated them.", ""]
        if optional:
            lines += ["This action is not relied upon for the acceptable-level finding. Its status does not establish effectiveness; additional safeguard evidence is not required for that finding.", ""]
        elif evaluation.gaps:
            lines += ["**Implementation or effectiveness evidence still needed:**", "", *_paragraphs(evaluation.gaps), ""]
    else:
        lines += ["**Effectiveness assessment:** Not established on the current record.", ""]
    return lines


def build_case_report(case: CaseState) -> str:
    """Present one snapshot as a three-section, threat-by-threat assessment."""
    from .case_actions import SUPPORTED, UNACCEPTABLE
    from .case_presentation import status_summary

    case = deepcopy(case)
    snapshot = reason_case(case)
    plan = plan_questions(case, snapshot)
    addressed = assess_actions(case, snapshot)
    facts = {fact.id: fact for fact in _active_facts(case)}
    labels = _threat_labels(case, snapshot)
    evaluations = {item.threat_id: item for item in snapshot.evaluations}
    residuals = {item.threat_id: item for item in addressed.outcomes}
    action_results = {item.action_id: item for item in addressed.actions}
    recommendations = {item.threat_id: item for item in getattr(addressed, "recommendations", ())}
    acceptable_ids = {item.threat_id for item in addressed.outcomes if item.status == ACCEPTABLE}
    status = "Conditional assessment" if case.reviewed else "Provisional assessment — account awaiting user review"
    roles = [fact.value for fact in facts.values() if fact.predicate == "role" and fact.status == "reported"]
    # This is an excerpt of the engine's authored conclusion, not a new verdict.
    headline = addressed.conclusion.split(". ", 1)[0].rstrip(".") + "."
    unresolved = [(number, threat) for number, threat in enumerate(snapshot.threats, 1)
                  if threat.id not in residuals or residuals[threat.id].status not in {ACCEPTABLE, SUPPORTED}]
    priority = [(number, threat) for number, threat in unresolved
                if threat.id in residuals and residuals[threat.id].status == UNACCEPTABLE] or unresolved
    concerns = [f"Threat {number:02} — {labels[threat.id]} ({_label(case, threat.subject)})"
                for number, threat in priority[:3]]
    if len(priority) > 3:
        concerns.append(f"{len(priority) - 3} further unresolved sources in Section 2")
    lines = [
        "# Objectivity Ethical Assessment Report", "", "**Objectivity Ethics Assistant**", "",
        f"**Revision:** {case.revision} · **Status:** {_escaped(status)}", "",
        "Reported accounts, not independently verified. Potential threats are not proof of bias, misconduct or a violation.", "",
        "Regenerate this report after material changes; an earlier download does not update automatically.", "",
        "## 1. Executive Summary", "",
        "**Overall position:** " + _escaped(status_summary(addressed, reference="threat assessments")), "",
        *(["**Principal concerns:** " + _escaped("; ".join(concerns)), ""] if concerns else []),
        "**Professional recommendation:** " + _escaped(headline), "",
        *_paragraphs([
            "Professional role: " + "; ".join(dict.fromkeys(roles)) if roles else "Professional role: not established.",
            "Professional activity: " + _decision(case),
            "Recorded parties: " + "; ".join(
                f"{actor.label} ({actor.role})" if actor.role and actor.role.casefold() != actor.label.casefold() else actor.label
                for actor in case.actors
            ) if case.actors else "Relevant parties: not established.",
        ]), "",
        "## 2. Threat-by-Threat Assessment", "",
        "The measures below are recommendations, not completed safeguards. Implementation and effectiveness are assessed separately.", "",
        "The reasonable and informed third-party test is a hypothetical perspective on the reported circumstances, not an actual independent review. Significance before safeguards is preliminary.", "",
    ]
    if not any(fact.predicate == "decision" and fact.status == "reported" for fact in facts.values()):
        lines += ["The professional activity has not been established sufficiently for a complete assessment.", ""]
        if case.scenario.strip():
            excerpt = case.scenario.strip()
            if len(excerpt) > 600:
                excerpt = excerpt[:600].rstrip() + "… [The complete account remains in saved progress.]"
            lines += ["**Reported context requiring clarification:**", "", _quote(excerpt), ""]
    context = [fact for fact in facts.values() if fact.predicate in {"context", "claim"}]
    if context:
        lines += ["**Additional reported context and qualifications:**", ""]
        for fact in context:
            speaker = fact.attribution if fact.attribution in {actor.id for actor in case.actors} else fact.subject
            same_wording = fact.excerpt.strip().rstrip('.').casefold() == fact.value.strip().rstrip('.').casefold()
            value = fact.excerpt if fact.source == "scenario" and same_wording else fact.value
            detail = _label(case, speaker) + ": " + value
            qualification = "reported claim, not verified evidence" if fact.predicate == "claim" else _fact_status(fact)
            lines += ["- " + _escaped(detail) + " — " + _escaped(qualification), ""]
            if fact.excerpt and not same_wording:
                lines += [_quote(fact.excerpt), ""]

    if not snapshot.threats:
        lines += ["No potential threat is supported by the currently recognised source information. Missing or unrecognised information may limit that result; it is not assurance that threats are absent.", "",
                  "There is no threat-specific significance conclusion on the current record. Residual protection cannot be inferred from the absence of a finding.", ""]
    shown_actions = {}
    shown_gaps = set()
    for number, threat in enumerate(snapshot.threats, 1):
        title = f"THREAT {number:02} — " + labels[threat.id]
        evaluation = evaluations.get(threat.id)
        preliminary = preliminary_assessment(case, snapshot, threat, plan)
        residual = residuals.get(threat.id)
        lines += ["### " + _escaped(title), "", "#### A. IDENTIFY", "",
                  "**Source:** " + _escaped(_label(case, threat.subject)), "",
                  _escaped(threat.mechanism), ""]
        shown_sources = set()
        for fid in threat.evidence_ids:
            fact = facts.get(fid)
            if fact is None:
                continue
            value = (fact.excerpt or _structured_detail(fact)) if fact.source == "scenario" else _structured_detail(fact)
            key = (fact.subject, fact.status, value)
            if key in shown_sources:
                continue
            shown_sources.add(key)
            lines += [f"**{_escaped(_label(case, fact.subject))} — {_escaped(_fact_status(fact))}:**", "", _quote(value), ""]
            if fact.source != "scenario" and fact.excerpt and fact.excerpt != value:
                lines += ["Earlier source wording, retained for context rather than confirmation of the correction:", "", _quote(fact.excerpt), ""]
        if threat.uncertainty:
            lines += ["**Identification limitations:**", "", *_paragraphs(threat.uncertainty), ""]
        lines += ["#### B. EVALUATE", "",
                  "**Preliminary significance before safeguards:** " + _escaped(preliminary.significance), "",
                  "**Key reasons:**", "", *_paragraphs(preliminary.factors), ""]
        if preliminary.gaps:
            lines += ["**Material uncertainties and missing evidence:**", "", *_paragraphs(preliminary.gaps), ""]
            shown_gaps.update(preliminary.gaps)
        perspective = preliminary.third_party.removesuffix(
            " This is a provisional, conditional perspective before assessing safeguards; no actual independent third party has reviewed the case.")
        lines += ["**Reasonable and informed third-party assessment:** " + _escaped(perspective), "",
                  "#### C. ADDRESS", "",
                  "**Residual position:** " + _escaped(residual.status if residual else "Acceptability not established"), ""]
        if threat.id in recommendations:
            lines += _recommendation_lines(recommendations[threat.id])
        elif residual and residual.status == ACCEPTABLE:
            lines += ["No additional safeguard is currently indicated on the recorded circumstances. This finding does not rely on an unrecorded action.", ""]
        elif residual and residual.status == SUPPORTED:
            lines += ["The recorded action evidence conditionally supports the response for this threat; maintain the stated protections.", ""]
        else:
            lines += ["A case-specific recommendation is not available in this assessment; retain the unresolved limitation.", ""]

        linked = [action for action in case.actions if threat.id in action.threat_ids]
        lines += ["**Implementation status and effectiveness:**", ""]
        if not linked:
            if residual and residual.status == ACCEPTABLE:
                lines += ["No action has been recorded for this source. The finding rests on existing conditions, not an assumed completed safeguard.", ""]
            else:
                lines += ["The account does not establish what relevant action has already been taken or proposed for this source. This does not mean that no action was taken.", ""]
        for action in linked:
            lines += _action_lines(case, action, action_results.get(action.id), labels,
                                   previously_shown=shown_actions.get(action.id, ""), optional=threat.id in acceptable_ids)
            shown_actions.setdefault(action.id, f"Threat {number:02}")
        if residual:
            linked_reasons = {text for action in linked for text in getattr(action_results.get(action.id), "reasoning", ())}
            initial = set(evaluation.reasoning) if evaluation and threat.id in acceptable_ids else set()
            reasons = [text for text in residual.reasoning if text not in linked_reasons | initial]
            if reasons:
                lines += ["**Basis of the residual assessment:**", "", *_paragraphs(reasons), ""]
            if residual.unknowns:
                lines += ["**Outstanding concerns:**", "", *_paragraphs(residual.unknowns), ""]
                shown_gaps.update(residual.unknowns)
            lines += ["**Third-party perspective after recorded measures:** " + _escaped(residual.third_party), ""]

    unlinked = [action for action in case.actions if action.id not in shown_actions]
    if unlinked:
        lines += ["### Action records awaiting current threat coverage", "",
                  "These records are retained without assuming coverage of an identified threat.", ""]
        for action in unlinked:
            lines += _action_lines(case, action, action_results.get(action.id), labels)
    if snapshot.interactions:
        lines += ["### Combined influences", "", *_paragraphs(snapshot.interactions), ""]

    lines += ["## 3. Overall Conclusion", "", _escaped(addressed.conclusion), ""]
    if unresolved:
        lines += ["**Unresolved threat positions:**", "",
                  *_paragraphs(f"Threat {number:02} — {labels[threat.id]}" for number, threat in unresolved), "",
                  "Apply the primary or feasible alternative measures in those threat assessments; establish their implementation and effect before relying on protection.", ""]
    effective = [action.description for action in addressed.actions if action.effective]
    lines += ["**Actions assessed as effective:**", ""]
    lines += [*_paragraphs(effective), ""] if effective else ["No recorded action is assessed as effective on the current evidence.", ""]
    follow_ups = getattr(addressed, "follow_up_steps", ()) if recommendations else addressed.next_steps
    if follow_ups:
        lines += ["**Further actions and conditions:**", "", *_paragraphs(follow_ups), ""]
    uncertainties = tuple(dict.fromkeys(
        [_uncertainty_description(case, fact) for fact in facts.values() if fact.status in {"unknown", "disputed"}]
        + ["Step 2 question limit leaves unresolved: " + question.prompt for question in plan.deferred]
        + list(addressed.unknowns) + list(snapshot.limitations) + list(case.limitations)
    ))
    remaining = [text for text in uncertainties if text not in shown_gaps]
    if remaining:
        lines += ["**Other uncertainties and limitations:**", "", *_paragraphs(remaining), ""]
    if not case.reviewed:
        lines += ["The source account remains awaiting user review; no positive conclusion should rely on unreviewed material assumptions.", ""]
    if case.legacy_records:
        lines += ["Earlier source records and answer history remain in saved progress. Unmapped historical records are not current evidence or conclusions.", ""]
    lines += [
        "**Scope:** Objectivity only; this assessment supports professional judgment. This application provides no independent fact verification, professional validation or certified ethical opinion. User confirmation and reported external checking are not verification performed by this application. Optional AI assistance cannot change the rule-based ethical findings or verify facts. Separate audit-independence and other applicable professional requirements need their own assessment.", "",
    ]
    return "\n".join(lines).rstrip() + "\n"
