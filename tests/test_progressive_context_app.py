"""Progressive Step 2 uses source suggestions plus focused, portable clarification.

AppTest covers the application/storage protocol; real Chromium checks are run
separately and are needed to establish browser localStorage behaviour.
"""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from objectivity.address import NO_ACTION
from objectivity.evaluation import evaluate
from objectivity.examples import EXAMPLE_SCENARIO
from objectivity.intake import next_intake_question
from objectivity.models import DEFAULT_BASIS, Context
from objectivity.progress import export_progress, import_progress
from objectivity.questions import next_question
from tests.test_general_prefill_app import AcknowledgedBrowserStore
from tests.test_full_context_extraction_app import FULL_INVENTORY


APP = Path(__file__).resolve().parents[1] / "app.py"
REVIEW_CONFIRMATION = "I have reviewed these details and any remaining uncertainties."
UNFAMILIAR = (
    "In my capacity as a heritage collections coordinator, I compare proposed loans "
    "of museum objects to two exhibitions. A board member has an interest in one "
    "exhibition and asks me to favour its application."
)
PROCUREMENT = (
    "In my capacity as a sourcing intelligence associate, I compare quotations "
    "from Quarry Engineering and Rivergate Supplies. My sister holds shares in "
    "Quarry Engineering. Our procurement director receives a consulting fee from "
    "Quarry Engineering and says my promotion depends on favouring it."
)


