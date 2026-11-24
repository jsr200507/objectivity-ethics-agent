"""Reusable local understanding: attribution, source evidence and uncertainty."""
from copy import deepcopy
import unittest

from objectivity.case_model import CaseActor, CaseAction, CaseFact, UnderstandingResult
from objectivity.examples import EXAMPLE_SCENARIO
from objectivity.understanding import LocalUnderstandingProvider, validate_understanding

FULL_INVENTORY = (
    "You are a financial accountant preparing the year-end financial statements of a manufacturing company. "
    "Your finance director asks you to delay recognising a significant inventory write-down because it would reduce the company's reported profit. "
    "Your annual performance bonus depends partly on achieving the company's profit target. "
    "The finance director says the inventory may recover in value next year and asks you not to raise the issue with the auditors."
)
PROPERTY = (
    "You are a financial accountant reviewing a property valuation prepared by Cedar Valuations. "
    "Your sister works for Cedar Valuations. You do not know whether she participated in the valuation."
)
PROCUREMENT = (
    "In my capacity as a sourcing intelligence associate, I compare quotations from Quarry Engineering and Rivergate Supplies. "
    "My sister holds shares in Quarry Engineering. Our procurement director receives a consulting fee from Quarry Engineering "
    "and says my promotion depends on favouring it."
)


