"""Adaptive Phase 2 follow-ups and reassessment history, independent of UI."""

from copy import deepcopy
import unittest

from objectivity.models import Answer, Assessment, Context
from objectivity.questions import confirm_context, next_question, save_answer
from objectivity.review import (
    REVIEW_QUESTIONS,
    ReviewState,
    eligible_review_questions,
    next_review_question,
    save_review_answer,
    sync_review,
)


def assessment_for(**overrides):
    fields = dict(
        role="Professional adviser",
        parties="Client and professional team",
        decision="Make a professional recommendation",
        relationship="No relevant relationship",
        interests="No known interest",
        pressure="No reported pressure",
    )
    fields.update(overrides)
    assessment = Assessment()
    confirm_context(assessment, "A professional decision requires judgment.", Context(**fields))
    return assessment


def commercial_assessment():
    assessment = assessment_for(interests="Commercial interest")
    save_answer(assessment, "commercial_connection", "Contract renewal or client retention")
    save_answer(assessment, "commercial_dependence", "One of several sources")
    return assessment


def familiarity_assessment(responsibility="I make or recommend the decision"):
    assessment = assessment_for(relationship="Close personal relationship")
    save_answer(assessment, "relationship_contact", "Frequent personal contact")
    save_answer(assessment, "relationship_influence", responsibility)
    return assessment


def review_ids(assessment, state):
    return [question.id for question in eligible_review_questions(assessment, state)]


class ReviewQuestionTests(unittest.TestCase):
    def test_review_waits_for_context_confirmation(self):
        assessment = Assessment()
        state = ReviewState()
        self.assertEqual(eligible_review_questions(assessment, state), [])
        self.assertIsNone(next_review_question(assessment, state))

    def test_review_waits_for_existing_clarification(self):
        assessment = assessment_for(interests="Commercial interest")
        self.assertIsNotNone(next_question(assessment))
        self.assertEqual(eligible_review_questions(assessment, ReviewState()), [])

    def test_no_established_threat_does_not_add_generic_questionnaire(self):
        assessment = assessment_for()
        self.assertIsNone(next_question(assessment))
        self.assertEqual(review_ids(assessment, ReviewState()), [])

    def test_unknown_only_answers_do_not_activate_mitigation_questions(self):
        assessment = assessment_for(relationship="Unknown", interests="Unknown", pressure="Unknown")
        while question := next_question(assessment):
            save_answer(assessment, question.id, "Unknown")
        self.assertEqual(review_ids(assessment, ReviewState()), [])

    def test_missing_responsibility_is_asked_only_when_relevant(self):
        assessment = commercial_assessment()
        state = ReviewState()
        sync_review(assessment, state)
        self.assertEqual(next_review_question(assessment, state).id, "decision_responsibility")
        save_review_answer(assessment, state, "decision_responsibility", "I supervise or review the work")
        self.assertEqual(next_review_question(assessment, state).id, "objectivity_basis")

    def test_phase_one_responsibility_is_reused(self):
        assessment = familiarity_assessment()
        state = ReviewState()
        self.assertNotIn("decision_responsibility", review_ids(assessment, state))
        self.assertEqual(next_review_question(assessment, state).id, "objectivity_basis")

    def test_unknown_phase_one_responsibility_is_not_asked_again(self):
        assessment = familiarity_assessment("Unknown")
        state = ReviewState()
        self.assertNotIn("decision_responsibility", review_ids(assessment, state))

    def test_all_unsupported_claim_types_trigger_targeted_challenge(self):
        claims = (
            "Confidence in my own impartiality", "Disclosure of the circumstances",
            "Documentation of the circumstances", "A proposed safeguard",
        )
        for claim in claims:
            with self.subTest(claim=claim):
                assessment = familiarity_assessment()
                state = ReviewState()
                save_review_answer(assessment, state, "objectivity_basis", claim)
                self.assertEqual(next_review_question(assessment, state).id, "basis_challenge")
                save_review_answer(assessment, state, "basis_challenge", "No additional basis identified")
                self.assertIsNone(next_review_question(assessment, state))

    def test_no_assurance_claim_avoids_redundant_challenge(self):
        assessment = familiarity_assessment()
        state = ReviewState()
        save_review_answer(
            assessment, state, "objectivity_basis", "I am not claiming the threats are addressed"
        )
        self.assertNotIn("basis_challenge", review_ids(assessment, state))
        self.assertIsNone(next_review_question(assessment, state))

    def test_unknown_claim_preserves_uncertainty_without_guessing(self):
        assessment = familiarity_assessment()
        state = ReviewState()
        save_review_answer(
            assessment, state, "objectivity_basis", "Unknown", "I am confident it is all fine."
        )
        self.assertNotIn("basis_challenge", review_ids(assessment, state))
        self.assertEqual(state.answers["objectivity_basis"].choice, "Unknown")
        self.assertEqual(state.answers["objectivity_basis"].explanation, "I am confident it is all fine.")

    def test_questions_have_rationale_and_explicit_uncertainty_choices(self):
        for question in REVIEW_QUESTIONS.values():
            self.assertTrue(question.prompt)
            self.assertTrue(question.why)
            self.assertTrue({"Unknown", "Not applicable", "Other"}.issubset(question.options))
            self.assertEqual(len(question.options), len(set(question.options)))