class ProgressiveContextAppTests(unittest.TestCase):
    def setUp(self):
        self.bridge_patch = patch("objectivity.progress_ui.browser_storage", return_value=None)
        self.bridge_patch.start()
        self.addCleanup(self.bridge_patch.stop)
        self.app = AppTest.from_file(str(APP), default_timeout=10).run()
        self.healthy()

    def healthy(self):
        self.assertEqual(len(self.app.exception), 0)
        self.assertLessEqual(len(self.app.radio), 1, "Only one active clarification may appear")

    def widget(self, kind, label):
        return next(widget for widget in getattr(self.app, kind) if widget.label == label)

    def click(self, label):
        self.widget("button", label).click().run()
        self.healthy()

    def begin(self, scenario):
        self.widget("text_area", "Your scenario").input(scenario)
        self.click("Continue to context confirmation")
        self.assertEqual(self.app.session_state["view"], "context")

    def active(self):
        return next_intake_question(self.app.session_state["assessment"])

    def answer_text(self, text):
        question = self.active()
        self.assertIsNotNone(question)
        self.assertFalse(question.options)
        self.widget("text_input", question.prompt).input(text)
        self.click("Continue with this answer")

    def answer_choice(self, choice, detail=""):
        question = self.active()
        self.assertIsNotNone(question)
        self.assertIn(choice, question.options)
        self.assertEqual(self.app.radio[0].label, question.prompt)
        self.app.radio[0].set_value(choice)
        self.widget("text_area", "Details for this clarification (optional)").input(detail)
        self.click("Continue with this answer")

    def unknown_choice(self, question):
        return next(choice for choice in question.options
                    if "unknown" in choice.lower() or "don't know" in choice.lower())

    def complete_remaining_as_unknown(self):
        seen = []
        for _ in range(12):
            question = self.active()
            if question is None:
                return seen
            self.assertNotIn(question.id, seen, "An explicitly unresolved fact must not be asked endlessly")
            seen.append(question.id)
            if question.options:
                self.answer_choice(self.unknown_choice(question))
            else:
                self.click("I don't know yet")
        self.fail("Progressive clarification did not finish")

    def confirm_reviewed(self):
        self.widget("checkbox", REVIEW_CONFIRMATION).check()
        self.click("Confirm reviewed context")
        self.assertTrue(self.app.session_state["assessment"].confirmed)
        self.assertEqual(self.app.session_state["view"], "questions")

    def snapshot(self):
        return import_progress(export_progress(
            self.app.session_state["assessment"], self.app.session_state["review_state"],
            self.app.session_state["address_state"], self.app.session_state["view"],
        ))

    def restore(self, snapshot):
        self.app.session_state["assessment"] = deepcopy(snapshot.assessment)
        self.app.session_state["review_state"] = deepcopy(snapshot.review)
        self.app.session_state["address_state"] = deepcopy(snapshot.address)
        self.app.session_state["view"] = snapshot.view
        self.app.session_state["widget_generation"] += 1
        for key in ("edit_answer_id", "edit_review_id", "edit_address_id"):
            self.app.session_state[key] = None
        self.app.run()
        self.healthy()

    def test_missing_role_and_decision_are_clarified_in_priority_order(self):
        self.begin("I need help with an unfamiliar professional situation.")
        self.assertEqual(self.active().field, "role")
        self.assertEqual(len(self.app.radio), 0)
        self.answer_text("Heritage collections coordinator")
        self.assertEqual(self.active().field, "decision")
        self.answer_text("Recommend whether to lend a museum collection to an exhibition")
        self.assertEqual(self.active().field, "parties")
        context = self.app.session_state["assessment"].context
        self.assertEqual(context.role, "Heritage collections coordinator")
        self.assertIn("museum collection", context.decision)
        self.assertFalse(self.app.session_state["assessment"].confirmed)
        self.assertEqual(evaluate(self.app.session_state["assessment"]).findings, ())

    def test_established_role_is_not_asked_again_before_missing_decision(self):
        self.begin("I am an auditor. Something concerns me.")
        self.assertEqual(self.active().field, "decision")
        self.assertEqual(self.app.session_state["assessment"].context.role, "Auditor")

    def test_unfamiliar_work_can_be_entered_without_matching_the_extractor(self):
        self.begin(UNFAMILIAR)
        self.assertEqual(self.active().field, "role")
        self.answer_text("Heritage collections coordinator")
        if self.active() and self.active().field == "decision":
            self.answer_text("Recommend a loan of objects to an exhibition")
        context = self.app.session_state["assessment"].context
        self.assertEqual(context.role, "Heritage collections coordinator")
        self.assertNotEqual(context.decision, "Unknown")
        self.app.run()
        self.healthy()
        self.assertNotEqual(self.active().field if self.active() else None, "role")

    def test_explicit_unknown_is_saved_and_does_not_reopen_the_same_question(self):
        self.begin("I need help, but the details are not available.")
        seen = self.complete_remaining_as_unknown()
        self.assertEqual(len(seen), len(set(seen)))
        self.assertTrue(self.app.session_state["assessment"].context_clarifications)
        self.assertFalse(self.app.session_state["assessment"].confirmed)
        snapshot = self.snapshot()
        self.restore(snapshot)
        self.assertIsNone(self.active())
        self.confirm_reviewed()
        self.assertIsNone(next_question(self.app.session_state["assessment"]),
                          "Equivalent broad relevance questions should reuse the explicit Unknown answers")

    def test_known_cfo_suggestions_do_not_require_reentering_the_context(self):
        self.begin(EXAMPLE_SCENARIO)
        self.assertIsNone(self.active())
        self.assertEqual(len(self.app.radio), 0)
        optional = next(expander for expander in self.app.expander
                        if expander.label == "Edit all context details (optional)")
        self.assertFalse(optional.proto.expanded)
        self.assertFalse(self.app.session_state["assessment"].confirmed)
        self.assertEqual(evaluate(self.app.session_state["assessment"]).findings, ())
        self.confirm_reviewed()
        self.assertEqual(next_question(self.app.session_state["assessment"]).id, "pressure_basis")

    def test_progressive_review_requires_its_own_explicit_acknowledgement(self):
        self.begin(EXAMPLE_SCENARIO)
        self.assertIsNone(self.active())
        self.click("Confirm reviewed context")
        self.assertFalse(self.app.session_state["assessment"].confirmed)
        self.assertEqual(self.app.session_state["view"], "context")
        self.assertTrue(self.app.warning)
        self.assertEqual(evaluate(self.app.session_state["assessment"]).findings, ())
        self.confirm_reviewed()

    def test_known_inventory_keeps_both_interests_without_a_repeated_benefit_question(self):
        self.begin(FULL_INVENTORY)
        self.assertIsNone(self.active())
        context = self.app.session_state["assessment"].context
        self.assertEqual(context.interests, "Both commercial and personal interests")
        self.assertIn("annual performance bonus", context.interests_notes)
        self.assertIn("auditors", context.parties.lower())
        self.assertEqual(context.basis, DEFAULT_BASIS)
        self.confirm_reviewed()

    def test_user_can_correct_an_incorrect_suggestion_before_confirmation(self):
        self.begin(EXAMPLE_SCENARIO)
        self.click("Edit role")
        editors = [widget for widget in self.app.text_input if widget.label != "Your professional role"]
        self.assertEqual(len(editors), 1)
        editors[0].input("Assistant engagement reviewer — user correction")
        self.click("Continue with this answer")
        assessment = self.app.session_state["assessment"]
        self.assertEqual(assessment.context.role, "Assistant engagement reviewer — user correction")
        self.assertFalse(assessment.confirmed)
        self.assertEqual(evaluate(assessment).findings, ())
        self.confirm_reviewed()
        self.assertEqual(self.app.session_state["assessment"].context.role,
                         "Assistant engagement reviewer — user correction")

    def test_generic_only_party_suggestion_requests_a_complete_role_list(self):
        self.begin("A professional judgement needs clarification.")
        self.app.session_state["assessment"].context = Context(
            role="Sourcing intelligence associate", parties="Director", decision="Evaluate quotations",
            relationship="Professional relationship only", interests="No known interest", pressure="No reported pressure",
        )
        self.app.session_state["widget_generation"] += 1
        self.app.run()
        self.healthy()
        self.assertEqual(self.active().field, "parties")
        self.answer_text("My sister — shareholder; procurement director — fee recipient; supplier — bidder")
        self.assertIsNone(self.active())
        self.assertIn("procurement director", self.app.session_state["assessment"].context.parties)

    def financial_fixture(self):
        self.begin(PROCUREMENT)
        # These are explicit structured source values for testing ownership
        # clarification; the rule-based narrative recogniser is not required to
        # understand this unfamiliar professional description.
        self.app.session_state["assessment"].context = Context(
            role="Sourcing intelligence associate", decision="Compare supplier quotations",
            parties="Sister — shareholder; procurement director — consulting-fee recipient; Quarry Engineering — supplier",
            relationship="Other", relationship_notes="A sister holds supplier shares; personal closeness is unspecified.",
            interests="Other", interests_notes="A sister holds shares and the director receives a consulting fee.",
            pressure="Reported pressure or threatened consequences",
            pressure_notes="Promotion was linked to favouring one bidder in the reported account.",
        )
        self.app.session_state["widget_generation"] += 1
        self.app.run()
        self.healthy()
        self.assertEqual(self.active().field, "interests")

    def test_family_shareholding_is_not_silently_assigned_to_user(self):
        self.financial_fixture()
        self.answer_choice(
            "A family member (not an established benefit for me)",
            "My sister owns shares in Quarry Engineering. A benefit for me is not established.",
        )
        self.assertIsNone(self.active())
        context = self.app.session_state["assessment"].context
        self.assertEqual(context.interests, "Other")
        self.assertIn("sister", context.interests_notes.lower())
        self.assertNotIn("Both commercial and personal interests", context.interests)
        self.assertFalse(self.app.session_state["assessment"].confirmed)
        self.confirm_reviewed()
        assessment = self.app.session_state["assessment"]
        self.assertEqual(assessment.answers["interest_relevance"].choice, "Other")
        self.assertNotEqual(assessment.context.interests, "Personal financial interest")

    def test_financial_beneficiary_is_asked_only_when_the_selected_owner_needs_it(self):
        self.financial_fixture()
        self.answer_choice("Another person or organisation")
        self.assertEqual(self.active().id, "beneficiary")
        self.answer_text("The procurement director receives the consulting fee from Quarry Engineering")
        self.assertIsNone(self.active())
        context = self.app.session_state["assessment"].context
        self.assertEqual(context.interests, "Other")
        self.assertIn("procurement director", context.interests_notes.lower())
        self.assertIn("consulting fee", context.interests_notes.lower())
        snapshot = self.snapshot()
        self.restore(snapshot)
        self.assertIsNone(self.active())
        self.assertEqual(self.app.session_state["assessment"].context.interests_notes,
                         context.interests_notes)

    def test_own_and_organisation_interests_remain_available_as_two_paths(self):
        self.financial_fixture()
        self.answer_choice(
            "Both me/my household and my organisation",
            "My performance bonus and the organisation's contract income depend on the decision.",
        )
        self.assertIsNone(self.active())
        self.confirm_reviewed()
        assessment = self.app.session_state["assessment"]
        self.assertEqual(assessment.context.interests, "Both commercial and personal interests")
        from objectivity.questions import eligible_questions
        ids = {question.id for question in eligible_questions(assessment)}
        self.assertIn("commercial_connection", ids)
        self.assertIn("personal_connection", ids)

    def test_focused_edit_invalidates_answers_and_actions_from_all_previous_phases(self):
        self.begin(EXAMPLE_SCENARIO)
        self.confirm_reviewed()
        for choice in (
            "Implied in the conversation", "Loss of fees or a contract", "No",
            "Frequent personal contact", "I supervise or review the work",
            "Contract renewal or client retention", "Unknown",
        ):
            self.app.radio[0].set_value(choice)
            self.click("Save and continue")
        self.click("Review potential threats")
        self.app.radio[0].set_value("I am not claiming the threats are addressed")
        self.click("Save and continue")
        self.click("Address Threats")
        for _ in range(5):
            if not self.app.radio:
                break
            self.assertIn(NO_ACTION, self.app.radio[0].options)
            self.app.radio[0].set_value(NO_ACTION)
            self.click("Save and continue")
        self.assertEqual(len(self.app.radio), 0)
        self.click("Generate Ethical Assessment Report")
        self.assertEqual(self.app.session_state["view"], "report")
        self.assertTrue(self.app.session_state["review_state"].answers)
        self.assertTrue(self.app.session_state["address_state"].answers)
        self.click("Edit scenario or context")
        self.click("Edit role")
        editor = next(widget for widget in self.app.text_input if widget.label != "Your professional role")
        editor.input("Engagement reviewer — changed responsibilities")
        self.click("Continue with this answer")
        assessment = self.app.session_state["assessment"]
        self.assertFalse(assessment.confirmed)
        self.assertEqual(assessment.answers, {})
        self.assertTrue(assessment.archive)
        self.assertEqual(self.app.session_state["review_state"].answers, {})
        self.assertTrue(self.app.session_state["review_state"].archive)
        self.assertEqual(self.app.session_state["address_state"].answers, {})
        self.assertTrue(self.app.session_state["address_state"].archive)
        self.assertEqual(evaluate(assessment).findings, ())
        self.confirm_reviewed()
        self.assertEqual(next_question(self.app.session_state["assessment"]).id, "pressure_basis")

    def test_unchanged_financial_edit_prefills_choice_and_preserves_named_beneficiary(self):
        self.financial_fixture()
        self.answer_choice("Another person or organisation")
        self.assertEqual(self.active().id, "beneficiary")
        self.answer_text("The procurement director receives a consulting fee from Quarry Engineering")
        before = deepcopy(self.app.session_state["assessment"])
        self.assertIn("beneficiary", before.context_clarifications)
        self.click("Edit financial interests")
        self.assertEqual(self.app.radio[0].value, "Another person or organisation")
        self.assertEqual(self.widget("text_area", "Details for this clarification (optional)").value, "")
        self.click("Continue with this answer")
        self.assertEqual(self.app.session_state["assessment"], before)
        self.assertIsNone(self.active())
        self.assertIn("consulting fee", self.app.session_state["assessment"].context.interests_notes)
        # A non-empty source explanation is also retained when this field is edited.
        self.click("Edit pressure")
        self.app.radio[0].set_value("Reported pressure or threatened consequences")
        detail = "The director linked promotion to favouring one supplier; no sanction is otherwise stated."
        self.widget("text_area", "Details for this clarification (optional)").input(detail)
        self.click("Continue with this answer")
        self.click("Edit pressure")
        self.assertEqual(self.app.radio[0].value, "Reported pressure or threatened consequences")
        self.assertEqual(self.widget("text_area", "Details for this clarification (optional)").value, detail)
        self.click("Cancel this edit")
        self.assertIsNone(self.active())

    def test_corrected_notes_are_not_presented_as_extracted_just_because_category_matches(self):
        self.begin(EXAMPLE_SCENARIO)
        assessment = self.app.session_state["assessment"]
        self.assertEqual(assessment.context.interests, "Commercial interest")
        corrected_note = "User correction: the renewal is prospective, and its value is not known."
        assessment.context.interests_notes = corrected_note
        self.app.session_state["widget_generation"] += 1
        self.app.run()
        self.healthy()
        captions = [caption.value for caption in self.app.caption]
        self.assertEqual(captions.count("Saved or edited account · Unconfirmed"), 1)
        self.assertEqual(captions.count("Extracted from your reported scenario · Unconfirmed"), 5)
        self.assertIn(corrected_note, [item.value for item in self.app.text])
        self.assertEqual(assessment.context.interests, "Commercial interest")
        self.assertFalse(assessment.confirmed)
        self.assertEqual(evaluate(assessment).findings, ())

    def test_confirmed_legacy_unknowns_remain_visible_as_explicit_uncertainty(self):
        self.begin("The details of this situation are not available.")
        self.app.checkbox[0].check()
        self.click("Confirm context and continue")
        assessment = self.app.session_state["assessment"]
        self.assertTrue(assessment.confirmed)
        self.assertEqual(assessment.context_clarifications, {})
        self.click("Edit scenario or context")
        self.assertIsNone(self.active())
        self.assertEqual(sum(item.value == "Not known from the current account" for item in self.app.text), 6)
        self.assertEqual(sum(item.value == "User-confirmed account · Not independently verified"
                             for item in self.app.caption), 6)
        self.assertIn("Edit role", [button.label for button in self.app.button])
        self.assertIn("Edit financial interests", [button.label for button in self.app.button])
        self.assertTrue(self.app.session_state["assessment"].confirmed)

    def test_partial_clarification_json_restores_next_question_without_stale_widgets(self):
        self.begin("Details of an unfamiliar work issue need clarification.")
        self.answer_text("Public arts acquisitions coordinator")
        self.assertEqual(self.active().field, "decision")
        expected = self.snapshot()
        self.assertFalse(expected.assessment.confirmed)
        self.restore(expected)
        self.assertEqual(self.active().field, "decision")
        self.assertEqual(self.app.session_state["assessment"].context.role,
                         "Public arts acquisitions coordinator")
        self.answer_text("Recommend a grant allocation")
        self.assertEqual(self.app.session_state["assessment"].context.decision,
                         "Recommend a grant allocation")

    def test_partial_progress_autosaves_and_resumes_without_reextracting_the_role(self):
        self.bridge_patch.stop()
        store = AcknowledgedBrowserStore()
        with patch("objectivity.progress_ui.browser_storage", side_effect=store):
            self.app = AppTest.from_file(str(APP), default_timeout=10).run()
            self.begin("A specialist professional assignment needs clarification.")
            self.answer_text("Community investment panel secretary")
            self.assertEqual(self.active().field, "decision")
            saved = import_progress(store.data)
            self.assertFalse(saved.assessment.confirmed)
            self.assertTrue(saved.assessment.context_clarifications)
            self.app = AppTest.from_file(str(APP), default_timeout=10).run()
            self.click("Resume previous assessment")
            self.assertEqual(self.active().field, "decision")
            self.assertEqual(self.app.session_state["assessment"].context.role,
                             "Community investment panel secretary")


if __name__ == "__main__":
    unittest.main()
