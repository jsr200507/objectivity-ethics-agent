"""Regression cases for reusable local actor and professional-activity rules."""

import unittest

from objectivity.extraction_entities import extract_entities
from objectivity.examples import EXAMPLE_SCENARIO


class EntityExtractionTests(unittest.TestCase):
    def assert_exact_evidence(self, source, result):
        for excerpts in result.evidence.values():
            for excerpt in excerpts:
                self.assertIn(excerpt, source)

    def test_existing_cfo_example_retains_context_without_invented_teams(self):
        result = extract_entities(EXAMPLE_SCENARIO)
        self.assertEqual(result.role, "Audit manager of a listed client")
        self.assertIn("CFO", result.parties)
        self.assertIn("revenue recognition", result.decision.lower())
        self.assertNotIn("audit team", result.parties.lower())
        self.assertNotIn("tax advisory team", result.parties.lower())
        self.assert_exact_evidence(EXAMPLE_SCENARIO, result)

    def test_financial_accountant_inventory_preserves_distinct_people(self):
        source = "I am a financial accountant at a manufacturing company. My finance director asked me to avoid an inventory write-down to meet profit targets."
        result = extract_entities(source)
        self.assertEqual(result.role, "Financial accountant at a manufacturing company")
        self.assertIn("Finance director", result.parties)
        self.assertEqual(result.decision, "Inventory write-down")
        self.assert_exact_evidence(source, result)

    def test_first_and_second_person_professional_role_grammar(self):
        cases = {
            "I serve as a credit analyst.": "Credit analyst",
            "I work as the procurement officer.": "Procurement officer",
            "As an actuary, I estimate insurance reserves.": "Actuary",
            "As a solicitor, you assess a litigation provision.": "Solicitor",
            "My position is senior financial accountant.": "Senior financial accountant",
            "Your role is a grant officer.": "Grant officer",
            "I am currently a deputy finance director.": "Deputy finance director",
            "I currently work as a chartered valuer.": "Chartered valuer",
            "I’m the CFO.": "CFO",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(extract_entities(source).role, expected)

    def test_named_employer_preserved_in_role(self):
        result = extract_entities("I serve as a credit analyst at Ridgeway Bank.")
        self.assertEqual(result.role, "Credit analyst at Ridgeway Bank")
        self.assertIn("Ridgeway Bank", result.parties)

    def test_conflicting_self_roles_do_not_become_other_parties(self):
        for source in (
            "I am an accountant or an auditor or a treasurer.",
            "I am an accountant and an audit manager.",
            "I am a financial accountant. I am a credit analyst.",
        ):
            with self.subTest(source=source):
                result = extract_entities(source)
                self.assertEqual(result.role, "Unknown")
                self.assertEqual(result.parties, "Unknown")
                self.assertTrue(result.limitations)

    def test_counterpart_after_conjunction_is_not_alternative_self_role(self):
        result = extract_entities("I am an auditor and the CFO warned me about the audit opinion.")
        self.assertEqual(result.role, "Auditor")
        self.assertIn("CFO", result.parties)

    def test_repeated_role_capitalisation_does_not_create_conflict(self):
        self.assertEqual(extract_entities("I am a Financial Accountant. My role is financial accountant.").role, "Financial accountant")

    def test_not_assigned_to_senior_persons_role(self):
        result = extract_entities("I am the audit manager's assistant.")
        self.assertEqual(result.role, "Unknown")
        self.assertEqual(result.parties, "Unknown")

    def test_reported_self_description_not_assigned_to_user(self):
        result = extract_entities("The CFO said, 'I am a financial accountant.'")
        self.assertEqual(result.role, "Unknown")
        self.assertEqual(result.parties, "CFO")

    def test_explicit_current_role_survives_separate_background_clause(self):
        result = extract_entities("Previously I am an auditor; I am now a financial accountant. The warehouse manager asked me to review stock valuation.")
        self.assertEqual(result.role, "Financial accountant")
        self.assertIn("Warehouse manager", result.parties)

    def test_complete_named_titles_in_both_directions(self):
        for phrase in ("Jane, the CFO", "CFO Jane", "Jane Smith, the finance director", "head of finance Priya Shah", "warehouse manager Joel Noor"):
            with self.subTest(phrase=phrase):
                source = f"I am an auditor. {phrase} asked me to review the audit report."
                result = extract_entities(source)
                self.assertIn(phrase, result.parties)
                self.assertIn(phrase, result.evidence['parties'])

    def test_all_explicit_people_not_only_first_title(self):
        source = "I am a financial accountant. The sales director Monica Hale, warehouse manager Joel Noor, and head of finance Priya Shah asked me to review stock valuation."
        result = extract_entities(source)
        for phrase in ("sales director Monica Hale", "warehouse manager Joel Noor", "head of finance Priya Shah"):
            self.assertIn(phrase, result.parties)
        self.assert_exact_evidence(source, result)

    def test_explicit_governance_groups_and_counterpart_roles(self):
        source = "I am an auditor. The audit committee, our client, the regulator and the external auditors are discussing the audit opinion. My line manager asked for a draft."
        result = extract_entities(source)
        for party in ("audit committee", "client", "regulator", "external auditors", "line manager"):
            self.assertIn(party, result.parties.lower())

    def test_named_supplier_lists_with_forward_role_cue(self):
        source = "I am a procurement analyst. Suppliers Acme and Beta submitted bids. I must assess the quotations."
        result = extract_entities(source)
        self.assertIn("Acme", result.parties)
        self.assertIn("Beta", result.parties)
        self.assertIn("quotations", result.decision.lower())
        self.assert_exact_evidence(source, result)

    def test_named_supplier_lists_with_reverse_role_cue(self):
        source = "Acme and Beta are competing suppliers. I am a procurement officer. I must select the winning bid."
        result = extract_entities(source)
        for party in ("Acme", "Beta", "supplier"):
            self.assertIn(party, result.parties)
        self.assertIn("winning bid", result.decision.lower())

    def test_bid_from_named_organisation(self):
        source = "I am a purchasing officer. I need to evaluate the bid from Cedar Manufacturing. The purchasing director requested an exception."
        result = extract_entities(source)
        self.assertIn("Cedar Manufacturing", result.parties)
        self.assertIn("evaluate the bid", result.decision.lower())

    def test_named_customer_and_named_bank(self):
        source = "I serve as a credit analyst at Ridgeway Bank. Daniel Price, the branch manager, told me to approve a loan for customer Stonebridge Ltd."
        result = extract_entities(source)
        for party in ("Ridgeway Bank", "Daniel Price, the branch manager", "Stonebridge Ltd"):
            self.assertIn(party, result.parties)
        self.assertIn("approve a loan", result.decision.lower())
        self.assert_exact_evidence(source, result)

    def test_progressive_activity_after_role_is_extracted(self):
        source = "I am a procurement officer choosing between Alpha Tools and Beta Supplies for a supplier contract. My spouse owns shares in Alpha Tools. Our purchasing director warned that refusing to favour Alpha Tools could block my promotion."
        result = extract_entities(source)
        self.assertIn("choosing between alpha tools and beta supplies", result.decision.lower())
        for party in ("Alpha Tools", "Beta Supplies", "spouse", "Purchasing director"):
            self.assertIn(party, result.parties)
        self.assert_exact_evidence(source, result)

    def test_legal_role_and_provision_outside_inventory_example(self):
        result = extract_entities("I work as a solicitor. The legal counsel, Priya Shah, asked me to assess litigation provision.")
        self.assertEqual(result.role, "Solicitor")
        self.assertIn("legal counsel, Priya Shah", result.parties)
        self.assertEqual(result.decision, "Litigation provision")

    def test_grant_applicants_honorific_and_explicit_affiliation(self):
        source = "I am a grant officer. Dr Patel is the chair of the selection panel. Green Aid and Hope Fund have applied for a grant. My spouse is a trustee at Green Aid. I recommend the grant award."
        result = extract_entities(source)
        for party in ("Dr Patel", "chair of the selection panel", "Green Aid", "Hope Fund", "spouse"):
            self.assertIn(party, result.parties)
        self.assertIn("Grant award", result.decision)
        self.assert_exact_evidence(source, result)

    def test_actuary_reserve_estimation(self):
        result = extract_entities("As an actuary, I must estimate insurance reserves. The chief actuary Maya Chen asked me to lower the estimate.")
        self.assertEqual(result.role, "Actuary")
        self.assertIn("chief actuary Maya Chen", result.parties)
        self.assertIn("Insurance reserves", result.decision)

    def test_property_valuer_activity(self):
        result = extract_entities("I am a chartered surveyor. My client asks about the property valuation and I must value the office building.")
        self.assertEqual(result.role, "Chartered surveyor")
        self.assertIn("Client", result.parties)
        self.assertIn("Property valuation", result.decision)

    def test_professional_activities_not_limited_to_accounting_topics(self):
        for clause, subject in (
            ("I must assess a grant application", "grant application"),
            ("I need to recommend a candidate for appointment", "candidate"),
            ("I must award the bridge maintenance tender", "tender"),
            ("I am reviewing a proposed acquisition", "proposed acquisition"),
            ("My task is to certify a safety inspection", "safety inspection"),
            ("I am responsible for evaluating a patent licence", "patent licence"),
            ("I am tasked with determining warranty estimates", "warranty estimates"),
        ):
            with self.subTest(clause=clause):
                self.assertIn(subject, extract_entities(clause + ".").decision.lower())

    def test_requested_generic_activity_is_not_claimed_complete(self):
        result = extract_entities("My manager asked me to approve an expense claim.")
        self.assertTrue(result.decision.startswith("Requested activity:"))
        self.assertNotIn("Approved", result.decision)

    def test_requested_nonperformance_retains_negation(self):
        source = "My manager instructed me not to approve an expense claim."
        result = extract_entities(source)
        self.assertIn("not to approve", result.decision)
        self.assert_exact_evidence(source, result)

    def test_passive_request_still_establishes_relevant_activity(self):
        result = extract_entities("I was asked to certify a safety inspection.")
        self.assertIn("certify a safety inspection", result.decision)
        self.assertTrue(result.decision.startswith("Requested activity:"))

    def test_negative_instruction_still_identifies_inventory_activity(self):
        for phrase in ("write down obsolete inventory", "write down the damaged inventory", "writing down inventory", "write-down of obsolete inventory"):
            with self.subTest(phrase=phrase):
                source = f"I am a financial accountant. My finance director told me not to {phrase}."
                result = extract_entities(source)
                self.assertIn("inventory", result.decision.lower())
                self.assertIn(phrase, result.evidence['decision'])

    def test_joint_topics_are_kept_rather_than_declared_ambiguous(self):
        result = extract_entities("I review revenue recognition and inventory write-down.")
        self.assertIn("Revenue recognition", result.decision)
        self.assertIn("Inventory write-down", result.decision)

    def test_joint_generic_activity_is_not_lost_after_known_topic(self):
        result = extract_entities("I review revenue recognition and approve payroll.")
        self.assertIn("approve payroll", result.decision.lower())

    def test_complete_financial_statements_case_retains_requests_and_recipients(self):
        source = (
            "You are a financial accountant preparing the year-end financial statements of a manufacturing company. "
            "Your finance director asks you to delay recognising a significant inventory write-down because it would reduce the company's reported profit. "
            "Your annual performance bonus depends partly on achieving the company's profit target. "
            "The finance director says the inventory may recover in value next year and asks you not to raise the issue with the auditors."
        )
        result = extract_entities(source)
        self.assertEqual(result.role, "Financial accountant")
        self.assertEqual(result.parties, "You — Financial accountant; Manufacturing company; Finance director; Auditors")
        for fragment in (
            "preparing the year-end financial statements of a manufacturing company",
            "to delay recognising a significant inventory write-down",
            "not to raise the issue with the auditors",
        ):
            self.assertIn(fragment, result.evidence['decision'])
            self.assertIn(fragment, result.decision.lower())
        self.assertNotIn("external", result.parties.lower())
        self.assertNotIn("recover", result.decision.lower())
        self.assertNotIn("reduce the company's reported profit", result.decision.lower())
        self.assert_exact_evidence(source, result)

    def test_plural_roles_are_literal_recipients_not_assumed_qualifications(self):
        source = "I am an accountant. My manager asked me not to disclose the discrepancy to the auditors or the finance directors."
        result = extract_entities(source)
        self.assertIn("Auditors", result.parties)
        self.assertIn("Finance directors", result.parties)
        self.assertNotIn("external", result.parties.lower())
        self.assertNotIn("chief", result.parties.lower())
        self.assertIn("not to disclose the discrepancy", result.decision)
        self.assert_exact_evidence(source, result)

    def test_other_plural_professional_groups_are_not_omitted(self):
        source = "I am an actuary. The claims managers and actuaries asked me to review claims reserves with the trustees."
        result = extract_entities(source)
        for party in ("Claims managers", "Actuaries", "Trustees"):
            self.assertIn(party, result.parties)
        self.assert_exact_evidence(source, result)

    def test_information_withheld_from_role_is_not_an_absent_party(self):
        source = "I am an audit manager. The CFO instructed me not to report the discrepancy to the audit committee and the regulator."
        result = extract_entities(source)
        self.assertIn("Audit committee", result.parties)
        self.assertIn("Regulator", result.parties)
        self.assertIn("not to report the discrepancy", result.decision)

    def test_requested_timing_paraphrases_are_distinct_from_topic(self):
        for request in (
            "asks me to defer booking the inventory write-down",
            "tells me to postpone recognition of the inventory write-down",
            "asked that I delay recognising the inventory write-down",
            "requests that I not recognise the inventory write-down",
        ):
            with self.subTest(request=request):
                source = f"I am a financial accountant. The finance director {request}."
                result = extract_entities(source)
                self.assertIn("Inventory write-down", result.decision)
                self.assertIn("Requested activity:", result.decision)
                self.assert_exact_evidence(source, result)

    def test_requested_amount_change_not_reduced_to_reserves_topic(self):
        source = "I am an actuary. The chief actuary asks me to lower the claims reserves because a larger estimate would affect reported earnings."
        result = extract_entities(source)
        self.assertIn("Claims reserves", result.decision)
        self.assertIn("Requested activity: to lower the claims reserves", result.decision)
        self.assertNotIn("would affect", result.decision)
        self.assert_exact_evidence(source, result)

    def test_simple_inventory_topic_remains_compact_without_extra_request(self):
        source = "I am a financial accountant at a manufacturing company. My finance director has asked me to avoid an inventory write-down to meet profit targets."
        self.assertEqual(extract_entities(source).decision, "Inventory write-down")

    def test_generic_company_reference_deduplicates_clear_descriptive_party(self):
        source = "I am a financial accountant at a manufacturing company. The company wants a draft and the finance director asked me about stock valuation."
        result = extract_entities(source)
        self.assertIn("Manufacturing company", result.parties)
        self.assertNotIn("; Company", result.parties)
        self.assertIn("company", result.evidence['parties'])

    def test_explicit_second_organisation_kept_distinct(self):
        source = "I am an accountant at a manufacturing company. Another company is a supplier. The finance director asked me to assess the contract."
        result = extract_entities(source)
        self.assertIn("Manufacturing company", result.parties)
        self.assertIn("Another company", result.parties)
        self.assertIn("Supplier", result.parties)

    def test_two_named_banks_not_merged_with_assumed_common_identity(self):
        source = "I am a credit analyst. Cedar Bank and Grove Bank are lenders. I must assess a loan application."
        result = extract_entities(source)
        self.assertIn("Cedar Bank", result.parties)
        self.assertIn("Grove Bank", result.parties)
        self.assert_exact_evidence(source, result)

    def test_grouped_and_individual_named_supplier_mentions_are_consolidated(self):
        for first, second in (("Northstar", "Beacon"), ("Alpha Tools", "Beta Supplies")):
            with self.subTest(names=(first, second)):
                source = (
                    f"I am a procurement officer. {first} and {second} are competing suppliers. "
                    f"I evaluate bids from {first} and {second}. My sister is a manager at {first}."
                )
                result = extract_entities(source)
                labels = result.parties.split('; ')
                self.assertEqual(labels.count(f"{first} — supplier"), 1)
                self.assertEqual(labels.count(f"{second} — supplier"), 1)
                self.assertFalse(any(f"{first} and {second}" in label for label in labels))
                self.assertNotIn("Suppliers", labels)
                self.assertIn("Manager", labels)
                self.assertIn("My sister", labels)
                self.assertIn(f"{first} and {second} are competing suppliers", result.evidence['parties'])
                self.assertIn(f"bids from {first} and {second}", result.evidence['parties'])
                self.assert_exact_evidence(source, result)

    def test_repeated_named_actor_retains_each_explicit_organisation_role(self):
        source = "I am an accountant. Suppliers Northstar and Beacon submitted bids. Customer Northstar requested a credit note. I assess a loan application."
        result = extract_entities(source)
        labels = result.parties.split('; ')
        self.assertEqual(sum('Northstar' in label for label in labels), 1)
        self.assertIn("Northstar — supplier, customer", labels)
        self.assertIn("Beacon — supplier", labels)
        self.assert_exact_evidence(source, result)

    def test_bid_cue_does_not_assign_an_unstated_supplier_role(self):
        result = extract_entities("I am a procurement officer. I evaluate bids from Northstar and Beacon.")
        self.assertIn("Northstar", result.parties)
        self.assertIn("Beacon", result.parties)
        self.assertNotIn("supplier", result.parties.lower())

    def test_hypothetical_disclosure_request_does_not_become_fact(self):
        result = extract_entities("If the CFO were involved, the auditors might ask me to conceal the inventory write-down.")
        self.assertEqual(result.parties, "Unknown")
        self.assertEqual(result.decision, "Unknown")

    def test_explicit_either_or_activities_need_clarification(self):
        result = extract_entities("My task is either revenue recognition or inventory valuation.")
        self.assertEqual(result.decision, "Unknown")
        self.assertTrue(result.limitations)

    def test_uncertain_other_activity_does_not_erase_known_work(self):
        result = extract_entities("I must review inventory valuation. We might consider revenue recognition later.")
        self.assertEqual(result.decision, "Inventory valuation")

    def test_not_involved_party_exclusion_is_local_to_role_and_name(self):
        result = extract_entities("CFO Alice is not involved; CFO Ben asked me to assess a loan application.")
        self.assertNotIn("Alice", result.parties)
        self.assertIn("CFO Ben", result.parties)

    def test_separate_absent_role_does_not_hide_active_party(self):
        result = extract_entities("The bank is not involved, but my warehouse manager asked me about stock valuation.")
        self.assertNotIn("Bank", result.parties)
        self.assertIn("Warehouse manager", result.parties)

    def test_role_negation_does_not_promote_user_or_counterpart(self):
        result = extract_entities("I am not an audit manager. No CFO is involved. My supervisor asked about payroll review.")
        self.assertEqual(result.role, "Unknown")
        self.assertNotIn("Audit manager", result.parties)
        self.assertNotIn("CFO", result.parties)
        self.assertIn("Supervisor", result.parties)

    def test_absent_activity_not_selected_as_professional_decision(self):
        for source in (
            "No decision about revenue recognition is involved.",
            "Revenue recognition is not under consideration.",
            "There is no revenue recognition issue.",
            "The decision is not revenue recognition.",
        ):
            with self.subTest(source=source):
                self.assertEqual(extract_entities(source).decision, "Unknown")

    def test_background_clauses_do_not_discard_current_actors(self):
        result = extract_entities("Last year the CFO reviewed revenue recognition; now the warehouse manager asked me to assess inventory valuation.")
        self.assertNotIn("CFO", result.parties)
        self.assertIn("Warehouse manager", result.parties)
        self.assertEqual(result.decision, "Inventory valuation")

    def test_hypothetical_actors_roles_and_topics_are_not_facts(self):
        for source in (
            "If I am a financial accountant, the CFO asks about inventory write-down.",
            "Suppose I am an audit manager.",
            "If the CFO were involved, we would discuss revenue recognition.",
            "The CFO could be involved in inventory valuation.",
            "I might be an auditor.",
        ):
            with self.subTest(source=source):
                result = extract_entities(source)
                self.assertEqual(result.role, "Unknown")
                self.assertEqual(result.parties, "Unknown")
                self.assertEqual(result.decision, "Unknown")

    def test_actual_warning_not_suppressed_by_possible_consequence(self):
        for consequence in ("I could lose my bonus", "I might be fired", "I may be removed from the team"):
            with self.subTest(consequence=consequence):
                source = f"I am a credit analyst. My line manager warned that {consequence} unless I approve the loan application."
                result = extract_entities(source)
                self.assertIn("Line manager", result.parties)
                self.assertIn("Loan application", result.decision)

    def test_unknown_information_not_filled_from_domain_assumptions(self):
        result = extract_entities("Something concerns me at work.")
        self.assertEqual((result.role, result.parties, result.decision), ("Unknown",) * 3)
        self.assertEqual(result.evidence, {"role": (), "parties": (), "decision": ()})

    def test_names_not_invented_from_sentence_connectives(self):
        result = extract_entities("I am an auditor. However, the CFO asked about revenue recognition.")
        self.assertNotIn("However", result.parties)
        self.assertIn("CFO", result.parties)

    def test_empty_and_nontext_input(self):
        self.assertEqual(extract_entities("").role, "Unknown")
        with self.assertRaises(TypeError):
            extract_entities({"role": "auditor"})

    def test_oversized_source_fails_closed_without_partial_suggestions(self):
        result = extract_entities("I am an auditor. " + "x" * 100_000)
        self.assertEqual((result.role, result.parties, result.decision), ("Unknown",) * 3)
        self.assertTrue(any("length limit" in note for note in result.limitations))

    def test_repeatable_results_have_fresh_evidence_mapping(self):
        first = extract_entities(EXAMPLE_SCENARIO)
        second = extract_entities(EXAMPLE_SCENARIO)
        self.assertEqual(first, second)
        first.evidence['role'] = ()
        self.assertTrue(second.evidence['role'])


if __name__ == "__main__":
    unittest.main()
