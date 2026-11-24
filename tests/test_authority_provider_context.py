"""Step 1 authority boundaries, valuation providers and response wording."""
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from objectivity.address import AddressState
from objectivity.ai_provider import AIConfig
from objectivity.ai_understanding import AIUnderstandingError, parse_ai_understanding
from objectivity.case_model import CaseFact
from objectivity.case_reasoning import reason_case
from objectivity.case_summary import summarise_case
from objectivity.case_workflow import edit_case_fact, review_case, start_case
from objectivity.models import Assessment
from objectivity.progress import export_progress, import_progress
from objectivity.review import ReviewState
from tests.test_ai_understanding import actor, fact, proposal
from tests.test_understanding import PROPERTY


SCENARIO = (
    "Role: Risk and compliance analyst.\n\n"
    "Decision: Reviewing an external valuation of our company's commercial property before the year-end financial statements are finalised.\n\n"
    "I am responsible for reviewing the valuation. The investment director has asked me to accept the valuation without further investigation "
    "because a lower valuation could affect the company's loan covenant. I do not have final approval authority."
)
LIMIT = 'I do not have final approval authority.'
EMPTY_ACTIONS = 'No steps to address the Objectivity concern were mentioned; this does not establish that none have been taken.'
APP = Path(__file__).resolve().parents[1] / 'app.py'


def facts(case, predicate):
    return [f for f in case.facts if f.predicate == predicate and f.status != 'withdrawn']


def section(case, title):
    return next(s for s in summarise_case(case) if s.title == title)


