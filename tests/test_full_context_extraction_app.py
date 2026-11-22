"""Full scenario suggestions stay evidence-linked through all assessment phases.

The acknowledged browser-store double tests the application's storage protocol;
actual Chromium refresh/reopen checks are performed separately by the parent.
"""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from objectivity.address import NO_ACTION
from objectivity.evaluation import evaluate
from objectivity.examples import EXAMPLE_SCENARIO
from objectivity.extraction import extract_context
from objectivity.models import DEFAULT_BASIS
from objectivity.progress import export_progress, import_progress
from objectivity.questions import eligible_questions, next_question
from tests.test_general_prefill_app import AcknowledgedBrowserStore


APP = Path(__file__).resolve().parents[1] / "app.py"
CONFIRMATION = (
    "I confirm that these fields reflect my account, including any uncertainty. "
    "This is not independent verification."
)
FULL_INVENTORY = (
    "You are a financial accountant preparing the year-end financial statements of a manufacturing company. "
    "Your finance director asks you to delay recognising a significant inventory write-down because it would reduce the company's reported profit. "
    "Your annual performance bonus depends partly on achieving the company's profit target. "
    "The finance director says the inventory may recover in value next year and asks you not to raise the issue with the auditors."
)
PROCUREMENT = (
    "I am a procurement officer choosing between Alpha Tools and Beta Supplies for a supplier contract. "
    "My spouse owns shares in Alpha Tools. Our purchasing director warned that refusing to favour "
    "Alpha Tools could block my promotion."
)


