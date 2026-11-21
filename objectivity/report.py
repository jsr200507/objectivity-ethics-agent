"""Create a readable, current Markdown snapshot without storing a verdict.

Only authored reasoning and recorded choices are used. Narrative and explanation
text is quoted as the user's account, never interpreted as verified evidence.
"""

from copy import deepcopy
import re

from .address import AddressState, assess_address, next_address_question
from .evaluation import evaluate
from .models import Assessment
from .questions import eligible_questions, next_question
from .review import ReviewState, eligible_review_questions, next_review_question, sync_review


_SOURCE_LABELS = {
    "pressure_relevance": "whether pressure may be relevant",
    "pressure_basis": "basis of the pressure connection",
    "pressure_support": "support for the pressure interpretation",
    "pressure_consequence": "reported consequences",
    "pressure_effect": "effect on professional work",
    "pressure_changes": "work affected by pressure",
    "relationship_relevance": "relevance of the personal relationship",
    "relationship_contact": "current personal contact",
    "relationship_ties": "continuing personal ties or obligations",
    "relationship_influence": "decision-making responsibility",
    "interest_relevance": "type of financial or commercial interest",
    "commercial_connection": "commercial connection to the decision",
    "commercial_dependence": "commercial dependence",
    "personal_connection": "nature of the personal financial interest",
    "personal_outcome": "effect on personal financial position",
    "decision_responsibility": "decision-making responsibility",
    "objectivity_basis": "basis for treating threats as addressed",
    "basis_challenge": "response to the assumption challenge",
    "relationship": "relationship account",
    "interests": "financial or commercial interest account",
    "pressure": "pressure account",
}
_SOURCE_PATTERN = re.compile(r"\b(?:answer|review|context)\.([A-Za-z_][A-Za-z0-9_]*)\b")


def humanize(text: str) -> str:
    """Render engine provenance references as ordinary professional English."""
    return _SOURCE_PATTERN.sub(
        lambda match: _SOURCE_LABELS.get(match[1], match[1].replace("_", " ")),
        text,
    )


