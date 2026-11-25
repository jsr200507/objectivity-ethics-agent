"""Threat-grouped interview, bounded gaps and preliminary/residual separation."""
from copy import deepcopy
from dataclasses import asdict
import re
import unittest
from unittest.mock import patch

from objectivity.address import AddressState
from objectivity.ai_understanding import AIUnderstandingError, parse_ai_understanding
from objectivity.case_actions import assess_actions
from objectivity.case_codec import case_from_dict, case_to_dict
from objectivity.case_model import CaseActor, CaseFact, CaseState, MaterialQuestion
from objectivity.case_preliminary import preliminary_assessment
from objectivity.case_questions import MAX_STEP2_QUESTIONS, plan_questions
from objectivity.case_reasoning import reason_case
from objectivity.case_report import build_case_report
from objectivity.case_workflow import (
    add_case_fact, answer_case_question, edit_case_fact, review_case, start_case,
)
from objectivity.models import Assessment
from objectivity.progress import export_progress, import_progress
from objectivity.review import ReviewState
from tests.test_ai_understanding import fact as ai_fact, proposal
from tests.test_authority_provider_context import SCENARIO
from tests.test_case_actions import action, source_case
from tests import test_case_ui as ui_helpers

PROPERTY_EMPLOYMENT = ui_helpers.PROPERTY_EMPLOYMENT


def run_interview(case, choices=None):
    seen = []
    choices = choices or {}
    for _ in range(15):
        questions = plan_questions(case).questions
        if not questions:
            return seen
        q = questions[0]
        if q.id in [item.id for item in seen]:
            raise AssertionError('An unchanged answered question was repeated.')
        seen.append(q)
        answer_case_question(case, q.id, choices.get(q.predicate, 'Unknown'))
    raise AssertionError('Question planning failed to terminate.')


def crowded_case():
    actors = [CaseActor('user', 'You', 'Accountant')]
    facts = [CaseFact('decision', 'user', 'decision', 'Assess supplier bids', source='user'),
             CaseFact('role', 'user', 'decision_responsibility', 'I prepare or assess the work', source='user')]
    for i in range(9):
        who = f'beneficiary-{i}'
        actors.append(CaseActor(who, f'Supplier {i}', kind='organisation'))
        facts.append(CaseFact(f'interest-{i}', who, 'interest', 'Contingent fee', who, source='user'))
    return CaseState('Several reported supplier incentives.', actors=actors, facts=facts)


