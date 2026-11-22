"""Six-field suggestions remain drafts, editable and portable across the UI.

The browser-store double checks the acknowledged autosave integration. It does
not claim to exercise an actual browser's localStorage implementation.
"""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from objectivity.address import AddressState
from objectivity.evaluation import evaluate
from objectivity.examples import EXAMPLE_SCENARIO
from objectivity.extraction import extract_context
from objectivity.models import DEFAULT_BASIS, Assessment, Context
from objectivity.progress import export_progress, import_progress
from objectivity.questions import next_question
from objectivity.review import ReviewState


APP = Path(__file__).resolve().parents[1] / "app.py"
CONFIRMATION = (
    "I confirm that these fields reflect my account, including any uncertainty. "
    "This is not independent verification."
)
REPLACEMENT_CONFIRMATION = (
    "Replace the selected fields and require context confirmation again"
)
PROCUREMENT_SCENARIO = (
    "I am a procurement officer choosing between Alpha Tools and Beta Supplies "
    "for a supplier contract. My spouse owns shares in Alpha Tools. "
    "Our purchasing director warned that refusing to favour Alpha Tools could "
    "block my promotion."
)
CREDIT_SCENARIO = (
    "I work as a credit analyst at a community bank. I must approve a loan "
    "application from Cedar Bank. My annual bonus depends on the number of loans "
    "I approve. The credit manager insists that I approve the loan despite "
    "my concerns about repayment."
)
ACTUARY_SCENARIO = (
    "As an actuary, I estimate insurance reserves. My manager insists that I "
    "lower the reserve estimate. My annual bonus depends on reported profit."
)
INVENTORY_SCENARIO = (
    "I am a financial accountant at a manufacturing company. My finance director "
    "has asked me to avoid an inventory write-down to meet profit targets."
)


class AcknowledgedBrowserStore:
    """Minimal acknowledgement protocol double, storing the exact JSON payload."""

    def __init__(self):
        self.data = None
        self.token = None
        self.responses = {}

    def __call__(self, command):
        if command["id"] in self.responses:
            return self.responses[command["id"]]
        if command["op"] == "write":
            if command.get("expected_token") != self.token:
                raise AssertionError("The UI attempted a stale browser write.")
            self.data = command["data"]
            self.token = command["id"]
        response = {
            "id": command["id"], "op": command["op"], "status": "ok",
            "token": self.token, "data": self.data,
        }
        self.responses[command["id"]] = response
        return response


