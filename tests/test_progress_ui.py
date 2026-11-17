"""Save/resume UX with an acknowledged browser-store protocol double.

These checks exercise Streamlit reruns and restoration. Actual storage refresh,
reopen and file-upload/download behavior are tested separately in Chromium.
"""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from objectivity.address import AddressState, REVIEW, save_address_answer, sync_address
from objectivity.examples import EXAMPLE_CONTEXT, EXAMPLE_SCENARIO
from objectivity.models import Assessment, Context
from objectivity.progress import MAX_PROGRESS_BYTES, export_progress, import_progress
from objectivity.progress_ui import INTENT, _queue
from objectivity.questions import confirm_context, save_answer
from objectivity.review import ReviewState, save_review_answer, sync_review


APP = Path(__file__).resolve().parents[1] / "app.py"


def draft(scenario="A saved professional situation", role="Saved manager"):
    return export_progress(
        Assessment(scenario=scenario, context=Context(role=role)),
        ReviewState(), AddressState(), "context",
    )


def cfo_report_progress():
    assessment = Assessment()
    confirm_context(assessment, EXAMPLE_SCENARIO, deepcopy(EXAMPLE_CONTEXT))
    for id, choice in (
        ("pressure_basis", "Implied in the conversation"),
        ("pressure_consequence", "Loss of fees or a contract"),
        ("pressure_effect", "No"),
        ("relationship_contact", "Frequent personal contact"),
        ("relationship_influence", "I supervise or review the work"),
        ("commercial_connection", "Contract renewal or client retention"),
        ("commercial_dependence", "Unknown"),
    ):
        save_answer(assessment, id, choice)
    review = ReviewState()
    sync_review(assessment, review)
    save_review_answer(assessment, review, "objectivity_basis", "I am not claiming the threats are addressed")
    address = AddressState()
    sync_address(assessment, review, address)
    for kind in ("Familiarity", "Intimidation", "Self-interest"):
        save_address_answer(assessment, review, address, f"{kind}:0:action", REVIEW)
        save_address_answer(assessment, review, address, f"{kind}:0:implementation", "Proposed, not yet started")
    return export_progress(assessment, review, address, "report")


class BrowserStore:
    def __init__(self, data=None, unavailable=False):
        self.data = data
        self.token = "existing-1" if data is not None else None
        self.unavailable = unavailable
        self.counter = 1
        self.responses = {}
        self.calls = []

    def external_change(self, data):
        self.counter += 1
        self.token = f"external-{self.counter}"
        self.data = data

    def __call__(self, command):
        command = deepcopy(command)
        self.calls.append(command)
        if command["id"] in self.responses:
            return self.responses[command["id"]]
        response = {"id": command["id"], "op": command["op"], "token": self.token, "data": self.data}
        if self.unavailable:
            response.update(status="unavailable", reason="Storage is blocked for this test")
        elif command["op"] == "read":
            response["status"] = "ok"
        elif command.get("expected_token") != self.token:
            response["status"] = "conflict"
        else:
            self.counter += 1
            self.token = f"saved-{self.counter}"
            self.data = None if command["op"] == "clear" else command["data"]
            response.update(status="ok", token=self.token, data=self.data)
        self.responses[command["id"]] = response
        return response


class DelayedBrowserStore(BrowserStore):
    """Hold an outstanding write before its CAS check to reproduce tab races."""

    def __init__(self):
        super().__init__()
        self.hold_writes = False

    def __call__(self, command):
        if self.hold_writes and command["op"] == "write" and command["id"] not in self.responses:
            self.calls.append(deepcopy(command))
            return None
        return super().__call__(command)


