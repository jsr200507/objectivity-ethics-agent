"""Professional reports preserve attributed evidence and conditional action outcomes."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from objectivity.case_model import (
    CaseAction, CaseActor, CaseFact, CaseState, ReasoningSnapshot,
    ThreatEvaluation, ThreatInstance,
)
from objectivity.case_report import build_case_report


def case_fixture():
    case = CaseState(
        "I am an audit manager reviewing revenue recognition. The CFO is my close friend. "
        "My bonus and the firm's contract renewal depend on approval. The CFO asked me to go easy.",
        actors=[CaseActor("user", "Audit manager", "Audit manager"), CaseActor("cfo", "CFO"), CaseActor("firm", "Audit firm", kind="organisation")],
        facts=[
            CaseFact("f-role", "user", "role", "Audit manager", excerpt="I am an audit manager", reviewed=True),
            CaseFact("f-decision", "user", "decision", "Review revenue recognition", excerpt="reviewing revenue recognition", reviewed=True),
            CaseFact("f-bonus", "user", "interest", "Personal performance bonus", "firm", excerpt="My bonus", reviewed=True),
            CaseFact("f-contract", "firm", "interest", "Contract renewal", excerpt="the firm's contract renewal", reviewed=True),
            CaseFact("f-pressure", "cfo", "pressure", "Request to favour revenue approval", "user", excerpt="The CFO asked me to go easy", reviewed=True),
        ], reviewed=True,
    )
    threats = (
        ThreatInstance("t-bonus", "Self-interest", "user", "decision", "The audit manager's bonus may favour approval over objective revenue judgment.", ("f-bonus",)),
        ThreatInstance("t-contract", "Self-interest", "firm", "decision", "Retaining the audit firm's contract may discourage challenge of revenue recognition.", ("f-contract",)),
        ThreatInstance("t-pressure", "Intimidation", "cfo", "decision", "The CFO's request may discourage the audit manager from challenging the revenue judgment.", ("f-pressure",)),
    )
    evaluations = tuple(ThreatEvaluation(
        t.id, "Action needed before proceeding", (f"The reported {t.kind.lower()} source intersects with the revenue decision.",),
        ("The degree of financial dependence is not established.",) if t.id == "t-contract" else (),
        "A reasonable and informed third party would need evidence that this particular source cannot steer the revenue judgment.",
    ) for t in threats)
    return case, ReasoningSnapshot(threats, evaluations, (), ("The bonus, contract renewal and CFO request may reinforce each other.",))


def action_assessment(case, snapshot, *, stage="Planned", effective=False):
    actions = tuple(SimpleNamespace(
        action_id=action.id, description=action.description, kind=action.kind,
        claimed_stage=action.stage, status="Effectiveness Established" if effective else stage,
        covered_threats=action.threat_ids,
        reasoning=("Coverage and outcome evidence support this response conditionally." if effective else "Completion and effectiveness are not established by a proposed review.",),
        gaps=() if effective else ("Obtain completion records covering the revenue judgment and the recorded influences.",),
        effective=effective, failed=False,
    ) for action in case.actions)
    outcomes = tuple(SimpleNamespace(
        threat_id=t.id, kind=t.kind,
        status="Threat adequately addressed — conditional on the recorded evidence" if effective else "Acceptability not established",
        reasoning=("The recorded review covers this source of influence." if effective else "The revenue judgment remains exposed to this recorded source.",),
        unknowns=() if effective else ("Effective review of this source is not established.",),
        action_ids=tuple(a.id for a in case.actions),
        third_party="Protection depends on the recorded review coverage and outcome.",
    ) for t in snapshot.threats)
    return SimpleNamespace(
        outcomes=outcomes, actions=actions,
        conclusion="The recorded evidence conditionally supports the responses; professional judgment is required." if effective else "The recorded evidence does not establish that all relevant threats are at an acceptable level.",
        third_party="The audit manager's bonus, firm contract and CFO request must each be covered before relying on protection of the revenue judgment.",
        next_steps=() if effective else ("Obtain a completed review of the revenue judgment by a reviewer independent of the bonus, contract and CFO influences, with authority to require correction.",),
        unknowns=() if effective else ("Completion evidence for the revenue review is missing.",),
    )


class CaseReportTests(unittest.TestCase):
    def report(self, case=None, snapshot=None, *, effective=False):
        if case is None:
            case, snapshot = case_fixture()
        addressed = action_assessment(case, snapshot, stage="Implemented" if effective else "Planned", effective=effective)
        with patch("objectivity.case_report.reason_case", return_value=snapshot), patch("objectivity.case_report.assess_actions", return_value=addressed):
            return build_case_report(case)

    def test_nine_sections_are_specific_and_same_category_sources_stay_distinct(self):
        report = self.report()
        for heading in ("A. Scenario summary", "B. Identified potential Objectivity threats", "C. Threat evaluation", "D. Reasonable and informed third party assessment", "E. Actions taken and proposed", "F. Safeguard effectiveness", "G. Residual threats", "H. Prioritised next steps", "I. Overall ethical conclusion and limitations"):
            self.assertIn("## " + heading, report)
        self.assertIn("Self\\-interest — source 1", report)
        self.assertIn("Self\\-interest — source 2", report)
        self.assertIn("CFO asked me to go easy", report)
        self.assertNotIn("Advocacy", report)
        self.assertNotIn("Self\\-review", report)
        self.assertIn("revenue judgment", report)

    def test_planned_review_is_not_presented_as_implemented_or_effective(self):
        case, snapshot = case_fixture()
        case.actions = [CaseAction("review-action", "Request an independent revenue review", "independent_review", "Planned", threat_ids=tuple(t.id for t in snapshot.threats))]
        report = self.report(case, snapshot)
        self.assertIn("**Recorded stage:** Planned", report)
        self.assertIn("completed implementation and effectiveness are not established", report)
        self.assertNotIn(r"Implemented \(reported\)", report)
        self.assertNotIn("Effectiveness Established", report)
        self.assertIn("does not establish that all relevant threats", report)

    def test_implemented_stage_does_not_upgrade_a_negative_effectiveness_assessment(self):
        case, snapshot = case_fixture()
        case.actions = [CaseAction("review-action", "Independent revenue review", "independent_review", "Implemented", threat_ids=tuple(t.id for t in snapshot.threats))]
        report = self.report(case, snapshot)
        self.assertIn(r"Implemented \(reported\)", report)
        self.assertIn("effectiveness are not established", report)
        self.assertNotIn("Effectiveness Established", report)

    def test_supported_effectiveness_is_qualified_and_not_certification(self):
        case, snapshot = case_fixture()
        case.actions = [CaseAction("review-action", "Independent revenue review", "independent_review", "Implemented", threat_ids=tuple(t.id for t in snapshot.threats), reviewed=True)]
        report = self.report(case, snapshot, effective=True)
        self.assertIn("Effectiveness Established", report)
        self.assertIn("conditional", report)
        self.assertIn("not verification performed by this application", report)
        self.assertIn("no generative AI, independent fact verification, professional validation or certified ethical opinion", report)

    def test_future_recovery_is_an_attributed_claim(self):
        case, snapshot = case_fixture()
        case.facts.append(CaseFact("f-claim", "cfo", "claim", "Inventory may recover in value next year", excerpt="inventory may recover", attribution="cfo"))
        report = self.report(case, snapshot)
        self.assertIn("CFO: Inventory may recover in value next year", report)
        self.assertIn("reported claim, not verified evidence", report)
        self.assertNotIn("Inventory will recover", report)

    def test_unknowns_are_human_descriptions_not_internal_keys(self):
        case, snapshot = case_fixture()
        case.facts.append(CaseFact("f-participation", "cfo", "participation", "Unknown", status="unknown", source="user"))
        report = self.report(case, snapshot)
        self.assertIn("CFO's participation in the relevant work remains unknown", report)
        self.assertNotIn("f-participation", report)
        self.assertNotIn("t-pressure", report)
        self.assertNotRegex(report, r"\b(?:answer|review|context)\.[A-Za-z_]")

    def test_report_does_not_mutate_the_case_or_store_conclusions(self):
        case, snapshot = case_fixture()
        before = deepcopy(case)
        report = self.report(case, snapshot)
        self.assertEqual(case, before)
        self.assertNotIn("conclusion", vars(case))
        self.assertTrue(report.endswith("\n"))

    def test_unreviewed_account_cannot_look_verified(self):
        case, snapshot = case_fixture()
        case.reviewed = False
        case.facts[2].reviewed = False
        report = self.report(case, snapshot)
        self.assertIn("account awaiting user review", report)
        self.assertIn("awaiting user review", report)
        self.assertIn("no positive conclusion should rely on unreviewed material assumptions", report)

    def test_unspecified_actions_are_not_reported_as_not_taken(self):
        report = self.report()
        self.assertIn("does not establish what relevant action has already been taken", report)
        self.assertNotIn("**Recorded stage:** Not Taken", report)

    def test_action_coverage_does_not_expose_or_silently_accept_unmapped_ids(self):
        case, snapshot = case_fixture()
        case.actions = [CaseAction("a-unknown", "Earlier reported action", threat_ids=("t-old-unknown",))]
        report = self.report(case, snapshot)
        self.assertIn("Coverage of current threats needs clarification", report)
        self.assertNotIn("t-old-unknown", report)
        self.assertNotIn("a-unknown", report)

    def test_source_markdown_and_html_are_escaped(self):
        case, snapshot = case_fixture()
        case.actors[1].label = '<script>alert("test")</script>'
        case.facts[2].excerpt = 'My bonus <img src=x onerror=alert(1)> [click](http://example.com)'
        report = self.report(case, snapshot)
        self.assertNotIn("<script>", report)
        self.assertNotIn("<img", report)
        self.assertIn("&lt;img", report)
        self.assertIn("\\[click\\]", report)

    def test_without_decision_or_findings_no_clearance_is_invented(self):
        case = CaseState("A situation concerns me.")
        snapshot = ReasoningSnapshot((), (), (), limitations=("Professional decision is not established.",))
        report = self.report(case, snapshot)
        self.assertIn("activity has not been established", report)
        self.assertIn("not assurance that threats are absent", report)
        self.assertIn("not independently verified", report)


    def test_described_records_are_attributed_without_document_authentication(self):
        case, snapshot = case_fixture()
        case.actions = [CaseAction(
            "review-action", "Independent revenue review", "independent_review", "Implemented",
            threat_ids=tuple(t.id for t in snapshot.threats),
            evidence_detail="Review memorandum records the challenged revenue assumptions and their resolution.",
        )]
        report = self.report(case, snapshot)
        self.assertIn("Review memorandum records the challenged revenue assumptions", report)
        self.assertIn("has not authenticated them", report)

    def test_real_engine_report_keeps_personal_and_firm_interest_sources_separate(self):
        case, _ = case_fixture()
        report = build_case_report(case)
        self.assertIn("Self\\-interest — source 1", report)
        self.assertIn("Self\\-interest — source 2", report)
        self.assertIn("My bonus", report)
        self.assertIn("firm's contract renewal", report)
        self.assertIn("CFO asked me to go easy", report)
        self.assertIn("not establish", report)
        self.assertNotRegex(report, r"threat-[0-9a-f]+")

    def test_real_report_recomputes_after_withdrawing_a_material_fact(self):
        case, _ = case_fixture()
        first = build_case_report(case)
        case.facts[2].status = "withdrawn"
        case.revision += 1
        second = build_case_report(case)
        self.assertIn("My bonus", first)
        self.assertNotIn("My bonus", second)
        self.assertIn("contract renewal", second)
        self.assertIn("**Revision:** 1", second)
        self.assertNotEqual(first, second)


if __name__ == '__main__':
    unittest.main()
