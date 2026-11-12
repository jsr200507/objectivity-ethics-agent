"""Conditional clarification rules, with no threat evaluations or text inference.

Only explicit structured choices select branches. Explanations are preserved as
user statements and never parsed for facts or ethical findings.
"""

from copy import deepcopy

from .models import (
    INTEREST_OPTIONS,
    PRESSURE_OPTIONS,
    RELATIONSHIP_OPTIONS,
    Answer,
    ArchivedAnswer,
    Assessment,
    Context,
    Question,
)


UNCERTAINTY = ("Unknown", "Not applicable", "Other")


def _question(id: str, prompt: str, options: tuple[str, ...], why: str, topic: str) -> Question:
    return Question(id, prompt, options + UNCERTAINTY, why, topic)


QUESTION_BANK = {
    q.id: q
    for q in (
        _question(
            "pressure_relevance",
            "Could someone be trying to influence this decision through pressure or consequences?",
            ("Possibly", "No reported pressure"),
            "Your pressure context is Unknown or Other. This clarifies relevance without interpreting your narrative.",
            "Intimidation context",
        ),
        _question(
            "pressure_basis",
            "How was the possible consequence linked to your professional decision?",
            ("Explicitly stated", "Implied in the conversation", "My interpretation only"),
            "You reported possible pressure. The basis of the connection matters: an explicit statement, an implication, and an interpretation are different accounts.",
            "Intimidation context",
        ),
        _question(
            "pressure_support",
            "Is there a separate statement or action supporting your interpretation?",
            ("A separate statement or action", "No further supporting information"),
            "You selected interpretation only. This checks the basis for that interpretation without assuming intent or treating it as verified.",
            "Intimidation context",
        ),
        _question(
            "pressure_consequence",
            "What consequence was stated or implied?",
            ("Loss of fees or a contract", "Employment or career consequences", "Personal or professional retaliation"),
            "You reported an explicit or implied connection, or a separate supporting event. This clarifies the kind of consequence reported.",
            "Intimidation context",
        ),
        _question(
            "pressure_effect",
            "Have you changed any work or recommendation in response to that pressure?",
            ("Yes", "No"),
            "A reported connection has been clarified. This separates possible influence from a reported change in professional work.",
            "Intimidation context",
        ),
        _question(
            "pressure_changes",
            "Which part of your work changed?",
            ("Procedures or evidence gathering", "Recommendation or judgment", "Both"),
            "You reported changing work in response to pressure. This records what changed without judging whether the change was appropriate.",
            "Intimidation context",
        ),
        _question(
            "relationship_relevance",
            "Could a personal relationship with someone involved be relevant to your judgment?",
            ("Possibly relevant", "No relevant personal relationship"),
            "Your relationship context is Unknown or Other. A structured clarification is needed before selecting the familiarity path.",
            "Familiarity context",
        ),
        _question(
            "relationship_contact",
            "How much personal contact do you currently have with this person?",
            ("Frequent personal contact", "Occasional personal contact", "Little or no current personal contact"),
            "You reported a close or possibly relevant personal relationship. Current contact helps distinguish an active relationship from a historical connection.",
            "Familiarity context",
        ),
        _question(
            "relationship_ties",
            "Despite limited contact, do any current personal ties or obligations remain?",
            ("Yes", "No"),
            "You reported little or no current contact. This checks for continuing ties rather than assuming the old relationship remains close.",
            "Familiarity context",
        ),
        _question(
            "relationship_influence",
            "What involvement do you have in the professional decision?",
            ("I make or recommend the decision", "I supervise or review the work", "I have no involvement in this decision"),
            "You reported an active relationship, continuing ties, or uncertainty about them. This clarifies where that relationship intersects with your responsibilities.",
            "Familiarity context",
        ),
        _question(
            "interest_relevance",
            "Which kind of financial or commercial interest could be connected to this decision?",
            ("Commercial interest", "Personal financial interest", "Both commercial and personal interests", "No known interest"),
            "Your interest context is Unknown or Other. Select the relevant type explicitly; free-text details are not automatically classified.",
            "Self-interest context",
        ),
        _question(
            "commercial_connection",
            "How could the decision affect your organisation's commercial interests?",
            ("Contract renewal or client retention", "Fees or profitability", "No identified link to the decision"),
            "You selected a commercial interest. This asks whether and how it connects to the specific professional decision.",
            "Self-interest context",
        ),
        _question(
            "commercial_dependence",
            "What do you know about the organisation's dependence on that income or relationship?",
            ("A major source of income or business", "One of several sources", "No known financial dependence"),
            "You linked the decision to renewal, retention, fees, or profitability. This records commercial context without scoring the threat.",
            "Self-interest context",
        ),
        _question(
            "personal_connection",
            "What personal financial interest is connected to the decision?",
            ("Bonus or performance-related pay", "Investment or ownership interest", "Another direct financial benefit", "No identified link to the decision"),
            "You selected a personal financial interest. Its nature must be clarified rather than assumed from a firm-level interest.",
            "Self-interest context",
        ),
        _question(
            "personal_outcome",
            "Could a particular outcome of this decision change your financial position?",
            ("Yes", "No"),
            "You identified a direct personal financial interest. This clarifies its connection to the outcome, without evaluating significance.",
            "Self-interest context",
        ),
    )
}

