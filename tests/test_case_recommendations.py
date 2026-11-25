"""Contextual response options must not become actions or residual evidence."""
from copy import deepcopy
from dataclasses import replace
import re
import unittest
from unittest.mock import patch

from objectivity.address import AddressState
from objectivity.case_actions import SUPPORTED, action_questions, assess_actions
from objectivity.case_model import CaseFact
from objectivity.case_reasoning import reason_case
from objectivity.case_report import build_case_report
from objectivity.case_workflow import edit_case_fact, review_case, start_case
from objectivity.models import Assessment
from objectivity.progress import export_progress, import_progress
from objectivity.review import ReviewState
from tests.test_authority_provider_context import SCENARIO
from tests.test_case_actions import action, full_review_checks, source_case
from tests.test_case_reasoning import case as reasoning_case, fact, responsible
from tests.test_step2_threat_flow import run_interview


def property_case(**answers):
    case = start_case(SCENARIO)
    run_interview(case, answers)
    review_case(case)
    return case


def steps(case):
    return ' '.join(assess_actions(case).next_steps)


class CaseRecommendationTests(unittest.TestCase):
    def test_property_recommendations_challenge_valuation_and_separate_financing(self):
        text = steps(property_case(financing_consequences='Possible covenant breach', work_changed='No'))
        self.assertIn("valuation's assumptions, methods and supporting evidence", text)
        self.assertIn('Separate the professional review and recommendation from financing or covenant negotiations', text)
        self.assertIn('Possible covenant breach', text)
        self.assertIn('not determine the professional judgment or be treated as a verified outcome', text)
        self.assertIn('Document professional disagreements, unresolved exceptions', text)

    def test_role_and_approval_limit_route_findings_without_inventing_powers(self):
        text = steps(property_case())
        self.assertIn('Risk and compliance analyst', text)
        self.assertIn('Submit findings and unresolved exceptions to an authorised decision-maker', text)
        self.assertIn('lack of final approval authority', text)
        self.assertNotIn('approve the valuation yourself', text)

    def test_third_party_authority_limits_do_not_become_users_limits(self):
        sample = property_case()
        note = next(f for f in sample.facts if f.predicate == 'context' and 'final approval' in f.value)
        director = next(f.subject for f in sample.facts if f.predicate == 'pressure')
        edit_case_fact(sample, note.id, note.value, subject=director)
        review_case(sample)
        self.assertNotIn('your reported lack of final approval authority', steps(sample))

    def test_uncertain_approval_limit_does_not_become_confirmed_restriction(self):
        for status in ('unknown', 'disputed', 'denied', 'withdrawn'):
            with self.subTest(status=status):
                sample = property_case()
                note = next(f for f in sample.facts if f.predicate == 'context' and 'final approval' in f.value)
                edit_case_fact(sample, note.id, note.value, status)
                review_case(sample)
                self.assertNotIn('your reported lack of final approval authority', steps(sample))

    def test_recommendation_authority_does_not_grant_approval(self):
        sample = source_case()
        sample.facts.append(fact('remit', 'context', 'I can only recommend changes.'))
        self.assertIn('Submit an evidence-based recommendation; final approval authority is not assumed', steps(sample))

    def test_preparer_works_through_authorised_person(self):
        sample = source_case()
        edit_case_fact(sample, 'responsibility', 'I prepare or assess the work')
        review_case(sample)
        self.assertIn('Prepare the analysis for an authorised decision-maker', steps(sample))

    def test_authority_and_changed_work_change_recommended_focus(self):
        strong = property_case(pressure_authority='Both work and career influence', work_changed='Yes',
                               work_change_details='Investigation or evidence gathering')
        safe = property_case(pressure_authority='No such authority or influence', work_changed='No',
                             challenge_safety='I can challenge or escalate without adverse consequences')
        strong_text, safe_text = steps(strong), steps(safe)
        self.assertIn('route controlled by investment director unsuitable', strong_text)
        self.assertIn('Independently reassess the reported affected work (Investigation or evidence gathering)', strong_text)
        self.assertIn('Use the reported safe challenge or escalation route', safe_text)
        self.assertIn('No work change is reported', safe_text)
        self.assertIn('possible future pressure', safe_text)
        self.assertNotIn('Independently reassess the reported affected work', safe_text)
        self.assertNotEqual(strong_text, safe_text)

    def test_no_known_route_offers_alternative_without_inventing_retaliation(self):
        text = steps(property_case(pressure_authority='No such authority or influence',
                                   challenge_safety='No practicable route is known'))
        self.assertIn('No practicable route is reported as known', text)
        self.assertIn('does not establish retaliation or that no route exists', text)
        self.assertIn('If none is available internally', text)
        self.assertIn('confidential professional advice externally', text)
        self.assertNotIn('audit committee', text)

    def test_unknown_resources_get_conditional_not_assumed_external_review(self):
        text = steps(source_case())
        self.assertIn('where accessible', text)
        self.assertIn('Consider competent external review where accessible', text)
        self.assertNotIn('audit committee', text)
        self.assertNotIn('independent department', text)

    def test_concern_without_consequence_does_not_become_retaliation(self):
        text = steps(property_case(challenge_safety='I am concerned but no consequence has been stated'))
        self.assertIn('Concern is reported without a stated adverse consequence; retaliation is not assumed', text)
        self.assertNotIn('Reported adverse consequences make', text)

    def test_unknown_or_disputed_safety_does_not_supply_safe_escalation_route(self):
        for status in ('unknown', 'disputed', 'denied', 'withdrawn'):
            with self.subTest(status=status):
                sample = property_case()
                sample.facts.append(CaseFact('safety-update', 'user', 'challenge_safety',
                    'I can challenge or escalate without adverse consequences',
                    object_id=next(f.subject for f in sample.facts if f.predicate == 'pressure'),
                    source='user', status=status, revision=100))
                self.assertNotIn('Use the reported safe challenge', steps(sample))

    def test_directors_reported_authority_does_not_grant_authority_to_user(self):
        text = steps(property_case(pressure_authority='Both work and career influence'))
        self.assertIn('route controlled by investment director unsuitable', text)
        self.assertIn('your reported lack of final approval authority', text)
        self.assertNotIn('your authority to override', text)

    def test_no_financing_consequence_keeps_organisational_interest(self):
        sample = property_case(financing_consequences='No financing consequence identified')
        text = steps(sample)
        self.assertIn('keep the response proportionate while retaining the recorded organisational interest', text)
        self.assertIn('financing or covenant negotiations', text)
        self.assertNotIn('your reported incentive (Organisational', text)
        self.assertNotEqual(text, steps(property_case(financing_consequences='Possible covenant breach')))

    def test_unknown_financing_effect_is_not_presented_as_a_stated_consequence(self):
        text = steps(property_case(financing_consequences='Unknown'))
        self.assertNotIn('The reported possibility (Unknown)', text)
        self.assertNotIn('covenant breach', text.lower())
        self.assertIn('financing or covenant negotiations', text)

    def test_personal_bonus_has_different_primary_response_from_financing(self):
        text = steps(source_case())
        self.assertIn('your reported incentive (Bonus linked to reported profit)', text)
        self.assertIn('remove or decouple your reported incentive', text)
        self.assertIn('Assess the inventory write-down', text)
        self.assertNotIn('covenant negotiations', text)

    def test_family_interest_does_not_assume_user_owns_relatives_assets(self):
        sample = reasoning_case(responsible(), fact('family', 'family_relationship', 'Sister', object_id='sister'),
            fact('shares', 'interest', 'Shareholding in Harbor Supplies', subject='sister', object_id='supplier'),
            fact('linked', 'interest_connection', 'Yes', subject='sister', object_id='supplier'))
        review_case(sample)
        text = steps(sample)
        self.assertIn('benefit belongs to Your sister', text)
        self.assertIn('your ownership or ability to dispose of it is not assumed', text)

    def test_commercial_dependence_requires_review_outside_same_income_pressure(self):
        sample = source_case()
        sample.facts = [f for f in sample.facts if f.predicate not in {'interest', 'interest_connection'}]
        sample.facts += [fact('fee', 'interest', 'Firm contract renewal/client retention', subject='firm'),
                         fact('fee-link', 'interest_connection', 'Yes', subject='firm'),
                         fact('dependence', 'commercial_dependence', 'A major source of income or business', subject='firm')]
        self.assertIn('same income pressure a weak alternative', steps(sample))
        self.assertIn('Use a reviewer outside that incentive', steps(sample))

    def test_familiarity_self_review_and_advocacy_have_distinct_primary_responses(self):
        sources = [
            fact('close', 'close_relationship', 'Close personal friendship', object_id='cfo'),
            fact('own', 'self_review', 'Reviewing my own earlier work'),
            fact('promoted', 'advocacy', 'Promoted a position now objectively assessed'),
        ]
        outputs = []
        for source, expected in zip(sources, ('outside the recorded relationship with CFO',
                                             'someone who did not prepare the earlier work',
                                             'Separate the promotional or representative role')):
            sample = reasoning_case(responsible(), source)
            review_case(sample)
            text = steps(sample)
            self.assertIn(expected, text)
            self.assertEqual(text.count('Primary:'), 1)
            self.assertEqual(text.count('Alternative:'), 1)
            self.assertEqual(text.count('Supporting:'), 1)
            outputs.append(text)
        self.assertEqual(len(set(outputs)), 3)

    def test_unfamiliar_decision_retains_scope_without_invented_valuation(self):
        sample = source_case()
        edit_case_fact(sample, 'decision', 'Assess grant proposals for a conservation programme')
        review_case(sample)
        text = steps(sample)
        self.assertIn('Assess grant proposals for a conservation programme', text)
        self.assertNotIn('valuation', text)

    def test_other_actor_and_other_decision_answers_do_not_supply_user_safety(self):
        sample = property_case()
        sample.facts += [fact('other-person', 'challenge_safety', 'I can challenge or escalate without adverse consequences',
                              subject='someone-else', object_id='investment_director'),
                         fact('other-decision', 'challenge_safety', 'I can challenge or escalate without adverse consequences',
                              object_id=next(f.subject for f in sample.facts if f.predicate == 'pressure'), decision_id='other')]
        self.assertNotIn('Use the reported safe challenge', steps(sample))

    def test_planned_safeguard_keeps_completion_requirement_without_new_questions(self):
        sample = source_case()
        action(sample, stage='Planned', checks={}, evidence='')
        result = assess_actions(sample)
        self.assertIn('Obtain completion', ' '.join(result.next_steps))
        self.assertIn('Primary:', ' '.join(result.next_steps))
        self.assertEqual(result.actions[0].status, 'Planned')
        self.assertFalse(result.actions[0].effective)
        self.assertFalse(action_questions(sample))

    def test_failed_safeguard_keeps_required_failure_response(self):
        sample = source_case()
        checks = full_review_checks(); checks['independence'] = 'No'
        action(sample, checks=checks)
        result = assess_actions(sample)
        self.assertIn('unsuccessful or inadequate', ' '.join(result.next_steps))
        self.assertTrue(result.actions[0].failed)

    def test_recommendations_do_not_mutate_actions_answers_or_evaluations(self):
        sample = property_case()
        before = deepcopy(sample)
        snapshot = reason_case(sample)
        result = assess_actions(sample)
        self.assertTrue(result.next_steps)
        self.assertEqual(sample, before)
        self.assertEqual(snapshot, reason_case(sample))
        self.assertFalse(sample.actions)
        self.assertFalse(result.actions)
        self.assertFalse(action_questions(sample))

    def test_recommendation_wording_cannot_change_residuals_or_evidence_questions(self):
        for stage in (None, 'Planned', 'Implemented'):
            with self.subTest(stage=stage):
                sample = property_case(work_changed='Yes')
                if stage:
                    action(sample, stage=stage, checks={}, evidence='')
                before = assess_actions(sample)
                questions = action_questions(sample)
                with patch('objectivity.case_actions._format_recommendation', return_value='Different wording only.'):
                    after = assess_actions(sample)
                self.assertEqual(replace(before, next_steps=()), replace(after, next_steps=()))
                self.assertEqual(questions, action_questions(sample))

    def test_effective_safeguards_and_existing_conditions_gain_no_extra_requirements(self):
        sample = source_case(); action(sample)
        result = assess_actions(sample)
        self.assertTrue(all(o.status == SUPPORTED for o in result.outcomes))
        self.assertFalse(result.next_steps)
        unrelated = source_case()
        edit_case_fact(unrelated, 'connection', 'No'); review_case(unrelated)
        self.assertNotIn('Primary:', steps(unrelated))
        self.assertIn('no additional safeguard is currently indicated', steps(unrelated))

    def test_json_restoration_recomputes_recommendations_without_creating_actions(self):
        sample = property_case(financing_consequences='Possible covenant breach')
        action(sample, stage='Planned', checks={}, evidence='')
        encoded = export_progress(Assessment(scenario=sample.scenario, case_state=sample), ReviewState(), AddressState(), 'case_address')
        restored = import_progress(encoded).assessment.case_state
        self.assertEqual(restored, sample)
        self.assertEqual(steps(restored), steps(sample))
        self.assertEqual(restored.actions[0].stage, 'Planned')
        self.assertEqual(len(restored.actions), 1)

    def test_edited_step2_answer_updates_recommendations(self):
        sample = property_case(financing_consequences='Possible covenant breach')
        before = steps(sample)
        consequence = next(f for f in sample.facts if f.predicate == 'financing_consequences')
        edit_case_fact(sample, consequence.id, 'No financing consequence identified')
        review_case(sample)
        after = steps(sample)
        self.assertIn('Possible covenant breach', before)
        self.assertNotIn('Possible covenant breach', after)
        self.assertIn('keep the response proportionate', after)
        self.assertTrue(sample.fact_history)

    def test_report_places_case_specific_safeguards_before_action_history_follow_up(self):
        sample = property_case()
        report = build_case_report(sample)
        primary = report.index("**Primary safeguard:**")
        history = report.index("Establish what has already been done or planned")
        self.assertLess(primary, history)
        self.assertIn("**Alternative safeguard:**", report)
        self.assertIn("**Supporting actions and evidence:**", report)

    def test_report_structure_and_proposed_implemented_distinction_remain_intact(self):
        sample = property_case()
        before = deepcopy(sample)
        report = build_case_report(sample)
        self.assertEqual(re.findall(r'^## ([1-3])\. ', report, re.MULTILINE), list('123'))
        self.assertIn('Primary safeguard:', report)
        self.assertIn('recommendations, not completed safeguards', report)
        self.assertNotIn('**Recorded stage:** Implemented', report)
        self.assertEqual(sample, before)

    def test_typed_recommendations_and_procedural_follow_ups_are_separate(self):
        sample = property_case()
        before = deepcopy(sample)
        result = assess_actions(sample)
        self.assertEqual({r.threat_id for r in result.recommendations},
                         {t.id for t in reason_case(sample).threats})
        self.assertEqual(len(result.recommendations), 2)
        for recommendation in result.recommendations:
            self.assertTrue(recommendation.primary and recommendation.alternative and recommendation.supporting)
            self.assertTrue(recommendation.considerations)
        self.assertTrue(result.follow_up_steps)
        self.assertIn('Establish what has already been done', result.follow_up_steps[0])
        self.assertEqual(sample, before)
        self.assertFalse(sample.actions)

    def test_report_does_not_classify_compatibility_recommendation_strings(self):
        sample = property_case()
        with patch('objectivity.case_actions._format_recommendation', return_value='Opaque compatibility output'):
            report = build_case_report(sample)
        section = report.split('## 1. Executive Summary')[1]
        self.assertNotIn('Opaque compatibility output', section)
        self.assertEqual(section.count('**Primary safeguard:**'), 2)
        self.assertIn('Establish what has already been done', section)

    def test_report_renders_typed_recommendations_without_legacy_next_steps(self):
        sample = property_case()
        result = assess_actions(sample)
        with patch('objectivity.case_report.assess_actions', return_value=replace(result, next_steps=())):
            report = build_case_report(sample)
        section = report.split('## 1. Executive Summary')[1]
        self.assertEqual(section.count('**Primary safeguard:**'), len(result.recommendations))
        self.assertIn('Establish what has already been done', section)

    def test_primary_label_in_user_context_cannot_hide_a_non_safeguard_follow_up(self):
        sample = source_case(fact('pressure', 'pressure', 'Requested a favourable judgment',
                                  subject='cfo', object_id='user'),
                             fact('changed', 'work_changed', 'No', object_id='cfo'))
        edit_case_fact(sample, 'decision', 'Review the Primary: inventory estimate')
        edit_case_fact(sample, 'connection', 'No')
        review_case(sample)
        result = assess_actions(sample)
        self.assertTrue(result.recommendations)
        self.assertTrue(any('Primary: ' in step for step in result.follow_up_steps))
        section = build_case_report(sample).split('## 3. Overall Conclusion')[1]
        self.assertIn('retain the recorded conditions supporting acceptability', section)
        self.assertIn('Primary:', section)

    def test_missing_extra_context_has_a_source_specific_qualified_consideration(self):
        sample = source_case()
        sample.facts = [f for f in sample.facts if f.predicate != 'role']
        before = deepcopy(sample)
        recommendation = assess_actions(sample).recommendations[0]
        self.assertFalse(recommendation.remit or recommendation.context)
        self.assertIn('Assess the inventory write-down', recommendation.considerations[0])
        self.assertIn('must not be assumed', recommendation.considerations[0])
        self.assertEqual(sample, before)


if __name__ == '__main__':
    unittest.main()
