"""Streamlit views; all question selection is delegated to the domain engine."""

import streamlit as st

from objectivity.examples import EXAMPLE_SCENARIO
from objectivity.case_workflow import start_case, migrate_legacy_assessment
from objectivity.case_ui import render_case
from objectivity.extraction import extract_context
from objectivity.intake_ui import render_intake
from objectivity.intake import sync_intake
from objectivity.context_suggestions import SUGGESTED_FIELDS, apply_suggestions
from objectivity.address import AddressState, sync_address
from objectivity.address_ui import render_address, render_report
from objectivity.progress_ui import render_save_resume
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
    st.session_state.edit_address_id = None
    # A new widget generation prevents stale form values after edits/navigation.
    st.session_state.widget_generation += 1
    st.rerun()


def _key(name: str) -> str:
    return f"{st.session_state.widget_generation}:{name}"


def _scenario_view(assessment: Assessment) -> None:
    st.caption("Identify · Describe the professional decision")
    st.subheader("What situation would you like to explore?")
    st.write(
        "Describe the decision, the people involved and any actions already taken. "
        "You will see provisional findings first, then clarify only material gaps."
    )
    if st.button("Try CFO example"):
        st.session_state.assessment = Assessment(scenario=EXAMPLE_SCENARIO, case_state=start_case(EXAMPLE_SCENARIO))
        _navigate("identify")
    with st.expander("Previous guided example (optional)"):
        if st.button("Load CFO / revenue recognition example"):
            suggested = extract_context(EXAMPLE_SCENARIO).context
            st.session_state.assessment = Assessment(scenario=EXAMPLE_SCENARIO, context=suggested)
            st.session_state.example_loaded = True
            _navigate("context")
    with st.form("scenario_entry"):
        scenario = st.text_area(
            "Your scenario", value=assessment.scenario, height=180,
            placeholder="Describe the professional work, relevant circumstances and what has happened…",
            key=_key("scenario"),
        )
        identify = st.form_submit_button("Identify potential threats")
        with st.expander("Previous guided assessment (optional)"):
            st.caption("Use the earlier context-confirmation workflow, including for saved assessments.")
            submitted = st.form_submit_button("Continue to context confirmation")
    if identify or submitted:
        if not scenario.strip():
            st.warning("Please enter a scenario before continuing.")
        elif identify:
            try:
                case = start_case(scenario)
            except ValueError as error:
                st.warning(str(error))
            else:
                assessment.scenario = scenario.strip()
                assessment.case_state = case
                _navigate("identify")
        else:
            assessment.scenario = scenario.strip()
            assessment.context = extract_context(assessment.scenario).context
            assessment.confirmed = False
            _navigate("context")


def _context_view(assessment: Assessment) -> None:
    sync_intake(assessment)
    st.caption("Step 2 of 6 · Confirm the context")
    st.subheader("Confirm what matters, one detail at a time")
    st.write(
        "Check the suggested account below. Local rules may miss details or misattribute them; "
        "correct any suggestion and clarify only what is needed. Nothing is independently verified."
    )
    if not assessment.confirmed:
        st.caption("Unconfirmed draft · Suggestions and your clarifications need confirmation before assessment.")
    else:
        st.caption("User-confirmed account · Review or edit without repeating established details.")
    # The complete editor remains an explicit alternative for direct corrections.
    # It is optional: the default route uses the summary and focused questions.
    opened = st.session_state.get("_open_context_details") == st.session_state.widget_generation
    with st.expander("Edit all context details (optional)", expanded=opened):
        st.caption(
            "Use this alternative if you prefer to review every field together. Confirming here "
            "also acknowledges any fields you explicitly leave Unknown."
        )
        _context_detailed_editor(assessment)
    matched = extract_context(assessment.scenario)
    with st.expander("How were the suggestions obtained?"):
        st.write(
            "Local English rules suggest details from your reported scenario; they do not "
            "understand every narrative or verify any claim. Saved values may include your edits."
        )
        for field, label in SUGGESTED_FIELDS.items():
            st.write(f"**{label} — matches in the saved scenario**")
            excerpts = matched.evidence.get(field, ())
            st.text("; ".join(excerpts) if excerpts else "No reliable extraction — clarify this detail if relevant.")
        for limitation in matched.limitations:
            st.caption(limitation)
    render_intake(assessment, _navigate, matched)