# Explicit dependencies also determine which old answers must be reconfirmed
# after editing an upstream answer, even if their question remains applicable.
DEPENDENCIES = {
    "pressure_basis": ("pressure_relevance",),
    "pressure_support": ("pressure_basis",),
    "pressure_consequence": ("pressure_basis", "pressure_support"),
    "pressure_effect": ("pressure_basis", "pressure_support"),
    "pressure_changes": ("pressure_effect",),
    "relationship_contact": ("relationship_relevance",),
    "relationship_ties": ("relationship_contact",),
    "relationship_influence": ("relationship_contact", "relationship_ties"),
    "commercial_connection": ("interest_relevance",),
    "commercial_dependence": ("commercial_connection",),
    "personal_connection": ("interest_relevance",),
    "personal_outcome": ("personal_connection",),
}


def _choice(assessment: Assessment, id: str) -> str | None:
    answer = assessment.answers.get(id)
    return answer.choice if answer else None


def eligible_questions(assessment: Assessment) -> list[Question]:
    """Return applicable questions, including already answered ones, in order."""
    if not assessment.confirmed:
        return []
    context = assessment.context
    ids: list[str] = []
    uncertain = {"Unknown", "Other"}

    if context.pressure in uncertain:
        ids.append("pressure_relevance")
    pressure_relevant = context.pressure == "Reported pressure or threatened consequences" or (
        context.pressure in uncertain and _choice(assessment, "pressure_relevance") == "Possibly"
    )
    if pressure_relevant:
        ids.append("pressure_basis")
        basis = _choice(assessment, "pressure_basis")
        if basis == "My interpretation only":
            ids.append("pressure_support")
        connected = basis in {"Explicitly stated", "Implied in the conversation"} or (
            basis == "My interpretation only"
            and _choice(assessment, "pressure_support") == "A separate statement or action"
        )
        if connected:
            ids.extend(("pressure_consequence", "pressure_effect"))
            if _choice(assessment, "pressure_effect") == "Yes":
                ids.append("pressure_changes")

    if context.relationship in uncertain:
        ids.append("relationship_relevance")
    relationship_relevant = context.relationship == "Close personal relationship" or (
        context.relationship in uncertain
        and _choice(assessment, "relationship_relevance") == "Possibly relevant"
    )
    if relationship_relevant:
        ids.append("relationship_contact")
        contact = _choice(assessment, "relationship_contact")
        if contact == "Little or no current personal contact":
            ids.append("relationship_ties")
        active = contact in {"Frequent personal contact", "Occasional personal contact", "Unknown", "Other"} or (
            contact == "Little or no current personal contact"
            and _choice(assessment, "relationship_ties") in {"Yes", "Unknown", "Other"}
        )
        if active:
            ids.append("relationship_influence")

    interests = context.interests
    if interests in uncertain:
        ids.append("interest_relevance")
        interests = _choice(assessment, "interest_relevance")
    if interests in {"Commercial interest", "Both commercial and personal interests"}:
        ids.append("commercial_connection")
        if _choice(assessment, "commercial_connection") in {"Contract renewal or client retention", "Fees or profitability"}:
            ids.append("commercial_dependence")
    if interests in {"Personal financial interest", "Both commercial and personal interests"}:
        ids.append("personal_connection")
        if _choice(assessment, "personal_connection") in {
            "Bonus or performance-related pay", "Investment or ownership interest", "Another direct financial benefit"
        }:
            ids.append("personal_outcome")
    return [QUESTION_BANK[id] for id in ids]


