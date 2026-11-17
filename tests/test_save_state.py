"""Browser-save coordination: acknowledge exact writes and preserve conflicts."""

from copy import deepcopy
import unittest

from objectivity.save_state import BrowserSaveState


def response(state, *, status="ok", token=None, data=None, **overrides):
    result = {
        "id": state.command["id"], "op": state.command["op"],
        "status": status, "token": token, "data": data,
    }
    result.update(overrides)
    return result


def empty_browser():
    state = BrowserSaveState()
    state.consume(response(state))
    return state


def saved_browser(payload='{"scenario":"A fictional case"}', token="saved-token"):
    state = BrowserSaveState()
    state.consume(response(state, token=token, data=payload))
    return state


class BrowserReadTests(unittest.TestCase):
    def test_initial_read_does_not_claim_storage_or_a_saved_payload(self):
        state = BrowserSaveState()
        self.assertEqual(state.command["op"], "read")
        self.assertTrue(state.busy)
        self.assertEqual(state.mode, "checking")
        self.assertFalse(state.available)
        self.assertIsNone(state.last_saved_data)
        self.assertNotIn("data", state.command)
        self.assertNotIn("expected_token", state.command)

    def test_no_or_unrelated_event_does_not_complete_pending_read(self):
        state = BrowserSaveState()
        before = deepcopy(state)
        for event in (None, [], "ok", {}, {"id": "earlier-session", "op": "read", "status": "ok"}):
            with self.subTest(event=event):
                self.assertIsNone(state.consume(event))
                self.assertEqual(state, before)

    def test_wrong_operation_unknown_status_and_invalid_field_types_are_ignored(self):
        for overrides in (
            {"op": "write"}, {"status": "unknown"}, {"token": 42}, {"data": {}},
        ):
            with self.subTest(overrides=overrides):
                state = BrowserSaveState()
                before = deepcopy(state)
                self.assertIsNone(state.consume(response(state, **overrides)))
                self.assertEqual(state, before)

    def test_empty_or_oversized_tokens_are_ignored(self):
        for token in ("", "x" * 257):
            with self.subTest(length=len(token)):
                state = BrowserSaveState()
                before = deepcopy(state)
                self.assertIsNone(state.consume(response(state, token=token, data="saved progress")))
                self.assertEqual(state, before)

    def test_read_payload_without_token_is_not_accepted_as_resumable(self):
        state = BrowserSaveState()
        self.assertEqual(state.consume(response(state, data="saved progress")), "read:failed")
        self.assertEqual(state.mode, "unavailable")
        self.assertFalse(state.available)
        self.assertFalse(state.busy)
        self.assertIsNone(state.last_saved_data)
        self.assertIn("valid saved-copy identifier", state.error)

    def test_missing_browser_assessment_enables_new_progress_without_fake_save(self):
        state = empty_browser()
        self.assertFalse(state.busy)
        self.assertTrue(state.available)
        self.assertEqual(state.mode, "active")
        self.assertIsNone(state.token)
        self.assertIsNone(state.saved_data)
        self.assertIsNone(state.last_saved_data)

    def test_existing_assessment_requires_explicit_resume_choice(self):
        state = saved_browser()
        self.assertEqual(state.mode, "choice")
        self.assertEqual(state.token, "saved-token")
        self.assertIsNotNone(state.saved_data)
        self.assertIsNone(state.last_saved_data)
        state.resume(state.saved_data)
        self.assertEqual(state.mode, "active")
        self.assertEqual(state.last_saved_data, state.saved_data)

    def test_resuming_normalized_progress_does_not_pretend_normalization_was_stored(self):
        state = saved_browser(payload="original saved payload")
        state.resume("normalized current payload")
        self.assertEqual(state.last_saved_data, "original saved payload")
        self.assertNotEqual(state.last_saved_data, "normalized current payload")

    def test_resume_without_an_existing_assessment_is_rejected(self):
        for state in (BrowserSaveState(), empty_browser()):
            with self.subTest(mode=state.mode):
                with self.assertRaises(ValueError):
                    state.resume("nothing saved")

    def test_corrupt_record_remains_a_choice_for_explicit_recovery_or_clear(self):
        state = BrowserSaveState()
        self.assertEqual(
            state.consume(response(state, status="corrupt", token="corrupt:checksum", reason="Saved record is corrupt.")),
            "read:failed",
        )
        self.assertEqual(state.mode, "corrupt")
        self.assertTrue(state.available)
        self.assertFalse(state.busy)
        self.assertEqual(state.token, "corrupt:checksum")
        self.assertEqual(state.error, "Saved record is corrupt.")
        self.assertIsNone(state.last_saved_data)

    def test_corrupt_raw_record_is_retained_for_recovery_without_claiming_save(self):
        state = BrowserSaveState()
        raw = "{an incomplete browser record"
        state.consume(response(state, status="corrupt", token="corrupt:checksum", raw=raw))
        self.assertEqual(state.mode, "corrupt")
        self.assertEqual(state.saved_data, raw)
        self.assertIsNone(state.last_saved_data)

    def test_corrupt_recovery_data_does_not_replace_an_explicit_payload(self):
        state = BrowserSaveState()
        state.consume(response(
            state, status="corrupt", token="corrupt:checksum", data="payload", raw="envelope",
        ))
        self.assertEqual(state.saved_data, "payload")

    def test_corrupt_raw_recovery_is_bounded_by_utf8_size(self):
        for label, raw in (
            ("too many ASCII bytes", "x" * (2 * 1024 * 1024 + 1)),
            ("too many UTF-8 bytes", "界" * (1024 * 1024)),
        ):
            with self.subTest(case=label):
                state = BrowserSaveState()
                state.consume(response(state, status="corrupt", token="corrupt:checksum", raw=raw))
                self.assertEqual(state.mode, "corrupt")
                self.assertIsNone(state.saved_data)
                self.assertIsNone(state.last_saved_data)


