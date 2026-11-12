"""Evidence-linked rule outcomes and boundaries for Phase 2."""

from copy import deepcopy
import unittest

from objectivity.evaluation import (
    ACTION, INSUFFICIENT, POTENTIAL, UNSUPPORTED_BASES,
    effective_responsibility, evaluate,
)
from objectivity.examples import EXAMPLE_CONTEXT, EXAMPLE_SCENARIO
from objectivity.models import Answer, ArchivedAnswer, Assessment, Context
from objectivity.questions import confirm_context, save_answer


def assessment_for(**context_fields):
    context = Context(
        role="Manager", parties="Colleague and team", decision="A professional decision",
        relationship="No relevant relationship", interests="No known interest",
        pressure="No reported pressure",
    )
    for field, value in context_fields.items():
        setattr(context, field, value)
    assessment = Assessment()
    confirm_context(assessment, "A reported scenario", context)
    return assessment


def record(assessment, **answers):
    for id, choice in answers.items():
        save_answer(assessment, id, choice)
    return assessment


def review_role(choice="I make or recommend the decision", **answers):
    return {"decision_responsibility": Answer(choice), **{id: Answer(value) for id, value in answers.items()}}


def cfo_assessment():
    assessment = Assessment()
    confirm_context(assessment, EXAMPLE_SCENARIO, EXAMPLE_CONTEXT)
    return record(
        assessment,
        pressure_basis="Implied in the conversation",
        pressure_consequence="Loss of fees or a contract",
        pressure_effect="No",
        relationship_contact="Frequent personal contact",
        relationship_influence="I supervise or review the work",
        commercial_connection="Contract renewal or client retention",
        commercial_dependence="Unknown",
    )