class Step2QuestionTests(unittest.TestCase):
    def test_old_material_question_constructors_default_to_identify(self):
        q = MaterialQuestion('q', 'Question?', ('Unknown',), 'Why', 'Impact', 'decision')
        self.assertEqual(q.phase, 'identify')

    def test_existing_questions_have_explicit_correct_phases(self):
        case = start_case(SCENARIO)
        self.assertEqual(reason_case(case).questions[0].phase, 'evaluate')
        other = start_case('My sister works for Cedar Valuations. I review a valuation prepared by Cedar Valuations.')
        self.assertTrue(all(q.phase == 'identify' for q in reason_case(other).questions))

    def test_property_interview_has_four_meaningful_questions_without_changed_work(self):
        case = start_case(SCENARIO)
        seen = run_interview(case, {'work_changed': 'No'})
        self.assertEqual([q.predicate for q in seen], ['financing_consequences', 'pressure_authority', 'challenge_safety', 'work_changed'])
        self.assertEqual([q.phase for q in seen], ['evaluate', 'identify', 'evaluate', 'evaluate'])
        self.assertTrue(all(q.why and q.impact and q.threat_ids for q in seen))

    def test_identify_precedes_evaluate_within_each_threat(self):
        case = start_case(SCENARIO)
        connection = next(f for f in case.facts if f.predicate == 'interest_connection')
        edit_case_fact(case, connection.id, connection.value, 'withdrawn')
        plan = plan_questions(case)
        self.assertEqual([q.predicate for q in plan.questions], ['interest_connection', 'financing_consequences', 'pressure_authority', 'challenge_safety', 'work_changed'])
        self.assertEqual([q.phase for q in plan.questions[:2]], ['identify', 'evaluate'])

    def test_recorded_role_responsibility_and_financing_link_are_reused(self):
        predicates = {q.predicate for q in plan_questions(start_case(SCENARIO)).questions}
        self.assertFalse(predicates & {'role', 'decision', 'decision_responsibility', 'interest_connection'})

    def test_authority_is_not_inferred_from_directors_title_or_users_approval_limit(self):
        case = start_case(SCENARIO)
        self.assertFalse(any(f.predicate == 'pressure_authority' for f in case.facts))
        self.assertIn('pressure_authority', {q.predicate for q in plan_questions(case).questions})

    def test_authority_and_ability_to_challenge_are_distinct_scoped_answers(self):
        case = start_case(SCENARIO)
        authority = next(q for q in plan_questions(case).questions if q.predicate == 'pressure_authority')
        answer_case_question(case, authority.id, 'No such authority or influence')
        challenge = next(q for q in plan_questions(case).questions if q.predicate == 'challenge_safety')
        self.assertEqual((challenge.subject, challenge.object_id), ('user', authority.subject))
        self.assertIn('not evidence', challenge.impact)

    def test_yes_changed_work_triggers_only_the_relevant_details_question(self):
        case = start_case(SCENARIO)
        seen = run_interview(case, {'work_changed': 'Yes', 'work_change_details': 'Investigation or evidence gathering'})
        self.assertEqual(len(seen), 5)
        self.assertEqual(seen[-1].predicate, 'work_change_details')
        self.assertEqual(seen[-1].phase, 'evaluate')
        self.assertIn('does not prove', seen[-1].impact)

    def test_no_or_unknown_changed_work_does_not_force_details(self):
        for answer in ('No', 'Unknown'):
            with self.subTest(answer=answer):
                seen = run_interview(start_case(SCENARIO), {'work_changed': answer})
                self.assertNotIn('work_change_details', [q.predicate for q in seen])

    def test_unknowns_do_not_repeat_or_imply_resolution(self):
        case = start_case(SCENARIO)
        seen = run_interview(case)
        self.assertEqual(len(seen), 4)
        self.assertFalse(plan_questions(case).questions)
        snapshot = reason_case(case)
        gaps = ' '.join(g for t in snapshot.threats for g in preliminary_assessment(case, snapshot, t).gaps)
        self.assertIn('remains unknown', gaps)

    def test_structured_information_already_recorded_skips_new_questions(self):
        case = start_case(SCENARIO)
        questions = list(plan_questions(case).questions)
        for q in questions:
            add_case_fact(case, q.subject, q.predicate, 'Unknown', q.object_id, 'unknown', q.decision_id)
        self.assertFalse(plan_questions(case).questions)
        self.assertFalse(case.answers)

    def test_financing_questions_are_not_forced_into_bonus_or_family_cases(self):
        for text in ('I assess inventory. My bonus depends on profit.', PROPERTY_EMPLOYMENT):
            with self.subTest(text=text):
                predicates = {q.predicate for q in plan_questions(start_case(text)).questions}
                self.assertNotIn('financing_consequences', predicates)
                self.assertNotIn('pressure_authority', predicates)
                self.assertNotIn('challenge_safety', predicates)

    def test_other_professional_financing_decision_does_not_invent_property_valuation(self):
        case = start_case(SCENARIO)
        decision = next(f for f in case.facts if f.predicate == 'decision')
        edit_case_fact(case, decision.id, 'Assess a funding application')
        q = next(q for q in plan_questions(case).questions if q.predicate == 'financing_consequences')
        self.assertNotIn('valuation', q.prompt)

    def test_unrelated_interest_narrows_branch_without_forced_evaluation_questions(self):
        case = start_case(SCENARIO)
        q = next(f for f in case.facts if f.predicate == 'interest_connection')
        edit_case_fact(case, q.id, 'No')
        self.assertNotIn('financing_consequences', {q.predicate for q in plan_questions(case).questions})

    def test_separate_pressure_sources_are_not_assigned_one_anothers_answers(self):
        case = start_case(SCENARIO)
        case.actors.append(CaseActor('other', 'Chief executive'))
        add_case_fact(case, 'other', 'pressure', 'Requested suppression of findings', 'user')
        q = next(q for q in plan_questions(case).questions if q.predicate == 'pressure_authority')
        answer_case_question(case, q.id, 'Unknown')
        other = [q for q in plan_questions(case).questions if q.predicate == 'pressure_authority']
        self.assertEqual(len(other), 1)
        self.assertNotEqual(other[0].subject, q.subject)

    def test_same_actor_multiple_requests_share_questions_and_all_dependencies(self):
        case = start_case(SCENARIO)
        person = next(f.subject for f in case.facts if f.predicate == 'pressure')
        second = add_case_fact(case, person, 'pressure', 'Do not tell the auditors', 'user')
        qs = [q for q in plan_questions(case).questions if q.predicate == 'pressure_authority']
        self.assertEqual(len(qs), 1)
        self.assertEqual(len(qs[0].threat_ids), 2)
        self.assertIn(second.id, qs[0].depends_on)

    def test_seven_question_limit_is_global_and_deferred_gaps_remain_visible(self):
        case = crowded_case()
        seen = run_interview(case)
        self.assertEqual(len(seen), MAX_STEP2_QUESTIONS)
        plan = plan_questions(case)
        self.assertTrue(plan.limit_reached)
        self.assertEqual(len(plan.deferred), 2)
        self.assertTrue(reason_case(case).questions)
        report = build_case_report(case)
        self.assertIn('Question limit leaves unresolved', report)
        self.assertIn('Step 2 question limit leaves unresolved', report.split('## 3. Overall Conclusion')[1])

    def test_deferred_question_cannot_be_answered_beyond_budget(self):
        case = crowded_case()
        blocked = plan_questions(case).deferred[0]
        run_interview(case)
        with self.assertRaises(ValueError):
            answer_case_question(case, blocked.id, 'Unknown')

    def test_editing_does_not_reset_budget_but_same_question_can_be_reconsidered(self):
        case = crowded_case()
        seen = run_interview(case)
        first_answer = case.answers[seen[0].id]
        source = next(f for f in case.facts if f.id in first_answer.depends_on and f.predicate == 'interest')
        edit_case_fact(case, source.id, 'A revised contingent fee')
        plan = plan_questions(case)
        self.assertEqual(plan.answered_count, 7)
        self.assertIn(seen[0].id, {q.id for q in plan.questions})
        answer_case_question(case, seen[0].id, 'Unknown')
        self.assertEqual(plan_questions(case).answered_count, 7)

    def test_planning_does_not_mutate_case_or_change_existing_evaluations(self):
        case = start_case(SCENARIO)
        before = deepcopy(case)
        evaluations = reason_case(case).evaluations
        self.assertEqual(plan_questions(case), plan_questions(case))
        self.assertEqual(before, case)
        self.assertEqual(reason_case(case).evaluations, evaluations)

    def test_no_threat_requires_no_artificial_minimum(self):
        case = start_case('I review an inventory valuation.')
        self.assertFalse(plan_questions(case).questions)


