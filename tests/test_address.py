"""Conditional action effectiveness, uncertainty and invalidation regressions."""

from copy import deepcopy
import unittest

from objectivity.address import (
    ACTION_OPTIONS, CHECKED, DECLINE, DISCLOSE, DOCUMENT, ELIMINATE, ENDED, ESCALATE,
    IMPLEMENTED, NO_ACTION, NOT_ESTABLISHED, REMAINS, REMOVAL, REVIEW, SUPPORTED,
    AddressState, add_supporting_action, address_ready, assess_address,
    eligible_address_questions, next_address_question, save_address_answer, sync_address,
)
from objectivity.examples import EXAMPLE_CONTEXT, EXAMPLE_SCENARIO
from objectivity.models import Assessment, Context
from objectivity.questions import confirm_context, save_answer
from objectivity.review import ReviewState, next_review_question, save_review_answer, sync_review


def setup_case(kind="Familiarity", cfo=False, pressure_changed=False):
    assessment = Assessment()
    context = Context(
        role="Manager", parties="Relevant colleague and team", decision="Professional judgment",
        relationship="No relevant relationship", interests="No known interest", pressure="No reported pressure",
    )
    if cfo:
        context = deepcopy(EXAMPLE_CONTEXT)
    elif kind == "Familiarity":
        context.relationship = "Close personal relationship"
    elif kind == "Intimidation":
        context.pressure = "Reported pressure or threatened consequences"
    elif kind == "Self-interest":
        context.interests = "Commercial interest"
    confirm_context(assessment, EXAMPLE_SCENARIO if cfo else "A user-reported scenario", context)
    if cfo or kind == "Intimidation":
        save_answer(assessment, "pressure_basis", "Implied in the conversation")
        save_answer(assessment, "pressure_consequence", "Loss of fees or a contract")
        save_answer(assessment, "pressure_effect", "Yes" if pressure_changed else "No")
        if pressure_changed:
            save_answer(assessment, "pressure_changes", "Procedures or evidence gathering")
    if cfo or kind == "Familiarity":
        save_answer(assessment, "relationship_contact", "Frequent personal contact")
        save_answer(assessment, "relationship_influence", "I make or recommend the decision")
    if cfo or kind == "Self-interest":
        save_answer(assessment, "commercial_connection", "Contract renewal or client retention")
        save_answer(assessment, "commercial_dependence", "Unknown" if cfo else "A major source of income or business")
    review = ReviewState()
    sync_review(assessment, review)
    while question := next_review_question(assessment, review):
        value = "I make or recommend the decision" if question.id == "decision_responsibility" else "I am not claiming the threats are addressed"
        save_review_answer(assessment, review, question.id, value)
    state = AddressState()
    sync_address(assessment, review, state)
    return assessment, review, state


def record(assessment, review, state, kind, field, value, slot=0, explanation=""):
    save_address_answer(assessment, review, state, f"{kind}:{slot}:{field}", value, explanation)


def successful_action(assessment, review, state, kind, action=REVIEW, slot=0):
    if slot == 0:
        record(assessment, review, state, kind, "action", action)
    values = {
        "implementation": IMPLEMENTED,
        "independence": "Reviewer is independent of the relevant influences",
        "competence": "Relevant competence is established",
        "authority": "Reassignment is authorised" if action == REMOVAL else "Can require changes before the decision is final",
        "replacement": "A competent person independent of this threat",
        "timing": "Before the decision or affected work was relied upon",
        "prior_work": "Affected work independently reconsidered and corrected where necessary",
        "effect": "No continuing influence identified in the outcome check",
        "obligations": "An appropriate responsible person reviewed these obligations",
        "evidence": CHECKED,
        "scope": {
            REVIEW: "All relevant aspects of this threat were reviewed",
            REMOVAL: "I have no remaining direct or indirect influence",
            DECLINE: "The activity ended and I have no continuing decision influence",
            ELIMINATE[kind]: {
                "Familiarity": "The relevant tie or obligation and its influence have ended",
                "Intimidation": "The pressure source and its ability to affect this decision have been removed",
                "Self-interest": "All relevant commercial and personal incentives have been removed",
            }[kind],
        }[action],
    }
    prefix = f"{kind}:{slot}:"
    while True:
        pending = next((q for q in eligible_address_questions(assessment, review, state)
                        if q.id.startswith(prefix) and q.id not in state.answers), None)
        if pending is None:
            break
        field = pending.id.rsplit(":", 1)[1]
        record(assessment, review, state, kind, field, values[field], slot=slot)


