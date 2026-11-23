"""Source edits, scoped Unknowns, actor corrections and legacy reassessment."""
from copy import deepcopy
import unittest

from objectivity.address import AddressState
from objectivity.case_model import CaseActor, CaseFact, CaseState
from objectivity.case_reasoning import reason_case
from objectivity.case_workflow import (
    start_case, answer_case_question, edit_case_fact, review_case,
    migrate_legacy_assessment, save_case_action, answer_action_question, add_case_fact,
)
from objectivity.case_actions import action_questions, assess_actions, EFFECTIVE
from objectivity.progress import export_progress, import_progress
from objectivity.models import Assessment
from objectivity.review import ReviewState
from tests.test_progress import proposed_case


def source_case():
    return CaseState('A reported professional decision.',actors=[CaseActor('user','You'),CaseActor('cfo','Finance director')],facts=[
        CaseFact('role','user','role','Financial accountant',source='user'),
        CaseFact('decision','user','decision','Assess an inventory write-down',source='user'),
        CaseFact('pressure','cfo','pressure','Requested delay to recognition',object_id='user',source='user'),
    ])


class CaseWorkflowTests(unittest.TestCase):
    def test_explicit_unknown_is_saved_and_does_not_loop(self):
        case=source_case()
        seen=[]
        for _ in range(8):
            pending=reason_case(case).questions
            if not pending: break
            question=pending[0]
            seen.append(question.id)
            answer_case_question(case,question.id,'Unknown')
        self.assertLess(len(seen),8)
        self.assertEqual(len(seen),len(set(seen)))
        self.assertFalse(reason_case(case).questions)
        self.assertTrue(any(f.status=='unknown' for f in case.facts))
        restored=import_progress(export_progress(Assessment(scenario=case.scenario,case_state=case),ReviewState(),AddressState(),'case_evaluate'))
        self.assertFalse(reason_case(restored.assessment.case_state).questions)

    def test_pressure_edit_expires_its_effect_answer_not_unrelated_responsibility(self):
        case=source_case()
        for _ in range(4):
            questions=reason_case(case).questions
            if not questions:break
            question=questions[0]
            answer_case_question(case,question.id,'I make or recommend the decision' if question.predicate=='decision_responsibility' else 'Unknown')
        self.assertEqual(len(case.answers),2)
        edit_case_fact(case,'pressure','A different direction about disclosure')
        self.assertEqual(len(case.answers),1)
        self.assertEqual(next(iter(case.answers.values())).choice,'I make or recommend the decision')
        self.assertTrue(case.history)
        self.assertFalse(case.reviewed)
        self.assertTrue(any(q.predicate=='work_changed' for q in reason_case(case).questions))

    def test_review_is_not_verification_or_new_circumstances(self):
        case=source_case()
        question=reason_case(case).questions[0]
        answer_case_question(case,question.id,'Unknown')
        before=deepcopy(case.answers)
        review_case(case)
        self.assertEqual(case.answers,before)
        self.assertTrue(all(f.status in {'reported','unknown'} for f in case.facts))

    def test_wrong_beneficiary_can_be_corrected_without_changing_who_receives_other_interests(self):
        case=source_case()
        case.facts.append(CaseFact('fee','user','interest','Consulting fee',source='user'))
        edit_case_fact(case,'fee','Consulting fee',subject='cfo')
        finding=next(t for t in reason_case(case).threats if t.kind=='Self-interest')
        self.assertEqual(finding.subject,'cfo')
        self.assertEqual(case.fact_history[-1].subject,'user')
        self.assertIn('not an assumed financial benefit for you',finding.mechanism)

    def test_legacy_reassessment_preserves_original_answers_and_actions(self):
        old,review,address=proposed_case()
        original=deepcopy((old,review,address))
        case=migrate_legacy_assessment(old,review,address)
        self.assertEqual((old,review,address),original)
        self.assertTrue(case.legacy_records)
        self.assertEqual(len(case.actions),3)
        self.assertTrue(all(a.stage=='Planned' and not a.reviewed for a in case.actions))
        self.assertTrue(any(f.predicate=='decision_responsibility' for f in case.facts))
        self.assertFalse(case.reviewed)
        document=export_progress(Assessment(scenario=case.scenario,case_state=case),ReviewState(),AddressState(),'identify')
        self.assertTrue(import_progress(document).assessment.case_state.legacy_records)

    def test_explicitly_unknown_action_stage_is_not_repeated(self):
        case=source_case()
        review_case(case)
        targets=[t.id for t in reason_case(case).threats]
        save_case_action(case,'A review is being considered','independent_review','Unknown',targets)
        self.assertFalse(any(q.key=='stage' for q in action_questions(case)))
        self.assertFalse(any(a.status==EFFECTIVE for a in assess_actions(case).actions))

    def test_known_professional_action_is_not_asked_again_as_unknown_decision(self):
        for text in (
            'I compare funding proposals. My bonus depends on the winning proposal.',
            'I prepared the impairment model and I am now reviewing my own impairment model.',
            'I promoted the client claim and I now independently assess the same claim.',
        ):
            with self.subTest(text=text):
                case=start_case(text)
                self.assertTrue(any(f.predicate=='decision' for f in case.facts))
                self.assertFalse(any(q.predicate=='decision' for q in reason_case(case).questions))

    def test_completed_action_keeps_the_person_who_performed_it(self):
        case=start_case('An independent partner completed a review of the inventory estimate.')
        self.assertTrue(case.actions)
        actor=next(a for a in case.actors if a.id==case.actions[0].actor_id)
        self.assertNotEqual(actor.id,'user')
        self.assertIn('partner',actor.label.lower())

    def test_explicit_preparation_and_comparison_are_not_asked_again_or_given_final_authority(self):
        for text in (
            'You are a financial accountant preparing year-end financial statements. Your bonus depends on profit.',
            'In my capacity as a grants assessor I compare funding proposals. My sister holds shares in a supplier.',
        ):
            case = start_case(text)
            involvement = [f for f in case.facts if f.predicate == 'decision_responsibility']
            self.assertEqual([f.value for f in involvement], ['I prepare or assess the work'])
            self.assertFalse(any(q.predicate == 'decision_responsibility' for q in reason_case(case).questions))

    def test_first_review_of_a_source_action_reuses_literal_evidence_without_verifying_it(self):
        case = start_case('I review an inventory estimate. My bonus depends on profit. An independent partner completed a review before sign-off.')
        record = case.actions[0]
        saved = save_case_action(case, record.description, record.kind, record.stage,
            [t.id for t in reason_case(case).threats], record.checks, record.id, record.actor_id)
        self.assertEqual(saved.checks['independence'], 'Yes')
        self.assertEqual(saved.checks['timing'], 'Before reliance')
        self.assertFalse(assess_actions(case).actions[0].effective)

    def test_new_evidence_answer_does_not_rebind_other_stale_effectiveness_checks(self):
        from tests.test_case_actions import source_case as financial_case, action
        case = financial_case()
        record = action(case)
        record.checks.pop('evidence')
        edit_case_fact(case, 'bonus', 'A different bonus arrangement tied to the inventory decision')
        question = next(q for q in action_questions(case) if q.key == 'evidence')
        answer_action_question(case, question.id, 'Records described')
        self.assertNotIn('independence', record.checks)
        review_case(case)
        self.assertFalse(assess_actions(case).actions[0].effective)
        self.assertTrue(case.action_history)

    def test_latest_legacy_categorical_corrections_do_not_reactivate_old_narrative_threats(self):
        from objectivity.models import Context
        previous = Assessment(
            scenario='You are an audit manager. The CFO is your close friend. Your bonus depends on profit. The CFO asks you to go easy on revenue recognition.',
            context=Context(role='Audit manager', parties='CFO', decision='Review revenue recognition',
                relationship='Professional relationship only', interests='No known interest', pressure='No reported pressure'),
            confirmed=True,
        )
        case = migrate_legacy_assessment(previous)
        self.assertFalse(reason_case(case).threats)
        self.assertTrue(case.fact_history)
        self.assertTrue(case.legacy_records)

    def test_no_involvement_avoids_immaterial_depth_but_checks_possible_earlier_work(self):
        case = start_case('I review a supplier selection. My sister owns shares in the supplier. The CFO warns that my job depends on favouring the supplier.')
        add_case_fact(case, 'user', 'decision_responsibility', 'I have no involvement in this decision')
        self.assertEqual([q.predicate for q in reason_case(case).questions], ['work_changed'])
