"""Existing acceptable circumstances must not create artificial safeguard work."""
from copy import deepcopy
import unittest

from objectivity.case_actions import (
    EFFECTIVE, INSUFFICIENT, SUPPORTED, UNACCEPTABLE, action_questions,
    assess_actions,
)
from objectivity.case_model import CaseAction
from objectivity.case_reasoning import ACCEPTABLE, reason_case
from objectivity.case_report import build_case_report
from objectivity.case_workflow import edit_case_fact, review_case
from tests.test_case_actions import action, fact, source_case


def unrelated_interest_case():
    case = source_case()
    case.scenario = 'An accountant assesses inventory with a fixed bonus reported as unrelated to that outcome.'
    next(item for item in case.facts if item.id == 'bonus').value = 'Fixed contractual bonus unrelated to the accounting outcome'
    case.facts = [item for item in case.facts if item.id != 'connection']
    case.facts.append(fact('connection', 'interest_connection', 'No'))
    case.actions_reviewed = False
    return case


class RefinedAddressReportTests(unittest.TestCase):
    def test_existing_acceptable_conditions_do_not_require_an_action_record(self):
        case = unrelated_interest_case()
        snapshot = reason_case(case)
        self.assertEqual(len(snapshot.threats), 1)
        self.assertEqual(snapshot.evaluations[0].outcome, ACCEPTABLE)
        result = assess_actions(case)
        self.assertEqual(result.outcomes[0].status, ACCEPTABLE)
        self.assertFalse(result.unknowns)
        self.assertFalse(result.actions)
        self.assertFalse(action_questions(case))
        self.assertIn('No additional safeguards are indicated', result.conclusion)
        self.assertNotIn('Establish what has already been done', ' '.join(result.next_steps))

    def test_optional_planned_review_is_not_counted_as_implemented_protection(self):
        case = unrelated_interest_case()
        action(case, stage='Planned')
        result = assess_actions(case)
        self.assertEqual(result.actions[0].status, 'Planned')
        self.assertFalse(result.actions[0].effective)
        self.assertEqual(result.outcomes[0].status, ACCEPTABLE)
        self.assertIn('does not rely on a proposed', ' '.join(result.outcomes[0].reasoning))

    def test_optional_implemented_review_does_not_trigger_irrelevant_checklist(self):
        case = unrelated_interest_case()
        action(case, checks={}, evidence='')
        result = assess_actions(case)
        self.assertFalse(result.actions[0].effective)
        self.assertFalse(action_questions(case))
        self.assertEqual(result.outcomes[0].status, ACCEPTABLE)

    def test_unlinked_optional_unknown_action_does_not_force_implementation_question(self):
        case = unrelated_interest_case()
        case.actions = [CaseAction('optional', 'A review may have been requested',
                                   'independent_review', 'Unknown')]
        self.assertFalse(action_questions(case))
        self.assertEqual(assess_actions(case).outcomes[0].status, ACCEPTABLE)

    def test_action_scope_is_established_before_implementation_details_are_questioned(self):
        case = source_case()
        case.actions = [CaseAction('source-action', 'An independent review may have been requested',
                                   'independent_review', 'Unknown')]
        self.assertFalse(action_questions(case))
        self.assertNotEqual(assess_actions(case).outcomes[0].status, ACCEPTABLE)

    def test_acceptability_does_not_validate_an_optional_ineffective_review(self):
        case = unrelated_interest_case()
        action(case, checks={'independence': 'No'}, evidence='')
        result = assess_actions(case)
        self.assertFalse(result.actions[0].effective)
        self.assertTrue(result.actions[0].failed)
        self.assertEqual(result.outcomes[0].status, ACCEPTABLE)
        self.assertIn('distinct', ' '.join(result.outcomes[0].reasoning))

    def test_continuing_influence_blocks_otherwise_acceptable_conditions(self):
        case = unrelated_interest_case()
        action(case, checks={'outcome': 'Continuing influence remains'}, evidence='')
        result = assess_actions(case)
        self.assertNotEqual(result.outcomes[0].status, ACCEPTABLE)
        self.assertIn('conflicts', ' '.join(result.outcomes[0].unknowns))
        self.assertNotIn('No additional safeguards are indicated', result.conclusion)

    def test_user_confirmation_is_not_itself_evidence_of_acceptability(self):
        case = source_case()
        case.reviewed = False
        review_case(case)
        result = assess_actions(case)
        self.assertNotEqual(result.outcomes[0].status, ACCEPTABLE)
        self.assertEqual(result.outcomes[0].status, UNACCEPTABLE)

    def test_unreviewed_positive_suggestion_does_not_create_final_positive_residual(self):
        case = unrelated_interest_case()
        case.reviewed = False
        self.assertNotEqual(assess_actions(case).outcomes[0].status, ACCEPTABLE)
        self.assertNotIn('No additional safeguards are indicated', assess_actions(case).conclusion)

    def test_revised_connection_recalculates_need_for_action(self):
        case = unrelated_interest_case()
        first = assess_actions(case)
        edit_case_fact(case, 'connection', 'Yes')
        review_case(case)
        second = assess_actions(case)
        self.assertEqual(first.outcomes[0].status, ACCEPTABLE)
        self.assertEqual(second.outcomes[0].status, UNACCEPTABLE)
        self.assertTrue(second.next_steps)
        self.assertIn('Establish what has already been done', second.next_steps[0])

    def test_acceptable_and_unresolved_sources_are_not_collapsed(self):
        case = unrelated_interest_case()
        case.facts.append(fact('pressure', 'pressure', 'Finance director requests delay to recognition',
                               subject='cfo', object_id='user'))
        result = assess_actions(case)
        by_kind = {item.kind: item for item in result.outcomes}
        self.assertEqual(by_kind['Self-interest'].status, ACCEPTABLE)
        self.assertNotEqual(by_kind['Intimidation'].status, ACCEPTABLE)
        self.assertNotIn('No additional safeguards are indicated', result.conclusion)

    def test_existing_conditions_and_supported_actions_can_address_distinct_sources(self):
        case = unrelated_interest_case()
        case.facts += [
            fact('pressure', 'pressure', 'Finance director requests delay to recognition',
                 subject='cfo', object_id='user'),
            fact('work', 'work_changed', 'No', object_id='cfo'),
        ]
        snapshot = reason_case(case)
        target = next(item.id for item in snapshot.threats if item.kind == 'Intimidation')
        action(case, selected=(target,))
        case.actions_reviewed = True
        result = assess_actions(case)
        self.assertEqual({item.status for item in result.outcomes}, {ACCEPTABLE, SUPPORTED})
        self.assertIn('conditionally supports', result.conclusion)

    def test_report_keeps_identify_evaluate_address_even_without_new_safeguard(self):
        case = unrelated_interest_case()
        report = build_case_report(case)
        for stage in ('#### A. IDENTIFY', '#### B. EVALUATE', '#### C. ADDRESS'):
            self.assertIn(stage, report)
        self.assertIn('Implementation status and effectiveness', report)
        self.assertIn('Residual position', report)
        self.assertIn('Self\\-interest', report)
        self.assertIn('At an acceptable level', report)
        self.assertIn('The finding rests on existing conditions', report)
        self.assertIn('no additional safeguard is indicated', report.lower())
        self.assertIn('Decision outcome affects the reported interest: No', report)
        self.assertIn('not an assumed completed safeguard', report)
        self.assertNotIn('No action effectiveness can be established from an unspecified action history', report)

    def test_report_distinguishes_optional_action_status_from_conditions(self):
        case = unrelated_interest_case()
        action(case, checks={}, evidence='')
        report = build_case_report(case)
        self.assertIn('not relied upon for the acceptable', report)
        self.assertNotIn('Implementation or effectiveness evidence still needed:', report)
        self.assertNotIn(EFFECTIVE, report)

    def test_recommendations_are_not_claimed_as_completed_safeguards(self):
        case = source_case()
        report = build_case_report(case)
        self.assertIn('recommendations, not completed safeguards', report)
        self.assertIn('inventory write', report)
        self.assertIn('**Primary safeguard:**', report)
        self.assertNotIn('**Recorded stage:** Implemented', report)

    def test_material_edit_updates_report_and_preserves_earlier_source(self):
        case = unrelated_interest_case()
        before = deepcopy(case)
        first = build_case_report(case)
        self.assertEqual(case, before)
        edit_case_fact(case, 'connection', 'Unknown', status='unknown')
        review_case(case)
        second = build_case_report(case)
        self.assertNotIn('No additional safeguards are indicated', second)
        self.assertIn('Significance remains uncertain', second)
        self.assertIn('Insufficient information to establish acceptability', second)
        self.assertIn('No additional safeguards are indicated', first)
        self.assertTrue(case.fact_history)


if __name__ == '__main__':
    unittest.main()
