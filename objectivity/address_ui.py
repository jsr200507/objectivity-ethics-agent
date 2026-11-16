"""Address-stage interaction and live report presentation."""

from collections.abc import Callable

import streamlit as st

from .address import (
    ACTION_OPTIONS, AddressState, add_supporting_action, assess_address,
    eligible_address_questions, next_address_question, save_address_answer,
)
from .evaluation import evaluate
from .models import Assessment, Question
from .questions import next_question
from .report import build_report, humanize
from .review import ReviewState, next_review_question


def _key(name: str) -> str:
    return f"{st.session_state.widget_generation}:address:{name}"


def _ready(assessment: Assessment, review: ReviewState) -> bool:
    return assessment.confirmed and next_question(assessment) is None and next_review_question(assessment, review) is None


def _earlier_answers(navigate: Callable[[str], None]) -> None:
    with st.expander("Update earlier information"):
        st.caption("Changing earlier facts or judgments invalidates dependent action answers and residual conclusions.")
        if st.button("Edit scenario or context"):
            navigate("context")
        if st.button("Edit clarification answers"):
            navigate("questions")
        if st.button("Edit evaluation answers"):
            navigate("review")


def _address_form(
    assessment: Assessment, review: ReviewState, state: AddressState,
    question: Question, editing: bool, navigate: Callable[[str], None],
) -> None:
    st.subheader("Edit an Address answer" if editing else question.topic)
    with st.expander("Why this question?"):
        st.write(question.why)
    previous = state.answers.get(question.id) if editing else None
    with st.form(_key(f"form:{question.id}")):
        choice = st.radio(
            question.prompt, question.options,
            index=question.options.index(previous.choice) if previous else None,
            key=_key(f"choice:{question.id}"),
        )
        explanation = st.text_area(
            "Additional explanation (optional)", value=previous.explanation if previous else "",
            key=_key(f"explanation:{question.id}"),
        )
        st.caption(
            "Only your structured selection drives the rules. Explanations are retained as "
            "your account; the assistant does not independently verify actions or evidence."
        )
        submitted = st.form_submit_button("Save Address edit" if editing else "Save and continue")
    if submitted:
        if choice is None:
            st.warning("Please choose an option, including Unknown if needed.")
        else:
            try:
                save_address_answer(assessment, review, state, question.id, choice, explanation)
            except ValueError as error:
                st.warning(str(error))
            else:
                navigate("address")
    if editing and st.button("Cancel Address edit"):
        navigate("address")


def _address_review(state: AddressState, questions: list[Question]) -> None:
    answered = {q.id: q for q in questions if q.id in state.answers}
    with st.expander(f"Review Address answers ({len(answered)})"):
        if answered:
            id = st.selectbox(
                "Choose an Address answer to review", list(answered),
                format_func=lambda value: answered[value].prompt, key=_key("review"),
            )
            st.text(state.answers[id].choice)
            if state.answers[id].explanation:
                st.text(state.answers[id].explanation)
            if st.button("Edit selected Address answer"):
                st.session_state.edit_address_id = id
                st.session_state.widget_generation += 1
                st.rerun()
        else:
            st.caption("Saved Address answers will appear here.")
    if state.archive:
        with st.expander(f"Superseded Address answers ({len(state.archive)})"):
            st.caption("Reference history only. These answers are excluded from the current assessment.")
            for record in state.archive:
                st.write(f"**Revision {record.revision} · {record.reason}**")
                st.text(record.prompt)
                st.text(record.answer.choice)
                if record.answer.explanation:
                    st.text(record.answer.explanation)


def _supporting_action(
    assessment: Assessment, review: ReviewState, state: AddressState,
    kinds: list[str], navigate: Callable[[str], None],
) -> None:
    if not kinds:
        return
    with st.expander("Add a supporting action"):
        st.write("Several measures may be needed. Record another action against the threat it addresses.")
        kind = st.selectbox("Threat to address", kinds, key=_key("support_kind"))
        with st.form(_key(f"support_form:{kind}")):
            action = st.selectbox(
                "Additional action", ACTION_OPTIONS[kind], index=None,
                key=_key(f"support_action:{kind}"),
            )
            submitted = st.form_submit_button("Add supporting action")
        if submitted:
            if action is None:
                st.warning("Choose the action you want to record.")
            else:
                try:
                    add_supporting_action(assessment, review, state, kind, action)
                except ValueError as error:
                    st.warning(str(error))
                else:
                    navigate("address")


