"""Source-only case persistence, legacy compatibility and safe recalculation."""
from copy import deepcopy
from dataclasses import asdict
import json
import unittest

from objectivity.address import AddressState
from objectivity.case_codec import CASE_RULES_VERSION, CaseCodecError, case_from_dict, case_to_dict
from objectivity.case_model import CaseAction, CaseActor, CaseAnswer, CaseFact, CaseHistory, CaseState
from objectivity.models import Assessment
from objectivity.progress import FORMAT_VERSION, ProgressError, export_progress, import_progress
from objectivity.review import ReviewState
from tests.test_progress import proposed_case


SCENARIO = 'I am an accountant. I review a valuation. The director asked me to ignore the loss. I requested an independent review.'


def sample_case():
    return CaseState(
        SCENARIO,
        actors=[CaseActor('user', 'You', 'Accountant'), CaseActor('director', 'The director', 'Director')],
        facts=[
            CaseFact('role', 'user', 'role', 'Accountant', excerpt='I am an accountant.'),
            CaseFact('decision', 'user', 'decision', 'Review a valuation', excerpt='I review a valuation.'),
            CaseFact('pressure', 'director', 'pressure', 'Ignore the loss', 'user', excerpt='The director asked me to ignore the loss.'),
        ],
    )


def document(case=None, view='identify'):
    case = case or sample_case()
    return json.loads(export_progress(
        Assessment(scenario=case.scenario, case_state=case), ReviewState(), AddressState(), view,
    ))


def legacy_document(schema, case=None):
    original = case or proposed_case()
    value = json.loads(export_progress(*original, 'report'))
    value['schema_version'] = schema
    value['assessment'].pop('case_state')
    if schema == 1:
        value['assessment'].pop('context_clarifications')
    return value, original


