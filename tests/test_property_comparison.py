"""Representative property comparison and reusable local-understanding rules.

The property narrative is constructed from the user's regression checklist;
the exact narrative used in the earlier browser test was not supplied.
"""
from copy import deepcopy
import unittest

from objectivity.case_actions import assess_actions
from objectivity.case_reasoning import reason_case
from objectivity.case_report import build_case_report
from objectivity.case_workflow import answer_case_question, review_case, start_case
from objectivity.understanding import LocalUnderstandingProvider


PROPERTY_COMPARISON = (
    "You are a financial accountant reviewing a property valuation prepared by Cedar Valuations. "
    "The investment director asks you to accept the valuation without challenging optimistic rental growth assumptions. "
    "Your promotion depends on approving the valuation. "
    "Our company's refinancing depends on meeting a loan covenant based on the property value. "
    "Your brother works for Cedar Valuations. You do not know whether he participated in the valuation. "
    "The investment director claims the rental growth assumptions are reasonable, but supporting evidence has not been provided."
)

PARAPHRASED_FINANCE = (
    "I am a financial analyst assessing a collateral estimate prepared by an external valuation firm. "
    "The funding director tells me not to question the assumptions. "
    "My continued employment is conditional on approving the estimate. "
    "The company's borrowing is tied to the collateral value. "
    "My brother is employed by an external valuation firm. It is unclear whether he was involved in that estimate. "
    "The funding director states that the expected rental growth is realistic."
)


