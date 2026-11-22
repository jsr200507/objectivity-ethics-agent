"""Portable progress, safe parsing and restored dependency behaviour."""

from copy import deepcopy
import json
import unittest

from objectivity.address import (
    ACTION_OPTIONS, CHECKED, IMPLEMENTED, NO_ACTION, REVIEW, AddressState,
    add_supporting_action, assess_address, eligible_address_questions,
    save_address_answer, sync_address,
)
from objectivity.evaluation import evaluate
from objectivity.examples import EXAMPLE_CONTEXT, EXAMPLE_SCENARIO
from objectivity.models import Assessment, Context
from objectivity.progress import (
    FORMAT_NAME, FORMAT_VERSION, MAX_PROGRESS_BYTES, MAX_RECORDS,
    MAX_TEXT_LENGTH, RULES_VERSION, ProgressError, export_progress, import_progress,
)
from objectivity.questions import confirm_context, next_question, save_answer
from objectivity.report import build_report
from objectivity.review import ReviewState, save_review_answer, sync_review


def empty_case():
    return Assessment(), ReviewState(), AddressState()


def cfo_case():
    assessment, review, address = empty_case()
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
    sync_review(assessment, review)
    save_review_answer(assessment, review, "objectivity_basis", "I am not claiming the threats are addressed")
    sync_address(assessment, review, address)
    return assessment, review, address


def proposed_case():
    case = cfo_case()
    for kind in ACTION_OPTIONS:
        save_address_answer(*case, f"{kind}:0:action", REVIEW)
        save_address_answer(*case, f"{kind}:0:implementation", "Proposed, not yet started")
    return case


def full_familiarity_review(case, slot=0):
    values = {
        "action": REVIEW,
        "implementation": IMPLEMENTED,
        "independence": "Reviewer is independent of the relevant influences",
        "competence": "Relevant competence is established",
        "authority": "Can require changes before the decision is final",
        "scope": "All relevant aspects of this threat were reviewed",
        "timing": "Before the decision or affected work was relied upon",
        "effect": "No continuing influence identified in the outcome check",
        "evidence": CHECKED,
    }
    prefix = f"Familiarity:{slot}:"
    while True:
        question = next((q for q in eligible_address_questions(*case)
                         if q.id.startswith(prefix) and q.id not in case[2].answers), None)
        if question is None:
            break
        save_address_answer(*case, question.id, values[question.id.rsplit(":", 1)[1]])


