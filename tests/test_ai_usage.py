"""Optional AI calls are consented, bounded, deduplicated and safely replaceable."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading
import unittest

from objectivity.ai_provider import AIConfig, AIProviderError
from objectivity.ai_usage import AISession, _SharedLimiter


CONFIG=AIConfig(api_key='fictional-test-credential',model='operator-verified-model',free_tier_confirmed=True)


class Provider:
    def __init__(self,error=None):
        self.calls=0
        self.error=error

    def generate(self,system,user):
        self.calls+=1
        if self.error:raise self.error
        return {'summary':'quoted source proposal'}


class AIUsageTests(unittest.TestCase):
    def session(self,**kwargs):
        return AISession(limiter=_SharedLimiter(per_minute=100),**kwargs)

    def request(self,session,provider,**changes):
        values=dict(purpose='understanding',source_key='scenario-digest',config=CONFIG,
                    provider=provider,system='fixed schema',user='fictional scenario',consent=True)
        values.update(changes)
        return session.request(**values)

    def test_no_consent_and_no_key_or_free_confirmation_make_zero_calls(self):
        provider=Provider()
        session=self.session()
        for changes in ({'consent':False},{'config':AIConfig()},{'config':replace(CONFIG,free_tier_confirmed=False)}):
            self.assertEqual(self.request(session,provider,**changes).status,'fallback')
        self.assertEqual(provider.calls,0)
        self.assertEqual(session.attempts,0)
        self.assertFalse(session.events)

    def test_missing_provider_and_unsupported_purpose_are_local_fallbacks(self):
        session=self.session()
        self.assertEqual(self.request(session,None).reason,'unavailable')
        provider=Provider()
        self.assertEqual(self.request(session,provider,purpose='every_button').reason,'unsupported')
        self.assertFalse(provider.calls)

    def test_reruns_reuse_exact_response_without_another_attempt(self):
        session=self.session()
        provider=Provider()
        first=self.request(session,provider)
        second=self.request(session,provider)
        self.assertEqual((first.status,first.attempted,first.reused),('assisted',True,False))
        self.assertEqual((second.status,second.attempted,second.reused),('assisted',False,True))
        self.assertEqual((provider.calls,session.attempts,len(session.events)),(1,1,1))
        second.data['summary']='mutated'
        self.assertEqual(self.request(session,provider).data['summary'],'quoted source proposal')

    def test_failed_attempt_is_cached_without_a_retry_loop(self):
        session=self.session()
        provider=Provider(AIProviderError('timeout'))
        self.assertEqual(self.request(session,provider).reason,'timeout')
        repeat=self.request(session,provider)
        self.assertEqual((repeat.reason,repeat.reused,repeat.attempted),('timeout',True,False))
        self.assertEqual(provider.calls,1)

    def test_three_call_hard_cap_and_configured_lower_limit(self):
        for configured_limit in (2,3,999):
            session=self.session(max_requests=configured_limit)
            provider=Provider()
            for index in range(4):
                result=self.request(session,provider,source_key=str(index))
            self.assertEqual(result.reason,'assessment_limit')
            self.assertEqual(provider.calls,min(configured_limit,3))
        session=self.session()
        provider=Provider()
        for index in range(2):
            self.request(session,provider,source_key=str(index),config=replace(CONFIG,max_requests=1))
        self.assertEqual(provider.calls,1)

    def test_budget_restore_is_monotonic_and_suppresses_calls_after_refresh(self):
        session=self.session(attempts=2)
        session.restore_budget(1)
        self.assertEqual(session.attempts,2)
        session.restore_budget(3)
        provider=Provider()
        self.assertEqual(self.request(session,provider).reason,'assessment_limit')
        self.assertEqual(provider.calls,0)
        for invalid in (-1,'3',True):
            with self.assertRaises(ValueError):session.restore_budget(invalid)

    def test_input_excess_does_not_consume_a_request(self):
        session=self.session()
        provider=Provider()
        result=self.request(session,provider,user='x'*1000,config=replace(CONFIG,max_input_tokens=300))
        self.assertEqual((result.reason,result.attempted,provider.calls,session.attempts),('input_limit',False,0,0))

    def test_changed_source_prompt_and_model_invalidate_only_relevant_cache(self):
        session=self.session()
        provider=Provider()
        self.request(session,provider)
        self.request(session,provider,purpose='report',source_key='assessment-A')
        self.assertTrue(self.request(session,provider).reused)
        changed=self.request(session,provider,purpose='report',source_key='assessment-B')
        self.assertTrue(changed.attempted)
        self.assertTrue(self.request(session,provider).reused)
        self.assertEqual(provider.calls,3)
        session=self.session()
        provider=Provider()
        self.request(session,provider)
        self.request(session,provider,user='changed fictional scenario')
        self.request(session,provider,config=replace(CONFIG,model='another-operator-model'))
        self.assertEqual(provider.calls,3)

    def test_rate_limit_and_quota_block_new_requests_in_same_assessment(self):
        for code in ('rate_limit','quota_exhausted','credentials_rejected','unsupported'):
            with self.subTest(code=code):
                session=self.session()
                provider=Provider(AIProviderError(code))
                self.assertEqual(self.request(session,provider).reason,code)
                next_result=self.request(session,provider,purpose='report',source_key='new')
                self.assertEqual(next_result.reason,code)
                self.assertFalse(next_result.attempted)
                self.assertEqual(provider.calls,1)

    def test_provider_errors_and_nonobjects_never_leak_raw_content(self):
        session=self.session()
        provider=Provider(ValueError('fictional-test-credential confidential scenario'))
        result=self.request(session,provider)
        self.assertEqual(result.reason,'runtime_error')
        self.assertNotIn('confidential',repr(result))
        provider.generate=lambda *_:[]
        self.assertEqual(self.request(self.session(),provider).reason,'malformed')

    def test_concurrent_duplicate_requests_send_one_provider_call(self):
        session=self.session()
        provider=Provider()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:self.request(session,provider),range(6)))
        self.assertEqual(provider.calls,1)
        self.assertEqual(sum(result.attempted for result in results),1)
        self.assertEqual(sum(result.reused for result in results),5)

    def test_shared_visitor_concurrency_and_rate_controls_fail_locally(self):
        clock=[0.0]
        limiter=_SharedLimiter(concurrent=1,per_minute=2,clock=lambda:clock[0])
        self.assertTrue(limiter.acquire())
        provider=Provider()
        session=AISession(limiter=limiter)
        self.assertEqual(self.request(session,provider).reason,'busy')
        self.assertFalse(provider.calls)
        limiter.release()
        self.assertTrue(limiter.acquire());limiter.release()
        self.assertFalse(limiter.acquire())
        clock[0]=61
        self.assertTrue(limiter.acquire());limiter.release()
        limiter.cooldown()
        self.assertFalse(limiter.acquire())

    def test_events_contain_only_purpose_digest_status_and_reason(self):
        session=self.session()
        self.request(session,Provider(),source_key='confidential scenario value')
        event=session.events[0]
        self.assertEqual(set(vars(event)),{'purpose','key_digest','status','reason'})
        self.assertEqual(len(event.key_digest),64)
        self.assertNotIn('confidential',repr(event))
        self.assertNotIn('fictional-test-credential',repr(event))


if __name__=='__main__':
    unittest.main()