class ReviewRevisionTests(unittest.TestCase):
    def setUp(self):
        self.assessment = commercial_assessment()
        self.state = ReviewState()
        save_review_answer(
            self.assessment, self.state, "decision_responsibility", "I make or recommend the decision"
        )
        save_review_answer(
            self.assessment, self.state, "objectivity_basis", "Confidence in my own impartiality", "Experience"
        )
        save_review_answer(
            self.assessment, self.state, "basis_challenge", "No additional basis identified", "No other basis"
        )

    def test_explanation_only_edit_preserves_followup_and_archives_old_text(self):
        save_review_answer(
            self.assessment, self.state, "objectivity_basis", "Confidence in my own impartiality", "Long experience"
        )
        self.assertEqual(self.state.answers["basis_challenge"].choice, "No additional basis identified")
        self.assertEqual(self.state.archive[-1].question_id, "objectivity_basis")
        self.assertEqual(self.state.archive[-1].answer.explanation, "Experience")

    def test_changed_claim_invalidates_previous_challenge(self):
        save_review_answer(
            self.assessment, self.state, "objectivity_basis", "A proposed safeguard"
        )
        self.assertNotIn("basis_challenge", self.state.answers)
        self.assertEqual(next_review_question(self.assessment, self.state).id, "basis_challenge")
        self.assertTrue(any(item.question_id == "basis_challenge" for item in self.state.archive))

    def test_changed_responsibility_invalidates_dependent_assurances(self):
        save_review_answer(
            self.assessment, self.state, "decision_responsibility", "I supervise or review the work"
        )
        self.assertNotIn("objectivity_basis", self.state.answers)
        self.assertNotIn("basis_challenge", self.state.answers)
        self.assertIn("decision_responsibility", self.state.answers)

    def test_removing_claim_archives_obsolete_challenge(self):
        save_review_answer(
            self.assessment, self.state, "objectivity_basis", "I am not claiming the threats are addressed"
        )
        self.assertIsNone(next_review_question(self.assessment, self.state))
        self.assertNotIn("basis_challenge", self.state.answers)

    def test_phase_one_choice_edit_invalidates_review_answers(self):
        save_answer(self.assessment, "commercial_connection", "No identified link to the decision")
        sync_review(self.assessment, self.state)
        self.assertEqual(self.state.answers, {})
        self.assertEqual(len(self.state.archive), 3)
        self.assertEqual(eligible_review_questions(self.assessment, self.state), [])

    def test_context_edit_invalidates_review_and_retains_history(self):
        context = deepcopy(self.assessment.context)
        context.interests = "No known interest"
        confirm_context(self.assessment, self.assessment.scenario, context)
        sync_review(self.assessment, self.state)
        self.assertEqual(self.state.answers, {})
        self.assertEqual({item.question_id for item in self.state.archive}, {
            "decision_responsibility", "objectivity_basis", "basis_challenge"
        })

    def test_phase_one_explanation_only_edit_does_not_reask_review(self):
        save_answer(
            self.assessment, "commercial_connection", "Contract renewal or client retention", "An explanation only"
        )
        sync_review(self.assessment, self.state)
        self.assertEqual(len(self.state.answers), 3)
        self.assertEqual(self.state.archive, [])

    def test_scenario_edit_invalidates_review(self):
        confirm_context(self.assessment, "A different professional decision.", self.assessment.context)
        sync_review(self.assessment, self.state)
        self.assertEqual(self.state.answers, {})
        self.assertEqual(len(self.state.archive), 3)

    def test_noop_save_and_sync_preserve_revision_and_history(self):
        revision = self.assessment.revision
        for _ in range(2):
            sync_review(self.assessment, self.state)
        save_review_answer(
            self.assessment, self.state, "basis_challenge", "No additional basis identified", "No other basis"
        )
        self.assertEqual(self.assessment.revision, revision)
        self.assertEqual(self.state.archive, [])

    def test_save_rejects_invalid_or_inapplicable_answers_without_mutation(self):
        before = deepcopy(self.state)
        revision = self.assessment.revision
        with self.assertRaises(ValueError):
            save_review_answer(self.assessment, self.state, "objectivity_basis", "Invented approval")
        with self.assertRaises(ValueError):
            save_review_answer(self.assessment, self.state, "unknown_question", "Unknown")
        self.assertEqual(self.state, before)
        self.assertEqual(self.assessment.revision, revision)

    def test_unrelated_stale_answer_does_not_change_review_signature(self):
        self.assessment.answers["pressure_effect"] = Answer("Yes", "An orphaned stale answer")
        sync_review(self.assessment, self.state)
        self.assertEqual(len(self.state.answers), 3)
        self.assertEqual(self.state.archive, [])

    def test_review_state_mutable_defaults_are_isolated(self):
        second = ReviewState()
        self.state.answers["test"] = Answer("Other")
        self.assertEqual(second.answers, {})
        self.assertEqual(second.archive, [])


if __name__ == "__main__":
    unittest.main()
