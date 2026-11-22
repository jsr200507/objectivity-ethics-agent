"""Progressive context clarification is reusable, adaptive and source-aware."""

from copy import deepcopy
import unittest

from objectivity.address import AddressState, assess_address, sync_address
from objectivity.evaluation import evaluate
from objectivity.examples import EXAMPLE_SCENARIO
from objectivity.extraction import extract_context
from objectivity.intake import (
    ANOTHER_INTEREST, BOTH_INTERESTS, FAMILY_INTEREST, FAMILY_RELATIONSHIP,
    NO_INTEREST, NOT_APPLICABLE, ORGANISATION_INTEREST, OTHER_INTEREST,
    OTHER_PRESSURE, OTHER_RELATIONSHIP, PROVIDED, SELF_INTEREST, UNKNOWN,
    clarification_fingerprint, confirm_intake, intake_questions,
    is_current_clarification, next_intake_question, question_for_field,
    save_intake_answer, sync_intake, validate_clarification,
)
from objectivity.models import Answer, Assessment, Context, ContextClarification
from objectivity.progress import export_progress, import_progress
from objectivity.questions import confirm_context, next_question
from objectivity.review import ReviewState, sync_review


def complete_context(**changes):
    context = Context(
        role="Marine grant coordinator", parties="Conservation panel and named applicants",
        decision="Recommend a habitat restoration grant",
        relationship="Professional relationship only", interests="No known interest",
        pressure="No reported pressure",
    )
    for field, value in changes.items():
        setattr(context, field, value)
    return context


def assessment(**changes):
    return Assessment(scenario="A reported professional judgement with relevant circumstances.", context=complete_context(**changes))


