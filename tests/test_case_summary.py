"""Compact source summaries remain editable projections, not ethical verdicts."""
from copy import deepcopy
import unittest

from objectivity.case_model import CaseActor, CaseFact, CaseState, ReasoningSnapshot
from objectivity.case_summary import summarise_case
from objectivity.case_workflow import edit_case_fact, start_case
from objectivity.examples import EXAMPLE_SCENARIO
from tests.test_understanding import FULL_INVENTORY, PROCUREMENT, PROPERTY


TITLES = (
    "Professional role and decision", "People and relationships",
    "Financial, commercial and career interests", "Reported pressure or influence",
    "Material uncertainties", "Actions already mentioned",
)


def section(case, title, snapshot=None):
    return next(item for item in summarise_case(case, snapshot) if item.title == title)


def words(case):
    return "\n".join(item for part in summarise_case(case) for item in part.items)


class CaseSummaryTests(unittest.TestCase):
    def test_exact_six_sections_without_mutating_the_case(self):
        case = start_case(EXAMPLE_SCENARIO)
        before = deepcopy(case)
        summary = summarise_case(case)
        self.assertEqual(tuple(item.title for item in summary), TITLES)
        self.assertEqual(case, before)
        self.assertTrue(all(isinstance(item.items, tuple) and item.items for item in summary))

    def test_cfo_summary_reuses_professional_context_without_repeating_the_scenario(self):
        case = start_case(EXAMPLE_SCENARIO)
        text = words(case)
        self.assertIn("Audit manager", text)
        self.assertIn("revenue recognition", text)
        self.assertIn("Close personal friendship", text)
        self.assertIn("Your firm", text)
        self.assertIn("'go easy'", text)
        self.assertNotIn(EXAMPLE_SCENARIO, text)
        self.assertNotIn("Source account:", text)
        self.assertNotRegex(text, r"\b(?:fact|answer|question)[_-][a-f0-9]+")

    def test_explicit_external_firm_apposition_deduplicates_only_display_parties(self):
        scenario = (
            'I review a property valuation prepared by an external valuation firm, Cedar Valuations. '
            'My brother works for Cedar Valuations. '
            'The valuation relies on an estimated property value.'
        )
        case = start_case(scenario)
        original = deepcopy(case)
        people = " ".join(section(case, TITLES[1]).items)
        self.assertIn('Cedar Valuations', people)
        self.assertNotIn('External valuation firm;', people)
        self.assertNotIn('Reported claimant', people)
        self.assertEqual(case, original)

    def test_separate_provider_or_unlinked_generic_is_not_hidden(self):
        scenario = (
            'I review a valuation prepared by an external valuation firm. '
            'My brother works for Cedar Valuations.'
        )
        case = start_case(scenario)
        people = " ".join(section(case, TITLES[1]).items)
        self.assertIn('External valuation firm', people)
        self.assertIn('Cedar Valuations', people)

    def test_two_explicitly_different_firms_are_not_conflated(self):
        scenario = (
            'I review a valuation prepared by an external valuation firm, Oak Valuations, '
            'and another report from an independent valuation firm, Cedar Valuations. '
            'My brother works for Cedar Valuations.'
        )
        case = start_case(scenario)
        people = " ".join(section(case, TITLES[1]).items)
        self.assertIn('Oak Valuations', people)
        self.assertIn('Cedar Valuations', people)
        self.assertTrue(any(a.label == 'External valuation firm' for a in case.actors))

    def test_inventory_keeps_actual_beneficiaries_pressure_recipient_and_claim_uncertainty(self):
        case = start_case(FULL_INVENTORY)
        interests = " ".join(section(case, TITLES[2]).items)
        self.assertIn("You: Bonus or performance-related pay", interests)
        self.assertIn("Manufacturing company: Organisational profit target", interests)
        people = " ".join(section(case, TITLES[1]).items)
        self.assertIn("auditors", people)
        pressure = " ".join(section(case, TITLES[3]).items)
        self.assertIn("delay recognising", pressure)
        self.assertIn("not to raise", pressure)
        uncertainty = section(case, TITLES[4])
        self.assertTrue(uncertainty.uncertain)
        self.assertIn("claim remains unverified", " ".join(uncertainty.items))
        self.assertIn("may recover", " ".join(uncertainty.items))

    def test_unfamiliar_procurement_does_not_invent_role_ownership_or_closeness(self):
        case = start_case(PROCUREMENT)
        summary = summarise_case(case)
        context = " ".join(summary[0].items)
        self.assertIn("role not yet established", context)
        interests = " ".join(summary[2].items)
        self.assertIn("Your sister: Shareholding", interests)
        self.assertIn("procurement director: Consulting", interests)
        self.assertIn("promotion", interests)
        self.assertNotIn("You: Shareholding", interests)
        self.assertNotIn("You: Consulting", interests)
        self.assertNotIn("close", " ".join(summary[1].items).lower())

    def test_missing_information_is_highlighted_without_claiming_negative_facts(self):
        case = start_case("An uncomfortable situation concerns me.")
        summary = summarise_case(case)
        self.assertTrue(summary[0].uncertain)
        self.assertTrue(summary[4].uncertain)
        self.assertIn("does not establish that none exists", " ".join(summary[2].items))
        self.assertIn("does not establish that none have been taken", " ".join(summary[5].items))
        self.assertNotIn("No threats", words(case))

    def test_unknown_participation_is_explicit_without_inventing_involvement(self):
        case = start_case(PROPERTY)
        unknowns = section(case, TITLES[4])
        self.assertTrue(unknowns.uncertain)
        self.assertIn("Participation in the relevant work", " ".join(unknowns.items))
        self.assertIn("Your sister", " ".join(unknowns.items))
        self.assertIn("remains unknown", " ".join(unknowns.items))
        self.assertNotIn("prepared the valuation", " ".join(section(case, TITLES[1]).items))

    def test_disputed_and_denied_facts_remain_qualified_and_withdrawn_fact_is_absent(self):
        case = CaseState("A reported case.", actors=[CaseActor('user', 'You'), CaseActor('manager', 'Manager')], facts=[
            CaseFact('interest', 'user', 'interest', 'Performance bonus', source='user', status='denied'),
            CaseFact('pressure', 'manager', 'pressure', 'Requested a favourable recommendation', source='user', status='disputed'),
            CaseFact('old', 'user', 'interest', 'Old ownership description', source='user', status='withdrawn'),
        ])
        summary = summarise_case(case, ReasoningSnapshot((), (), ()))
        self.assertIn("Performance bonus (explicitly denied)", " ".join(summary[2].items))
        self.assertIn("disputed account", " ".join(summary[3].items))
        self.assertTrue(summary[3].uncertain)
        self.assertNotIn("Old ownership description", " ".join(item for part in summary for item in part.items))

    def test_source_correction_is_immediately_reflected_and_old_value_stays_in_history_only(self):
        case = start_case(FULL_INVENTORY)
        bonus = next(fact for fact in case.facts if fact.predicate == 'interest' and fact.subject == 'user')
        edit_case_fact(case, bonus.id, 'No personal bonus applies', 'denied')
        summary = section(case, TITLES[2])
        text = " ".join(summary.items)
        self.assertIn("No personal bonus applies (explicitly denied)", text)
        self.assertNotIn("Bonus or performance-related pay", text)
        self.assertTrue(case.fact_history)

    def test_compacting_pressure_does_not_remove_negation_uncertainty_or_attribution(self):
        for detail in (
            'The manager has not asked for a change.',
            'It is unclear whether the manager asked for a change.',
            'The manager claims another person asked for a change.',
            'The manager denies having asked for a change.',
        ):
            with self.subTest(detail=detail):
                case = CaseState('A reported case.', actors=[CaseActor('user', 'You'), CaseActor('manager', 'Manager')], facts=[
                    CaseFact('pressure', 'manager', 'pressure', detail, source='user'),
                ])
                text = " ".join(section(case, TITLES[3], ReasoningSnapshot((), (), ())).items)
                for qualifier in ('not', 'unclear', 'claims', 'denies'):
                    if qualifier in detail:
                        self.assertIn(qualifier, text)

    def test_action_summary_keeps_planned_implemented_and_effectiveness_separate(self):
        planned = start_case('I have requested an independent review of the inventory estimate.')
        implemented = start_case('An independent partner completed a review of the inventory estimate.')
        self.assertIn('planned or requested; not completed', " ".join(section(planned, TITLES[5]).items))
        text = " ".join(section(implemented, TITLES[5]).items)
        self.assertIn('implemented according to the account', text)
        self.assertIn('effectiveness requires assessment', text)
        self.assertNotIn('Effectiveness Established', text)

    def test_large_cases_remain_bounded_with_an_explicit_detail_notice(self):
        case = CaseState('A long case.', actors=[CaseActor('user', 'You')], facts=[
            CaseFact(f'interest-{number}', 'user', 'interest', f'Interest {number}: ' + 'long detail ' * 100, source='user')
            for number in range(12)
        ])
        summary = summarise_case(case, ReasoningSnapshot((), (), ()))
        self.assertTrue(all(len(part.items) <= 5 for part in summary))
        self.assertTrue(all(len(item) <= 240 for part in summary for item in part.items))
        self.assertIn('further reported details', summary[2].items[-1])

    def test_a_provided_snapshot_does_not_trigger_additional_reasoning(self):
        from unittest.mock import patch
        case = CaseState('A situation.', actors=[CaseActor('user', 'You')])
        with patch('objectivity.case_reasoning.reason_case', side_effect=AssertionError('Should reuse the supplied snapshot')):
            self.assertEqual(len(summarise_case(case, ReasoningSnapshot((), (), ()))), 6)


if __name__ == '__main__':
    unittest.main()
