"""Streamlit views; all question selection is delegated to the domain engine."""

from copy import deepcopy

import streamlit as st

from objectivity.examples import EXAMPLE_CONTEXT, EXAMPLE_SCENARIO
from objectivity.evaluation import evaluate
from objectivity.evaluation_ui import render_findings
from objectivity.models import (
    INTEREST_OPTIONS,
    PRESSURE_OPTIONS,
    RELATIONSHIP_OPTIONS,
    Assessment,
    Context,
    Question,
)
from objectivity.questions import (
    QUESTION_BANK,
    confirm_context,
    eligible_questions,
    next_question,
    save_answer,
)
from objectivity.review import (
    REVIEW_QUESTIONS,
    ReviewState,
    eligible_review_questions,
    next_review_question,
    save_review_answer,
    sync_review,
)


def _navigate(view: str) -> None:
    st.session_state.view = view
    st.session_state.edit_answer_id = None
    st.session_state.edit_review_id = None
    # A new widget generation prevents stale form values after edits/navigation.
    st.session_state.widget_generation += 1
    st.rerun()


def _key(name: str) -> str:
    return f"{st.session_state.widget_generation}:{name}"


def _scenario_view(assessment: Assessment) -> None:
    st.caption("Step 1 of 4 · Describe your scenario")
    st.subheader("What situation would you like to explore?")
    st.write(
        "Describe the professional decision and the circumstances that concern you. "
        "You will confirm the relevant details yourself in the next step."
    )
    if st.button("Load CFO / revenue recognition example"):
        st.session_state.assessment = Assessment(
            scenario=EXAMPLE_SCENARIO, context=deepcopy(EXAMPLE_CONTEXT)
        )
        st.session_state.example_loaded = True
        _navigate("context")
    with st.form("scenario_entry"):
        scenario = st.text_area(
            "Your scenario", value=assessment.scenario, height=180,
            placeholder="Describe your role, the decision and what happened…",
            key=_key("scenario"),
        )
        submitted = st.form_submit_button("Continue to context confirmation")
    if submitted:
        if not scenario.strip():
            st.warning("Please enter a scenario before continuing.")
        else:
            assessment.scenario = scenario.strip()
            _navigate("context")


def _context_view(assessment: Assessment) -> None:
    st.caption("Step 2 of 4 · Confirm the context")
    st.subheader("Check the details that will guide the questions")
    if st.session_state.get("example_loaded"):
        st.info(
            "This example includes editable context supplied with the example. "
            "It was not extracted from the narrative. Please review it before confirming."
        )
    st.write(
        "These fields are your account of the situation. No facts have been independently "
        "verified. Free text is retained for reference; only the structured selections "
        "control which follow-up questions appear."
    )
    context = assessment.context
    with st.form("context_confirmation"):
        scenario = st.text_area(
            "Scenario account", value=assessment.scenario, key=_key("context_scenario")
        )
        role = st.text_input("Your professional role", value=context.role, key=_key("role"))
        parties = st.text_area(
            "Relevant parties and their roles", value=context.parties, key=_key("parties")
        )
        decision = st.text_area(
            "Professional decision or activity", value=context.decision, key=_key("decision")
        )
        st.caption("For the fields above, enter 'Unknown' if you cannot establish the detail yet.")
        relationship = st.selectbox(
            "Relevant relationship", RELATIONSHIP_OPTIONS,
            index=RELATIONSHIP_OPTIONS.index(context.relationship), key=_key("relationship"),
        )
        relationship_notes = st.text_area(
            "Relationship details (optional)", value=context.relationship_notes,
            key=_key("relationship_notes"),
        )
        interests = st.selectbox(
            "Commercial or personal financial interests", INTEREST_OPTIONS,
            index=INTEREST_OPTIONS.index(context.interests), key=_key("interests"),
        )
        interests_notes = st.text_area(
            "Interest details (optional)", value=context.interests_notes,
            key=_key("interests_notes"),
        )
        pressure = st.selectbox(
            "Reported pressure or threatened consequences", PRESSURE_OPTIONS,
            index=PRESSURE_OPTIONS.index(context.pressure), key=_key("pressure"),
        )
        pressure_notes = st.text_area(
            "Pressure details (optional)", value=context.pressure_notes,
            key=_key("pressure_notes"),
        )
        confirmed = st.checkbox(
            "I confirm that these fields reflect my account, including any uncertainty. "
            "This is not independent verification.",
            key=_key("confirmed"),
        )
        submitted = st.form_submit_button("Confirm context and continue")
    if submitted:
        if not confirmed:
            st.warning("Please confirm the context before continuing.")
        else:
            try:
                confirm_context(
                    assessment, scenario,
                    Context(
                        role=role, parties=parties, decision=decision,
                        relationship=relationship, interests=interests, pressure=pressure,
                        relationship_notes=relationship_notes,
                        interests_notes=interests_notes, pressure_notes=pressure_notes,
                    ),
                )
            except ValueError as error:
                st.warning(str(error))
            else:
                st.session_state.example_loaded = False
                _navigate("questions")
    if assessment.confirmed and st.button("Cancel context edit"):
        _navigate("questions")


