"""Branch selection and reassessment tests for the pure clarification engine."""

from copy import deepcopy
import unittest

from objectivity.examples import EXAMPLE_CONTEXT, EXAMPLE_SCENARIO
from objectivity.models import Answer, Assessment, Context
from objectivity.questions import (
    QUESTION_BANK,
    confirm_context,
    eligible_questions,
    next_question,
    save_answer,
)


def assessment_for(**overrides):
    fields = dict(
        role="Finance professional",
        parties="Manager and client",
        decision="Review a financial judgment",
        relationship="No relevant relationship",
        interests="No known interest",
        pressure="No reported pressure",
    )
    fields.update(overrides)
    assessment = Assessment()
    confirm_context(assessment, "A professional decision needs review.", Context(**fields))
    return assessment


def ids(assessment):
    return [q.id for q in eligible_questions(assessment)]


class ContextTests(unittest.TestCase):
    def test_unconfirmed_context_does_not_start_questions(self):
        assessment = Assessment(context=deepcopy(EXAMPLE_CONTEXT))
        self.assertEqual(eligible_questions(assessment), [])
        self.assertIsNone(next_question(assessment))

    def test_required_context_is_validated_before_mutation(self):
        assessment = Assessment()
        with self.assertRaises(ValueError):
            confirm_context(assessment, "", Context())
        self.assertFalse(assessment.confirmed)
        self.assertEqual(assessment.revision, 0)

    def test_invalid_structured_option_rejected(self):
        assessment = Assessment()
        context = Context(role="Manager", parties="CFO", decision="Revenue", pressure="Extracted automatically")
        with self.assertRaises(ValueError):
            confirm_context(assessment, "Scenario", context)

    def test_no_relevant_context_has_no_followups_or_ethical_conclusion(self):
        assessment = assessment_for()
        self.assertEqual(ids(assessment), [])
        self.assertIsNone(next_question(assessment))

    def test_unknown_and_other_require_explicit_relevance_answers(self):
        for option in ("Unknown", "Other"):
            assessment = assessment_for(relationship=option, interests=option, pressure=option)
            self.assertEqual(ids(assessment), ["pressure_relevance", "relationship_relevance", "interest_relevance"])

    def test_not_applicable_does_not_activate_branches(self):
        assessment = assessment_for(relationship="Not applicable", interests="Not applicable", pressure="Not applicable")
        self.assertEqual(ids(assessment), [])

    def test_free_text_does_not_trigger_paths(self):
        assessment = assessment_for(pressure_notes="My bonus depends on pleasing a close friend who threatened me.")
        self.assertEqual(ids(assessment), [])

    def test_example_must_be_confirmed_and_is_copied(self):
        assessment = Assessment()
        context = deepcopy(EXAMPLE_CONTEXT)
        confirm_context(assessment, EXAMPLE_SCENARIO, context)
        context.role = "Modified externally"
        self.assertEqual(assessment.context.role, "Audit manager of a listed client")
        self.assertEqual(ids(assessment), ["pressure_basis", "relationship_contact", "commercial_connection"])