class Step2PersistenceAndReportTests(unittest.TestCase):
    def test_new_answers_and_phase_order_survive_json_export_import(self):
        case = start_case(SCENARIO)
        q = plan_questions(case).questions[0]
        answer_case_question(case, q.id, 'Possible covenant breach', 'The agreement needs legal review; no breach is established.')
        encoded = export_progress(Assessment(scenario=case.scenario, case_state=case), ReviewState(), AddressState(), 'case_evaluate')
        restored = import_progress(encoded).assessment.case_state
        self.assertEqual(asdict(restored), asdict(case))
        self.assertEqual(plan_questions(case), plan_questions(restored))
        self.assertEqual(plan_questions(restored).questions[0].phase, 'identify')

    def test_previous_saved_case_schema_remains_compatible(self):
        case = start_case(SCENARIO)
        document = case_to_dict(case)
        self.assertEqual(case_from_dict(document), case)
        self.assertNotIn('phase', document['state'])

    def test_older_progress_with_more_than_seven_answers_is_retained(self):
        case = crowded_case()
        with patch('objectivity.case_questions.MAX_STEP2_QUESTIONS', 10):
            run_interview(case)
        self.assertEqual(len(case.answers), 9)
        restored = case_from_dict(case_to_dict(case))
        self.assertEqual(restored, case)
        self.assertEqual(plan_questions(restored).answered_count, 9)
        self.assertFalse(plan_questions(restored).questions)

    def test_changed_work_revision_expires_dependent_details_and_retains_history(self):
        case = start_case(SCENARIO)
        run_interview(case, {'work_changed': 'Yes', 'work_change_details': 'Recommendation or conclusion'})
        details = next(f for f in case.facts if f.predicate == 'work_change_details')
        changed = next(f for f in case.facts if f.predicate == 'work_changed')
        edit_case_fact(case, changed.id, 'No')
        self.assertEqual(details.status, 'withdrawn')
        self.assertTrue(any(f.id == details.id for f in case.fact_history))
        self.assertNotIn('work_change_details', {q.predicate for q in plan_questions(case).questions})
        self.assertEqual(case_from_dict(case_to_dict(case)), case)

    def test_new_answers_are_single_scoped_values_when_replaced(self):
        case = start_case(SCENARIO)
        q = next(q for q in plan_questions(case).questions if q.predicate == 'pressure_authority')
        answer_case_question(case, q.id, 'Unknown')
        add_case_fact(case, q.subject, q.predicate, 'Directs or can override my work', q.object_id)
        current = [f for f in case.facts if f.predicate == q.predicate and f.status != 'withdrawn']
        self.assertEqual(len(current), 1)
        self.assertNotIn(q.id, case.answers)
        self.assertTrue(case.history)

    def test_preliminary_report_has_no_final_acceptable_level_verdict(self):
        case = start_case(SCENARIO)
        report = build_case_report(case)
        early = '\n'.join(re.findall(r'(?ms)^#### B\. EVALUATE\n(.*?)^#### C\. ADDRESS', report))
        self.assertNotIn('at an acceptable level', early.lower())
        self.assertIn('Preliminary significance before safeguards', early)
        self.assertIn('not an actual independent review', report)
        self.assertIn('If the recorded account is accurate', early)
        self.assertIn('commercial property', early)
        self.assertIn('Residual position', report)

    def test_favourable_initial_circumstances_are_preliminary_but_final_residual_is_preserved(self):
        case = source_case()
        connection = next(f for f in case.facts if f.predicate == 'interest_connection')
        edit_case_fact(case, connection.id, 'No')
        review_case(case)
        report = build_case_report(case)
        early = '\n'.join(re.findall(r'(?ms)^#### B\. EVALUATE\n(.*?)^#### C\. ADDRESS', report))
        self.assertIn('Recorded circumstances narrow', early)
        self.assertNotIn('at an acceptable level', early.lower())
        self.assertIn('At an acceptable level', report.split('#### C. ADDRESS')[1])

    def test_different_financing_and_pressure_answers_change_preliminary_factors_not_personal_ownership(self):
        case = start_case(SCENARIO)
        run_interview(case, {'financing_consequences': 'Possible covenant breach', 'pressure_authority': 'Both work and career influence', 'challenge_safety': 'Adverse consequences have been reported', 'work_changed': 'No'})
        first = build_case_report(case)
        self.assertIn('Possible covenant breach', first)
        self.assertIn('not verified outcomes', first)
        self.assertIn('possible future influence', first)
        self.assertFalse(any(f.predicate == 'interest' and f.subject == 'user' for f in case.facts))
        authority = next(f for f in case.facts if f.predicate == 'pressure_authority')
        edit_case_fact(case, authority.id, 'No such authority or influence')
        second = build_case_report(case)
        self.assertNotEqual(first, second)
        self.assertIn('No such authority or influence', second)

    def test_unknowns_are_natural_language_in_report(self):
        case = start_case(SCENARIO)
        run_interview(case, {'work_changed': 'Yes'})
        report = build_case_report(case)
        for key in ('pressure_authority', 'challenge_safety', 'financing_consequences', 'work_change_details'):
            self.assertNotIn(key, report)
        self.assertIn('remains unknown', report)

    def test_adequate_existing_safeguard_is_not_reclassified_by_the_planner(self):
        case = source_case()
        action(case)
        before = assess_actions(case)
        plan_questions(case)
        self.assertEqual(before, assess_actions(case))
        self.assertTrue(before.actions[0].effective)

    def test_optional_ai_cannot_invent_structured_interview_answers(self):
        source = 'I review a valuation. The CFO asks me to accept it.'
        raw = proposal(ai_fact('user', 'challenge_safety', 'review a valuation', source))
        with self.assertRaises(AIUnderstandingError):
            parse_ai_understanding(source, raw)


