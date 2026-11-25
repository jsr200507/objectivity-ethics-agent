"""Exact real-case regression: undecided option must not become an action."""
import unittest

from objectivity.case_workflow import start_case
from objectivity.case_summary import summarise_case
from objectivity.case_questions import plan_questions


CEDAR_CASE = (
    "I am a financial accountant at a property investment company. "
    "I am responsible for reviewing a property valuation prepared by an external valuation firm, Cedar Valuations. "
    "Cedar Valuations has valued one of our investment properties at approximately £18 million. "
    "The valuation relies on relatively optimistic rental growth assumptions, which have a significant impact "
    "on the estimated property value. "
    "However, I have not yet received sufficient supporting market evidence to establish whether these assumptions are reasonable. "
    "Our investment director has asked me to accept the valuation without challenging the optimistic rental growth assumptions. "
    "The company is currently arranging refinancing, and meeting a loan covenant depends on the property value. "
    "A lower valuation could therefore create difficulties for the refinancing process. "
    "There is also a personal career-related interest. "
    "My promotion depends on approving the property valuation, which may influence my willingness to challenge the assumptions. "
    "In addition, my brother works for Cedar Valuations, the external firm that prepared the valuation. "
    "However, I do not know whether he was involved in preparing or reviewing this particular valuation. "
    "His exact role and participation have not been established. "
    "I have been asked to complete my review within three days. "
    "I need to decide whether to approve the valuation as presented, request further supporting evidence "
    "and challenge the assumptions, or disclose the relevant interests and arrange an independent review of the valuation. "
    "I am concerned about whether I can make an objective professional judgment given the combination "
    "of personal interests, organisational financing pressure, family relationships and the investment director's request."
)


class CedarExactFreshCaseRegressionTests(unittest.TestCase):
    def test_new_case_does_not_record_an_undecided_action(self):
        case = start_case(CEDAR_CASE)
        self.assertEqual(case.actions, [])
        summary = summarise_case(case)
        actions = next(part for part in summary if part.title == 'Actions already mentioned')
        self.assertIn('No steps to address', ' '.join(actions.items))

    def test_original_case_keeps_explicit_employment_and_promotion(self):
        case = start_case(CEDAR_CASE)
        interests = [f for f in case.facts if f.predicate == 'interest']
        self.assertTrue(any(f.subject == 'user' and 'Promotion' in f.value for f in interests))
        employment = [f for f in case.facts if f.predicate == 'employment']
        self.assertTrue(any(f.subject == 'family_brother' for f in employment))
        people = next(s for s in summarise_case(case) if s.title == 'People and relationships')
        details = ' '.join(people.items)
        self.assertIn('Your brother at Cedar Valuations', details)
        parties = details.split('Relevant parties: ', 1)[-1].split('You with', 1)[0]
        self.assertNotIn('; External valuation firm;', parties)

    def test_original_case_does_not_repeat_unattributed_claim_label(self):
        case = start_case(CEDAR_CASE)
        uncertainties = next(s for s in summarise_case(case) if s.title == 'Material uncertainties')
        details = ' '.join(uncertainties.items)
        self.assertNotIn('Unattributed reported claim remains unverified: Unattributed reported claim', details)

    def test_new_case_retains_career_and_familiarity_questions(self):
        case = start_case(CEDAR_CASE)
        asked = {q.predicate for q in plan_questions(case).questions}
        self.assertIn('career_incentive_basis', asked)
        self.assertIn('familiarity_contact', asked)


if __name__ == '__main__':
    unittest.main()
