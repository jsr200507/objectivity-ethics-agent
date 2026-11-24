"""Action effectiveness requires scope, implementation and outcome evidence."""
from copy import deepcopy
import unittest

from objectivity.case_model import CaseAction, CaseActor, CaseFact, CaseState
from objectivity.case_reasoning import reason_case
from objectivity.case_actions import (
    EFFECTIVE, INSUFFICIENT, POTENTIALLY_REDUCED, SUPPORTED, UNACCEPTABLE,
    action_basis_signature, action_questions, assess_actions,
)
from objectivity.case_workflow import answer_action_question, edit_case_fact, review_case


def fact(id, predicate, value, subject='user', object_id='', **kwargs):
    return CaseFact(id, subject, predicate, value, object_id=object_id,
                    source='user', reviewed=True, **kwargs)


def source_case(*extra):
    return CaseState(
        'An accountant assesses inventory while a recorded bonus may be affected.',
        actors=[CaseActor('user','You','Accountant'), CaseActor('cfo','Finance director'),
                CaseActor('firm','Your firm',kind='organisation'),
                CaseActor('sister','Your sister'),CaseActor('valuer','Cedar Valuations',kind='organisation')],
        facts=[fact('role','role','Financial accountant'),
               fact('decision','decision','Assess the inventory write-down'),
               fact('responsibility','decision_responsibility','I make or recommend the decision'),
               fact('bonus','interest','Bonus linked to reported profit'),
               fact('connection','interest_connection','Yes'),
               *extra],
        reviewed=True, actions_reviewed=True,
    )


def full_review_checks():
    return {
        'independence':'Yes','competence':'Yes','authority':'Yes',
        'coverage':'All linked circumstances','timing':'Before reliance',
        'outcome':'No continuing influence identified','evidence':'Records described',
    }


def action(case, *, kind='independent_review', stage='Implemented', checks=None,
           selected=None, reviewed=True, evidence='Signed review notes describe the inventory test, challenge and resolved changes.',
           description='Review the inventory judgment independently', id='review'):
    snapshot=reason_case(case)
    targets=tuple(t.id for t in snapshot.threats) if selected is None else tuple(selected)
    record=CaseAction(id,description,kind,stage,threat_ids=targets,
                      checks=full_review_checks() if checks is None else dict(checks),
                      reviewed=reviewed,evidence_detail=evidence)
    case.actions.append(record)
    record.basis_signature=action_basis_signature(case,record)
    return record