class AddressQuestionTests(unittest.TestCase):
    def test_unconfirmed_and_incomplete_stages_do_not_start_actions(self):
        assessment, review, state = setup_case()
        assessment.confirmed = False
        self.assertFalse(address_ready(assessment, review))
        self.assertEqual(eligible_address_questions(assessment, review, state), [])
        self.assertFalse(assess_address(assessment, review, state).current)

    def test_no_findings_does_not_invent_questionnaire(self):
        assessment, review, state = setup_case(kind="None")
        self.assertIsNone(next_address_question(assessment, review, state))
        result = assess_address(assessment, review, state)
        self.assertEqual(result.outcomes, ())
        self.assertIn("not an assurance", result.conclusion)
        self.assertIn("No potential threat is established", result.third_party)
        self.assertNotIn("missing information or remaining influence", result.third_party)

    def test_routes_are_tailored_to_current_threats(self):
        assessment, review, state = setup_case(cfo=True)
        questions = eligible_address_questions(assessment, review, state)
        self.assertEqual({q.id for q in questions}, {f"{kind}:0:action" for kind in ACTION_OPTIONS})
        self.assertIn(ELIMINATE["Familiarity"], questions[0].options)
        self.assertNotIn(ELIMINATE["Self-interest"], questions[0].options)

    def test_proposed_action_stops_before_effectiveness_questions(self):
        assessment, review, state = setup_case()
        record(assessment, review, state, "Familiarity", "action", REVIEW)
        record(assessment, review, state, "Familiarity", "implementation", "Proposed, not yet started")
        self.assertIsNone(next_address_question(assessment, review, state))
        outcome = assess_address(assessment, review, state).outcomes[0]
        self.assertEqual(outcome.status, NOT_ESTABLISHED)
        self.assertEqual(outcome.actions[0].stage, "Proposed, not yet started")

    def test_requested_review_is_not_implemented(self):
        assessment, review, state = setup_case()
        record(assessment, review, state, "Familiarity", "action", REVIEW)
        record(assessment, review, state, "Familiarity", "implementation", "Requested or in progress")
        self.assertEqual(assess_address(assessment, review, state).outcomes[0].status, NOT_ESTABLISHED)

    def test_ineffective_independence_stops_redundant_checklist(self):
        assessment, review, state = setup_case()
        record(assessment, review, state, "Familiarity", "action", REVIEW)
        record(assessment, review, state, "Familiarity", "implementation", IMPLEMENTED)
        record(assessment, review, state, "Familiarity", "independence", "Reviewer is not independent")
        self.assertIsNone(next_address_question(assessment, review, state))
        self.assertEqual(assess_address(assessment, review, state).outcomes[0].status, REMAINS)
        with self.assertRaises(ValueError):
            record(assessment, review, state, "Familiarity", "competence", "Relevant competence is established")

    def test_unknown_and_other_are_not_positive_checks(self):
        for choice in ("Unknown", "Other", "Not applicable"):
            with self.subTest(choice=choice):
                assessment, review, state = setup_case()
                record(assessment, review, state, "Familiarity", "action", REVIEW)
                record(assessment, review, state, "Familiarity", "implementation", IMPLEMENTED)
                record(assessment, review, state, "Familiarity", "independence", choice, explanation="It is definitely independent")
                result = assess_address(assessment, review, state)
                self.assertEqual(result.outcomes[0].status, NOT_ESTABLISHED)
                self.assertIn("Is the reviewer independent", " ".join(result.unknowns))

    def test_supporting_actions_allowed_without_replacing_primary(self):
        assessment, review, state = setup_case()
        record(assessment, review, state, "Familiarity", "action", DISCLOSE)
        record(assessment, review, state, "Familiarity", "implementation", "Requested or in progress")
        add_supporting_action(assessment, review, state, "Familiarity", REVIEW)
        self.assertEqual(len(state.extra_slots), 1)
        successful_action(assessment, review, state, "Familiarity", REVIEW, slot=1)
        result = assess_address(assessment, review, state)
        self.assertEqual(len(result.outcomes[0].actions), 2)
        self.assertEqual(result.outcomes[0].status, SUPPORTED)

    def test_wrong_threat_or_invalid_choices_rejected(self):
        assessment, review, state = setup_case()
        with self.assertRaises(ValueError):
            record(assessment, review, state, "Self-interest", "action", REVIEW)
        with self.assertRaises(ValueError):
            record(assessment, review, state, "Familiarity", "action", "Trust me")
        with self.assertRaises(ValueError):
            add_supporting_action(assessment, review, state, "Familiarity", REVIEW)
        self.assertEqual(state.answers, {})