class AuthorityContextTests(unittest.TestCase):
    def test_exact_scenario_keeps_review_and_source_linked_approval_limit(self):
        case = start_case(SCENARIO)
        context = next(f for f in facts(case, 'context') if LIMIT.rstrip('.') in f.value)
        self.assertEqual((context.subject, context.source, context.status, context.reviewed), ('user', 'scenario', 'reported', False))
        self.assertIn(context.excerpt, SCENARIO)
        self.assertIn(LIMIT.rstrip('.'), context.excerpt)
        self.assertEqual(context.attribution, 'You')
        self.assertEqual([f.value for f in facts(case, 'decision_responsibility')], ['I supervise or review the work'])
        self.assertIn('final approval authority', ' '.join(section(case, 'Professional role and decision').items))
        self.assertEqual({q.predicate for q in reason_case(case).questions}, {'work_changed'})

    def test_recommendation_permission_is_separate_from_final_approval(self):
        case = start_case('I review a property valuation. I can only recommend adjustments.')
        notes = facts(case, 'context')
        self.assertTrue(any('I can only recommend adjustments' in f.value for f in notes))
        self.assertFalse(any('final approval' in f.value.casefold() for f in notes))
        self.assertEqual([f.value for f in facts(case, 'decision_responsibility')], ['I supervise or review the work'])

    def test_explicit_final_approval_authority_remains_reported(self):
        case = start_case('I have final approval authority for the valuation.')
        note, = facts(case, 'context')
        self.assertIn('I have final approval authority', note.value)
        self.assertEqual((note.status, note.reviewed), ('reported', False))

    def test_explicit_absence_of_approval_authority_is_retained(self):
        for source in (
            LIMIT, 'I have no final approval authority.',
            'I do not have authority to approve the valuation.',
            'I cannot approve the final valuation.',
            'I am not authorised to give final approval.',
        ):
            with self.subTest(source=source):
                case = start_case('I review a property valuation. ' + source)
                self.assertTrue(facts(case, 'context'))
                self.assertEqual([f.value for f in facts(case, 'decision_responsibility')], ['I supervise or review the work'])
                self.assertIn(source.rstrip('.'), ' '.join(section(case, 'Professional role and decision').items))

    def test_no_final_approval_responsibility_does_not_erase_review_work(self):
        case = start_case(SCENARIO.replace(LIMIT, 'I have no responsibility for final approval.'))
        self.assertEqual([f.value for f in facts(case, 'decision_responsibility')], ['I supervise or review the work'])
        self.assertTrue(any('no responsibility for final approval' in f.value for f in facts(case, 'context')))
        self.assertEqual({q.predicate for q in reason_case(case).questions}, {'work_changed'})

    def test_genuine_absence_of_involvement_is_still_recorded(self):
        case = start_case('I have no involvement in this decision. The CFO has final approval authority.')
        self.assertEqual([f.value for f in facts(case, 'decision_responsibility')], ['I have no involvement in this decision'])

    def test_third_party_authority_is_not_assigned_to_user(self):
        case = start_case('I review a property valuation. The investment director has final approval authority.')
        approval, = [f for f in facts(case, 'context') if 'approval' in f.value]
        self.assertNotEqual(approval.subject, 'user')
        self.assertEqual(approval.attribution.casefold(), 'investment director')
        self.assertEqual([f.value for f in facts(case, 'decision_responsibility')], ['I supervise or review the work'])

    def test_quoted_first_person_authority_belongs_to_the_named_speaker(self):
        case = start_case('I review a property valuation. The CFO says, "I do not have final approval authority."')
        note, = [f for f in facts(case, 'context') if 'approval' in f.value]
        self.assertEqual((note.subject, note.attribution), ('cfo', 'CFO'))
        self.assertIn('The CFO says', note.excerpt)

    def test_uncertain_or_hypothetical_authority_is_not_promoted(self):
        for source in ('Suppose I have final approval authority.', 'I do not know whether I have final approval authority.', 'The CFO says, "I might have final approval authority."'):
            with self.subTest(source=source):
                self.assertFalse(facts(start_case(source), 'context'))

    def test_questions_requests_and_denials_do_not_assert_user_authority(self):
        for source in (
            'I have asked the CFO who has final approval authority.',
            'I have asked whether I have final approval authority.',
            'The CFO denies that I have final approval authority.',
            'The CFO asks, "Do I have final approval authority?"',
        ):
            with self.subTest(source=source):
                self.assertFalse(facts(start_case(source), 'context'))

    def test_job_title_alone_does_not_supply_an_authority_note(self):
        self.assertFalse(facts(start_case('Role: Finance director\nDecision: Reviewing a property valuation.'), 'context'))

    def test_material_restriction_is_visible_despite_summary_limits(self):
        case = start_case(SCENARIO)
        case.facts[:0] = [CaseFact(f'additional-{i}', 'user', 'context', f'Additional context {i}', source='user') for i in range(10)]
        part = section(case, 'Professional role and decision')
        self.assertIn('I do not have final approval authority', ' '.join(part.items))
        self.assertLessEqual(len(part.items), 5)
        self.assertTrue(all(len(item) <= 240 for item in part.items))

    def test_disputed_or_unknown_authority_is_not_presented_as_established(self):
        for status in ('unknown', 'disputed', 'denied'):
            with self.subTest(status=status):
                case = start_case(SCENARIO)
                note = next(f for f in facts(case, 'context') if 'final approval authority' in f.value)
                edit_case_fact(case, note.id, note.value, status)
                text = ' '.join(section(case, 'Professional role and decision').items)
                self.assertNotIn('explicitly not held (reported)', text)
                self.assertIn({'unknown': 'uncertain', 'disputed': 'disputed account', 'denied': 'explicitly denied'}[status], text)

    def test_multiple_material_restrictions_are_not_hidden_by_the_item_cap(self):
        case = start_case(SCENARIO)
        case.facts.extend(CaseFact(f'limit-{i}', 'user', 'context', f'I have no final approval authority for activity {i}', source='user') for i in range(6))
        text = ' '.join(section(case, 'Professional role and decision').items)
        for i in range(6):
            self.assertIn(f'activity {i}', text)

    def test_edit_and_json_progress_round_trip_preserve_authority_evidence(self):
        case = start_case(SCENARIO)
        note = next(f for f in facts(case, 'context') if 'final approval authority' in f.value)
        review_case(case)
        payload = export_progress(Assessment(scenario=case.scenario, case_state=case), ReviewState(), AddressState(), 'identify')
        restored = import_progress(payload).assessment.case_state
        kept = next(f for f in restored.facts if f.id == note.id)
        self.assertEqual((kept.value, kept.excerpt, kept.attribution, kept.status), (note.value, note.excerpt, 'You', 'reported'))
        edit_case_fact(restored, kept.id, 'I now have final approval authority.')
        self.assertTrue(any(f.id == note.id and f.value == note.value for f in restored.fact_history))
        self.assertIn('I now have final approval authority', ' '.join(section(restored, 'Professional role and decision').items))
        self.assertFalse(restored.reviewed)