class Step2SupplementalEvaluationTests(unittest.TestCase):
    def assess(self, choices=None, kind='Intimidation'):
        case = start_case(SCENARIO)
        run_interview(case, choices)
        snapshot = reason_case(case)
        threat = next(t for t in snapshot.threats if t.kind == kind)
        return case, snapshot, preliminary_assessment(case, snapshot, threat)

    def test_user_experience_answers_are_labelled_you_not_the_director(self):
        case, _, result = self.assess({
            'pressure_authority': 'Both work and career influence',
            'challenge_safety': 'Adverse consequences have been reported',
            'work_changed': 'Yes', 'work_change_details': 'Investigation or evidence gathering',
        })
        self.assertTrue(any('Authority or influence over your work or career — investment director' in f for f in result.factors))
        self.assertTrue(any('Ability to challenge or escalate without adverse consequences — You:' in f for f in result.factors))
        self.assertTrue(any('Aspects of work reported as changed — You:' in f for f in result.factors))
        authority = next(f for f in case.facts if f.predicate == 'pressure_authority')
        self.assertNotEqual(authority.subject, 'user')

    def test_financing_answer_is_user_account_about_organisation_not_own_interest(self):
        case, _, result = self.assess({'financing_consequences': 'Possible covenant breach'}, 'Self-interest')
        text = ' '.join(result.factors)
        self.assertIn('You (concerning Your organisation)', text)
        self.assertIn('reported, not independently verified', text)
        self.assertFalse(any(f.predicate == 'interest' and f.subject == 'user' for f in case.facts))

    def test_authority_label_does_not_claim_director_personally_answered(self):
        _, _, result = self.assess({'pressure_authority': 'Directs or can override my work'})
        self.assertIn('investment director (reported by You)', ' '.join(result.factors))

    def test_source_explanations_are_retained_without_interpretation_or_verification(self):
        case = start_case(SCENARIO)
        q = next(q for q in plan_questions(case).questions if q.predicate == 'challenge_safety')
        explanation = 'I was told a review route exists; I have not independently checked it.'
        answer_case_question(case, q.id, 'I can challenge or escalate without adverse consequences', explanation)
        snapshot = reason_case(case)
        threat = next(t for t in snapshot.threats if t.kind == 'Intimidation')
        before = deepcopy(case)
        result = preliminary_assessment(case, snapshot, threat)
        self.assertIn(explanation, ' '.join(result.factors))
        self.assertIn('without automatic interpretation', ' '.join(result.factors))
        self.assertEqual(case, before)
        self.assertEqual(next(f for f in case.facts if f.id == case.answers[q.id].fact_id).status, 'reported')

    def test_reported_work_or_career_authority_heightens_preliminary_influence(self):
        for value in ('Directs or can override my work', 'Influences performance assessment or career progression', 'Both work and career influence'):
            with self.subTest(value=value):
                _, _, result = self.assess({'pressure_authority': value})
                self.assertIn('heightened', result.significance.lower())
                self.assertIn('uncertain', result.significance.lower())

    def test_reported_adverse_consequences_heighten_preliminary_influence(self):
        _, _, result = self.assess({'challenge_safety': 'Adverse consequences have been reported'})
        self.assertIn('heightened', result.significance.lower())
        self.assertIn('reported adverse consequences', ' '.join(result.factors).lower())

    def test_changed_work_heightens_influence_without_claiming_misconduct(self):
        _, _, result = self.assess({'work_changed': 'Yes', 'work_change_details': 'Recommendation or conclusion'})
        self.assertIn('heightened', result.significance.lower())
        self.assertIn('does not establish', ' '.join(result.factors))

    def test_favourable_channels_narrow_concern_but_future_pressure_remains(self):
        _, _, result = self.assess({
            'pressure_authority': 'No such authority or influence',
            'challenge_safety': 'I can challenge or escalate without adverse consequences',
            'work_changed': 'No',
        })
        self.assertIn('narrowed', result.significance.lower())
        self.assertIn('future pressure', result.significance.lower())
        self.assertIn('not establish that the threat has been eliminated', ' '.join(result.factors))

    def test_favourable_answer_does_not_fill_other_unknown_information(self):
        _, _, result = self.assess({'pressure_authority': 'No such authority or influence', 'work_changed': 'No'})
        self.assertIn('narrowed', result.significance.lower())
        self.assertIn('uncertain', result.significance.lower())
        self.assertTrue(any('Ability to challenge' in gap and 'unknown' in gap for gap in result.gaps))

    def test_safe_challenge_does_not_cancel_reported_authority(self):
        _, _, result = self.assess({
            'pressure_authority': 'Both work and career influence',
            'challenge_safety': 'I can challenge or escalate without adverse consequences', 'work_changed': 'No',
        })
        self.assertIn('heightened', result.significance.lower())
        self.assertIn('narrows', ' '.join(result.factors))

    def test_unknown_other_and_disputed_information_do_not_establish_favourable_facts(self):
        for value in ('Unknown', 'Other'):
            with self.subTest(value=value):
                case, snapshot, result = self.assess({'pressure_authority': value, 'challenge_safety': value, 'work_changed': 'Unknown'})
                self.assertEqual(result.significance, 'Significance remains uncertain')
                self.assertTrue(result.gaps)
                authority = next(f for f in case.facts if f.predicate == 'pressure_authority')
                edit_case_fact(case, authority.id, 'Directs or can override my work', 'disputed')
                snapshot = reason_case(case)
                threat = next(t for t in snapshot.threats if t.kind == 'Intimidation')
                self.assertNotIn('heightened', preliminary_assessment(case, snapshot, threat).significance.lower())

    def test_financing_consequences_heighten_reported_incentive_conditionally(self):
        for value in ('Possible covenant breach', 'Renegotiation or lender consent', 'Additional security', 'Changes to borrowing terms', 'Several possible consequences'):
            with self.subTest(value=value):
                _, _, result = self.assess({'financing_consequences': value}, 'Self-interest')
                self.assertIn('heightened', result.significance.lower())
                self.assertIn('not verified outcomes', ' '.join(result.factors))

    def test_no_financing_consequence_narrows_factor_without_erasing_interest(self):
        case, snapshot, result = self.assess({'financing_consequences': 'No financing consequence identified'}, 'Self-interest')
        self.assertIn('factor narrowed', result.significance.lower())
        self.assertIn('organisational interest remains', result.significance.lower())
        self.assertEqual(len([t for t in snapshot.threats if t.kind == 'Self-interest']), 1)
        self.assertTrue(any(f.predicate == 'interest' and f.subject == 'company' for f in case.facts))

    def test_unknown_financing_consequences_remain_uncertain(self):
        _, _, result = self.assess(kind='Self-interest')
        self.assertEqual(result.significance, 'Significance remains uncertain')
        self.assertTrue(any('financing' in gap.lower() and 'unknown' in gap for gap in result.gaps))

    def test_preliminary_refinements_do_not_mutate_core_evaluation_or_residuals(self):
        case = start_case(SCENARIO)
        run_interview(case, {'pressure_authority': 'Both work and career influence', 'work_changed': 'No'})
        snapshot = reason_case(case)
        original, residual = deepcopy(case), assess_actions(case)
        for threat in snapshot.threats:
            result = preliminary_assessment(case, snapshot, threat)
            self.assertNotIn('at an acceptable level', result.significance.lower())
        self.assertEqual(original, case)
        self.assertEqual(snapshot, reason_case(case))
        self.assertEqual(residual, assess_actions(case))

    def test_edit_and_json_restore_recalculate_preliminary_significance(self):
        case, _, first = self.assess({
            'pressure_authority': 'Both work and career influence',
            'challenge_safety': 'I can challenge or escalate without adverse consequences', 'work_changed': 'No',
        })
        authority = next(f for f in case.facts if f.predicate == 'pressure_authority')
        edit_case_fact(case, authority.id, 'No such authority or influence')
        run_interview(case, {'challenge_safety': 'I can challenge or escalate without adverse consequences'})
        restored = case_from_dict(case_to_dict(case))
        snapshot = reason_case(restored)
        threat = next(t for t in snapshot.threats if t.kind == 'Intimidation')
        second = preliminary_assessment(restored, snapshot, threat)
        self.assertIn('heightened', first.significance.lower())
        self.assertIn('narrowed', second.significance.lower())
        self.assertTrue(restored.fact_history)
        self.assertLessEqual(plan_questions(restored).answered_count, 7)

    def test_actual_ui_recalculates_preliminary_findings_without_clearing_step3(self):
        from objectivity.case_reasoning import ACCEPTABLE
        ui = ui_helpers.ScenarioCaseAppTests()
        ui.setUp()
        self.addCleanup(ui.doCleanups)
        ui.begin(SCENARIO)
        ui.confirm_account()
        ui.answer_material('Possible covenant breach')
        self.assertIn('Potentially heightened organisational incentive', ui.text())
        ui.answer_material('No such authority or influence')
        ui.answer_material('I can challenge or escalate without adverse consequences')
        ui.answer_material('No')
        self.assertIn('Influence channels narrowed; future pressure remains', ui.text())
        self.assertIn('investment director (reported by You)', ui.text())
        self.assertIn('Ability to challenge or escalate without adverse consequences — You:', ui.text())
        self.assertEqual(len(ui.case().answers), 4)
        ui.to_actions()
        self.assertIn('Step 3: Address Threats', ui.text())
        self.assertFalse(ui.case().actions)
        self.assertTrue(all(outcome.status != ACCEPTABLE for outcome in assess_actions(ui.case()).outcomes))


