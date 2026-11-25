"""Presentation must preserve the current assessment and its evidence boundaries."""
from copy import deepcopy
import re
import unittest
from unittest.mock import patch

from objectivity.case_actions import SUPPORTED, assess_actions
from objectivity.case_model import CaseAction, CaseFact
from objectivity.case_preliminary import preliminary_assessment
from objectivity.case_presentation import status_summary, threat_overview
from objectivity.case_questions import plan_questions
from objectivity.case_reasoning import reason_case
from objectivity.case_report import _escaped, build_case_report
from objectivity.case_workflow import edit_case_fact, review_case, start_case
from tests.test_authority_provider_context import SCENARIO
from tests.test_case_actions import action, full_review_checks, source_case
from tests.test_case_recommendations import property_case
from tests.test_property_comparison import PROPERTY_COMPARISON
from tests.test_step2_threat_flow import run_interview


def threat_blocks(report):
    body = report.split('## 2. Threat-by-Threat Assessment', 1)[1].split('## 3. Overall Conclusion', 1)[0]
    return re.split(r'(?m)^### THREAT ', body)[1:]


class StructuredProfessionalReportTests(unittest.TestCase):
    def test_both_valuation_fixtures_have_three_sections_and_one_stage_sequence_per_threat(self):
        for narrative in (SCENARIO, PROPERTY_COMPARISON):
            with self.subTest(narrative=narrative):
                case = start_case(narrative)
                run_interview(case)
                review_case(case)
                report = build_case_report(case)
                self.assertEqual(re.findall(r'^## (.*)$', report, re.M), [
                    '1. Executive Summary', '2. Threat-by-Threat Assessment', '3. Overall Conclusion'])
                blocks = threat_blocks(report)
                self.assertEqual(len(blocks), len(reason_case(case).threats))
                for block in blocks:
                    self.assertEqual(re.findall(r'^#### (.*)$', block, re.M), ['A. IDENTIFY', 'B. EVALUATE', 'C. ADDRESS'])
                    self.assertIn('**Residual position:**', block)
                self.assertNotIn('Addressing Threats', report)
                executive = report.split('## 1. Executive Summary')[1].split('## 2.')[0]
                self.assertIn('**Principal concerns:**', executive)
                self.assertLessEqual(len(executive.split()), 170)

    def test_each_address_uses_its_own_typed_recommendation_exactly_once(self):
        case = property_case()
        result = assess_actions(case)
        report = build_case_report(case)
        blocks = threat_blocks(report)
        for index, threat in enumerate(reason_case(case).threats):
            recommendation = next(r for r in result.recommendations if r.threat_id == threat.id)
            address = blocks[index].split('#### C. ADDRESS')[1]
            for text in (recommendation.primary, *recommendation.application,
                         recommendation.alternative, *recommendation.supporting_actions):
                self.assertEqual(address.count(_escaped(text)), 1)
            other = next(r for r in result.recommendations if r.threat_id != threat.id)
            self.assertNotIn(_escaped(other.primary), address)

    def test_application_and_evidence_are_explicit_bounded_bullets(self):
        cases = [property_case(), source_case()]
        cedar = start_case(PROPERTY_COMPARISON)
        run_interview(cedar); review_case(cedar); cases.append(cedar)
        for case in cases:
            for recommendation in assess_actions(case).recommendations:
                with self.subTest(threat=recommendation.threat_id):
                    self.assertIsInstance(recommendation.application, tuple)
                    self.assertIsInstance(recommendation.supporting_actions, tuple)
                    self.assertTrue(1 <= len(recommendation.application) <= 3)
                    self.assertTrue(2 <= len(recommendation.supporting_actions) <= 4)
                    self.assertLessEqual(len(recommendation.primary.split()), 65)
                    self.assertLessEqual(len(recommendation.alternative.split()), 55)

    def test_engine_conclusion_is_preserved_in_full_without_a_new_clearance(self):
        for case in (source_case(), property_case()):
            result = assess_actions(case)
            report = build_case_report(case)
            conclusion = report.split('## 3. Overall Conclusion')[1]
            self.assertIn(_escaped(result.conclusion), conclusion)
            self.assertNotIn('You may proceed unconditionally', report)

    def test_preliminary_significance_and_reasoning_match_step2(self):
        case = property_case(pressure_authority='Both work and career influence',
                             challenge_safety='No practicable route is known', work_changed='No')
        snapshot = reason_case(case)
        plan = plan_questions(case, snapshot)
        for block, threat in zip(threat_blocks(build_case_report(case)), snapshot.threats):
            initial = preliminary_assessment(case, snapshot, threat, plan)
            evaluate = block.split('#### B. EVALUATE')[1].split('#### C. ADDRESS')[0]
            self.assertIn(_escaped(initial.significance), evaluate)
            for reason in (*initial.factors, *initial.gaps):
                self.assertIn(_escaped(reason), evaluate)
            self.assertNotIn('at an acceptable level', evaluate.lower())

    def test_unknown_and_its_explanation_remain_qualified_in_the_correct_threat(self):
        case = start_case(SCENARIO)
        from objectivity.case_workflow import answer_case_question
        question = plan_questions(case).questions[0]
        explanation = 'The covenant terms have not been checked; no breach is established.'
        answer_case_question(case, question.id, 'Unknown', explanation)
        review_case(case)
        report = build_case_report(case)
        first = threat_blocks(report)[0]
        self.assertIn(_escaped(explanation), first)
        self.assertIn('remains unknown', first)
        self.assertEqual(case.answers[question.id].choice, 'Unknown')
        self.assertNotIn('**Recorded stage:** Implemented', first)

    def test_shared_planned_action_keeps_each_threats_status_but_quotes_its_records_once(self):
        case = property_case()
        case.actions = [CaseAction('planned', 'Request independent valuation review', 'independent_review', 'Planned',
            threat_ids=tuple(t.id for t in reason_case(case).threats),
            evidence_detail='A fictional review request is awaiting acceptance.', reviewed=True)]
        before = deepcopy(case)
        report = build_case_report(case)
        blocks = threat_blocks(report)
        self.assertEqual(report.count('A fictional review request is awaiting acceptance'), 1)
        for block in blocks:
            self.assertIn('**Recorded stage:** Planned', block)
            self.assertIn('completed implementation and effectiveness are not established', block)
        self.assertIn('Source and implementation evidence: see Threat 01', blocks[1])
        self.assertNotIn('**Recorded stage:** Implemented', report)
        self.assertEqual(case, before)

    def test_effective_action_and_its_conditional_conclusion_come_only_from_the_engine(self):
        case = source_case()
        action(case)
        result = assess_actions(case)
        self.assertTrue(all(a.effective for a in result.actions))
        report = build_case_report(case)
        self.assertIn('Effectiveness Established', report)
        self.assertIn(_escaped(result.conclusion), report.split('## 3. Overall Conclusion')[1])
        self.assertNotIn('**Primary safeguard:**', report)
        self.assertEqual(result.outcomes[0].status, SUPPORTED)

    def test_partial_review_does_not_gain_effectiveness_from_the_presentation(self):
        case = source_case()
        action(case, checks={**full_review_checks(), 'coverage': 'Partial'})
        before = deepcopy(case)
        result = assess_actions(case)
        self.assertFalse(result.actions[0].effective)
        report = build_case_report(case)
        self.assertIn('Implemented \\(reported\\)', report)
        self.assertIn('No recorded action is assessed as effective', report)
        self.assertNotIn('**Effectiveness assessment:** Effectiveness Established', report)
        self.assertEqual(case, before)

    def test_revised_facts_recalculate_recommendations_and_do_not_reuse_a_prior_report(self):
        case = property_case()
        before = build_case_report(case)
        fact = next(f for f in case.facts if f.predicate == 'interest_connection')
        edit_case_fact(case, fact.id, 'No'); review_case(case)
        after = build_case_report(case)
        first = threat_blocks(after)[0]
        self.assertNotEqual(before, after)
        self.assertIn('Recorded circumstances narrow this potential threat', first)
        self.assertNotIn('**Primary safeguard:**', first)
        self.assertTrue(case.fact_history)

    def test_compatibility_text_is_never_parsed_to_build_cards_or_report(self):
        case = property_case()
        with patch('objectivity.case_actions._format_recommendation', return_value='Primary: INVALID LEGACY PROJECTION'):
            report = build_case_report(case)
        self.assertNotIn('INVALID LEGACY PROJECTION', report)
        self.assertEqual(report.count('**Primary safeguard:**'), 2)

    def test_authority_and_provider_precision_are_retained(self):
        original = build_case_report(property_case())
        self.assertIn('I do not have final approval authority', original)
        self.assertNotIn('Cedar Valuations', original)
        cedar = start_case(PROPERTY_COMPARISON)
        run_interview(cedar); review_case(cedar)
        report = build_case_report(cedar)
        self.assertIn('Cedar Valuations', report)
        self.assertIn('brother', report.lower())
        self.assertIn('remains unknown', report)

    def test_summary_counts_findings_without_replacing_the_ethical_conclusion(self):
        case = property_case()
        result = assess_actions(case)
        self.assertIn('2 of 2 threats need further action or evidence', status_summary(result))
        before = deepcopy(case)
        for threat in reason_case(case).threats:
            problem, why = threat_overview(case, threat)
            self.assertTrue(problem and why)
            self.assertNotEqual(problem, why)
            self.assertNotIn('proven', problem)
        self.assertEqual(case, before)

    def test_empty_case_retains_limits_without_a_forced_safeguard(self):
        report = build_case_report(start_case('There is a professional concern.'))
        self.assertIn('not assurance that threats are absent', report)
        self.assertNotIn('### THREAT ', report)
        self.assertNotIn('**Primary safeguard:**', report)
        self.assertIn('activity has not been established', report)

    def test_organisational_interest_does_not_deny_a_separately_recorded_personal_benefit(self):
        case = property_case(financing_consequences='Unknown')
        case.facts += [CaseFact('own-bonus', 'user', 'interest', 'Annual bonus linked to valuation', source='user', reviewed=True),
                       CaseFact('bonus-link', 'user', 'interest_connection', 'Yes', source='user', reviewed=True)]
        result = assess_actions(case)
        organisational = next(r for r in result.recommendations if 'covenant negotiations' in r.primary)
        personal = next(r for r in result.recommendations if 'Annual bonus linked to valuation' in r.primary)
        self.assertIn('organisational interest alone does not establish', ' '.join(organisational.application))
        report = build_case_report(case)
        self.assertIn(_escaped(personal.primary), report)
        self.assertIn('Annual bonus linked to valuation', report)
        self.assertEqual(len(reason_case(case).threats), 3)

    def test_shared_literal_evidence_retains_all_parties_without_repeating_the_quote(self):
        case = start_case(PROPERTY_COMPARISON)
        run_interview(case); review_case(case)
        report = build_case_report(case)
        family = next(block for block in threat_blocks(report) if '— Familiarity' in block.splitlines()[0])
        self.assertEqual(family.count('> Your brother works for Cedar Valuations\\.'), 1)
        self.assertIn('Concerning You; Your brother', family)
        self.assertIn('Explicitly unknown in the recorded account', family)
        self.assertIn('You do not know whether he participated', family)
        self.assertEqual(report.count('> Your promotion depends on approving the valuation\\.'), 1)
        self.assertEqual(report.count("> Our company's refinancing depends on meeting a loan covenant based on the property value\\."), 1)

    def test_shared_excerpt_does_not_collapse_distinct_evidence_statuses(self):
        case = start_case(PROPERTY_COMPARISON)
        employment = next(f for f in case.facts if f.predicate == 'employment')
        participation = next(f for f in case.facts if f.predicate == 'participation')
        # A reused source must not cause its separate Unknown record to vanish.
        participation.excerpt = employment.excerpt
        review_case(case)
        family = next(block for block in threat_blocks(build_case_report(case)) if '— Familiarity' in block.splitlines()[0])
        self.assertEqual(family.count('> Your brother works for Cedar Valuations\\.'), 2)
        self.assertIn('not independently verified', family)
        self.assertIn('Explicitly unknown in the recorded account', family)

    def test_action_gap_is_not_repeated_as_an_identical_outstanding_concern(self):
        case = property_case()
        case.actions = [CaseAction('planned', 'Request independent review', 'independent_review', 'Planned',
            threat_ids=tuple(t.id for t in reason_case(case).threats), reviewed=True)]
        result = assess_actions(case)
        for block, residual in zip(threat_blocks(build_case_report(case)), result.outcomes):
            for gap in result.actions[0].gaps:
                self.assertEqual(block.count(_escaped(gap)), 1)
            for gap in residual.unknowns:
                self.assertIn(_escaped(gap), block)

    def test_case_application_omits_role_only_filler_without_losing_recorded_role(self):
        case = property_case()
        before = deepcopy(case)
        result = assess_actions(case)
        for recommendation in result.recommendations:
            self.assertTrue(recommendation.application)
            self.assertNotIn('Apply the response within your recorded role', ' '.join(recommendation.application))
        self.assertIn('Risk and compliance analyst', build_case_report(case))
        self.assertEqual(case, before)

    def test_shared_text_preserves_a_distinct_reported_attribution(self):
        case = start_case(PROPERTY_COMPARISON)
        interest = next(f for f in case.facts if f.predicate == 'interest' and f.subject == 'user')
        interest.attribution = 'investment director'
        review_case(case)
        block = threat_blocks(build_case_report(case))[0]
        self.assertEqual(block.count('> Your promotion depends on approving the valuation\\.'), 2)
        self.assertIn('attributed in the account to investment director', block)
        self.assertIn('not independently verified', block)

    def test_changed_work_caution_is_complete_without_repeating_equivalent_cautions(self):
        case = property_case(pressure_authority='Both work and career influence', work_changed='Yes',
                             work_change_details='Investigation or evidence gathering')
        snapshot = reason_case(case)
        threat = next(t for t in snapshot.threats if t.kind == 'Intimidation')
        initial = preliminary_assessment(case, snapshot, threat)
        block = next(b for b in threat_blocks(build_case_report(case)) if '— Intimidation' in b.splitlines()[0])
        evaluate = block.split('#### B. EVALUATE')[1].split('#### C. ADDRESS')[0]
        self.assertIn(_escaped(initial.significance), evaluate)
        self.assertIn('A reported change to work indicates potentially heightened influence', evaluate)
        self.assertIn('it does not establish technical error or misconduct', evaluate)
        self.assertIn('Investigation or evidence gathering', evaluate)
        self.assertNotIn('The reported change identifies work needing attention', evaluate)
        self.assertNotIn('A change to work is reported', evaluate)

    def test_scope_caveats_are_not_duplicated_as_case_specific_unknowns(self):
        report = build_case_report(property_case(financing_consequences='Unknown'))
        remaining = report.split('**Other uncertainties and limitations:**')[1].split('**Scope:**')[0]
        self.assertIn('Possible financing or loan covenant consequences remains unknown', remaining)
        self.assertNotIn('No facts or documents have been independently verified', remaining)
        self.assertNotIn('does not certify compliance', remaining)
        self.assertIn('It does not certify compliance', report.split('**Scope:**')[1])
        self.assertIn('no independent fact verification', report.split('**Scope:**')[1])


if __name__ == '__main__':
    unittest.main()