class ValuationProviderTests(unittest.TestCase):
    def test_bare_external_valuation_does_not_create_a_provider_or_owner_link(self):
        case = start_case(SCENARIO)
        self.assertFalse(facts(case, 'professional_relationship'))
        self.assertFalse(any(a.id == 'valuation_firm' for a in case.actors))
        self.assertIn('Valuation provider not identified in the account.', section(case, 'People and relationships').items)

    def test_named_provider_is_separate_from_the_property_owner(self):
        for source in (
            "I review a valuation prepared by Cedar Valuations for our company's property.",
            "I review our company's property valuation prepared by Cedar Valuations.",
        ):
            with self.subTest(source=source):
                case = start_case(source)
                link, = facts(case, 'professional_relationship')
                provider = next(a for a in case.actors if a.id == link.object_id)
                self.assertEqual(provider.label, 'Cedar Valuations')
                self.assertNotEqual(provider.id, 'company')
                self.assertNotIn('Valuation provider not identified in the account.', section(case, 'People and relationships').items)

    def test_explicitly_identified_unnamed_provider_is_preserved(self):
        case = start_case('I review a property valuation prepared by an external valuation firm.')
        link, = facts(case, 'professional_relationship')
        self.assertEqual(link.object_id, 'valuation_firm')
        self.assertEqual(next(a.label for a in case.actors if a.id == link.object_id), 'External valuation firm')
        self.assertFalse(case.actions)

    def test_unidentified_provider_is_not_replaced_by_an_invented_firm(self):
        case = start_case('Decision: Reviewing an external property valuation. The provider is not identified.')
        self.assertFalse(facts(case, 'professional_relationship'))
        self.assertIn('Valuation provider not identified in the account.', section(case, 'People and relationships').items)

    def test_organisation_can_be_a_provider_when_explicitly_stated(self):
        case = start_case('I review a property valuation prepared by our company.')
        self.assertEqual([f.object_id for f in facts(case, 'professional_relationship')], ['company'])

    def test_existing_provider_and_family_relationships_are_preserved(self):
        case = start_case(PROPERTY)
        employer = facts(case, 'employment')[0].object_id
        self.assertEqual(facts(case, 'professional_relationship')[0].object_id, employer)
        self.assertEqual(facts(case, 'participation')[0].status, 'unknown')
        self.assertIn('Familiarity', {t.kind for t in reason_case(case).threats})

    def test_another_persons_review_is_not_a_user_provider_work_link(self):
        case = start_case('The CFO reviews a property valuation prepared by Cedar Valuations.')
        self.assertFalse(facts(case, 'professional_relationship'))

    def test_negated_and_denied_provider_work_is_not_affirmed(self):
        for source in (
            'I review a valuation not prepared by Cedar Valuations.',
            'I review a valuation that is not a valuation from Cedar Valuations.',
            'I review a valuation; the CFO denies that Cedar Valuations prepared it.',
        ):
            with self.subTest(source=source):
                self.assertFalse(facts(start_case(source), 'professional_relationship'))

    def test_a_property_owner_preparing_a_different_document_is_not_the_valuer(self):
        case = start_case("I review an external valuation of our company's property using a schedule prepared by our company.")
        self.assertFalse(facts(case, 'professional_relationship'))
        self.assertIn('Valuation provider not identified in the account.', section(case, 'People and relationships').items)

    def test_provider_relationship_correction_is_not_undone_by_summary(self):
        case = start_case('I review a property valuation prepared by Cedar Valuations.')
        link, = facts(case, 'professional_relationship')
        edit_case_fact(case, link.id, 'The provider connection is withdrawn.', 'withdrawn')
        self.assertIn('Valuation provider not identified in the account.', section(case, 'People and relationships').items)