class IdentificationTests(unittest.TestCase):
    def test_unconfirmed_context_cannot_generate_findings(self):
        assessment = Assessment(context=deepcopy(EXAMPLE_CONTEXT))
        assessment.answers["pressure_basis"] = Answer("Explicitly stated")
        result = evaluate(assessment, review_role())
        self.assertEqual(result.findings, ())
        self.assertIn("not been confirmed", result.unknowns[0])

    def test_no_relevant_circumstances_does_not_assert_compliance(self):
        result = evaluate(assessment_for())
        self.assertEqual(result.findings, ())
        self.assertEqual(result.unknowns, ())
        self.assertIn("not assurance", result.third_party)

    def test_narrative_explanations_and_notes_do_not_identify_threats(self):
        assessment = assessment_for(
            role="Auditor and CFO's friend", parties="CFO threatened me",
            pressure_notes="The CFO threatened the tax contract and bonus",
            relationship_notes="We are close friends", interests_notes="I own shares",
        )
        assessment.scenario = "My friend threatened to cancel contracts and I changed work."
        result = evaluate(assessment)
        self.assertEqual(result.findings, ())

    def test_unknown_only_does_not_invent_threats(self):
        assessment = assessment_for(relationship="Unknown", interests="Unknown", pressure="Unknown")
        record(assessment, pressure_relevance="Unknown", relationship_relevance="Other", interest_relevance="Unknown")
        result = evaluate(assessment)
        self.assertEqual(result.findings, ())
        self.assertGreaterEqual(len(result.unknowns), 3)
        self.assertIn("insufficient information", result.third_party)

    def test_familiarity_close_active_and_authority_requires_action_conditionally(self):
        assessment = record(
            assessment_for(relationship="Close personal relationship"),
            relationship_contact="Frequent personal contact",
            relationship_influence="I make or recommend the decision",
        )
        finding = evaluate(assessment).findings[0]
        self.assertEqual((finding.kind, finding.outcome), ("Familiarity", ACTION))
        self.assertIn("not proof", " ".join(finding.reasoning))
        self.assertTrue({"context.relationship", "answer.relationship_contact", "answer.relationship_influence"}.issubset({item.source for item in finding.evidence}))

    def test_historical_contact_without_ties_does_not_identify_current_familiarity(self):
        assessment = record(
            assessment_for(relationship="Close personal relationship"),
            relationship_contact="Little or no current personal contact", relationship_ties="No",
        )
        result = evaluate(assessment)
        self.assertEqual(result.findings, ())
        self.assertIn("current relevance", " ".join(result.unknowns))

    def test_historical_contact_with_current_ties_and_authority_is_relevant(self):
        assessment = record(
            assessment_for(relationship="Close personal relationship"),
            relationship_contact="Little or no current personal contact", relationship_ties="Yes",
            relationship_influence="I supervise or review the work",
        )
        self.assertEqual(evaluate(assessment).findings[0].kind, "Familiarity")

    def test_no_decision_involvement_does_not_establish_personal_threat(self):
        assessment = record(
            assessment_for(relationship="Close personal relationship"),
            relationship_contact="Frequent personal contact",
            relationship_influence="I have no involvement in this decision",
        )
        result = evaluate(assessment)
        self.assertEqual(result.findings, ())
        self.assertIn("not established", " ".join(result.unknowns))

    def test_explicit_pressure_with_consequence_and_authority_requires_action(self):
        assessment = record(
            assessment_for(pressure="Reported pressure or threatened consequences"),
            pressure_basis="Explicitly stated", pressure_consequence="Employment or career consequences",
            pressure_effect="No",
        )
        finding = evaluate(assessment, review_role()).findings[0]
        self.assertEqual((finding.kind, finding.outcome), ("Intimidation", ACTION))
        self.assertIn("potential future influence", " ".join(finding.reasoning))

    def test_interpretation_without_support_does_not_identify_intimidation(self):
        assessment = record(
            assessment_for(pressure="Reported pressure or threatened consequences"),
            pressure_basis="My interpretation only", pressure_support="No further supporting information",
        )
        result = evaluate(assessment, review_role())
        self.assertEqual(result.findings, ())
        self.assertIn("interpretation", " ".join(result.unknowns))

    def test_interpretation_with_separate_event_has_conditional_pressure_finding(self):
        assessment = record(
            assessment_for(pressure="Reported pressure or threatened consequences"),
            pressure_basis="My interpretation only", pressure_support="A separate statement or action",
            pressure_consequence="Personal or professional retaliation", pressure_effect="Unknown",
        )
        result = evaluate(assessment, review_role())
        self.assertEqual(result.findings[0].kind, "Intimidation")
        self.assertIn("answer.pressure_support", {item.source for item in result.findings[0].evidence})

    def test_commercial_connection_establishes_potential_not_personal_bonus(self):
        assessment = record(
            assessment_for(interests="Commercial interest"),
            commercial_connection="Contract renewal or client retention", commercial_dependence="Unknown",
        )
        finding = evaluate(assessment, review_role()).findings[0]
        self.assertEqual((finding.kind, finding.outcome), ("Self-interest", POTENTIAL))
        self.assertTrue(finding.unknowns)
        self.assertIn("does not establish a direct personal", " ".join(finding.reasoning))

    def test_major_commercial_dependence_and_responsibility_requires_action(self):
        assessment = record(
            assessment_for(interests="Commercial interest"),
            commercial_connection="Fees or profitability", commercial_dependence="A major source of income or business",
        )
        self.assertEqual(evaluate(assessment, review_role()).findings[0].outcome, ACTION)

    def test_no_commercial_link_does_not_identify_self_interest(self):
        assessment = record(
            assessment_for(interests="Commercial interest"),
            commercial_connection="No identified link to the decision",
        )
        self.assertEqual(evaluate(assessment, review_role()).findings, ())

    def test_direct_personal_benefit_with_outcome_and_authority_requires_action(self):
        assessment = record(
            assessment_for(interests="Personal financial interest"),
            personal_connection="Bonus or performance-related pay", personal_outcome="Yes",
        )
        self.assertEqual(evaluate(assessment, review_role()).findings[0].outcome, ACTION)

    def test_personal_benefit_without_known_outcome_remains_potential(self):
        assessment = record(
            assessment_for(interests="Personal financial interest"),
            personal_connection="Investment or ownership interest", personal_outcome="Unknown",
        )
        finding = evaluate(assessment, review_role()).findings[0]
        self.assertEqual(finding.outcome, POTENTIAL)
        self.assertIn("financial position", " ".join(finding.unknowns))

    def test_personal_outcome_no_does_not_invent_financial_incentive(self):
        assessment = record(
            assessment_for(interests="Personal financial interest"),
            personal_connection="Investment or ownership interest", personal_outcome="No",
        )
        self.assertEqual(evaluate(assessment, review_role()).findings, ())