class GeneralPrefillAppTests(unittest.TestCase):
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
        return next(item for item in getattr(self.app, kind) if item.label == label)

    def click(self, label):
        self.widget("button", label).click().run()
        self.healthy()

    def text(self):
        return "\n".join(
            item.value for kind in ("caption", "info", "warning", "markdown", "text")
            for item in getattr(self.app, kind)
        )

    def begin(self, scenario):
        self.widget("text_area", "Your scenario").input(scenario)
        self.click("Continue to context confirmation")
        self.assertEqual(self.app.session_state["view"], "context")

    def confirm(self):
        self.widget("checkbox", CONFIRMATION).check()
        self.click("Confirm context and continue")

    def answer(self, choice):
        self.app.radio[0].set_value(choice)
        self.click("Save and continue")

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

    def assert_unconfirmed(self):
        assessment = self.app.session_state["assessment"]
        self.assertFalse(assessment.confirmed)
        self.assertEqual(assessment.context.basis, DEFAULT_BASIS)
        self.assertEqual(evaluate(assessment).findings, ())
        self.assertIsNone(next_question(assessment))
        self.assertEqual(len(self.app.radio), 0)

    def test_cfo_pasted_scenario_suggests_all_six_fields_with_literal_sources(self):
        self.begin(EXAMPLE_SCENARIO)
        context = self.app.session_state["assessment"].context
        self.assertEqual(context.interests, "Commercial interest")
        self.assertEqual(context.pressure, "Reported pressure or threatened consequences")
        self.assertEqual(context.relationship, "Close personal relationship")
        self.assert_unconfirmed()
        result = extract_context(EXAMPLE_SCENARIO)
        for field in ("role", "parties", "decision", "relationship", "interests", "pressure"):
            with self.subTest(field=field):
                self.assertTrue(result.evidence[field])
                for excerpt in result.evidence[field]:
                    self.assertIn(excerpt, EXAMPLE_SCENARIO)
                    self.assertIn(excerpt, self.text())
        self.assertIn("Financial interests and incentives", self.text())
        self.assertIn("Reported pressure", self.text())
        self.assertIn("not independently verified", self.text().lower())

    def test_procurement_competitors_family_investment_and_promotion_warning(self):
        self.begin(PROCUREMENT_SCENARIO)
        context = self.app.session_state["assessment"].context
        self.assertIn("procurement officer", context.role.lower())
        for party in ("Alpha Tools", "Beta Supplies", "purchasing director", "spouse"):
            self.assertIn(party.lower(), context.parties.lower())
        self.assertIn("supplier", context.decision.lower())
        self.assertEqual(context.relationship, "Other")
        self.assertEqual(context.interests, "Personal financial interest")
        self.assertEqual(context.pressure, "Reported pressure or threatened consequences")
        self.assertIn("promotion", context.pressure_notes.lower())
        self.assert_unconfirmed()

    def test_credit_analyst_own_bonus_and_loan_direction(self):
        self.begin(CREDIT_SCENARIO)
        context = self.app.session_state["assessment"].context
        self.assertIn("credit analyst", context.role.lower())
        self.assertIn("credit manager", context.parties.lower())
        self.assertIn("Cedar Bank", context.parties)
        self.assertIn("loan", context.decision.lower())
        self.assertEqual(context.interests, "Personal financial interest")
        self.assertEqual(context.pressure, "Reported pressure or threatened consequences")
        self.assert_unconfirmed()

    def test_actuary_reserve_work_and_own_performance_payment(self):
        self.begin(ACTUARY_SCENARIO)
        context = self.app.session_state["assessment"].context
        self.assertIn("actuary", context.role.lower())
        self.assertIn("manager", context.parties.lower())
        self.assertIn("reserve", context.decision.lower())
        self.assertEqual(context.interests, "Personal financial interest")
        self.assertEqual(context.pressure, "Reported pressure or threatened consequences")
        self.assert_unconfirmed()

    def test_inventory_profit_targets_and_direction_are_not_missing(self):
        self.begin(INVENTORY_SCENARIO)
        context = self.app.session_state["assessment"].context
        self.assertIn("financial accountant", context.role.lower())
        self.assertIn("finance director", context.parties.lower())
        self.assertIn("inventory", context.decision.lower())
        self.assertEqual(context.interests, "Commercial interest")
        self.assertEqual(context.pressure, "Reported pressure or threatened consequences")
        self.assertIn("profit targets", context.interests_notes.lower())
        self.assert_unconfirmed()

    def test_counterpart_bonus_does_not_become_users_personal_financial_interest(self):
        scenario = (
            "I am an audit manager assessing revenue recognition. The CFO's annual "
            "bonus depends on revenue. The CFO asks me to assess the judgement."
        )
        self.begin(scenario)
        context = self.app.session_state["assessment"].context
        self.assertNotIn(context.interests, (
            "Personal financial interest", "Both commercial and personal interests",
        ))
        self.assertEqual(context.pressure, "Unknown")
        self.assert_unconfirmed()

    def test_incomplete_or_entirely_hypothetical_details_do_not_become_facts(self):
        self.begin(
            "I might be a credit analyst or an actuary. It is unclear what decision "
            "I must make. If the CFO were to threaten me, my bonus might be affected."
        )
        context = self.app.session_state["assessment"].context
        self.assertEqual(context.role, "Unknown")
        self.assertEqual(context.decision, "Unknown")
        self.assertEqual(context.interests, "Unknown")
        self.assertEqual(context.pressure, "Unknown")
        self.assert_unconfirmed()

    def test_six_field_manual_corrections_survive_rerun_and_json_restore(self):
        self.begin(EXAMPLE_SCENARIO)
        self.widget("text_input", "Your professional role").input("Corrected assurance specialist")
        self.widget("text_area", "Relevant parties and their roles").input("Corrected oversight board")
        self.widget("text_area", "Professional decision or activity").input("Corrected supplier review")
        for label, value in (
            ("Relevant relationship", "No relevant relationship"),
            ("Commercial or personal financial interests", "No known interest"),
            ("Reported pressure or threatened consequences", "No reported pressure"),
        ):
            self.widget("selectbox", label).select(value)
        for label in ("Relationship details (optional)", "Interest details (optional)", "Pressure details (optional)"):
            self.widget("text_area", label).input("A correction explicitly recorded by the user.")
        self.confirm()
        before = deepcopy(self.app.session_state["assessment"].context)
        self.app.run()
        self.healthy()
        self.restore(self.snapshot())
        self.assertEqual(self.app.session_state["assessment"].context, before)
        self.click("Edit scenario or context")
        self.assertEqual(self.widget("text_input", "Your professional role").value, before.role)
        self.assertEqual(self.widget("text_area", "Relevant parties and their roles").value, before.parties)
        self.assertEqual(self.widget("text_area", "Professional decision or activity").value, before.decision)
        self.assertEqual(self.widget("selectbox", "Relevant relationship").value, before.relationship)
        self.assertEqual(self.widget("selectbox", "Commercial or personal financial interests").value, before.interests)
        self.assertEqual(self.widget("selectbox", "Reported pressure or threatened consequences").value, before.pressure)

    def test_acknowledged_autosave_and_resume_retain_extraction_then_manual_override(self):
        self.bridge_patch.stop()
        store = AcknowledgedBrowserStore()
        bridge = patch("objectivity.progress_ui.browser_storage", side_effect=store)
        bridge.start()
        self.addCleanup(bridge.stop)
        self.app = AppTest.from_file(str(APP), default_timeout=10).run()
        self.begin(CREDIT_SCENARIO)
        saved_draft = import_progress(store.data)
        self.assertEqual(saved_draft.assessment.context, self.app.session_state["assessment"].context)
        self.assertFalse(saved_draft.assessment.confirmed)
        self.widget("text_input", "Your professional role").input("Manually corrected credit reviewer")
        self.widget("selectbox", "Commercial or personal financial interests").select("Unknown")
        self.confirm()
        before = deepcopy(self.app.session_state["assessment"].context)
        saved = import_progress(store.data)
        self.assertTrue(saved.assessment.confirmed)
        self.assertEqual(saved.assessment.context, before)
        self.app = AppTest.from_file(str(APP), default_timeout=10).run()
        self.healthy()
        self.click("Resume previous assessment")
        self.assertEqual(self.app.session_state["assessment"].context, before)
        self.click("Edit scenario or context")
        self.assertEqual(self.widget("text_input", "Your professional role").value, before.role)
        self.assertEqual(self.widget("selectbox", "Commercial or personal financial interests").value, "Unknown")

    def test_old_saved_unknown_fields_refresh_selectively_and_require_confirmation(self):
        context = Context(
            role="Manually confirmed specialist", parties="Manually recorded parties",
            decision="Manually recorded decision", relationship="No relevant relationship",
            relationship_notes="A manual correction that must be retained.",
        )
        assessment = Assessment(scenario=EXAMPLE_SCENARIO, context=context, confirmed=True)
        snapshot = import_progress(export_progress(assessment, ReviewState(), AddressState(), "context"))
        self.restore(snapshot)
        before = deepcopy(self.app.session_state["assessment"])
        self.click("Preview fresh suggestions")
        self.assertEqual(self.app.session_state["assessment"], before)
        self.assertEqual(set(self.widget("multiselect", "Fields to replace").value), {"interests", "pressure"})
        self.widget("multiselect", "Fields to replace").set_value(["interests", "pressure"])
        self.widget("checkbox", REPLACEMENT_CONFIRMATION).check().run()
        self.click("Apply selected suggestions as draft")
        updated = self.app.session_state["assessment"].context
        for field in ("role", "parties", "decision", "relationship", "relationship_notes"):
            self.assertEqual(getattr(updated, field), getattr(before.context, field))
        self.assertEqual(updated.interests, "Commercial interest")
        self.assertEqual(updated.pressure, "Reported pressure or threatened consequences")
        self.assert_unconfirmed()
        self.restore(self.snapshot())
        self.assertEqual(self.app.session_state["assessment"].context, updated)
        self.assert_unconfirmed()
        self.confirm()
        self.assertTrue(self.app.session_state["assessment"].confirmed)
        self.assertEqual(self.app.session_state["view"], "questions")

    def test_preview_and_cancel_do_not_mutate_context_or_live_answers(self):
        self.begin(EXAMPLE_SCENARIO)
        self.confirm()
        self.answer("Implied in the conversation")
        self.click("Edit scenario or context")
        before = deepcopy(self.app.session_state["assessment"])
        self.widget("text_input", "Your professional role").input("An unsaved manual draft")
        self.click("Preview fresh suggestions")
        self.assertEqual(self.app.session_state["assessment"], before)
        self.click("Cancel suggestion preview")
        self.assertEqual(self.app.session_state["assessment"], before)
        self.assertTrue(self.app.session_state["assessment"].confirmed)

    def test_applying_unchanged_suggestions_retains_confirmed_context_and_answers(self):
        self.begin(EXAMPLE_SCENARIO)
        self.confirm()
        self.answer("Implied in the conversation")
        self.click("Edit scenario or context")
        before = deepcopy(self.app.session_state["assessment"])
        self.click("Preview fresh suggestions")
        self.widget("multiselect", "Fields to replace").set_value(["role"])
        self.widget("checkbox", REPLACEMENT_CONFIRMATION).check().run()
        self.click("Apply selected suggestions as draft")
        self.assertEqual(self.app.session_state["assessment"], before)
        self.assertTrue(self.app.session_state["assessment"].confirmed)

    def test_applied_draft_archives_all_phases_without_retaining_a_report_conclusion(self):
        self.begin(EXAMPLE_SCENARIO)
        self.confirm()
        for choice in (
            "Implied in the conversation", "Loss of fees or a contract", "No",
            "Frequent personal contact", "I supervise or review the work",
            "Contract renewal or client retention", "Unknown",
        ):
            self.answer(choice)
        self.click("Review potential threats")
        self.answer("I am not claiming the threats are addressed")
        self.click("Address Threats")
        for _ in range(3):
            self.answer("No action identified")
        self.click("Generate Ethical Assessment Report")
        self.click("Edit scenario or context")
        self.widget("text_input", "Your professional role").input("Manually corrected reviewer")
        self.widget("selectbox", "Reported pressure or threatened consequences").select("Unknown")
        before = deepcopy(self.app.session_state["assessment"])
        self.click("Preview fresh suggestions")
        self.assertEqual(self.app.session_state["assessment"], before)
        self.widget("multiselect", "Fields to replace").set_value(["pressure"])
        self.widget("checkbox", REPLACEMENT_CONFIRMATION).check().run()
        self.click("Apply selected suggestions as draft")
        assessment = self.app.session_state["assessment"]
        self.assertEqual(assessment.context.role, "Manually corrected reviewer")
        self.assertEqual(assessment.context.pressure, "Reported pressure or threatened consequences")
        self.assertEqual(assessment.answers, {})
        self.assertTrue(assessment.archive)
        for key in ("review_state", "address_state"):
            self.assertEqual(self.app.session_state[key].answers, {})
            self.assertTrue(self.app.session_state[key].archive)
        self.assertEqual(self.app.session_state["view"], "context")
        self.assert_unconfirmed()
        restored = self.snapshot()
        self.assertFalse(restored.assessment.confirmed)
        self.assertTrue(restored.assessment.archive)
        self.assertTrue(restored.review.archive)
        self.assertTrue(restored.address.archive)
        self.assertNotEqual(restored.view, "report")


if __name__ == "__main__":
    unittest.main()
