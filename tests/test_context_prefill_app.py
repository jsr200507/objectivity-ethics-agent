"""Context suggestions remain editable, unconfirmed and portable source data."""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from objectivity.address import AddressState
from objectivity.evaluation import evaluate
from objectivity.examples import EXAMPLE_SCENARIO
from objectivity.models import DEFAULT_BASIS, Assessment, Context
from objectivity.progress import export_progress, import_progress
from objectivity.questions import next_question
from objectivity.review import ReviewState


APP = Path(__file__).resolve().parents[1] / "app.py"
INVENTORY_SCENARIO = (
    "I am a financial accountant at a manufacturing company. My finance director "
    "has asked me to avoid an inventory write-down to meet profit targets."
)


class ContextPrefillAppTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("objectivity.progress_ui.browser_storage", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = AppTest.from_file(str(APP), default_timeout=10).run()
        self.healthy()

    def healthy(self):
        self.assertEqual(len(self.app.exception), 0)
        self.assertLessEqual(len(self.app.radio), 1)

    def widget(self, kind, label):
        return next(item for item in getattr(self.app, kind) if item.label == label)

    def click(self, label):
        self.widget("button", label).click().run()
        self.healthy()

    def begin(self, scenario):
        self.widget("text_area", "Your scenario").input(scenario)
        self.click("Continue to context confirmation")
        self.assertEqual(self.app.session_state["view"], "context")

    def text(self):
        return "\n".join(
            item.value
            for kind in ("caption", "info", "warning", "markdown", "text")
            for item in getattr(self.app, kind)
        )

    def confirm(self):
        self.app.checkbox[0].check()
        self.click("Confirm context and continue")

    def answer(self, choice):
        self.assertEqual(len(self.app.radio), 1)
        self.app.radio[0].set_value(choice)
        self.click("Save and continue")

    def current_snapshot(self):
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

    def test_pasted_cfo_scenario_prefills_supported_fields_without_teams(self):
        self.begin(EXAMPLE_SCENARIO)
        context = self.app.session_state["assessment"].context
        self.assertIn("audit manager", context.role.lower())
        self.assertIn("cfo", context.parties.lower())
        self.assertIn("revenue recognition", context.decision.lower())
        self.assertEqual(context.relationship, "Close personal relationship")
        self.assertNotIn("audit team", context.parties.lower())
        self.assertNotIn("tax advisory team", context.parties.lower())
        self.assertEqual(self.widget("text_input", "Your professional role").value, context.role)
        self.assertEqual(self.widget("text_area", "Relevant parties and their roles").value, context.parties)
        self.assertEqual(self.widget("text_area", "Professional decision or activity").value, context.decision)
        self.assertFalse(self.app.session_state["assessment"].confirmed)
        self.assertEqual(context.basis, DEFAULT_BASIS)

    def test_inventory_scenario_prefills_financial_accountant_and_decision(self):
        self.begin(INVENTORY_SCENARIO)
        context = self.app.session_state["assessment"].context
        self.assertIn("financial accountant", context.role.lower())
        self.assertIn("finance director", context.parties.lower())
        self.assertIn("inventory", context.decision.lower())
        self.assertIn("write-down", context.decision.lower())
        self.assertEqual(context.relationship, "Unknown")
        self.assertEqual(context.interests, "Unknown")
        self.assertEqual(context.pressure, "Unknown")

    def test_missing_information_is_unknown_and_not_confirmed(self):
        self.begin("I need help with a situation.")
        context = self.app.session_state["assessment"].context
        self.assertEqual((context.role, context.parties, context.decision, context.relationship), ("Unknown",) * 4)
        self.assertFalse(self.app.session_state["assessment"].confirmed)

    def test_ambiguous_roles_and_decisions_are_not_invented(self):
        self.begin(
            "I might be the audit manager or financial accountant. "
            "Either revenue recognition or an inventory write-down may be involved."
        )
        context = self.app.session_state["assessment"].context
        self.assertEqual(context.role, "Unknown")
        self.assertEqual(context.decision, "Unknown")
        self.assertEqual(context.relationship, "Unknown")

    def test_suggestions_have_no_ethical_effect_before_confirmation(self):
        self.begin(EXAMPLE_SCENARIO)
        assessment = self.app.session_state["assessment"]
        self.assertEqual(evaluate(assessment).findings, ())
        self.assertIsNone(next_question(assessment))
        self.assertEqual(len(self.app.radio), 0)
        self.click("Confirm context and continue")
        self.assertTrue(self.app.warning)
        self.assertFalse(assessment.confirmed)
        self.assertEqual(self.app.session_state["view"], "context")
        self.assertIn("suggest", self.text().lower())
        self.assertIn("not independently verified", self.text().lower())
        self.confirm()
        self.assertTrue(self.app.session_state["assessment"].confirmed)
        self.assertEqual(self.app.session_state["view"], "questions")

    def test_every_context_field_can_be_replaced_and_survives_rerun(self):
        self.begin(INVENTORY_SCENARIO)
        replacements = {
            "Your professional role": "Management accountant",
            "Relevant parties and their roles": "Operations director and purchasing team",
            "Professional decision or activity": "Review a supplier decision",
            "Relationship details (optional)": "No personal ties are reported.",
            "Interest details (optional)": "A performance-related payment is possible.",
            "Pressure details (optional)": "No pressure is reported in this revised account.",
        }
        self.widget("text_input", "Your professional role").input(replacements["Your professional role"])
        for label, value in replacements.items():
            if label != "Your professional role":
                self.widget("text_area", label).input(value)
        self.widget("selectbox", "Relevant relationship").select("No relevant relationship")
        self.widget("selectbox", "Commercial or personal financial interests").select("Personal financial interest")
        self.widget("selectbox", "Reported pressure or threatened consequences").select("No reported pressure")
        self.confirm()
        self.app.run()
        self.healthy()
        context = self.app.session_state["assessment"].context
        self.assertEqual(context, Context(
            role="Management accountant", parties="Operations director and purchasing team",
            decision="Review a supplier decision", relationship="No relevant relationship",
            interests="Personal financial interest", pressure="No reported pressure",
            relationship_notes=replacements["Relationship details (optional)"],
            interests_notes=replacements["Interest details (optional)"],
            pressure_notes=replacements["Pressure details (optional)"],
        ))
        self.click("Edit scenario or context")
        self.assertEqual(self.widget("text_input", "Your professional role").value, "Management accountant")
        self.assertEqual(self.widget("text_area", "Professional decision or activity").value, "Review a supplier decision")
        self.assertFalse(self.app.checkbox[0].value)

    def test_unconfirmed_suggestions_roundtrip_through_progress_json(self):
        self.begin(INVENTORY_SCENARIO)
        before = deepcopy(self.app.session_state["assessment"])
        snapshot = self.current_snapshot()
        self.assertEqual(snapshot.assessment.context, before.context)
        self.assertFalse(snapshot.assessment.confirmed)
        self.assertEqual(snapshot.view, "context")
        self.restore(snapshot)
        self.assertEqual(self.app.session_state["assessment"], before)
        self.assertEqual(self.widget("text_input", "Your professional role").value, before.context.role)

    def test_confirmed_corrections_roundtrip_without_extraction_overwrite(self):
        self.begin(INVENTORY_SCENARIO)
        self.widget("text_input", "Your professional role").input("Corrected controller")
        self.widget("text_area", "Relevant parties and their roles").input("Corrected director and accountant")
        self.widget("text_area", "Professional decision or activity").input("Corrected inventory evaluation")
        self.widget("selectbox", "Relevant relationship").select("Other")
        self.confirm()
        snapshot = self.current_snapshot()
        self.restore(snapshot)
        self.click("Edit scenario or context")
        self.assertEqual(self.widget("text_input", "Your professional role").value, "Corrected controller")
        self.assertEqual(self.widget("text_area", "Relevant parties and their roles").value, "Corrected director and accountant")
        self.assertEqual(self.widget("text_area", "Professional decision or activity").value, "Corrected inventory evaluation")
        self.assertEqual(self.widget("selectbox", "Relevant relationship").value, "Other")

    def test_imported_unconfirmed_manual_fields_are_not_reextracted(self):
        assessment = Assessment(scenario=EXAMPLE_SCENARIO, context=Context(
            role="A manually saved role", parties="Manually saved parties",
            decision="A manually saved decision", relationship="Other",
            relationship_notes="These are retained draft details.",
        ))
        snapshot = import_progress(export_progress(assessment, ReviewState(), AddressState(), "context"))
        self.restore(snapshot)
        self.assertEqual(self.widget("text_input", "Your professional role").value, "A manually saved role")
        self.assertEqual(self.widget("text_area", "Relevant parties and their roles").value, "Manually saved parties")
        self.assertEqual(self.widget("text_area", "Professional decision or activity").value, "A manually saved decision")
        self.assertEqual(self.widget("selectbox", "Relevant relationship").value, "Other")
        self.assertFalse(self.app.session_state["assessment"].confirmed)

    def test_example_loader_keeps_existing_interest_and_pressure_paths(self):
        self.click("Load CFO / revenue recognition example")
        context = self.app.session_state["assessment"].context
        self.assertIn("audit manager", context.role.lower())
        self.assertIn("cfo", context.parties.lower())
        self.assertNotIn("tax advisory team", context.parties.lower())
        self.assertEqual(context.interests, "Commercial interest")
        self.assertEqual(context.pressure, "Reported pressure or threatened consequences")
        self.assertFalse(self.app.session_state["assessment"].confirmed)

    def test_confirmed_context_edit_invalidates_existing_all_phase_answers(self):
        self.click("Load CFO / revenue recognition example")
        self.confirm()
        for answer in (
            "Implied in the conversation", "Loss of fees or a contract", "No",
            "Frequent personal contact", "I supervise or review the work",
            "Contract renewal or client retention", "Unknown",
        ):
            self.answer(answer)
        self.click("Review potential threats")
        self.answer("I am not claiming the threats are addressed")
        self.click("Address Threats")
        for _ in range(3):
            self.answer("No action identified")
        self.click("Generate Ethical Assessment Report")
        self.click("Edit scenario or context")
        self.widget("text_input", "Your professional role").input("Independent review manager")
        self.confirm()
        assessment = self.app.session_state["assessment"]
        self.assertEqual(assessment.context.role, "Independent review manager")
        self.assertEqual(assessment.answers, {})
        self.assertTrue(assessment.archive)
        self.assertEqual(self.app.session_state["review_state"].answers, {})
        self.assertTrue(self.app.session_state["review_state"].archive)
        self.assertEqual(self.app.session_state["address_state"].answers, {})
        self.assertTrue(self.app.session_state["address_state"].archive)
        self.assertEqual(self.app.session_state["view"], "questions")


if __name__ == "__main__":
    unittest.main()
