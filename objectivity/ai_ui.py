"""Explicit-consent UI orchestration for optional, bounded external assistance.

No provider is called while rendering, navigating or recording ordinary answers.
Only explicit scenario/report submissions can request assistance. Ethical
findings always come from the existing deterministic assessment modules.
"""
import hashlib
import os

import streamlit as st

from .ai_provider import AIConfig, GroqProvider
from .ai_usage import AISession
from .case_model import CaseHistory
from .case_workflow import start_case

_REQUEST = 'Optional AI request'
_METHOD = 'Scenario understanding method'
_CONFIG = (
    'GROQ_API_KEY', 'OBJECTIVITY_AI_PROVIDER', 'OBJECTIVITY_AI_MODEL',
    'OBJECTIVITY_AI_FREE_TIER_CONFIRMED', 'OBJECTIVITY_AI_MAX_REQUESTS',
    'OBJECTIVITY_AI_MAX_INPUT_TOKENS', 'OBJECTIVITY_AI_MAX_OUTPUT_TOKENS',
    'OBJECTIVITY_AI_TIMEOUT_SECONDS',
)
_REASONS = {
    'consent_required': 'External assistance was not requested or consented to.',
    'missing_credentials': 'External assistance is not configured.',
    'free_tier_unconfirmed': 'An eligible free-tier configuration has not been confirmed by the operator.',
    'unsupported': 'The configured provider or model is unavailable.',
    'rate_limit': 'The provider rate limit was reached.',
    'quota_exhausted': 'The provider quota was exhausted.',
    'assessment_limit': 'The assessment request allowance has been reached.',
    'credentials_rejected': 'The provider did not accept its server-side configuration.',
    'input_limit': 'This case exceeds the configured external-assistance input allowance.',
    'timeout': 'The external request timed out.',
    'busy': 'The shared external-assistance allowance is temporarily busy.',
    'malformed': 'The external response could not be safely validated.',
    'unavailable': 'External assistance is unavailable.',
}


def load_config():
    """Read server configuration without exposing or storing a key in progress."""
    values = {name: os.environ[name] for name in _CONFIG if name in os.environ}
    try:
        for name in _CONFIG:
            if name in st.secrets:
                values[name] = st.secrets[name]
    except Exception:
        # A missing secrets file is normal for the fully local/default mode.
        # Framework errors and secret values must never be echoed to the page.
        pass
    return AIConfig.from_mapping(values)


def understanding_choice():
    config = load_config()
    if config.enabled:
        st.caption('Optional external assistance can suggest scenario facts. With your consent, the scenario will be processed by the configured external provider. Use fictional or appropriately anonymised cases; do not include confidential client information.')
    else:
        st.caption('Deterministic fallback is active. Optional external AI is not configured; no scenario will be transmitted. The full assessment remains available.')
    return st.checkbox('I consent to optional external AI-assisted understanding of this scenario.',
                       value=False, disabled=not config.enabled)


def _digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _attempts(case):
    return sum(record.label == _REQUEST for record in case.history)


def _record_budget(case, session, purpose):
    # Persist counts as non-evidential history, keeping schema 1/2/3 unchanged.
    # No key, full prompt, model response or ethical conclusion is persisted.
    for _ in range(max(0, session.attempts - _attempts(case))):
        case.history.append(CaseHistory(_REQUEST, purpose,
            'External request attempted; content and credentials are not stored in this request record.',
            case.revision, 'Request allowance retained across refresh and import.'))


def _bind(case, session):
    st.session_state['_case_ai_session'] = (id(case), session)


def _session(case, config):
    entry = st.session_state.get('_case_ai_session')
    if entry and entry[0] == id(case):
        session = entry[1]
        session.restore_budget(_attempts(case))
        return session
    session = AISession(max_requests=config.max_requests, attempts=_attempts(case))
    _bind(case, session)
    return session


class _Proposals:
    def __init__(self, result):
        self.result = result

    def understand(self, scenario):
        return self.result


