"""Versioned progress preserves Step 2 source clarification, never findings."""

from copy import deepcopy
import json
import unittest

from objectivity.address import AddressState
from objectivity.evaluation import evaluate
from objectivity.models import Assessment, Context
from objectivity.progress import (
    FORMAT_VERSION, ProgressError, export_progress, import_progress,
)
from objectivity.report import build_report
from objectivity.review import ReviewState
from tests.test_progress import proposed_case


def document(assessment=None, view="context"):
    return json.loads(export_progress(
        assessment or Assessment(), ReviewState(), AddressState(), view,
    ))


def as_legacy(value):
    value = deepcopy(value)
    value["schema_version"] = 1
    value["assessment"].pop("context_clarifications", None)
    value["assessment"].pop("case_state", None)
    return value


class IntakeProgressCompatibilityTests(unittest.TestCase):
    def restore(self, value):
        return import_progress(json.dumps(value))

    def test_new_format_carries_an_explicit_empty_clarification_collection(self):
        value = document()
        self.assertEqual(FORMAT_VERSION, 3)
        self.assertEqual(value["schema_version"], FORMAT_VERSION)
        self.assertEqual(value["assessment"]["context_clarifications"], {})

    def test_legacy_empty_assessment_migrates_without_confirmation(self):
        value = as_legacy(document(view="scenario"))
        restored = self.restore(value)
        self.assertEqual(restored.assessment, Assessment())
        self.assertEqual(restored.view, "scenario")
        self.assertFalse(restored.assessment.confirmed)
        self.assertFalse(restored.assessment.context_clarifications)

    def test_legacy_draft_retains_user_fields_and_stays_unconfirmed(self):
        original = Assessment(
            scenario="A role the local grammar does not recognise.",
            context=Context(role="Marine grant coordinator", parties="Board", decision="Allocate grants"),
        )
        restored = self.restore(as_legacy(document(original)))
        self.assertEqual(restored.assessment, original)
        self.assertEqual(restored.view, "context")
        self.assertEqual(evaluate(restored.assessment).findings, ())

    def test_legacy_all_phase_progress_and_report_still_recompute(self):
        original = proposed_case()
        exported = json.loads(export_progress(*original, "report"))
        restored = self.restore(as_legacy(exported))
        self.assertEqual((restored.assessment, restored.review, restored.address), original)
        self.assertEqual(build_report(*original), build_report(restored.assessment, restored.review, restored.address))
        self.assertIn("Proposed, not yet started", build_report(restored.assessment, restored.review, restored.address))
        self.assertEqual(restored.view, "report")

    def test_migrated_legacy_save_exports_as_the_current_schema(self):
        restored = self.restore(as_legacy(document()))
        current = json.loads(export_progress(restored.assessment, restored.review, restored.address, restored.view))
        self.assertEqual(current["schema_version"], FORMAT_VERSION)
        self.assertIn("context_clarifications", current["assessment"])

    def test_future_schema_versions_remain_incompatible(self):
        value = document()
        value["schema_version"] = FORMAT_VERSION + 1
        with self.assertRaises(ProgressError):
            self.restore(value)

    def test_legacy_schema_cannot_smuggle_new_clarification_fields(self):
        value = as_legacy(document())
        value["assessment"]["context_clarifications"] = {}
        with self.assertRaises(ProgressError):
            self.restore(value)

    def test_current_schema_requires_the_clarification_collection(self):
        value = document()
        del value["assessment"]["context_clarifications"]
        with self.assertRaises(ProgressError):
            self.restore(value)