class AddressReasoningTests(unittest.TestCase):
    def test_successful_review_supports_only_conditional_reduction(self):
        assessment, review, state = setup_case()
        successful_action(assessment, review, state, "Familiarity")
        result = assess_address(assessment, review, state)
        self.assertEqual(result.outcomes[0].status, SUPPORTED)
        self.assertIn("conditional support", result.conclusion)
        self.assertIn("not automatic clearance", result.conclusion)
        self.assertIn("not independently verified", result.third_party)

    def test_external_check_is_still_reported_not_app_verified(self):
        assessment, review, state = setup_case()
        successful_action(assessment, review, state, "Familiarity")
        summary = assess_address(assessment, review, state).outcomes[0].actions[0]
        self.assertIn("User reports an external independent check", summary.evidence_status)
        self.assertIn("not verified by the application", summary.evidence_status)

    def test_implementation_records_without_external_check_do_not_establish_reduction(self):
        assessment, review, state = setup_case()
        successful_action(assessment, review, state, "Familiarity")
        record(assessment, review, state, "Familiarity", "evidence", "Implementation records exist but no independent check")
        result = assess_address(assessment, review, state)
        self.assertEqual(result.outcomes[0].status, NOT_ESTABLISHED)
        self.assertIn("external independent check", " ".join(result.unknowns))

    def test_unsuccessful_action_cannot_reduce_threat(self):
        assessment, review, state = setup_case()
        record(assessment, review, state, "Familiarity", "action", REMOVAL)
        record(assessment, review, state, "Familiarity", "implementation", "Attempted but unsuccessful")
        result = assess_address(assessment, review, state)
        self.assertEqual(result.outcomes[0].status, REMAINS)
        self.assertIn("Replace or improve the unsuccessful response", result.next_steps[0])
        self.assertIn("Escalate ineffective", " ".join(result.next_steps))

    def test_bad_escalation_recipient_gets_targeted_reason_and_next_step(self):
        for recipient in ("A person affected by the same interest or pressure", "A person without authority"):
            with self.subTest(recipient=recipient):
                assessment, review, state = setup_case()
                record(assessment, review, state, "Familiarity", "action", ESCALATE)
                record(assessment, review, state, "Familiarity", "implementation", IMPLEMENTED)
                record(assessment, review, state, "Familiarity", "recipient", recipient)
                record(assessment, review, state, "Familiarity", "response", "No response")
                record(assessment, review, state, "Familiarity", "evidence", "My assertion only")
                result = assess_address(assessment, review, state)
                self.assertIn("lacks authority", " ".join(result.outcomes[0].reasoning))
                self.assertIn("independent of the relevant influences", " ".join(result.next_steps))
                self.assertIn("unanswered concern", " ".join(result.next_steps))

    def test_good_supporting_action_not_blocked_by_unused_proposal(self):
        assessment, review, state = setup_case()
        record(assessment, review, state, "Familiarity", "action", REMOVAL)
        record(assessment, review, state, "Familiarity", "implementation", "Proposed, not yet started")
        add_supporting_action(assessment, review, state, "Familiarity", REVIEW)
        successful_action(assessment, review, state, "Familiarity", REVIEW, slot=1)
        result = assess_address(assessment, review, state)
        self.assertEqual(result.outcomes[0].status, SUPPORTED)
        self.assertEqual(result.unknowns, ())
        self.assertIn("conditional support", result.conclusion)
        self.assertEqual(result.outcomes[0].actions[0].stage, "Proposed, not yet started")
        self.assertNotIn("Confirm completed implementation", " ".join(result.next_steps))

    def test_good_supporting_action_not_blocked_by_unsuccessful_old_measure(self):
        assessment, review, state = setup_case()
        record(assessment, review, state, "Familiarity", "action", REMOVAL)
        record(assessment, review, state, "Familiarity", "implementation", "Attempted but unsuccessful")
        add_supporting_action(assessment, review, state, "Familiarity", REVIEW)
        successful_action(assessment, review, state, "Familiarity", REVIEW, slot=1)
        result = assess_address(assessment, review, state)
        self.assertEqual(result.outcomes[0].status, SUPPORTED)
        self.assertEqual(result.unknowns, ())
        self.assertIn("reported unsuccessful", " ".join(result.outcomes[0].reasoning))

    def test_historical_confidence_does_not_replace_or_permanently_block_new_evidence(self):
        assessment, review, state = setup_case()
        save_review_answer(assessment, review, "objectivity_basis", "Confidence in my own impartiality")
        save_review_answer(assessment, review, "basis_challenge", "No additional basis identified")
        sync_address(assessment, review, state)
        successful_action(assessment, review, state, "Familiarity")
        result = assess_address(assessment, review, state)
        self.assertEqual(result.outcomes[0].status, SUPPORTED)
        self.assertEqual(result.unknowns, ())
        self.assertIn("conditional support", result.conclusion)

    def test_ineffective_review_next_step_is_specific_to_independence(self):
        assessment, review, state = setup_case()
        record(assessment, review, state, "Familiarity", "action", REVIEW)
        record(assessment, review, state, "Familiarity", "implementation", IMPLEMENTED)
        record(assessment, review, state, "Familiarity", "independence", "Reviewer is not independent")
        result = assess_address(assessment, review, state)
        self.assertIn("Arrange a reviewer independent", result.next_steps[0])

    def test_disclosure_escalation_and_documentation_not_automatically_sufficient(self):
        for action in (DISCLOSE, ESCALATE, DOCUMENT):
            with self.subTest(action=action):
                assessment, review, state = setup_case()
                record(assessment, review, state, "Familiarity", "action", action)
                record(assessment, review, state, "Familiarity", "implementation", IMPLEMENTED)
                while question := next_address_question(assessment, review, state):
                    choice = CHECKED if question.id.endswith(":evidence") else question.options[0]
                    save_address_answer(assessment, review, state, question.id, choice)
                self.assertNotEqual(assess_address(assessment, review, state).outcomes[0].status, SUPPORTED)

    def test_removal_checks_remaining_influence_and_replacement(self):
        assessment, review, state = setup_case()
        successful_action(assessment, review, state, "Familiarity", REMOVAL)
        self.assertEqual(assess_address(assessment, review, state).outcomes[0].status, SUPPORTED)
        record(assessment, review, state, "Familiarity", "scope", "I retain some influence")
        self.assertEqual(assess_address(assessment, review, state).outcomes[0].status, REMAINS)

    def test_partial_incentive_elimination_cannot_address_whole_threat(self):
        assessment, review, state = setup_case(kind="Self-interest")
        record(assessment, review, state, "Self-interest", "action", ELIMINATE["Self-interest"])
        record(assessment, review, state, "Self-interest", "implementation", IMPLEMENTED)
        record(assessment, review, state, "Self-interest", "scope", "An incentive remains or only part was removed")
        self.assertEqual(assess_address(assessment, review, state).outcomes[0].status, REMAINS)

    def test_elimination_requires_complete_source_change(self):
        for kind in ELIMINATE:
            with self.subTest(kind=kind):
                assessment, review, state = setup_case(kind=kind)
                successful_action(assessment, review, state, kind, ELIMINATE[kind])
                self.assertEqual(assess_address(assessment, review, state).outcomes[0].status, SUPPORTED)

    def test_prior_changed_work_needs_reconsideration_even_after_withdrawal(self):
        assessment, review, state = setup_case(kind="Intimidation", pressure_changed=True)
        successful_action(assessment, review, state, "Intimidation", DECLINE)
        self.assertEqual(assess_address(assessment, review, state).outcomes[0].status, ENDED)
        record(assessment, review, state, "Intimidation", "prior_work", "Affected work has not been independently reconsidered")
        self.assertEqual(assess_address(assessment, review, state).outcomes[0].status, REMAINS)

    def test_late_review_is_not_retroactive_protection(self):
        assessment, review, state = setup_case()
        successful_action(assessment, review, state, "Familiarity")
        record(assessment, review, state, "Familiarity", "timing", "After finalisation or too late")
        self.assertEqual(assess_address(assessment, review, state).outcomes[0].status, REMAINS)

    def test_combined_cfo_threats_and_missing_commercial_evidence_prevent_clearance(self):
        assessment, review, state = setup_case(cfo=True)
        for kind in ACTION_OPTIONS:
            successful_action(assessment, review, state, kind)
        result = assess_address(assessment, review, state)
        self.assertEqual({o.kind for o in result.outcomes}, set(ACTION_OPTIONS))
        commercial = next(o for o in result.outcomes if o.kind == "Self-interest")
        self.assertEqual(commercial.status, NOT_ESTABLISHED)
        self.assertIn("dependence", " ".join(commercial.unknowns))
        self.assertIn("does not yet establish", result.conclusion)

    def test_a_remaining_combined_threat_blocks_overall_reduction(self):
        assessment, review, state = setup_case(cfo=True)
        successful_action(assessment, review, state, "Familiarity")
        record(assessment, review, state, "Intimidation", "action", NO_ACTION)
        record(assessment, review, state, "Self-interest", "action", NO_ACTION)
        result = assess_address(assessment, review, state)
        self.assertEqual(result.outcomes[0].status, SUPPORTED)
        self.assertIn("does not yet establish", result.conclusion)

    def test_conflicting_persistent_influence_blocks_apparent_success(self):
        assessment, review, state = setup_case()
        successful_action(assessment, review, state, "Familiarity")
        add_supporting_action(assessment, review, state, "Familiarity", REMOVAL)
        record(assessment, review, state, "Familiarity", "implementation", IMPLEMENTED, slot=1)
        record(assessment, review, state, "Familiarity", "authority", "Reassignment is authorised", slot=1)
        record(assessment, review, state, "Familiarity", "scope", "I retain some influence", slot=1)
        outcome = assess_address(assessment, review, state).outcomes[0]
        self.assertEqual(outcome.status, REMAINS)
        self.assertIn("Continuing influence", " ".join(outcome.unknowns))


