"""Scenario-driven UI regressions through the real Streamlit session harness.

These checks distinguish source/confirmation from derived assessments. Browser
localStorage itself is exercised separately in Chromium, not claimed by AppTest.
"""

from copy import deepcopy
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from objectivity.examples import EXAMPLE_SCENARIO
from objectivity.progress import export_progress, import_progress
from tests.test_general_prefill_app import AcknowledgedBrowserStore


APP = Path(__file__).resolve().parents[1] / "app.py"
PROPERTY_EMPLOYMENT = (
    "You are a financial accountant reviewing a property valuation prepared by "
    "Cedar Valuations. Your sister works for Cedar Valuations. You do not know "
    "whether she participated in the valuation."
)
MULTIPLE_INTERESTS = (
    "You are an audit manager reviewing revenue recognition. Your annual "
    "performance bonus depends on reported profit. Your firm's tax advisory "
    "contract renewal depends on a smooth audit. The CFO warns that the "
    "contract will not be renewed unless you accept the revenue judgment."
)
PLANNED_REVIEW = MULTIPLE_INTERESTS + " I have requested an independent review of the revenue judgement."
UNFAMILIAR = (
    "In my capacity as a conservation grants assessor I compare proposals from "
    "two restoration charities. My sister holds shares in a supplier to one "
    "charity. The grants director says my promotion depends on favouring that "
    "charity."
)
BONUS_CASE = (
    "You are a financial accountant preparing year-end financial statements. "
    "Your annual performance bonus depends on the company's profit target."
)


