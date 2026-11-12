"""Interaction checks through Streamlit's real script/session test harness."""

from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"


class AppFlowTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(APP), default_timeout=10).run()
        self.assert_healthy()

    def assert_healthy(self):
        self.assertEqual(len(self.app.exception), 0)
        self.assertLessEqual(len(self.app.radio), 1, "Only one active follow-up may be shown")

    def widget(self, kind, label):
        return next(widget for widget in getattr(self.app, kind) if widget.label == label)

    def click(self, label):
        self.widget("button", label).click().run()
        self.assert_healthy()

    def context(self, relationship="No relevant relationship", interests="No known interest",
                pressure="No reported pressure"):
        self.widget("text_area", "Your scenario").input(
            "A professional decision needs consideration."
        )
        self.click("Continue to context confirmation")
        self.widget("text_input", "Your professional role").input("Finance manager")
        self.widget("text_area", "Relevant parties and their roles").input("A supplier and my team")
        self.widget("text_area", "Professional decision or activity").input("Approve a supplier")
        self.set_routes(relationship, interests, pressure)
        self.app.checkbox[0].check()
        self.click("Confirm context and continue")

    def set_routes(self, relationship, interests, pressure):
        self.widget("selectbox", "Relevant relationship").select(relationship)
        self.widget("selectbox", "Commercial or personal financial interests").select(interests)
        self.widget("selectbox", "Reported pressure or threatened consequences").select(pressure)

    def answer(self, choice, explanation=""):
        self.assertEqual(len(self.app.radio), 1)
        self.app.radio[0].set_value(choice)
        self.widget("text_area", "Additional explanation (optional)").input(explanation)
        self.click("Save and continue")

    def edit(self, question_id, choice):
        self.widget("selectbox", "Choose an answer to review").set_value(question_id)
        self.click("Edit selected answer")
        self.app.radio[0].set_value(choice)
        self.click("Save answer")

    def assert_complete(self):
        self.assertEqual(len(self.app.radio), 0)
        self.assertIn("Current clarification complete", [s.value for s in self.app.subheader])

    def test_homepage_and_empty_scenario(self):
        self.assertEqual(self.app.title[0].value, "Objectivity Ethics Assistant")
        self.click("Continue to context confirmation")
        self.assertTrue(self.app.warning)
        self.assertEqual(self.app.session_state["view"], "scenario")

    def test_narrative_not_extracted_and_confirmation_required(self):
        self.app.text_area[0].input("My friend the CFO threatened to cancel a contract.")
        self.click("Continue to context confirmation")
        self.assertEqual(self.app.text_input[0].value, "")
        self.assertEqual([s.value for s in self.app.selectbox], ["Unknown"] * 3)
        self.click("Confirm context and continue")
        self.assertTrue(self.app.warning)
        self.assertFalse(self.app.session_state["assessment"].confirmed)
        self.app.checkbox[0].check()
        self.click("Confirm context and continue")
        self.assertTrue(self.app.warning)
        self.assertFalse(self.app.session_state["assessment"].confirmed)

    def test_familiarity_path_and_edit_reselects_dependent_questions(self):
        self.context(relationship="Close personal relationship")
        self.answer("Frequent personal contact", "We meet weekly.")
        self.answer("I make or recommend the decision")
        self.assert_complete()
        self.app.run()
        self.assertEqual(
            self.app.session_state["assessment"].answers["relationship_contact"].explanation,
            "We meet weekly.",
        )
        self.edit("relationship_contact", "Little or no current personal contact")
        assessment = self.app.session_state["assessment"]
        self.assertNotIn("relationship_influence", assessment.answers)
        self.assertIn("current personal ties", self.app.radio[0].label)
        self.answer("No")
        self.assert_complete()
        self.assertTrue(assessment.archive)

    def test_commercial_path_and_context_edit_to_personal(self):
        self.context(interests="Commercial interest")
        self.answer("Contract renewal or client retention")
        self.answer("Unknown")
        self.assert_complete()
        self.click("Edit scenario or context")
        self.assertFalse(self.app.checkbox[0].value)
        self.widget("selectbox", "Commercial or personal financial interests").select(
            "Personal financial interest"
        )
        self.app.checkbox[0].check()
        self.click("Confirm context and continue")
        self.assertNotIn("commercial_connection", self.app.session_state["assessment"].answers)
        self.assertIn("personal financial interest", self.app.radio[0].label)
        self.answer("Bonus or performance-related pay")
        self.answer("Yes")
        self.assert_complete()

    def test_intimidation_interpretation_branch_then_explicit_branch(self):
        self.context(pressure="Reported pressure or threatened consequences")
        self.answer("My interpretation only")
        self.assertIn("supporting your interpretation", self.app.radio[0].label)
        self.answer("No further supporting information")
        self.assert_complete()
        self.edit("pressure_basis", "Explicitly stated")
        self.answer("Employment or career consequences")
        self.answer("Yes")
        self.assertIn("Which part of your work changed", self.app.radio[0].label)
        self.answer("Procedures or evidence gathering")
        self.assert_complete()

    def test_unknown_other_and_explanation_are_not_inferred(self):
        self.context(relationship="Other", interests="Unknown", pressure="Not applicable")
        self.answer("Unknown", "My bonus depends on this. Someone threatened me.")
        self.assertIn("financial or commercial interest", self.app.radio[0].label)
        self.answer("Other", "A very close friend.")
        self.assert_complete()
        assessment = self.app.session_state["assessment"]
        self.assertEqual(set(assessment.answers), {"relationship_relevance", "interest_relevance"})

    def test_example_runs_all_three_topics(self):
        self.click("Load CFO / revenue recognition example")
        self.assertFalse(self.app.session_state["assessment"].confirmed)
        self.app.checkbox[0].check()
        self.click("Confirm context and continue")
        self.answer("Implied in the conversation")
        self.answer("Loss of fees or a contract")
        self.answer("No")
        self.answer("Frequent personal contact")
        self.answer("I supervise or review the work")
        self.answer("Contract renewal or client retention")
        self.answer("Unknown")
        self.assert_complete()
        self.assertEqual(len(self.app.session_state["assessment"].answers), 7)
        self.assertTrue(any("not included" in item.value for item in self.app.info))

    def test_no_relevant_routes_does_not_invent_questions(self):
        self.context()
        self.assert_complete()
        self.assertEqual(self.app.session_state["assessment"].answers, {})

    def test_unselected_question_guard_and_saved_answer_survives_rerun(self):
        self.context(relationship="Close personal relationship")
        self.click("Save and continue")
        self.assertTrue(self.app.warning)
        self.assertEqual(self.app.session_state["assessment"].answers, {})
        self.answer("Other", "Some context")
        self.app.run()
        answer = self.app.session_state["assessment"].answers["relationship_contact"]
        self.assertEqual(answer.choice, "Other")
        self.assertEqual(answer.explanation, "Some context")
        self.assertIn("involvement", self.app.radio[0].label)

    def test_cancel_edits_and_reset_confirmation(self):
        self.context(relationship="Close personal relationship")
        self.answer("Unknown")
        self.click("Edit selected answer")
        self.app.radio[0].set_value("Not applicable")
        self.click("Cancel answer edit")
        self.assertEqual(self.app.session_state["assessment"].answers["relationship_contact"].choice, "Unknown")
        self.click("Edit scenario or context")
        self.app.text_input[0].input("Changed role")
        self.click("Cancel context edit")
        self.assertEqual(self.app.session_state["assessment"].context.role, "Finance manager")
        self.click("Start a new scenario")
        self.click("Keep current scenario")
        self.assertTrue(self.app.session_state["assessment"].answers)
        self.click("Start a new scenario")
        self.click("Discard and start again")
        self.assertEqual(self.app.session_state["view"], "scenario")
        self.assertEqual(self.app.session_state["assessment"].answers, {})


if __name__ == "__main__":
    unittest.main()
