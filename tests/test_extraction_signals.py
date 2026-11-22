"""Regression cases for local signals, ownership, uncertainty and source evidence."""

import unittest

from objectivity.extraction_signals import extract_signals


CFO = (
    "You are the audit manager of a listed client. The CFO, a close personal "
    "friend from university, has asked you to 'go easy' on an aggressive revenue "
    "recognition judgement, hinting that your firm's tax advisory contract "
    "renewal depends on a smooth audit."
)


def parameterized(_names, scenarios):
    """Keep data-driven cases within the project's standard-library test suite."""
    def decorate(method):
        def run(self):
            for scenario in scenarios:
                args = scenario if isinstance(scenario, tuple) else (scenario,)
                with self.subTest(scenario=args[0]):
                    method(self, *args)
        return run
    return decorate


class SignalExtractionTests(unittest.TestCase):
    def test_cfo_combines_three_explicit_reported_signals(self):
        result = extract_signals(CFO, user_role="Audit manager")
        assert result.relationship == "Close personal relationship"
        assert result.interests == "Commercial interest"
        assert result.pressure == "Reported pressure or threatened consequences"
        assert "does not establish undue pressure" in result.pressure_notes
        for field, fragments in result.evidence.items():
            assert fragments, field
            assert all(fragment in CFO for fragment in fragments)


    @parameterized("scenario, expected", [
        ("I am close friends with the finance director.", "Close personal relationship"),
        ("The client is my close personal friend.", "Close personal relationship"),
        ("My sister is the procurement director.", "Other"),
        ("My spouse owns shares in the supplier.", "Other"),
        ("I report directly to the finance director.", "Other"),
        ("My line manager asked me to review the estimate.", "Other"),
        ("The department head insists I approve the loan.", "Other"),
        ("We have worked together for ten years.", "Other"),
        ("Our relationship is professional only.", "Professional relationship only"),
        ("I have no personal relationship with the CFO.", "No relevant relationship"),
        ("The CFO is the CEO's close friend.", "Unknown"),
        ("The CFO, a close friend of the CEO, asked me for help.", "Other"),
        ("The CFO is my close friend's manager.", "Unknown"),
        ("The CFO is my spouse's colleague.", "Unknown"),
        ("The CFO is a close friend.", "Unknown"),
        ("The CFO is not my close friend.", "Unknown"),
        ("If the CFO were my close friend, I would ask for advice.", "Unknown"),
        ("Previously the CFO was my close friend.", "Unknown"),
        ("The CFO is my close friend, but the CFO is not involved in this decision.", "Unknown"),
    ])
    def test_relationship_scope(self, scenario, expected):
        result = extract_signals(scenario, user_role="Accountant")
        assert result.relationship == expected
        assert all(source in scenario for source in result.evidence["relationship"])


    def test_professional_and_personal_relationships_can_coexist(self):
        result = extract_signals("I report to the CFO. The CFO is my close friend.")
        assert result.relationship == "Close personal relationship"
        assert len(result.evidence["relationship"]) == 2


    @parameterized("scenario", [
        "The CFO is my close friend, but we are not close.",
        "The CFO is my close friend. I have no personal relationship with the CFO.",
        "The CFO is my close friend. Our relationship is professional only.",
    ])
    def test_relationship_conflicts_require_clarification(self, scenario):
        result = extract_signals(scenario)
        assert result.relationship == "Unknown"
        assert "conflict" in result.relationship_notes
        assert result.limitations


    @parameterized("scenario, expected", [
        ("I own shares in the client.", "Personal financial interest"),
        ("I value a company in which I hold a 20 percent stake.", "Personal financial interest"),
        ("My bonus depends on loan approvals.", "Personal financial interest"),
        ("My annual bonus is tied to reported profit.", "Personal financial interest"),
        ("My professional fee is conditional on achieving a tax saving.", "Personal financial interest"),
        ("I earn commission on each sale approved.", "Personal financial interest"),
        ("My spouse owns shares in Alpha Tools.", "Personal financial interest"),
        ("My brother holds shares in the supplier.", "Other"),
        ("The CFO's bonus depends on reported profit.", "Other"),
        ('The CFO said, "My bonus depends on approval of this policy."', "Other"),
        ('My manager said, "I own shares in the client."', "Other"),
        ("The CFO said, 'My bonus depends on approval.'", "Other"),
        ("The sales director receives commission.", "Other"),
        ("The director said my promotion depends on approval.", "Other"),
        ("My firm's contract renewal depends on signing the report.", "Commercial interest"),
        ("Our firm may lose the client if I qualify the opinion.", "Commercial interest"),
        ("The employer wants to meet earnings targets.", "Commercial interest"),
        ("I work for a manufacturing company. The director wants to meet profit targets.", "Commercial interest"),
        ("I have no financial interest.", "No known interest"),
        ("I have no personal financial interest. My firm's contract renewal depends on the audit.", "Commercial interest"),
        ("I have no commercial interest. My bonus depends on the decision.", "Personal financial interest"),
        ("This inventory adjustment would reduce reported profit.", "Unknown"),
        ("The CFO receives no bonus.", "Unknown"),
        ("My bonus is not linked to this decision.", "Unknown"),
        ("If I owned shares, the decision would affect their value.", "Unknown"),
        ("Perhaps my bonus is tied to profit.", "Unknown"),
    ])
    def test_financial_ownership_scope_and_missing_facts(self, scenario, expected):
        result = extract_signals(scenario)
        assert result.interests == expected
        assert all(source in scenario for source in result.evidence["interests"])


    def test_own_and_firm_incentives_are_both_retained(self):
        text = "My annual bonus depends on profit. My firm's contract renewal depends on approval."
        result = extract_signals(text)
        assert result.interests == "Both commercial and personal interests"
        assert len(result.evidence["interests"]) == 2


    def test_family_holding_qualifies_ownership(self):
        result = extract_signals("My wife holds shares in a supplier I evaluate.")
        assert result.interests == "Personal financial interest"
        assert "user's own ownership is not asserted" in result.interests_notes


    def test_counterpart_bonus_does_not_become_user_financial_interest(self):
        result = extract_signals("The CFO's bonus depends on revenue. The CFO asked me to review revenue.")
        assert result.interests == "Other"
        assert "another party" in result.interests_notes
        assert "personal benefit for the user" in result.interests_notes


    @parameterized("scenario", [
        "I have no financial interest. I own shares in the client.",
        "I have no personal financial interest. My bonus depends on the outcome.",
        "I have no commercial interest. Our firm will lose the contract if I object.",
    ])
    def test_conflicting_interest_statements_are_not_resolved_by_assumption(self, scenario):
        result = extract_signals(scenario)
        assert result.interests == "Unknown"
        assert "conflicts" in result.interests_notes
        assert result.limitations


    @parameterized("scenario, expected", [
        ("My manager warned me I could lose my job unless I sign.", "Reported pressure or threatened consequences"),
        ("The purchasing director warned that refusing to favour Alpha Tools may block my promotion.", "Reported pressure or threatened consequences"),
        ("The department head insists I approve the loan despite my concerns.", "Reported pressure or threatened consequences"),
        ("My manager insists I lower the reserve.", "Reported pressure or threatened consequences"),
        ("The director asked me to avoid an inventory write-down to meet profit targets.", "Reported pressure or threatened consequences"),
        ("The CFO asked me to make the warranty provision smaller so the company can meet earnings targets.", "Reported pressure or threatened consequences"),
        ("The client wants me to omit overseas income.", "Reported pressure or threatened consequences"),
        ("The CFO asked me to go easy on revenue recognition.", "Reported pressure or threatened consequences"),
        ("The supervisor threatened to dismiss me if I refused.", "Reported pressure or threatened consequences"),
        ("The director pressured me into approving the estimate.", "Reported pressure or threatened consequences"),
        ("I am under no pressure.", "No reported pressure"),
        ("I am not under pressure.", "No reported pressure"),
        ("No one has pressured me.", "No reported pressure"),
        ("No one threatened me.", "No reported pressure"),
        ("There is no reported pressure.", "No reported pressure"),
        ("The CFO asked me to evaluate inventory.", "Unknown"),
        ("The partner asked me to sign the completed report.", "Unknown"),
        ("The CFO threatened litigation against a supplier.", "Unknown"),
        ("The CFO denies having threatened me.", "Unknown"),
        ("The CFO warned me not to ignore contradictory audit evidence.", "Unknown"),
        ("My finance director has told me not to avoid an inventory write-down to meet profit targets.", "Unknown"),
        ("I may face pressure in future.", "Unknown"),
        ("If the CFO were to threaten me, I would consult my partner.", "Unknown"),
        ("If my manager warned me I could lose my job, I would consult a partner.", "Unknown"),
        ("The CFO might threaten me.", "Unknown"),
        ("My manager has never threatened me.", "Unknown"),
    ])
    def test_reported_pressure_is_distinct_from_routine_requests_and_hypotheses(self, scenario, expected):
        result = extract_signals(scenario)
        assert result.pressure == expected
        assert all(source in scenario for source in result.evidence["pressure"])


    def test_conflicting_pressure_accounts_require_clarification(self):
        result = extract_signals("I am under no pressure. My manager threatened to dismiss me unless I sign.")
        assert result.pressure == "Unknown"
        assert "conflict" in result.pressure_notes
        assert result.limitations


    def test_unknown_scenario_does_not_generate_signals(self):
        result = extract_signals("Please help me assess an ethical situation.")
        assert (result.relationship, result.interests, result.pressure) == ("Unknown", "Unknown", "Unknown")
        assert result.evidence == {"relationship": (), "interests": (), "pressure": ()}
        assert not any((result.relationship_notes, result.interests_notes, result.pressure_notes))


    def test_only_text_inputs_are_accepted(self):
        with self.assertRaises(TypeError):
            extract_signals(None)


    def test_excerpts_remain_exact_across_contrast_and_semicolon_splitting(self):
        text = "My manager is my close friend; my bonus depends on profit, but no one has pressured me."
        result = extract_signals(text)
        assert result.relationship == "Close personal relationship"
        assert result.interests == "Personal financial interest"
        assert result.pressure == "No reported pressure"
        assert all(source in text for sources in result.evidence.values() for source in sources)