class ScenarioCaseAppTests(unittest.TestCase):
    def setUp(self):
        self.bridge_patch = patch("objectivity.progress_ui.browser_storage", return_value=None)
        self.bridge_patch.start()
        self.addCleanup(self.bridge_patch.stop)
        self.app = AppTest.from_file(str(APP), default_timeout=15).run()
        self.healthy()

    def healthy(self):
        self.assertEqual(len(self.app.exception), 0)
        self.assertLessEqual(len(self.app.radio), 1, "Only one focused question may be active")

    def widget(self, kind, label):
        return next(item for item in getattr(self.app, kind) if item.label == label)

    def click(self, label):
        self.widget("button", label).click().run()
        self.healthy()

    def begin(self, scenario):
        self.widget("text_area", "Your scenario").input(scenario)
        self.click("Review scenario")
        self.assertEqual(self.app.session_state["view"], "identify")
        self.assertIsNotNone(self.case())

    def case(self):
        return self.app.session_state["assessment"].case_state

    def text(self):
        return "\n".join(
            item.value
            for kind in ("markdown", "caption", "text", "info", "warning", "subheader", "success", "header")
            for item in getattr(self.app, kind)
        )

    def reasoning(self):
        from dataclasses import replace
        from objectivity.case_reasoning import reason_case
        from objectivity.case_questions import plan_questions
        snapshot = reason_case(self.case())
        return replace(snapshot, questions=plan_questions(self.case(), snapshot).questions)

    def main_text_without_expanders(self):
        """Inspect the main reading path without optional source/edit records."""
        values = []
        def visit(node):
            if getattr(node, 'type', '') == 'expander':
                return
            value = getattr(node, 'value', None)
            if isinstance(value, str):
                values.append(value)
            for child in getattr(node, 'children', {}).values():
                visit(child)
        visit(self.app.main)
        return '\n'.join(values)

    def round_trip(self):
        return import_progress(export_progress(
            self.app.session_state["assessment"], self.app.session_state["review_state"],
            self.app.session_state["address_state"], self.app.session_state["view"],
        ))

    def restore(self, snapshot):
        self.app.session_state["assessment"] = deepcopy(snapshot.assessment)
        self.app.session_state["review_state"] = deepcopy(snapshot.review)
        self.app.session_state["address_state"] = deepcopy(snapshot.address)
        self.app.session_state["view"] = snapshot.view
        self.app.session_state["widget_generation"] += 1
        for key in ("edit_answer_id", "edit_review_id", "edit_address_id"):
            self.app.session_state[key] = None
        self.app.run()
        self.healthy()

    def answer_material(self, choice, explanation=""):
        question = self.reasoning().questions[0]
        if question.options:
            self.widget("radio", question.prompt).set_value(choice)
        else:
            self.widget("text_input", question.prompt).input(choice)
        self.widget("text_area", "Additional explanation (optional)").input(explanation)
        self.click("Record answer and continue")
        self.assertIn(question.id, self.case().answers)
        return question

    def confirm_account(self):
        self.widget("checkbox", "These records reflect my account, including uncertainties.").check()
        self.click("Confirm scenario and continue")
        self.assertTrue(self.case().reviewed)
        self.assertEqual(self.app.session_state["view"], "case_evaluate")

    def to_actions(self):
        if self.app.session_state["view"] == "identify":
            self.confirm_account()
        self.assertEqual(self.app.session_state["view"], "case_evaluate")
        self.click("Review existing actions")
        self.assertEqual(self.app.session_state["view"], "case_address")

    def expand_action_editor(self):
        expander = self.widget("expander", "Add or edit an action record")
        expander.expand().run()
        self.healthy()

    def save_review(self, stage, evidence=""):
        self.expand_action_editor()
        self.widget("text_area", "What has been done or proposed?").input(
            "Independent review of the year-end judgments and the bonus-linked influence"
        )
        self.widget("selectbox", "Type of response").select("independent_review")
        self.widget("selectbox", "Reported action status").select(stage)
        self.widget("multiselect", "Threats this action addresses").set_value(
            [threat.id for threat in self.reasoning().threats]
        )
        self.widget("text_area", "Records or outcome evidence (reported, not authenticated)").input(evidence)
        self.widget("checkbox", "These action details reflect my reported account.").check()
        self.click("Save action record")

    def revise_action_evidence(self, criterion, choice, records):
        self.widget("selectbox", "Action record").select(self.case().actions[0].id).run()
        self.healthy()
        self.widget("selectbox", "Action evidence to revise").select(criterion).run()
        self.healthy()
        self.widget("selectbox", "Revised evidence answer").select(choice)
        self.widget("text_area", "Revised supporting record description").input(records)
        self.widget("checkbox", "I have reviewed this action and its coverage against the current account.").check()
        self.click("Correct action evidence and reassess")

    def complete_action_checks(self):
        from objectivity.case_actions import action_questions
        checks = {
            "independence": "Yes", "competence": "Yes", "authority": "Yes",
            "coverage": "All linked circumstances", "timing": "Before reliance",
            "outcome": "No continuing influence identified", "evidence": "Records described",
        }
        seen = []
        for _ in range(10):
            questions = action_questions(self.case())
            if not questions:
                return seen
            question = questions[0]
            self.assertNotIn(question.key, seen)
            seen.append(question.key)
            self.widget("radio", question.prompt).set_value(checks[question.key])
            self.click("Record action evidence")
        self.fail("Complete review evidence must not create an endless follow-up loop")

    def test_new_default_confirms_concise_account_before_main_threat_assessment(self):
        self.begin(EXAMPLE_SCENARIO)
        self.assertFalse(self.case().reviewed)
        self.assertFalse(self.app.session_state["assessment"].confirmed)
        kinds = {threat.kind for threat in self.reasoning().threats}
        self.assertTrue({"Familiarity", "Intimidation", "Self-interest"} <= kinds)
        self.assertNotIn("Self-review", kinds)
        self.assertNotIn("Advocacy", kinds)
        text = self.text().lower()
        self.assertIn("understand your scenario", text)
        self.assertIn("objectivity", text)
        self.assertIn("not independently verified", text)
        self.assertFalse(self.app.radio, "Confirmation must not turn into a mandatory questionnaire")
        self.assertFalse(any("Potential " in item.value for item in self.app.subheader))
        self.assertNotIn("Review existing actions", [button.label for button in self.app.button])
        self.confirm_account()
        self.assertIn("Step 2: Identify & Evaluate Threats", self.text())
        for threat in self.reasoning().threats:
            self.assertIn(threat.kind, self.text())
            self.assertTrue(threat.evidence_ids)
            for fact_id in threat.evidence_ids:
                self.assertTrue(any(fact.id == fact_id for fact in self.case().facts))

    def test_same_category_sources_remain_separate_and_owner_attributed(self):
        self.begin(MULTIPLE_INTERESTS)
        threats = [threat for threat in self.reasoning().threats if threat.kind == "Self-interest"]
        self.assertGreaterEqual(len(threats), 2)
        self.assertEqual(len({threat.id for threat in threats}), len(threats))
        interests = [fact for fact in self.case().facts if fact.predicate == "interest" and fact.status == "reported"]
        self.assertGreaterEqual(len({fact.subject for fact in interests}), 2)
        self.assertTrue(any("bonus" in fact.value.lower() for fact in interests))
        self.assertTrue(any("contract" in fact.value.lower() for fact in interests))
        self.assertNotIn("Advocacy", {threat.kind for threat in self.reasoning().threats})

    def test_confirmation_requires_acknowledgement_without_adding_questions(self):
        self.begin(EXAMPLE_SCENARIO)
        self.click('Confirm scenario and continue')
        self.assertEqual(self.app.session_state['view'], 'identify')
        self.assertFalse(self.case().reviewed)
        self.assertTrue(self.app.warning)
        self.assertFalse(self.app.radio)
        self.confirm_account()
        self.assertTrue(self.case().reviewed)
        self.assertTrue(all(f.status != 'independently_verified' for f in self.case().facts))

    def test_confirmation_summary_keeps_original_sources_and_technical_editing_optional(self):
        self.begin(EXAMPLE_SCENARIO)
        primary = self.main_text_without_expanders()
        self.assertNotIn(EXAMPLE_SCENARIO, primary)
        self.assertNotIn('answer.', primary)
        self.assertNotIn('basis_signature', primary)
        self.assertIn('CFO', primary)
        self.assertIn('revenue', primary.lower())
        self.assertTrue(self.app.expander)
        for field in ('role', 'decision', 'pressure'):
            fact = next(f for f in self.case().facts if f.predicate == field)
            self.assertTrue(fact.excerpt, 'Editable suggestions retain their exact scenario source')

    def test_one_guided_question_exposes_relevance_and_impact_in_the_main_reading_path(self):
        self.begin(EXAMPLE_SCENARIO)
        self.confirm_account()
        question = self.reasoning().questions[0]
        self.assertEqual(len(self.app.radio), 1)
        self.assertEqual(self.app.radio[0].label, question.prompt)
        primary = self.main_text_without_expanders()
        self.assertIn(question.why, primary)
        self.assertIn(question.impact, primary)
        self.assertTrue(any(threat.kind in primary for threat in self.reasoning().threats
                            if threat.id in question.threat_ids))


    def test_step3_shows_case_specific_safeguards_before_action_history(self):
        self.begin(BONUS_CASE)
        self.confirm_account()
        self.to_actions()
        text = self.text()
        self.assertIn('Recommended safeguards', text)
        self.assertIn('Problem identified', text)
        self.assertIn('Primary safeguard', text)
        self.assertIn('Alternative if the primary response is unavailable', text)
        self.assertIn('Supporting actions and evidence', text)
        self.assertIn('Existing or planned actions', text)
        self.assertLess(text.index('Recommended safeguards'), text.index('Existing or planned actions'))
        self.assertNotIn('What steps, if any, have you already taken', text)

    def test_recorded_unknown_participation_does_not_trigger_an_artificial_question(self):
        self.begin(PROPERTY_EMPLOYMENT)
        self.confirm_account()
        self.assertFalse(self.reasoning().questions)
        self.assertFalse(self.app.radio)
        self.assertIn('Familiarity', self.text())
        self.assertIn('Significance remains uncertain', self.text())
        self.to_actions()
        self.assertIn('Recommended safeguards', self.text())
        self.assertIn('Existing or planned actions', self.text())
        self.assertNotIn('What steps, if any, have you already taken to address these concerns?', self.text())

    def test_acceptable_condition_is_retained_without_forced_safeguards_and_in_report(self):
        from objectivity.address import AddressState
        from objectivity.case_actions import action_questions, assess_actions
        from objectivity.case_model import CaseActor, CaseFact, CaseState
        from objectivity.case_reasoning import ACCEPTABLE
        from objectivity.case_workflow import review_case
        from objectivity.models import Assessment
        from objectivity.review import ReviewState
        case = CaseState(
            'I review a valuation. I report a shareholding unrelated to this decision.',
            actors=[CaseActor('user', 'You', 'Financial accountant'), CaseActor('firm', 'Other company', kind='organisation')],
            facts=[
                CaseFact('role', 'user', 'role', 'Financial accountant', source='user'),
                CaseFact('decision', 'user', 'decision', 'Review an inventory valuation', source='user'),
                CaseFact('shares', 'user', 'interest', 'Shareholding in an unrelated company', 'firm', source='user'),
                CaseFact('connection', 'user', 'interest_connection', 'No', 'firm', source='user'),
            ],
        )
        review_case(case)
        self.restore(import_progress(export_progress(
            Assessment(scenario=case.scenario, case_state=case), ReviewState(), AddressState(), 'case_evaluate',
        )))
        self.assertEqual(len(self.reasoning().threats), 1)
        self.assertEqual(self.reasoning().evaluations[0].outcome, ACCEPTABLE)
        self.assertFalse(self.app.radio)
        self.assertIn('Recorded circumstances narrow this potential threat', self.text())
        self.assertNotIn('At an acceptable level', self.text())
        self.to_actions()
        self.assertFalse(action_questions(self.case()))
        self.assertFalse(self.app.radio)
        self.assertFalse(self.case().actions, 'Protective circumstances must not be invented as completed actions')
        self.assertTrue(all(outcome.status == ACCEPTABLE for outcome in assess_actions(self.case()).outcomes))
        self.click('Generate Objectivity report')
        report = self.text()
        self.assertIn('Self', report)
        self.assertIn('At an acceptable level', report)
        self.assertIn('ADDRESS', report)
        self.assertNotIn('Effectiveness Established', report)

    def test_family_employment_does_not_invent_participation(self):
        self.begin(PROPERTY_EMPLOYMENT)
        case = self.case()
        self.assertTrue(any(fact.predicate == "family_relationship" for fact in case.facts))
        self.assertTrue(any(fact.predicate == "employment" for fact in case.facts))
        participation = [fact for fact in case.facts if fact.predicate == "participation"]
        self.assertFalse(any(fact.value == "Yes" and fact.status == "reported" for fact in participation))
        self.assertIn("Familiarity", {threat.kind for threat in self.reasoning().threats})
        self.assertNotIn("Self-review", {threat.kind for threat in self.reasoning().threats})

    def test_unfamiliar_scenario_has_summary_without_six_mandatory_context_fields(self):
        self.begin(UNFAMILIAR)
        self.assertEqual(self.app.session_state["view"], "identify")
        self.assertFalse(self.case().reviewed)
        self.assertTrue(self.reasoning().threats)
        self.assertNotEqual({threat.kind for threat in self.reasoning().threats}, {
            "Self-interest", "Self-review", "Advocacy", "Familiarity", "Intimidation",
        })
        self.assertNotIn("Confirm context and continue", [button.label for button in self.app.button])
        self.assertFalse(self.app.radio)
        self.assertIn("Confirm scenario and continue", [button.label for button in self.app.button])

    def test_source_ledger_and_stage_round_trip_without_importing_findings(self):
        self.begin(EXAMPLE_SCENARIO)
        original = deepcopy(self.case())
        restored = self.round_trip()
        self.assertEqual(restored.view, "identify")
        self.assertEqual(restored.assessment.case_state, original)
        self.assertFalse(restored.assessment.case_state.reviewed)
        self.restore(restored)
        self.assertEqual(self.case(), original)
        self.assertEqual(
            self.reasoning().threats,
            __import__("objectivity.case_reasoning", fromlist=["reason_case"]).reason_case(original).threats,
        )

    def test_requested_review_remains_planned_source_action(self):
        self.begin(PLANNED_REVIEW)
        actions = self.case().actions
        self.assertTrue(actions, "An explicitly requested review should be visible as a source action")
        reviews = [action for action in actions if action.kind == "independent_review"]
        self.assertTrue(reviews)
        self.assertTrue(all(action.stage == "Planned" for action in reviews))
        self.assertFalse(any(action.stage == "Effectiveness Established" for action in actions))
        self.assertFalse(self.case().actions_reviewed)

    def test_scenario_action_is_prefilled_for_review_instead_of_reentered(self):
        self.begin(PLANNED_REVIEW)
        original = deepcopy(self.case().actions[0])
        self.to_actions()
        self.expand_action_editor()
        self.assertEqual(self.widget('selectbox', 'Action record').value, original.id)
        self.assertEqual(self.widget('text_area', 'What has been done or proposed?').value, original.description)
        self.assertEqual(self.widget('selectbox', 'Reported action status').value, 'Planned')
        self.assertFalse(self.app.radio, 'A known Planned action needs no implementation-evidence questionnaire')

    def test_prefilled_detail_can_be_corrected_before_first_confirmation(self):
        self.begin(EXAMPLE_SCENARIO)
        role = next(f for f in self.case().facts if f.predicate == 'role')
        self.widget('selectbox', 'Choose reported information to correct').select(role.id).run()
        self.widget('text_area', 'Corrected detail').input('Engagement quality reviewer')
        self.click('Save correction and reassess')
        self.assertFalse(self.case().reviewed)
        self.assertFalse(self.app.radio)
        self.assertIn('Engagement quality reviewer', self.main_text_without_expanders())
        self.assertTrue(any(f.id == role.id and f.value != 'Engagement quality reviewer'
                            for f in self.case().fact_history))
        self.confirm_account()
        self.assertEqual(next(f.value for f in self.case().facts if f.id == role.id), 'Engagement quality reviewer')
        self.assertEqual(self.round_trip().view, 'case_evaluate')

    def test_missing_information_does_not_block_evaluation_or_hide_qualified_report(self):
        self.begin(UNFAMILIAR)
        pending = [question.id for question in self.reasoning().questions]
        self.assertTrue(pending)
        self.to_actions()
        self.assertFalse(self.case().answers)
        self.assertTrue(self.case().reviewed)
        self.assertEqual(pending, [question.id for question in self.reasoning().questions])
        self.click("Existing actions are not known")
        self.assertFalse(self.case().actions, "Unknown action history is not a declaration of no action")
        self.click("Generate Objectivity report")
        self.assertEqual(self.app.session_state["view"], "case_report")
        report = self.text()
        self.assertIn("Conditional assessment", report)
        self.assertIn("unknown", report.lower())
        self.assertNotIn("Effectiveness Established", report)

    def test_explicit_unknowns_are_not_repeated_and_survive_progress_restore(self):
        self.begin(UNFAMILIAR)
        self.confirm_account()
        answered = []
        for _ in range(10):
            if not self.reasoning().questions:
                break
            question = self.reasoning().questions[0]
            self.assertNotIn(question.id, answered)
            answered.append(self.answer_material("Unknown", "I cannot establish this from the available account.").id)
        else:
            self.fail("Explicit Unknown answers must not cause an endless clarification loop")
        self.assertGreater(len(answered), 1)
        self.assertTrue(all(answer.choice == "Unknown" for answer in self.case().answers.values()))
        self.assertFalse(self.app.radio)
        before = deepcopy(self.case())
        self.restore(self.round_trip())
        self.assertEqual(self.case(), before)
        self.assertFalse(self.reasoning().questions)
        self.assertTrue(any(fact.status == "unknown" for fact in self.case().facts))
        self.to_actions()
        self.click("Generate Objectivity report")
        self.assertIn("remains unknown", self.text())

    def test_source_correction_recalculates_findings_and_archives_only_dependent_answers(self):
        self.begin(EXAMPLE_SCENARIO)
        self.confirm_account()
        responsibility = self.answer_material("I supervise or review the work")
        # The threat-grouped interview completes the first threat and asks
        # pressure-specific Identify/Evaluate questions before changed work.
        for _ in range(7):
            if self.reasoning().questions[0].predicate == 'work_changed':
                break
            self.answer_material('Unknown')
        pressure_question = self.reasoning().questions[0]
        self.assertEqual(pressure_question.predicate, "work_changed")
        self.answer_material("Yes", "I had softened the challenge before raising my concern.")
        pressure = next(fact for fact in self.case().facts if fact.predicate == "pressure")
        self.widget("selectbox", "Choose reported information to correct").select(pressure.id).run()
        self.healthy()
        self.widget("text_area", "Corrected detail").input("No request or pressure from the CFO occurred; I correct my earlier account.")
        self.widget("selectbox", "Evidence status").select("denied")
        self.click("Save correction and reassess")
        self.assertEqual(self.app.session_state["view"], "identify")
        self.assertNotIn("Intimidation", {threat.kind for threat in self.reasoning().threats})
        self.assertIn("Familiarity", {threat.kind for threat in self.reasoning().threats})
        self.assertIn(responsibility.id, self.case().answers)
        self.assertNotIn(pressure_question.id, self.case().answers)
        self.assertTrue(any(record.value == "Yes" and "changed" in record.reason.lower()
                            for record in self.case().history))
        self.assertTrue(any(fact.id == pressure.id and fact.status == "reported"
                            for fact in self.case().fact_history))
        self.assertFalse(self.case().reviewed)
        self.assertFalse(self.app.radio, "Corrected facts need review before ethical questioning resumes")
        restored = self.round_trip().assessment.case_state
        self.assertEqual(restored.history, self.case().history)
        self.assertNotIn(pressure_question.id, restored.answers)

    def test_planned_review_editor_never_establishes_effectiveness(self):
        from objectivity.case_actions import SUPPORTED, assess_actions
        self.begin(BONUS_CASE)
        self.assertFalse(any(q.predicate == 'decision_responsibility' for q in self.reasoning().questions))
        self.confirm_account()
        self.to_actions()
        self.save_review("Planned", "A review has been requested; no work or outcome has yet been checked.")
        result = assess_actions(self.case())
        self.assertTrue(self.case().actions_reviewed)
        self.assertEqual(result.actions[0].status, "Planned")
        self.assertFalse(result.actions[0].effective)
        self.assertTrue(all(outcome.status != SUPPORTED for outcome in result.outcomes))
        self.click("Generate Objectivity report")
        self.assertIn("completed implementation and effectiveness are not established", self.text())
        self.assertNotIn("Effectiveness Established", self.text())

    def test_implemented_review_requires_case_specific_checks_before_conditional_support(self):
        from objectivity.case_actions import SUPPORTED, action_questions, assess_actions
        self.begin(BONUS_CASE)
        self.assertFalse(any(q.predicate == 'decision_responsibility' for q in self.reasoning().questions))
        self.confirm_account()
        self.to_actions()
        self.save_review("Implemented", "Signed review notes describe the year-end estimates, bonus conflict, challenge and changes before sign-off.")
        self.assertFalse(any(record.effective for record in assess_actions(self.case()).actions))
        checks = {
            "independence": "Yes", "competence": "Yes", "authority": "Yes",
            "coverage": "All linked circumstances", "timing": "Before reliance",
            "outcome": "No continuing influence identified", "evidence": "Records described",
        }
        seen = []
        for _ in range(10):
            questions = action_questions(self.case())
            if not questions:
                break
            question = questions[0]
            self.assertNotIn(question.key, seen)
            seen.append(question.key)
            self.widget("radio", question.prompt).set_value(checks[question.key])
            self.click("Record action evidence")
        else:
            self.fail("Complete review evidence must not create an endless follow-up loop")
        self.assertEqual(set(seen), set(checks))
        result = assess_actions(self.case())
        self.assertTrue(result.actions[0].effective)
        self.assertTrue(all(outcome.status == SUPPORTED for outcome in result.outcomes))
        self.assertIn("conditionally", result.conclusion)
        self.click("Generate Objectivity report")
        self.assertIn("Signed review notes describe", self.text())
        self.assertIn("not authenticated", self.text())
        self.assertIn("conditionally", self.text())
        self.assertEqual(self.round_trip().view, "case_report")

    def test_unknown_action_evidence_stops_questions_but_is_revisable(self):
        from objectivity.case_actions import SUPPORTED, action_questions, assess_actions
        self.begin(BONUS_CASE)
        self.assertFalse(any(q.predicate == 'decision_responsibility' for q in self.reasoning().questions))
        self.confirm_account()
        self.to_actions()
        self.save_review("Implemented", "Review notes exist; the reviewer's independence is not yet known.")
        question = action_questions(self.case())[0]
        self.assertEqual(question.key, "independence")
        self.widget("radio", question.prompt).set_value("Unknown")
        self.click("Record action evidence")
        self.assertFalse(action_questions(self.case()))
        self.assertFalse(self.app.radio)
        self.assertFalse(any(record.effective for record in assess_actions(self.case()).actions))
        self.app.run()
        self.healthy()
        self.assertFalse(self.app.radio, "An explicitly Unknown criterion must not be asked on every rerun")
        self.revise_action_evidence(
            "independence", "Yes",
            "Review notes identify a reviewer outside the bonus decision and document the challenge before sign-off.",
        )
        self.assertEqual(self.case().actions[0].checks["independence"], "Yes")
        self.assertEqual(action_questions(self.case())[0].key, "competence")
        self.assertTrue(any(record.checks.get("independence") == "Unknown"
                            for record in self.case().action_history))
        self.assertNotIn("independence", self.complete_action_checks())
        self.assertTrue(all(outcome.status == SUPPORTED for outcome in assess_actions(self.case()).outcomes))
        restored = self.round_trip()
        self.restore(restored)
        self.assertEqual(self.case().actions[0].checks["independence"], "Yes")
        self.assertFalse(action_questions(self.case()))
        self.assertTrue(any(record.checks.get("independence") == "Unknown"
                            for record in self.case().action_history))

    def test_correcting_effectiveness_evidence_recalculates_residual_and_report(self):
        from objectivity.case_actions import SUPPORTED, UNACCEPTABLE, assess_actions
        self.begin(BONUS_CASE)
        self.assertFalse(any(q.predicate == 'decision_responsibility' for q in self.reasoning().questions))
        self.confirm_account()
        self.to_actions()
        self.save_review("Implemented", "Signed review notes describe the estimates, bonus conflict and resolution before sign-off.")
        self.complete_action_checks()
        self.assertTrue(all(outcome.status == SUPPORTED for outcome in assess_actions(self.case()).outcomes))
        self.click("Generate Objectivity report")
        self.assertIn("conditionally", self.text())
        self.click("Revisit actions and residual threats")
        self.revise_action_evidence(
            "outcome", "Continuing influence remains",
            "A later outcome check shows the bonus-linked judgment remains unchanged despite the reviewer's challenge.",
        )
        result = assess_actions(self.case())
        self.assertFalse(result.actions[0].effective)
        self.assertTrue(result.actions[0].failed)
        self.assertTrue(all(outcome.status == UNACCEPTABLE for outcome in result.outcomes))
        self.assertTrue(any(record.checks.get("outcome") == "No continuing influence identified"
                            for record in self.case().action_history))
        self.click("Generate Objectivity report")
        self.assertIn("later outcome check", self.text())
        self.assertNotIn("Effectiveness Established", self.text())
        self.assertEqual(self.round_trip().assessment.case_state.actions[0].checks["outcome"],
                         "Continuing influence remains")

    def test_report_has_nine_professional_sections_download_and_no_engine_ids(self):
        self.begin(EXAMPLE_SCENARIO)
        self.to_actions()
        self.click("No relevant action has been taken")
        self.click("Generate Objectivity report")
        report = next(item.value for item in self.app.markdown
                      if item.value.startswith("# Objectivity Ethical Assessment Report"))
        self.assertEqual(re.findall(r"^## ([A-I])\. ", report, re.MULTILINE), list("ABCDEFGHI"))
        for record in (*self.case().facts, *self.reasoning().threats):
            self.assertNotIn(record.id, report)
        self.assertNotIn("answer.", report)
        self.assertNotIn("review.objectivity_basis", report)
        self.assertIn("revenue recognition", report.lower())
        self.assertIn("Not Taken", report)
        self.assertTrue(any(element.proto.label == "Download Objectivity report (Markdown)"
                            for element in self.app.get("download_button")))
        self.click("Revisit actions and residual threats")
        self.assertEqual(self.app.session_state["view"], "case_address")

    def test_legacy_reassessment_is_explicit_and_retains_original_answers_and_history(self):
        from objectivity.models import Answer, ArchivedAnswer
        from tests.test_progress import cfo_case
        assessment, review, address = cfo_case()
        assessment.archive.append(ArchivedAnswer("pressure_effect", Answer("Unknown"), "Earlier answer revised", 1))
        old = deepcopy(assessment)
        restored = import_progress(export_progress(assessment, review, address, "review"))
        self.restore(restored)
        self.assertIsNone(self.case(), "Loading an old assessment must not silently migrate its workflow")
        self.click("Reassess saved case")
        self.assertEqual(self.app.session_state["view"], "identify")
        current = self.app.session_state["assessment"]
        for field in ("scenario", "context", "confirmed", "answers", "archive"):
            self.assertEqual(getattr(current, field), getattr(old, field))
        self.assertTrue(self.case().legacy_records)
        self.assertTrue(any(fact.source == "legacy" for fact in self.case().facts))
        self.assertFalse(self.case().reviewed)
        self.assertTrue(self.reasoning().threats)

    def test_acknowledged_autosave_restores_unconfirmed_summary_for_explicit_resume(self):
        store = AcknowledgedBrowserStore()
        self.bridge_patch.stop()
        with patch("objectivity.progress_ui.browser_storage", side_effect=store):
            first = AppTest.from_file(str(APP), default_timeout=15).run()
            next(widget for widget in first.text_area if widget.label == "Your scenario").input(EXAMPLE_SCENARIO)
            next(widget for widget in first.button if widget.label == "Review scenario").click().run()
            for _ in range(5):
                first.run()
            self.assertIsNotNone(store.data)
            saved = import_progress(store.data)
            self.assertEqual(saved.view, "identify")
            self.assertIsNotNone(saved.assessment.case_state)
            self.assertFalse(saved.assessment.case_state.reviewed)
            second = AppTest.from_file(str(APP), default_timeout=15).run()
            next(widget for widget in second.button if widget.label == "Resume previous assessment").click().run()
            self.assertEqual(len(second.exception), 0)
            self.assertEqual(second.session_state["view"], "identify")
            self.assertEqual(second.session_state["assessment"].case_state, saved.assessment.case_state)

    def test_acknowledged_autosave_preserves_confirmation_and_combined_stage_on_resume(self):
        store = AcknowledgedBrowserStore()
        self.bridge_patch.stop()
        with patch('objectivity.progress_ui.browser_storage', side_effect=store):
            first = AppTest.from_file(str(APP), default_timeout=15).run()
            next(w for w in first.text_area if w.label == 'Your scenario').input(PROPERTY_EMPLOYMENT)
            next(w for w in first.button if w.label == 'Review scenario').click().run()
            next(w for w in first.checkbox if w.label == 'These records reflect my account, including uncertainties.').check()
            next(w for w in first.button if w.label == 'Confirm scenario and continue').click().run()
            for _ in range(5):
                first.run()
            saved = import_progress(store.data)
            self.assertEqual(saved.view, 'case_evaluate')
            self.assertTrue(saved.assessment.case_state.reviewed)
            second = AppTest.from_file(str(APP), default_timeout=15).run()
            next(w for w in second.button if w.label == 'Resume previous assessment').click().run()
            self.assertFalse(second.exception)
            self.assertEqual(second.session_state['view'], 'case_evaluate')
            self.assertEqual(second.session_state['assessment'].case_state, saved.assessment.case_state)
            self.assertFalse(second.radio, 'Reopening must not invent a question already recorded as Unknown')


if __name__ == "__main__":
    unittest.main()
