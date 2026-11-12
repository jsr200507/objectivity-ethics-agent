"""Adaptive evaluation follow-ups and session-only review answer history.

Phase 1 is unchanged. These questions run after clarification and use only the
same explicit structured choices as the reasoning engine.
"""

from dataclasses import astuple, dataclass, field

from .evaluation import evaluate
from .models import Answer, ArchivedAnswer, Assessment, Question
from .questions import eligible_questions, next_question


REVIEW_QUESTIONS = {
    "decision_responsibility": Question(
        "decision_responsibility",
        "What involvement do you have in this professional decision?",
        (
            "I make or recommend the decision", "I supervise or review the work",
            "I have no involvement in this decision", "Unknown", "Not applicable", "Other",
        ),
        "A potential threat is supported, but decision responsibility has not been "
        "recorded in the earlier questions. Your role description is not automatically interpreted.",
        "Decision responsibility",
    ),
    "objectivity_basis": Question(
        "objectivity_basis",
        "What is your current basis for believing the threats are addressed, if any?",
        (
            "I am not claiming the threats are addressed", "Confidence in my own impartiality",
            "Disclosure of the circumstances", "Documentation of the circumstances",
            "A proposed safeguard", "Unknown", "Not applicable", "Other",
        ),
        "Potential threats have been identified. This checks the basis of any assurance "
        "about objectivity; it does not evaluate or approve a safeguard.",
        "Basis for your judgment",
    ),
    "basis_challenge": Question(
        "basis_challenge",
        "What supports that belief beyond the measure you selected?",
        (
            "No additional basis identified", "A change in circumstances has been reported",
            "Further examination is needed", "Unknown", "Not applicable", "Other",
        ),
        "Confidence, disclosure, documentation or a proposed safeguard alone does not "
        "demonstrate that a threat is addressed. Record the basis without assuming sufficiency. "
        "If circumstances changed, edit the context or earlier answers so they can be reassessed.",
        "Examine the assumption",
    ),
}

UNSUPPORTED_BASES = {
    "Confidence in my own impartiality", "Disclosure of the circumstances",
    "Documentation of the circumstances", "A proposed safeguard",
}


@dataclass
class ReviewState:
    answers: dict[str, Answer] = field(default_factory=dict)
    archive: list[ArchivedAnswer] = field(default_factory=list)
    source_signature: tuple | None = None


def _signature(assessment: Assessment) -> tuple:
    current = {question.id for question in eligible_questions(assessment)}
    return (
        assessment.confirmed, assessment.scenario, astuple(assessment.context),
        tuple(sorted((id, answer.choice) for id, answer in assessment.answers.items() if id in current)),
    )


def _archive(assessment: Assessment, state: ReviewState, ids: set[str], reason: str) -> None:
    for id in list(state.answers):
        if id in ids:
            state.archive.append(ArchivedAnswer(id, state.answers.pop(id), reason, assessment.revision))


def sync_review(assessment: Assessment, state: ReviewState) -> None:
    """Do not reuse review judgments after the underlying structured account changes."""
    signature = _signature(assessment)
    if signature != state.source_signature:
        _archive(assessment, state, set(state.answers), "The underlying assessment changed.")
        state.source_signature = signature


def eligible_review_questions(assessment: Assessment, state: ReviewState) -> list[Question]:
    if not assessment.confirmed or next_question(assessment) is not None:
        return []
    evaluation = evaluate(assessment, state.answers)
    ids = []
    current = {question.id for question in eligible_questions(assessment)}
    # Reuse even an Unknown answer: asking the same fact again adds no evidence.
    responsibility_already_asked = (
        "relationship_influence" in current and "relationship_influence" in assessment.answers
    )
    if not responsibility_already_asked and (
        evaluation.findings or "decision_responsibility" in state.answers
    ):
        ids.append("decision_responsibility")
    if evaluation.findings:
        ids.append("objectivity_basis")
        basis = state.answers.get("objectivity_basis")
        if basis and basis.choice in UNSUPPORTED_BASES:
            ids.append("basis_challenge")
    return [REVIEW_QUESTIONS[id] for id in ids]


def next_review_question(assessment: Assessment, state: ReviewState) -> Question | None:
    return next((q for q in eligible_review_questions(assessment, state) if q.id not in state.answers), None)


def save_review_answer(
    assessment: Assessment, state: ReviewState, question_id: str, choice: str, explanation: str = ""
) -> None:
    sync_review(assessment, state)
    eligible = {q.id: q for q in eligible_review_questions(assessment, state)}
    if question_id not in eligible or choice not in eligible[question_id].options:
        raise ValueError("Choose an available answer to a currently relevant review question.")
    answer = Answer(choice, explanation.strip())
    previous = state.answers.get(question_id)
    if previous == answer:
        return
    assessment.revision += 1
    if previous:
        affected = {question_id}
        if previous.choice != choice:
            if question_id == "decision_responsibility":
                affected.update(("objectivity_basis", "basis_challenge"))
            elif question_id == "objectivity_basis":
                affected.add("basis_challenge")
        _archive(assessment, state, affected, "An earlier review answer changed.")
    state.answers[question_id] = answer
    applicable = {q.id for q in eligible_review_questions(assessment, state)}
    _archive(assessment, state, set(state.answers) - applicable, "This review question is no longer applicable.")
