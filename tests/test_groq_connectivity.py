"""Bounded connectivity diagnostics and GPT-OSS compatibility, all mocked."""
from copy import deepcopy
from dataclasses import asdict
from io import BytesIO
import json
from pathlib import Path
import socket
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from streamlit.testing.v1 import AppTest

from objectivity.ai_provider import AIConfig, AIProviderError, ENDPOINT, GroqProvider, safe_diagnostics
from objectivity.ai_usage import AISession, _SharedLimiter
from objectivity.ai_diagnostic import FICTIONAL_SCENARIO, run_diagnostic

APP = Path(__file__).resolve().parents[1] / 'app.py'
KEY = 'fictional-test-credential'
TOKEN = 'separate-operator-test-access-code'
CONFIG = AIConfig(api_key=KEY, model='openai/gpt-oss-120b', free_tier_confirmed=True)


class Response(BytesIO):
    status = 200
    headers = {'x-request-id': 'req_mock_12345678'}


def completion(content=None, finish='stop'):
    content = json.dumps({'actors': [], 'facts': [], 'actions': []}) if content is None else content
    return Response(json.dumps({'choices': [{'finish_reason': finish,
        'message': {'content': content, 'reasoning': 'Never displayed or logged'}}]}).encode())


def session():
    return AISession(max_requests=1, limiter=_SharedLimiter(per_minute=100))