class PropertyComparisonTests(unittest.TestCase):
    def source(self, scenario):
        result = LocalUnderstandingProvider().understand(scenario)
        for fact in result.facts:
            self.assertIn(fact.excerpt, scenario)
            self.assertFalse(fact.reviewed)
            self.assertEqual(fact.source, 'scenario')
        return result

    def facts(self, result, predicate):
        return [item for item in result.facts if item.predicate == predicate]

    def test_representative_property_case_keeps_all_relevant_distinct_sources(self):
        result = self.source(PROPERTY_COMPARISON)
        actors = {a.id: a for a in result.actors}
        pressure = self.facts(result, 'pressure')
        self.assertEqual(len(pressure), 1)
        self.assertEqual(actors[pressure[0].subject].label.lower(), 'investment director')
        self.assertIn('without challenging', pressure[0].value)
        interests = self.facts(result, 'interest')
        career = next(item for item in interests if 'career' in item.value)
        financing = next(item for item in interests if 'financing' in item.value)
        self.assertEqual(career.subject, 'user')
        self.assertNotEqual(financing.subject, 'user')
        self.assertEqual(actors[financing.subject].kind, 'organisation')
        self.assertEqual(len(interests), 2)
        self.assertTrue(any('loan covenant' in item.excerpt for item in interests))

    def test_brother_employment_and_explicit_unknown_do_not_invent_participation(self):
        result = self.source(PROPERTY_COMPARISON)
        relationship = self.facts(result, 'family_relationship')[0]
        employment = self.facts(result, 'employment')[0]
        participation = self.facts(result, 'participation')[0]
        self.assertEqual(relationship.object_id, 'family_brother')
        self.assertEqual(employment.subject, relationship.object_id)
        self.assertEqual(participation.object_id, employment.object_id)
        self.assertEqual((participation.value, participation.status), ('Unknown', 'unknown'))
        self.assertFalse(self.facts(result, 'close_relationship'))

    def test_technical_valuation_assumption_remains_an_attributed_unverified_claim(self):
        result = self.source(PROPERTY_COMPARISON)
        claim = self.facts(result, 'claim')[0]
        actor = next(a for a in result.actors if a.id == claim.subject)
        self.assertEqual(actor.label.lower(), 'investment director')
        self.assertIn('assumptions are reasonable', claim.value)
        self.assertIn('supporting evidence has not been provided', claim.value)
        self.assertEqual(claim.status, 'reported')
        self.assertEqual(claim.attribution, claim.subject)
        self.assertFalse(self.facts(result, 'self_review'))
        self.assertFalse(self.facts(result, 'advocacy'))

    def test_paraphrased_finance_case_uses_the_same_rules(self):
        result = self.source(PARAPHRASED_FINANCE)
        self.assertEqual({f.subject for f in self.facts(result, 'interest')}, {'user', 'company'})
        self.assertTrue(any(a.label.lower() == 'funding director' for a in result.actors))
        self.assertEqual(self.facts(result, 'participation')[0].status, 'unknown')
        self.assertTrue(self.facts(result, 'pressure'))
        self.assertTrue(self.facts(result, 'claim'))

    def test_unseen_grants_context_keeps_career_and_organisation_interests_separate(self):
        source = (
            'I compare restoration grant proposals. The grants director tells me not to question the forecast. '
            'My promotion depends on recommending one proposal. Our company funding renewal depends on the recommendation.'
        )
        result = self.source(source)
        self.assertEqual({f.subject for f in self.facts(result, 'interest')}, {'user', 'company'})
        self.assertTrue(any(a.label.lower() == 'grants director' for a in result.actors))
        self.assertTrue(self.facts(result, 'pressure'))
        self.assertFalse(self.facts(result, 'family_relationship'))

    def test_quoted_counterpart_promotion_is_not_assigned_to_user(self):
        result = self.source('The investment director says, "My promotion depends on approving the estimate."')
        interest = self.facts(result, 'interest')[0]
        self.assertNotEqual(interest.subject, 'user')
        self.assertIn('investment director', next(a.label for a in result.actors if a.id == interest.subject).lower())

    def test_uncertain_career_connection_stays_unknown(self):
        result = self.source('My promotion might depend on approving the estimate.')
        self.assertEqual(self.facts(result, 'interest')[0].subject, 'user')
        self.assertEqual((self.facts(result, 'interest_connection')[0].value,
                          self.facts(result, 'interest_connection')[0].status), ('Unknown', 'unknown'))

    def test_negated_or_unspecified_promotion_link_is_not_invented(self):
        for source in (
            'My promotion does not depend on approving the estimate.',
            'My promotion is unrelated to the estimate.',
            'My promotion may be affected, but no financial benefit is stated.',
            'Suppose my promotion depends on accepting an estimate.',
        ):
            with self.subTest(source=source):
                self.assertFalse(self.facts(self.source(source), 'interest'))

    def test_financing_connection_can_be_explicitly_unrelated_or_uncertain(self):
        for source, value, status in (
            ('Our company refinancing does not depend on the estimate.', 'No', 'reported'),
            ('Our company refinancing may depend on the estimate.', 'Unknown', 'unknown'),
        ):
            with self.subTest(source=source):
                result = self.source(source)
                self.assertEqual(self.facts(result, 'interest')[0].subject, 'company')
                link = self.facts(result, 'interest_connection')[0]
                self.assertEqual((link.value, link.status), (value, status))

    def test_financing_without_a_stated_beneficiary_does_not_invent_user_or_company_interest(self):
        result = self.source('A loan covenant may be relevant to the estimate.')
        self.assertFalse(self.facts(result, 'interest'))

    def test_ordinary_and_protective_requests_do_not_become_pressure(self):
        for source in (
            'The investment director asks me to assess the assumptions.',
            'The funding director asks me to question the assumptions.',
            'The investment director asks me not to accept the estimate without challenging the assumptions.',
        ):
            with self.subTest(source=source):
                self.assertFalse(self.facts(self.source(source), 'pressure'))

    def test_assumptions_alone_are_not_a_technical_error_or_objectivity_threat(self):
        case = start_case('I am a financial analyst assessing a property valuation. The report assumes rental growth of 8 percent.')
        self.assertTrue(any(f.predicate == 'claim' for f in case.facts))
        self.assertFalse(reason_case(case).threats)
        report = build_case_report(case).lower()
        self.assertNotIn('valuation is wrong', report)
        self.assertNotIn('valuation is misstated', report)
        self.assertIn('reported claim', report)

    def test_paraphrased_technical_claim_and_denial_keep_their_source_meaning(self):
        result = self.source('The investment director says the rental growth assumption is reasonable.')
        claim = self.facts(result, 'claim')[0]
        self.assertEqual(claim.subject, claim.attribution)
        self.assertIn('says the rental growth assumption is reasonable', claim.value)
        denied = self.source('The investment director did not say the rental growth assumption is reasonable.')
        self.assertFalse(self.facts(denied, 'claim'))

    def test_participation_unknown_is_scoped_to_the_relative_in_its_clause(self):
        source = (
            'My sister works for Pine Valuations. '
            'I do not know whether my sister participated in the valuation, but my brother works for Cedar Valuations.'
        )
        result = self.source(source)
        participation = self.facts(result, 'participation')
        self.assertEqual([(f.subject, f.value) for f in participation], [('family_sister', 'Unknown')])
        case = start_case('I review the property valuation. ' + source)
        pending = [q for q in reason_case(case).questions if q.predicate == 'participation']
        self.assertEqual([q.subject for q in pending], ['family_brother'])

    def test_unrelated_technical_uncertainty_does_not_change_known_personal_participation(self):
        source = (
            'My brother works for Cedar Valuations. '
            'I am unsure about the rental assumptions, but my brother prepared the valuation.'
        )
        result = self.source(source)
        participation = self.facts(result, 'participation')
        self.assertEqual([(f.subject, f.value, f.status) for f in participation], [('family_brother', 'Yes', 'reported')])

    def test_employer_work_does_not_establish_relative_participation(self):
        for detail in (
            "The assumptions are unknown, and my brother's firm prepared the valuation.",
            'My brother works for Cedar Valuations which prepared the valuation; the rental assumptions are unknown.',
        ):
            source = 'My brother works for Cedar Valuations. ' + detail
            with self.subTest(detail=detail):
                self.assertFalse(self.facts(self.source(source), 'participation'))

    def test_single_employer_pronoun_unknown_still_closes_only_its_own_question(self):
        result = self.source('My brother works for Cedar Valuations. I do not know whether he participated in the valuation.')
        self.assertEqual([(f.subject, f.value) for f in self.facts(result, 'participation')], [('family_brother', 'Unknown')])

    def test_undecided_safeguard_menu_is_not_an_action_record(self):
        scenario = (
            'I review the property valuation prepared by Cedar Valuations. '
            'I need to decide whether to approve the valuation as presented, '
            'request further supporting evidence and challenge the assumptions, '
            'or disclose the relevant interests and arrange an independent review of the valuation.'
        )
        case = start_case(scenario)
        self.assertEqual(case.actions, [])
        self.assertIn('valuation', case.scenario)

    def test_genuine_planned_independent_review_is_still_recorded(self):
        scenario = (
            'I review a property valuation. '
            'I plan to arrange an independent review of the valuation.'
        )
        case = start_case(scenario)
        self.assertEqual(len(case.actions), 1)
        self.assertEqual(case.actions[0].kind, 'independent_review')
        self.assertEqual(case.actions[0].stage, 'Planned')

    def test_comparison_journey_does_not_repeat_supplied_unknown_or_ask_technical_valuation_questions(self):
        case = start_case(PROPERTY_COMPARISON)
        review_case(case)
        snapshot = reason_case(case)
        self.assertEqual({t.kind for t in snapshot.threats}, {'Self-interest', 'Familiarity', 'Intimidation'})
        self.assertEqual(len([t for t in snapshot.threats if t.kind == 'Self-interest']), 2)
        self.assertFalse(any(q.predicate in {'participation', 'decision_responsibility'} for q in snapshot.questions))
        asked = []
        for _ in range(10):
            questions = reason_case(case).questions
            if not questions:
                break
            question = questions[0]
            self.assertNotIn(question.id, asked)
            asked.append(question.id)
            answer_case_question(case, question.id, 'Unknown')
        else:
            self.fail('Explicit Unknown answers must not repeat equivalent questions')
        self.assertFalse(reason_case(case).questions)
        before = deepcopy(case)
        addressed = assess_actions(case)
        report = build_case_report(case)
        self.assertEqual(case, before)
        self.assertIn('Cedar Valuations', report)
        self.assertIn('loan covenant', report)
        self.assertIn('promotion', report.lower())
        self.assertIn('unknown', report.lower())
        self.assertIn('investment director: The investment director claims', report)
        self.assertFalse(all(item.status.startswith('Threat adequately addressed') for item in addressed.outcomes))


if __name__ == '__main__':
    unittest.main()