class BrowserWriteTests(unittest.TestCase):
    def test_pending_operations_cannot_overlap(self):
        state = BrowserSaveState()
        command = deepcopy(state.command)
        with self.assertRaises(ValueError):
            state.request("write", "some progress")
        self.assertEqual(state.command, command)

    def test_unsupported_operations_and_nonstring_writes_are_rejected(self):
        state = empty_browser()
        before = deepcopy(state)
        for operation, data in (("delete_everything", None), ("write", None), ("write", {})):
            with self.subTest(operation=operation, data=data):
                with self.assertRaises(ValueError):
                    state.request(operation, data)
                self.assertEqual(state, before)

    def test_write_uses_current_expected_token_and_waits_for_exact_ack(self):
        state = saved_browser()
        state.resume(state.saved_data)
        previous_saved = state.last_saved_data
        state.request("write", "updated progress")
        self.assertEqual(state.command["expected_token"], "saved-token")
        self.assertEqual(state.command["data"], "updated progress")
        self.assertTrue(state.busy)
        self.assertEqual(state.last_saved_data, previous_saved)
        self.assertEqual(state.consume(response(state, token="new-token", data="updated progress")), "autosave")
        self.assertFalse(state.busy)
        self.assertEqual(state.mode, "active")
        self.assertEqual(state.token, "new-token")
        self.assertEqual(state.last_saved_data, "updated progress")

    def test_mismatched_write_payload_does_not_claim_successful_save(self):
        state = empty_browser()
        state.request("write", "intended progress")
        result = state.consume(response(state, token="new-token", data="another payload"))
        self.assertEqual(result, "autosave:failed")
        self.assertEqual(state.mode, "unavailable")
        self.assertFalse(state.available)
        self.assertIsNone(state.last_saved_data)
        self.assertIn("did not confirm", state.error)

    def test_missing_write_token_does_not_claim_successful_save(self):
        state = empty_browser()
        state.request("write", "intended progress", purpose="import")
        self.assertEqual(state.consume(response(state, data="intended progress")), "import:failed")
        self.assertEqual(state.mode, "unavailable")
        self.assertIsNone(state.last_saved_data)

    def test_duplicate_ack_is_ignored_without_creating_another_event(self):
        state = empty_browser()
        state.request("write", "progress")
        event = response(state, token="token", data="progress")
        self.assertEqual(state.consume(event), "autosave")
        completed = deepcopy(state)
        self.assertIsNone(state.consume(event))
        self.assertEqual(state, completed)

    def test_late_ack_for_previous_command_does_not_complete_new_write(self):
        state = empty_browser()
        state.request("write", "first progress")
        earlier_ack = response(state, token="first-token", data="first progress")
        state.consume(earlier_ack)
        state.request("write", "newer progress")
        self.assertIsNone(state.consume(earlier_ack))
        self.assertTrue(state.busy)
        self.assertEqual(state.last_saved_data, "first progress")
        state.consume(response(state, token="second-token", data="newer progress"))
        self.assertEqual(state.last_saved_data, "newer progress")

    def test_conflict_preserves_the_other_tabs_saved_assessment(self):
        state = saved_browser(payload="original")
        state.resume("original")
        state.request("write", "this tab's new progress")
        result = state.consume(response(state, status="conflict", token="other-tab-token", data="other tab's progress"))
        self.assertEqual(result, "autosave:failed")
        self.assertEqual(state.mode, "conflict")
        self.assertEqual(state.saved_data, "other tab's progress")
        self.assertEqual(state.token, "other-tab-token")
        self.assertEqual(state.last_saved_data, "original")
        state.resume("other tab's progress")
        self.assertEqual(state.mode, "active")
        self.assertEqual(state.last_saved_data, "other tab's progress")

    def test_explicit_overwrite_after_conflict_uses_the_latest_token(self):
        state = empty_browser()
        state.request("write", "this assessment")
        state.consume(response(state, status="conflict", token="latest", data="other assessment"))
        state.request("write", "replacement approved by user", purpose="replace")
        self.assertEqual(state.command["expected_token"], "latest")
        self.assertEqual(state.consume(response(state, token="replacement-token", data="replacement approved by user")), "replace")
        self.assertEqual(state.last_saved_data, "replacement approved by user")

    def test_unavailable_storage_never_claims_the_pending_progress_is_saved(self):
        state = empty_browser()
        state.request("write", "unsaved progress")
        self.assertEqual(state.consume(response(state, status="unavailable", reason="Storage quota was exceeded.")), "autosave:failed")
        self.assertEqual(state.mode, "unavailable")
        self.assertFalse(state.available)
        self.assertFalse(state.busy)
        self.assertIsNone(state.last_saved_data)
        self.assertIn("quota", state.error)

    def test_read_retry_can_recover_from_unavailable_storage(self):
        state = BrowserSaveState()
        state.consume(response(state, status="unavailable", reason="Storage blocked."))
        state.request("read", purpose="read")
        self.assertTrue(state.busy)
        self.assertEqual(state.consume(response(state, token="restored", data="existing progress")), "read")
        self.assertEqual(state.mode, "choice")
        self.assertTrue(state.available)