class CaseProgressRoundTripTests(unittest.TestCase):
    def test_current_format_keeps_distinct_case_rules_version_and_no_verdicts(self):
        value = document()
        self.assertEqual(FORMAT_VERSION, 3)
        self.assertEqual(value['assessment']['case_state']['rules_version'], CASE_RULES_VERSION)
        state = value['assessment']['case_state']['state']
        for key in ('findings', 'evaluations', 'report', 'conclusion', 'effectiveness'):
            self.assertNotIn(key, state)
        restored = import_progress(json.dumps(value))
        self.assertEqual(restored.assessment.case_state, sample_case())
        self.assertEqual(restored.view, 'identify')
        self.assertFalse(restored.assessment.case_state.reviewed)
        self.assertFalse(restored.assessment.confirmed)

    def test_all_case_views_allow_qualified_analysis_before_global_confirmation(self):
        for view in ('identify', 'case_evaluate', 'case_address', 'case_report'):
            with self.subTest(view=view):
                restored = import_progress(json.dumps(document(view=view)))
                self.assertEqual(restored.view, view)
                self.assertFalse(restored.assessment.confirmed)
                self.assertFalse(restored.assessment.case_state.reviewed)

    def test_case_report_view_without_source_records_moves_back_with_notice(self):
        value = json.loads(export_progress(Assessment(), ReviewState(), AddressState(), 'scenario'))
        value['view'] = 'case_report'
        restored = import_progress(json.dumps(value))
        self.assertEqual(restored.view, 'scenario')
        self.assertTrue(any('no supported case source' in warning for warning in restored.warnings))

    def test_case_source_at_entry_stage_restores_to_identify_not_replacement_entry(self):
        restored = import_progress(json.dumps(document(view='scenario')))
        self.assertEqual(restored.view, 'identify')
        self.assertTrue(restored.warnings)

    def test_schema1_and_schema2_all_phase_saves_keep_legacy_progress(self):
        for schema in (1, 2):
            with self.subTest(schema=schema):
                value, original = legacy_document(schema)
                restored = import_progress(json.dumps(value))
                self.assertEqual((restored.assessment, restored.review, restored.address), original)
                self.assertEqual(restored.view, 'report')
                self.assertIsNone(restored.assessment.case_state)
                latest = json.loads(export_progress(restored.assessment, restored.review, restored.address, restored.view))
                self.assertEqual(latest['schema_version'], 3)
                self.assertIsNone(latest['assessment']['case_state'])

    def test_old_schemas_cannot_smuggle_case_state(self):
        for schema in (1, 2):
            with self.subTest(schema=schema):
                value, _ = legacy_document(schema)
                value['assessment']['case_state'] = case_to_dict(sample_case())
                with self.assertRaises(ProgressError):
                    import_progress(json.dumps(value))

    def test_empty_case_state_keeps_existing_model_equality(self):
        original = Assessment()
        restored = import_progress(export_progress(original, ReviewState(), AddressState(), 'scenario'))
        self.assertEqual(restored.assessment, original)
        self.assertIsNone(restored.assessment.case_state)

    def test_all_source_histories_and_previous_case_facts_survive(self):
        case = sample_case()
        case.history.append(CaseHistory('Earlier reply', 'Unknown', 'Not established', 1, 'Revised facts'))
        case.legacy_records.append(CaseHistory('Previous action', 'Requested', 'Original answer', 99, 'Legacy account'))
        old = deepcopy(case.facts[0])
        old.excerpt = 'A quote from an earlier scenario.'
        old.subject = 'former-user'
        case.fact_history.append(old)
        old_action = CaseAction('old-review', 'A former review', actor_id='former-reviewer', source='scenario', excerpt='Earlier account', checks={'former_question':'Original wording'})
        case.action_history.append(old_action)
        result = case_from_dict(case_to_dict(case))
        self.assertEqual(result, case)

    def test_reported_planned_and_implemented_actions_are_preserved_without_effectiveness(self):
        case = sample_case()
        case.actions = [CaseAction('review', 'Requested an independent review', 'independent_review', 'Planned', source='scenario', excerpt='I requested an independent review.')]
        result = case_from_dict(case_to_dict(case))
        self.assertEqual(result.actions[0].stage, 'Planned')
        self.assertFalse(result.actions[0].reviewed)
        case.actions[0].source = 'user'
        case.actions[0].stage = 'Implemented'
        case.actions[0].evidence_detail = 'The user describes review notes; authentication is not claimed.'
        case.actions[0].checks = {'evidence':'Records described'}
        result = case_from_dict(case_to_dict(case))
        self.assertEqual(result.actions[0].stage, 'Implemented')
        self.assertEqual(result.actions[0].evidence_detail, case.actions[0].evidence_detail)

    def test_explicit_unknown_answer_survives_without_becoming_a_negative_fact(self):
        from objectivity.case_reasoning import facts_signature
        case = sample_case()
        deps = ('pressure',)
        fact = CaseFact('answer', 'user', 'work_changed', 'Unknown', source='user', status='unknown', reviewed=True, depends_on=deps)
        case.facts.append(fact)
        case.answers['question-effect'] = CaseAnswer('question-effect', 'Unknown', 'Not known', 'answer', deps, facts_signature(case,deps), 'Has the work changed?')
        restored = case_from_dict(case_to_dict(case))
        self.assertEqual(restored.answers['question-effect'].choice, 'Unknown')
        self.assertEqual(next(f for f in restored.facts if f.id=='answer').status, 'unknown')

    def test_import_recalculates_dependency_bindings_and_retains_stale_reply_in_history(self):
        from objectivity.case_reasoning import facts_signature
        case = sample_case()
        deps = ('pressure',)
        case.facts.append(CaseFact('answer','user','work_changed','Unknown',source='user',status='unknown',reviewed=True,depends_on=deps))
        case.answers['question-effect'] = CaseAnswer('question-effect','Unknown','Not known','answer',deps,facts_signature(case,deps),'Has work changed?')
        value = case_to_dict(case)
        value['state']['facts'][2]['value'] = 'A materially different requested change'
        restored = case_from_dict(value)
        self.assertEqual(restored.answers, {})
        self.assertEqual(next(f for f in restored.facts if f.id=='answer').status,'withdrawn')
        self.assertTrue(any(record.value=='Unknown' for record in restored.history))
        wrapped = document(case)
        wrapped['assessment']['case_state'] = value
        self.assertTrue(import_progress(json.dumps(wrapped)).warnings)

    def test_export_is_deterministic_without_mutating_live_case(self):
        case = sample_case()
        before = deepcopy(case)
        assessment = Assessment(scenario=case.scenario,case_state=case)
        first = export_progress(assessment,ReviewState(),AddressState(),'identify')
        second = export_progress(assessment,ReviewState(),AddressState(),'identify')
        self.assertEqual(first,second)
        self.assertEqual(case,before)


