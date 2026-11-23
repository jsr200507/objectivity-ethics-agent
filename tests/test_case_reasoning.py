"""Decision-relevant Objectivity reasoning over attributed source facts."""
from copy import deepcopy
import unittest

from objectivity.case_model import CaseActor, CaseFact, CaseState
from objectivity.case_reasoning import (
    ACTION_REQUIRED, NARROWED, NOT_ESTABLISHED, facts_signature, reason_case,
)


def fact(id, predicate, value, subject='user', object_id='', **kwargs):
    return CaseFact(id,subject,predicate,value,object_id=object_id,source='user',**kwargs)


def case(*facts):
    return CaseState('A reported professional scenario.',actors=[
        CaseActor('user','You','Accountant'), CaseActor('cfo','CFO','Finance director'),
        CaseActor('sister','Your sister'), CaseActor('firm','Your firm',kind='organisation'),
        CaseActor('valuer','Cedar Valuations',kind='organisation'),
        CaseActor('supplier','Harbor Supplies',kind='organisation'),
    ],facts=[fact('decision','decision','Review the property valuation'),*facts])


def responsible():
    return fact('responsibility','decision_responsibility','I make or recommend the decision')


class CaseReasoningTests(unittest.TestCase):
    def test_immediate_provisional_findings_need_no_confirmation(self):
        state=case(fact('pressure','pressure','Asked to suppress a loss',subject='cfo',object_id='user'))
        result=reason_case(state)
        self.assertFalse(state.reviewed)
        self.assertEqual([t.kind for t in result.threats],['Intimidation'])
        self.assertIn('provisional',' '.join(result.evaluations[0].reasoning))
        self.assertEqual(result.threats[0].evidence_ids,('pressure',))

    def test_each_category_requires_its_specific_mechanism(self):
        examples={
            'Self-interest':fact('i','interest','Bonus or performance-related pay'),
            'Self-review':fact('r','self_review','Prepared and now reviewing own valuation'),
            'Advocacy':fact('a','advocacy','Promoted claim now expected to assess objectively'),
            'Familiarity':fact('f','close_relationship','Close personal friendship',object_id='cfo'),
            'Intimidation':fact('p','pressure','Instruction to withhold evidence',subject='cfo',object_id='user'),
        }
        for kind,source in examples.items():
            with self.subTest(kind=kind):
                self.assertEqual({t.kind for t in reason_case(case(source)).threats},{kind})

    def test_no_mechanical_all_five_categories(self):
        state=case(fact('routine','context','The manager asked for an ordinary technical assessment'))
        result=reason_case(state)
        self.assertFalse(result.threats)
        self.assertFalse(result.questions)
        self.assertIn('not evidence that threats are absent',' '.join(result.limitations))

    def test_two_interests_produce_distinct_instances_with_actual_owners(self):
        state=case(
            fact('bonus','interest','Bonus or performance-related pay'),
            fact('fee','interest','Consulting fee',subject='cfo',object_id='supplier'),
            fact('firmfee','interest','Firm fee income',subject='firm',object_id='supplier'),
        )
        result=reason_case(state)
        interests=[t for t in result.threats if t.kind=='Self-interest']
        self.assertEqual(len(interests),3)
        self.assertEqual({t.subject for t in interests},{'user','cfo','firm'})
        cfo=next(t for t in interests if t.subject=='cfo')
        self.assertIn("not an assumed financial benefit for you",cfo.mechanism)
        self.assertIn('consulting fee',cfo.mechanism.lower())

    def test_sister_shareholding_is_not_users_ownership(self):
        result=reason_case(case(
            fact('family','family_relationship','Sister',object_id='sister'),
            fact('shares','interest','Shareholding',subject='sister',object_id='supplier'),
        ))
        interest=next(t for t in result.threats if t.kind=='Self-interest')
        self.assertEqual(interest.subject,'sister')
        self.assertIn('does not establish your ownership',interest.mechanism)
        self.assertIn('family',next(t for t in result.threats if t.kind=='Familiarity').mechanism)

    def test_family_employment_questions_participation_not_personal_contact(self):
        state=case(responsible(),
            fact('family','family_relationship','Sister',object_id='sister'),
            fact('employment','employment','Employment',subject='sister',object_id='valuer'),
            fact('provider','professional_relationship','Reviewing provider work',object_id='valuer'),
        )
        result=reason_case(state)
        self.assertEqual([q.predicate for q in result.questions],['participation'])
        q=result.questions[0]
        self.assertEqual((q.subject,q.object_id),('sister','valuer'))
        self.assertIn('participate',q.prompt)
        self.assertIn('Cedar Valuations',q.prompt)
        self.assertNotIn('contact',q.prompt)
        self.assertIn('does not establish',q.why)

    def test_friendship_uses_different_material_requirements(self):
        state=case(responsible(),fact('close','close_relationship','Current close friend',object_id='cfo'))
        result=reason_case(state)
        self.assertFalse(any(q.predicate=='participation' for q in result.questions))
        self.assertFalse(result.questions)
        self.assertEqual(result.evaluations[0].outcome,ACTION_REQUIRED)

    def test_explicit_unknown_participation_is_not_reasked(self):
        state=case(responsible(),
            fact('family','family_relationship','Sister',object_id='sister'),
            fact('employment','employment','Employment',subject='sister',object_id='valuer'),
            fact('answer','participation','Unknown',subject='sister',object_id='valuer',status='unknown'),
        )
        result=reason_case(state)
        self.assertFalse(result.questions)
        self.assertTrue(result.evaluations[0].material_gaps)
        self.assertEqual(result.evaluations[0].outcome,NOT_ESTABLISHED)
        self.assertIn('unknown',result.evaluations[0].third_party)

    def test_unknown_is_scoped_to_actual_relative_and_work(self):
        state=case(responsible(),
            fact('family','family_relationship','Sister',object_id='sister'),
            fact('employment','employment','Employment',subject='sister',object_id='valuer'),
            fact('unrelated','participation','Unknown',subject='cfo',object_id='valuer',status='unknown'),
        )
        q=reason_case(state).questions[0]
        self.assertEqual(q.subject,'sister')

    def test_participation_changes_significance_without_assuming_misconduct(self):
        state=case(responsible(),
            fact('family','family_relationship','Sister',object_id='sister'),
            fact('employment','employment','Employment',subject='sister',object_id='valuer'),
            fact('participation','participation','Yes',subject='sister',object_id='valuer'),
        )
        yes=reason_case(state)
        state.facts[-1].value='No'
        no=reason_case(state)
        self.assertEqual(yes.evaluations[0].outcome,ACTION_REQUIRED)
        self.assertEqual(no.evaluations[0].outcome,NOT_ESTABLISHED)
        self.assertIn('not to have participated',' '.join(no.evaluations[0].reasoning))
        self.assertEqual(yes.threats[0].id,no.threats[0].id)

    def test_explicit_unrelated_interest_is_not_an_established_threat(self):
        result=reason_case(case(
            fact('stake','interest','Shareholding',object_id='supplier'),
            fact('link','interest_connection','No',object_id='supplier'),
        ))
        # Keep a considered source visible so a favourable evaluation has an
        # inspectable basis rather than silently disappearing from the report.
        self.assertEqual([item.kind for item in result.threats], ['Self-interest'])
        self.assertEqual(result.evaluations[0].outcome, NARROWED)
        self.assertFalse(result.questions)
        self.assertIn('not to connect',' '.join(result.limitations))

    def test_known_bonus_connection_is_not_requested_again(self):
        state=case(responsible(),
            fact('bonus','interest','Bonus or performance-related pay'),
            fact('link','interest_connection','Yes'),
        )
        result=reason_case(state)
        self.assertFalse(result.questions)
        self.assertEqual(result.evaluations[0].outcome,ACTION_REQUIRED)

    def test_pressure_already_changed_work_is_distinct_from_future_influence(self):
        state=case(responsible(),fact('pressure','pressure','Requested early revenue recognition',subject='cfo',object_id='user'))
        first=reason_case(state)
        self.assertEqual([q.predicate for q in first.questions],['work_changed'])
        state.facts.append(fact('changed','work_changed','No',object_id='cfo'))
        unchanged=reason_case(state)
        self.assertFalse(unchanged.questions)
        self.assertIn('possible future influence',' '.join(unchanged.evaluations[0].reasoning))
        state.facts[-1].value='Yes'
        changed=reason_case(state)
        self.assertIn('affected judgment',' '.join(changed.evaluations[0].reasoning))
        self.assertEqual(changed.evaluations[0].outcome,ACTION_REQUIRED)

    def test_no_involvement_narrows_finding_and_conflicting_changed_work_remains_explicit(self):
        state=case(fact('r','decision_responsibility','I have no involvement in this decision'),
            fact('p','pressure','A warning was reported',subject='cfo',object_id='user'),
            fact('w','work_changed','No',object_id='cfo'),
        )
        self.assertEqual(reason_case(state).evaluations[0].outcome,NARROWED)
        state.facts[-1].value='Yes'
        result=reason_case(state)
        self.assertEqual(result.evaluations[0].outcome,ACTION_REQUIRED)
        self.assertIn('conflicts',' '.join(result.evaluations[0].material_gaps))

    def test_one_scoped_question_can_serve_distinct_pressure_sources(self):
        state=case(responsible(),
            fact('delay','pressure','Delay recognising the loss',subject='cfo',object_id='user'),
            fact('withhold','pressure','Do not inform the auditors',subject='cfo',object_id='user'),
        )
        result=reason_case(state)
        self.assertEqual(len(result.threats),2)
        self.assertEqual(len(result.questions),1)
        self.assertEqual(len(result.questions[0].threat_ids),2)
        self.assertEqual(set(result.questions[0].depends_on),{'delay','withhold','decision'})

    def test_material_question_prioritises_responsibility(self):
        state=case(fact('pressure','pressure','Pressure',subject='cfo',object_id='user'))
        questions=reason_case(state).questions
        self.assertEqual(questions[0].predicate,'decision_responsibility')
        self.assertIn('can narrow',questions[0].impact)
        self.assertTrue(all(q.why and q.impact for q in questions))

    def test_self_review_and_advocacy_do_not_reask_explicit_current_role(self):
        for predicate in ('self_review','advocacy'):
            with self.subTest(predicate=predicate):
                state=case(fact('source',predicate,'Earlier work or position now objectively assessed'))
                result=reason_case(state)
                self.assertFalse(result.questions)
                self.assertEqual(result.evaluations[0].outcome,ACTION_REQUIRED)

    def test_denied_withdrawn_and_unknown_sources_do_not_create_affirmative_findings(self):
        for status in ('denied','withdrawn','unknown','disputed'):
            with self.subTest(status=status):
                state=case(fact('p','pressure','Unknown influence',subject='cfo',status=status))
                self.assertFalse(reason_case(state).threats)

    def test_confidence_and_planned_actions_cannot_clear_initial_findings(self):
        from objectivity.case_model import CaseAction
        state=case(responsible(),fact('p','pressure','Suppress findings',subject='cfo',object_id='user'))
        initial=reason_case(state)
        state.facts.append(fact('confidence','assurance','I am completely impartial'))
        state.actions.append(CaseAction('a','Request review','independent_review','Planned'))
        after=reason_case(state)
        self.assertEqual(initial.evaluations[0].outcome,after.evaluations[0].outcome)
        self.assertEqual(initial.threats[0].id,after.threats[0].id)

    def test_combined_threats_have_interaction_without_double_corroboration(self):
        state=case(fact('bonus','interest','Bonus or performance-related pay'),
            fact('pressure','pressure','Bonus may be lost',subject='cfo',object_id='user'),
            fact('close','close_relationship','Close friend',object_id='cfo'))
        result=reason_case(state)
        text=' '.join(result.interactions)
        self.assertIn('not independent corroboration',text)
        self.assertIn('beneficiary',text)
        self.assertIn('identities are not assumed',text)

    def test_third_party_assessment_is_case_specific_and_conditional(self):
        state=case(responsible(),fact('p','pressure','Omit the valuation issue',subject='cfo',object_id='user'))
        result=reason_case(state)
        text=result.evaluations[0].third_party
        self.assertIn('CFO',text)
        self.assertIn('property valuation',text)
        self.assertIn('actual bias need not be proved',text)
        self.assertNotIn('independently reviewed this case',text)

    def test_signature_changes_with_material_source_but_not_review_or_revision(self):
        state=case(fact('bonus','interest','Bonus'))
        original=facts_signature(state,['bonus'])
        state.reviewed=True
        state.revision=15
        state.facts[-1].reviewed=True
        state.facts[-1].revision=15
        self.assertEqual(original,facts_signature(state,['bonus']))
        state.facts[-1].value='Shares'
        self.assertNotEqual(original,facts_signature(state,['bonus']))
        self.assertNotEqual(original,facts_signature(state,['missing']))

    def test_reasoning_does_not_mutate_source_state(self):
        state=case(fact('bonus','interest','Bonus'))
        before=deepcopy(state)
        self.assertEqual(reason_case(state),reason_case(state))
        self.assertEqual(state,before)

    def test_vague_scenario_asks_only_material_professional_decision_once(self):
        state=CaseState('Something worries me.')
        result=reason_case(state)
        self.assertFalse(result.threats)
        self.assertEqual([q.predicate for q in result.questions],['decision'])
        state.facts.append(fact('q','decision','Unknown',status='unknown'))
        result=reason_case(state)
        self.assertFalse(result.questions)
        self.assertIn('explicitly unknown',' '.join(result.limitations))


if __name__=='__main__':
    unittest.main()
