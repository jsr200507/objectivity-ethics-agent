"""The optional network boundary, exercised without credentials or live calls."""
from dataclasses import replace
from io import BytesIO
import json
import socket
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import Mock

from objectivity.ai_provider import (
    AIConfig, AIProviderError, ENDPOINT, GroqProvider, MAX_RESPONSE_BYTES,
    _NoRedirect, strict_json_object,
)


def configured(**changes):
    return replace(AIConfig(api_key='fictional-test-credential', model='operator-verified-model', free_tier_confirmed=True), **changes)


class Response(BytesIO):
    pass


def response(content='{"actors":[],"facts":[]}', finish='stop'):
    return Response(json.dumps({'choices':[{'message':{'content':content},'finish_reason':finish}]}).encode())


class AIProviderTests(unittest.TestCase):
    def test_missing_key_model_and_operator_free_confirmation_keep_provider_disabled(self):
        for config in (AIConfig(), configured(api_key=''), configured(model=''), configured(free_tier_confirmed=False)):
            with self.subTest(config=config):
                transport = Mock()
                with self.assertRaises(AIProviderError):
                    GroqProvider(config, transport).generate('system', 'fictional scenario')
                transport.assert_not_called()

    def test_secret_alone_does_not_assume_a_model_or_free_plan(self):
        config=AIConfig.from_mapping({'GROQ_API_KEY':'fictional-test-credential'})
        self.assertFalse(config.enabled)
        self.assertEqual(config.model,'')
        self.assertFalse(config.free_tier_confirmed)
        self.assertNotIn(config.api_key,repr(config))

    def test_mapping_settings_enable_only_explicit_eligible_configuration(self):
        config=AIConfig.from_mapping({
            'GROQ_API_KEY':'fictional-test-credential','OBJECTIVITY_AI_MODEL':'operator-verified-model',
            'OBJECTIVITY_AI_PROVIDER':'groq','OBJECTIVITY_AI_FREE_TIER_CONFIRMED':'true',
            'OBJECTIVITY_AI_MAX_REQUESTS':'2','OBJECTIVITY_AI_MAX_INPUT_TOKENS':'8000',
            'OBJECTIVITY_AI_MAX_OUTPUT_TOKENS':'1000','OBJECTIVITY_AI_TIMEOUT_SECONDS':'5',
        })
        self.assertTrue(config.enabled)
        self.assertEqual((config.max_requests,config.max_input_tokens,config.max_output_tokens,config.timeout_seconds),(2,8000,1000,5))

    def test_operator_settings_have_hard_bounds_even_when_constructed_directly(self):
        config=configured(max_requests=100,max_input_tokens=100000,max_output_tokens=100000,timeout_seconds=1000)
        self.assertEqual((config.max_requests,config.max_input_tokens,config.max_output_tokens,config.timeout_seconds),(3,16384,4096,60))
        invalid=AIConfig.from_mapping({'OBJECTIVITY_AI_MAX_REQUESTS':'oops','OBJECTIVITY_AI_TIMEOUT_SECONDS':'nan'})
        self.assertEqual((invalid.max_requests,invalid.timeout_seconds),(3,30))

    def test_unsupported_provider_invalid_model_and_header_injection_are_disabled(self):
        for config in (configured(provider='other-paid-provider'),configured(model='bad\nmodel'),configured(api_key='fake\r\nInjected:header')):
            self.assertFalse(config.enabled)

    def test_transport_uses_fixed_https_endpoint_and_bounded_json_configuration(self):
        transport=Mock(return_value=response())
        data=GroqProvider(configured(),transport).generate('Extract only source facts','Fictional case')
        self.assertEqual(data,{'actors':[],'facts':[]})
        request=transport.call_args.args[0]
        payload=json.loads(request.data)
        self.assertEqual(request.full_url,ENDPOINT)
        self.assertEqual(request.get_method(),'POST')
        self.assertEqual(request.get_header('Authorization'),'Bearer fictional-test-credential')
        self.assertEqual(payload['response_format'],{'type':'json_object'})
        self.assertEqual(payload['max_completion_tokens'],1800)
        self.assertNotIn('max_tokens', payload)
        self.assertNotIn('retry',payload)
        self.assertEqual(transport.call_args.kwargs,{'timeout':30})

    def test_input_budget_prevents_transport_and_does_not_retry(self):
        transport=Mock()
        with self.assertRaises(AIProviderError) as caught:
            GroqProvider(configured(max_input_tokens=256),transport).generate('system','case')
        self.assertEqual(caught.exception.code,'input_limit')
        transport.assert_not_called()

    def test_http_failures_are_sanitised_and_never_retried(self):
        for status,code in ((400,'bad_request'),(401,'credentials_rejected'),(402,'quota_exhausted'),(403,'forbidden'),(404,'unsupported'),(429,'rate_limit'),(503,'provider_error')):
            with self.subTest(status=status):
                transport=Mock(side_effect=HTTPError(ENDPOINT,status,'fictional-test-credential confidential scenario',{},None))
                with self.assertRaises(AIProviderError) as caught:
                    GroqProvider(configured(),transport).generate('s','u')
                self.assertEqual(caught.exception.code,code)
                self.assertEqual(caught.exception.diagnostic['http_status'], status)
                self.assertNotIn('fictional-test-credential',str(caught.exception))
                self.assertNotIn('confidential scenario',str(caught.exception))
                self.assertEqual(transport.call_count,1)

    def test_timeout_and_network_failure_use_safe_categories(self):
        for error,code in ((TimeoutError('secret'),'timeout'),(socket.timeout('secret'),'timeout'),(URLError(socket.timeout('secret')),'timeout'),(URLError('secret'),'network_error')):
            with self.subTest(code=code):
                with self.assertRaises(AIProviderError) as caught:
                    GroqProvider(configured(),Mock(side_effect=error)).generate('s','u')
                self.assertEqual(caught.exception.code,code)
                self.assertNotIn('secret',str(caught.exception))

    def test_malformed_envelopes_truncation_and_oversize_fall_back(self):
        for body,category in ((b'not JSON','invalid_json'),(b'{}','invalid_response'),(b'{"choices":[]}','invalid_response'),(b'\xff','invalid_json'),(b'x'*(MAX_RESPONSE_BYTES+1),'invalid_response')):
            with self.subTest(size=len(body)):
                with self.assertRaises(AIProviderError) as caught:
                    GroqProvider(configured(),Mock(return_value=Response(body))).generate('s','u')
                self.assertEqual(caught.exception.code,category)
        with self.assertRaises(AIProviderError):
            GroqProvider(configured(),Mock(return_value=response('{}','length'))).generate('s','u')

    def test_model_content_must_be_standard_json_object_with_unique_fields(self):
        for content in ('not JSON','[]','{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}',None,'\ud800'):
            with self.subTest(content=repr(content)):
                with self.assertRaises(AIProviderError):
                    strict_json_object(content)

    def test_redirects_are_not_followed_with_server_credentials(self):
        self.assertIsNone(_NoRedirect().redirect_request(None,None,302,'redirect',{},'https://other.example'))


if __name__=='__main__':
    unittest.main()