class Step2RouteAndNeutralWordingTests(unittest.TestCase):
    def intimidation(self, challenge, authority='No such authority or influence', changed='No'):
        case = start_case(SCENARIO)
        run_interview(case, {'challenge_safety': challenge, 'pressure_authority': authority,
                             'work_changed': changed, 'work_change_details': 'Investigation or evidence gathering'})
        snapshot = reason_case(case)
        threat = next(t for t in snapshot.threats if t.kind == 'Intimidation')
        return case, snapshot, preliminary_assessment(case, snapshot, threat)

    def test_no_authority_and_no_known_route_remain_uncertain_not_narrowed(self):
        case, snapshot, result = self.intimidation('No practicable route is known')
        self.assertEqual(result.significance, 'Significance remains uncertain')
        self.assertNotIn('narrows that particular influence channel', ' '.join(result.factors))
        self.assertIn('No practicable route is known', ' '.join(result.factors))
        self.assertIn('not evidence of explicit retaliation or coercion', ' '.join(result.factors))
        self.assertIn('Possible future pressure still needs consideration', ' '.join(result.factors))
        self.assertFalse(plan_questions(case).questions)
        self.assertEqual(reason_case(case), snapshot)

    def test_no_authority_and_safe_challenge_still_narrow_only_the_relevant_channels(self):
        _, _, result = self.intimidation('I can challenge or escalate without adverse consequences')
        self.assertIn('Influence channels narrowed; future pressure remains', result.significance)
        self.assertNotIn('heightened', result.significance)
        self.assertIn('not establish that the threat has been eliminated', ' '.join(result.factors))

    def test_concern_without_stated_consequence_does_not_become_reported_retaliation(self):
        _, _, result = self.intimidation('I am concerned but no consequence has been stated')
        self.assertIn('uncertain', result.significance)
        self.assertNotIn('heightened', result.significance)
        self.assertIn('no adverse consequence has been stated', ' '.join(result.factors))
        self.assertFalse(any(text.startswith('Reported adverse consequences may heighten') for text in result.factors))

    def test_no_route_and_independent_reported_authority_can_support_heightened_influence(self):
        _, _, result = self.intimidation('No practicable route is known', 'Both work and career influence')
        self.assertIn('Potentially heightened influence', result.significance)
        self.assertIn('uncertain', result.significance)
        self.assertIn('Reported authority over work or career', ' '.join(result.factors))
        self.assertIn('not evidence of explicit retaliation or coercion', ' '.join(result.factors))

    def test_no_route_and_changed_work_can_support_heightened_influence(self):
        _, _, result = self.intimidation('No practicable route is known', changed='Yes')
        self.assertIn('Potentially heightened influence', result.significance)
        self.assertIn('uncertain', result.significance)
        self.assertIn('A reported change to work', ' '.join(result.factors))
        self.assertNotIn('narrows that particular influence channel', ' '.join(result.factors))

    def assert_neutral(self, case, kind):
        from objectivity.case_reasoning import ACTION_REQUIRED
        snapshot = reason_case(case)
        threat = next(t for t in snapshot.threats if t.kind == kind)
        evaluation = next(e for e in snapshot.evaluations if e.threat_id == threat.id)
        self.assertEqual(evaluation.outcome, ACTION_REQUIRED)
        before, residual = deepcopy(case), assess_actions(case)
        result = preliminary_assessment(case, snapshot, threat)
        self.assertEqual(result.significance, 'Potentially significant influence')
        self.assertEqual(snapshot, reason_case(case))
        self.assertEqual(before, case)
        self.assertEqual(residual, assess_actions(case))
        report = build_case_report(case)
        preliminary = '\n'.join(re.findall(r'(?ms)^#### B\. EVALUATE\n(.*?)^#### C\. ADDRESS', report))
        self.assertIn('Potentially significant influence', preliminary)
        self.assertNotIn('Potential threat requiring a response', preliminary)
        self.assertNotIn('at an acceptable level', preliminary.lower())

    def test_familiarity_uses_neutral_significance_label(self):
        from tests.test_case_reasoning import case, fact, responsible
        self.assert_neutral(case(responsible(), fact('friend', 'close_relationship', 'Close personal friendship', object_id='cfo')), 'Familiarity')

    def test_self_review_uses_neutral_significance_label(self):
        from tests.test_case_reasoning import case, fact, responsible
        self.assert_neutral(case(responsible(), fact('own-work', 'self_review', 'Reviewing my own earlier work')), 'Self-review')

    def test_advocacy_uses_neutral_significance_label(self):
        from tests.test_case_reasoning import case, fact, responsible
        self.assert_neutral(case(responsible(), fact('promoted', 'advocacy', 'Promoted a position now objectively assessed')), 'Advocacy')

    def test_personal_self_interest_uses_neutral_significance_label(self):
        self.assert_neutral(source_case(), 'Self-interest')

    def test_supported_narrowing_keeps_its_label_and_step3_result(self):
        from objectivity.case_reasoning import ACCEPTABLE
        case = source_case()
        connection = next(f for f in case.facts if f.predicate == 'interest_connection')
        edit_case_fact(case, connection.id, 'No')
        review_case(case)
        snapshot = reason_case(case)
        residual = assess_actions(case)
        result = preliminary_assessment(case, snapshot, snapshot.threats[0])
        self.assertEqual(result.significance, 'Recorded circumstances narrow this potential threat')
        self.assertEqual(residual, assess_actions(case))
        self.assertTrue(all(o.status == ACCEPTABLE for o in residual.outcomes))