class GroqConnectivityTests(unittest.TestCase):
    def test_dns_tls_network_and_timeouts_remain_distinct(self):
        cases = [(socket.gaierror(-2, 'private DNS details'), 'dns_error'),
                 (URLError(socket.gaierror(-2, 'private DNS details')), 'dns_error'),
                 (ssl.SSLCertVerificationError('private certificate details'), 'tls_error'),
                 (URLError(ssl.SSLCertVerificationError('private details')), 'tls_error'),
                 (ConnectionRefusedError('private host'), 'network_error'),
                 (URLError('private host'), 'network_error'),
                 (TimeoutError('private request'), 'timeout')]
        for error, category in cases:
            with self.subTest(category=category):
                provider = GroqProvider(CONFIG, Mock(side_effect=error))
                with self.assertRaises(AIProviderError) as caught:
                    provider.generate('JSON only', 'fictional')
                self.assertEqual(caught.exception.code, category)
                self.assertNotIn('private', str(caught.exception))
                self.assertNotIn(KEY, repr(caught.exception.diagnostic))

    def test_proxy_403_does_not_claim_a_groq_http_response(self):
        provider = GroqProvider(CONFIG, Mock(side_effect=URLError('Tunnel connection failed: 403 Forbidden')))
        result = run_diagnostic(CONFIG, session=session(), provider=provider)
        self.assertEqual(result.category, 'proxy_error')
        self.assertEqual(result.technical['response_origin'], 'proxy')
        self.assertEqual(result.steps[1].status, 'Not established')
        self.assertEqual(result.steps[2].status, 'Not run')

    def test_http_categories_are_actionable_without_response_body_or_credentials(self):
        for status, category in ((400, 'bad_request'), (401, 'credentials_rejected'),
                (403, 'forbidden'), (404, 'unsupported'), (429, 'rate_limit'),
                (500, 'provider_error'), (502, 'provider_error'), (503, 'provider_error')):
            with self.subTest(status=status):
                transport = Mock(side_effect=HTTPError(ENDPOINT, status, KEY,
                    {'x-request-id': 'req_mock_12345678'}, BytesIO(b'{"error":{"message":"confidential case"}}')))
                result = run_diagnostic(CONFIG, session=session(), provider=GroqProvider(CONFIG, transport))
                self.assertEqual(result.category, category)
                self.assertEqual(result.technical['http_status'], status)
                self.assertEqual(result.steps[1].status, 'Passed')
                self.assertEqual(result.steps[2].status, 'Failed' if status == 401 else 'Not established')
                self.assertNotIn(KEY, repr(asdict(result)))
                self.assertNotIn('confidential case', repr(asdict(result)))
                self.assertEqual(transport.call_count, 1)

    def test_provider_json_generation_failure_is_not_a_network_error(self):
        error = HTTPError(ENDPOINT, 400, 'private', {}, BytesIO(
            b'{"error":{"code":"json_validate_failed","message":"private prompt"}}'))
        result = run_diagnostic(CONFIG, session=session(), provider=GroqProvider(CONFIG, Mock(side_effect=error)))
        self.assertEqual(result.category, 'generation_invalid_json')
        self.assertEqual(result.steps[1].status, 'Passed')
        self.assertEqual(result.steps[3].status, 'Failed')
        self.assertNotIn('private prompt', repr(result))

    def test_gpt_oss_uses_supported_token_and_low_reasoning_parameters(self):
        transport = Mock(return_value=completion())
        result = GroqProvider(CONFIG, transport).generate('Return JSON', 'fictional')
        self.assertEqual(result, {'actors': [], 'facts': [], 'actions': []})
        request = transport.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, ENDPOINT)
        self.assertEqual(body['max_completion_tokens'], CONFIG.max_output_tokens)
        self.assertEqual(body['reasoning_effort'], 'low')
        self.assertEqual(body['response_format'], {'type': 'json_object'})
        self.assertNotIn('reasoning_format', body)
        self.assertNotIn('include_reasoning', body)
        self.assertNotIn('max_tokens', body)
        self.assertEqual(transport.call_args.kwargs['timeout'], 30)
        self.assertEqual(request.get_header('User-agent'), 'ObjectivityEthicsAssistant/1.0')

    def test_truncated_200_response_is_not_accepted_or_called_a_network_failure(self):
        result = run_diagnostic(CONFIG, session=session(), provider=GroqProvider(CONFIG,
            Mock(return_value=completion('{"actors":', finish='length'))))
        self.assertEqual(result.category, 'response_truncated')
        self.assertEqual(result.technical['finish_reason'], 'length')
        self.assertEqual([step.status for step in result.steps[1:]],
                         ['Passed', 'Passed', 'Failed', 'Not run'])

    def test_invalid_json_and_application_validation_have_different_stages(self):
        for content, category, statuses in (
            ('not JSON', 'invalid_json', ['Failed', 'Not run']),
            ('{"unsupported":"fabricated facts"}', 'application_validation', ['Passed', 'Failed']),
        ):
            with self.subTest(category=category):
                result = run_diagnostic(CONFIG, session=session(), provider=GroqProvider(CONFIG, Mock(return_value=completion(content))))
                self.assertEqual(result.category, category)
                self.assertEqual([step.status for step in result.steps[3:]], statuses)
                self.assertEqual(result.steps[2].status, 'Passed')

    def test_unrecognised_http_200_body_does_not_prove_authentication(self):
        result = run_diagnostic(CONFIG, session=session(), provider=GroqProvider(CONFIG, Mock(return_value=Response(b'{}'))))
        self.assertEqual(result.category, 'invalid_response')
        self.assertEqual(result.steps[2].status, 'Not established')

    def test_successful_fictional_probe_is_one_call_and_contains_no_generated_body(self):
        transport = Mock(return_value=completion())
        provider = GroqProvider(CONFIG, transport)
        ledger = session()
        first = run_diagnostic(CONFIG, session=ledger, provider=provider)
        repeated = run_diagnostic(CONFIG, session=ledger, provider=provider)
        self.assertEqual(first.category, 'success')
        self.assertTrue(all(step.status == 'Passed' for step in first.steps))
        self.assertTrue(repeated.reused)
        self.assertEqual(transport.call_count, 1)
        self.assertNotIn('reasoning', json.dumps(asdict(first)))
        self.assertNotIn(KEY, json.dumps(asdict(first)))
        payload = json.loads(transport.call_args.args[0].data)
        self.assertEqual(json.loads(payload['messages'][1]['content']), {'scenario': FICTIONAL_SCENARIO})

    def test_configuration_failure_sends_no_request(self):
        provider = Mock()
        result = run_diagnostic(AIConfig(), provider=provider)
        self.assertFalse(result.attempted)
        self.assertEqual(result.steps[0].status, 'Failed')
        provider.generate.assert_not_called()

    def test_failures_are_cached_with_their_safe_status(self):
        transport = Mock(side_effect=HTTPError(ENDPOINT, 403, KEY, {}, None))
        provider = GroqProvider(CONFIG, transport)
        ledger = session()
        first = run_diagnostic(CONFIG, session=ledger, provider=provider)
        second = run_diagnostic(CONFIG, session=ledger, provider=provider)
        self.assertEqual((first.category, second.category), ('forbidden', 'forbidden'))
        self.assertEqual(second.technical['http_status'], 403)
        self.assertTrue(second.reused)
        self.assertEqual(transport.call_count, 1)

    def test_runtime_error_logs_only_category_and_exception_class(self):
        provider = Mock()
        provider.generate.side_effect = RuntimeError(KEY + ' confidential scenario')
        with self.assertLogs('objectivity.ai_usage', level='WARNING') as captured:
            result = run_diagnostic(CONFIG, session=session(), provider=provider)
        self.assertEqual(result.category, 'runtime_error')
        self.assertIn('RuntimeError', captured.output[0])
        self.assertNotIn(KEY, repr(captured.output))
        self.assertNotIn('confidential scenario', repr(captured.output))

    def test_safe_metadata_rejects_arbitrary_fields_and_shapes(self):
        safe = safe_diagnostics({'api_key': KEY, 'body': 'private', 'http_status': True,
                                 'request_id': KEY, 'provider_code': {'secret': KEY}, 'finish_reason': []})
        self.assertEqual(safe, {})