class BranchTests(unittest.TestCase):
    def test_close_relationship_current_contact_branch(self):
        assessment = assessment_for(relationship="Close personal relationship")
        self.assertEqual(next_question(assessment).id, "relationship_contact")
        save_answer(assessment, "relationship_contact", "Frequent personal contact")
        self.assertEqual(next_question(assessment).id, "relationship_influence")
        self.assertNotIn("relationship_ties", ids(assessment))

    def test_historical_relationship_asks_about_remaining_ties(self):
        assessment = assessment_for(relationship="Close personal relationship")
        save_answer(assessment, "relationship_contact", "Little or no current personal contact")
        self.assertEqual(next_question(assessment).id, "relationship_ties")
        save_answer(assessment, "relationship_ties", "No")
        self.assertIsNone(next_question(assessment))
        self.assertNotIn("relationship_influence", ids(assessment))

    def test_unknown_contact_is_not_treated_as_absence(self):
        assessment = assessment_for(relationship="Close personal relationship")
        save_answer(assessment, "relationship_contact", "Unknown")
        self.assertEqual(next_question(assessment).id, "relationship_influence")

    def test_explicit_pressure_branches_to_consequence_and_effect(self):
        assessment = assessment_for(pressure="Reported pressure or threatened consequences")
        save_answer(assessment, "pressure_basis", "Explicitly stated")
        self.assertIn("pressure_consequence", ids(assessment))
        self.assertIn("pressure_effect", ids(assessment))
        self.assertNotIn("pressure_support", ids(assessment))
        save_answer(assessment, "pressure_consequence", "Employment or career consequences")
        save_answer(assessment, "pressure_effect", "Yes")
        self.assertEqual(next_question(assessment).id, "pressure_changes")

    def test_interpretation_without_support_has_shorter_pressure_path(self):
        assessment = assessment_for(pressure="Reported pressure or threatened consequences")
        save_answer(assessment, "pressure_basis", "My interpretation only")
        self.assertEqual(next_question(assessment).id, "pressure_support")
        save_answer(assessment, "pressure_support", "No further supporting information")
        self.assertIsNone(next_question(assessment))
        self.assertNotIn("pressure_effect", ids(assessment))

    def test_interpretation_with_support_reopens_consequence_path(self):
        assessment = assessment_for(pressure="Reported pressure or threatened consequences")
        save_answer(assessment, "pressure_basis", "My interpretation only")
        save_answer(assessment, "pressure_support", "A separate statement or action")
        self.assertEqual(next_question(assessment).id, "pressure_consequence")

    def test_commercial_interest_connected_and_unconnected_paths_differ(self):
        assessment = assessment_for(interests="Commercial interest")
        save_answer(assessment, "commercial_connection", "No identified link to the decision")
        self.assertIsNone(next_question(assessment))
        save_answer(assessment, "commercial_connection", "Contract renewal or client retention")
        self.assertEqual(next_question(assessment).id, "commercial_dependence")

    def test_personal_interest_asks_about_personal_outcome(self):
        assessment = assessment_for(interests="Personal financial interest")
        save_answer(assessment, "personal_connection", "Bonus or performance-related pay")
        self.assertEqual(next_question(assessment).id, "personal_outcome")
        self.assertNotIn("commercial_connection", ids(assessment))

    def test_both_interests_are_retained(self):
        assessment = assessment_for(interests="Both commercial and personal interests")
        self.assertEqual(ids(assessment), ["commercial_connection", "personal_connection"])

    def test_other_can_activate_a_confirmed_structured_path(self):
        assessment = assessment_for(interests="Other")
        save_answer(assessment, "interest_relevance", "Personal financial interest", "A shareholding")
        self.assertEqual(next_question(assessment).id, "personal_connection")

    def test_unknown_answer_preserves_uncertainty_and_does_not_guess(self):
        assessment = assessment_for(pressure="Unknown")
        save_answer(assessment, "pressure_relevance", "Unknown", "They threatened my job")
        self.assertIsNone(next_question(assessment))
        self.assertEqual(assessment.answers["pressure_relevance"].choice, "Unknown")

    def test_all_paths_coexist_in_example(self):
        assessment = Assessment()
        confirm_context(assessment, EXAMPLE_SCENARIO, EXAMPLE_CONTEXT)
        save_answer(assessment, "pressure_basis", "Implied in the conversation")
        save_answer(assessment, "pressure_consequence", "Loss of fees or a contract")
        save_answer(assessment, "pressure_effect", "No")
        self.assertEqual(next_question(assessment).id, "relationship_contact")
        save_answer(assessment, "relationship_contact", "Frequent personal contact")
        save_answer(assessment, "relationship_influence", "I make or recommend the decision")
        self.assertEqual(next_question(assessment).id, "commercial_connection")
        save_answer(assessment, "commercial_connection", "Contract renewal or client retention")
        save_answer(assessment, "commercial_dependence", "Unknown")
        self.assertIsNone(next_question(assessment))


