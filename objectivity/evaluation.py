"""Authored, deterministic Objectivity reasoning; not a professional opinion.

The ACCA/IESBA conceptual-framework sequence is Identify, Evaluate, Address.
This module implements provisional identification and evaluation only. Rule IDs
identify our implementation, not paragraphs of a professional standard. No text
inference, independent verification, safeguard conclusions or numerical scores
are performed here.
"""

from dataclasses import dataclass

from .models import Answer, Assessment
from .questions import QUESTION_BANK, eligible_questions


INSUFFICIENT = "Insufficient information"
POTENTIAL = "Potential threat requiring evaluation"
ACTION = "Threat requiring action before proceeding"
INVOLVED = {"I make or recommend the decision", "I supervise or review the work"}
NO_INVOLVEMENT = "I have no involvement in this decision"
UNRESOLVED = {None, "Unknown", "Other", "Not applicable"}
RESPONSIBILITY_OPTIONS = INVOLVED | {NO_INVOLVEMENT, "Unknown", "Other", "Not applicable"}
UNSUPPORTED_BASES = {
    "Confidence in my own impartiality": (
        "Confidence in impartiality is not evidence that the circumstances no longer affect judgment."
    ),
    "Disclosure of the circumstances": (
        "Disclosure makes circumstances known; it does not, by itself, remove their influence on judgment."
    ),
    "Documentation of the circumstances": (
        "Documentation records circumstances; it does not, by itself, remove their influence on judgment."
    ),
    "A proposed safeguard": (
        "A proposed safeguard has not been shown effective merely by being proposed. "
        "This phase does not assess safeguard sufficiency."
    ),
}


@dataclass(frozen=True)
class Evidence:
    source: str
    label: str
    value: str
    status: str


@dataclass(frozen=True)
class Finding:
    kind: str
    outcome: str
    rule_id: str
    summary: str
    evidence: tuple[Evidence, ...]
    reasoning: tuple[str, ...]
    unknowns: tuple[str, ...]


@dataclass(frozen=True)
class Evaluation:
    revision: int
    findings: tuple[Finding, ...]
    unknowns: tuple[str, ...]
    interactions: tuple[str, ...]
    third_party: str
    limitations: tuple[str, ...]


def _current_answers(assessment: Assessment) -> dict[str, Answer]:
    """Archived, inapplicable and invalid answers cannot drive reasoning."""
    return {
        question.id: assessment.answers[question.id]
        for question in eligible_questions(assessment)
        if question.id in assessment.answers
        and assessment.answers[question.id].choice in question.options
    }