class Step2StreamlitTests(unittest.TestCase):
    def setUp(self):
        self.ui = ui_helpers.ScenarioCaseAppTests()
        self.ui.setUp()
        self.addCleanup(self.ui.doCleanups)

    def test_property_path_shows_one_question_stage_and_actual_source_at_a_time(self):
        self.ui.begin(SCENARIO)
        self.ui.confirm_account()
        seen = []
        while plan_questions(self.ui.case()).questions:
            q = plan_questions(self.ui.case()).questions[0]
            self.assertEqual(len(self.ui.app.radio), 1)
            self.assertEqual(self.ui.app.radio[0].label, q.prompt)
            text = self.ui.main_text_without_expanders()
            self.assertIn('STAGE 1 — IDENTIFY' if q.phase == 'identify' else 'STAGE 2 — EVALUATE', text)
            self.assertIn('THREAT IDENTIFIED', text)
            self.assertIn(q.why, text)
            self.assertIn(q.impact, text)
            self.assertNotIn('at an acceptable level', self.ui.text().lower())
            seen.append(q.predicate)
            self.ui.answer_material('Yes' if q.predicate == 'work_changed' else 'Unknown')
        self.assertEqual(len(seen), 5)
        self.assertFalse(self.ui.app.radio)
        self.assertIn('Overall preliminary assessment', self.ui.text())
        self.assertIn('investment director', self.ui.text())
        self.ui.to_actions()
        self.assertIn('Step 3: Address Threats', self.ui.text())

    def test_limit_warning_and_unresolved_issues_survive_restore(self):
        case = crowded_case()
        run_interview(case)
        review_case(case)
        progress = import_progress(export_progress(Assessment(scenario=case.scenario, case_state=case), ReviewState(), AddressState(), 'case_evaluate'))
        self.ui.restore(progress)
        self.assertFalse(self.ui.app.radio)
        self.assertIn('seven-question limit', self.ui.text())
        self.assertIn('Question limit leaves unresolved', self.ui.text())

    def test_editing_and_resume_recompute_the_active_question_and_do_not_reuse_stale_widgets(self):
        self.ui.begin(SCENARIO)
        self.ui.confirm_account()
        self.ui.answer_material('Unknown')
        current = plan_questions(self.ui.case()).questions[0]
        self.ui.restore(self.ui.round_trip())
        self.assertEqual(self.ui.app.radio[0].label, current.prompt)
        self.assertIsNone(self.ui.app.radio[0].value)
        self.assertIn('STAGE 1 — IDENTIFY', self.ui.text())

    def assert_phase_order(self, expected_groups):
        text = self.ui.main_text_without_expanders()
        threats = self.ui.reasoning().threats
        self.assertEqual(len(threats), expected_groups)
        for threat in threats:
            self.assertIn(threat.kind, text)
        plan = plan_questions(self.ui.case())
        if plan.questions:
            current = plan.questions[0]
            stage = 'STAGE 1 — IDENTIFY' if current.phase == 'identify' else 'STAGE 2 — EVALUATE'
            self.assertIn(stage, text)
            self.assertIn('Current question:', self.ui.text())
        else:
            self.assertIn('All selected clarification questions have been answered', self.ui.text())
        self.assertLessEqual(len(self.ui.app.radio), 1)

    def restore_evaluation(self, case):
        review_case(case)
        self.ui.restore(import_progress(export_progress(
            Assessment(scenario=case.scenario, case_state=case), ReviewState(), AddressState(), 'case_evaluate')))

    def test_fully_clarified_organisational_interest_keeps_both_headings_without_questions(self):
        case = start_case(SCENARIO)
        run_interview(case, {'work_changed': 'No'})
        self.restore_evaluation(case)
        self.assert_phase_order(2)
        self.assertFalse(self.ui.app.radio)
        self.assertEqual(len(case.answers), 4)
        self.assertNotIn('at an acceptable level', self.ui.text().lower())

    def test_fully_clarified_personal_interest_shows_established_information(self):
        self.restore_evaluation(source_case())
        self.assert_phase_order(1)
        self.assertFalse(self.ui.app.radio)
        self.assertIn('already established in the recorded account', self.ui.text())

    def test_fully_clarified_familiarity_keeps_both_headings_without_inventing_questions(self):
        from tests.test_case_reasoning import case, fact, responsible
        sample = case(responsible(), fact('friend', 'close_relationship', 'Current close friend', object_id='cfo'))
        self.restore_evaluation(sample)
        self.assert_phase_order(1)
        self.assertFalse(self.ui.app.radio)
        self.assertFalse(self.ui.case().answers)

    def test_identify_complete_evaluate_pending_keeps_both_headings(self):
        self.ui.begin(SCENARIO)
        self.ui.confirm_account()
        self.assert_phase_order(2)
        self.assertEqual(plan_questions(self.ui.case()).questions[0].phase, 'evaluate')
        self.assertEqual(len(self.ui.app.radio), 1)
        self.assertIn('Current question: Self-interest · EVALUATE', self.ui.text())
        self.assertIn('Relevant information already established in your account is reused', self.ui.text())
        self.assertNotIn('interest_connection', {q.predicate for q in plan_questions(self.ui.case()).questions})

    def test_both_phases_pending_show_headings_in_order_with_only_one_question(self):
        sample = start_case(SCENARIO)
        connection = next(f for f in sample.facts if f.predicate == 'interest_connection')
        edit_case_fact(sample, connection.id, connection.value, 'withdrawn')
        self.restore_evaluation(sample)
        self.assert_phase_order(2)
        first = plan_questions(self.ui.case()).questions[0]
        self.assertEqual((first.predicate, first.phase), ('interest_connection', 'identify'))
        self.assertEqual(self.ui.app.radio[0].label, first.prompt)
        self.assertIn('A relevant clarification is pending', self.ui.text())

    def test_heading_rendering_preserves_unknowns_and_source_state_across_reruns(self):
        sample = start_case(SCENARIO)
        run_interview(sample)
        self.restore_evaluation(sample)
        before = deepcopy(self.ui.case())
        self.ui.app.run()
        self.ui.healthy()
        self.assert_phase_order(2)
        self.assertEqual(before, self.ui.case())
        self.assertFalse(self.ui.app.radio)
        self.assertIn('Explicit Unknown answers and unresolved matters remain qualified', self.ui.text())

    def test_interactive_unknown_and_explanation_are_preserved_across_phase_changes(self):
        sample = start_case(SCENARIO)
        connection = next(f for f in sample.facts if f.predicate == 'interest_connection')
        edit_case_fact(sample, connection.id, connection.value, 'withdrawn')
        self.restore_evaluation(sample)
        first = plan_questions(self.ui.case()).questions[0]
        self.assertEqual(first.phase, 'identify')
        self.ui.answer_material('Yes', 'This link is my reported understanding of the agreement.')
        self.assertEqual(plan_questions(self.ui.case()).questions[0].phase, 'evaluate')
        current = plan_questions(self.ui.case()).questions[0]
        explanation = 'The covenant terms have not been checked; authority is not established.'
        self.ui.answer_material('Unknown', explanation)
        answer = self.ui.case().answers[current.id]
        self.assertEqual((answer.choice, answer.explanation), ('Unknown', explanation))
        self.assertEqual(next(f.status for f in self.ui.case().facts if f.id == answer.fact_id), 'unknown')
        next_question = plan_questions(self.ui.case()).questions[0]
        self.assertEqual((next_question.predicate, next_question.phase), ('pressure_authority', 'identify'))
        self.assertEqual(self.ui.app.radio[0].label, next_question.prompt)
        self.assertEqual(len(self.ui.app.radio), 1)
        self.ui.restore(self.ui.round_trip())
        self.assertEqual(self.ui.case().answers[current.id].explanation, explanation)
        self.assertEqual(self.ui.app.radio[0].label, next_question.prompt)
        self.assertIsNone(self.ui.app.radio[0].value)

    def test_unanswered_question_does_not_advance_or_invent_unknown(self):
        self.ui.begin(SCENARIO)
        self.ui.confirm_account()
        current = plan_questions(self.ui.case()).questions[0]
        before = deepcopy(self.ui.case())
        self.ui.click('Record answer and continue')
        self.assertEqual(before, self.ui.case())
        self.assertEqual(self.ui.app.radio[0].label, current.prompt)
        self.assertTrue(self.ui.app.warning)

    def test_free_text_decision_unknown_keeps_identify_stage_and_explanation(self):
        self.ui.begin('I need help with a professional issue.')
        self.ui.confirm_account()
        current = plan_questions(self.ui.case()).questions[0]
        self.assertEqual((current.predicate, current.options), ('decision', ()))
        self.assertIn('STAGE 1 — IDENTIFY', self.ui.main_text_without_expanders())
        self.ui.widget('text_area', 'Additional explanation (optional)').input('The assignment has not been defined.')
        self.ui.click('I do not know')
        answer = self.ui.case().answers[current.id]
        self.assertEqual((answer.choice, answer.explanation), ('Unknown', 'The assignment has not been defined.'))
        self.assertFalse(plan_questions(self.ui.case()).questions)

    def test_imported_older_budget_can_reopen_an_existing_slot_without_hiding_it(self):
        sample = crowded_case()
        seen = run_interview(sample)
        sample.fact_history.append(CaseFact('answer-old-extra', 'user', 'context',
                                           'Earlier imported answer', source='user', reviewed=True))
        source = next(f for f in sample.facts if f.id in seen[0].depends_on and f.predicate == 'interest')
        edit_case_fact(sample, source.id, 'Revised contingent fee')
        self.restore_evaluation(sample)
        plan = plan_questions(self.ui.case())
        self.assertEqual(plan.answered_count, 8)
        self.assertEqual(plan.questions[0].id, seen[0].id)
        self.assertEqual(len(self.ui.app.radio), 1)
        self.assertEqual(self.ui.app.radio[0].label, plan.questions[0].prompt)
        self.assertIn('8 answers retained from earlier progress', self.ui.text())
        self.ui.answer_material('Unknown', 'Still not established after correcting the source.')
        self.assertEqual(plan_questions(self.ui.case()).answered_count, 8)
        self.assertFalse(plan_questions(self.ui.case()).questions)
        self.assertTrue(plan_questions(self.ui.case()).deferred)


if __name__ == '__main__':
    unittest.main()
