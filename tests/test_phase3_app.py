"""Streamlit regressions for Address interaction, editing and live reports."""

from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

from objectivity.address import CHECKED, DOCUMENT, IMPLEMENTED, NO_ACTION, REVIEW


APP = Path(__file__).resolve().parents[1] / "app.py"


class AddressAppTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(APP), default_timeout=10).run()
        self.assert_healthy()

    def assert_healthy(self):
        self.assertEqual(len(self.app.exception), 0)
        self.assertLessEqual(len(self.app.radio), 1, "At most one active question may appear")

    def widget(self, kind, label):
        return next(widget for widget in getattr(self.app, kind) if widget.label == label)

    def click(self, label):
        self.widget("button", label).click().run()
        self.assert_healthy()

    def text(self):
        return "\n".join(
            item.value for kind in ("markdown", "caption", "text", "info", "warning", "subheader")
            for item in getattr(self.app, kind)
        )

    def answer(self, choice, explanation=""):
        self.assertEqual(len(self.app.radio), 1)
        self.app.radio[0].set_value(choice)
        self.widget("text_area", "Additional explanation (optional)").input(explanation)
        self.click("Save and continue")

    def example_to_address(self):
        self.click("Load CFO / revenue recognition example")
        self.app.checkbox[0].check()
        self.click("Confirm context and continue")
        for choice in (
            "Implied in the conversation", "Loss of fees or a contract", "No",
            "Frequent personal contact", "I supervise or review the work",
            "Contract renewal or client retention", "Unknown",
        ):
            self.answer(choice)
        self.click("Review potential threats")
        self.answer("I am not claiming the threats are addressed")
        self.click("Address Threats")
        self.assertEqual(self.app.session_state["view"], "address")

    def neutral_to_address(self, uncertain=False):
        self.widget("text_area", "Your scenario").input("A reported professional decision.")
        self.click("Continue to context confirmation")
        self.widget("text_input", "Your professional role").input("Finance manager")
        self.widget("text_area", "Relevant parties and their roles").input("Supplier and team")
        self.widget("text_area", "Professional decision or activity").input("Select supplier")
        self.widget("selectbox", "Relevant relationship").select("Unknown" if uncertain else "No relevant relationship")
        self.widget("selectbox", "Commercial or personal financial interests").select("Unknown" if uncertain else "No known interest")
        self.widget("selectbox", "Reported pressure or threatened consequences").select("Unknown" if uncertain else "No reported pressure")
        self.app.checkbox[0].check()
        self.click("Confirm context and continue")
        if uncertain:
            for _ in range(3):
                self.answer("Unknown")
        self.click("Review potential threats")
        self.click("Address Threats")

    def generate_report(self):
        self.click("Generate Ethical Assessment Report")
        self.assertEqual(self.app.session_state["view"], "report")
        report = next(item.value for item in self.app.markdown if item.value.startswith("# Ethical Assessment Report"))
        self.assertNotRegex(report, r"\b(?:answer|review|context)\.[A-Za-z_]")
        self.assertEqual(len(self.app.get("download_button")), 1)
        return report

    def proposed_reviews(self):
        for _ in range(3):
            self.answer(REVIEW)
            self.answer("Proposed, not yet started")
        self.assertEqual(len(self.app.radio), 0)

    def no_remaining_actions(self):
        while self.app.radio:
            self.assertIn(NO_ACTION, self.app.radio[0].options)
            self.answer(NO_ACTION)

    def test_cfo_proposed_safeguards_are_not_completed_or_effective(self):
        self.example_to_address()
        self.proposed_reviews()
        report = self.generate_report()
        self.assertIn("Proposed, not yet started", report)
        self.assertIn("completed implementation is not established", report)
        self.assertIn("does not yet establish", report)
        self.assertNotIn("Recorded stage: Implemented according to my account", report)

    def test_implemented_review_without_independence_preserves_threat(self):
        self.example_to_address()
        self.answer(REVIEW)
        self.answer(IMPLEMENTED)
        self.answer("Reviewer is not independent")
        self.no_remaining_actions()
        report = self.generate_report()
        self.assertIn("Threat remains; further action required", report)
        self.assertIn("Reviewer is not independent", report)
        self.assertIn("implemented", report.lower())
        self.assertIn("does not yet establish", report)

    def test_reported_successful_review_is_conditional_and_does_not_clear_other_threats(self):
        self.example_to_address()
        for choice in (
            REVIEW, IMPLEMENTED,
            "Reviewer is independent of the relevant influences",
            "Relevant competence is established",
            "Can require changes before the decision is final",
            "All relevant aspects of this threat were reviewed",
            "Before the decision or affected work was relied upon",
            "No continuing influence identified in the outcome check",
            CHECKED,
        ):
            self.answer(choice)
        self.no_remaining_actions()
        report = self.generate_report()
        self.assertIn("Conditional support for reduction", report)
        self.assertIn("external independent check", report)
        self.assertIn("not verified by the application", report)
        self.assertIn("does not yet establish that all", report)

    def test_documentation_even_with_reported_external_check_is_not_elimination(self):
        self.example_to_address()
        self.answer(DOCUMENT)
        self.answer(IMPLEMENTED)
        self.answer("The concern, response and outcome")
        self.answer(CHECKED)
        self.no_remaining_actions()
        report = self.generate_report()
        self.assertIn("does not itself establish elimination or reduction", report)
        self.assertIn("Acceptability not yet established", report)

    def test_address_edit_reopens_relevant_followups_and_archives_old_answer(self):
        self.example_to_address()
        self.proposed_reviews()
        self.widget("selectbox", "Choose an Address answer to review").set_value("Familiarity:0:implementation")
        self.click("Edit selected Address answer")
        self.app.radio[0].set_value(IMPLEMENTED)
        self.click("Save Address edit")
        self.assertIn("reviewer independent", self.app.radio[0].label)
        self.assertTrue(self.app.session_state["address_state"].archive)
        self.answer("Unknown")
        report = self.generate_report()
        self.assertIn("Unresolved", report)
        self.assertIn("does not yet establish", report)

    def test_cancel_address_edit_preserves_saved_action(self):
        self.example_to_address()
        self.proposed_reviews()
        self.widget("selectbox", "Choose an Address answer to review").set_value("Familiarity:0:action")
        self.click("Edit selected Address answer")
        self.app.radio[0].set_value(DOCUMENT)
        self.click("Cancel Address edit")
        self.assertEqual(self.app.session_state["address_state"].answers["Familiarity:0:action"].choice, REVIEW)
        self.assertEqual(len(self.app.radio), 0)

    def test_supporting_action_adds_another_measure_without_overwriting_first(self):
        self.example_to_address()
        self.no_remaining_actions()
        self.widget("selectbox", "Threat to address").select("Familiarity").run()
        self.widget("selectbox", "Additional action").select(REVIEW)
        self.click("Add supporting action")
        self.assertIn("implementation status", self.app.radio[0].label)
        self.answer("Requested or in progress")
        actions = self.app.session_state["address_state"].answers
        self.assertEqual(actions["Familiarity:0:action"].choice, NO_ACTION)
        self.assertTrue(any(answer.choice == REVIEW for answer in actions.values()))
        report = self.generate_report()
        self.assertIn("Requested or in progress", report)
        self.assertIn("completed implementation is not established", report)

    def test_earlier_context_change_from_report_invalidates_all_old_actions(self):
        self.example_to_address()
        self.proposed_reviews()
        original = self.generate_report()
        self.click("Edit scenario or context")
        self.widget("selectbox", "Relevant relationship").select("No relevant relationship")
        self.widget("selectbox", "Commercial or personal financial interests").select("No known interest")
        self.widget("selectbox", "Reported pressure or threatened consequences").select("No reported pressure")
        self.app.checkbox[0].check()
        self.click("Confirm context and continue")
        self.click("Review potential threats")
        self.click("Address Threats")
        state = self.app.session_state["address_state"]
        self.assertEqual(state.answers, {})
        self.assertGreaterEqual(len(state.archive), 6)
        current = self.generate_report()
        self.assertNotEqual(current, original)
        self.assertNotIn("Recorded stage: Proposed, not yet started", current)
        self.assertIn("No potential threat is established", current)

    def test_phase2_judgment_change_invalidates_address_assurances(self):
        self.example_to_address()
        self.proposed_reviews()
        self.generate_report()
        self.click("Edit evaluation answers")
        self.widget("selectbox", "Choose an evaluation answer to review").set_value("objectivity_basis")
        self.click("Edit selected evaluation answer")
        self.app.radio[0].set_value("Confidence in my own impartiality")
        self.click("Save answer")
        self.answer("No additional basis identified")
        self.click("Address Threats")
        self.assertEqual(self.app.session_state["address_state"].answers, {})
        self.assertTrue(self.app.session_state["address_state"].archive)
        report = self.generate_report()
        self.assertIn("Confidence in impartiality is not evidence", report)
        self.assertNotIn("Recorded stage: Proposed, not yet started", report)

    def test_phase1_pressure_answer_change_recalculates_report_and_discards_stale_actions(self):
        self.example_to_address()
        self.proposed_reviews()
        self.generate_report()
        self.click("Edit clarification answers")
        self.widget("selectbox", "Choose an answer to review").set_value("pressure_basis")
        self.click("Edit selected answer")
        self.app.radio[0].set_value("My interpretation only")
        self.click("Save answer")
        self.answer("No further supporting information")
        self.click("Review potential threats")
        self.answer("I am not claiming the threats are addressed")
        self.click("Address Threats")
        self.assertEqual(self.app.session_state["address_state"].answers, {})
        self.assertTrue(self.app.session_state["address_state"].archive)
        report = self.generate_report()
        self.assertNotIn("### Intimidation", report)
        self.assertIn("interpretation", report)
        self.assertNotIn("Recorded stage: Proposed, not yet started", report)

    def test_cfo_can_generate_specific_interim_report_before_actions(self):
        self.example_to_address()
        self.assertEqual(len(self.app.radio), 1)
        report = self.generate_report()
        for text in ("CFO", "revenue recognition", "tax advisory", "Familiarity", "Intimidation", "Self-interest"):
            self.assertIn(text, report)
        self.assertIn("Interim", report)
        self.assertIn("Proposed versus implemented actions", report)
        self.assertIn("Prioritised next steps", report)
        self.assertIn("not a certified ethical opinion", report)

    def test_no_established_threat_does_not_invent_action_questions(self):
        self.neutral_to_address()
        self.assertEqual(len(self.app.radio), 0)
        self.assertIn("No potential threat", self.text())
        report = self.generate_report()
        self.assertIn("not establish that threats are absent", report)
        self.assertIn("session-only", report)

    def test_unknown_only_account_is_not_given_acceptability_assurance(self):
        self.neutral_to_address(uncertain=True)
        self.assertEqual(len(self.app.radio), 0)
        report = self.generate_report()
        self.assertIn("Interim", report)
        self.assertRegex(report.lower(), r"(?:insufficient|cannot|not).*?(?:information|establish|acceptable)")
        self.assertIn("not independently verified", report)

    def test_address_requires_explicit_selection(self):
        self.example_to_address()
        self.click("Save and continue")
        self.assertTrue(self.app.warning)
        self.assertEqual(self.app.session_state["address_state"].answers, {})


if __name__ == "__main__":
    unittest.main()