class FullContextExtractionAppTests(unittest.TestCase):
    def setUp(self):
        self.bridge_patch = patch("objectivity.progress_ui.browser_storage", return_value=None)
        self.bridge_patch.start()
        self.addCleanup(self.bridge_patch.stop)
        self.app = AppTest.from_file(str(APP), default_timeout=10).run()
        self.healthy()

    def healthy(self):
        self.assertEqual(len(self.app.exception), 0)
        self.assertLessEqual(len(self.app.radio), 1)

    def widget(self, kind, label):
        return next(widget for widget in getattr(self.app, kind) if widget.label == label)

    def click(self, label):
        self.widget("button", label).click().run()
        self.healthy()

    def begin(self, scenario=FULL_INVENTORY):
        self.widget("text_area", "Your scenario").input(scenario)
        self.click("Continue to context confirmation")
        self.assertEqual(self.app.session_state["view"], "context")

    def confirm(self):
        self.widget("checkbox", CONFIRMATION).check()
        self.click("Confirm context and continue")

    def answer(self, choice):
        self.assertEqual(len(self.app.radio), 1)
        self.app.radio[0].set_value(choice)
        self.click("Save and continue")

    def text(self):
        return "\n".join(
            item.value for kind in ("caption", "info", "warning", "markdown", "text")
            for item in getattr(self.app, kind)
        )

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

    def assert_full_context(self, context):
        self.assertIn("financial accountant", context.role.lower())
        self.assertIn("manufacturing company", context.parties.lower())
        self.assertIn("finance director", context.parties.lower())
        self.assertIn("auditors", context.parties.lower())
        self.assertNotIn("external auditors", context.parties.lower())
        party_labels = [label.strip().casefold() for label in context.parties.split(";")]
        self.assertNotIn("company", party_labels, "The same company should not be duplicated under a generic label")
        self.assertEqual(context.relationship, "Other")
        self.assertIn("professional", context.relationship_notes.lower())
        self.assertIn("closeness is not established", context.relationship_notes.lower())
        self.assertEqual(context.interests, "Both commercial and personal interests")
        self.assertIn("Your annual performance bonus", context.interests_notes)
        self.assertNotIn("unclear recipient", context.interests_notes)
        self.assertNotIn("do not establish a personal benefit", context.interests_notes)
        self.assertEqual(context.pressure, "Reported pressure or threatened consequences")
        self.assertIn("delay recognising", context.pressure_notes)
        self.assertIn("not to raise", context.pressure_notes)
        self.assertIn("auditors", context.pressure_notes)
        self.assertIn("year-end financial statements", context.decision.lower())
        self.assertIn("inventory write-down", context.decision.lower())
        self.assertIn("delay", context.decision.lower())
        self.assertIn("not", context.decision.lower())
        self.assertIn("auditors", context.decision.lower())
        self.assertEqual(context.basis, DEFAULT_BASIS)

    def inventory_to_report(self):
        self.begin()
        self.confirm()
        choices = {
            "pressure_basis": "Explicitly stated",
            "pressure_consequence": "Unknown",  # The scenario does not state a sanction.
            "pressure_effect": "No",
            "relationship_relevance": "No relevant personal relationship",
            "commercial_connection": "Fees or profitability",
            "commercial_dependence": "Unknown",
            "personal_connection": "Bonus or performance-related pay",
            "personal_outcome": "Yes",
        }
        for _ in range(12):
            question = next_question(self.app.session_state["assessment"])
            if question is None:
                break
            self.assertIn(question.id, choices)
            self.answer(choices[question.id])
        self.assertIsNone(next_question(self.app.session_state["assessment"]))
        self.click("Review potential threats")
        self.answer("I make or recommend the decision")
        self.answer("I am not claiming the threats are addressed")
        self.click("Address Threats")
        for _ in range(5):
            if not self.app.radio:
                break
            self.assertIn(NO_ACTION, self.app.radio[0].options)
            self.answer(NO_ACTION)
        self.assertEqual(len(self.app.radio), 0)
        self.click("Generate Ethical Assessment Report")
        self.assertEqual(self.app.session_state["view"], "report")
        return next(item.value for item in self.app.markdown if item.value.startswith("# Ethical Assessment Report"))

    def test_full_inventory_draft_records_bonus_pressure_recipients_and_decision(self):
        self.begin()
        assessment = self.app.session_state["assessment"]
        self.assert_full_context(assessment.context)
        self.assertFalse(assessment.confirmed)
        self.assertEqual(evaluate(assessment).findings, ())
        self.assertIsNone(next_question(assessment))
        self.assertEqual(len(self.app.radio), 0)
        self.assertEqual(self.widget("selectbox", "Commercial or personal financial interests").value,
                         "Both commercial and personal interests")
        self.assertEqual(self.widget("selectbox", "Reported pressure or threatened consequences").value,
                         "Reported pressure or threatened consequences")

    def test_every_full_case_suggestion_has_literal_visible_source_evidence(self):
        self.begin()
        result = extract_context(FULL_INVENTORY)
        for field in ("role", "parties", "decision", "relationship", "interests", "pressure"):
            with self.subTest(field=field):
                self.assertTrue(result.evidence[field])
                for excerpt in result.evidence[field]:
                    self.assertIn(excerpt, FULL_INVENTORY)
                    self.assertIn(excerpt, self.text())
        self.assertIn("not independently verified", self.text().lower())
        self.assertNotIn("unknown — no sufficiently clear supported match", self.text().lower())

    def test_confirmation_required_before_both_interest_and_pressure_paths(self):
        self.begin()
        self.click("Confirm context and continue")
        self.assertFalse(self.app.session_state["assessment"].confirmed)
        self.assertEqual(self.app.session_state["view"], "context")
        self.confirm()
        assessment = self.app.session_state["assessment"]
        ids = {question.id for question in eligible_questions(assessment)}
        self.assertTrue({"pressure_basis", "commercial_connection", "personal_connection"}.issubset(ids))
        self.assertNotIn("pressure_relevance", ids, "Do not re-ask whether an explicitly reported request exists")
        self.assertNotIn("interest_relevance", ids, "Do not omit the personal branch behind a commercial-only suggestion")
        self.assertEqual(self.app.radio[0].label, next_question(assessment).prompt)

    def test_draft_json_round_trip_keeps_complete_unconfirmed_sources(self):
        self.begin()
        before = deepcopy(self.app.session_state["assessment"])
        snapshot = self.snapshot()
        self.assertFalse(snapshot.assessment.confirmed)
        self.assertEqual(snapshot.assessment, before)
        self.restore(snapshot)
        self.assert_full_context(self.app.session_state["assessment"].context)
        self.assertEqual(self.app.session_state["view"], "context")
        self.assertEqual(len(self.app.radio), 0)
        self.assertFalse(self.widget("checkbox", CONFIRMATION).value)

    def test_user_corrections_override_suggestions_and_restore_without_reextraction(self):
        self.begin()
        self.widget("text_input", "Your professional role").input("User-corrected financial controller")
        self.widget("text_area", "Relevant parties and their roles").input("Corrected company, directors and auditors")
        self.widget("text_area", "Professional decision or activity").input("Corrected year-end valuation review")
        self.widget("selectbox", "Relevant relationship").select("No relevant relationship")
        self.widget("selectbox", "Commercial or personal financial interests").select("Personal financial interest")
        self.widget("selectbox", "Reported pressure or threatened consequences").select("Other")
        self.widget("text_area", "Interest details (optional)").input("User correction of incentive attribution")
        self.confirm()
        before = deepcopy(self.app.session_state["assessment"].context)
        self.restore(self.snapshot())
        self.assertEqual(self.app.session_state["assessment"].context, before)
        self.click("Edit scenario or context")
        self.assertEqual(self.widget("text_input", "Your professional role").value, before.role)
        self.assertEqual(self.widget("selectbox", "Commercial or personal financial interests").value,
                         "Personal financial interest")
        self.assertEqual(self.widget("selectbox", "Reported pressure or threatened consequences").value, "Other")

    def test_acknowledged_autosave_resume_preserves_both_interests_and_pressure(self):
        self.bridge_patch.stop()
        store = AcknowledgedBrowserStore()
        bridge = patch("objectivity.progress_ui.browser_storage", side_effect=store)
        bridge.start()
        self.addCleanup(bridge.stop)
        self.app = AppTest.from_file(str(APP), default_timeout=10).run()
        self.begin()
        saved_draft = import_progress(store.data)
        self.assert_full_context(saved_draft.assessment.context)
        self.assertFalse(saved_draft.assessment.confirmed)
        self.confirm()
        self.answer("Explicitly stated")
        before = self.snapshot()
        self.app = AppTest.from_file(str(APP), default_timeout=10).run()
        self.click("Resume previous assessment")
        self.assertEqual(self.app.session_state["assessment"], before.assessment)
        self.assertEqual(self.app.session_state["view"], "questions")
        self.assertEqual(self.app.radio[0].label, next_question(before.assessment).prompt)

    def test_full_inventory_reaches_conditional_report_without_invented_safeguards(self):
        report = self.inventory_to_report()
        self.assertIn("Both commercial and personal interests", report)
        self.assertIn("Your annual performance bonus", report)
        self.assertIn("auditors", report)
        self.assertIn("delay recognising", report)
        self.assertIn("Intimidation", report)
        self.assertIn("Self-interest", report)
        self.assertNotIn("### Familiarity", report)
        self.assertIn("No action identified", report)
        self.assertIn("not independently verified", report.lower())
        self.assertIn("does not yet establish", report.lower())
        self.assertNotRegex(report, r"\b(?:answer|review|context)\.[A-Za-z_]")
        snapshot = self.snapshot()
        self.restore(snapshot)
        restored_report = next(item.value for item in self.app.markdown if item.value.startswith("# Ethical Assessment Report"))
        self.assertEqual(restored_report, report)

    def test_earlier_edit_archives_dependent_report_answers(self):
        self.inventory_to_report()
        self.click("Edit scenario or context")
        self.widget("selectbox", "Commercial or personal financial interests").select("No known interest")
        self.widget("selectbox", "Reported pressure or threatened consequences").select("No reported pressure")
        self.confirm()
        assessment = self.app.session_state["assessment"]
        self.assertNotIn("personal_connection", assessment.answers)
        self.assertNotIn("commercial_connection", assessment.answers)
        self.assertNotIn("pressure_basis", assessment.answers)
        self.assertTrue(assessment.archive)
        for key in ("review_state", "address_state"):
            self.assertEqual(self.app.session_state[key].answers, {})
            self.assertTrue(self.app.session_state[key].archive)
        self.assertNotEqual(self.app.session_state["view"], "report")

    def test_cfo_case_keeps_friendship_commercial_interest_and_reported_request(self):
        self.begin(EXAMPLE_SCENARIO)
        context = self.app.session_state["assessment"].context
        self.assertEqual(context.relationship, "Close personal relationship")
        self.assertEqual(context.interests, "Commercial interest")
        self.assertEqual(context.pressure, "Reported pressure or threatened consequences")
        self.assertIn("CFO", context.parties)
        self.assertIn("revenue recognition", context.decision.lower())
        self.assertNotIn("personal bonus", context.interests_notes.lower())

    def test_procurement_conflict_keeps_family_ownership_scope_and_named_suppliers(self):
        self.begin(PROCUREMENT)
        context = self.app.session_state["assessment"].context
        for party in ("Alpha Tools", "Beta Supplies", "purchasing director", "spouse"):
            self.assertIn(party.lower(), context.parties.lower())
        self.assertEqual(context.relationship, "Other")
        self.assertEqual(context.interests, "Personal financial interest")
        self.assertEqual(context.pressure, "Reported pressure or threatened consequences")
        self.assertIn("user's own ownership is not asserted", context.interests_notes)

    def test_incomplete_scenario_keeps_missing_financial_and_pressure_details_unknown(self):
        self.begin("I am an accountant preparing a financial statement. My supervisor asked me to assess an estimate.")
        context = self.app.session_state["assessment"].context
        self.assertIn("accountant", context.role.lower())
        self.assertIn("supervisor", context.parties.lower())
        self.assertEqual(context.interests, "Unknown")
        self.assertEqual(context.pressure, "Unknown")
        self.assertNotIn("bonus", context.interests_notes.lower())
        self.assertNotIn("auditors", context.parties.lower())
        self.assertFalse(self.app.session_state["assessment"].confirmed)


if __name__ == "__main__":
    unittest.main()