def start_assisted_case(scenario, *, consent=False):
    """One explicit initial request, with safe local fallback for every failure."""
    from .ai_understanding import build_understanding_prompt, parse_ai_understanding
    config = load_config()
    # Validate input locally before even constructing an external request.
    local = start_case(scenario)
    sessions = st.session_state.setdefault('_initial_ai_sessions', {})
    key = _digest(local.scenario)
    session = sessions.get(key)
    if session is None:
        if len(sessions) >= 8:
            sessions.pop(next(iter(sessions)))
        session = AISession(max_requests=config.max_requests)
        sessions[key] = session
    mode, reason, case = 'Deterministic fallback', 'consent_required', local
    if consent and config.enabled:
        system, user = build_understanding_prompt(local.scenario)
        response = session.request('understanding', key, config, GroqProvider(config), system, user, consent=True)
        reason = response.reason
        if response.data is not None:
            try:
                proposals = parse_ai_understanding(local.scenario, response.data)
                case = start_case(local.scenario, _Proposals(proposals))
                mode, reason = 'AI-assisted understanding', ''
            except (ValueError, TypeError, KeyError):
                mode, reason = 'Deterministic fallback', 'malformed'
    elif consent:
        reason = config.disabled_reason
    _record_budget(case, session, 'understanding')
    case.history.append(CaseHistory(_METHOD, mode, _REASONS.get(reason, '') if reason else '',
                                   case.revision, 'Suggestions remain reported and require user review.'))
    _bind(case, session)
    return case


def understanding_status(case):
    method = next((item for item in reversed(case.history) if item.label == _METHOD), None)
    if method:
        st.caption(method.value + ' · Ethical evaluation is deterministic · No independent fact verification')
        if method.detail:
            st.caption(method.detail + ' Your progress remains available through local guidance.')
    else:
        st.caption('Deterministic understanding and ethical evaluation · No independent fact verification')


def report_assistance(case):
    """An optional constrained overview; never replace the ethical report."""
    from .ai_report import build_ai_report_request, validate_ai_report
    config = load_config()
    if not config.enabled:
        st.caption('Deterministic report mode: external AI is not configured. No report data is transmitted.')
        return ''
    try:
        system, user, context = build_ai_report_request(case)
    except (ValueError, TypeError, KeyError):
        st.caption('Optional overview preparation is unavailable for this assessment. The complete deterministic report remains available.')
        return ''
    key = context.basis_signature
    cache = st.session_state.setdefault('_ai_report_overviews', {})
    overview = ''
    if key in cache:
        try:
            overview = validate_ai_report(cache[key], context, case=case)
        except ValueError:
            cache.pop(key, None)
    with st.expander('Optional AI-assisted report overview'):
        st.caption('This optional assistance organises approved, case-specific wording. It cannot change facts, threat evaluations, action stages or conclusions. The complete rule-based report remains available below.')
        if not config.enabled:
            st.caption('Deterministic report mode: external AI is not configured. No report data is transmitted.')
        else:
            with st.form(f'{st.session_state.widget_generation}:ai_report'):
                consent = st.checkbox('I consent to send this assessment and recorded actions to the external provider for an optional overview.')
                submitted = st.form_submit_button('Create AI-assisted report overview')
            if submitted:
                if not consent:
                    st.warning('Consent is required before assessment information can be sent externally.')
                else:
                    session = _session(case, config)
                    response = session.request('report', key, config, GroqProvider(config), system, user, consent=True)
                    _record_budget(case, session, 'report')
                    message = 'AI-assisted overview prepared. Ethical findings remain rule-based.'
                    if response.data is not None:
                        try:
                            overview = validate_ai_report(response.data, context, case=case)
                            if len(cache) >= 8:
                                cache.pop(next(iter(cache)))
                            cache[key] = response.data
                        except (ValueError, TypeError, KeyError):
                            message = 'The suggested overview failed consistency checks. The deterministic report is retained.'
                    else:
                        message = _REASONS.get(response.reason, _REASONS['unavailable']) + ' The deterministic report is retained.'
                    st.session_state['_ai_report_notice'] = (key, message)
                    if response.attempted:
                        # The sidebar builds exports/autosave before this form
                        # is processed. Rebuild it with the spent request count
                        # before showing the completed report. Cached responses
                        # ensure this rerun cannot issue another model request.
                        st.rerun()
        notice = st.session_state.get('_ai_report_notice')
        if notice and notice[0] == key:
            st.info(notice[1])
        if overview:
            st.markdown(overview)
    return overview