class RevisionTests(unittest.TestCase):
    def test_changed_upstream_choice_archives_descendants(self):
        assessment = assessment_for(relationship="Close personal relationship")
        save_answer(assessment, "relationship_contact", "Frequent personal contact")
        save_answer(assessment, "relationship_influence", "I make or recommend the decision")
        save_answer(assessment, "relationship_contact", "Little or no current personal contact")
        self.assertNotIn("relationship_influence", assessment.answers)
        self.assertEqual(next_question(assessment).id, "relationship_ties")
        self.assertTrue(any(a.question_id == "relationship_influence" for a in assessment.archive))

    def test_still_applicable_descendants_need_reconfirmation_after_change(self):
        assessment = assessment_for(relationship="Close personal relationship")
        save_answer(assessment, "relationship_contact", "Frequent personal contact")
        save_answer(assessment, "relationship_influence", "I make or recommend the decision")
        save_answer(assessment, "relationship_contact", "Occasional personal contact")
        self.assertEqual(next_question(assessment).id, "relationship_influence")

    def test_explanation_edit_preserves_dependents_without_text_inference(self):
        assessment = assessment_for(interests="Personal financial interest")
        save_answer(assessment, "personal_connection", "Investment or ownership interest", "Shares")
        save_answer(assessment, "personal_outcome", "Yes")
        save_answer(assessment, "personal_connection", "Investment or ownership interest", "Different shares")
        self.assertEqual(assessment.answers["personal_connection"].explanation, "Different shares")
        self.assertEqual(assessment.answers["personal_outcome"].choice, "Yes")
        self.assertIsNone(next_question(assessment))
        self.assertEqual(len(assessment.archive), 1)
        self.assertEqual(assessment.archive[0].answer.explanation, "Shares")

    def test_changed_choice_still_invalidates_dependents(self):
        assessment = assessment_for(interests="Personal financial interest")
        save_answer(assessment, "personal_connection", "Investment or ownership interest", "Shares")
        save_answer(assessment, "personal_outcome", "Yes")
        save_answer(assessment, "personal_connection", "Bonus or performance-related pay", "Bonus")
        self.assertNotIn("personal_outcome", assessment.answers)
        self.assertEqual(next_question(assessment).id, "personal_outcome")

    def test_topic_context_edit_preserves_unaffected_answers(self):
        assessment = assessment_for(relationship="Close personal relationship", interests="Commercial interest")
        save_answer(assessment, "relationship_contact", "Frequent personal contact")
        save_answer(assessment, "commercial_connection", "Fees or profitability")
        context = deepcopy(assessment.context)
        context.relationship = "No relevant relationship"
        confirm_context(assessment, assessment.scenario, context)
        self.assertNotIn("relationship_contact", assessment.answers)
        self.assertIn("commercial_connection", assessment.answers)

    def test_scenario_edit_requires_all_answers_to_be_reconfirmed(self):
        assessment = assessment_for(interests="Commercial interest")
        save_answer(assessment, "commercial_connection", "Fees or profitability")
        confirm_context(assessment, "New decision involving a different client.", assessment.context)
        self.assertEqual(assessment.answers, {})
        self.assertEqual(len(assessment.archive), 1)

    def test_noop_save_and_confirmation_do_not_invalidate(self):
        assessment = assessment_for(interests="Commercial interest")
        save_answer(assessment, "commercial_connection", "Fees or profitability")
        revision = assessment.revision
        confirm_context(assessment, assessment.scenario, assessment.context)
        save_answer(assessment, "commercial_connection", "Fees or profitability")
        self.assertEqual(assessment.revision, revision)
        self.assertEqual(assessment.archive, [])

    def test_invalid_choice_or_inapplicable_question_rejected(self):
        assessment = assessment_for(interests="Commercial interest")
        with self.assertRaises(ValueError):
            save_answer(assessment, "commercial_connection", "Invented choice")
        with self.assertRaises(ValueError):
            save_answer(assessment, "pressure_basis", "Explicitly stated")
        self.assertEqual(assessment.answers, {})

    def test_mutable_defaults_are_not_shared(self):
        first, second = Assessment(), Assessment()
        first.answers["test"] = Answer("test")
        first.context.role = "Changed"
        self.assertEqual(second.answers, {})
        self.assertEqual(second.context.role, "")

    def test_questions_explain_why_and_offer_explicit_uncertainty(self):
        for question in QUESTION_BANK.values():
            self.assertTrue(question.prompt and question.why and question.topic)
            self.assertEqual(len(question.options), len(set(question.options)))
            self.assertTrue({"Unknown", "Not applicable", "Other"}.issubset(question.options))


if __name__ == "__main__":
    unittest.main()
