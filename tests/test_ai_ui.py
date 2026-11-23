"""Real Streamlit session journeys for consent, bounded AI and local fallback.

Provider calls are controlled in memory. These tests do not establish live API
access or browser-local storage; the latter has separate Chromium coverage.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from objectivity.ai_provider import AIConfig, AIProviderError
from objectivity.case_model import CaseHistory
from objectivity.examples import EXAMPLE_SCENARIO
from objectivity.progress import export_progress, import_progress
from tests.test_general_prefill_app import AcknowledgedBrowserStore


APP = Path(__file__).resolve().parents[1] / 'app.py'
UNDERSTANDING_CONSENT = 'I consent to optional external AI-assisted understanding of this scenario.'
REPORT_CONSENT = 'I consent to send this assessment and recorded actions to the external provider for an optional overview.'


class AvailableAllowance:
    def acquire(self):
        return True

    def release(self):
        pass

    def cooldown(self):
        pass


class ControlledProvider:
    def __init__(self):
        self.calls = []
        self.understanding = {'actors': [], 'facts': [], 'actions': []}
        self.error = None
        self.bad_report = False

    def generate(self, system, user):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        if 'Extract source proposals' in system:
            return deepcopy(self.understanding)
        request = json.loads(user)
        result = {
            'basis_signature': request['basis_signature'],
            'selection': [{'id': clause['id'], 'variant': 0} for clause in request['catalog']],
        }
        if self.bad_report:
            result['conclusion'] = 'All threats have been eliminated and the case is certified.'
        return result


class OptionalAIAppTests(unittest.TestCase):
    def _assert_report_request_is_immediately_autosaved(self, error=None):
        store = AcknowledgedBrowserStore()
        self.bridge_patch.stop()
        with patch('objectivity.progress_ui.browser_storage', side_effect=store):
            self.new_app()
            self.begin()
            self.to_report()
            self.provider.error = error
            self.widget('checkbox', REPORT_CONSENT).check()
            self.click('Create AI-assisted report overview')
            self.assertEqual(len(self.provider.calls), 2)
            saved = import_progress(store.data)
            self.assertEqual(sum(h.label == 'Optional AI request' for h in saved.assessment.case_state.history), 2)
            if error:
                self.assertIn('timed out', self.text())
                self.assertIn('## I. Overall ethical conclusion and limitations', self.text())

    def test_report_request_count_is_autosaved_before_any_further_user_action(self):
        self._assert_report_request_is_immediately_autosaved()

    def test_failed_report_request_is_autosaved_with_usable_fallback_notice(self):
        self._assert_report_request_is_immediately_autosaved(AIProviderError('timeout'))

    def setUp(self):
        self.config = AIConfig(api_key='fictional-test-credential', model='mock-free-model',
                               free_tier_confirmed=True, max_input_tokens=16384)
        self.provider = ControlledProvider()
        self.config_patch = patch('objectivity.ai_ui.load_config', side_effect=lambda: self.config)
        self.provider_patch = patch('objectivity.ai_ui.GroqProvider', return_value=self.provider)
        self.bridge_patch = patch('objectivity.progress_ui.browser_storage', return_value=None)
        self.limiter_patch = patch('objectivity.ai_usage._GLOBAL_LIMITER', AvailableAllowance())
        for item in (self.config_patch, self.provider_patch, self.bridge_patch, self.limiter_patch):
            item.start()
            self.addCleanup(item.stop)
        self.new_app()

    def new_app(self):
        self.app = AppTest.from_file(str(APP), default_timeout=15).run()
        self.healthy()

    def healthy(self):
        self.assertEqual(len(self.app.exception), 0)

    def widget(self, kind, label):
        return next(item for item in getattr(self.app, kind) if item.label == label)

    def click(self, label):
        self.widget('button', label).click().run()
        self.healthy()

    def text(self):
        return '\n'.join(item.value for kind in ('markdown', 'caption', 'text', 'info', 'warning', 'header')
                         for item in getattr(self.app, kind))

    def case(self):
        return self.app.session_state['assessment'].case_state

    def begin(self, scenario=EXAMPLE_SCENARIO, *, consent=True):
        self.widget('text_area', 'Your scenario').input(scenario)
        if consent:
            self.widget('checkbox', UNDERSTANDING_CONSENT).check()
        self.click('Review scenario')
        self.assertEqual(self.app.session_state['view'], 'identify')

    def confirm(self):
        self.widget('checkbox', 'These records reflect my account, including uncertainties.').check()
        self.click('Confirm scenario and continue')
        self.assertTrue(self.case().reviewed)

    def to_report(self):
        if self.app.session_state['view'] == 'identify':
            self.confirm()
        self.click('Review existing actions')
        self.click('Generate Objectivity report')
        self.assertEqual(self.app.session_state['view'], 'case_report')

    def request_report(self, *, consent=True):
        if consent:
            self.widget('checkbox', REPORT_CONSENT).check()
        self.click('Create AI-assisted report overview')

    def has_overview(self):
        return any(item.value.startswith('### AI-assisted case overview') for item in self.app.markdown)

    def export(self):
        return export_progress(self.app.session_state['assessment'], self.app.session_state['review_state'],
                               self.app.session_state['address_state'], self.app.session_state['view'])

    def restore(self, document):
        snapshot = import_progress(document)
        self.new_app()
        self.app.session_state['assessment'] = deepcopy(snapshot.assessment)
        self.app.session_state['review_state'] = deepcopy(snapshot.review)
        self.app.session_state['address_state'] = deepcopy(snapshot.address)
        self.app.session_state['view'] = snapshot.view
        self.app.session_state['widget_generation'] += 1
        self.app.run()
        self.healthy()

    def test_no_credentials_keeps_complete_local_journey_and_sends_nothing(self):
        self.config = AIConfig()
        self.new_app()
        self.assertTrue(self.widget('checkbox', UNDERSTANDING_CONSENT).disabled)
        self.begin(consent=False)
        self.assertIn('Deterministic fallback', self.text())
        self.to_report()
        self.assertIn('## E. Actions taken and proposed', self.text())
        self.assertFalse(self.provider.calls)
        self.assertFalse(any(item.label == 'Create AI-assisted report overview' for item in self.app.button))

    def test_disabled_assistance_does_not_require_optional_report_request_preparation(self):
        from objectivity.ai_report import AIReportError
        self.config = AIConfig()
        self.new_app()
        self.begin(consent=False)
        with patch('objectivity.ai_report.build_ai_report_request',
                   side_effect=AIReportError('This assessment is too large for optional overview assistance.')):
            self.to_report()
        self.assertIn('## E. Actions taken and proposed', self.text())
        self.assertFalse(self.provider.calls)

    def test_optional_report_preparation_failure_keeps_the_complete_report_available(self):
        from objectivity.ai_report import AIReportError
        self.begin()
        with patch('objectivity.ai_report.build_ai_report_request',
                   side_effect=AIReportError('This assessment is too large for optional overview assistance.')):
            self.to_report()
        self.assertIn('## I. Overall ethical conclusion and limitations', self.text())
        self.assertEqual(len(self.provider.calls), 1)

    def test_configured_provider_never_receives_scenario_without_consent(self):
        self.begin(consent=False)
        self.app.run()
        self.to_report()
        self.assertFalse(self.provider.calls)
        self.assertEqual(sum(h.label == 'Optional AI request' for h in self.case().history), 0)

    def test_valid_grounded_ai_role_remains_unconfirmed_until_review(self):
        first = 'In my capacity as a conservation grants assessor I compare funding proposals.'
        scenario = first + ' My bonus depends on the winning proposal.'
        self.provider.understanding = {
            'actors': [{'label': 'user', 'role': 'conservation grants assessor',
                        'kind': 'professional', 'excerpt': first}],
            'facts': [{'subject': 'user', 'predicate': 'role', 'value': 'conservation grants assessor',
                       'object': '', 'excerpt': first, 'status': 'reported'}],
            'actions': [],
        }
        self.begin(scenario)
        role = next(fact for fact in self.case().facts if fact.predicate == 'role')
        self.assertEqual(role.value, 'conservation grants assessor')
        self.assertFalse(role.reviewed)
        self.assertFalse(self.case().reviewed)
        self.assertIn('AI-assisted understanding', self.text())
        self.confirm()
        self.assertTrue(role.reviewed)
        self.assertEqual(role.status, 'reported')
        self.assertEqual(len(self.provider.calls), 1)

    def test_structured_answers_navigation_and_reruns_do_not_consume_more_calls(self):
        from objectivity.case_reasoning import reason_case
        self.begin()
        self.confirm()
        for _ in range(10):
            questions = reason_case(self.case()).questions
            if not questions:
                break
            question = questions[0]
            self.widget('radio', question.prompt).set_value('Unknown')
            self.click('Record answer and reassess')
            self.app.run()
            self.healthy()
        else:
            self.fail('Unknown answers must not create an endless clarification loop')
        self.to_report()
        self.app.run()
        self.healthy()
        self.assertEqual(len(self.provider.calls), 1)
        self.assertFalse(self.has_overview())

    def test_report_call_requires_its_own_explicit_consent(self):
        self.begin()
        self.to_report()
        self.request_report(consent=False)
        self.assertEqual(len(self.provider.calls), 1)
        self.assertIn('Consent is required', self.text())
        self.assertFalse(self.has_overview())
        self.request_report()
        self.assertEqual(len(self.provider.calls), 2)
        self.assertTrue(self.has_overview())
        self.assertIn('## I. Overall ethical conclusion and limitations', self.text())

    def test_successful_report_is_reused_on_rerun_and_repeated_explicit_request(self):
        self.begin()
        self.to_report()
        self.request_report()
        self.app.run()
        self.healthy()
        self.assertTrue(self.has_overview())
        self.request_report()
        self.assertEqual(len(self.provider.calls), 2)
        self.assertEqual(sum(h.label == 'Optional AI request' for h in self.case().history), 2)

    def test_repeated_initial_submission_reuses_the_completed_source_request(self):
        self.begin()
        self.app.session_state['view'] = 'scenario'
        self.app.session_state['widget_generation'] += 1
        self.app.run()
        self.begin()
        self.assertEqual(len(self.provider.calls), 1)
        self.assertIn('AI-assisted understanding', self.text())
        self.assertEqual(sum(h.label == 'Optional AI request' for h in self.case().history), 1)

    def test_malformed_understanding_falls_back_without_losing_scenario_or_budget(self):
        self.provider.understanding = {'facts': 'invented unstructured answer'}
        self.begin()
        self.assertEqual(self.case().scenario, EXAMPLE_SCENARIO)
        self.assertTrue(self.case().facts)
        self.assertIn('Deterministic fallback', self.text())
        self.assertIn('could not be safely validated', self.text())
        self.assertEqual(sum(h.label == 'Optional AI request' for h in self.case().history), 1)
        self.to_report()
        self.assertIn('## B. Identified potential Objectivity threats', self.text())

    def test_rate_limit_timeout_and_failure_preserve_a_working_local_assessment(self):
        for code in ('rate_limit', 'timeout', 'unavailable'):
            with self.subTest(code=code):
                self.provider.calls.clear()
                self.provider.error = AIProviderError(code)
                self.new_app()
                self.begin()
                self.assertEqual(len(self.provider.calls), 1)
                self.assertEqual(self.case().scenario, EXAMPLE_SCENARIO)
                self.assertIn('Deterministic fallback', self.text())
                self.app.run()
                self.to_report()
                self.assertEqual(len(self.provider.calls), 1)
                self.assertIn('## E. Actions taken and proposed', self.text())

    def test_contradictory_ai_report_is_not_displayed_or_saved_as_a_conclusion(self):
        self.provider.bad_report = True
        self.begin()
        self.to_report()
        self.request_report()
        self.assertEqual(len(self.provider.calls), 2)
        self.assertIn('failed consistency checks', self.text())
        self.assertFalse(self.has_overview())
        self.assertNotIn('the case is certified', self.text())
        self.assertEqual(self.app.session_state['_ai_report_overviews'], {})
        self.assertNotIn('the case is certified', self.export())

    def test_request_budget_survives_export_and_fresh_session_import(self):
        self.begin()
        self.to_report()
        self.request_report()
        self.case().history.append(CaseHistory('Optional AI request', 'report', revision=self.case().revision))
        document = self.export()
        self.restore(document)
        self.assertEqual(sum(h.label == 'Optional AI request' for h in self.case().history), 3)
        self.assertFalse(self.has_overview(), 'Derived AI overview is not a trusted imported report')
        self.request_report()
        self.assertEqual(len(self.provider.calls), 2)
        self.assertIn('assessment request allowance', self.text())
        self.assertNotIn('fictional-test-credential', document)
        self.assertNotIn('_case_ai_session', document)

    def test_material_edit_invalidates_only_report_overview_not_source_understanding(self):
        self.begin()
        self.to_report()
        self.request_report()
        self.assertTrue(self.has_overview())
        pressure = next(fact for fact in self.case().facts if fact.predicate == 'pressure')
        self.widget('selectbox', 'Choose reported information to correct').select(pressure.id).run()
        self.widget('text_area', 'Corrected detail').input('The CFO has now expressly requested withholding the revenue concern.')
        self.click('Save correction and reassess')
        self.assertEqual(self.app.session_state['view'], 'identify')
        self.assertFalse(self.case().reviewed)
        self.confirm()
        self.to_report()
        self.assertFalse(self.has_overview())
        self.assertEqual(len(self.provider.calls), 2)
        self.assertEqual(len(self.app.session_state['_initial_ai_sessions']), 1)
        self.request_report()
        self.assertEqual(len(self.provider.calls), 3)
        self.assertTrue(self.has_overview())
        self.assertEqual(sum(h.label == 'Optional AI request' for h in self.case().history), 3)


if __name__ == '__main__':
    unittest.main()