class ProgressRoundTripTests(unittest.TestCase):
    def test_empty_assessment_can_be_exported_restored_and_cleared(self):
        restored = import_progress(export_progress(*empty_case(), "scenario"))
        self.assertEqual(restored.assessment, Assessment())
        self.assertEqual(restored.review.answers, {})
        self.assertEqual(restored.address.answers, {})
        self.assertEqual(restored.view, "scenario")
        self.assertEqual(restored.warnings, ())

    def test_format_and_rules_versions_are_explicit(self):
        document = json.loads(export_progress(*empty_case(), "scenario"))
        self.assertEqual(document["format"], FORMAT_NAME)
        self.assertEqual(document["schema_version"], FORMAT_VERSION)
        self.assertEqual(document["rules_version"], RULES_VERSION)

    def test_unconfirmed_example_context_is_preserved_without_confirmation(self):
        case = empty_case()
        case[0].scenario = EXAMPLE_SCENARIO
        case[0].context = deepcopy(EXAMPLE_CONTEXT)
        result = import_progress(export_progress(*case, "context"))
        self.assertEqual(result.assessment.context, EXAMPLE_CONTEXT)
        self.assertFalse(result.assessment.confirmed)
        self.assertEqual(evaluate(result.assessment).findings, ())

    def test_partial_clarification_preserves_question_and_explanation(self):
        case = empty_case()
        confirm_context(case[0], EXAMPLE_SCENARIO, EXAMPLE_CONTEXT)
        save_answer(case[0], "pressure_basis", "Implied in the conversation", "Recalled words only.")
        result = import_progress(export_progress(*case, "questions"))
        self.assertEqual(next_question(result.assessment).id, "pressure_consequence")
        self.assertEqual(result.assessment.answers["pressure_basis"].explanation, "Recalled words only.")

    def test_cfo_all_phases_and_report_roundtrip(self):
        case = proposed_case()
        result = import_progress(export_progress(*case, "report"))
        self.assertEqual((result.assessment, result.review, result.address), case)
        self.assertEqual(result.view, "report")
        self.assertEqual(result.warnings, ())
        self.assertEqual(build_report(*case), build_report(result.assessment, result.review, result.address))
        self.assertIn("does not yet establish", assess_address(result.assessment, result.review, result.address).conclusion)

    def test_export_is_deterministic_and_does_not_mutate_state(self):
        case = proposed_case()
        before = deepcopy(case)
        first = export_progress(*case, "address")
        self.assertEqual(first, export_progress(*case, "address"))
        self.assertEqual(case, before)
        restored = import_progress(first)
        self.assertEqual(first, export_progress(restored.assessment, restored.review, restored.address, restored.view))

    def test_json_has_no_signatures_widget_state_or_derived_conclusions(self):
        document = json.loads(export_progress(*proposed_case(), "report"))
        self.assertNotIn("source_signature", document["review"])
        self.assertNotIn("source_signature", document["address"])
        for key in ("findings", "report", "conclusion", "widget_generation", "edit_answer_id"):
            self.assertNotIn(key, document)

    def test_supporting_action_slots_and_checks_are_preserved(self):
        case = cfo_case()
        save_address_answer(*case, "Familiarity:0:action", NO_ACTION)
        add_supporting_action(*case, "Familiarity", REVIEW)
        full_familiarity_review(case, slot=1)
        result = import_progress(export_progress(*case, "address"))
        self.assertEqual(result.address.extra_slots, [("Familiarity", 1)])
        self.assertEqual(result.address.next_slot, 2)
        self.assertEqual(result.address.answers, case[2].answers)
        self.assertEqual(result.address, case[2])
        self.assertEqual(result.address.source_signature, case[2].source_signature)
        self.assertEqual(assess_address(*case), assess_address(result.assessment, result.review, result.address))

    def test_archive_history_across_all_three_phases_survives(self):
        case = proposed_case()
        save_answer(case[0], "pressure_basis", "Implied in the conversation", "Updated explanation only.")
        save_review_answer(case[0], case[1], "objectivity_basis", "I am not claiming the threats are addressed", "Updated account.")
        save_address_answer(*case, "Familiarity:0:implementation", "Requested or in progress", "Awaiting approval.")
        result = import_progress(export_progress(*case, "address"))
        self.assertTrue(result.assessment.archive)
        self.assertTrue(result.review.archive)
        self.assertTrue(result.address.archive)
        self.assertEqual(result.assessment.archive, case[0].archive)
        self.assertEqual(result.review.archive, case[1].archive)
        self.assertEqual(result.address.archive, case[2].archive)

    def test_prior_history_that_is_no_longer_an_active_branch_is_preserved(self):
        case = cfo_case()
        save_answer(case[0], "pressure_basis", "My interpretation only")
        save_answer(case[0], "pressure_support", "No further supporting information")
        sync_review(case[0], case[1])
        sync_address(*case)
        result = import_progress(export_progress(*case, "review"))
        self.assertNotIn("Intimidation", {finding.kind for finding in evaluate(result.assessment).findings})
        self.assertTrue(any(record.question_id == "pressure_consequence" for record in result.assessment.archive))

    def test_imported_answers_stay_user_accounts_not_verified_evidence(self):
        result = import_progress(export_progress(*proposed_case(), "report"))
        self.assertTrue(all("not independently verified" in evidence.status
                            for finding in evaluate(result.assessment, result.review.answers).findings
                            for evidence in finding.evidence))
        self.assertIn("Proposed, not yet started", build_report(result.assessment, result.review, result.address))

    def test_editing_restored_phase_one_invalidates_later_state(self):
        restored = import_progress(export_progress(*proposed_case(), "report"))
        save_answer(restored.assessment, "pressure_basis", "My interpretation only")
        save_answer(restored.assessment, "pressure_support", "No further supporting information")
        sync_review(restored.assessment, restored.review)
        sync_address(restored.assessment, restored.review, restored.address)
        self.assertEqual(restored.address.answers, {})
        self.assertTrue(restored.address.archive)
        self.assertNotIn("Intimidation", {finding.kind for finding in evaluate(restored.assessment).findings})

    def test_editing_restored_review_invalidates_action_findings(self):
        restored = import_progress(export_progress(*proposed_case(), "report"))
        save_review_answer(restored.assessment, restored.review, "objectivity_basis", "Confidence in my own impartiality")
        self.assertFalse(assess_address(restored.assessment, restored.review, restored.address).current)
        sync_address(restored.assessment, restored.review, restored.address)
        self.assertEqual(restored.address.answers, {})

    def test_stale_inapplicable_answer_is_archived_with_warning(self):
        document = json.loads(export_progress(*cfo_case(), "report"))
        document["assessment"]["context"]["pressure"] = "No reported pressure"
        restored = import_progress(json.dumps(document))
        self.assertNotIn("pressure_basis", restored.assessment.answers)
        self.assertTrue(restored.warnings)
        self.assertTrue(any(record.question_id == "pressure_basis" for record in restored.assessment.archive))
        self.assertNotIn("Intimidation", {finding.kind for finding in evaluate(restored.assessment).findings})

    def test_impossible_future_stage_returns_to_context_or_questions(self):
        document = json.loads(export_progress(*empty_case(), "scenario"))
        document["view"] = "report"
        restored = import_progress(json.dumps(document))
        self.assertEqual(restored.view, "scenario")
        self.assertTrue(restored.warnings)
        case = empty_case()
        confirm_context(case[0], EXAMPLE_SCENARIO, EXAMPLE_CONTEXT)
        document = json.loads(export_progress(*case, "questions"))
        document["view"] = "report"
        restored = import_progress(json.dumps(document))
        self.assertEqual(restored.view, "questions")

    def test_later_stage_without_complete_review_returns_to_review(self):
        case = cfo_case()
        case[1].answers.clear()
        document = json.loads(export_progress(*case, "review"))
        document["view"] = "report"
        result = import_progress(json.dumps(document))
        self.assertEqual(result.view, "review")
        self.assertTrue(result.warnings)

    def test_export_archives_stale_downstream_state_without_mutating_original(self):
        case = proposed_case()
        save_answer(case[0], "relationship_contact", "Occasional personal contact")
        before = deepcopy(case)
        restored = import_progress(export_progress(*case, "report"))
        self.assertEqual(case, before)
        self.assertEqual(restored.address.answers, {})
        self.assertTrue(restored.address.archive)
        self.assertEqual(restored.view, "questions")

    def test_existing_assessment_cannot_restore_to_replacement_entry_screen(self):
        for case in (cfo_case(), proposed_case()):
            with self.subTest(confirmed=case[0].confirmed, actions=bool(case[2].answers)):
                result = import_progress(export_progress(*case, "scenario"))
                self.assertEqual(result.view, "context")
                self.assertTrue(result.warnings)
                self.assertEqual(result.assessment, case[0])
                self.assertEqual(result.address.answers, case[2].answers)

    def test_nonempty_unconfirmed_entry_is_moved_to_context_without_data_loss(self):
        for scenario, context in (
            ("My partially described scenario", Context()),
            ("", Context(role="Finance manager", parties="Unknown", decision="")),
            ("", Context(relationship="Close personal relationship")),
        ):
            with self.subTest(scenario=scenario, role=context.role):
                case = empty_case()
                case[0].scenario, case[0].context = scenario, context
                result = import_progress(export_progress(*case, "scenario"))
                self.assertEqual(result.view, "context")
                self.assertEqual(result.assessment.scenario, scenario)
                self.assertEqual(result.assessment.context, context)
                self.assertFalse(result.assessment.confirmed)
                self.assertTrue(result.warnings)

    def test_incomplete_context_draft_is_valid_without_confirmation_claim(self):
        case = empty_case()
        case[0].context = Context(role="Finance manager", parties="Unknown", decision="")
        result = import_progress(export_progress(*case, "context"))
        self.assertEqual(result.view, "context")
        self.assertFalse(result.assessment.confirmed)
        self.assertEqual(result.assessment.context.role, "Finance manager")
        self.assertEqual(result.warnings, ())
        self.assertEqual(evaluate(result.assessment).findings, ())

    def test_actual_valid_workflow_stages_survive_restoration(self):
        scenario_case = empty_case()
        context_case = empty_case()
        context_case[0].scenario = "An unconfirmed scenario"
        questions_case = empty_case()
        confirm_context(questions_case[0], EXAMPLE_SCENARIO, EXAMPLE_CONTEXT)
        review_case = cfo_case()
        review_case[1].answers.clear()
        for view, case in (
            ("scenario", scenario_case), ("context", context_case),
            ("questions", questions_case), ("review", review_case),
            ("address", cfo_case()), ("report", proposed_case()),
        ):
            with self.subTest(view=view):
                result = import_progress(export_progress(*case, view))
                self.assertEqual(result.view, view)
                self.assertEqual(result.warnings, ())


