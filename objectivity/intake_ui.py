"""Progressive context clarification; ethical evaluation stays in later stages."""

from collections.abc import Callable

import streamlit as st

from .extraction import ExtractionResult
from .intake import (
    NOT_APPLICABLE, UNKNOWN, confirm_intake, is_current_clarification,
    next_intake_question, question_for_field, save_intake_answer,
)
from .models import Assessment


_LABELS = {
    "role": "Professional role", "decision": "Professional decision or activity",
    "parties": "Relevant people and organisations", "relationship": "Relationship",
    "interests": "Financial interests and who benefits", "pressure": "Reported pressure or influence",
}
_EDIT_LABELS = {
    "role": "Edit role", "decision": "Edit decision", "parties": "Edit parties",
    "relationship": "Edit relationship", "interests": "Edit financial interests", "pressure": "Edit pressure",
}
_NOTES = {"relationship": "relationship_notes", "interests": "interests_notes", "pressure": "pressure_notes"}


def _key(name: str) -> str:
    return f"{st.session_state.widget_generation}:intake:{name}"


def _edit_field(field: str) -> None:
    st.session_state["_intake_edit"] = (st.session_state.widget_generation, field)
    st.rerun()


def _current_edit() -> str | None:
    selected = st.session_state.get("_intake_edit")
    if selected and selected[0] == st.session_state.widget_generation:
        return selected[1]
    st.session_state.pop("_intake_edit", None)
    return None


def _summary(assessment: Assessment, matched: ExtractionResult) -> None:
    st.markdown("**Your context so far**")
    shown = 0
    for field, label in _LABELS.items():
        value = getattr(assessment.context, field)
        clarified = is_current_clarification(assessment, field)
        if value.strip() in {"", "Unknown"} and not clarified and not assessment.confirmed:
            continue  # An extraction gap is a question, not a stack of Unknown fields.
        shown += 1
        content, controls = st.columns([4, 2])
        with content:
            st.write(f"**{label}**")
            st.text("Not known from the current account" if value == "Unknown" else value)
            if assessment.confirmed:
                status = "User-confirmed account · Not independently verified"
            elif clarified:
                status = "Clarified by you · Awaiting confirmation"
            elif value == getattr(matched.context, field) and (
                field not in _NOTES
                or getattr(assessment.context, _NOTES[field]) == getattr(matched.context, _NOTES[field])
            ):
                status = "Extracted from your reported scenario · Unconfirmed"
            else:
                status = "Saved or edited account · Unconfirmed"
            st.caption(status)
            if clarified and field in _NOTES:
                record = assessment.context_clarifications[field]
                if record.choice != UNKNOWN:
                    st.caption(f"Your selection: {record.choice}")
                if record.detail:
                    st.text(record.detail)
            if field == "interests" and is_current_clarification(assessment, "beneficiary"):
                recipient = assessment.context_clarifications["beneficiary"]
                st.caption("Reported beneficiary and interest")
                st.text(recipient.detail if recipient.choice != UNKNOWN else "Recipient or interest not known from the current account")
            notes = getattr(assessment.context, _NOTES[field]) if field in _NOTES else ""
            excerpts = matched.evidence.get(field, ())
            if notes or excerpts:
                with st.expander(f"{label}: details and sources"):
                    if notes:
                        st.text(notes)
                    for excerpt in excerpts:
                        st.text(f"Scenario excerpt: {excerpt}")
                    st.caption("Scenario wording is a reported account, not independently verified evidence.")
        with controls:
            if st.button(_EDIT_LABELS[field], key=_key(f"edit_{field}")):
                _edit_field(field)
    if not shown:
        st.caption("The rules could not establish a reliable summary yet. Start with the focused question below.")
    if st.button("Edit scenario and detailed context", key=_key("open_details")):
        st.session_state["_open_context_details"] = st.session_state.widget_generation
        st.rerun()


def render_intake(
    assessment: Assessment, navigate: Callable[[str], None], matched: ExtractionResult,
) -> None:
    """Show suggestions plus a single adaptive source-clarification question."""
    editing = _current_edit()
    question = question_for_field(editing) if editing else next_intake_question(assessment)
    if question:
        st.subheader("Clarify this detail" if not editing else "Correct this detail")
        st.caption("One context detail at a time · Your answer determines what needs clarification next.")
        with st.expander("Why this question?"):
            if editing:
                st.write(
                    "You chose to correct this detail. Saving a change requires confirmation again "
                    "and refreshes dependent assessment answers. Your wording remains a reported account."
                )
            else:
                st.write(question.why)
        if question.id == "interests":
            st.caption(
                "Distinguish your own or household benefit from a family member's or another "
                "person's interest. A promotion does not automatically mean a financial benefit."
            )
        previous = (
            assessment.context_clarifications.get(question.id)
            if editing and is_current_clarification(assessment, question.id) else None
        )
        with st.form(_key(f"question_{question.id}_{'edit' if editing else 'new'}")):
            if question.options:
                selected_index = question.options.index(previous.choice) if previous else None
                choice = st.radio(question.prompt, question.options, index=selected_index, key=_key(f"choice_{question.id}"))
                detail = st.text_area(
                    "Details for this clarification (optional)",
                    value=previous.detail if previous else "",
                    max_chars=45_000,
                    placeholder="For example, who receives a benefit or what was said. Text is kept as your account.",
                    key=_key(f"detail_{question.id}"),
                )
            else:
                choice = ""
                existing = (
                    previous.detail if previous else
                    getattr(assessment.context, question.field) if editing and question.field in _LABELS else ""
                )
                detail = st.text_input(
                    question.prompt, value="" if existing in {"Unknown", "Not applicable"} else existing,
                    max_chars=45_000 if question.id == "beneficiary" else 100_000,
                    key=_key(f"text_{question.id}"),
                )
            submit = st.form_submit_button("Continue with this answer")
            unknown = st.form_submit_button(UNKNOWN) if not question.options else False
            not_applicable = st.form_submit_button(NOT_APPLICABLE) if not question.options and question.allow_not_applicable else False
        if submit or unknown or not_applicable:
            selected = UNKNOWN if unknown else NOT_APPLICABLE if not_applicable else choice
            try:
                save_intake_answer(assessment, question.id, selected or "", detail)
            except ValueError as error:
                st.warning(str(error))
            else:
                st.session_state.pop("_intake_edit", None)
                navigate("context")
        if editing and st.button("Cancel this edit", key=_key("cancel_edit")):
            st.session_state.pop("_intake_edit", None)
            st.rerun()
        st.caption("An unrecognised detail is not evidence that it is absent. You may record a genuine uncertainty and continue.")
        _summary(assessment, matched)
        return
    _summary(assessment, matched)
    st.success("The context is ready for your review. Remaining uncertainties will stay explicit.")
    st.caption(
        "Check the summary and correct anything missing or misleading. Confirmation records your "
        "account; it does not verify claims, prove a threat or establish that proceeding is acceptable."
    )
    with st.form(_key("confirm")):
        acknowledged = st.checkbox(
            "I have reviewed these details and any remaining uncertainties.", key=_key("acknowledged"),
        )
        submit = st.form_submit_button("Confirm reviewed context")
    if submit:
        if not acknowledged:
            st.warning("Review the context and acknowledge the remaining uncertainties before continuing.")
        else:
            try:
                confirm_intake(assessment)
            except ValueError as error:
                st.warning(str(error))
            else:
                st.session_state.example_loaded = False
                navigate("questions")
    if assessment.confirmed and st.button("Return to clarification", key=_key("return")):
        navigate("questions")