class IntakeSourceRecordTests(unittest.TestCase):
    def partial(self, *, unknown=False):
        from objectivity.intake import save_intake_answer
        assessment = Assessment(
            scenario="A professional issue needs clarification.",
            context=Context(role="Unknown", parties="Unknown", decision="Unknown"),
        )
        save_intake_answer(
            assessment, "role", "I don't know yet" if unknown else "Provided",
            "" if unknown else "Marine grant coordinator",
        )
        return assessment

    def restore(self, value):
        return import_progress(json.dumps(value))

    def test_submitted_clarification_round_trip_restores_next_question(self):
        from objectivity.intake import next_intake_question
        assessment = self.partial()
        value = document(assessment)
        restored = self.restore(value)
        self.assertEqual(restored.assessment, assessment)
        self.assertFalse(restored.assessment.confirmed)
        self.assertEqual(next_intake_question(restored.assessment).id, "decision")
        self.assertEqual(restored.assessment.context.role, "Marine grant coordinator")
        self.assertEqual(restored.assessment.context_clarifications["role"].choice, "Provided")

    def test_user_declared_unknown_is_not_asked_again_after_restoration(self):
        from objectivity.intake import next_intake_question
        assessment = self.partial(unknown=True)
        restored = self.restore(document(assessment))
        self.assertEqual(restored.assessment.context.role, "Unknown")
        self.assertEqual(next_intake_question(restored.assessment).id, "decision")
        self.assertEqual(restored.assessment.context_clarifications["role"].choice, "I don't know yet")

    def test_export_import_is_deterministic_for_partial_source_records(self):
        assessment = self.partial()
        encoded = export_progress(assessment, ReviewState(), AddressState(), "context")
        restored = import_progress(encoded)
        self.assertEqual(encoded, export_progress(restored.assessment, restored.review, restored.address, restored.view))

    def test_imported_partial_record_does_not_confirm_or_evaluate(self):
        value = document(self.partial())
        value["view"] = "report"
        restored = self.restore(value)
        self.assertFalse(restored.assessment.confirmed)
        self.assertEqual(evaluate(restored.assessment).findings, ())
        self.assertEqual(restored.view, "context")
        self.assertTrue(restored.warnings)

    def test_edited_source_discards_stale_record_and_reopens_needed_question(self):
        from objectivity.intake import next_intake_question
        value = document(self.partial())
        value["assessment"]["context"]["role"] = "Unknown"
        restored = self.restore(value)
        self.assertEqual(restored.assessment.context.role, "Unknown")
        self.assertFalse(restored.assessment.context_clarifications)
        self.assertEqual(next_intake_question(restored.assessment).id, "role")
        self.assertTrue(any("earlier account" in warning for warning in restored.warnings))

    def test_scenario_edit_invalidates_old_source_acknowledgement(self):
        value = document(self.partial(unknown=True))
        value["assessment"]["scenario"] = "A different case, with a different role."
        restored = self.restore(value)
        self.assertFalse(restored.assessment.context_clarifications)
        self.assertEqual(restored.assessment.scenario, value["assessment"]["scenario"])
        self.assertTrue(restored.warnings)

    def test_export_prunes_stale_metadata_on_a_copy(self):
        assessment = self.partial()
        records = deepcopy(assessment.context_clarifications)
        assessment.scenario = "The user has revised the scenario."
        encoded = export_progress(assessment, ReviewState(), AddressState(), "context")
        self.assertEqual(assessment.context_clarifications, records)
        self.assertEqual(json.loads(encoded)["assessment"]["context_clarifications"], {})

    def test_record_structure_identifiers_choices_tokens_and_text_are_bounded(self):
        for mutate in (
            lambda value: value["assessment"].update(context_clarifications=[]),
            lambda value: value["assessment"]["context_clarifications"].update(report={}),
            lambda value: value["assessment"]["context_clarifications"]["role"].update(conclusion="Ethically acceptable"),
            lambda value: value["assessment"]["context_clarifications"]["role"].update(choice="Independently verified"),
            lambda value: value["assessment"]["context_clarifications"]["role"].update(fingerprint="not-a-source-token"),
            lambda value: value["assessment"]["context_clarifications"]["role"].update(detail=[]),
            lambda value: value["assessment"]["context_clarifications"]["role"].update(detail="x" * 100_001),
        ):
            with self.subTest(mutation=mutate):
                value = document(self.partial())
                mutate(value)
                with self.assertRaises(ProgressError):
                    self.restore(value)

    def test_current_token_cannot_hide_semantically_contradictory_record(self):
        value = document(self.partial())
        value["assessment"]["context_clarifications"]["role"]["choice"] = "I don't know yet"
        with self.assertRaises(ProgressError):
            self.restore(value)

    def family_beneficiary(self):
        from objectivity.intake import FAMILY_INTEREST, save_intake_answer
        assessment = Assessment(
            scenario="A sister has shares in a supplier whose bid I assess.",
            context=Context(
                role="Marine grant coordinator", parties="Sister; supplier",
                decision="Assess bids", relationship="Professional relationship only",
                pressure="No reported pressure",
            ),
        )
        save_intake_answer(assessment, "interests", FAMILY_INTEREST)
        save_intake_answer(assessment, "beneficiary", "Provided", "My sister owns shares in the supplier.")
        return assessment

    def test_family_beneficiary_progress_restores_without_assigning_user_ownership(self):
        from objectivity.intake import next_intake_question
        assessment = self.family_beneficiary()
        restored = self.restore(document(assessment))
        self.assertEqual(restored.assessment, assessment)
        self.assertEqual(restored.assessment.context.interests, "Other")
        self.assertIn("not established", restored.assessment.context.interests_notes)
        self.assertIn("My sister owns shares", restored.assessment.context.interests_notes)
        self.assertIsNone(next_intake_question(restored.assessment))

    def test_beneficiary_without_primary_source_answer_is_rejected(self):
        value = document(self.family_beneficiary())
        del value["assessment"]["context_clarifications"]["interests"]
        with self.assertRaises(ProgressError):
            self.restore(value)

    def test_stale_primary_record_cannot_leave_a_current_orphan_beneficiary(self):
        from objectivity.intake import next_intake_question
        value = document(self.family_beneficiary())
        value["assessment"]["context_clarifications"]["interests"]["fingerprint"] = "0" * 64
        restored = self.restore(value)
        self.assertFalse(restored.assessment.context_clarifications)
        self.assertEqual(next_intake_question(restored.assessment).id, "interests")
        self.assertTrue(restored.warnings)

    def test_confirmed_intake_source_answers_restore_and_context_edits_recalculate(self):
        from objectivity.intake import confirm_intake
        assessment = self.family_beneficiary()
        confirm_intake(assessment)
        value = document(assessment, view="review")
        restored = self.restore(value)
        self.assertTrue(restored.assessment.confirmed)
        self.assertEqual(restored.assessment.answers["interest_relevance"].choice, "Other")
        self.assertEqual(restored.assessment.context_clarifications, assessment.context_clarifications)
        # A manually changed source classification cannot retain the old
        # applicability, metadata or downstream stage from an imported save.
        value["assessment"]["context"]["interests"] = "Commercial interest"
        changed = self.restore(value)
        self.assertNotIn("interest_relevance", changed.assessment.answers)
        self.assertTrue(changed.assessment.archive)
        self.assertFalse(changed.assessment.context_clarifications)
        self.assertEqual(changed.view, "questions")


if __name__ == "__main__":
    unittest.main()