def _escaped(text: str) -> str:
    """Escape Markdown and HTML without altering the user's meaning."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_{}\[\]()#+.!|~\-])", r"\\\1", text)


def _quote(text: str) -> str:
    return "\n".join("> " + _escaped(line) for line in text.splitlines()) if text else "> Not supplied."


def _paragraphs(items) -> list[str]:
    return ["- " + humanize(item) for item in dict.fromkeys(items)]


def _current_review(assessment: Assessment, review: ReviewState) -> ReviewState:
    current = deepcopy(review)
    sync_review(assessment, current)
    allowed = {question.id: question for question in eligible_review_questions(assessment, current)}
    current.answers = {
        id: answer for id, answer in current.answers.items()
        if id in allowed and answer.choice in allowed[id].options
    }
    return current


def build_report(assessment: Assessment, review: ReviewState, address: AddressState) -> str:
    """Recompute a report from current data; do not mutate session state or infer text."""
    assessment = deepcopy(assessment)
    address = deepcopy(address)
    current_review = _current_review(assessment, review)
    evaluation = evaluate(assessment, current_review.answers)
    addressed = assess_address(assessment, current_review, address)
    phase_one_pending = next_question(assessment) is not None
    phase_two_pending = next_review_question(assessment, current_review) is not None
    phase_three_pending = next_address_question(assessment, current_review, address) is not None
    # The Address assessment retains genuine factual gaps but distinguishes an
    # earlier unsupported assurance from current evidence about concrete actions.
    # Do not reintroduce that historical caution as a permanent residual gap.
    uncertainty = tuple(dict.fromkeys(addressed.unknowns))
    incomplete = (
        not assessment.confirmed or phase_one_pending or phase_two_pending or phase_three_pending
        or not addressed.current or bool(uncertainty)
        or any(outcome.unknowns for outcome in addressed.outcomes)
    )
    status = (
        "Interim — information, actions or acceptability remain unresolved"
        if incomplete else "Conditional assessment — professional judgment remains required"
    )
    lines = [
        "# Ethical Assessment Report", "", "**Objectivity Ethics Assistant**", "",
        f"**Assessment revision:** {assessment.revision}", "", f"**Status:** {status}", "",
        "This report is a snapshot of the current recorded account. Regenerate it after any "
        "change; an earlier download does not update automatically.", "",
        "## 1. Scenario and confirmed context", "",
        "### Reported scenario", "", _quote(assessment.scenario), "",
        "The narrative is reported information. Limited local rules may have suggested context "
        "fields before user confirmation; this report relies on the recorded structured account. "
        "The narrative has not been independently verified or understood as unrestricted text.", "",
    ]
    lines += [
        "### User-confirmed context" if assessment.confirmed else "### Context awaiting confirmation", "",
    ]
    context = assessment.context
    for label, value in (
        ("Professional role", context.role), ("Relevant parties", context.parties),
        ("Professional decision or activity", context.decision),
        ("Relationship", context.relationship), ("Relationship details", context.relationship_notes),
        ("Commercial or personal financial interests", context.interests),
        ("Interest details", context.interests_notes), ("Reported pressure", context.pressure),
        ("Pressure details", context.pressure_notes),
    ):
        if value:
            lines += [f"**{label}**", "", _quote(value), ""]
    lines += [
        "Confirmation records the user's account, including uncertainty. It does not make "
        "the account independently verified evidence.", "",
        "## 2. Facts, recorded answers and uncertainties", "",
        "The entries below are recorded user answers. Additional explanations remain "
        "uninterpreted accounts; they do not establish additional structured facts.", "",
    ]
    recorded = False
    for questions, answers in (
        (eligible_questions(assessment), assessment.answers),
        (eligible_review_questions(assessment, current_review), current_review.answers),
    ):
        for question in questions:
            answer = answers.get(question.id)
            if answer and answer.choice in question.options:
                recorded = True
                lines += [f"**{question.prompt}**", "", _quote(answer.choice), ""]
                if answer.explanation:
                    lines += ["Additional explanation — user account:", "", _quote(answer.explanation), ""]
    if not recorded:
        lines += ["No current structured follow-up answers are recorded.", ""]
    lines += [
        "**Evidence status:** No independently verified evidence has been obtained by this "
        "application. A user's report of an external check is distinguished from verification "
        "performed by this application.", "",
    ]
    if uncertainty:
        lines += ["**Unresolved information**", "", *_paragraphs(uncertainty), ""]
    if not assessment.confirmed:
        lines += ["The context must be confirmed before reliance on a case-specific assessment.", ""]
    if phase_one_pending or phase_two_pending:
        lines += ["Earlier clarification or evaluation questions remain unanswered.", ""]
    lines += ["## 3. Potential Objectivity threats and supporting evidence", ""]
    if not evaluation.findings:
        lines += [
            "No potential threat is established from the current structured information within "
            "these rules. This does not establish that threats are absent or that proceeding "
            "is acceptable.", "",
        ]
    for finding in evaluation.findings:
        lines += [f"### {finding.kind}", "", humanize(finding.summary), ""]
        for evidence in finding.evidence:
            lines += [f"**{evidence.label}**", "", _quote(evidence.value), "", evidence.status + ".", ""]
        lines += ["This is a potential threat, not proof of biased conduct or misconduct.", ""]
    lines += [
        "## 4. Initial significance and combined-threat reasoning", "",
        "The following findings describe the account before the actions in section 6. "
        "The residual assessment in section 7 considers the current action evidence.", "",
    ]
    for finding in evaluation.findings:
        lines += [f"### {finding.kind}: {finding.outcome}", "", *_paragraphs(finding.reasoning), ""]
        if finding.unknowns:
            lines += ["Information still needed:", "", *_paragraphs(finding.unknowns), ""]
    if not evaluation.findings:
        lines += ["A positive threat finding cannot be substituted for missing evidence.", ""]
    initial_finding_gaps = {item for finding in evaluation.findings for item in finding.unknowns}
    initial_cautions = [item for item in evaluation.unknowns if item not in initial_finding_gaps]
    if initial_cautions:
        lines += [
            "**Initial evaluation cautions and gaps — before the recorded actions**", "",
            *_paragraphs(initial_cautions), "",
        ]
    if evaluation.interactions:
        lines += ["### Combined circumstances", "", *[humanize(item) + "\n" for item in evaluation.interactions]]
    lines += [
        "## 5. Reasonable and informed third party assessment", "",
        "### Assessment before addressing the threats", "", humanize(evaluation.third_party), "",
        "### Reassessment after the recorded actions", "", humanize(addressed.third_party), "",
        "No actual independent third party has reviewed this case through the application.", "",
        "## 6. Proposed versus implemented actions", "",
    ]
    if not addressed.current:
        lines += [
            "Earlier action records are no longer current. They have not been used to support "
            "a residual-threat conclusion; revisit the Address stage using the current account.", "",
        ]
    has_actions = False
    for outcome in addressed.outcomes:
        if not outcome.actions:
            continue
        lines += [f"### Actions relating to {outcome.kind.lower()}", ""]
        for action in outcome.actions:
            has_actions = True
            lines += [f"**{humanize(action.description)}**", "", f"Recorded stage: {humanize(action.stage)}.", "",
                      humanize(action.evidence_status), ""]
            for label, value in action.details:
                lines += [f"**{humanize(label)}**", "", _quote(value), ""]
    if not has_actions:
        lines += ["No current implemented action has been established by the recorded information.", ""]
    lines += ["## 7. Remaining threats and missing information", ""]
    for outcome in addressed.outcomes:
        lines += [f"### {outcome.kind}: {humanize(outcome.status)}", "", *_paragraphs(outcome.reasoning), ""]
        if outcome.unknowns:
            lines += ["Remaining gaps:", "", *_paragraphs(outcome.unknowns), ""]
    if not addressed.outcomes:
        lines += [
            "No supported threat has an action assessment in this snapshot. Existing "
            "uncertainties and the limits of the structured rules still apply.", "",
        ]
    lines += ["## 8. Conditional conclusion", "", humanize(addressed.conclusion), ""]
    lines += ["## 9. Prioritised next steps", ""]
    if addressed.next_steps:
        lines += [f"{number}. {humanize(item)}" for number, item in enumerate(addressed.next_steps, 1)]
    else:
        lines += ["1. Apply professional judgment to the current account and reassess if any relevant circumstance changes."]
    lines += [
        "", "## 10. Scope and professional judgment", "",
        "This assistant focuses exclusively on the fundamental principle of Objectivity and "
        "uses rule-based guidance informed by the Identify, Evaluate, Address conceptual "
        "framework. It supports, rather than replaces, professional judgment.", "",
        "There is no generative AI, unrestricted free-text understanding or independent fact "
        "verification. Reported implementation and reported external checks remain "
        "user-provided accounts; the application does not authenticate documents or reviewers.", "",
        "The rules and this report have not received professional validation. This is not a "
        "certified ethical opinion, an automatic declaration of compliance or assurance that "
        "every relevant threat has been identified. Humans remain responsible for final "
        "judgment and for consulting applicable current requirements.", "",
        "For audit-related work, separate audit-independence and non-assurance-service "
        "requirements may apply and require their own assessment.", "",
        "The active assessment runs in session state. When browser saving is available and "
        "acknowledged, submitted progress can be resumed from that browser; otherwise use "
        "Download progress and Import progress. Browser storage and exported JSON may contain "
        "sensitive details: use fictional or anonymised cases. Clearing browser storage or "
        "private browsing can lose saved progress. No permanent server storage is used. "
        "Downloaded reports are snapshots and may become outdated; regenerate them following "
        "any material change.", "",
    ]
    return "\n".join(lines)