def effective_responsibility(
    assessment: Assessment, review_answers: dict[str, Answer] | None = None
) -> str | None:
    """Reuse a relevant Phase 1 answer before asking the same question again."""
    if not assessment.confirmed:
        return None
    answer = _current_answers(assessment).get("relationship_influence")
    if answer is None:
        answer = (review_answers or {}).get("decision_responsibility")
    return answer.choice if answer and answer.choice in RESPONSIBILITY_OPTIONS else None


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def evaluate(
    assessment: Assessment, review_answers: dict[str, Answer] | None = None
) -> Evaluation:
    """Recompute conditional findings exclusively from current structured choices.

    No conclusion is cached in session state. An edit therefore cannot leave an
    obsolete finding active. Narratives and explanations are deliberately unused.
    """
    review_answers = review_answers or {}
    answers = _current_answers(assessment)
    choice = lambda name: answers[name].choice if name in answers else None
    context = assessment.context
    role = effective_responsibility(assessment, review_answers)
    involved = role in INVOLVED
    role_conflict = role == NO_INVOLVEMENT and choice("pressure_effect") == "Yes"
    no_involvement = role == NO_INVOLVEMENT and not role_conflict
    findings: list[Finding] = []
    unknowns: list[str] = []

    def evidence(*sources: str) -> tuple[Evidence, ...]:
        result = []
        for source in sources:
            category, name = source.split(".", 1)
            if category == "context":
                label = {"relationship": "Relationship", "interests": "Interests", "pressure": "Reported pressure"}[name]
                result.append(Evidence(source, label, getattr(context, name), "User-confirmed account; not independently verified"))
            elif category == "answer" and name in answers:
                result.append(Evidence(source, QUESTION_BANK[name].prompt, answers[name].choice, "Recorded user answer; not independently verified"))
            elif category == "review" and name in review_answers:
                label = {
                    "decision_responsibility": "Decision-making responsibility",
                    "objectivity_basis": "Basis for believing threats are addressed",
                    "basis_challenge": "Response to the assumption challenge",
                }[name]
                result.append(Evidence(source, label, review_answers[name].choice, "Recorded user answer; not independently verified"))
        return tuple(result)

    role_source = (
        "answer.relationship_influence"
        if "relationship_influence" in answers
        else "review.decision_responsibility"
    )
    role_conflict_gap = (
        "Decision responsibility conflicts with a reported change to work under pressure; "
        "reconcile these accounts before relying on the responsibility assessment "
        f"({role_source}; answer.pressure_effect)."
    )
    assumption = review_answers.get("objectivity_basis")
    assumption_reason = UNSUPPORTED_BASES.get(assumption.choice) if assumption else None

    def add(kind, outcome, rule_id, summary, sources, reasons, gaps):
        if assumption_reason:
            reasons.append(assumption_reason)
            reasons.append(
                "An explanation or assertion of a change is retained as the user's account, "
                "not accepted as proof that a threat is addressed; update the structured facts where relevant."
            )
            sources.extend(("review.objectivity_basis", "review.basis_challenge"))
        findings.append(Finding(kind, outcome, rule_id, summary, evidence(*sources), tuple(reasons), _unique(gaps)))
        unknowns.extend(gaps)

    def role_gap(gaps):
        if role_conflict:
            gaps.append(role_conflict_gap)
        elif role in UNRESOLVED:
            gaps.append(f"Decision-making responsibility is unresolved ({role_source}).")

    if not assessment.confirmed:
        unknowns.append("The structured context has not been confirmed; no threat finding is made.")
    else:
        if role_conflict:
            unknowns.append(role_conflict_gap)
        # Familiarity: a personal connection alone does not prove biased work.
        relationship_relevant = context.relationship == "Close personal relationship" or (
            context.relationship in {"Unknown", "Other"}
            and choice("relationship_relevance") == "Possibly relevant"
        )
        contact, ties = choice("relationship_contact"), choice("relationship_ties")
        historical_only = contact == "Little or no current personal contact" and ties == "No"
        active = contact in {"Frequent personal contact", "Occasional personal contact"} or ties == "Yes"
        if relationship_relevant:
            if historical_only:
                unknowns.append(
                    "Little or no current contact and no continuing ties are reported; "
                    "current relevance of the relationship is not established. Reconcile this "
                    "with any close-relationship context before drawing a broader conclusion."
                )
            elif no_involvement:
                unknowns.append(
                    "No involvement in this decision is reported (decision responsibility); "
                    "a link between the relationship and the user's judgment is not established."
                )
            elif active or context.relationship == "Close personal relationship":
                gaps = []
                role_gap(gaps)
                if contact in UNRESOLVED:
                    gaps.append("The extent of current personal contact is unresolved (answer.relationship_contact).")
                if contact == "Little or no current personal contact" and ties in UNRESOLVED:
                    gaps.append("Continuing personal ties or obligations are unresolved (answer.relationship_ties).")
                outcome = INSUFFICIENT if role_conflict else ACTION if active and involved and context.relationship == "Close personal relationship" else POTENTIAL
                reasons = [
                    "A close or continuing personal relationship can create excessive sympathy "
                    "or acceptance of another person's interests, affecting objective judgment.",
                    "The reported relationship is a potential source of influence, not proof of actual bias or misconduct.",
                ]
                if active and involved:
                    reasons.append("Current personal ties intersect with reported decision-making or review responsibility.")
                if outcome == ACTION:
                    reasons.append("On this account, the close active relationship and decision responsibility require the threat to be addressed before proceeding; no response has been assessed as sufficient.")
                add("Familiarity", outcome, "FAM-01", "The reported personal relationship may affect objective judgment.",
                    ["context.relationship", "answer.relationship_relevance", "answer.relationship_contact", "answer.relationship_ties", role_source], reasons, gaps)
            else:
                unknowns.append("Whether the possible personal relationship is current and relevant remains unresolved (answer.relationship_contact).")
        elif context.relationship in {"Unknown", "Other"} and choice("relationship_relevance") in UNRESOLVED:
            unknowns.append("Whether a relevant personal relationship exists is unresolved (answer.relationship_relevance).")

        # Intimidation: an unsupported interpretation is not a demonstrated link.
        pressure_relevant = context.pressure == "Reported pressure or threatened consequences" or (
            context.pressure in {"Unknown", "Other"} and choice("pressure_relevance") == "Possibly"
        )
        basis, support = choice("pressure_basis"), choice("pressure_support")
        connected = basis in {"Explicitly stated", "Implied in the conversation"} or (
            basis == "My interpretation only" and support == "A separate statement or action"
        )
        if pressure_relevant:
            if connected:
                gaps = []
                role_gap(gaps)
                effect, consequence = choice("pressure_effect"), choice("pressure_consequence")
                conflict = role_conflict
                if consequence in UNRESOLVED:
                    gaps.append("The nature of the consequence is unresolved (answer.pressure_consequence).")
                if effect in UNRESOLVED:
                    gaps.append("Whether pressure has changed professional work is unresolved (answer.pressure_effect).")
                if effect == "Yes" and choice("pressure_changes") in UNRESOLVED:
                    gaps.append("The part of the work that changed is unresolved (answer.pressure_changes).")
                if conflict:
                    gaps.append(role_conflict_gap)
                if no_involvement and not conflict:
                    unknowns.append("Reported pressure has not been linked to the user's own judgment because no decision involvement is reported.")
                else:
                    outcome = INSUFFICIENT if conflict else ACTION if (
                        effect == "Yes" or involved and consequence not in UNRESOLVED
                    ) else POTENTIAL
                    reasons = [
                        "The recorded answer links a professional decision to a stated, implied or separately supported consequence; this can deter objective judgment.",
                        "The account of pressure and the other person's intention have not been independently verified.",
                    ]
                    if effect == "Yes":
                        reasons.append("A change to professional work in response to pressure is reported. This is a reported actual effect, not proof that the change was technically wrong or misconduct occurred.")
                    elif effect == "No":
                        reasons.append("No change to work is reported. That distinguishes the account from an actual changed procedure, but does not remove potential future influence.")
                    if outcome == ACTION:
                        reasons.append("On this account, pressure affecting work or a consequence linked to decision responsibility requires action before proceeding; neither compliance nor safeguard effectiveness is established.")
                    add("Intimidation", outcome, "INT-01", "Reported pressure may constrain objective professional judgment.",
                        ["context.pressure", "answer.pressure_relevance", "answer.pressure_basis", "answer.pressure_support", "answer.pressure_consequence", "answer.pressure_effect", "answer.pressure_changes", role_source], reasons, gaps)
            elif basis == "My interpretation only":
                unknowns.append("The pressure connection is an interpretation without separately reported support (answer.pressure_support); intimidation is not established from that interpretation alone.")
            else:
                unknowns.append("How the reported pressure connects to the professional decision is unresolved (answer.pressure_basis).")
        elif context.pressure in {"Unknown", "Other"} and choice("pressure_relevance") in UNRESOLVED:
            unknowns.append("Whether pressure or threatened consequences are present is unresolved (answer.pressure_relevance).")

        # Self-interest: a benefit or firm interest needs a decision connection.
        interests = context.interests
        if interests in {"Unknown", "Other"}:
            interests = choice("interest_relevance")
            if interests in UNRESOLVED:
                unknowns.append("Whether a commercial or personal financial interest is relevant is unresolved (answer.interest_relevance).")
        commercial = interests in {"Commercial interest", "Both commercial and personal interests"}
        personal = interests in {"Personal financial interest", "Both commercial and personal interests"}
        commercial_link = choice("commercial_connection") in {"Contract renewal or client retention", "Fees or profitability"}
        direct_personal = choice("personal_connection") in {"Bonus or performance-related pay", "Investment or ownership interest", "Another direct financial benefit"}
        personal_link = direct_personal and choice("personal_outcome") != "No"
        if commercial or personal:
            gaps, reasons = [], []
            if commercial and choice("commercial_connection") in UNRESOLVED:
                gaps.append("The connection between the commercial interest and the decision is unresolved (answer.commercial_connection).")
            if personal and choice("personal_connection") in UNRESOLVED:
                gaps.append("The nature of a personal financial interest is unresolved (answer.personal_connection).")
            if commercial_link and choice("commercial_dependence") in UNRESOLVED:
                gaps.append("The organisation's dependence on the income or relationship is unresolved (answer.commercial_dependence).")
            if direct_personal and choice("personal_outcome") in UNRESOLVED:
                gaps.append("Whether the outcome changes the user's financial position is unresolved (answer.personal_outcome).")
            if commercial_link:
                reasons.append("The recorded answer links the decision to client retention, renewal, fees or profitability; this may create a commercial incentive to favour a particular outcome.")
                reasons.append("The firm-level incentive does not establish a direct personal remuneration benefit.")
            if personal_link:
                reasons.append("A direct personal financial interest is reported; whether it benefits from a particular decision outcome affects the incentive to favour that outcome.")
            if commercial_link or personal_link:
                if no_involvement:
                    unknowns.append("A financial interest is reported, but no involvement in the decision is reported; a link to the user's own judgment is not established.")
                    unknowns.extend(gaps)
                else:
                    role_gap(gaps)
                    strong = commercial_link and choice("commercial_dependence") == "A major source of income or business" or direct_personal and choice("personal_outcome") == "Yes"
                    outcome = INSUFFICIENT if role_conflict else ACTION if strong and involved else POTENTIAL
                    if outcome == ACTION:
                        reasons.append("The reported incentive and decision responsibility require the threat to be addressed before proceeding; this is conditional reasoning, not a finding of biased conduct.")
                    if commercial_link and choice("commercial_dependence") == "No known financial dependence":
                        reasons.append("No known financial dependence is reported, but this does not remove the identified commercial incentive.")
                    add("Self-interest", outcome, "SELF-01", "A reported commercial or personal incentive may affect objective judgment.",
                        ["context.interests", "answer.interest_relevance", "answer.commercial_connection", "answer.commercial_dependence", "answer.personal_connection", "answer.personal_outcome", role_source], reasons, gaps)
            else:
                unknowns.extend(gaps)
                if direct_personal and choice("personal_outcome") == "No":
                    unknowns.append("A personal interest is reported but no decision-outcome effect is identified (answer.personal_outcome); clarify any other link before identifying a threat.")

        # Missing answers remain visible even if an incomplete path is reviewed.
        for question in eligible_questions(assessment):
            if question.id not in answers:
                unknowns.append(f"A currently relevant question has not been answered ({'answer.' + question.id}).")

    interactions = []
    kinds = {finding.kind for finding in findings}
    if len(kinds) > 1:
        interactions.append(
            "These circumstances should be considered together, not in isolation: "
            + ", ".join(sorted(kinds))
            + " may reinforce one another. Their combination is not a numerical score or proof of compromised judgment."
        )
    if {"Intimidation", "Self-interest"}.issubset(kinds):
        interactions.append("Commercial or personal consequences can make pressure harder to resist; a single reported contract renewal may support both categories and is not independent corroboration of either.")
    if {"Familiarity", "Intimidation"}.issubset(kinds):
        interactions.append("If the relationship is with the person applying pressure, it can make that person harder to challenge. The structured answers do not establish that these are the same person; their identities and connection remain user-reported.")
    if assumption_reason:
        unknowns.append("The recorded basis for treating threats as addressed is not sufficient by assertion alone (review.objectivity_basis); no safeguard conclusion is made.")

    explanation = (
        "The reasonable and informed third party test asks whether a reasonable and informed "
        "third party, weighing the relevant facts and circumstances known or reasonably expected "
        "to be known, would likely reach the same conclusion about compliance with Objectivity. "
        "This is a reasoning lens, not a claim that an independent third party reviewed the case. "
    )
    if not assessment.confirmed:
        provisional = "The context must be confirmed before a case-specific provisional assessment can be made."
    elif any(f.outcome == ACTION for f in findings):
        provisional = (
            "If the recorded account is accurate, the decision links described in the findings "
            "would give such a third party reason to question proceeding under the current "
            "circumstances without addressing the threats. This does not establish misconduct, "
            "the technical correctness of any decision, or the sufficiency of any response."
        )
    elif findings:
        provisional = (
            "On the recorded account, the potential sources of influence in the findings require "
            "evaluation. Missing or conflicting information prevents a justified conclusion that "
            "the threats are at an acceptable level; no actual bias is established."
        )
    elif unknowns:
        provisional = "Critical links remain uncertain. There is insufficient information for a case-specific conclusion that threats are present or that Objectivity is adequately protected."
    else:
        provisional = "No potential threat is established by the structured information within these rules. This is not assurance of Objectivity or a conclusion that all possible threats are absent."
    if assumption_reason:
        provisional += " " + assumption_reason
    return Evaluation(
        assessment.revision, tuple(findings), _unique(unknowns), tuple(interactions),
        explanation + provisional,
        (
            "Scenario narrative is a reported account; confirmed context and recorded answers remain user-provided, not independently verified evidence. No independently verified evidence has been obtained by this app.",
            "Only Objectivity is considered. For audit-related work, separate audit-independence and non-assurance-service requirements need their own assessment.",
            "The Identify, Evaluate, Address conceptual framework informs this design. This phase does not implement the Address stage or determine whether safeguards are sufficient.",
            "These are authored implementation rules, not ACCA/IESBA approval, professional validation or a complete application of all applicable requirements. Professional judgment remains necessary.",
        ),
    )