class CaseProgressValidationTests(unittest.TestCase):
    def rejects(self, value):
        with self.assertRaises((CaseCodecError,ProgressError)):
            case_from_dict(value)

    def test_effectiveness_or_verified_status_cannot_be_imported_as_source_state(self):
        value = case_to_dict(sample_case())
        value['state']['facts'][0]['status'] = 'independently_verified'
        self.rejects(value)
        case = sample_case()
        case.actions.append(CaseAction('review','An alleged safeguard'))
        value = case_to_dict(case)
        value['state']['actions'][0]['stage'] = 'Effectiveness Established'
        self.rejects(value)

    def test_unknown_rules_and_derived_fields_are_rejected(self):
        value = case_to_dict(sample_case())
        value['rules_version'] = 'future-case-rules'
        self.rejects(value)
        for level in ('envelope','state','fact'):
            with self.subTest(level=level):
                value = case_to_dict(sample_case())
                target = value if level=='envelope' else value['state'] if level=='state' else value['state']['facts'][0]
                target['conclusion'] = 'Objectivity is protected'
                self.rejects(value)

    def test_missing_records_duplicate_ids_and_unknown_actor_references_are_rejected(self):
        for mutate in (
            lambda v:v['state'].pop('history'),
            lambda v:v['state']['actors'].append(deepcopy(v['state']['actors'][0])),
            lambda v:v['state']['facts'].append(deepcopy(v['state']['facts'][0])),
            lambda v:v['state']['facts'][0].update(subject='missing'),
            lambda v:v['state']['facts'][0].update(object_id='missing'),
            lambda v:v['state']['facts'][0].update(depends_on=['missing']),
        ):
            with self.subTest(mutate=mutate):
                value = case_to_dict(sample_case())
                mutate(value)
                self.rejects(value)

    def test_active_scenario_sources_must_quote_the_actual_account(self):
        value = case_to_dict(sample_case())
        value['state']['facts'][0]['excerpt'] = 'A fabricated source quotation'
        self.rejects(value)
        value['state']['facts'][0]['excerpt'] = ''
        self.rejects(value)

    def test_actions_require_supported_check_answers_and_real_source_excerpts(self):
        case = sample_case()
        case.actions.append(CaseAction('review','A review',source='scenario',excerpt='I requested an independent review.'))
        for changes in ({'excerpt':'Invented source'}, {'checks':{'evidence':'Definitely verified'}}, {'checks':{'compliance':'Certified'}}):
            with self.subTest(changes=changes):
                value = case_to_dict(case)
                value['state']['actions'][0].update(changes)
                self.rejects(value)

    def test_answer_source_must_match_the_recorded_choice_and_dependencies(self):
        from objectivity.case_reasoning import facts_signature
        case = sample_case()
        deps = ('pressure',)
        case.facts.append(CaseFact('answer','user','work_changed','Unknown',source='user',status='unknown',depends_on=deps))
        case.answers['question-effect'] = CaseAnswer('question-effect','Unknown','','answer',deps,facts_signature(case,deps),'Question')
        for changes in ({'choice':'Yes'}, {'fact_id':'missing'}, {'depends_on':[]}):
            with self.subTest(changes=changes):
                value = case_to_dict(case)
                value['state']['answers']['question-effect'].update(changes)
                self.rejects(value)

    def test_strict_booleans_and_record_bounds(self):
        for path, change in (('reviewed','yes'),('actions_reviewed',1),('revision',True)):
            with self.subTest(path=path):
                value = case_to_dict(sample_case())
                value['state'][path] = change
                self.rejects(value)
        value = case_to_dict(sample_case())
        value['state']['facts'] = value['state']['facts'] * 2_001
        self.rejects(value)

    def test_malformed_live_case_cannot_be_exported(self):
        case = sample_case()
        case.actions.append(CaseAction('bad','A claimed action',stage='Effectiveness Established'))
        with self.assertRaises(ProgressError):
            export_progress(Assessment(case_state=case),ReviewState(),AddressState(),'identify')

    def test_unknown_case_source_is_preserved_as_plain_data(self):
        case = sample_case()
        case.facts[0].value = "__import__('os').system('never-run')"
        case.facts[0].source = 'user'
        restored = case_from_dict(case_to_dict(case))
        self.assertEqual(restored.facts[0].value,case.facts[0].value)


if __name__=='__main__':
    unittest.main()