def _context_detailed_editor(assessment: Assessment) -> None:
    context = assessment.context
    with st.form("context_confirmation"):
        scenario = st.text_area(
            "Scenario account", value=assessment.scenario, key=_key("context_scenario")
        )
        role = st.text_input("Your professional role", value=context.role or "Unknown", key=_key("role"))
        parties = st.text_area(
            "Relevant parties and their roles", value=context.parties or "Unknown", key=_key("parties")
        )
        decision = st.text_area(
            "Professional decision or activity", value=context.decision or "Unknown", key=_key("decision")
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
        preview_requested = st.form_submit_button("Preview fresh suggestions")
        submitted = st.form_submit_button("Confirm context and continue")
    draft = Context(
        role=role, parties=parties, decision=decision, relationship=relationship,
        interests=interests, pressure=pressure, relationship_notes=relationship_notes,
        interests_notes=interests_notes, pressure_notes=pressure_notes,
    )
    if preview_requested:
        if not scenario.strip():
            st.warning("Enter a scenario before requesting suggestions.")
        else:
            st.session_state["_context_preview_counter"] = st.session_state.get("_context_preview_counter", 0) + 1
            st.session_state["_context_suggestion_preview"] = {
                "scenario": scenario, "draft": draft, "result": extract_context(scenario),
                "generation": st.session_state.widget_generation,
                "counter": st.session_state["_context_preview_counter"],
            }
    if submitted:
        if not confirmed:
            st.warning("Please confirm the context before continuing.")
        else:
            try:
                confirm_context(
                    assessment, scenario, draft,
                )
            except ValueError as error:
                st.warning(str(error))
            else:
                st.session_state.example_loaded = False
                st.session_state.pop("_context_suggestion_preview", None)
                _navigate("questions")
    _context_suggestion_preview(assessment)
    if assessment.confirmed and st.button("Cancel context edit"):
        _navigate("questions")


def _context_suggestion_preview(assessment: Assessment) -> None:
    preview = st.session_state.get("_context_suggestion_preview")
    if preview and preview["generation"] != st.session_state.widget_generation:
        st.session_state.pop("_context_suggestion_preview", None)
        preview = None
    notice = st.session_state.get("_context_suggestion_notice")
    if notice and notice[0] == st.session_state.widget_generation:
        st.info(notice[1])
    if not preview:
        return
    result = preview["result"]
    st.subheader("Preview refreshed context suggestions")
    st.caption("Preview only: the last submitted scenario is shown below. No assessment fields or answers have been replaced yet.")
    st.text(preview["scenario"])
    for field, label in SUGGESTED_FIELDS.items():
        st.write(f"**{label}**")
        st.text(getattr(result.context, field))
        for excerpt in result.evidence.get(field, ()):
            st.text(f"Source: {excerpt}")
    for limitation in result.limitations:
        st.caption(limitation)
    defaults = [
        field for field in SUGGESTED_FIELDS
        if getattr(preview["draft"], field).strip() in {"", "Unknown"}
        and getattr(result.context, field) != "Unknown"
    ]
    selected = st.multiselect(
        "Fields to replace", list(SUGGESTED_FIELDS), default=defaults,
        format_func=lambda field: SUGGESTED_FIELDS[field],
        key=_key(f"suggestion_fields_{preview['counter']}"),
    )
    acknowledged = st.checkbox(
        "Replace the selected fields and require context confirmation again",
        key=_key(f"suggestion_ack_{preview['counter']}"),
    )
    st.caption("Applying saves the submitted context as an unconfirmed draft. Existing assessment answers move to history and must be reconsidered; unselected fields retain the submitted form values.")
    if st.button("Apply selected suggestions as draft", disabled=not acknowledged):
        try:
            changed = apply_suggestions(
                assessment, preview["scenario"], preview["draft"], result.context, selected,
            )
        except ValueError as error:
            st.warning(str(error))
        else:
            st.session_state.pop("_context_suggestion_preview", None)
            message = (
                "Selected suggestions saved as an unconfirmed draft. Review and confirm the context again."
                if changed else "The selected suggestions did not change the recorded context."
            )
            st.session_state["_context_suggestion_notice"] = (st.session_state.widget_generation + 1, message)
            _navigate("context")
    if st.button("Cancel suggestion preview"):
        st.session_state.pop("_context_suggestion_preview", None)
        st.rerun()


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
    st.caption("Step 3 of 6 · Guided clarification")
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
            "Address actions and report generation follow the evaluation step."
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
    st.caption("Step 4 of 6 · Identify and evaluate")
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
        if st.button("Address Threats"):
            _navigate("address")
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
    if "address_state" not in st.session_state:
        st.session_state.address_state = AddressState()
    assessment = st.session_state.assessment
    sync_review(assessment, st.session_state.review_state)
    sync_address(assessment, st.session_state.review_state, st.session_state.address_state)
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
        st.write("Identify → Evaluate → Address → Report")
        waiting_for_resume = render_save_resume()
    if waiting_for_resume:
        if "_progress_intent" in st.session_state:
            st.info("Completing the confirmed browser save operation. Please wait before changing the assessment.")
        else:
            st.info("Choose Resume previous assessment or Start new assessment in Save & Resume. The saved copy has not been overwritten.")
        return
    if st.session_state.view in {"identify", "case_evaluate", "case_address", "case_report"}:
        render_case(assessment, _navigate)
        return
    if st.session_state.view != "scenario" and assessment.scenario.strip():
        with st.expander("Reassess this saved case with the scenario-driven workflow"):
            st.caption("Your previous answers and history stay available. Ambiguous coverage is reviewed rather than assumed.")
            if st.button("Reassess saved case"):
                assessment.case_state = migrate_legacy_assessment(assessment, st.session_state.review_state, st.session_state.address_state)
                _navigate("identify")
    if st.session_state.view == "scenario":
        _scenario_view(assessment)
    elif st.session_state.view == "context":
        _context_view(assessment)
    elif st.session_state.view == "review":
        _review_view(assessment, st.session_state.review_state)
    elif st.session_state.view == "address":
        render_address(assessment, st.session_state.review_state, st.session_state.address_state, _navigate)
    elif st.session_state.view == "report":
        render_report(assessment, st.session_state.review_state, st.session_state.address_state, _navigate)
    else:
        _questions_view(assessment)