class IntakeTests(unittest.TestCase):
    def test_supported_cfo_context_needs_no_fixed_questionnaire(self):
        value = Assessment(scenario=EXAMPLE_SCENARIO, context=extract_context(EXAMPLE_SCENARIO).context)
        self.assertEqual(intake_questions(value), ())
        self.assertIsNone(next_intake_question(value))
        self.assertEqual(evaluate(value).findings, ())
        confirm_intake(value)
        self.assertTrue(value.confirmed)
        self.assertEqual(next_question(value).id, "pressure_basis")

    def test_prioritises_unfamiliar_role_then_decision_then_weak_party_list(self):
        value = assessment(role="Unknown", decision="Unknown", parties="Director")
        self.assertEqual(next_intake_question(value).id, "role")
        save_intake_answer(value, "role", detail="Coastal adaptation programme coordinator")
        self.assertEqual(value.context.role, "Coastal adaptation programme coordinator")
        self.assertEqual(next_intake_question(value).id, "decision")
        save_intake_answer(value, "decision", detail="Rank applications for a flood resilience grant")
        self.assertEqual(next_intake_question(value).id, "parties")
        save_intake_answer(value, "parties", detail="The coordinator, grant director and named applicants")
        self.assertIsNone(next_intake_question(value))
        self.assertEqual(evaluate(value).findings, ())
        self.assertFalse(value.confirmed)

    def test_arbitrary_professional_role_does_not_require_recognised_title(self):
        value = assessment(role="Unknown")
        save_intake_answer(value, "role", PROVIDED, "Heritage collections registrar")
        self.assertEqual(value.context.role, "Heritage collections registrar")
        self.assertTrue(is_current_clarification(value, "role"))
        self.assertIsNone(next_intake_question(value))

    def test_missing_details_require_clarification_or_explicit_unknown(self):
        value = Assessment(scenario="Something happened at work.")
        with self.assertRaises(ValueError): confirm_intake(value)
        seen = []
        for _ in range(7):
            question = next_intake_question(value)
            if question is None: break
            seen.append(question.id)
            save_intake_answer(value, question.id, UNKNOWN)
        self.assertEqual(seen, ["role", "decision", "parties", "relationship", "interests", "pressure"])
        self.assertIsNone(next_intake_question(value))
        confirm_intake(value)
        self.assertIsNone(next_question(value), "The same relevance questions must not be asked again")
        self.assertEqual(set(value.answers), {"pressure_relevance", "relationship_relevance", "interest_relevance"})
        self.assertTrue(all(answer.choice == "Unknown" for answer in value.answers.values()))
        self.assertTrue(evaluate(value).unknowns)
        self.assertEqual(evaluate(value).findings, ())

    def test_resolved_unknown_does_not_become_negative_fact(self):
        value = assessment(pressure="Unknown")
        save_intake_answer(value, "pressure", UNKNOWN)
        self.assertEqual(value.context.pressure, "Unknown")
        self.assertNotEqual(value.context.pressure, "No reported pressure")
        self.assertIsNone(next_intake_question(value))
        self.assertIn("not known", value.context.pressure_notes)

    def test_explicit_not_applicable_is_supported_without_invented_absence(self):
        value = assessment(relationship="Unknown", interests="Unknown", pressure="Unknown")
        for field in ("relationship", "interests", "pressure"):
            save_intake_answer(value, field, NOT_APPLICABLE)
        self.assertIsNone(next_intake_question(value))
        self.assertEqual(value.context.relationship, "Not applicable")
        self.assertEqual(value.context.interests, "Not applicable")
        confirm_intake(value)
        self.assertEqual(value.answers, {})

    def test_professional_other_with_supported_notes_is_not_reasked(self):
        value = assessment(relationship="Other", relationship_notes="A professional association is reported; personal closeness is unspecified.")
        self.assertIsNone(next_intake_question(value))

    def test_unsupported_other_relationship_gets_focused_question(self):
        value = assessment(relationship="Other", relationship_notes="")
        self.assertEqual(next_intake_question(value).id, "relationship")
        save_intake_answer(value, "relationship", FAMILY_RELATIONSHIP, "My sister holds shares in an applicant.")
        self.assertEqual(value.context.relationship, "Other")
        self.assertIn("closeness is not established", value.context.relationship_notes)
        confirm_intake(value)
        self.assertEqual(value.answers["relationship_relevance"].choice, "Possibly relevant")
        self.assertEqual(next_question(value).id, "relationship_contact")

    def test_relationship_professional_only_is_user_selection_never_inference(self):
        value = assessment(relationship="Unknown")
        save_intake_answer(value, "relationship", "Professional relationship only")
        self.assertEqual(value.context.relationship, "Professional relationship only")
        confirm_intake(value)
        self.assertNotIn("relationship_relevance", value.answers)

    def test_direct_and_organisational_interests_remain_distinct(self):
        for choice, expected in (
            (SELF_INTEREST, "Personal financial interest"),
            (ORGANISATION_INTEREST, "Commercial interest"),
            (BOTH_INTERESTS, "Both commercial and personal interests"),
            (NO_INTEREST, "No known interest"),
        ):
            with self.subTest(choice=choice):
                value = assessment(interests="Unknown")
                save_intake_answer(value, "interests", choice, "The reported recipient and connection.")
                self.assertEqual(value.context.interests, expected)
                self.assertIsNone(next_intake_question(value))
                confirm_intake(value)
                expected_question = "personal_connection" if choice == SELF_INTEREST else "commercial_connection"
                if choice != NO_INTEREST: self.assertEqual(next_question(value).id, expected_question)

    def test_family_interest_is_not_assigned_to_user_and_names_recipient(self):
        value = assessment(interests="Other")
        save_intake_answer(value, "interests", FAMILY_INTEREST)
        self.assertEqual(value.context.interests, "Other")
        self.assertEqual(next_intake_question(value).id, "beneficiary")
        save_intake_answer(value, "beneficiary", detail="My sister holds shares in the supplier.")
        self.assertIsNone(next_intake_question(value))
        self.assertIn("My sister holds shares", value.context.interests_notes)
        self.assertIn("benefit for the user or household is not established", value.context.interests_notes)
        confirm_intake(value)
        self.assertEqual(value.answers["interest_relevance"].choice, "Other")
        self.assertNotIn("Self-interest", {finding.kind for finding in evaluate(value).findings})

    def test_other_person_fee_remains_counterpart_interest(self):
        value = assessment(interests="Other")
        save_intake_answer(value, "interests", ANOTHER_INTEREST, "The procurement director receives a consulting fee from the supplier.")
        self.assertIsNone(next_intake_question(value), "A named recipient explanation avoids an unnecessary repeat question")
        self.assertEqual(value.context.interests, "Other")
        self.assertIn("procurement director receives a consulting fee", value.context.interests_notes)
        self.assertIn("personal benefit for the user is not established", value.context.interests_notes)

    def test_missing_beneficiary_can_be_explicitly_unknown(self):
        value = assessment(interests="Other")
        save_intake_answer(value, "interests", OTHER_INTEREST)
        self.assertEqual(next_intake_question(value).id, "beneficiary")
        save_intake_answer(value, "beneficiary", UNKNOWN)
        self.assertIsNone(next_intake_question(value))
        self.assertIn("Specific beneficiary or interest details are not known", value.context.interests_notes)
        self.assertEqual(sync_intake(value), ())

    def test_financial_beneficiary_change_reselects_applicable_followups(self):
        value = assessment(interests="Other")
        save_intake_answer(value, "interests", FAMILY_INTEREST)
        save_intake_answer(value, "beneficiary", detail="My sister's supplier shares")
        save_intake_answer(value, "interests", BOTH_INTERESTS, "My bonus and company profits")
        self.assertNotIn("beneficiary", value.context_clarifications)
        self.assertNotIn("My sister", value.context.interests_notes)
        self.assertIsNone(next_intake_question(value))
        confirm_intake(value)
        self.assertEqual(next_question(value).id, "commercial_connection")

    def test_reported_request_does_not_become_verified_threat_or_completed_work(self):
        value = assessment(pressure="Unknown")
        save_intake_answer(value, "pressure", "Reported pressure or threatened consequences", "A director asked me not to raise the issue with auditors.")
        self.assertEqual(value.context.pressure, "Reported pressure or threatened consequences")
        self.assertIn("does not establish an explicit threat", value.context.pressure_notes)
        self.assertIn("completed change", value.context.pressure_notes)
        self.assertEqual(evaluate(value).findings, ())
        confirm_intake(value)
        self.assertEqual(next_question(value).id, "pressure_basis")

    def test_other_pressure_reuses_explicit_other_without_interpreting_explanation(self):
        value = assessment(pressure="Unknown")
        save_intake_answer(value, "pressure", OTHER_PRESSURE, "I cannot classify the influence yet.")
        confirm_intake(value)
        self.assertEqual(value.answers["pressure_relevance"].choice, "Other")
        self.assertIsNone(next_question(value))

    def test_existing_extraction_can_be_corrected_without_reparsing_answer(self):
        value = assessment(role="Auditor", interests="Personal financial interest")
        self.assertEqual(question_for_field("role").id, "role")
        save_intake_answer(value, "role", detail="Tender evaluation analyst")
        save_intake_answer(value, "interests", ANOTHER_INTEREST, "The director receives the fee; I do not receive it.")
        self.assertEqual(value.context.role, "Tender evaluation analyst")
        self.assertEqual(value.context.interests, "Other")
        self.assertEqual(evaluate(value).findings, ())

    def test_changed_source_archives_phase_answers_and_requires_confirmation(self):
        value = assessment()
        confirm_context(value, value.scenario, value.context)
        value.answers["pressure_relevance"] = Answer("Unknown", "An earlier recorded answer")
        save_intake_answer(value, "role", detail="Revised grant coordinator")
        self.assertFalse(value.confirmed)
        self.assertEqual(value.answers, {})
        self.assertEqual(value.archive[-1].answer.explanation, "An earlier recorded answer")

    def test_metadata_only_first_answer_also_archives_old_confirmed_answers(self):
        value = assessment(role="Unknown")
        confirm_context(value, value.scenario, value.context)
        value.answers["pressure_relevance"] = Answer("Unknown")
        save_intake_answer(value, "role", UNKNOWN)
        self.assertFalse(value.confirmed)
        self.assertFalse(value.answers)
        self.assertTrue(value.archive)

    def test_identical_current_answer_is_noop(self):
        value = assessment(role="Unknown")
        save_intake_answer(value, "role", detail="Tender analyst")
        confirm_intake(value)
        before = deepcopy(value)
        save_intake_answer(value, "role", detail="Tender analyst")
        self.assertEqual(value, before)

    def test_core_edit_invalidates_dependent_unknown_resolutions(self):
        value = assessment(pressure="Unknown")
        save_intake_answer(value, "pressure", UNKNOWN)
        self.assertTrue(is_current_clarification(value, "pressure"))
        save_intake_answer(value, "role", detail="Different professional role")
        self.assertNotIn("pressure", value.context_clarifications)
        self.assertEqual(next_intake_question(value).id, "pressure")

    def test_topic_edit_retains_unrelated_clarification(self):
        value = assessment(pressure="Unknown", interests="Unknown")
        save_intake_answer(value, "interests", UNKNOWN)
        save_intake_answer(value, "pressure", "No reported pressure")
        self.assertTrue(is_current_clarification(value, "interests"))
        self.assertIsNone(next_intake_question(value))

    def test_scenario_change_discards_previous_resolution(self):
        value = assessment(role="Unknown")
        save_intake_answer(value, "role", UNKNOWN)
        value.scenario = "A different reported professional situation."
        self.assertEqual(sync_intake(value), ("role",))
        self.assertEqual(next_intake_question(value).id, "role")

    def test_manual_context_change_discards_stale_metadata(self):
        value = assessment(pressure="Unknown")
        save_intake_answer(value, "pressure", UNKNOWN)
        value.context.pressure = "Reported pressure or threatened consequences"
        self.assertEqual(sync_intake(value), ("pressure",))
        self.assertEqual(value.context.pressure, "Reported pressure or threatened consequences")

    def test_beneficiary_dependency_prunes_regardless_of_record_order(self):
        value = assessment(interests="Other")
        save_intake_answer(value, "interests", FAMILY_INTEREST)
        save_intake_answer(value, "beneficiary", detail="A sister's supplier shareholding")
        primary = value.context_clarifications["interests"]
        recipient = value.context_clarifications["beneficiary"]
        value.context_clarifications = {
            "beneficiary": recipient,
            "interests": ContextClarification(primary.choice, primary.detail, "0" * 64),
        }
        removed = sync_intake(value)
        self.assertEqual(set(removed), {"beneficiary", "interests"})
        self.assertEqual(value.context_clarifications, {})

    def test_legacy_confirmed_unknown_context_does_not_force_new_intake(self):
        value = Assessment(scenario="A previously reviewed account", context=Context(role="Unknown", parties="Unknown", decision="Unknown"))
        confirm_context(value, value.scenario, value.context)
        self.assertIsNone(next_intake_question(value))
        self.assertEqual(question_for_field("role").field, "role")

    def test_confirm_does_not_overwrite_later_phase_one_answer(self):
        value = assessment(pressure="Unknown")
        save_intake_answer(value, "pressure", UNKNOWN)
        confirm_intake(value)
        value.answers["pressure_relevance"] = Answer("Possibly", "New information recorded later")
        confirm_intake(value)
        self.assertEqual(value.answers["pressure_relevance"].choice, "Possibly")

    def test_context_edit_invalidates_review_and_address_state(self):
        value = assessment(pressure="Unknown")
        save_intake_answer(value, "pressure", UNKNOWN)
        confirm_intake(value)
        review, address = ReviewState(), AddressState()
        sync_review(value, review)
        sync_address(value, review, address)
        review.answers["objectivity_basis"] = Answer("Confidence in my own impartiality")
        address.answers["Intimidation:0:action"] = Answer("Arrange independent review")
        address.prompts["Intimidation:0:action"] = "What action will you take?"
        save_intake_answer(value, "pressure", "Reported pressure or threatened consequences", "A reported instruction")
        sync_review(value, review)
        sync_address(value, review, address)
        self.assertFalse(review.answers)
        self.assertFalse(address.answers)
        self.assertTrue(review.archive)
        self.assertTrue(address.archive)
        residual = assess_address(value, review, address)
        self.assertEqual(residual.outcomes, ())
        self.assertIn("Earlier clarification or evaluation questions still need answers.", residual.unknowns)

    def test_current_tokens_validate_source_consistency(self):
        value = assessment(role="Unknown")
        save_intake_answer(value, "role", PROVIDED, "Restoration grant coordinator")
        record = value.context_clarifications["role"]
        self.assertTrue(validate_clarification(value, "role", record))
        self.assertEqual(record.fingerprint, clarification_fingerprint(value, "role"))
        forged = ContextClarification(UNKNOWN, "", record.fingerprint)
        self.assertFalse(validate_clarification(value, "role", forged))
        self.assertFalse(validate_clarification(value, "unsupported", record))

    def test_empty_invalid_or_unbounded_answers_do_not_mutate_context(self):
        for args in (("role", "", ""), ("role", "Invalid choice", "A role"), ("interests", "Invented category", ""), ("role", PROVIDED, "x" * 100001)):
            with self.subTest(args=args[:2]):
                value = assessment()
                before = deepcopy(value)
                with self.assertRaises(ValueError): save_intake_answer(value, *args)
                self.assertEqual(value, before)
        with self.assertRaises(ValueError): question_for_field("unsupported")
        with self.assertRaises(ValueError): save_intake_answer(assessment(), "beneficiary", detail="A person")

    def test_generated_explanation_must_fit_existing_progress_text_limit(self):
        value = assessment(interests="Unknown")
        before = deepcopy(value)
        with self.assertRaises(ValueError):
            save_intake_answer(value, "interests", ANOTHER_INTEREST, "x" * 100_000)
        self.assertEqual(value, before)

    def test_combined_beneficiary_notes_are_bounded_without_partial_mutation(self):
        value = assessment(interests="Other")
        save_intake_answer(value, "interests", FAMILY_INTEREST, "a" * 50_000)
        before = deepcopy(value)
        with self.assertRaises(ValueError):
            save_intake_answer(value, "beneficiary", PROVIDED, "b" * 50_000)
        self.assertEqual(value, before)
        save_intake_answer(value, "beneficiary", PROVIDED, "b" * 40_000)
        review, address = ReviewState(), AddressState()
        restored = import_progress(export_progress(value, review, address, "context"))
        self.assertEqual(restored.assessment, value)
        self.assertGreater(len(value.context.interests_notes), 90_000)
        self.assertLessEqual(len(value.context.interests_notes), 100_000)

    def test_rejected_oversized_answer_does_not_prune_existing_stale_metadata(self):
        value = assessment(role="Unknown", interests="Unknown")
        save_intake_answer(value, "role", UNKNOWN)
        value.scenario = "A changed account before the attempted source save"
        before = deepcopy(value)
        with self.assertRaises(ValueError):
            save_intake_answer(value, "interests", ANOTHER_INTEREST, "x" * 100_000)
        self.assertEqual(value, before)


if __name__ == "__main__":
    unittest.main()
