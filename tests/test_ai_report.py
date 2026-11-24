"""AI may organise approved report language, never supply ethical assertions."""
from copy import deepcopy
import json
import unittest

from objectivity.ai_report import AIReportError, build_ai_report_request, validate_ai_report
from objectivity.case_model import CaseAction, CaseHistory
from objectivity.case_report import build_case_report
from objectivity.case_workflow import edit_case_fact, review_case
from tests.test_case_actions import action, source_case
from tests.test_case_refined_address_report import unrelated_interest_case


def valid_response(context, variant=0):
    return {"basis_signature": context.basis_signature,
            "selection": [{"id": clause.id, "variant": min(variant, len(clause.variants) - 1)}
                          for clause in context.clauses]}


class AIReportTests(unittest.TestCase):
    def setUp(self):
        self.case = source_case()
        self.system, self.user, self.context = build_ai_report_request(self.case)

    def test_valid_structured_choice_renders_only_server_owned_case_wording(self):
        result = validate_ai_report(valid_response(self.context, 1), self.context, case=self.case)
        self.assertIn("AI-assisted case overview", result)
        self.assertIn("inventory", result)
        self.assertIn("bonus", result.lower())
        self.assertIn("Ethical findings remain deterministic", result)
        self.assertNotIn(self.context.basis_signature, result)
        self.assertNotIn("threat-1", result)

    def test_arbitrary_generated_prose_is_not_accepted(self):
        response = valid_response(self.context)
        response["text"] = "The accountant has complied with every ethical requirement."
        with self.assertRaises(AIReportError):
            validate_ai_report(response, self.context)

    def test_model_supplied_conclusion_or_verification_is_rejected(self):
        for key, value in (("conclusion", "At an acceptable level"),
                           ("verified", True), ("effectiveness", "Established")):
            response = valid_response(self.context)
            response[key] = value
            with self.subTest(key=key), self.assertRaises(AIReportError):
                validate_ai_report(response, self.context)

    def test_clause_text_injection_or_fabricated_safeguard_is_rejected(self):
        response = valid_response(self.context)
        response["selection"][0]["text"] = "An independent partner eliminated the conflict."
        with self.assertRaises(AIReportError):
            validate_ai_report(response, self.context)

    def test_unknown_clause_and_duplicate_clause_are_rejected(self):
        for identifier in ("new-perfect-safeguard", self.context.clauses[1].id):
            response = valid_response(self.context)
            response["selection"][0]["id"] = identifier
            with self.subTest(identifier=identifier), self.assertRaises(AIReportError):
                validate_ai_report(response, self.context)

    def test_omitting_a_threat_or_conclusion_or_scope_is_rejected(self):
        for identifier in ("threat-1", "conclusion", "scope"):
            response = valid_response(self.context)
            response["selection"] = [item for item in response["selection"] if item["id"] != identifier]
            with self.subTest(identifier=identifier), self.assertRaises(AIReportError):
                validate_ai_report(response, self.context)

    def test_boolean_negative_out_of_range_and_non_integer_variants_are_rejected(self):
        for variant in (True, False, -1, 99, 1.0, "0", None):
            response = valid_response(self.context)
            response["selection"][0]["variant"] = variant
            with self.subTest(variant=variant), self.assertRaises(AIReportError):
                validate_ai_report(response, self.context)

    def test_malformed_output_shapes_are_rejected(self):
        for raw in (None, "{}", [], {}, {"basis_signature": self.context.basis_signature, "selection": {}},
                    {"basis_signature": self.context.basis_signature, "selection": ["threat-1"]}):
            with self.subTest(raw=raw), self.assertRaises(AIReportError):
                validate_ai_report(raw, self.context)

    def test_stale_basis_is_rejected_after_material_fact_change(self):
        response = valid_response(self.context)
        edit_case_fact(self.case, "bonus", "Shareholding in the inventory supplier")
        review_case(self.case)
        with self.assertRaises(AIReportError):
            validate_ai_report(response, self.context, case=self.case)
        self.assertNotEqual(build_ai_report_request(self.case)[2].basis_signature,
                            self.context.basis_signature)

    def test_action_stage_and_evidence_changes_invalidate_only_report_context(self):
        action(self.case, stage="Planned")
        first = build_ai_report_request(self.case)[2]
        self.case.actions[0].stage = "Implemented"
        second = build_ai_report_request(self.case)[2]
        self.assertNotEqual(first.basis_signature, second.basis_signature)
        self.case.actions[0].evidence_detail = "A signed review records the inventory challenge."
        third = build_ai_report_request(self.case)[2]
        self.assertNotEqual(second.basis_signature, third.basis_signature)

    def test_reruns_and_usage_history_do_not_change_report_basis(self):
        before = build_ai_report_request(self.case)[2]
        self.case.revision += 1
        self.case.history.append(CaseHistory("AI assistance request", "report", "hashed metadata only"))
        after = build_ai_report_request(self.case)[2]
        self.assertEqual(before.basis_signature, after.basis_signature)

    def test_request_excludes_superseded_history_and_full_interaction_transcript(self):
        self.case.history.append(CaseHistory("Secret earlier account", "Superseded private text"))
        self.case.scenario = "Complete raw scenario that should not be sent as interaction history."
        _, user, context = build_ai_report_request(self.case)
        self.assertNotIn("Superseded private text", user)
        self.assertNotIn("Complete raw scenario", user)
        self.assertEqual(set(json.loads(user)), {"basis_signature", "mandatory_ids", "catalog"})
        self.assertIn("Never create", self.system)
        self.assertEqual(len(context.mandatory_ids), len(context.clauses))

    def test_confirmed_user_account_is_required_but_is_not_external_verification(self):
        self.case.reviewed = False
        with self.assertRaises(AIReportError):
            build_ai_report_request(self.case)
        review_case(self.case)
        result = validate_ai_report(valid_response(build_ai_report_request(self.case)[2]),
                                    build_ai_report_request(self.case)[2])
        self.assertIn("not verified events", result)

    def test_optional_ai_overview_does_not_modify_deterministic_report_or_sources(self):
        before_case = deepcopy(self.case)
        before_report = build_case_report(self.case)
        validate_ai_report(valid_response(self.context), self.context)
        self.assertEqual(self.case, before_case)
        self.assertEqual(build_case_report(self.case), before_report)

    def test_acceptable_threat_remains_in_overview_without_inventing_action(self):
        case = unrelated_interest_case()
        _, _, context = build_ai_report_request(case)
        result = validate_ai_report(valid_response(context), context)
        self.assertIn("At an acceptable level", result)
        self.assertIn("No additional safeguards are indicated", result)
        self.assertIn("No action is recorded", result)
        self.assertNotIn("Implemented", result)

    def test_planned_action_stays_planned_and_cannot_be_relabelled_implemented(self):
        action(self.case, stage="Planned")
        _, _, context = build_ai_report_request(self.case)
        result = validate_ai_report(valid_response(context), context)
        self.assertIn("Reported implementation: Planned", result)
        self.assertNotIn("Reported implementation: Implemented", result)
        response = valid_response(context)
        response["selection"].append({"id": "action-1", "variant": 0})
        with self.assertRaises(AIReportError):
            validate_ai_report(response, context)

    def test_source_html_and_markdown_are_escaped(self):
        self.case.actions = [CaseAction("a", "<script>bad</script> [open](https://example.com)",
                                        "other", "Planned")]
        _, _, context = build_ai_report_request(self.case)
        result = validate_ai_report(valid_response(context), context)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)
        self.assertIn("\\[open\\]", result)


if __name__ == "__main__":
    unittest.main()