class OperatorDiagnosticAppTests(unittest.TestCase):
    def test_operator_authorisation_is_required_and_probe_does_not_change_assessment(self):
        transport = Mock(return_value=completion())
        provider = GroqProvider(CONFIG, transport)
        def setting(name, default=''):
            return {'OBJECTIVITY_AI_DIAGNOSTICS_ENABLED': True,
                    'OBJECTIVITY_AI_DIAGNOSTIC_TOKEN': TOKEN}.get(name, default)
        with patch('objectivity.ai_ui.load_config', return_value=CONFIG), \
             patch('objectivity.ai_diagnostic._setting', side_effect=setting), \
             patch('objectivity.ai_diagnostic.GroqProvider', return_value=provider), \
             patch('objectivity.progress_ui.browser_storage', return_value=None):
            app = AppTest.from_file(str(APP), default_timeout=15).run()
            before = deepcopy(app.session_state['assessment'])
            access = next(w for w in app.text_input if w.label == 'Diagnostic access code (not the API key)')
            access.input('wrong code')
            next(w for w in app.button if w.label == 'Run one fictional Groq check').click().run()
            self.assertFalse(app.exception)
            transport.assert_not_called()
            access = next(w for w in app.text_input if w.label == 'Diagnostic access code (not the API key)')
            access.input(TOKEN)
            next(w for w in app.button if w.label == 'Run one fictional Groq check').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['_groq_operator_result'].category, 'success')
            next(w for w in app.button if w.label == 'Run one fictional Groq check').click().run()
            self.assertEqual(transport.call_count, 1)
            self.assertEqual(app.session_state['assessment'], before)

    def test_diagnostic_controls_are_absent_by_default(self):
        with patch('objectivity.ai_diagnostic._setting', return_value=False), \
             patch('objectivity.progress_ui.browser_storage', return_value=None):
            app = AppTest.from_file(str(APP), default_timeout=15).run()
            self.assertFalse(app.exception)
            self.assertNotIn('Run one fictional Groq check', [button.label for button in app.button])


if __name__ == '__main__':
    unittest.main()