FULL_INVENTORY = (
    "You are a financial accountant preparing the year-end financial statements of a manufacturing company. "
    "Your finance director asks you to delay recognising a significant inventory write-down because it would reduce the company's reported profit. "
    "Your annual performance bonus depends partly on achieving the company's profit target. "
    "The finance director says the inventory may recover in value next year and asks you not to raise the issue with the auditors."
)


class ExpandedSignalExtractionTests(unittest.TestCase):
    def assert_literal_evidence(self, scenario, result):
        for field, excerpts in result.evidence.items():
            for excerpt in excerpts:
                self.assertIn(excerpt, scenario, field)

    def test_full_inventory_has_both_interests_and_two_reported_instructions(self):
        result = extract_signals(FULL_INVENTORY, user_role="Financial accountant")
        self.assertEqual(result.relationship, "Other")
        self.assertEqual(result.interests, "Both commercial and personal interests")
        self.assertEqual(result.pressure, "Reported pressure or threatened consequences")
        self.assertIn("Your annual performance bonus", result.interests_notes)
        self.assertNotIn("unclear recipient", result.interests_notes)
        self.assertNotIn("do not establish a personal benefit", result.interests_notes)
        self.assertEqual(len(result.evidence["pressure"]), 2)
        self.assertIn("delay recognising", result.pressure_notes)
        self.assertIn("not to raise the issue with the auditors", result.pressure_notes)
        self.assertIn("does not establish undue pressure, intent or misconduct", result.pressure_notes)
        self.assert_literal_evidence(FULL_INVENTORY, result)

    def test_multiple_modifiers_and_financial_incentive_forms_keep_recipient(self):
        cases = (
            "Your annual performance bonus depends partly on meeting the target.",
            "My quarterly personal sales commission depends on approved transactions.",
            "Your year-end performance-related bonuses are linked to approval.",
            "My deferred cash bonus is tied to the valuation.",
            "I receive a performance bonus on each loan I approve.",
            "Your financial incentive depends on the figures you approve.",
            "I have been offered a cash reward if I sign the report.",
            "I am eligible for share options if the acquisition is approved.",
            "I stand to gain financially from the decision.",
            "My annual performance bonus is substantial.",
            "My salary increase depends on the report I prepare.",
        )
        for source in cases:
            with self.subTest(source=source):
                result = extract_signals(source)
                self.assertEqual(result.interests, "Personal financial interest")
                self.assertNotIn("unclear recipient", result.interests_notes)
                self.assert_literal_evidence(source, result)

    def test_shareholdings_numeric_ownership_and_decimal_percentages(self):
        cases = (
            "Your indirect shareholding in the supplier is relevant to the bid.",
            "I hold a 2.5 percent equity stake in the company I value.",
            "I own 3,000 shares in the client.",
            "My beneficial ownership is unclear. I hold shares in a bidder.",
        )
        for source in cases:
            with self.subTest(source=source):
                result = extract_signals(source)
                self.assertEqual(result.interests, "Personal financial interest")
                self.assert_literal_evidence(source, result)

    def test_counterpart_or_company_benefit_does_not_become_own_bonus(self):
        cases = (
            "The finance director's annual performance bonus depends on approval.",
            'The finance director said, "My annual performance bonus depends on approval."',
            "The supplier pays its staff a sales commission.",
        )
        for source in cases:
            with self.subTest(source=source):
                result = extract_signals(source)
                self.assertEqual(result.interests, "Other")
                self.assertIn("another party", result.interests_notes)
                self.assert_literal_evidence(source, result)
        result = extract_signals("Your firm's contract renewal depends on the report. The director receives a bonus.")
        self.assertEqual(result.interests, "Commercial interest")

    def test_organisational_and_individual_incentives_coexist_in_either_order(self):
        personal = "Your annual performance bonus depends on approval."
        commercial = "Your firm's contract renewal depends on the work."
        for source in (personal + " " + commercial, commercial + " " + personal):
            with self.subTest(source=source):
                result = extract_signals(source)
                self.assertEqual(result.interests, "Both commercial and personal interests")
                self.assert_literal_evidence(source, result)

    def test_career_recognition_and_routine_salary_are_not_invented_money(self):
        for source in (
            "My annual recognition award is a certificate.",
            "My promotion depends on the manager's appraisal.",
            "I receive a fixed salary. No financial incentive is linked to this decision.",
        ):
            with self.subTest(source=source):
                result = extract_signals(source)
                self.assertNotIn(result.interests, {"Personal financial interest", "Both commercial and personal interests"})

    def test_directional_accounting_timing_requests_are_reported_not_proven_threats(self):
        cases = (
            "The controller asks you to delay recognising a material provision because it would reduce reported earnings.",
            "My manager asked me to defer recording the warranty expense until next year.",
            "The finance director instructed me to postpone recognition of the impairment loss.",
            "The supervisor requests that I hold back the accounting adjustment.",
            "The manager's instruction was to delay booking a liability.",
        )
        for source in cases:
            with self.subTest(source=source):
                result = extract_signals(source)
                self.assertEqual(result.pressure, "Reported pressure or threatened consequences")
                self.assertIn("does not establish undue pressure", result.pressure_notes)
                self.assert_literal_evidence(source, result)

    def test_requests_to_withhold_from_accountability_recipients_are_preserved(self):
        cases = (
            "Your finance director asks you not to raise the issue with the auditors.",
            "The manager told me not to inform the audit committee about the adjustment.",
            "The partner asks me to withhold the documents from the regulator.",
            "The director wants me to keep the loss out of the board papers.",
            "The supervisor requests that I never mention the transaction to the independent reviewer.",
            'The manager said, "Do not inform the auditors about the missing invoices."',
            "The director's instruction was not to disclose the finding to the board.",
        )
        for source in cases:
            with self.subTest(source=source):
                result = extract_signals(source)
                self.assertEqual(result.pressure, "Reported pressure or threatened consequences")
                self.assert_literal_evidence(source, result)

    def test_protective_and_routine_requests_do_not_become_pressure(self):
        cases = (
            "The finance director asks you to raise the issue with the auditors.",
            "The manager told me not to conceal evidence from auditors.",
            "The CFO asked me not to delay informing the regulator.",
            "The director did not ask me to defer recognising the loss.",
            "The manager denies having asked me to withhold information from auditors.",
            "My manager asked me to postpone the team lunch.",
            "The supervisor asks me to keep personnel records confidential from competitors.",
            "The finance director asks me to review recognition of an inventory adjustment.",
        )
        for source in cases:
            with self.subTest(source=source):
                result = extract_signals(source)
                self.assertEqual(result.pressure, "Unknown")

    def test_hypothetical_or_incomplete_monetary_or_pressure_claims_remain_unknown(self):
        cases = (
            "Perhaps my annual performance bonus depends on approval.",
            "If my manager asked me not to inform the auditors, I would seek advice.",
            "Suppose I hold shares and the director asks me to defer recognising a loss.",
            "I need help with a concern at work.",
        )
        for source in cases:
            with self.subTest(source=source):
                result = extract_signals(source)
                self.assertEqual(result.interests, "Unknown")
                self.assertEqual(result.pressure, "Unknown")

    def test_commission_and_organisation_receipt_of_fee_income_coexist(self):
        source = (
            "I am an investment analyst. I assess Cedar PLC. "
            "I receive a commission if Cedar wins the investment mandate; the firm also earns fees from Cedar."
        )
        result = extract_signals(source)
        self.assertEqual(result.interests, "Both commercial and personal interests")
        self.assertEqual(len(result.evidence["interests"]), 2)
        self.assertIn("commission", result.interests_notes)
        self.assertIn("the firm also earns fees", result.interests_notes)
        self.assert_literal_evidence(source, result)

    def test_organisation_income_paraphrases_do_not_include_outgoing_bonus_payments(self):
        for source in (
            "Our practice receives a contingent fee if the transaction completes.",
            "The firm will earn a success fee for the mandate.",
            "Your employer collects advisory fees from the client.",
            "My consultancy firm receives a retainer for the work.",
            "The company is paid commission on the sale.",
        ):
            with self.subTest(source=source):
                result = extract_signals(source)
                self.assertEqual(result.interests, "Commercial interest")
                self.assert_literal_evidence(source, result)
        for source in (
            "The supplier earns a success fee if the sale completes.",
            "The client's firm receives a retainer.",
            "Another company earns fees from the transaction.",
            "My firm pays performance bonuses to staff.",
        ):
            with self.subTest(source=source):
                result = extract_signals(source)
                self.assertNotIn(result.interests, {"Commercial interest", "Both commercial and personal interests"})
                self.assertNotEqual(result.interests, "Personal financial interest")