class EvaluationTests(unittest.TestCase):
    def test_missing_decision_responsibility_blocks_stronger_commercial_outcome(self):
        assessment = record(
            assessment_for(interests="Commercial interest"),
            commercial_connection="Fees or profitability", commercial_dependence="A major source of income or business",
        )
        finding = evaluate(assessment).findings[0]
        self.assertEqual(finding.outcome, POTENTIAL)
        self.assertIn("responsibility", " ".join(finding.unknowns))

    def test_known_relationship_responsibility_is_reused(self):
        assessment = cfo_assessment()
        self.assertEqual(effective_responsibility(assessment), "I supervise or review the work")
        self.assertEqual(effective_responsibility(assessment, review_role("I have no involvement in this decision")), "I supervise or review the work")

    def test_unknown_phase1_responsibility_retains_its_source_and_is_not_reasked(self):
        assessment = cfo_assessment()
        save_answer(assessment, "relationship_influence", "Unknown")
        result = evaluate(assessment, review_role())
        self.assertEqual(effective_responsibility(assessment, review_role()), "Unknown")
        finding = next(f for f in result.findings if f.kind == "Familiarity")
        self.assertIn("answer.relationship_influence", {item.source for item in finding.evidence})
        self.assertIn("answer.relationship_influence", " ".join(finding.unknowns))
        self.assertNotIn("review.decision_responsibility", {item.source for item in finding.evidence})

    def test_actual_work_change_is_distinguished_without_declaring_misconduct(self):
        assessment = record(
            assessment_for(pressure="Reported pressure or threatened consequences"),
            pressure_basis="Explicitly stated", pressure_consequence="Loss of fees or a contract",
            pressure_effect="Yes", pressure_changes="Recommendation or judgment",
        )
        finding = evaluate(assessment, review_role()).findings[0]
        self.assertEqual(finding.outcome, ACTION)
        self.assertIn("reported actual effect", " ".join(finding.reasoning))
        self.assertIn("not proof", " ".join(finding.reasoning))

    def test_changed_work_and_no_involvement_is_a_conflict_not_certainty(self):
        assessment = record(
            assessment_for(pressure="Reported pressure or threatened consequences"),
            pressure_basis="Explicitly stated", pressure_consequence="Loss of fees or a contract",
            pressure_effect="Yes", pressure_changes="Procedures or evidence gathering",
        )
        finding = evaluate(assessment, review_role("I have no involvement in this decision")).findings[0]
        self.assertEqual(finding.outcome, INSUFFICIENT)
        self.assertIn("conflicts", " ".join(finding.unknowns))

    def test_responsibility_conflict_is_global_and_does_not_silently_discard_other_findings(self):
        assessment = cfo_assessment()
        save_answer(assessment, "relationship_influence", "I have no involvement in this decision")
        save_answer(assessment, "pressure_effect", "Yes")
        save_answer(assessment, "pressure_changes", "Recommendation or judgment")
        result = evaluate(assessment)
        self.assertEqual({f.kind for f in result.findings}, {"Familiarity", "Intimidation", "Self-interest"})
        self.assertTrue(all(f.outcome == INSUFFICIENT for f in result.findings))
        self.assertIn("conflicts", " ".join(result.unknowns))

    def test_relationship_pressure_interaction_does_not_infer_party_identity(self):
        result = evaluate(cfo_assessment())
        self.assertIn("If the relationship is with the person applying pressure", " ".join(result.interactions))
        self.assertIn("do not establish that these are the same person", " ".join(result.interactions))

    def test_all_three_threats_interact_in_cfo_example(self):
        result = evaluate(cfo_assessment())
        self.assertEqual({f.kind for f in result.findings}, {"Familiarity", "Intimidation", "Self-interest"})
        self.assertGreaterEqual(len(result.interactions), 2)
        self.assertIn("not independent corroboration", " ".join(result.interactions))
        self.assertIn("If the recorded account is accurate", result.third_party)

    def test_insufficient_consequence_does_not_get_invented(self):
        assessment = record(
            assessment_for(pressure="Reported pressure or threatened consequences"),
            pressure_basis="Implied in the conversation", pressure_consequence="Unknown", pressure_effect="Unknown",
        )
        finding = evaluate(assessment, review_role()).findings[0]
        self.assertEqual(finding.outcome, POTENTIAL)
        self.assertIn("nature of the consequence", " ".join(finding.unknowns))

    def test_unknown_closeness_preserves_gap_without_inventing_contact(self):
        assessment = record(
            assessment_for(relationship="Close personal relationship"),
            relationship_contact="Unknown", relationship_influence="I make or recommend the decision",
        )
        finding = evaluate(assessment).findings[0]
        self.assertEqual(finding.outcome, POTENTIAL)
        self.assertIn("current personal contact", " ".join(finding.unknowns))

    def test_all_unsupported_mitigation_claims_fail_to_downgrade(self):
        assessment = cfo_assessment()
        original = {finding.kind: finding.outcome for finding in evaluate(assessment).findings}
        for basis in UNSUPPORTED_BASES:
            with self.subTest(basis=basis):
                result = evaluate(assessment, {
                    "objectivity_basis": Answer(basis),
                    "basis_challenge": Answer("A specific change to the circumstances is reported", "I feel sure it is enough"),
                })
                self.assertEqual({finding.kind: finding.outcome for finding in result.findings}, original)
                self.assertIn(UNSUPPORTED_BASES[basis], result.third_party)
                self.assertTrue(all("review.objectivity_basis" in {item.source for item in finding.evidence} for finding in result.findings))

    def test_not_claiming_addressed_does_not_manufacture_a_challenge(self):
        result = evaluate(cfo_assessment(), {"objectivity_basis": Answer("I am not claiming the threats are addressed")})
        self.assertFalse(any("review.objectivity_basis" in gap for gap in result.unknowns))

    def test_changed_answer_recalculates_findings_and_excludes_superseded_evidence(self):
        assessment = cfo_assessment()
        old_revision = evaluate(assessment).revision
        save_answer(assessment, "pressure_basis", "My interpretation only")
        save_answer(assessment, "pressure_support", "No further supporting information")
        result = evaluate(assessment)
        self.assertGreater(result.revision, old_revision)
        self.assertNotIn("Intimidation", {f.kind for f in result.findings})
        self.assertTrue(any(record.question_id == "pressure_consequence" for record in assessment.archive))
        self.assertFalse(any(item.source == "answer.pressure_consequence" for finding in result.findings for item in finding.evidence))

    def test_stale_inapplicable_or_archived_answers_cannot_drive_findings(self):
        assessment = assessment_for()
        assessment.answers["pressure_basis"] = Answer("Explicitly stated")
        assessment.answers["personal_outcome"] = Answer("Yes")
        assessment.archive.append(ArchivedAnswer("relationship_contact", Answer("Frequent personal contact"), "Old context", 1))
        self.assertEqual(evaluate(assessment, review_role()).findings, ())

    def test_invalid_choice_not_used_as_evidence(self):
        assessment = assessment_for(pressure="Reported pressure or threatened consequences")
        assessment.answers["pressure_basis"] = Answer("Definitely verified")
        result = evaluate(assessment)
        self.assertEqual(result.findings, ())
        self.assertTrue(result.unknowns)

    def test_evidence_never_becomes_independently_verified_from_confirmation(self):
        result = evaluate(cfo_assessment())
        self.assertTrue(all("not independently verified" in item.status for finding in result.findings for item in finding.evidence))
        self.assertIn("No independently verified evidence", " ".join(result.limitations))

    def test_no_numerical_ethics_score_or_standards_validation_claim(self):
        result = evaluate(cfo_assessment())
        self.assertFalse(hasattr(result, "score"))
        self.assertIn("not ACCA/IESBA approval", " ".join(result.limitations))
        self.assertIn("separate audit-independence", " ".join(result.limitations))

    def test_evaluation_does_not_mutate_assessment_or_answers(self):
        assessment = cfo_assessment()
        before = deepcopy(assessment)
        evaluate(assessment, review_role(objectivity_basis="Disclosure of the circumstances"))
        self.assertEqual(assessment, before)


if __name__ == "__main__":
    unittest.main()