class ProgressValidationTests(unittest.TestCase):
    def document(self):
        return json.loads(export_progress(*cfo_case(), "address"))

    def rejects(self, document):
        with self.assertRaises(ProgressError):
            import_progress(json.dumps(document))

    def test_missing_unknown_and_derived_fields_are_rejected(self):
        for location, name in (("root", "conclusion"), ("assessment", "findings"), ("review", "source_signature"), ("address", "report")):
            with self.subTest(location=location):
                document = self.document()
                target = document if location == "root" else document[location]
                target[name] = "Everything is acceptable"
                self.rejects(document)
        document = self.document()
        del document["assessment"]["context"]
        self.rejects(document)

    def test_unknown_versions_are_rejected(self):
        for field, value in (("format", "another app"), ("schema_version", FORMAT_VERSION + 1), ("schema_version", True), ("rules_version", "future-rules")):
            document = self.document()
            document[field] = value
            self.rejects(document)

    def test_confirmation_and_revision_are_strict_types(self):
        for field, value in (("confirmed", "yes"), ("confirmed", 1), ("revision", True), ("revision", -1), ("revision", 1.5)):
            document = self.document()
            document["assessment"][field] = value
            self.rejects(document)

    def test_context_choices_and_false_verification_are_rejected(self):
        for field, value in (("relationship", "Automatically extracted"), ("basis", "Independently verified by app"), ("role", {})):
            document = self.document()
            document["assessment"]["context"][field] = value
            self.rejects(document)

    def test_confirmed_context_requires_nonempty_details(self):
        document = self.document()
        document["assessment"]["context"]["role"] = "  "
        self.rejects(document)

    def test_unknown_question_and_wrong_answer_choice_rejected(self):
        for id, choice in (("made_up", "Yes"), ("pressure_basis", "Verified pressure")):
            document = self.document()
            document["assessment"]["answers"][id] = {"choice": choice, "explanation": ""}
            self.rejects(document)

    def test_invalid_review_and_address_choices_rejected(self):
        document = self.document()
        document["review"]["answers"]["objectivity_basis"]["choice"] = "Certified compliance"
        self.rejects(document)
        document = self.document()
        document["address"]["answers"]["Familiarity:0:action"] = {"choice": "Certified clearance", "explanation": ""}
        self.rejects(document)

    def test_incompatible_address_fields_and_orphan_slots_rejected(self):
        for id in ("Familiarity:0:verdict", "OtherThreat:0:action", "Familiarity:1:action", "Familiarity:000:action"):
            document = self.document()
            document["address"]["answers"][id] = {"choice": REVIEW, "explanation": ""}
            self.rejects(document)

    def test_duplicate_or_invalid_supporting_slots_rejected(self):
        for slots in ((["Familiarity", 1], ["Familiarity", 1]), (["Familiarity", 1], ["Intimidation", 1]), (["Familiarity", 0],), ([[], 1],), (["Familiarity", True],)):
            document = self.document()
            document["address"]["extra_slots"] = list(slots)
            document["address"]["next_slot"] = 2
            self.rejects(document)

    def test_active_question_labels_cannot_import_a_verdict(self):
        document = json.loads(export_progress(*proposed_case(), "address"))
        document["address"]["prompts"]["Familiarity:0:implementation"] = "Certified compliant"
        self.rejects(document)

    def test_slot_sequence_and_workflow_are_validated(self):
        document = self.document()
        document["address"]["extra_slots"] = [["Familiarity", 5]]
        document["address"]["next_slot"] = 5
        self.rejects(document)
        document = self.document()
        document["view"] = "execute_shell"
        self.rejects(document)

    def test_archive_revision_and_schema_are_validated(self):
        document = self.document()
        document["assessment"]["archive"] = [{
            "question_id": "pressure_basis", "answer": {"choice": "Explicitly stated", "explanation": ""},
            "reason": "An edit", "revision": document["assessment"]["revision"] + 1,
        }]
        self.rejects(document)

    def test_malformed_json_duplicates_nonstandard_numbers_and_utf8_rejected(self):
        for raw in ("{", "[]", "null", '{"format":1,"format":2}', "NaN", "Infinity", b'\xff', '{"x":"\\ud800"}'):
            with self.subTest(raw=repr(raw)):
                with self.assertRaises(ProgressError):
                    import_progress(raw)

    def test_depth_and_file_size_limits(self):
        for raw in ("[" * 2000 + "0" + "]" * 2000, " " * (MAX_PROGRESS_BYTES + 1)):
            with self.assertRaises(ProgressError):
                import_progress(raw)

    def test_text_and_record_count_limits(self):
        document = self.document()
        document["assessment"]["scenario"] = "x" * (MAX_TEXT_LENGTH + 1)
        self.rejects(document)
        document = self.document()
        document["assessment"]["archive"] = [{}] * (MAX_RECORDS + 1)
        self.rejects(document)

    def test_incompatible_nested_data_always_raises_a_progress_error(self):
        for field in ("assessment", "review", "address"):
            for value in (None, [], "text", 5, True):
                with self.subTest(field=field, value=value):
                    document = self.document()
                    document[field] = value
                    self.rejects(document)

    def test_malformed_live_state_never_produces_an_export(self):
        for field, value in (("context", None), ("scenario", None), ("confirmed", "yes")):
            with self.subTest(field=field):
                case = empty_case()
                setattr(case[0], field, value)
                with self.assertRaises(ProgressError):
                    export_progress(*case, "scenario")
        for index in (0, 1, 2):
            with self.subTest(missing_state=index):
                case = list(empty_case())
                case[index] = None
                with self.assertRaises(ProgressError):
                    export_progress(*case, "scenario")

    def test_executable_looking_text_remains_data(self):
        document = self.document()
        text = "__import__('os').system('do-not-run')"
        document["assessment"]["scenario"] = text
        restored = import_progress(json.dumps(document))
        self.assertEqual(restored.assessment.scenario, text)
        report = build_report(restored.assessment, restored.review, restored.address)
        self.assertIn("> \\_\\_import\\_\\_\\(", report)
        self.assertIn("do\\-not\\-run", report)


if __name__ == "__main__":
    unittest.main()
