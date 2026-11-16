"""Professional report snapshots, evidence provenance and stale-state protection."""

from copy import deepcopy
import unittest

from objectivity.address import (
    AddressState, CHECKED, IMPLEMENTED, REVIEW, save_address_answer, sync_address,
)
from objectivity.examples import EXAMPLE_CONTEXT, EXAMPLE_SCENARIO
from objectivity.models import Assessment, Context
from objectivity.questions import confirm_context, save_answer
from objectivity.report import build_report, humanize
from objectivity.review import ReviewState, save_review_answer, sync_review


def cfo_case():
    assessment = Assessment()
    confirm_context(assessment, EXAMPLE_SCENARIO, deepcopy(EXAMPLE_CONTEXT))
    for id, choice in (
        ("pressure_basis", "Implied in the conversation"),
        ("pressure_consequence", "Loss of fees or a contract"),
        ("pressure_effect", "No"),
        ("relationship_contact", "Frequent personal contact"),
        ("relationship_influence", "I supervise or review the work"),
        ("commercial_connection", "Contract renewal or client retention"),
        ("commercial_dependence", "Unknown"),
    ):
        save_answer(assessment, id, choice)
    review = ReviewState()
    sync_review(assessment, review)
    save_review_answer(assessment, review, "objectivity_basis", "I am not claiming the threats are addressed")
    address = AddressState()
    sync_address(assessment, review, address)
    return assessment, review, address


def neutral_case():
    assessment = Assessment()
    confirm_context(assessment, "A supplier approval decision", Context(
        role="Finance manager", parties="Supplier and finance team", decision="Approve supplier",
        relationship="No relevant relationship", interests="No known interest", pressure="No reported pressure",
    ))
    review, address = ReviewState(), AddressState()
    sync_review(assessment, review)
    sync_address(assessment, review, address)
    return assessment, review, address


def familiarity_case_with_initial_confidence():
    assessment = Assessment()
    confirm_context(assessment, "A manager must review a close friend's work.", Context(
        role="Manager", parties="Manager and close friend", decision="Review the work",
        relationship="Close personal relationship", interests="No known interest",
        pressure="No reported pressure",
    ))
    save_answer(assessment, "relationship_contact", "Frequent personal contact")
    save_answer(assessment, "relationship_influence", "I supervise or review the work")
    review, address = ReviewState(), AddressState()
    sync_review(assessment, review)
    save_review_answer(assessment, review, "objectivity_basis", "Confidence in my own impartiality")
    save_review_answer(assessment, review, "basis_challenge", "No additional basis identified")
    sync_address(assessment, review, address)
    return assessment, review, address


def review_action(case, *, stage=IMPLEMENTED, independent=True):
    assessment, review, address = case
    answers = [
        ("action", REVIEW), ("implementation", stage),
    ]
    if stage == IMPLEMENTED:
        answers.append(("independence", "Reviewer is independent of the relevant influences" if independent else "Reviewer is not independent"))
        if independent:
            answers.extend((
                ("competence", "Relevant competence is established"),
                ("authority", "Can require changes before the decision is final"),
                ("scope", "All relevant aspects of this threat were reviewed"),
                ("timing", "Before the decision or affected work was relied upon"),
                ("effect", "No continuing influence identified in the outcome check"),
                ("evidence", CHECKED),
            ))
    for field, choice in answers:
        save_address_answer(assessment, review, address, "Familiarity:0:" + field, choice)
    return case


