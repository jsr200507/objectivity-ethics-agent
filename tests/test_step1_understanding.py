"""Step 1 reuses explicit professional work without inventing its outcome."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from objectivity.ai_provider import AIConfig
from objectivity.ai_understanding import AIUnderstandingError, parse_ai_understanding
from objectivity.case_reasoning import reason_case
from objectivity.case_summary import summarise_case
from objectivity.case_workflow import review_case, start_case


ROLE = 'Senior financial analyst'
DECISION = ('Reviewing an external valuation of a commercial property before '
            'the year-end financial statements are finalised')
PRESSURE = ("The investment director has asked me to accept the valuation without further investigation "
            "because a lower valuation could affect the company's loan covenant.")
STRUCTURED = f'Role: {ROLE}\nDecision: {DECISION}.\nReported pressure: {PRESSURE}'
NARRATIVE = f'I am a {ROLE.lower()} {DECISION[0].lower() + DECISION[1:]}. {PRESSURE}'
APP = Path(__file__).resolve().parents[1] / 'app.py'


def facts(case, predicate):
    return [fact for fact in case.facts if fact.predicate == predicate]


class StepOneUnderstandingTests(unittest.TestCase):
    def test_structured_property_context_retains_literal_sources_and_role_ownership(self):
        case = start_case(STRUCTURED)
        self.assertEqual([f.value for f in facts(case, 'role')], [ROLE])
        self.assertEqual([f.value for f in facts(case, 'decision')], [DECISION])
        self.assertEqual(next(a.role for a in case.actors if a.id == 'user'), ROLE)
        self.assertFalse(any(a.id != 'user' and a.role.casefold() == ROLE.casefold() for a in case.actors))
        for fact in case.facts:
            self.assertIn(fact.excerpt, STRUCTURED)
            self.assertEqual(fact.source, 'scenario')
            self.assertFalse(fact.reviewed)
            self.assertNotEqual(fact.status, 'verified')

    def test_structured_and_narrative_work_close_only_established_questions(self):
        for source in (STRUCTURED, NARRATIVE):
            with self.subTest(source=source):
                case = start_case(source)
                self.assertEqual([f.value for f in facts(case, 'decision_responsibility')],
                                 ['I supervise or review the work'])
                review_case(case)
                self.assertEqual({q.predicate for q in reason_case(case).questions}, {'work_changed'})
                uncertainty = next(s for s in summarise_case(case) if s.title == 'Material uncertainties')
                text = ' '.join(uncertainty.items)
                self.assertNotIn('Your responsibility for the decision', text)
                self.assertNotIn('connection between the interest and this decision', text)
                self.assertIn('Whether work has already changed', text)

    def test_reusable_self_activity_grammars_classify_review_assessment_and_preparation(self):
        for activity, expected in (
            ('Reviewing', 'I supervise or review the work'),
            ('Supervising', 'I supervise or review the work'),
            ('Assessing', 'I prepare or assess the work'),
            ('Preparing', 'I prepare or assess the work'),
            ('Evaluating', 'I prepare or assess the work'),
            ('Recommending', 'I make or recommend the decision'),
        ):
            for source in (f'Decision: {activity} a pension estimate.',
                           f'I am a senior financial analyst {activity.lower()} a pension estimate.',
                           f'I am currently a senior financial analyst {activity.lower()} a pension estimate.'):
                with self.subTest(source=source):
                    self.assertEqual([f.value for f in facts(start_case(source), 'decision_responsibility')], [expected])

    def test_review_does_not_invent_final_approval_authority(self):
        case = start_case('Decision: Reviewing the reserve estimate; the director gives final approval.')
        self.assertEqual([f.value for f in facts(case, 'decision_responsibility')],
                         ['I supervise or review the work'])

    def test_third_party_requests_quotes_negation_and_hypotheticals_are_not_user_work(self):
        for source in (
            'The investment director is reviewing a valuation.',
            'The director asked me to accept the valuation.',
            'You are not reviewing the valuation.',
            'I am no longer reviewing the valuation.',
            'I might be reviewing the valuation next year.',
            'The director says, "I review the valuation."',
            'Decision: I might review the valuation.',
            'I am a consultant asked to review the valuation.',
            'I am a consultant interested in reviewing the valuation.',
        ):
            with self.subTest(source=source):
                self.assertFalse(facts(start_case(source), 'decision_responsibility'))

    def test_explicit_work_with_an_unfamiliar_job_title_does_not_need_a_title_dictionary(self):
        for source, expected in (
            ('You are a conservation grants assessor reviewing restoration proposals.', 'I supervise or review the work'),
            ('I am a marine resources coordinator assessing a habitat estimate.', 'I prepare or assess the work'),
            ('I am currently a materials compliance associate preparing a certificate.', 'I prepare or assess the work'),
            ('I need to review the estimate.', 'I supervise or review the work'),
            ('I have to prepare the reserve estimate.', 'I prepare or assess the work'),
        ):
            with self.subTest(source=source):
                self.assertEqual([f.value for f in facts(start_case(source), 'decision_responsibility')], [expected])

    def test_explicit_unknown_fields_remain_unknown_without_invented_involvement(self):
        case = start_case(f'Role: Unknown\nDecision: Unknown\n{PRESSURE}')
        self.assertEqual([(f.value, f.status) for f in facts(case, 'role')], [('Unknown', 'unknown')])
        self.assertEqual([(f.value, f.status) for f in facts(case, 'decision')], [('Unknown', 'unknown')])
        self.assertFalse(facts(case, 'decision_responsibility'))
        self.assertFalse(facts(case, 'interest_connection'))
        self.assertNotIn('decision', {q.predicate for q in reason_case(case).questions})

    def test_missing_responsibility_is_not_inferred_from_a_job_title(self):
        case = start_case('Role: Senior financial analyst\n' + PRESSURE)
        self.assertFalse(facts(case, 'decision_responsibility'))
        self.assertIn('decision_responsibility', {q.predicate for q in reason_case(case).questions})

    def test_organisation_financing_does_not_create_a_personal_interest(self):
        for source in (STRUCTURED, NARRATIVE):
            with self.subTest(source=source):
                case = start_case(source)
                self.assertEqual({f.subject for f in facts(case, 'interest')}, {'company'})
                self.assertEqual(next(a.kind for a in case.actors if a.id == 'company'), 'organisation')
                self.assertFalse(facts(case, 'family_relationship'))

    def test_conditional_connection_is_reported_possibility_not_an_established_consequence(self):
        case = start_case(STRUCTURED)
        connection, = facts(case, 'interest_connection')
        self.assertEqual((connection.subject, connection.object_id, connection.value, connection.status),
                         ('company', 'company', 'Yes', 'reported'))
        self.assertIn("a lower valuation could affect the company's loan covenant", connection.excerpt)
        self.assertFalse(connection.reviewed)
        self.assertFalse(facts(case, 'work_changed'))
        self.assertFalse(facts(case, 'prior_work_affected'))
        pressure, = facts(case, 'pressure')
        self.assertEqual(pressure.status, 'reported')
        self.assertIn('could affect', pressure.value)
        self.assertNotEqual(pressure.subject, 'user')
        review_case(case)
        self.assertEqual(connection.status, 'reported')
        self.assertTrue(connection.reviewed)
        self.assertEqual({q.predicate for q in reason_case(case).questions}, {'work_changed'})

    def test_reusable_financing_connection_is_bounded_to_the_current_work(self):
        for source in (
            "Decision: Assessing a collateral estimate.\nA lower estimate may jeopardise our organisation's financing.",
            "Decision: Preparing a reserve estimate.\nThe company's credit facility could be affected by the estimate.",
            "Decision: Reviewing a collateral estimate.\nThis decision might affect our organization's borrowing.",
        ):
            with self.subTest(source=source):
                case = start_case(source)
                connection, = facts(case, 'interest_connection')
                self.assertEqual((connection.value, connection.status), ('Yes', 'reported'))
                self.assertNotEqual(connection.subject, 'user')

    def test_explicit_uncertainty_and_denial_of_a_connection_are_preserved(self):
        for statement, expected, status in (
            ("It is unclear whether a lower valuation could affect the company's loan covenant.", 'Unknown', 'unknown'),
            ("A lower valuation does not affect the company's loan covenant.", 'No', 'reported'),
            ("The company's refinancing may depend on the valuation.", 'Unknown', 'unknown'),
        ):
            with self.subTest(statement=statement):
                case = start_case(f'Decision: Reviewing a property valuation.\n{statement}')
                connection, = facts(case, 'interest_connection')
                self.assertEqual((connection.value, connection.status), (expected, status))

    def test_unrelated_statements_do_not_manufacture_a_financing_link(self):
        for statement in (
            "The company's loan covenant is mentioned in another report.",
            "A lower valuation affects the accounts, but the company's loan covenant is unrelated to it.",
            "The director's mood could affect the company's loan covenant.",
        ):
            with self.subTest(statement=statement):
                case = start_case(f'Decision: Reviewing a property valuation.\n{statement}')
                self.assertFalse(any(f.value == 'Yes' for f in facts(case, 'interest_connection')))

    def test_understanding_and_summary_do_not_mutate_or_prematurely_review_the_case(self):
        case = start_case(STRUCTURED)
        before = deepcopy(case)
        summarise_case(case)
        reason_case(case)
        self.assertEqual(case, before)
        self.assertFalse(case.reviewed)
        self.assertFalse(case.answers)

    def test_optional_proposals_keep_supported_structured_roles_without_weakening_attribution(self):
        raw = {'actors': [{'label': 'user', 'role': ROLE, 'kind': 'professional', 'excerpt': f'Role: {ROLE}'}],
               'facts': [], 'actions': []}
        result = parse_ai_understanding(STRUCTURED, raw)
        self.assertEqual([f.value for f in facts(result, 'decision_responsibility')],
                         ['I supervise or review the work'])
        raw['actors'][0].update(role='investment director', excerpt=PRESSURE)
        with self.assertRaises(AIUnderstandingError):
            parse_ai_understanding(STRUCTURED, raw)


class StepOnePropertyAppTests(unittest.TestCase):
    def test_actual_confirmation_and_next_step_use_the_recorded_work_and_conditional_interest(self):
        with patch('objectivity.ai_ui.load_config', return_value=AIConfig()), \
             patch('objectivity.progress_ui.browser_storage', return_value=None):
            app = AppTest.from_file(str(APP), default_timeout=15).run()
            next(w for w in app.text_area if w.label == 'Your scenario').input(STRUCTURED)
            next(w for w in app.button if w.label == 'Review scenario').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['view'], 'identify')
            text = '\n'.join(item.value for kind in ('markdown', 'caption', 'text', 'warning', 'header')
                             for item in getattr(app, kind))
            self.assertIn('Step 1: Understand Your Scenario', text)
            self.assertIn(f'Role: {ROLE}', text)
            self.assertIn(f'Decision: {DECISION}', text)
            self.assertIn('could affect', text)
            self.assertNotIn('Your responsibility for the decision needs clarification', text)
            self.assertNotIn('The connection between the interest and this decision', text)
            next(w for w in app.checkbox if w.label == 'These records reflect my account, including uncertainties.').check()
            next(w for w in app.button if w.label == 'Confirm scenario and continue').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['view'], 'case_evaluate')
            case = app.session_state['assessment'].case_state
            self.assertTrue(case.reviewed)
            self.assertEqual({q.predicate for q in reason_case(case).questions}, {'work_changed'})
            self.assertEqual(len(app.radio), 1)


class FinancingDenialRegressionTests(unittest.TestCase):
    def case(self, statement):
        return start_case('I review a property valuation. ' + statement)

    def assert_unresolved(self, statement):
        case = self.case(statement)
        self.assertFalse(facts(case, 'interest_connection'))
        interest, = facts(case, 'interest')
        self.assertEqual((interest.subject, interest.status, interest.reviewed), ('company', 'reported', False))
        self.assertIn(interest.excerpt, case.scenario)
        self.assertIn(statement.rstrip('."\'”'), interest.excerpt)
        review_case(case)
        snapshot = reason_case(case)
        self.assertIn('interest_connection', {q.predicate for q in snapshot.questions})
        self.assertEqual({e.outcome for e in snapshot.evaluations}, {'Acceptability not established'})
        self.assertTrue(all(f.status == 'reported' for f in case.facts))

    def test_direct_affirmative_connections_are_still_reported(self):
        for statement in (
            "A lower valuation affects the company's loan covenant.",
            "A lower valuation could affect the company's loan covenant.",
            "The company's refinancing depends on the valuation.",
        ):
            with self.subTest(statement=statement):
                connection, = facts(self.case(statement), 'interest_connection')
                self.assertEqual((connection.value, connection.status, connection.reviewed), ('Yes', 'reported', False))

    def test_direct_negated_connections_do_not_become_affirmative(self):
        for statement in (
            "A lower valuation does not affect the company's loan covenant.",
            "A lower valuation cannot affect the company's loan covenant.",
            "A lower valuation could not affect the company's loan covenant.",
            "The company's refinancing does not depend on the valuation.",
        ):
            with self.subTest(statement=statement):
                connection, = facts(self.case(statement), 'interest_connection')
                self.assertEqual((connection.value, connection.status, connection.reviewed), ('No', 'reported', False))

    def test_third_party_denies_that_keeps_the_connection_question_and_qualified_evaluation(self):
        for statement in (
            "The investment director denies that a lower valuation could affect the company's loan covenant.",
            "The investment director denies that the company's refinancing depends on the valuation.",
        ):
            with self.subTest(statement=statement):
                self.assert_unresolved(statement)

    def test_quoted_denials_are_unverified_and_do_not_close_clarification(self):
        for statement in (
            'The investment director says, "A lower valuation could not affect the company\'s loan covenant."',
            "The investment director said, 'A lower valuation does not affect the company's loan covenant.'",
            'The investment director states, “The company\'s refinancing does not depend on the valuation.”',
            'The investment director says, "If the valuation were lower, the company\'s loan covenant would not be affected by it."',
        ):
            with self.subTest(statement=statement):
                self.assert_unresolved(statement)

    def test_conditional_negation_preserves_uncertainty_and_hypothetical_scope(self):
        for statement in (
            "A lower valuation may not affect the company's loan covenant.",
            "A lower valuation might not affect the company's loan covenant.",
        ):
            with self.subTest(statement=statement):
                connection, = facts(self.case(statement), 'interest_connection')
                self.assertEqual((connection.value, connection.status), ('Unknown', 'unknown'))
        hypothetical = self.case("If the valuation did not change, the company's refinancing would not depend on it.")
        self.assertFalse(facts(hypothetical, 'interest_connection'))
        absent = self.case("The company has no known refinancing that might depend on the valuation.")
        self.assertFalse(facts(absent, 'interest'))

    def test_unrelated_negation_does_not_suppress_an_explicit_positive_connection(self):
        for statement in (
            "The investment director says a valuation that is not corrected could affect the company's loan covenant.",
            "The investment director denies there was a delay, but says a lower valuation could affect the company's loan covenant.",
        ):
            with self.subTest(statement=statement):
                connection, = facts(self.case(statement), 'interest_connection')
                self.assertEqual((connection.value, connection.status), ('Yes', 'reported'))


class CompoundTitleRegressionTests(unittest.TestCase):
    def test_compound_titles_are_attributed_to_the_user_with_literal_evidence(self):
        for title in ('risk and compliance analyst', 'finance and operations manager', 'financial planning and analysis manager'):
            source = f'You are a {title}.'
            with self.subTest(title=title):
                case = start_case(source)
                role, = facts(case, 'role')
                self.assertEqual((role.subject, role.value.casefold(), role.status, role.reviewed), ('user', title, 'reported', False))
                self.assertIn(role.excerpt, source)
                self.assertEqual(next(a.role.casefold() for a in case.actors if a.id == 'user'), title)
                self.assertFalse(any(a.id != 'user' and 'analyst' in a.label.casefold() for a in case.actors))

    def test_compound_title_reviewing_is_reused_instead_of_reasked(self):
        case = start_case('You are a risk and compliance analyst reviewing a property valuation. Your annual bonus depends on the valuation.')
        self.assertEqual([f.value for f in facts(case, 'decision_responsibility')], ['I supervise or review the work'])
        self.assertNotIn('decision_responsibility', {q.predicate for q in reason_case(case).questions})

    def test_compound_title_assessing_and_preparing_responsibilities_are_explicit(self):
        for title, activity in (('risk and compliance analyst', 'assessing'), ('finance and operations manager', 'preparing')):
            with self.subTest(title=title, activity=activity):
                case = start_case(f'I am a {title} {activity} a reserve estimate.')
                self.assertEqual([f.value for f in facts(case, 'decision_responsibility')], ['I prepare or assess the work'])
                self.assertEqual([f.value.casefold() for f in facts(case, 'role')], [title])

    def test_compound_titles_alone_do_not_establish_responsibility_or_authority(self):
        for source in ('You are a risk and compliance analyst.', 'I am a finance and operations manager.', 'Role: Risk and compliance analyst'):
            with self.subTest(source=source):
                case = start_case(source + '\nYour annual bonus depends on the valuation.')
                self.assertTrue(facts(case, 'role'))
                self.assertFalse(facts(case, 'decision_responsibility'))
                self.assertIn('decision_responsibility', {q.predicate for q in reason_case(case).questions})

    def test_reviewing_and_approving_remain_different_recorded_activities(self):
        reviewer = start_case('I am a risk and compliance analyst reviewing the valuation; the director approves it.')
        approver = start_case('I am a risk and compliance analyst approving the valuation.')
        self.assertEqual([f.value for f in facts(reviewer, 'decision_responsibility')], ['I supervise or review the work'])
        self.assertEqual([f.value for f in facts(approver, 'decision_responsibility')], ['I make or recommend the decision'])

    def test_compound_title_support_does_not_loosen_other_attribution_guards(self):
        for source in (
            'You are a risk and compliance analyst, and the director is reviewing the valuation.',
            'The director says, "I am a risk and compliance analyst reviewing the valuation."',
            'You might be a risk and compliance analyst reviewing the valuation next year.',
            'You are a risk and compliance analyst not reviewing the valuation.',
        ):
            with self.subTest(source=source):
                self.assertFalse(facts(start_case(source), 'decision_responsibility'))


class MergeIntegrationRegressionTests(unittest.TestCase):
    def test_full_context_affirmative_financing_link_before_the_financing_noun_is_reused(self):
        case = start_case("I review a property valuation. This valuation is linked to the company's financing.")
        connection, = facts(case, 'interest_connection')
        self.assertEqual((connection.value, connection.status, connection.reviewed), ('Yes', 'reported', False))
        self.assertNotIn('interest_connection', {q.predicate for q in reason_case(case).questions})

    def test_contextual_direct_financing_negation_is_not_affirmed(self):
        case = start_case("I review a property valuation. This valuation is not linked to the company's financing.")
        connection, = facts(case, 'interest_connection')
        self.assertEqual((connection.value, connection.status, connection.reviewed), ('No', 'reported', False))

    def test_contextual_third_party_denial_keeps_its_question_and_qualified_evaluation(self):
        case = start_case("I review a property valuation. The investment director denies that this valuation is linked to the company's financing.")
        self.assertFalse(facts(case, 'interest_connection'))
        self.assertIn('denies that', facts(case, 'interest')[0].excerpt)
        review_case(case)
        snapshot = reason_case(case)
        self.assertIn('interest_connection', {q.predicate for q in snapshot.questions})
        self.assertEqual({e.outcome for e in snapshot.evaluations}, {'Acceptability not established'})

    def test_contextual_quoted_denial_cannot_be_reaffirmed_by_the_fallback(self):
        case = start_case('I review a property valuation. The investment director says, "This valuation is not linked to the company\'s financing."')
        self.assertFalse(facts(case, 'interest_connection'))
        self.assertIn('interest_connection', {q.predicate for q in reason_case(case).questions})
        self.assertTrue(all(f.status == 'reported' and not f.reviewed for f in case.facts))

    def test_conditional_financing_effect_keeps_its_literal_qualification(self):
        source = "I review a property valuation. A lower valuation could affect the company's loan covenant."
        case = start_case(source)
        connection, = facts(case, 'interest_connection')
        self.assertEqual((connection.value, connection.status, connection.reviewed), ('Yes', 'reported', False))
        self.assertIn('could affect', connection.excerpt)
        self.assertIn(connection.excerpt, source)
        self.assertFalse(facts(case, 'work_changed'))
        self.assertFalse(facts(case, 'prior_work_affected'))

    def test_compound_and_structured_roles_keep_new_explicit_responsibilities(self):
        for activity in ('reviewing', 'overseeing', 'checking', 'examining', 'auditing'):
            for source in (
                f'You are a risk and compliance analyst responsible for {activity} a property valuation.',
                f'Role: Risk and compliance analyst\nDecision: {activity.capitalize()} a property valuation.',
            ):
                with self.subTest(source=source):
                    case = start_case(source)
                    self.assertEqual([f.value.casefold() for f in facts(case, 'role')], ['risk and compliance analyst'])
                    self.assertEqual([f.value for f in facts(case, 'decision_responsibility')], ['I supervise or review the work'])

    def test_explicit_work_without_compound_titles_uses_the_unified_helper(self):
        for activity in ('reviewing', 'overseeing', 'checking', 'examining', 'auditing', 'assessing', 'preparing'):
            expected = 'I prepare or assess the work' if activity in {'assessing', 'preparing'} else 'I supervise or review the work'
            source = f'I am a financial accountant. I am responsible for {activity} a property valuation.'
            with self.subTest(activity=activity):
                self.assertEqual([f.value for f in facts(start_case(source), 'decision_responsibility')], [expected])

    def test_job_titles_still_do_not_establish_work_or_final_authority(self):
        for source in ('I am a financial accountant.', 'You are a risk and compliance analyst.'):
            with self.subTest(source=source):
                case = start_case(source + ' My annual bonus depends on the valuation.')
                self.assertFalse(facts(case, 'decision_responsibility'))
                self.assertIn('decision_responsibility', {q.predicate for q in reason_case(case).questions})

    def test_review_responsibility_does_not_take_the_directors_approval_authority(self):
        case = start_case('I am responsible for checking a property valuation; the director approves the final valuation.')
        self.assertEqual([f.value for f in facts(case, 'decision_responsibility')], ['I supervise or review the work'])

    def test_other_peoples_work_negation_and_quoted_first_person_remain_separate(self):
        for activity in ('checking', 'overseeing', 'examining', 'auditing'):
            for source in (
                f'The director is responsible for {activity} the valuation.',
                f'The director says, "I am responsible for {activity} the valuation."',
                f'I am not responsible for {activity} the valuation.',
                f'I might be responsible for {activity} the valuation.',
            ):
                with self.subTest(source=source):
                    self.assertFalse(facts(start_case(source), 'decision_responsibility'))


if __name__ == '__main__':
    unittest.main()