class ProgressUITests(unittest.TestCase):
    def start(self, store=None, response=None):
        self.store = store
        patcher = patch("objectivity.progress_ui.browser_storage", side_effect=store) if store else patch(
            "objectivity.progress_ui.browser_storage", return_value=response
        )
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

    def text(self):
        return "\n".join(
            widget.value for kind in ("caption", "warning", "info", "markdown", "text")
            for widget in getattr(self.app, kind)
        )

    def download_labels(self):
        return {item.proto.label for item in self.app.get("download_button")}

    def begin_scenario(self, scenario="Current professional situation"):
        self.widget("text_area", "Your scenario").input(scenario)
        self.click("Continue to context confirmation")

    def test_missing_browser_copy_only_saves_submitted_progress(self):
        self.start(BrowserStore())
        self.assertIsNone(self.store.data)
        self.assertEqual(self.app.session_state["_browser_save_state"].mode, "active")
        self.begin_scenario()
        saved = import_progress(self.store.data)
        self.assertEqual(saved.assessment.scenario, "Current professional situation")
        self.assertEqual(saved.view, "context")
        self.assertIn("Submitted progress saved in this browser", self.text())

    def test_context_only_draft_is_meaningful_and_autosaved(self):
        self.start(BrowserStore())
        self.app.session_state["assessment"].context = Context(role="Finance manager")
        self.app.session_state["view"] = "context"
        self.app.run()
        self.healthy()
        saved = import_progress(self.store.data)
        self.assertEqual(saved.assessment.scenario, "")
        self.assertFalse(saved.assessment.confirmed)
        self.assertEqual(saved.assessment.context.role, "Finance manager")
        self.assertEqual(saved.view, "context")
        self.assertIn("Submitted progress saved in this browser", self.text())

    def test_resuming_over_context_only_draft_requires_confirmation(self):
        previous = draft("Saved scenario", "Saved role")
        self.start(BrowserStore(previous))
        self.app.session_state["assessment"].context = Context(role="Finance manager")
        self.app.session_state["view"] = "context"
        self.app.run()
        self.click("Resume previous assessment")
        self.assertEqual(self.app.session_state["assessment"].scenario, "")
        self.assertEqual(self.app.session_state["assessment"].context.role, "Finance manager")
        self.assertEqual(self.store.data, previous)
        self.assertIn("Confirm resume and replace current progress", [b.label for b in self.app.button])
        self.click("Cancel resume")
        self.assertEqual(self.app.session_state["assessment"].context.role, "Finance manager")
        self.click("Resume previous assessment")
        self.click("Confirm resume and replace current progress")
        self.assertEqual(self.app.session_state["assessment"].scenario, "Saved scenario")
        self.assertEqual(self.app.session_state["assessment"].context.role, "Saved role")

    def test_previous_copy_requires_explicit_resume_without_initial_overwrite(self):
        saved = draft()
        self.start(BrowserStore(saved))
        self.assertEqual(self.store.data, saved)
        self.assertEqual(self.app.session_state["assessment"].scenario, "")
        self.assertFalse(any(call["op"] == "write" for call in self.store.calls))
        self.click("Resume previous assessment")
        self.assertEqual(self.app.session_state["view"], "context")
        self.assertEqual(self.widget("text_input", "Your professional role").value, "Saved manager")
        self.assertIn("Progress restored", self.text())

    def test_new_app_session_can_resume_all_three_phases_and_report_stage(self):
        saved = cfo_report_progress()
        self.start(BrowserStore(saved))
        self.click("Resume previous assessment")
        self.assertEqual(self.app.session_state["view"], "report")
        self.assertEqual(len(self.app.session_state["assessment"].answers), 7)
        self.assertEqual(len(self.app.session_state["review_state"].answers), 1)
        self.assertEqual(len(self.app.session_state["address_state"].answers), 6)
        self.assertIn("Download progress", self.download_labels())
        self.assertIn("Download report (Markdown)", self.download_labels())
        self.assertIn("Proposed, not yet started", self.text())

    def test_start_new_needs_confirmation_then_clears_browser_and_session(self):
        saved = draft()
        self.start(BrowserStore(saved))
        self.click("Start new assessment")
        self.assertEqual(self.store.data, saved)
        self.click("Keep current scenario")
        self.assertEqual(self.store.data, saved)
        self.click("Start new assessment")
        self.click("Discard and start again")
        self.assertIsNone(self.store.data)
        self.assertIsNotNone(self.store.token)
        self.assertEqual(self.app.session_state["assessment"].scenario, "")
        self.assertEqual(self.app.session_state["view"], "scenario")
        self.assertIn("saved browser assessment was deleted", self.text())

    def test_corrupt_saved_payload_is_preserved_until_confirmed_clear(self):
        self.start(BrowserStore("{not-json"))
        self.assertEqual(self.app.session_state["_browser_save_state"].mode, "corrupt")
        self.assertEqual(self.store.data, "{not-json")
        self.assertIn("Download saved browser copy", self.download_labels())
        self.assertFalse(any(call["op"] == "write" for call in self.store.calls))
        self.click("Start new assessment")
        self.assertEqual(self.store.data, "{not-json")
        self.click("Discard and start again")
        self.assertIsNone(self.store.data)

    def test_unavailable_storage_keeps_portable_controls_without_saved_claim(self):
        self.start(BrowserStore(unavailable=True))
        self.begin_scenario()
        self.assertIn("Browser autosave is unavailable", self.text())
        self.assertNotIn("Submitted progress saved in this browser", self.text())
        self.assertIn("Download progress", self.download_labels())
        self.assertTrue(self.app.file_uploader)

    def test_pending_bridge_response_never_claims_saved(self):
        self.start(response=None)
        self.begin_scenario()
        self.assertIn("Saving is not yet confirmed", self.text())
        self.assertNotIn("Submitted progress saved in this browser", self.text())
        self.assertIn("Download progress", self.download_labels())

    def test_stale_read_ack_cannot_restore_or_claim_a_browser_save(self):
        self.start(response={
            "id": "stale-command", "op": "read", "status": "ok",
            "token": "other-token", "data": draft("Not accepted"),
        })
        self.assertEqual(self.app.session_state["_browser_save_state"].mode, "checking")
        self.assertEqual(self.app.session_state["assessment"].scenario, "")
        self.assertNotIn("Resume previous assessment", [button.label for button in self.app.button])
        self.assertIn("Saving is not yet confirmed", self.text())

    def test_import_confirmation_replaces_source_state_and_refreshes_widgets(self):
        self.start(BrowserStore())
        self.begin_scenario("Current situation to replace")
        previous = self.store.data
        self.widget("text_input", "Your professional role").input("Old widget role").run()
        snapshot = import_progress(draft("Imported situation", "Imported investigator"))
        self.app.session_state["_pending_import"] = snapshot
        self.app.run()
        self.assertEqual(self.store.data, previous)
        self.click("Confirm import and replace progress")
        self.assertEqual(self.app.session_state["assessment"].scenario, "Imported situation")
        self.assertEqual(self.widget("text_input", "Your professional role").value, "Imported investigator")
        self.assertEqual(import_progress(self.store.data).assessment.scenario, "Imported situation")
        self.assertIsNone(self.app.session_state["edit_answer_id"])
        self.assertIsNone(self.app.session_state["edit_review_id"])
        self.assertIsNone(self.app.session_state["edit_address_id"])

    def test_cancel_import_retains_current_session_and_browser_copy(self):
        self.start(BrowserStore())
        self.begin_scenario()
        previous = self.store.data
        self.app.session_state["_pending_import"] = import_progress(draft("Do not import"))
        self.app.run()
        self.click("Cancel import")
        self.assertEqual(self.store.data, previous)
        self.assertEqual(self.app.session_state["assessment"].scenario, "Current professional situation")

    def test_import_without_storage_restores_session_only(self):
        self.start(BrowserStore(unavailable=True))
        self.app.session_state["_pending_import"] = import_progress(draft("Portable fallback", "Fallback manager"))
        self.app.run()
        self.click("Confirm import and replace progress")
        self.assertEqual(self.app.session_state["assessment"].scenario, "Portable fallback")
        self.assertIn("Restored into this session only", self.text())
        self.assertIn("Browser autosave is unavailable", self.text())
        self.assertFalse(any(call["op"] == "write" for call in self.store.calls))

    def test_failed_import_write_does_not_claim_browser_copy_was_untouched(self):
        self.start(BrowserStore())
        self.begin_scenario("Original case")
        self.app.session_state["_pending_import"] = import_progress(draft("Imported after failure"))
        self.app.run()
        self.store.unavailable = True
        self.click("Confirm import and replace progress")
        self.assertEqual(self.app.session_state["assessment"].scenario, "Imported after failure")
        self.assertEqual(self.app.session_state["_browser_save_state"].mode, "unavailable")
        self.assertIn("Browser saving was not confirmed", self.text())
        self.assertNotIn("browser copy was not overwritten", self.text())

    def test_oversized_upload_is_rejected_before_reading_contents(self):
        upload = SimpleNamespace(
            size=MAX_PROGRESS_BYTES + 1,
            getvalue=Mock(side_effect=AssertionError("Oversized upload contents must not be read")),
        )
        with patch("objectivity.progress_ui.st.file_uploader", return_value=upload):
            self.start(BrowserStore())
            self.assertTrue(self.app.error)
            self.assertIn("2 MiB size limit", self.app.error[0].value)
            upload.getvalue.assert_not_called()
            self.assertNotIn("_pending_import", self.app.session_state)
            self.assertIsNone(self.store.data)

    def test_browser_clear_failure_keeps_current_assessment(self):
        self.start(BrowserStore())
        self.begin_scenario("Keep if browser deletion fails")
        previous = self.store.data
        self.store.unavailable = True
        self.click("Start a new scenario")
        self.click("Discard and start again")
        self.assertEqual(self.app.session_state["assessment"].scenario, "Keep if browser deletion fails")
        self.assertEqual(self.store.data, previous)
        self.assertIn("current assessment has been retained", self.text())

    def test_import_conflict_restores_only_session_without_overwriting_newer_copy(self):
        self.start(BrowserStore())
        self.begin_scenario("Original case")
        self.app.session_state["_pending_import"] = import_progress(draft("Imported case"))
        self.app.run()
        other = draft("Another tab's newer case")
        self.store.external_change(other)
        self.click("Confirm import and replace progress")
        self.assertEqual(self.app.session_state["assessment"].scenario, "Imported case")
        self.assertEqual(self.store.data, other)
        self.assertEqual(self.app.session_state["_browser_save_state"].mode, "conflict")
        self.assertIn("browser copy was not overwritten", self.text())

    def test_conflict_does_not_overwrite_newer_copy_and_resume_needs_confirmation(self):
        self.start(BrowserStore())
        self.begin_scenario("This tab's first account")
        other = draft("Another tab's account", "Other manager")
        self.store.external_change(other)
        self.app.session_state["assessment"].scenario = "This tab's unsaved change"
        self.app.run()
        self.healthy()
        self.assertEqual(self.store.data, other)
        self.assertEqual(self.app.session_state["_browser_save_state"].mode, "conflict")
        self.assertIn("Download progress", self.download_labels())
        self.click("Resume previous assessment")
        self.assertEqual(self.app.session_state["assessment"].scenario, "This tab's unsaved change")
        self.click("Cancel resume")
        self.assertEqual(self.store.data, other)
        self.click("Resume previous assessment")
        self.click("Confirm resume and replace current progress")
        self.assertEqual(self.app.session_state["assessment"].scenario, "Another tab's account")

    def test_conflict_browser_replacement_requires_confirmation(self):
        self.start(BrowserStore())
        self.begin_scenario("This tab")
        other = draft("Another tab")
        self.store.external_change(other)
        self.app.session_state["assessment"].scenario = "Keep this version"
        self.app.run()
        self.click("Keep this session instead")
        self.assertEqual(self.store.data, other)
        self.click("Confirm replace browser copy")
        self.assertEqual(import_progress(self.store.data).assessment.scenario, "Keep this version")

    def test_queued_clear_cannot_adopt_a_newer_token_after_autosave_conflict(self):
        self.start(DelayedBrowserStore())
        self.begin_scenario("Original saved case")
        self.store.hold_writes = True
        self.app.session_state["assessment"].scenario = "Current unsaved change"
        self.app.run()
        self.assertTrue(self.app.session_state["_browser_save_state"].busy)
        self.assertEqual(self.app.session_state["_browser_save_state"].purpose, "autosave")
        self.click("Start a new scenario")
        self.click("Discard and start again")
        self.assertEqual(self.app.session_state[INTENT]["kind"], "clear")
        other = draft("Newer case saved in another tab")
        self.store.external_change(other)
        conflict_token = self.store.token
        self.store.hold_writes = False
        self.app.run()
        self.healthy()
        self.assertNotIn(INTENT, self.app.session_state)
        self.assertEqual(self.app.session_state["assessment"].scenario, "Current unsaved change")
        self.assertEqual(self.store.data, other)
        self.assertEqual(self.store.token, conflict_token)
        self.assertFalse(any(call["op"] == "clear" for call in self.store.calls))
        self.assertIn("pending replacement or deletion was cancelled", self.text())
        self.app.run()
        self.assertEqual(self.store.data, other)
        self.assertFalse(any(call["op"] == "clear" for call in self.store.calls))
        # A new explicit confirmation can clear the now-visible newer copy.
        self.click("Discard and start again")
        self.assertIsNone(self.store.data)
        self.assertEqual(self.app.session_state["assessment"].scenario, "")

    def test_queued_import_needs_new_confirmation_after_autosave_conflict(self):
        self.start(DelayedBrowserStore())
        self.begin_scenario("Original saved case")
        self.store.hold_writes = True
        self.app.session_state["assessment"].scenario = "Current unsaved change"
        self.app.run()
        self.assertTrue(self.app.session_state["_browser_save_state"].busy)
        self.app.session_state["_pending_import"] = import_progress(draft("Imported case"))
        self.app.run()
        self.click("Confirm import and replace progress")
        self.assertEqual(self.app.session_state[INTENT]["kind"], "import")
        other = draft("Newer case saved in another tab")
        self.store.external_change(other)
        conflict_token = self.store.token
        self.store.hold_writes = False
        self.app.run()
        self.healthy()
        self.assertNotIn(INTENT, self.app.session_state)
        self.assertEqual(self.app.session_state["assessment"].scenario, "Current unsaved change")
        self.assertEqual(self.store.data, other)
        self.assertEqual(self.store.token, conflict_token)
        self.assertFalse(any(
            call["op"] == "write" and call.get("expected_token") == conflict_token
            for call in self.store.calls
        ))
        self.assertIn("pending replacement or deletion was cancelled", self.text())
        self.app.run()
        self.assertEqual(self.store.data, other)
        # Import is still staged; it is not applied until reapproved.
        self.click("Confirm import and replace progress")
        self.assertEqual(import_progress(self.store.data).assessment.scenario, "Imported case")
        self.assertEqual(self.app.session_state["assessment"].scenario, "Imported case")

    def test_earlier_answer_edit_after_resume_invalidates_downstream_actions(self):
        self.start(BrowserStore(cfo_report_progress()))
        self.click("Resume previous assessment")
        self.click("Edit clarification answers")
        self.widget("selectbox", "Choose an answer to review").set_value("relationship_contact")
        self.click("Edit selected answer")
        self.app.radio[0].set_value("Little or no current personal contact")
        self.click("Save answer")
        self.assertIn("current personal ties", self.app.radio[0].label)
        self.assertEqual(self.app.session_state["review_state"].answers, {})
        self.assertEqual(self.app.session_state["address_state"].answers, {})
        self.assertTrue(self.app.session_state["address_state"].archive)
        saved = import_progress(self.store.data)
        self.assertEqual(saved.address.answers, {})
        self.assertTrue(saved.address.archive)

    def test_privacy_and_submitted_forms_limitations_are_visible(self):
        self.start(BrowserStore())
        text = self.text()
        self.assertIn("fictional or anonymised", text)
        self.assertIn("private browsing", text)
        self.assertIn("Only submitted forms", text)
        self.assertIn("No permanent server storage", text)


class ProgressQueueTests(unittest.TestCase):
    def test_new_confirmation_cannot_silently_replace_an_already_queued_operation(self):
        class Rerun(Exception):
            pass

        existing = {"kind": "clear", "snapshot": None}
        fake_streamlit = SimpleNamespace(
            session_state={INTENT: existing}, rerun=Mock(side_effect=Rerun),
        )
        with patch("objectivity.progress_ui.st", fake_streamlit):
            with self.assertRaises(Rerun):
                _queue("import", import_progress(draft("Do not queue over deletion")))
        self.assertIs(fake_streamlit.session_state[INTENT], existing)
        self.assertIn("already pending", fake_streamlit.session_state["_progress_notice"])


if __name__ == "__main__":
    unittest.main()