class UnderstandingTests(unittest.TestCase):
    def understand(self, text):
        result=LocalUnderstandingProvider().understand(text)
        actors={actor.id:actor for actor in result.actors}
        for fact in result.facts:
            self.assertIn(fact.excerpt,text)
            self.assertFalse(fact.reviewed)
            self.assertEqual(fact.source,'scenario')
            self.assertIn(fact.subject,actors)
            if fact.object_id:self.assertIn(fact.object_id,actors)
        for action in result.actions:
            self.assertIn(action.excerpt,text)
            self.assertFalse(action.reviewed)
            self.assertNotEqual(action.stage,'Effectiveness Established')
        return result

    def facts(self,result,predicate):
        return [fact for fact in result.facts if fact.predicate==predicate]

    def test_cfo_has_distinct_relationship_incentive_and_pressure_sources(self):
        result=self.understand(EXAMPLE_SCENARIO)
        relation=self.facts(result,'close_relationship')[0]
        self.assertEqual(relation.subject,'user')
        self.assertEqual(relation.object_id,'cfo')
        self.assertEqual(self.facts(result,'relationship_active')[0].value,'Yes')
        self.assertEqual(self.facts(result,'interest')[0].subject,'firm')
        self.assertTrue(self.facts(result,'pressure'))
        self.assertFalse(self.facts(result,'self_review'))
        self.assertFalse(self.facts(result,'advocacy'))

    def test_inventory_separates_bonus_from_organisational_profit(self):
        result=self.understand(FULL_INVENTORY)
        interests=self.facts(result,'interest')
        self.assertEqual({f.subject for f in interests},{'user','company'})
        self.assertIn('Bonus or performance-related pay',{f.value for f in interests})
        self.assertEqual(len(self.facts(result,'interest_connection')),2)
        self.assertEqual(len(self.facts(result,'pressure')),2)
        claim=self.facts(result,'claim')[0]
        self.assertIn('may recover',claim.value)
        self.assertNotEqual(claim.subject,'user')
        self.assertFalse(any(f.predicate=='context' and 'will recover' in f.value for f in result.facts))
        self.assertTrue(any(a.label.lower() == 'auditors' for a in result.actors))
        self.assertFalse(any('external auditors' in a.label.lower() for a in result.actors))
        decision = self.facts(result, 'decision')[0]
        self.assertIn('inventory write-down', decision.excerpt)
        self.assertIn('auditors', decision.excerpt)

    def test_information_recipients_retain_literal_roles_without_inventing_affiliations(self):
        for recipient in ('auditors', 'audit committee', 'regulator', 'board of directors'):
            source = f'The finance director asks me not to inform the {recipient} about the estimate.'
            result = self.understand(source)
            self.assertTrue(any(a.label.lower() == recipient for a in result.actors))
            self.assertFalse(any(f.predicate in {'family_relationship', 'close_relationship'} for f in result.facts))

    def test_family_employment_does_not_invent_participation(self):
        result=self.understand(PROPERTY)
        relation=self.facts(result,'family_relationship')[0]
        employment=self.facts(result,'employment')[0]
        provider_link=self.facts(result,'professional_relationship')[0]
        self.assertEqual(relation.object_id,employment.subject)
        self.assertEqual(employment.object_id,provider_link.object_id)
        participation=self.facts(result,'participation')[0]
        self.assertEqual(participation.value,'Unknown')
        self.assertEqual(participation.status,'unknown')
        self.assertFalse(self.facts(result,'interest'))

    def test_unmentioned_family_participation_stays_missing(self):
        result=self.understand(PROPERTY.split(' You do not know')[0])
        self.assertTrue(self.facts(result,'employment'))
        self.assertFalse(self.facts(result,'participation'))

    def test_explicit_nonparticipation_is_reusable_and_not_unknown(self):
        result=self.understand(PROPERTY.split(' You do not know')[0]+' Your sister was not involved in the valuation.')
        self.assertEqual(self.facts(result,'participation')[0].value,'No')

    def test_procurement_does_not_assign_family_or_director_money_to_user(self):
        result=self.understand(PROCUREMENT)
        interests=self.facts(result,'interest')
        financial=[f for f in interests if 'career' not in f.value.lower()]
        self.assertEqual(len(financial),2)
        self.assertNotIn('user',{f.subject for f in financial})
        self.assertTrue(any(f.subject=='user' and 'career' in f.value.lower() for f in interests))
        self.assertIn('family_sister',{f.subject for f in interests})
        fee=next(f for f in interests if 'fee' in f.value)
        self.assertIn('director',{a.id:a for a in result.actors}[fee.subject].label)
        self.assertEqual(self.facts(result,'pressure')[0].subject,fee.subject)
        self.assertFalse(self.facts(result,'role'))  # unfamiliar title is not guessed

    def test_multiple_same_category_sources_remain_distinct(self):
        source='I am an auditor. My annual bonus depends on profit. Our firm contract renewal depends on a smooth audit.'
        result=self.understand(source)
        self.assertEqual(len(self.facts(result,'interest')),2)
        self.assertEqual(len({f.id for f in self.facts(result,'interest')}),2)

    def test_own_commission_and_counterpart_fee_are_not_merged(self):
        result=self.understand('I am a credit analyst. My commission depends on loan approval. The branch manager receives a consulting fee from Oak Bank.')
        self.assertEqual(len(self.facts(result,'interest')),2)
        self.assertIn('user',{f.subject for f in self.facts(result,'interest')})
        self.assertEqual(len({f.subject for f in self.facts(result,'interest')}),2)

    def test_quoted_counterpart_first_person_is_not_user_interest(self):
        for text in (
            'I am an auditor. The CFO says, "My annual bonus depends on approval."',
            "I am an auditor. My manager explained, 'I own shares in the client.'",
        ):
            with self.subTest(text=text):
                result=self.understand(text)
                self.assertTrue(self.facts(result,'interest'))
                self.assertNotIn('user',{f.subject for f in self.facts(result,'interest')})

    def test_unidentified_quoted_speaker_is_not_assigned_to_user(self):
        result=self.understand('Jane said, "My annual bonus depends on profit."')
        owner=self.facts(result,'interest')[0].subject
        self.assertNotEqual(owner,'user')

    def test_own_statement_remains_own_interest(self):
        result=self.understand('I said, "My bonus depends on the outcome."')
        self.assertEqual(self.facts(result,'interest')[0].subject,'user')

    def test_negated_ownership_and_nonfinancial_promotion_are_not_personal_money(self):
        for text in ('I do not own shares in the client.','My salary is not linked to this decision.','My promotion may be affected, but no financial benefit is stated.'):
            with self.subTest(text=text):self.assertFalse(self.facts(self.understand(text),'interest'))

    def test_hypothetical_family_and_pressure_are_not_current_facts(self):
        for text in (
            'Suppose my sister owns shares in a supplier.',
            'If the CFO were my close friend, I would consult my manager.',
            'If my manager threatened me, I would refuse.',
        ):
            with self.subTest(text=text):
                result=self.understand(text)
                self.assertFalse([f for f in result.facts if f.predicate in {'interest','pressure','close_relationship','family_relationship'}])

    def test_third_party_friendship_is_not_user_friendship(self):
        for text in ("I am an auditor. The CFO is the CEO's close friend.","I am an auditor. The CFO, a close friend of the CEO, asks for help."):
            with self.subTest(text=text):self.assertFalse(self.facts(self.understand(text),'close_relationship'))

    def test_pressure_is_reported_without_asserting_threat_or_work_change(self):
        result=self.understand('The finance director asks me to defer recognition of the loss and not inform the auditors.')
        self.assertTrue(self.facts(result,'pressure'))
        self.assertFalse(self.facts(result,'work_changed'))

    def test_routine_and_protective_requests_do_not_become_pressure(self):
        for text in (
            'The director asks me to assess the estimate.',
            'The CFO warns me not to ignore contradictory audit evidence.',
            'The director asks me not to conceal the loss from the auditors.',
            'The CFO threatened litigation against a supplier.',
        ):
            with self.subTest(text=text):self.assertFalse(self.facts(self.understand(text),'pressure'))

    def test_own_earlier_work_supports_self_review_only(self):
        result=self.understand('I am an actuary. I prepared the reserve model and now review my own reserve model.')
        self.assertEqual(len(self.facts(result,'self_review')),1)
        self.assertFalse(self.facts(result,'advocacy'))
        self.assertFalse(self.facts(result,'pressure'))

    def test_same_work_reference_supports_self_review(self):
        result=self.understand('I prepared a valuation and now review it.')
        self.assertTrue(self.facts(result,'self_review'))

    def test_unrelated_work_or_negation_does_not_create_self_review(self):
        for text in ('I prepared training slides and now review a different property valuation.','I do not review my own work.','I review a report prepared by an unrelated valuer.'):
            with self.subTest(text=text):self.assertFalse(self.facts(self.understand(text),'self_review'))

    def test_advocacy_requires_promoting_the_position_under_assessment(self):
        result=self.understand("I promoted the client's compensation claim and now must assess it objectively.")
        self.assertTrue(self.facts(result,'advocacy'))
        self.assertFalse(self.facts(result,'self_review'))

    def test_communicating_results_or_unrelated_advocacy_is_not_automatically_advocacy(self):
        for text in ('I communicate the completed audit findings to the board.','I promoted a charity event and now assess an unrelated tax return.','I do not advocate a position; I assess it independently.'):
            with self.subTest(text=text):self.assertFalse(self.facts(self.understand(text),'advocacy'))

    def test_action_request_is_planned_not_implemented(self):
        result=self.understand('I have requested an independent review of the revenue judgement.')
        self.assertEqual(result.actions[0].stage,'Planned')
        self.assertEqual(result.actions[0].kind,'independent_review')
        self.assertFalse(result.actions[0].reviewed)
        self.assertEqual(result.actions[0].threat_ids,())
        self.assertNotIn('evidence',result.actions[0].checks)

    def test_completed_review_does_not_invent_effectiveness(self):
        result=self.understand('An independent partner completed a review of the estimate before sign-off.')
        action=result.actions[0]
        self.assertEqual(action.stage,'Implemented')
        self.assertEqual(action.checks,{'independence':'Yes','timing':'Before reliance'})
        self.assertEqual(action.evidence_detail,'')

    def test_negated_completion_never_establishes_implementation(self):
        for source in ('The independent review was never completed.',
                       'No independent review has been completed.',
                       'The independent review has never been completed.'):
            with self.subTest(source=source):
                self.assertEqual(self.understand(source).actions[0].stage, 'Unknown')

    def test_uncertainty_about_completion_remains_unknown(self):
        for source in ('I do not know whether the independent review was completed.',
                       'It is unclear whether the independent review was carried out.'):
            with self.subTest(source=source):
                self.assertEqual(self.understand(source).actions[0].stage, 'Unknown')

    def test_actual_records_and_outcome_checks_remain_source_assertions(self):
        result=self.understand('An independent partner completed a review; review notes are retained and no continuing influence was identified.')
        action=result.actions[0]
        self.assertEqual(action.checks['evidence'],'Records described')
        self.assertEqual(action.checks['outcome'],'No continuing influence identified')
        self.assertIn('review notes',action.evidence_detail)
        self.assertFalse(action.reviewed)

    def test_no_mentioned_action_is_unknown_not_not_taken(self):
        self.assertFalse(self.understand('I am an auditor reviewing an estimate.').actions)
        result=self.understand('I have taken no action about the concern.')
        self.assertEqual(result.actions[0].stage,'Not Taken')

    def test_review_in_progress_or_not_completed_stays_planned(self):
        for text in ('The independent review is in progress.','An independent review has not yet completed.'):
            with self.subTest(text=text):self.assertEqual(self.understand(text).actions[0].stage,'Planned')

    def test_explicit_responsibility_and_work_effect_are_reusable(self):
        source='I recommend the supplier. I have not changed any work in response to pressure.'
        result=self.understand(source)
        self.assertEqual(self.facts(result,'decision_responsibility')[0].value,'I make or recommend the decision')
        self.assertEqual(self.facts(result,'work_changed')[0].value,'No')

    def test_validation_rejects_unanchored_facts_and_fake_verification(self):
        source='The CFO asked for a review.'
        result=UnderstandingResult(
            (CaseActor('user','You'),),
            (CaseFact('f1','user','interest','Shares',excerpt='Invented shares'),
             CaseFact('f2','user','interest','Shares',excerpt=source,status='verified'),
             CaseFact('f3','user','interest','Shares',excerpt=source,source='user')),
        )
        clean=validate_understanding(source,result)
        self.assertFalse(clean.facts)
        self.assertTrue(clean.limitations)

    def test_validation_cannot_confer_review_or_effectiveness(self):
        source='I requested an independent review.'
        result=UnderstandingResult(
            (CaseActor('user','You'),),
            (CaseFact('f','user','context','Reported request',excerpt=source,reviewed=True),),
            (CaseAction('a','Review','independent_review','Implemented',source='scenario',excerpt=source,reviewed=True,checks={'evidence':'Records described','coverage':'All linked circumstances'}),),
        )
        clean=validate_understanding(source,result)
        self.assertFalse(clean.facts[0].reviewed)
        self.assertEqual(clean.actions[0].stage,'Planned')
        self.assertFalse(clean.actions[0].reviewed)
        self.assertNotIn('evidence',clean.actions[0].checks)
        self.assertNotIn('coverage',clean.actions[0].checks)
        self.assertTrue(result.facts[0].reviewed)

    def test_deterministic_results_and_independent_return_objects(self):
        first=self.understand(FULL_INVENTORY); second=self.understand(FULL_INVENTORY)
        self.assertEqual(first,second)
        first.facts[0].value='User correction'
        self.assertNotEqual(first.facts[0].value,second.facts[0].value)

    def test_empty_and_oversized_input_do_not_invent_a_case(self):
        self.assertFalse(self.understand('').facts)
        result=LocalUnderstandingProvider().understand('x'*100001)
        self.assertFalse(result.facts)
        self.assertTrue(result.limitations)
        with self.assertRaises(TypeError):LocalUnderstandingProvider().understand(None)


    def test_property_valuation_preserves_amount_assumptions_responsibility_and_uncertain_link(self):
        scenario = (
            "I am a senior financial analyst reviewing an external valuation of a commercial building before the year-end financial statements are finalised. "
            "The external valuation firm has estimated the property's fair value at £12 million. "
            "However, I noticed that the valuation relies on rental growth assumptions that appear higher than recent market trends. "
            "The investment director has asked me to accept the valuation without further investigation because a lower valuation could affect the company's loan covenant. "
            "I have not yet obtained sufficient supporting evidence to confirm whether the assumptions are reasonable. "
            "I am responsible for reviewing the valuation and reporting my findings to my manager. "
            "I want to understand whether my professional objectivity could be threatened and what actions I should take."
        )
        result = self.understand(scenario)
        responsibility = self.facts(result, 'decision_responsibility')
        self.assertTrue(any(f.value == 'I supervise or review the work' for f in responsibility))
        company_interest = next(f for f in self.facts(result, 'interest')
                                if f.value == 'Organisational financing or loan covenant interest')
        self.assertEqual(company_interest.subject, 'company')
        connection = next(f for f in self.facts(result, 'interest_connection')
                          if f.subject == 'company')
        self.assertEqual(connection.value, 'Unknown')
        self.assertEqual(connection.status, 'unknown')
        claims = self.facts(result, 'claim')
        self.assertTrue(any(f.subject == 'valuation_firm' and '£12 million' in f.value for f in claims))
        self.assertTrue(any(f.subject == 'user' and 'rental growth assumptions' in f.value for f in claims))
        self.assertTrue(any(f.subject == 'user' and 'sufficient supporting evidence' in f.value for f in claims))


if __name__=='__main__':unittest.main()