def render_address(
    assessment: Assessment, review: ReviewState, state: AddressState,
    navigate: Callable[[str], None],
) -> None:
    st.caption("Step 5 of 6 · Address")
    st.subheader("Address Threats")
    if not _ready(assessment, review):
        st.warning("Earlier clarification or evaluation needs attention before actions can be reassessed.")
        _earlier_answers(navigate)
        return
    evaluation = evaluate(assessment, review.answers)
    st.write(
        "Consider eliminating the circumstances, applying effective safeguards, or declining "
        "or ending the activity where necessary. Potential threats are not proven bias or misconduct."
    )
    if evaluation.findings:
        st.write("**Potential threats to address:** " + ", ".join(f.kind for f in evaluation.findings))
        with st.expander("Threats and recorded facts to address"):
            for finding in evaluation.findings:
                st.write(f"**{finding.kind} · {finding.outcome}**")
                st.write(finding.summary)
                for evidence in finding.evidence:
                    st.text(f"{evidence.label}: {evidence.value}")
                st.caption("User-confirmed account and recorded answers; not independently verified by the app.")
    else:
        st.info("No potential threat is established by the current structured information. Uncertainties still need attention; no action questionnaire is invented.")
    questions = eligible_address_questions(assessment, review, state)
    answered = sum(q.id in state.answers for q in questions)
    st.progress(
        answered / len(questions) if questions else 1.0,
        text=f"Address · {answered} of {len(questions)} currently relevant questions answered",
    )
    edit_id = st.session_state.get("edit_address_id")
    question = next((q for q in questions if q.id == edit_id), None) if edit_id else next_address_question(assessment, review, state)
    if question:
        _address_form(assessment, review, state, question, bool(edit_id), navigate)
    else:
        st.caption("All currently selected action questions are answered. That does not itself establish acceptability.")
        _supporting_action(assessment, review, state, [f.kind for f in evaluation.findings], navigate)
    result = assess_address(assessment, review, state)
    st.subheader("Residual threats and current evidence")
    for outcome in result.outcomes:
        st.write(f"**{outcome.kind} · {outcome.status}**")
        for reason in outcome.reasoning:
            st.markdown(f"- {humanize(reason)}")
        for action in outcome.actions:
            st.write(f"{action.description} — {action.stage}")
            st.caption(action.evidence_status)
        for gap in outcome.unknowns:
            st.markdown(f"- Still needed: {humanize(gap)}")
    st.write(humanize(result.conclusion))
    st.write(humanize(result.third_party))
    _address_review(state, questions)
    _earlier_answers(navigate)
    if st.button("Generate Ethical Assessment Report"):
        navigate("report")
    st.caption("You can generate an interim report while information is incomplete. Unsaved form changes are not included.")


def render_report(
    assessment: Assessment, review: ReviewState, state: AddressState,
    navigate: Callable[[str], None],
) -> None:
    st.caption("Step 6 of 6 · Report")
    if not _ready(assessment, review):
        st.warning("The supporting account has changed. Complete the earlier clarification and evaluation before generating a current report.")
        _earlier_answers(navigate)
        return
    # Build afresh, including on download reruns. There is no cached verdict.
    report = build_report(assessment, review, state)
    st.markdown(report)
    st.download_button(
        "Download report (Markdown)", data=report,
        file_name=f"objectivity-assessment-revision-{assessment.revision}.md",
        mime="text/markdown",
    )
    st.caption("A download is a revision-specific snapshot. Return and regenerate it if any information changes.")
    if st.button("Return to Address Threats"):
        navigate("address")
    _earlier_answers(navigate)