def next_question(assessment: Assessment) -> Question | None:
    return next((q for q in eligible_questions(assessment) if q.id not in assessment.answers), None)


def _archive_answers(assessment: Assessment, ids: set[str], reason: str) -> None:
    for id in list(assessment.answers):
        if id in ids:
            assessment.archive.append(
                ArchivedAnswer(id, assessment.answers.pop(id), reason, assessment.revision)
            )


def _descendants(id: str) -> set[str]:
    descendants: set[str] = set()
    changed = {id}
    while changed:
        changed = {
            child for child, parents in DEPENDENCIES.items()
            if child not in descendants and any(parent in changed for parent in parents)
        }
        descendants.update(changed)
    return descendants


def save_answer(assessment: Assessment, question_id: str, choice: str, explanation: str = "") -> None:
    """Save a choice; only changed structured choices invalidate descendants."""
    eligible = {q.id: q for q in eligible_questions(assessment)}
    if question_id not in eligible:
        raise ValueError("This question is not currently applicable.")
    if choice not in eligible[question_id].options:
        raise ValueError("Choose one of the available answers.")
    answer = Answer(choice, explanation.strip())
    previous = assessment.answers.get(question_id)
    if previous == answer:
        return
    assessment.revision += 1
    if previous is not None:
        invalidated = {question_id}
        if previous.choice != answer.choice:
            invalidated |= _descendants(question_id)
        _archive_answers(assessment, invalidated, "An earlier answer changed.")
    assessment.answers[question_id] = answer
    current = {q.id for q in eligible_questions(assessment)}
    _archive_answers(assessment, set(assessment.answers) - current, "The question is no longer applicable.")


def confirm_context(assessment: Assessment, scenario: str, context: Context) -> None:
    """Validate user-confirmed context and invalidate answers affected by edits."""
    if not all(value.strip() for value in (scenario, context.role, context.parties, context.decision)):
        raise ValueError("Enter a scenario, your role, the relevant parties, and the professional decision.")
    for value, options in (
        (context.relationship, RELATIONSHIP_OPTIONS),
        (context.interests, INTEREST_OPTIONS),
        (context.pressure, PRESSURE_OPTIONS),
    ):
        if value not in options:
            raise ValueError("Select a supported structured context option.")
    previous = assessment.context
    if assessment.confirmed and assessment.scenario == scenario.strip() and previous == context:
        return
    assessment.revision += 1
    common_changed = assessment.scenario != scenario.strip() or any(
        getattr(previous, field) != getattr(context, field)
        for field in ("role", "parties", "decision", "basis")
    )
    if common_changed:
        affected = set(assessment.answers)
    else:
        topics = set()
        for fields, topic in (
            (("relationship", "relationship_notes"), "Familiarity context"),
            (("interests", "interests_notes"), "Self-interest context"),
            (("pressure", "pressure_notes"), "Intimidation context"),
        ):
            if any(getattr(previous, field) != getattr(context, field) for field in fields):
                topics.add(topic)
        affected = {id for id in assessment.answers if QUESTION_BANK[id].topic in topics}
    _archive_answers(assessment, affected, "The confirmed context changed.")
    assessment.scenario = scenario.strip()
    assessment.context = deepcopy(context)
    assessment.confirmed = True
    current = {q.id for q in eligible_questions(assessment)}
    _archive_answers(assessment, set(assessment.answers) - current, "The question is no longer applicable.")
