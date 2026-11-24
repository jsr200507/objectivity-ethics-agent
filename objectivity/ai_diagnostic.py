"""One explicit, fictional operator check; no retries or assessment changes."""
from dataclasses import dataclass
import os
import secrets

from .ai_provider import GroqProvider, provider_error_message
from .ai_usage import AISession
from .ai_understanding import build_understanding_prompt, parse_ai_understanding

FICTIONAL_SCENARIO = (
    'I am an accountant reviewing an estimate for a fictional company. '
    'My annual bonus depends on its reported profit.'
)


@dataclass(frozen=True)
class DiagnosticStep:
    name: str
    status: str
    detail: str = ''


@dataclass(frozen=True)
class DiagnosticResult:
    category: str
    steps: tuple[DiagnosticStep, ...]
    technical: dict
    attempted: bool = False
    reused: bool = False


def run_diagnostic(config, *, session=None, provider=None):
    """Use one JSON completion to check transport, JSON and source validation.

    The caller must obtain operator authorisation. Passing the same AISession
    reuses a result/failure instead of retrying it. Returned data contains no
    credential, generated body, real scenario, or full prompt.
    """
    names = ('Configuration loaded', 'HTTPS connection to Groq',
             'Authenticated Groq HTTP response', 'JSON completion',
             'Fictional scenario schema and attribution checks')
    steps = [DiagnosticStep(name, 'Not run') for name in names]
    steps[0] = DiagnosticStep(names[0], 'Passed' if config.enabled else 'Failed',
        'Required settings are present.' if config.enabled else provider_error_message(config.disabled_reason))
    if not config.enabled:
        return DiagnosticResult(config.disabled_reason, tuple(steps), {})
    session = session if session is not None else AISession(max_requests=1)
    provider = provider if provider is not None else GroqProvider(config)
    system, user = build_understanding_prompt(FICTIONAL_SCENARIO)
    result = session.request('understanding', 'operator-fictional-diagnostic-v1', config,
                             provider, system, user, consent=True)
    details = result.diagnostic
    status = details.get('http_status')
    received = status is not None and details.get('response_origin') == 'provider'
    category = result.reason
    if received:
        steps[1] = DiagnosticStep(names[1], 'Passed', 'An HTTPS HTTP response was received.')
        authenticated = 200 <= status < 300 and details.get('completion_received') is True
        steps[2] = DiagnosticStep(names[2], 'Passed' if authenticated else 'Failed' if status == 401 else 'Not established',
                                  f'HTTP {status}; a 2xx response with a completion envelope establishes this check.')
    elif result.attempted or result.reused:
        steps[1] = DiagnosticStep(names[1], 'Not established', provider_error_message(result.reason))
    if result.data is not None:
        steps[3] = DiagnosticStep(names[3], 'Passed', 'A JSON object was returned; no generated body is displayed.')
        try:
            parse_ai_understanding(FICTIONAL_SCENARIO, result.data)
        except (ValueError, TypeError, KeyError):
            category = 'application_validation'
            steps[4] = DiagnosticStep(names[4], 'Failed', provider_error_message(category))
        else:
            category = 'success'
            steps[4] = DiagnosticStep(names[4], 'Passed', 'The fictional source proposals passed application checks; facts are still unverified.')
    elif (received and 200 <= status < 300) or result.reason == 'generation_invalid_json':
        steps[3] = DiagnosticStep(names[3], 'Failed', provider_error_message(result.reason))
    return DiagnosticResult(category, tuple(steps), details, result.attempted, result.reused)


def _setting(name, default=''):
    import streamlit as st
    value = os.environ.get(name, default)
    try:
        if name in st.secrets:
            value = st.secrets[name]
    except Exception:
        pass
    return value


def render_operator_diagnostic():
    """Disabled by default; separate operator code gates one fictional call."""
    enabled = _setting('OBJECTIVITY_AI_DIAGNOSTICS_ENABLED', False)
    if enabled is not True and str(enabled).strip().lower() != 'true':
        return
    import streamlit as st
    from .ai_ui import load_config
    with st.expander('Operator: Groq connectivity diagnostic'):
        st.caption('One explicitly requested API call using only a built-in fictional case. This does not send or change your assessment. No API key or generated response is displayed.')
        token = _setting('OBJECTIVITY_AI_DIAGNOSTIC_TOKEN')
        if not isinstance(token, str) or len(token) < 16:
            st.info('Set a separate diagnostic access code of at least 16 characters in server Secrets before enabling this check. Do not use the Groq API key as the access code.')
            return
        with st.form('groq_operator_diagnostic'):
            entered = st.text_input('Diagnostic access code (not the API key)', type='password')
            submitted = st.form_submit_button('Run one fictional Groq check')
        if submitted:
            config = load_config()
            if token == config.api_key or not secrets.compare_digest(token.encode(), entered.encode()):
                st.warning('The diagnostic access code was not accepted. No request was sent.')
            else:
                if '_groq_operator_session' not in st.session_state:
                    st.session_state['_groq_operator_session'] = AISession(max_requests=1)
                st.session_state['_groq_operator_result'] = run_diagnostic(config,
                    session=st.session_state['_groq_operator_session'])
        result = st.session_state.get('_groq_operator_result')
        if result:
            st.write('Diagnostic category: ' + result.category)
            for step in result.steps:
                st.write(f'**{step.name}: {step.status}**')
                if step.detail:
                    st.caption(step.detail)
            st.json(result.technical)
            st.caption('This result uses only the fictional probe. It does not verify real-case evidence or all possible scenario responses. Repeat clicks reuse the result; no automatic retry is made. Disable diagnostics after verification.')
