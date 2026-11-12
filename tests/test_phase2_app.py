"""End-to-end Streamlit interactions for the additive Phase 2 review step."""

from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"


class ThreatReviewAppTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(APP), default_timeout=10).run()
        self.assert_healthy()

    def assert_healthy(self):
        self.assertEqual(len(self.app.exception), 0)
        self.assertLessEqual(len(self.app.radio), 1, "Only one active follow-up may appear")

    def widget(self, kind, label):
        return next(widget for widget in getattr(self.app, kind) if widget.label == label)

    def click(self, label):
        self.widget("button", label).click().run()
        self.assert_healthy()

    def answer(self, choice, explanation=""):
        self.assertEqual(len(self.app.radio), 1)
        self.app.radio[0].set_value(choice)
        self.widget("text_area", "Additional explanation (optional)").input(explanation)
        self.click("Save and continue")

    def text(self):
        kinds = ("markdown", "caption", "text", "info", "warning", "subheader")
        return "\n".join(widget.value for kind in kinds for widget in getattr(self.app, kind))

    def finding_headers(self):
        names = {"### Familiarity", "### Intimidation", "### Self-interest"}
        return {widget.value for widget in self.app.markdown if widget.value in names}

    def example_to_review(self, responsibility="I supervise or review the work"):
        self.click("Load CFO / revenue recognition example")
        self.app.checkbox[0].check()
        self.click("Confirm context and continue")
        for answer in (
            "Implied in the conversation", "Loss of fees or a contract", "No",
            "Frequent personal contact", responsibility,
            "Contract renewal or client retention", "Unknown",
        ):
            self.answer(answer)
        self.assertEqual(len(self.app.radio), 0)
        self.assertIn("Current clarification complete", self.text())
        self.click("Review potential threats")
        self.assertEqual(self.app.session_state["view"], "review")

    def neutral_context(self, relationship="No relevant relationship", interests="No known interest",
                        pressure="No reported pressure"):
        self.widget("text_area", "Your scenario").input(
            "My close friend allegedly threatened my financial bonus."
        )
        self.click("Continue to context confirmation")
        self.widget("text_input", "Your professional role").input("Finance manager")
        self.widget("text_area", "Relevant parties and their roles").input("A supplier and team")
        self.widget("text_area", "Professional decision or activity").input("Select supplier")
        self.widget("selectbox", "Relevant relationship").select(relationship)
        self.widget("selectbox", "Commercial or personal financial interests").select(interests)
        self.widget("selectbox", "Reported pressure or threatened consequences").select(pressure)
        self.app.checkbox[0].check()
        self.click("Confirm context and continue")

    def test_cfo_example_runs_from_phase1_to_evidence_linked_review(self):
        self.example_to_review()
        self.assertIn("basis for believing", self.app.radio[0].label)
        self.assertEqual(self.finding_headers(), {"### Familiarity", "### Intimidation", "### Self-interest"})
        text = self.text()
        self.assertIn("Reasonable and informed third party test", text)
        self.assertIn("answer.pressure_basis", text)
        self.assertIn("answer.relationship_contact", text)
        self.assertIn("answer.commercial_connection", text)
        self.assertIn("not independently verified", text)
        self.assertIn("no change to work", text.lower())
        self.assertIn("future influence", text)
        self.answer("I am not claiming the threats are addressed")
        self.assertEqual(len(self.app.radio), 0)
        self.app.run()
        self.assert_healthy()
        self.assertEqual(self.app.session_state["review_state"].answers["objectivity_basis"].choice,
                         "I am not claiming the threats are addressed")

    def test_unsupported_claims_trigger_targeted_followup_without_approval(self):
        for claim in (
            "Confidence in my own impartiality", "Disclosure of the circumstances",
            "Documentation of the circumstances", "A proposed safeguard",
        ):
            with self.subTest(claim=claim):
                self.setUp()
                self.example_to_review()
                self.answer(claim)
                self.assertEqual(self.app.radio[0].key.split(":")[-1], "choice_basis_challenge")
                self.assertIn("does not", self.text())
                self.answer("A change in circumstances has been reported", "I feel certain now.")
                self.assertEqual(len(self.app.radio), 0)
                text = self.text()
                self.assertIn("Threat requiring action before proceeding", text)
                self.assertIn("not accepted as proof", text)
                self.assertIn("not sufficient by assertion alone", text)

    def test_phase1_answer_edit_from_review_recalculates_and_archives_review(self):
        self.example_to_review()
        self.answer("I am not claiming the threats are addressed")
        self.widget("selectbox", "Choose an answer to review").set_value("relationship_contact")
        self.click("Edit selected answer")
        self.assertEqual(self.app.session_state["view"], "questions")
        self.app.radio[0].set_value("Little or no current personal contact")
        self.click("Save answer")
        self.assertIn("current personal ties", self.app.radio[0].label)
        self.answer("No")
        self.click("Review potential threats")
        self.assertEqual(self.finding_headers(), {"### Intimidation", "### Self-interest"})
        review = self.app.session_state["review_state"]
        self.assertEqual(review.answers, {})
        self.assertTrue(any(item.question_id == "objectivity_basis" for item in review.archive))
        self.assertIn("involvement", self.app.radio[0].label)
        self.answer("I make or recommend the decision")
        self.assertIn("basis for believing", self.app.radio[0].label)

    def test_context_edit_from_review_removes_stale_findings(self):
        self.example_to_review()
        self.answer("Confidence in my own impartiality")
        self.answer("No additional basis identified")
        self.click("Edit scenario or context")
        self.widget("selectbox", "Relevant relationship").select("No relevant relationship")
        self.widget("selectbox", "Commercial or personal financial interests").select("No known interest")
        self.widget("selectbox", "Reported pressure or threatened consequences").select("No reported pressure")
        self.app.checkbox[0].check()
        self.click("Confirm context and continue")
        self.click("Review potential threats")
        self.assertEqual(self.finding_headers(), set())
        self.assertEqual(len(self.app.radio), 0)
        self.assertEqual(self.app.session_state["review_state"].answers, {})
        self.assertTrue(self.app.session_state["review_state"].archive)
        self.assertIn("No potential threat is established", self.text())

    def test_evaluation_answer_edit_and_cancel_preserve_history(self):
        self.example_to_review()
        self.answer("Confidence in my own impartiality")
        self.answer("No additional basis identified")
        self.widget("selectbox", "Choose an evaluation answer to review").set_value("objectivity_basis")
        self.click("Edit selected evaluation answer")
        self.app.radio[0].set_value("Unknown")
        self.click("Cancel answer edit")
        self.assertEqual(self.app.session_state["view"], "review")
        self.assertEqual(self.app.session_state["review_state"].answers["objectivity_basis"].choice,
                         "Confidence in my own impartiality")
        self.widget("selectbox", "Choose an evaluation answer to review").set_value("objectivity_basis")
        self.click("Edit selected evaluation answer")
        self.app.radio[0].set_value("I am not claiming the threats are addressed")
        self.click("Save answer")
        state = self.app.session_state["review_state"]
        self.assertNotIn("basis_challenge", state.answers)
        self.assertTrue(any(item.question_id == "basis_challenge" for item in state.archive))
        self.assertIn("Superseded evaluation answers", "\n".join(item.label for item in self.app.expander))
        self.assertEqual(len(self.app.radio), 0)

    def test_no_concerns_does_not_infer_threats_from_narrative(self):
        self.neutral_context()
        self.click("Review potential threats")
        self.assertEqual(self.finding_headers(), set())
        self.assertEqual(len(self.app.radio), 0)
        self.assertIn("not a finding that threats are absent", self.text())
        self.assertIn("not assurance of Objectivity", self.text())

    def test_unknown_facts_stay_unknown_and_do_not_establish_threat(self):
        self.neutral_context("Unknown", "Unknown", "Unknown")
        for _ in range(3):
            self.answer("Unknown", "I feel intimidated and financially interested.")
        self.click("Review potential threats")
        self.assertEqual(self.finding_headers(), set())
        self.assertEqual(len(self.app.radio), 0)
        self.assertIn("insufficient information", self.text().lower())
        self.assertIn("not independently verified", self.text())

    def test_unknown_phase1_responsibility_is_not_asked_again(self):
        self.example_to_review(responsibility="Unknown")
        self.assertIn("basis for believing", self.app.radio[0].label)
        self.assertIn("responsibility is unresolved", self.text())
        self.assertNotIn("decision_responsibility", self.app.session_state["review_state"].answers)

    def test_review_requires_an_explicit_choice_before_saving(self):
        self.example_to_review()
        self.click("Save and continue")
        self.assertTrue(self.app.warning)
        self.assertEqual(self.app.session_state["review_state"].answers, {})
        self.assertIn("basis for believing", self.app.radio[0].label)


if __name__ == "__main__":
    unittest.main()