class ReportTests(unittest.TestCase):
    def test_cfo_snapshot_has_specific_account_and_all_required_sections(self):
        report = build_report(*cfo_case())
        self.assertTrue(report.startswith("# Ethical Assessment Report"))
        for text in (
            "Audit manager of a listed client", "tax advisory", "revenue recognition",
            "Familiarity", "Intimidation", "Self-interest", "Significance", "significance",
            "Reasonable and informed third party", "Proposed versus implemented actions",
            "Remaining threats", "Conditional conclusion", "Prioritised next steps",
            "Scope and professional judgment", "Interim",
        ):
            with self.subTest(text=text):
                self.assertIn(text.lower(), report.lower())

    def test_generated_report_does_not_expose_internal_evidence_keys(self):
        report = build_report(*cfo_case())
        self.assertNotRegex(report, r"\b(?:answer|review|context)\.[a-z_]+")
        self.assertNotRegex(report, r"(?:FAM|INT|SELF)-\d+")
        self.assertNotIn("objectivity_basis", report)
        self.assertNotIn("relationship_ties", report)
        self.assertIn("commercial dependence", report)

    def test_humanize_replaces_multiple_sources_and_unknown_source_labels(self):
        text = humanize("A conflict (answer.pressure_effect; review.decision_responsibility) and answer.new_field.")
        self.assertIn("effect on professional work", text)
        self.assertIn("decision-making responsibility", text)
        self.assertIn("new field", text)
        self.assertNotRegex(text, r"\b(?:answer|review|context)\.")

    def test_report_preserves_uncertainty_and_provenance(self):
        report = build_report(*cfo_case())
        self.assertIn("organisation's dependence", report)
        self.assertIn("Unknown", report)
        self.assertIn("user-confirmed", report.lower())
        self.assertIn("recorded user answers", report.lower())
        self.assertIn("No independently verified evidence", report)
        self.assertIn("report of an external check", report)
        self.assertIn("not proof of biased conduct or misconduct", report)

    def test_unknown_only_case_does_not_invent_threats(self):
        assessment = Assessment()
        confirm_context(assessment, "An uncertain professional situation", Context(
            role="Unknown", parties="Unknown", decision="Unknown",
        ))
        for id in ("pressure_relevance", "relationship_relevance", "interest_relevance"):
            save_answer(assessment, id, "Unknown", "I am not sure.")
        review, address = ReviewState(), AddressState()
        sync_review(assessment, review)
        sync_address(assessment, review, address)
        report = build_report(assessment, review, address)
        self.assertIn("Interim", report)
        self.assertIn("insufficient information", report.lower())
        self.assertIn("No potential threat is established", report)
        self.assertNotIn("### Familiarity", report)

    def test_neutral_case_is_not_a_compliance_certificate(self):
        report = build_report(*neutral_case())
        self.assertIn("No potential threat is established", report)
        self.assertIn("does not establish that threats are absent", report)
        self.assertIn("not a certified ethical opinion", report)
        self.assertIn("audit-independence", report)

    def test_unconfirmed_context_is_explicitly_interim(self):
        report = build_report(Assessment(scenario="An unconfirmed report"), ReviewState(), AddressState())
        self.assertIn("Context awaiting confirmation", report)
        self.assertIn("Interim", report)
        self.assertNotIn("### Familiarity", report)

    def test_user_text_is_quoted_and_cannot_forge_report_sections(self):
        assessment, review, address = neutral_case()
        malicious = "An account\n\n# Certified compliant\n<script>alert('x')</script>\n[Approved](https://example.com)"
        confirm_context(assessment, malicious, assessment.context)
        sync_review(assessment, review)
        sync_address(assessment, review, address)
        report = build_report(assessment, review, address)
        self.assertNotIn("\n# Certified compliant", report)
        self.assertNotIn("<script>", report)
        self.assertNotIn("[Approved](https://example.com)", report)
        self.assertIn("> \\# Certified compliant", report)
        self.assertIn("&lt;script&gt;", report)

    def test_extra_explanation_is_retained_without_fact_inference(self):
        assessment, review, address = cfo_case()
        save_answer(assessment, "relationship_contact", "Frequent personal contact", "We meet each Friday.")
        report = build_report(assessment, review, address)
        self.assertIn("We meet each Friday", report)
        self.assertIn("Additional explanation — user account", report)
        self.assertIn("No independently verified evidence", report)

    def test_generation_does_not_mutate_any_phase_state(self):
        case = cfo_case()
        before = deepcopy(case)
        build_report(*case)
        self.assertEqual(case, before)

    def test_changed_phase_one_answers_remove_stale_pressure_finding(self):
        assessment, review, address = cfo_case()
        save_answer(assessment, "pressure_basis", "My interpretation only")
        save_answer(assessment, "pressure_support", "No further supporting information")
        report = build_report(assessment, review, address)
        self.assertNotIn("### Intimidation", report)
        self.assertIn("Interim", report)
        self.assertIn("no longer current", report)
        self.assertIn("interpretation", report)

    def test_report_before_address_has_no_invented_implemented_actions(self):
        report = build_report(*cfo_case())
        self.assertIn("No current implemented action", report)
        self.assertNotIn("All threats have been eliminated", report)
        self.assertIn("snapshot", report)

    def test_proposed_review_is_not_reported_as_completed(self):
        report = build_report(*review_action(cfo_case(), stage="Proposed, not yet started"))
        self.assertIn("Arrange independent review", report)
        self.assertIn("Recorded stage: Proposed, not yet started", report)
        self.assertIn("completed implementation is not established", report)
        self.assertNotIn("Recorded stage: Implemented according to my account", report)
        self.assertIn("does not yet establish", report)

    def test_requested_review_is_not_reported_as_an_effective_safeguard(self):
        report = build_report(*review_action(cfo_case(), stage="Requested or in progress"))
        self.assertIn("Recorded stage: Requested or in progress", report)
        self.assertIn("Acceptability not yet established", report)
        self.assertNotIn("User reports an external independent check", report)

    def test_unsuccessful_safeguard_remains_visible_in_report(self):
        report = build_report(*review_action(cfo_case(), independent=False))
        self.assertIn("Recorded stage: Implemented according to my account", report)
        self.assertIn("Reviewer is not independent", report)
        self.assertIn("Threat remains; further action required", report)
        self.assertIn("Escalate ineffective responses", report)

    def test_reported_external_check_is_distinguished_from_app_verification(self):
        report = build_report(*review_action(cfo_case()))
        self.assertIn("User reports an external independent check; not verified by the application", report)
        self.assertIn("Recorded stage: Implemented according to my account", report)
        self.assertIn("Conditional support for reduction", report)
        self.assertIn("does not yet establish that all relevant Objectivity threats", report)
        self.assertIn("No independently verified evidence", report)
        self.assertNotRegex(report, r"\b(?:answer|review|context)\.[a-z_]+")

    def test_phase_two_edit_ignores_stale_action_records_even_without_ui_sync(self):
        assessment, review, address = review_action(cfo_case(), stage="Proposed, not yet started")
        save_review_answer(assessment, review, "objectivity_basis", "Confidence in my own impartiality")
        report = build_report(assessment, review, address)
        self.assertIn("no longer current", report)
        self.assertNotIn("Recorded stage: Proposed, not yet started", report)
        self.assertIn("Earlier clarification or evaluation questions remain unanswered", report)

    def test_later_supported_action_does_not_preserve_historical_belief_as_current_gap(self):
        report = build_report(*review_action(familiarity_case_with_initial_confidence()))
        self.assertIn("**Status:** Conditional assessment", report)
        self.assertNotIn("**Status:** Interim", report)
        self.assertIn("Conditional support for reduction", report)
        facts = report.split("## 2.", 1)[1].split("## 3.", 1)[0]
        initial = report.split("## 4.", 1)[1].split("## 5.", 1)[0]
        residual = report.split("## 7.", 1)[1].split("## 8.", 1)[0]
        caution = "The recorded basis for treating threats as addressed is not sufficient by assertion alone"
        self.assertNotIn(caution, facts)
        self.assertNotIn(caution, residual)
        self.assertIn(caution, initial)
        self.assertIn("before the recorded actions", initial)
        self.assertIn("Confidence in my own impartiality", facts)

    def test_current_factual_gaps_survive_removal_of_historical_assertion_caution(self):
        assessment, review, address = cfo_case()
        save_review_answer(assessment, review, "objectivity_basis", "Confidence in my own impartiality")
        save_review_answer(assessment, review, "basis_challenge", "No additional basis identified")
        sync_address(assessment, review, address)
        report = build_report(*review_action((assessment, review, address)))
        facts = report.split("## 2.", 1)[1].split("## 3.", 1)[0]
        self.assertIn("**Status:** Interim", report)
        self.assertIn("organisation's dependence on the income or relationship is unresolved", facts)
        self.assertNotIn("The recorded basis for treating threats as addressed is not sufficient by assertion alone", facts)


if __name__ == "__main__":
    unittest.main()
