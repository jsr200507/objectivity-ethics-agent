"""Applying refreshed suggestions preserves edits, history and confirmation gates."""

from copy import deepcopy
import unittest

from objectivity.context_suggestions import apply_suggestions
from objectivity.models import Answer, Assessment, Context
from objectivity.progress import export_progress, import_progress
from objectivity.review import ReviewState, sync_review
from objectivity.address import AddressState, sync_address


class ApplySuggestionTests(unittest.TestCase):
    def setUp(self):
        self.assessment = Assessment(
            scenario="Original account", confirmed=True,
            context=Context(role="Auditor", parties="CFO", decision="Revenue recognition"),
            answers={"relationship_contact": Answer("Unknown", "A retained explanation")},
            revision=3,
        )
        self.draft = deepcopy(self.assessment.context)
        self.draft.parties = "User-corrected parties"
        self.suggested = Context(
            role="Actuary", parties="Manager", decision="Insurance reserves",
            relationship="Other", relationship_notes="A professional relationship is reported.",
            interests="Personal financial interest", interests_notes="My bonus depends on profit.",
        )

    def test_selected_fields_and_related_notes_only_are_replaced(self):
        original_suggestion = deepcopy(self.suggested)
        self.draft.pressure_notes = "Keep this user explanation"
        changed = apply_suggestions(self.assessment, "Revised account", self.draft, self.suggested, ["role", "interests"])
        self.assertTrue(changed)
        self.assertEqual(self.assessment.context.role, "Actuary")
        self.assertEqual(self.assessment.context.parties, "User-corrected parties")
        self.assertEqual(self.assessment.context.interests_notes, self.suggested.interests_notes)
        self.assertEqual(self.assessment.context.pressure_notes, "Keep this user explanation")
        self.assertEqual(self.suggested, original_suggestion)
        self.assertEqual(self.draft.role, "Auditor")

    def test_changed_suggestions_archive_answers_and_require_reconfirmation(self):
        apply_suggestions(self.assessment, "New account", self.draft, self.suggested, ["role"])
        self.assertFalse(self.assessment.confirmed)
        self.assertEqual(self.assessment.answers, {})
        self.assertEqual(len(self.assessment.archive), 1)
        self.assertEqual(self.assessment.archive[0].answer.explanation, "A retained explanation")
        self.assertEqual(self.assessment.archive[0].revision, 4)
        self.assertEqual(self.assessment.revision, 4)

    def test_identical_replacement_does_not_invalidate_a_confirmed_assessment(self):
        before = deepcopy(self.assessment)
        changed = apply_suggestions(self.assessment, "Original account", self.assessment.context, self.assessment.context, ["role"])
        self.assertFalse(changed)
        self.assertEqual(self.assessment, before)

    def test_scenario_change_alone_still_invalidates_confirmation(self):
        changed = apply_suggestions(self.assessment, "New facts", self.assessment.context, self.assessment.context, ["role"])
        self.assertTrue(changed)
        self.assertFalse(self.assessment.confirmed)
        self.assertFalse(self.assessment.answers)

    def test_invalid_choices_cannot_partially_mutate_source_state(self):
        for fields in ([], ["report"], ["role", "unsupported"]):
            with self.subTest(fields=fields):
                before = deepcopy(self.assessment)
                with self.assertRaises(ValueError):
                    apply_suggestions(self.assessment, "Account", self.draft, self.suggested, fields)
                self.assertEqual(self.assessment, before)
        bad = deepcopy(self.suggested)
        bad.interests = "Invented option"
        with self.assertRaises(ValueError):
            apply_suggestions(self.assessment, "Account", self.draft, bad, ["interests"])
        with self.assertRaises(ValueError):
            apply_suggestions(self.assessment, "  ", self.draft, self.suggested, ["role"])

    def test_applied_draft_round_trips_without_trusting_conclusions(self):
        apply_suggestions(self.assessment, "Revised account", self.draft, self.suggested, ["role", "interests"])
        review, address = ReviewState(), AddressState()
        sync_review(self.assessment, review)
        sync_address(self.assessment, review, address)
        restored = import_progress(export_progress(self.assessment, review, address, "context"))
        self.assertEqual(restored.assessment, self.assessment)
        self.assertEqual(restored.view, "context")
        self.assertFalse(restored.assessment.confirmed)


if __name__ == "__main__":
    unittest.main()