class BrowserClearTests(unittest.TestCase):
    def test_clear_uses_expected_token_and_preserves_old_save_until_ack(self):
        state = saved_browser(payload="sensitive scenario")
        state.resume(state.saved_data)
        state.request("clear", purpose="clear")
        self.assertEqual(state.command["expected_token"], "saved-token")
        self.assertNotIn("data", state.command)
        self.assertEqual(state.last_saved_data, "sensitive scenario")
        self.assertEqual(state.consume(response(state, token="tombstone-token", data=None)), "clear")
        self.assertEqual(state.mode, "active")
        self.assertEqual(state.token, "tombstone-token")
        self.assertIsNone(state.saved_data)
        self.assertIsNone(state.last_saved_data)
        state.request("write", "new assessment")
        self.assertEqual(state.command["expected_token"], "tombstone-token")

    def test_clear_ack_with_remaining_data_is_not_success(self):
        state = saved_browser(payload="saved scenario")
        state.resume(state.saved_data)
        state.request("clear", purpose="clear")
        self.assertEqual(state.consume(response(state, token="new-token", data="still present")), "clear:failed")
        self.assertEqual(state.mode, "unavailable")
        self.assertEqual(state.last_saved_data, "saved scenario")

    def test_clear_without_tombstone_token_does_not_claim_deletion(self):
        state = saved_browser(payload="saved scenario")
        state.resume(state.saved_data)
        state.request("clear", purpose="clear")
        self.assertEqual(state.consume(response(state, data=None)), "clear:failed")
        self.assertEqual(state.mode, "unavailable")
        self.assertEqual(state.last_saved_data, "saved scenario")
        self.assertIn("did not confirm removal", state.error)

    def test_conflicted_clear_does_not_claim_other_assessment_was_deleted(self):
        state = saved_browser(payload="old scenario")
        state.resume(state.saved_data)
        state.request("clear", purpose="clear")
        self.assertEqual(state.consume(response(state, status="conflict", token="other", data="newer scenario")), "clear:failed")
        self.assertEqual(state.mode, "conflict")
        self.assertEqual(state.saved_data, "newer scenario")
        self.assertEqual(state.last_saved_data, "old scenario")

    def test_corrupt_saved_record_can_only_be_cleared_using_its_current_token(self):
        state = BrowserSaveState()
        state.consume(response(state, status="corrupt", token="corrupt:digest"))
        state.request("clear", purpose="clear")
        self.assertEqual(state.command["expected_token"], "corrupt:digest")
        state.consume(response(state, token="clear-token", data=None))
        self.assertEqual(state.mode, "active")
        self.assertIsNone(state.saved_data)

    def test_requests_and_instances_receive_distinct_command_ids(self):
        first, second = BrowserSaveState(), BrowserSaveState()
        self.assertNotEqual(first.command["id"], second.command["id"])
        first.consume(response(first))
        read_id = first.command["id"]
        first.request("read", purpose="read")
        self.assertNotEqual(first.command["id"], read_id)
        self.assertNotEqual(first.command["id"], second.command["id"])


if __name__ == "__main__":
    unittest.main()