def _context_review(assessment: Assessment) -> None:
    with st.expander("Confirmed context — review or edit"):
        st.caption("User-confirmed account · Not independently verified")
        st.text(assessment.scenario)
        context = assessment.context
        for label, value in (
            ("Role", context.role), ("Relevant parties", context.parties),
            ("Professional decision", context.decision),
            ("Relationship", context.relationship), ("Relationship details", context.relationship_notes),
            ("Interests", context.interests), ("Interest details", context.interests_notes),
            ("Reported pressure", context.pressure), ("Pressure details", context.pressure_notes),
        ):
            if value:
                st.write(f"**{label}**")
                st.text(value)
        if st.button("Edit scenario or context"):
            _navigate("context")
        st.caption(
            "Changing context refreshes the question paths. Answers that no longer apply "
            "are excluded from current progress."
        )


def _answer_form(
    assessment: Assessment, question: Question, editing: bool,
    review_state: ReviewState | None = None,
) -> None:
    st.subheader("Edit a previous answer" if editing else question.topic)
    with st.expander("Why this question?"):
        st.write(question.why)
    answers = review_state.answers if review_state is not None else assessment.answers
    previous = answers.get(question.id) if editing else None
    with st.form(f"answer_{question.id}_{st.session_state.widget_generation}"):
        choice = st.radio(
            question.prompt, question.options,
            index=question.options.index(previous.choice) if previous else None,
            key=_key(f"choice_{question.id}"),
        )
        explanation = st.text_area(
            "Additional explanation (optional)",
            value=previous.explanation if previous else "",
            key=_key(f"explanation_{question.id}"),
        )
        st.caption(
            "Explanations are stored as your account and are not automatically interpreted. "
            "Select the option that should guide the next question."
        )
        submitted = st.form_submit_button("Save answer" if editing else "Save and continue")
    if submitted:
        if choice is None:
            st.warning("Please choose an option, including Unknown if needed.")
        else:
            try:
                if review_state is None:
                    save_answer(assessment, question.id, choice, explanation)
                else:
                    save_review_answer(assessment, review_state, question.id, choice, explanation)
            except ValueError as error:
                st.warning(str(error))
            else:
                _navigate("review" if review_state is not None else "questions")
    if editing and st.button("Cancel answer edit"):
        _navigate("review" if review_state is not None else "questions")


def _answer_review(
    assessment: Assessment, questions: list[Question], review_state: ReviewState | None = None,
) -> None:
    answers = review_state.answers if review_state is not None else assessment.answers
    answered = [question for question in questions if question.id in answers]
    title = "Review evaluation answers" if review_state is not None else "Review previous answers"
    with st.expander(f"{title} ({len(answered)})"):
        if not answered:
            st.caption("Your saved answers will appear here.")
            return
        by_id = {question.id: question for question in answered}
        selected_id = st.selectbox(
            "Choose an evaluation answer to review" if review_state is not None else "Choose an answer to review",
            list(by_id),
            format_func=lambda question_id: by_id[question_id].prompt,
            key=_key("evaluation_selection" if review_state is not None else "review_selection"),
        )
        answer = answers[selected_id]
        st.write("**Selected answer**")
        st.text(answer.choice)
        if answer.explanation:
            st.write("**Your explanation — not automatically interpreted**")
            st.text(answer.explanation)
        if st.button("Edit selected evaluation answer" if review_state is not None else "Edit selected answer"):
            if review_state is None:
                st.session_state.edit_answer_id = selected_id
                st.session_state.edit_review_id = None
                st.session_state.view = "questions"
            else:
                st.session_state.edit_review_id = selected_id
                st.session_state.edit_answer_id = None
            st.session_state.widget_generation += 1
            st.rerun()
        st.caption(
            "An edited answer can add or remove later questions. Dependent answers "
            "may need to be answered again."
        )


