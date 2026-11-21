"""Explicit source suggestions, uncertainty and no invented ethical facts."""

import unittest

from objectivity.examples import EXAMPLE_SCENARIO
from objectivity.extraction import MAX_SCENARIO_LENGTH, extract_context
from objectivity.models import DEFAULT_BASIS


INVENTORY = (
    "I am a financial accountant at a manufacturing company. "
    "My finance director has asked me to avoid an inventory write-down to meet profit targets."
)


class ExtractionTests(unittest.TestCase):
    def test_cfo_example_extracts_only_supported_details(self):
        result = extract_context(EXAMPLE_SCENARIO)
        self.assertEqual(result.context.role, "Audit manager of a listed client")
        self.assertIn("CFO", result.context.parties)
        self.assertNotIn("audit team", result.context.parties)
        self.assertNotIn("tax advisory team", result.context.parties)
        self.assertIn("revenue recognition judgement", result.context.decision.lower())
        self.assertEqual(result.context.relationship, "Close personal relationship")
        self.assertIn("close personal friend from university", result.context.relationship_notes)
        self.assertNotIn("not yet confirmed", result.context.relationship_notes)
        self.assertNotIn("verified", result.context.relationship_notes)

    def test_inventory_accountant_and_director_are_not_confused(self):
        result = extract_context(INVENTORY)
        self.assertEqual(result.context.role, "Financial accountant at a manufacturing company")
        self.assertIn("Finance director", result.context.parties)
        self.assertEqual(result.context.decision, "Inventory write-down")
        self.assertEqual(result.context.relationship, "Unknown")

    def test_inventory_verb_phrases_preserve_stated_words_and_modifiers(self):
        for phrase in (
            "write down obsolete inventory", "writing down inventory",
            "write down the damaged inventory", "write-down of obsolete inventory",
        ):
            with self.subTest(phrase=phrase):
                source = f"I am a financial accountant. My finance director told me not to {phrase}."
                result = extract_context(source)
                self.assertIn("inventory", result.context.decision.lower())
                self.assertIn(phrase, result.evidence['decision'])

    def test_generic_counterpart_roles_are_not_upgraded_to_financial_titles(self):
        for title in ("manager", "supervisor", "director"):
            with self.subTest(title=title):
                context = extract_context(f"I am a financial accountant. My {title} asks about inventory valuation.").context
                self.assertIn(title, context.parties.lower())
                self.assertNotIn("finance " + title, context.parties.lower())

    def test_clear_name_and_role_apposition_preserves_literal_wording(self):
        for phrase in ("Jane, the CFO", "CFO Jane", "Jane Smith, the finance director"):
            with self.subTest(phrase=phrase):
                source = f"I am an auditor. {phrase} asked me about revenue recognition."
                result = extract_context(source)
                self.assertIn(phrase, result.context.parties)
                self.assertIn(phrase, result.evidence['parties'])

    def test_connective_before_role_is_not_invented_as_a_person_name(self):
        result = extract_context("I am an auditor. However, the CFO asked me about revenue recognition.")
        self.assertIn("CFO", result.context.parties)
        self.assertNotIn("However", result.context.parties)

    def test_exact_evidence_is_present_in_original_source(self):
        for scenario in (EXAMPLE_SCENARIO, INVENTORY):
            for fragments in extract_context(scenario).evidence.values():
                for fragment in fragments:
                    self.assertIn(fragment, scenario)

    def test_extraction_does_not_confirm_or_verify_anything(self):
        result = extract_context(EXAMPLE_SCENARIO)
        self.assertEqual(result.context.basis, DEFAULT_BASIS)
        self.assertEqual(result.context.interests, "Unknown")
        self.assertEqual(result.context.pressure, "Unknown")
        self.assertTrue(any("not independently verified" in text for text in result.limitations))

    def test_missing_details_are_unknown(self):
        context = extract_context("Something concerns me at work.").context
        for field in ("role", "parties", "decision", "relationship"):
            self.assertEqual(getattr(context, field), "Unknown")

    def test_empty_scenario_is_safe(self):
        self.assertEqual(extract_context("").context.role, "Unknown")

    def test_conflicting_user_roles_are_not_guessed(self):
        result = extract_context("I am a financial accountant and I am an audit manager.")
        self.assertEqual(result.context.role, "Unknown")
        self.assertEqual(result.context.parties, "Unknown")
        self.assertTrue(any("More than one" in text for text in result.limitations))

    def test_alternative_user_roles_are_unknown(self):
        for scenario in ("I am an accountant or an auditor.", "I am an accountant and an audit manager."):
            with self.subTest(scenario=scenario):
                self.assertEqual(extract_context(scenario).context.role, "Unknown")
                self.assertEqual(extract_context(scenario).context.parties, "Unknown")

    def test_alternative_self_roles_are_not_recast_as_separate_parties(self):
        result = extract_context("I am an audit manager or a financial accountant. I need to assess an inventory write-down.")
        self.assertEqual(result.context.role, "Unknown")
        self.assertEqual(result.context.parties, "Unknown")
        self.assertEqual(result.context.decision, "Inventory write-down")

    def test_entire_chain_of_alternative_roles_is_excluded_from_parties(self):
        for conjunction in ("or", "and"):
            with self.subTest(conjunction=conjunction):
                scenario = f"I am an accountant {conjunction} an auditor {conjunction} a treasurer."
                result = extract_context(scenario)
                self.assertEqual(result.context.role, "Unknown")
                self.assertEqual(result.context.parties, "Unknown")
                self.assertEqual(result.evidence['parties'], ())

    def test_assistant_to_a_role_is_not_assigned_that_role(self):
        result = extract_context("I am the audit manager's assistant.")
        self.assertEqual(result.context.role, "Unknown")

    def test_repeated_role_with_different_capitalisation_is_not_a_conflict(self):
        result = extract_context("I am a Financial Accountant. My role is financial accountant.")
        self.assertEqual(result.context.role, "Financial accountant")

    def test_competing_professional_decisions_are_unknown(self):
        result = extract_context("I am an auditor. The issue concerns revenue recognition and inventory write-down.")
        self.assertEqual(result.context.decision, "Unknown")

    def test_role_negation_does_not_turn_counterpart_into_user(self):
        result = extract_context("I am not an audit manager. My CFO wants an audit opinion.")
        self.assertEqual(result.context.role, "Unknown")
        self.assertNotIn("Audit manager", result.context.parties)
        self.assertIn("CFO", result.context.parties)

    def test_explicit_role_after_negated_role(self):
        result = extract_context("I am not an auditor; I work as a financial accountant.")
        self.assertEqual(result.context.role, "Financial accountant")

    def test_smart_apostrophes_and_first_person_variants(self):
        for text in ("I'm a financial accountant.", "I’m a financial accountant.", "My role is financial accountant.", "As a financial accountant, I review inventory valuation."):
            with self.subTest(text=text):
                self.assertEqual(extract_context(text).context.role, "Financial accountant")

    def test_second_person_as_role(self):
        self.assertEqual(extract_context("As an audit manager, you review revenue recognition.").context.role, "Audit manager")

    def test_hypothetical_roles_are_not_facts(self):
        for text in ("Suppose I am an audit manager.", "If I am a financial accountant, I might review inventory valuation.", "Imagine I am a financial accountant."):
            with self.subTest(text=text):
                self.assertEqual(extract_context(text).context.role, "Unknown")

    def test_reported_speech_does_not_assign_the_speakers_role_to_user(self):
        result = extract_context("The CFO said, 'I am a financial accountant.'")
        self.assertEqual(result.context.role, "Unknown")

    def test_old_role_is_not_current_role(self):
        result = extract_context("Previously I am an auditor. I now work in a different department.")
        self.assertEqual(result.context.role, "Unknown")

    def test_third_party_friendship_is_not_users_relationship(self):
        for text in (
            "I am an auditor. The CFO is the CEO's close friend.",
            "I am an auditor. The CFO, a close friend of the CEO, asked for help.",
            "I am an auditor. The CFO is my manager's close friend.",
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_context(text).context.relationship, "Unknown")

    def test_friend_manager_and_spouses_colleague_are_not_direct_relations(self):
        for scenario in (
            "I am an auditor. The CFO is my close friend's manager.",
            "I am an auditor. The CFO is my spouse's colleague.",
            "I am an auditor. The CFO is a close friend.",
        ):
            with self.subTest(scenario=scenario):
                self.assertEqual(extract_context(scenario).context.relationship, "Unknown")

    def test_conditional_scenario_does_not_establish_parties_or_decision(self):
        result = extract_context("If I am a financial accountant, the CFO asks about inventory write-down.")
        self.assertEqual(result.context.parties, "Unknown")
        self.assertEqual(result.context.decision, "Unknown")

    def test_conditional_counterpart_and_topic_are_not_current_facts(self):
        for source in (
            "If the CFO were involved, we would discuss revenue recognition.",
            "The CFO could be involved in inventory valuation.",
            "If revenue recognition were involved, the CFO would advise.",
        ):
            with self.subTest(source=source):
                result = extract_context(source)
                self.assertEqual(result.context.parties, "Unknown")
                self.assertEqual(result.context.decision, "Unknown")

    def test_explicit_absence_is_not_an_active_decision(self):
        for source in (
            "No decision about revenue recognition is involved.",
            "Revenue recognition is not under consideration.",
            "There is no revenue recognition issue.",
            "The decision is not revenue recognition.",
        ):
            with self.subTest(source=source):
                self.assertEqual(extract_context(source).context.decision, "Unknown")

    def test_noninvolved_counterpart_is_not_suggested_as_relevant_party(self):
        result = extract_context("I am an auditor. The CFO is not involved in this decision. I review inventory valuation.")
        self.assertNotIn("CFO", result.context.parties)
        self.assertEqual(result.context.decision, "Inventory valuation")

    def test_noninvolved_friendship_does_not_become_relevant_relationship(self):
        result = extract_context("I am a financial accountant. The CFO is my close friend, but the CFO is not involved in this decision. I assess inventory valuation.")
        self.assertEqual(result.context.relationship, "Unknown")
        self.assertNotIn("CFO", result.context.parties)

    def test_negated_friendship_is_not_a_close_relationship(self):
        self.assertEqual(extract_context("I am an auditor. The CFO is not my close friend.").context.relationship, "Unknown")

    def test_ambiguous_closeness_remains_unknown(self):
        self.assertEqual(extract_context("I am an auditor. The CFO is my close friend but we are not close.").context.relationship, "Unknown")

    def test_explicit_no_personal_relationship(self):
        result = extract_context("I am a financial accountant. I have no personal relationship with the CFO.")
        self.assertEqual(result.context.relationship, "No relevant relationship")

    def test_explicit_professional_only_relationship(self):
        result = extract_context("The CFO is involved. Our relationship is professional only.")
        self.assertEqual(result.context.relationship, "Professional relationship only")

    def test_family_tie_is_not_assumed_close(self):
        result = extract_context("I am an auditor. My brother is the CFO.")
        self.assertEqual(result.context.relationship, "Other")
        self.assertIn("My brother is the CFO", result.context.relationship_notes)

    def test_explicit_close_friends_with_counterpart(self):
        result = extract_context("I am an auditor. I am close friends with the CFO.")
        self.assertEqual(result.context.relationship, "Close personal relationship")

    def test_historical_acquaintance_does_not_imply_closeness(self):
        result = extract_context("I am an auditor. I knew the CFO at university many years ago.")
        self.assertEqual(result.context.relationship, "Unknown")

    def test_topic_negation_does_not_erase_decision(self):
        result = extract_context("I am a financial accountant. I was asked not to write down the inventory.")
        self.assertIn("inventory", result.context.decision.lower())

    def test_background_topic_does_not_override_explicit_current_topic(self):
        result = extract_context("Last year we reviewed revenue recognition. The current issue is inventory valuation.")
        self.assertEqual(result.context.decision, "Inventory valuation")

    def test_hypothetical_competing_topics_do_not_become_decisions(self):
        result = extract_context("We might consider inventory write-down or revenue recognition.")
        self.assertEqual(result.context.decision, "Unknown")

    def test_deterministic_and_return_values_are_not_shared(self):
        first, second = extract_context(INVENTORY), extract_context(INVENTORY)
        self.assertEqual(first, second)
        first.context.role = "Edited"
        self.assertEqual(second.context.role, "Financial accountant at a manufacturing company")

    def test_large_scenarios_do_not_silently_truncate_evidence(self):
        result = extract_context("I am an auditor. " + "x" * MAX_SCENARIO_LENGTH)
        self.assertEqual(result.context.role, "Unknown")
        self.assertTrue(any("length limit" in text for text in result.limitations))

    def test_non_text_is_rejected_without_conversion(self):
        with self.assertRaises(TypeError):
            extract_context({"role": "auditor"})


if __name__ == "__main__":
    unittest.main()
