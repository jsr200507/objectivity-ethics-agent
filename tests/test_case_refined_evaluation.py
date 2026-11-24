"""Retained favourable findings and material questions over scoped evidence."""
from copy import deepcopy
import unittest

from objectivity.case_model import CaseAction, CaseFact, CaseState
from objectivity.case_reasoning import ACCEPTABLE, ACTION_REQUIRED, NOT_ESTABLISHED, reason_case
from objectivity.case_workflow import answer_case_question, review_case
from tests.test_case_reasoning import case, fact, responsible


class RefinedEvaluationTests(unittest.TestCase):
    def test_career_interest_does_not_invent_a_financial_reward(self):
        state = case(responsible(), fact('career', 'interest', 'Promotion or career-related interest'),
                     fact('link', 'interest_connection', 'Yes'))
        result = reason_case(state)
        self.assertEqual(result.evaluations[0].outcome, ACTION_REQUIRED)
        self.assertIn('career prospects', result.threats[0].mechanism)
        self.assertNotIn('benefits you financially', result.threats[0].mechanism)

    def test_no_involvement_coalesces_earlier_work_question_across_sources(self):
        state = case(fact('responsibility', 'decision_responsibility', 'I have no involvement in this decision'),
                     fact('stake', 'interest', 'Bonus'),
                     fact('pressure', 'pressure', 'CFO asked for a favourable judgment', subject='cfo', object_id='user'))
        result = reason_case(state)
        self.assertEqual([q.predicate for q in result.questions], ['prior_work_affected'])
        self.assertEqual(set(result.questions[0].threat_ids), {t.id for t in result.threats})
        answer_case_question(state, result.questions[0].id, 'Unknown')
        self.assertFalse(reason_case(state).questions)

    def test_protective_nonconnection_cannot_ignore_reported_affected_work(self):
        state = case(responsible(), fact('stake', 'interest', 'Bonus'),
                     fact('link', 'interest_connection', 'No'),
                     fact('affected', 'prior_work_affected', 'Yes'))
        result = reason_case(state)
        self.assertEqual(result.evaluations[0].outcome, ACTION_REQUIRED)
        self.assertIn('conflicts', ' '.join(result.evaluations[0].material_gaps))

    def test_unrelated_interest_is_retained_with_favourable_basis_and_no_forced_question(self):
        state = case(fact('stake', 'interest', 'Shareholding', object_id='supplier'),
                     fact('link', 'interest_connection', 'No', object_id='supplier'))
        result = reason_case(state)
        self.assertEqual(len(result.threats), 1)
        self.assertEqual(result.evaluations[0].outcome, ACCEPTABLE)
        self.assertFalse(result.questions)
        self.assertIn('link', result.threats[0].evidence_ids)
        self.assertIn('no additional safeguard', ' '.join(result.evaluations[0].reasoning))
        self.assertIn('conditional on the account', result.evaluations[0].third_party)

    def test_interest_connection_change_keeps_identity_but_changes_evaluation(self):
        state = case(responsible(), fact('stake', 'interest', 'Shareholding', object_id='supplier'),
                     fact('link', 'interest_connection', 'No', object_id='supplier'))
        no = reason_case(state)
        state.facts[-1].value = 'Yes'
        yes = reason_case(state)
        self.assertEqual(no.threats[0].id, yes.threats[0].id)
        self.assertEqual(no.evaluations[0].outcome, ACCEPTABLE)
        self.assertEqual(yes.evaluations[0].outcome, ACTION_REQUIRED)

    def test_unknown_connection_is_not_a_favourable_evaluation_or_repeated_question(self):
        state = case(responsible(), fact('stake', 'interest', 'Bonus'),
                     fact('link', 'interest_connection', 'Unknown', status='unknown'))
        result = reason_case(state)
        self.assertEqual(result.evaluations[0].outcome, NOT_ESTABLISHED)
        self.assertFalse(result.questions)
        self.assertTrue(result.evaluations[0].material_gaps)

    def test_historical_relationship_without_current_connection_is_retained(self):
        state = case(fact('relation', 'close_relationship', 'Former close friendship', object_id='cfo'),
                     fact('current', 'relationship_active', 'No', object_id='cfo'))
        result = reason_case(state)
        self.assertEqual(result.threats[0].kind, 'Familiarity')
        self.assertEqual(result.evaluations[0].outcome, ACCEPTABLE)
        self.assertFalse(result.questions)
        self.assertIn('current', result.threats[0].evidence_ids)

    def test_no_current_ties_does_not_erase_connected_family_financial_interest(self):
        state = case(responsible(), fact('relation', 'family_relationship', 'Sister', object_id='sister'),
                     fact('current', 'relationship_active', 'No', object_id='sister'),
                     fact('shares', 'interest', 'Shareholding', subject='sister', object_id='supplier'),
                     fact('link', 'interest_connection', 'Yes', subject='sister', object_id='supplier'))
        result = reason_case(state)
        familiarity = next(e for e in result.evaluations if next(t for t in result.threats if t.id == e.threat_id).kind == 'Familiarity')
        self.assertEqual(familiarity.outcome, NOT_ESTABLISHED)
        self.assertIn('financial connection', ' '.join(familiarity.material_gaps))
        self.assertEqual(len(result.threats), 2)

    def test_inactive_tie_and_unknown_related_work_are_not_automatically_acceptable(self):
        state = case(responsible(), fact('relation', 'family_relationship', 'Sister', object_id='sister'),
                     fact('current', 'relationship_active', 'No', object_id='sister'),
                     fact('employer', 'employment', 'Valuation provider', subject='sister', object_id='valuer'),
                     fact('participation', 'participation', 'Unknown', subject='sister', object_id='valuer', status='unknown'))
        result = reason_case(state)
        self.assertEqual(result.evaluations[0].outcome, NOT_ESTABLISHED)
        self.assertFalse(result.questions)

    def test_inactive_tie_and_explicit_nonparticipation_support_existing_conditions(self):
        state = case(responsible(), fact('relation', 'family_relationship', 'Sister', object_id='sister'),
                     fact('current', 'relationship_active', 'No', object_id='sister'),
                     fact('employer', 'employment', 'Valuation provider', subject='sister', object_id='valuer'),
                     fact('participation', 'participation', 'No', subject='sister', object_id='valuer'))
        result = reason_case(state)
        self.assertEqual(result.evaluations[0].outcome, ACCEPTABLE)
        self.assertFalse(result.questions)
        self.assertFalse(result.evaluations[0].material_gaps)

    def test_no_current_involvement_alone_does_not_clear_earlier_work(self):
        state = case(fact('responsibility', 'decision_responsibility', 'I have no involvement in this decision'),
                     fact('stake', 'interest', 'Bonus'))
        result = reason_case(state)
        self.assertEqual(result.evaluations[0].outcome, NOT_ESTABLISHED)
        self.assertEqual([q.predicate for q in result.questions], ['prior_work_affected'])
        question = result.questions[0]
        self.assertTrue(question.why and question.impact and question.threat_ids)

    def test_explicit_unknown_prior_work_is_finite_and_limits_acceptability(self):
        state = case(fact('responsibility', 'decision_responsibility', 'I have no involvement in this decision'),
                     fact('stake', 'interest', 'Bonus'))
        question = reason_case(state).questions[0]
        answer_case_question(state, question.id, 'Unknown')
        result = reason_case(state)
        self.assertFalse(result.questions)
        self.assertEqual(result.evaluations[0].outcome, NOT_ESTABLISHED)

    def test_no_current_involvement_and_no_prior_affected_work_can_need_no_new_safeguard(self):
        state = case(fact('responsibility', 'decision_responsibility', 'I have no involvement in this decision'),
                     fact('stake', 'interest', 'Bonus'), fact('earlier', 'prior_work_affected', 'No'))
        result = reason_case(state)
        self.assertEqual(result.evaluations[0].outcome, ACCEPTABLE)
        self.assertFalse(result.questions)
        self.assertEqual(set(result.threats[0].evidence_ids), {'stake', 'responsibility', 'earlier'})

    def test_changed_prior_work_still_requires_response_despite_no_current_role(self):
        state = case(fact('responsibility', 'decision_responsibility', 'I have no involvement in this decision'),
                     fact('pressure', 'pressure', 'CFO requested suppression', subject='cfo', object_id='user'),
                     fact('changed', 'work_changed', 'Yes', object_id='cfo'))
        result = reason_case(state)
        self.assertEqual(result.evaluations[0].outcome, ACTION_REQUIRED)
        self.assertIn('earlier affected work', ' '.join(result.evaluations[0].material_gaps))

    def test_current_own_review_conflicts_with_claimed_no_involvement(self):
        for predicate in ('self_review', 'advocacy'):
            with self.subTest(predicate=predicate):
                state = case(fact('responsibility', 'decision_responsibility', 'I have no involvement in this decision'),
                             fact('source', predicate, 'Own work or position now being objectively reviewed'),
                             fact('earlier', 'prior_work_affected', 'No'))
                result = reason_case(state)
                self.assertEqual(result.evaluations[0].outcome, NOT_ESTABLISHED)
                self.assertIn('conflicts', ' '.join(result.evaluations[0].material_gaps))

    def test_missing_professional_scope_prevents_positive_conclusion(self):
        state = case(fact('stake', 'interest', 'Shareholding', object_id='supplier'),
                     fact('link', 'interest_connection', 'No', object_id='supplier'))
        state.facts = [f for f in state.facts if f.predicate != 'decision']
        self.assertEqual(reason_case(state).evaluations[0].outcome, NOT_ESTABLISHED)

    def test_user_review_and_claimed_implemented_action_do_not_supply_protective_facts(self):
        state = case(responsible(), fact('stake', 'interest', 'Bonus'),
                     fact('link', 'interest_connection', 'Yes'),
                     fact('confidence', 'assurance', 'I am entirely objective'))
        state.actions.append(CaseAction('claimed', 'A review happened', 'independent_review', 'Implemented'))
        before = reason_case(state).evaluations[0].outcome
        review_case(state)
        self.assertEqual(before, ACTION_REQUIRED)
        self.assertEqual(reason_case(state).evaluations[0].outcome, ACTION_REQUIRED)

    def test_denied_or_withdrawn_underlying_sources_are_not_retained_as_supported_threats(self):
        for status in ('denied', 'withdrawn', 'unknown', 'disputed'):
            state = case(fact('stake', 'interest', 'Shareholding', object_id='supplier', status=status),
                         fact('link', 'interest_connection', 'No', object_id='supplier'))
            self.assertFalse(reason_case(state).threats)

    def test_acceptable_source_does_not_remove_active_questions_for_other_threats(self):
        state = case(fact('stake', 'interest', 'Shareholding', object_id='supplier'),
                     fact('link', 'interest_connection', 'No', object_id='supplier'),
                     fact('pressure', 'pressure', 'CFO requested suppression', subject='cfo', object_id='user'))
        result = reason_case(state)
        acceptable = next(e.threat_id for e in result.evaluations if e.outcome == ACCEPTABLE)
        self.assertTrue(result.questions)
        self.assertTrue(all(acceptable not in question.threat_ids for question in result.questions))

    def test_reasoning_remains_pure_and_exposes_no_numerical_risk_score(self):
        state = case(fact('stake', 'interest', 'Shareholding', object_id='supplier'),
                     fact('link', 'interest_connection', 'No', object_id='supplier'))
        before = deepcopy(state)
        result = reason_case(state)
        self.assertEqual(state, before)
        self.assertTrue(all(isinstance(e.outcome, str) for e in result.evaluations))
        self.assertFalse(any('score' in key for e in result.evaluations for key in vars(e)))


if __name__ == '__main__':
    unittest.main()