def _questions_view(assessment: Assessment) -> None:
    st.caption("Step 3 of 4 · Guided clarification")
    questions = eligible_questions(assessment)
    count = sum(question.id in assessment.answers for question in questions)
    st.progress(
        count / len(questions) if questions else 1.0,
        text=f"Clarification · {count} of {len(questions)} currently relevant questions answered",
    )
    st.caption("The question count adapts to your answers; it is not a measure of ethical acceptability.")
    _context_review(assessment)
    edit_id = st.session_state.edit_answer_id
    question = next((item for item in questions if item.id == edit_id), None) if edit_id else next_question(assessment)
    if question:
        _answer_form(assessment, question, editing=bool(edit_id))
    else:
        st.subheader("Current clarification complete")
        st.info(
            "You have answered all questions currently selected by the rules. "
            "This does not establish that any threat is acceptable or that the facts are verified. "
            "Continue to review potential threats and provisional significance reasoning. "
            "Safeguard conclusions and assessment reports are not included in this release."
        )
        st.write("Review your answers or edit the context when new information becomes available.")
        if st.button("Review potential threats"):
            _navigate("review")
    _answer_review(assessment, questions)
    _answer_history(assessment.archive, QUESTION_BANK, "Superseded answers")


def _answer_history(archive, bank: dict[str, Question], title: str) -> None:
    if archive:
        with st.expander(f"{title} ({len(archive)})"):
            st.caption(
                "Retained for reference only; excluded from current question selection and "
                "progress. If a question returns, please answer it again using the current context."
            )
            for record in archive:
                st.write(f"**Revision {record.revision} · {record.reason}**")
                st.text(bank[record.question_id].prompt)
                st.text(record.answer.choice)
                if record.answer.explanation:
                    st.text(record.answer.explanation)


def _review_view(assessment: Assessment, state: ReviewState) -> None:
    st.caption("Step 4 of 4 · Identify and evaluate")
    st.subheader("Review potential threats")
    if not assessment.confirmed or next_question(assessment) is not None:
        st.info("The earlier clarification has changed. Complete the relevant questions before reviewing.")
        if st.button("Return to clarification"):
            _navigate("questions")
        return
    st.write(
        "These are provisional findings from your structured account, not proof of bias "
        "or misconduct. Findings are recalculated when you edit the supporting information."
    )
    _context_review(assessment)
    questions = eligible_review_questions(assessment, state)
    edit_id = st.session_state.get("edit_review_id")
    question = next((q for q in questions if q.id == edit_id), None) if edit_id else next_review_question(assessment, state)
    if question:
        st.info("An additional point needs clarification. You can review the conditional reasoning below while answering.")
        _answer_form(assessment, question, editing=bool(edit_id), review_state=state)
    else:
        st.caption("No further evaluation questions are currently selected. Uncertainties may remain.")
    render_findings(evaluate(assessment, state.answers))
    st.divider()
    _answer_review(assessment, questions, review_state=state)
    _answer_review(assessment, eligible_questions(assessment))
    _answer_history(assessment.archive, QUESTION_BANK, "Superseded answers")
    _answer_history(state.archive, REVIEW_QUESTIONS, "Superseded evaluation answers")
    if st.button("Return to clarification"):
        _navigate("questions")


def render_app() -> None:
    st.set_page_config(page_title="Objectivity Ethics Assistant", page_icon="⚖️")
    if "assessment" not in st.session_state:
        st.session_state.assessment = Assessment()
        st.session_state.view = "scenario"
        st.session_state.edit_answer_id = None
        st.session_state.widget_generation = 0
    if "review_state" not in st.session_state:
        st.session_state.review_state = ReviewState()
    st.title("Objectivity Ethics Assistant")
    st.write(
        "Explore circumstances that may affect objective professional judgment through "
        "guided, relevant questions. This assistant focuses exclusively on the fundamental "
        "principle of Objectivity and supports, rather than replaces, professional judgment."
    )
    st.caption(
        "Rule-based guidance · No generative AI · No independent fact verification"
    )
    with st.sidebar:
        st.subheader("Your session")
        st.write("Describe → Confirm → Clarify → Review")
        st.caption(
            "Progress is kept in this Streamlit session, not saved to a database. "
            "Refreshing, reconnecting or restarting the server may lose it. "
            "Use anonymised details and avoid confidential information."
        )
        if st.button("Start a new scenario"):
            st.session_state.reset_pending = True
        if st.session_state.get("reset_pending"):
            st.warning("Discard this session's scenario and answers?")
            if st.button("Discard and start again"):
                for key in list(st.session_state):
                    del st.session_state[key]
                st.rerun()
            if st.button("Keep current scenario"):
                st.session_state.reset_pending = False
                st.rerun()
    assessment = st.session_state.assessment
    sync_review(assessment, st.session_state.review_state)
    if st.session_state.view == "scenario":
        _scenario_view(assessment)
    elif st.session_state.view == "context":
        _context_view(assessment)
    elif st.session_state.view == "review":
        _review_view(assessment, st.session_state.review_state)
    else:
        _questions_view(assessment)