class OptionalAIProviderTests(unittest.TestCase):
    def test_document_as_organisation_proposals_are_rejected(self):
        for label in ('external valuation', 'property valuation', 'valuation report'):
            source = f'I review an {label} of our company property.'
            with self.subTest(label=label), self.assertRaises(AIUnderstandingError):
                parse_ai_understanding(source, proposal(actors=[actor(label, source, kind='organisation')]))

    def test_unmentioned_valuation_firm_is_still_rejected(self):
        source = 'I review an external valuation of our company property.'
        with self.assertRaises(AIUnderstandingError):
            parse_ai_understanding(source, proposal(actors=[actor('external valuation firm', source, kind='organisation')]))

    def test_ai_cannot_reintroduce_a_property_owner_as_the_provider(self):
        source = "I review an external valuation of our company's commercial property."
        raw = proposal(fact('user', 'professional_relationship', 'external valuation', source, object='company'))
        with self.assertRaises(AIUnderstandingError):
            parse_ai_understanding(source, raw)

    def test_ai_cannot_assign_another_persons_reviewing_work_to_user(self):
        source = 'I am an accountant; the CFO reviews a valuation prepared by Cedar Valuations.'
        raw = proposal(fact('user', 'professional_relationship', 'valuation', source, object='Cedar Valuations'), actors=[actor('Cedar Valuations', source, kind='organisation')])
        with self.assertRaises(AIUnderstandingError):
            parse_ai_understanding(source, raw)

    def test_named_provider_relationship_proposals_remain_supported(self):
        source = 'I review a property valuation prepared by Cedar Valuations.'
        raw = proposal(fact('user', 'professional_relationship', 'property valuation', source, object='Cedar Valuations'), actors=[actor('Cedar Valuations', source, kind='organisation')])
        result = parse_ai_understanding(source, raw)
        self.assertTrue(facts(result, 'professional_relationship'))

    def test_explicit_unnamed_provider_proposals_remain_supported(self):
        source = 'I review a property valuation prepared by an external valuation firm.'
        result = parse_ai_understanding(source, proposal(actors=[actor('external valuation firm', source, kind='organisation')]))
        self.assertEqual(len([a for a in result.actors if a.id == 'valuation_firm']), 1)

    def test_legitimate_firm_named_external_valuation_is_not_a_document(self):
        source = 'I review a report prepared by a firm called External Valuation.'
        result = parse_ai_understanding(source, proposal(actors=[actor('External Valuation', source, kind='organisation')]))
        self.assertTrue(any(a.label == 'External Valuation' for a in result.actors))


class ResponseSummaryTests(unittest.TestCase):
    def test_pressure_without_a_response_has_the_exact_qualified_empty_state(self):
        case = start_case(SCENARIO)
        self.assertTrue(facts(case, 'pressure'))
        self.assertFalse(case.actions)
        self.assertEqual(section(case, 'Actions already mentioned').items, (EMPTY_ACTIONS,))

    def test_user_response_keeps_attribution(self):
        case = start_case('I have escalated the concern to the audit committee.')
        self.assertEqual(case.actions[0].actor_id, 'user')
        self.assertIn('You:', ' '.join(section(case, 'Actions already mentioned').items))

    def test_other_party_response_keeps_attribution(self):
        case = start_case('An independent partner completed a review of the valuation.')
        self.assertNotEqual(case.actions[0].actor_id, 'user')
        self.assertIn('independent partner:', ' '.join(section(case, 'Actions already mentioned').items).casefold())

    def test_planned_and_implemented_measures_are_not_equated_with_effectiveness(self):
        planned = start_case('I have requested an independent review of the valuation.')
        implemented = start_case('An independent partner completed a review of the valuation.')
        self.assertIn('planned or requested; not completed', ' '.join(section(planned, 'Actions already mentioned').items))
        self.assertIn('effectiveness requires assessment', ' '.join(section(implemented, 'Actions already mentioned').items))


class AuthorityProviderAppTests(unittest.TestCase):
    def test_exact_scenario_is_visible_and_confirmable_with_only_work_effect_pending(self):
        with patch('objectivity.ai_ui.load_config', return_value=AIConfig()), patch('objectivity.progress_ui.browser_storage', return_value=None):
            app = AppTest.from_file(str(APP), default_timeout=15).run()
            next(w for w in app.text_area if w.label == 'Your scenario').input(SCENARIO)
            next(w for w in app.button if w.label == 'Review scenario').click().run()
            self.assertFalse(app.exception)
            text = '\n'.join(item.value for kind in ('markdown', 'caption', 'text', 'warning') for item in getattr(app, kind))
            self.assertIn('I do not have final approval authority', text)
            self.assertIn('Valuation provider not identified in the account.', text)
            self.assertIn(EMPTY_ACTIONS, text)
            next(w for w in app.checkbox if w.label == 'These records reflect my account, including uncertainties.').check()
            next(w for w in app.button if w.label == 'Confirm scenario and continue').click().run()
            self.assertFalse(app.exception)
            case = app.session_state['assessment'].case_state
            self.assertEqual({q.predicate for q in reason_case(case).questions}, {'work_changed'})


if __name__ == '__main__':
    unittest.main()