class AddressRevisionTests(unittest.TestCase):
    def test_earlier_choice_edit_archives_actions_and_cannot_keep_stale_conclusion(self):
        assessment, review, state = setup_case()
        successful_action(assessment, review, state, "Familiarity")
        save_answer(assessment, "relationship_contact", "Little or no current personal contact")
        result = assess_address(assessment, review, state)
        self.assertFalse(result.current)
        self.assertFalse(any(o.status == SUPPORTED for o in result.outcomes))
        sync_address(assessment, review, state)
        self.assertEqual(state.answers, {})
        self.assertTrue(state.archive)

    def test_phase2_edit_invalidates_address_state(self):
        assessment, review, state = setup_case()
        successful_action(assessment, review, state, "Familiarity")
        save_review_answer(assessment, review, "objectivity_basis", "Confidence in my own impartiality")
        self.assertFalse(assess_address(assessment, review, state).current)
        sync_address(assessment, review, state)
        self.assertEqual(state.answers, {})

    def test_changed_action_status_archives_dependent_checks(self):
        assessment, review, state = setup_case()
        successful_action(assessment, review, state, "Familiarity")
        record(assessment, review, state, "Familiarity", "implementation", "Proposed, not yet started")
        self.assertNotIn("Familiarity:0:evidence", state.answers)
        self.assertTrue(any(r.question_id.endswith(":evidence") for r in state.archive))
        self.assertEqual(assess_address(assessment, review, state).outcomes[0].status, NOT_ESTABLISHED)

    def test_explanation_only_edits_preserve_checks_without_interpreting_text(self):
        assessment, review, state = setup_case()
        successful_action(assessment, review, state, "Familiarity")
        record(assessment, review, state, "Familiarity", "implementation", IMPLEMENTED, explanation="It was verified by an authority.")
        self.assertIn("Familiarity:0:evidence", state.answers)
        self.assertEqual(len(state.archive), 1)

    def test_upstream_explanation_only_edit_does_not_invalidate_actions(self):
        assessment, review, state = setup_case()
        successful_action(assessment, review, state, "Familiarity")
        save_answer(assessment, "relationship_contact", "Frequent personal contact", "A different description")
        self.assertTrue(assess_address(assessment, review, state).current)
        sync_address(assessment, review, state)
        self.assertTrue(state.answers)

    def test_noop_answer_does_not_increase_revision(self):
        assessment, review, state = setup_case()
        record(assessment, review, state, "Familiarity", "action", REVIEW)
        revision = assessment.revision
        record(assessment, review, state, "Familiarity", "action", REVIEW)
        self.assertEqual(assessment.revision, revision)

    def test_assessment_is_pure_and_state_defaults_not_shared(self):
        assessment, review, state = setup_case()
        successful_action(assessment, review, state, "Familiarity")
        before = deepcopy((assessment, review, state))
        assess_address(assessment, review, state)
        self.assertEqual((assessment, review, state), before)
        self.assertEqual(AddressState().answers, {})
        self.assertEqual(AddressState().extra_slots, [])


if __name__ == "__main__":
    unittest.main()