class CaseActionTests(unittest.TestCase):
    def test_no_recorded_action_is_unknown_not_not_taken(self):
        case=source_case()
        case.actions_reviewed=False
        result=assess_actions(case)
        self.assertFalse(result.actions)
        self.assertIn('absence', ' '.join(result.unknowns))
        self.assertNotIn('adequately addressed', result.conclusion)

    def test_explicit_not_taken_is_distinct_from_missing(self):
        case=source_case()
        action(case,kind='none',stage='Not Taken',checks={},evidence='',description='No relevant action has been taken')
        result=assess_actions(case)
        self.assertEqual(result.actions[0].status,'Not Taken')
        self.assertFalse(result.actions[0].effective)
        self.assertEqual(result.outcomes[0].status,UNACCEPTABLE)

    def test_planned_review_never_counts_as_completed_or_effective(self):
        case=source_case()
        action(case,stage='Planned')
        result=assess_actions(case)
        self.assertEqual(result.actions[0].status,'Planned')
        self.assertFalse(result.actions[0].effective)
        self.assertIn('completed implementation is not established',' '.join(result.actions[0].reasoning))
        self.assertFalse(action_questions(case))
        self.assertNotEqual(result.outcomes[0].status,SUPPORTED)

    def test_implementation_alone_has_no_effectiveness_assurance(self):
        case=source_case()
        action(case,checks={},evidence='')
        result=assess_actions(case)
        self.assertEqual(result.actions[0].status,'Implemented')
        self.assertFalse(result.actions[0].effective)
        self.assertEqual(result.outcomes[0].status,POTENTIALLY_REDUCED)
        self.assertIn('independence', ' '.join(result.actions[0].gaps))
        self.assertEqual(action_questions(case)[0].key,'independence')

    def test_complete_case_specific_records_support_conditional_effectiveness(self):
        case=source_case()
        action(case)
        result=assess_actions(case)
        self.assertTrue(result.actions[0].effective)
        self.assertEqual(result.actions[0].status,EFFECTIVE)
        self.assertEqual(result.outcomes[0].status,SUPPORTED)
        self.assertIn('conditionally', result.conclusion)
        self.assertIn('not independent verification', result.conclusion)
        self.assertFalse(action_questions(case))

    def test_external_independent_checker_is_not_a_universal_requirement(self):
        case=source_case()
        record=action(case)
        self.assertFalse(any('external' in key for key in record.checks))
        self.assertEqual(assess_actions(case).outcomes[0].status,SUPPORTED)

    def test_unreviewed_action_does_not_receive_positive_effectiveness(self):
        case=source_case()
        action(case,reviewed=False)
        result=assess_actions(case)
        self.assertFalse(result.actions[0].effective)
        self.assertTrue(any('reviewed by the user' in gap for gap in result.actions[0].gaps))

    def test_reviewing_case_is_not_independent_verification(self):
        case=source_case()
        case.reviewed=False
        record=action(case)
        self.assertFalse(assess_actions(case).actions[0].effective)
        signature=record.basis_signature
        review_case(case)
        self.assertEqual(record.basis_signature,signature)
        self.assertTrue(assess_actions(case).actions[0].effective)
        self.assertIn('not independent verification',' '.join(assess_actions(case).actions[0].reasoning))

    def test_partial_coverage_cannot_clear_the_linked_source(self):
        case=source_case()
        checks=full_review_checks();checks['coverage']='Partial'
        action(case,checks=checks)
        result=assess_actions(case)
        self.assertFalse(result.actions[0].effective)
        self.assertEqual(result.outcomes[0].status,POTENTIALLY_REDUCED)
        self.assertTrue(any('coverage' in gap for gap in result.actions[0].gaps))
        self.assertFalse(action_questions(case), 'Known partial coverage should not trigger an irrelevant full checklist')

    def test_known_ineffective_review_requires_further_action(self):
        case=source_case()
        checks=full_review_checks();checks['independence']='No'
        action(case,checks=checks)
        result=assess_actions(case)
        self.assertTrue(result.actions[0].failed)
        self.assertEqual(result.outcomes[0].status,UNACCEPTABLE)
        self.assertTrue(any('unsuccessful or inadequate' in step for step in result.next_steps))

    def test_documentation_and_disclosure_are_not_automatic_safeguards(self):
        for kind in ('document','disclose','escalate'):
            with self.subTest(kind=kind):
                case=source_case()
                action(case,kind=kind)
                result=assess_actions(case)
                self.assertFalse(result.actions[0].effective)
                self.assertIn('concrete resulting protective measure',' '.join(result.actions[0].gaps))
                self.assertEqual(action_questions(case)[0].key,'result')

    def test_reporting_a_result_still_requires_separate_protective_measure(self):
        case=source_case()
        checks={'result':'A separate protective measure was completed'}
        action(case,kind='escalate',checks=checks)
        self.assertFalse(action_questions(case))
        self.assertFalse(assess_actions(case).actions[0].effective)

    def test_concrete_record_description_is_required_not_checkbox_assertion(self):
        case=source_case()
        action(case,evidence='')
        result=assess_actions(case)
        self.assertFalse(result.actions[0].effective)
        self.assertEqual(action_questions(case)[0].key,'evidence_detail')

    def test_explicit_unknown_record_description_is_not_effectiveness(self):
        case=source_case()
        action(case,evidence='Unknown')
        result=assess_actions(case)
        self.assertFalse(result.actions[0].effective)
        self.assertTrue(any('not been described' in gap for gap in result.actions[0].gaps))
        self.assertFalse(action_questions(case), 'An explicit Unknown should not be asked repeatedly')

    def test_unknown_criterion_is_not_an_endless_question_loop(self):
        case=source_case()
        action(case,checks={'independence':'Unknown'},evidence='')
        self.assertFalse(action_questions(case))
        self.assertFalse(assess_actions(case).actions[0].effective)

    def test_unknown_implementation_status_is_asked_and_saved_once(self):
        case=source_case()
        action(case,stage='Unknown',checks={},evidence='')
        q=action_questions(case)[0]
        self.assertEqual(q.key,'stage')
        answer_action_question(case,q.id,'Unknown')
        self.assertFalse(action_questions(case))
        self.assertEqual(case.actions[0].stage,'Unknown')
        self.assertFalse(assess_actions(case).actions[0].effective)

    def test_implemented_status_answer_opens_only_relevant_evidence_question(self):
        case=source_case()
        action(case,stage='Unknown',checks={},evidence='')
        answer_action_question(case,action_questions(case)[0].id,'Implemented')
        self.assertEqual(case.actions[0].stage,'Implemented')
        self.assertEqual(action_questions(case)[0].key,'independence')

    def test_one_action_covers_only_explicitly_linked_threat_instances(self):
        case=source_case(fact('pressure','pressure','Promotion depends on favouring the estimate',subject='cfo',object_id='user'))
        snapshot=reason_case(case)
        bonus=next(t for t in snapshot.threats if t.kind=='Self-interest')
        action(case,selected=(bonus.id,))
        result=assess_actions(case)
        self.assertEqual(next(o for o in result.outcomes if o.threat_id==bonus.id).status,SUPPORTED)
        self.assertNotEqual(next(o for o in result.outcomes if o.kind=='Intimidation').status,SUPPORTED)
        self.assertNotIn('conditionally supports',result.conclusion)

    def test_one_review_can_cover_multiple_sources_when_explicitly_supported(self):
        case=source_case(fact('pressure','pressure','Promotion depends on favouring the estimate',subject='cfo',object_id='user'),
                         fact('changed','work_changed','No',object_id='cfo'))
        action(case)
        result=assess_actions(case)
        self.assertEqual(len(result.outcomes),2)
        self.assertTrue(all(o.status==SUPPORTED for o in result.outcomes))

    def test_separate_effective_actions_can_address_separate_sources(self):
        case=source_case(fact('fee','interest','Consulting fee',subject='cfo'))
        threats=reason_case(case).threats
        for n,threat in enumerate(threats):
            action(case,selected=(threat.id,),id=f'review{n}')
        result=assess_actions(case)
        self.assertTrue(all(o.status==SUPPORTED for o in result.outcomes))

    def test_continuing_influence_overrides_another_positive_response(self):
        case=source_case()
        action(case,id='good')
        checks=full_review_checks();checks['outcome']='Continuing influence remains'
        action(case,checks=checks,id='bad')
        result=assess_actions(case)
        self.assertFalse(all(o.status==SUPPORTED for o in result.outcomes))
        self.assertTrue(any(a.failed for a in result.actions))
        self.assertNotIn('conditionally supports',result.conclusion)

    def test_editing_material_fact_invalidates_action_coverage(self):
        case=source_case()
        record=action(case)
        before=record.basis_signature
        edit_case_fact(case,'bonus','Bonus depends on a different judgment')
        self.assertFalse(case.reviewed)
        self.assertNotEqual(before,action_basis_signature(case,record))
        self.assertFalse(assess_actions(case).actions[0].effective)
        self.assertTrue(any('coverage needs confirmation' in gap for gap in assess_actions(case).actions[0].gaps))

    def test_source_history_survives_material_correction(self):
        case=source_case()
        action(case)
        edit_case_fact(case,'bonus','Revised bonus terms')
        self.assertEqual(case.fact_history[-1].value,'Bonus linked to reported profit')
        self.assertTrue(case.actions)
        self.assertEqual(case.actions[0].stage,'Implemented')

    def test_replacement_does_not_automatically_repair_affected_prior_work(self):
        case=source_case(fact('pressure','pressure','Director threatened a demotion',subject='cfo',object_id='user'),
                         fact('changed','work_changed','Yes',object_id='cfo'))
        checks={
            'replacement':'Independent replacement with decision authority','coverage':'All linked circumstances',
            'timing':'Before reliance','outcome':'No continuing influence identified','evidence':'Records described',
        }
        action(case,kind='remove_from_decision',checks=checks)
        self.assertFalse(assess_actions(case).actions[0].effective)
        self.assertEqual(action_questions(case)[0].key,'prior_work')

    def test_reassessing_affected_work_can_change_residual_conclusion(self):
        case=source_case(fact('changed','work_changed','Yes'))
        record=action(case)
        self.assertFalse(assess_actions(case).actions[0].effective)
        record.checks['prior_work']='Affected work was reassessed'
        self.assertTrue(assess_actions(case).actions[0].effective)

    def test_old_unknown_can_become_immaterial_after_evidenced_full_review(self):
        case=source_case(
            fact('family','family_relationship','Sister',object_id='sister'),
            fact('employment','employment','Works at the valuation provider',subject='sister',object_id='valuer'),
            fact('provider','professional_relationship','Reviewing provider work',object_id='valuer'),
            fact('participation','participation','Unknown',subject='sister',object_id='valuer',status='unknown'),
        )
        self.assertTrue(any(e.material_gaps for e in reason_case(case).evaluations))
        action(case)
        result=assess_actions(case)
        self.assertTrue(all(o.status==SUPPORTED for o in result.outcomes))
        self.assertTrue(any('Earlier uncertainty remains' in reason for o in result.outcomes for reason in o.reasoning))

    def test_no_threat_is_not_certified_clearance(self):
        case=source_case()
        case.facts=[f for f in case.facts if f.predicate not in {'interest','interest_connection'}]
        result=assess_actions(case)
        self.assertFalse(result.outcomes)
        self.assertIn('not assurance',result.conclusion)

    def test_assessment_does_not_mutate_sources_or_claim_authentication(self):
        case=source_case();action(case)
        before=deepcopy(case)
        result=assess_actions(case)
        self.assertEqual(case,before)
        self.assertIn('not independent verification',result.conclusion)
        self.assertIn('not an actual independent',result.outcomes[0].third_party)


if __name__=='__main__':
    unittest.main()
