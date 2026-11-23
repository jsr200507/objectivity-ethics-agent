# Optional AI: configuration, consent and limits

The full application works without a key or network service. Leave this feature
unconfigured to use deterministic scenario understanding, ethical evaluation,
actions, persistence and reports. `app.py` remains the Streamlit entrypoint;
`requirements.txt` remains unchanged. The optional transport uses Python's
standard library rather than a provider SDK.

## Availability has not been verified

The adapter supports a Groq-compatible JSON chat endpoint. During this task on
23 November 2026, requests to Groq's official documentation failed through the
workspace network proxy with `Tunnel connection failed: 403 Forbidden`. The
current bounded check covered models, rate limits, free-versus-paid plans,
supported countries, data policies and OpenAI compatibility; none returned
official content. No live API credential was supplied or live inference tested.

Consequently no current free model, quota, regional eligibility or usable live
free provider was verified. There is **no default model** and no promise of free
availability. The implementation and controlled tests establish the optional
integration boundary and fallback, not a verified provider account.

Before enabling it, the operator must review the relevant current official
information and their actual account:

- [Groq models](https://console.groq.com/docs/models)
- [Rate limits](https://console.groq.com/docs/rate-limits)
- [Free versus paid](https://console.groq.com/docs/production-readiness/free-vs-paid)
- [Supported countries](https://console.groq.com/docs/supported-countries)
- [Structured output](https://console.groq.com/docs/structured-outputs)
- [OpenAI compatibility](https://console.groq.com/docs/openai)
- [Data policies](https://console.groq.com/docs/your-data)

These are verification links, not claims that their contents or current URLs
were successfully checked here. Confirm a currently supported text model,
eligible free plan without paid billing, service/regional terms and data policy
before setting the operator acknowledgement below. Never route around regional
or service restrictions. The app does not create an account, select a paid plan,
enable billing or guarantee that an operator's settings remain free.

## Server configuration

For a **new, separate** Streamlit Community Cloud test app, use repository
`jsr200507/objectivity-ethics-agent`, branch `dev/hybrid-genai-v5`, main
file `app.py`, and Python `3.12`. Leave Secrets empty for deterministic mode.
Do not change an existing deployment when testing this branch.

After the operator has verified eligibility, add the following in that new app's
**Settings → Secrets**. Replace both placeholders with server-side values from
the eligible account. The model placeholder is not a real or recommended model.

```toml
GROQ_API_KEY = "REPLACE_WITH_YOUR_API_KEY"
OBJECTIVITY_AI_PROVIDER = "groq"
OBJECTIVITY_AI_MODEL = "REPLACE_WITH_A_CURRENT_FREE_MODEL_ID"
OBJECTIVITY_AI_FREE_TIER_CONFIRMED = true

# Optional engineering ceilings, not provider quota claims:
OBJECTIVITY_AI_MAX_REQUESTS = 3
OBJECTIVITY_AI_MAX_INPUT_TOKENS = 7000
OBJECTIVITY_AI_MAX_OUTPUT_TOKENS = 1800
OBJECTIVITY_AI_TIMEOUT_SECONDS = 12
```

Environment variables with these exact names are also supported. Use the string
`true` for the confirmation variable in an environment. Streamlit Secrets take
precedence when the same setting exists in both places. A missing secrets file is
normal and does not prevent startup.

Do not put a real credential in Python code, a README, an exported JSON file,
browser input or Git. Prefer managed Secrets or your process environment. If
using a local `.streamlit/secrets.toml`, ensure that path is excluded from version
control before creating it; do not commit a real secrets file or `.env` file.
The application does not display key values or include them in progress data.

The key, explicit model and free-tier confirmation are all required. A missing
value, invalid model identifier or unsupported provider leaves assistance
disabled. The operator acknowledgement records a configuration choice; it is not
programmatic verification of free billing or country eligibility.

## User consent and visible mode

An enabled configuration does not itself authorise transmission.

1. At scenario input, the user must select **I consent to optional external
   AI-assisted understanding of this scenario.** before submitting. Only that
   explicit submission can send the scenario. A declined or unavailable consent
   option uses the local provider.
2. The confirmed case displays **AI-assisted understanding** or **Deterministic
   fallback**, with a safe explanation where appropriate. Both retain the same
   rule-based ethical evaluation and no independent verification.
3. At the report, **Optional AI-assisted report overview** has a separate consent
   control: **I consent to send this assessment and recorded actions to the
   external provider for an optional overview.** The user must also select
   **Create AI-assisted report overview**. Initial scenario consent does not
   automatically cover this second transmission.

Use fictional or appropriately anonymised scenarios. The scenario and current
case clauses can contain sensitive professional information even when names are
removed. Provider processing is external to browser-local storage; review its
actual current retention and service terms. Neither mode independently verifies
the events, reviews actual documents or provides a certified ethical opinion.

## What the optional model can change

Initial understanding produces structured source proposals. Schema validation,
literal-source evidence and local attribution checks must accept those proposals
before they enter the normal user review step. Unsupported or malformed output
causes local fallback. This does not make all interpretations reliable or prove
the underlying events occurred.

The report mode is intentionally narrower than unrestricted AI rewriting. The
model selects and orders approved, case-specific wording variants constructed
from the current validated assessment. It cannot supply arbitrary prose, omit a
required threat or action, invent a safeguard, upgrade implementation or replace
the deterministic conclusion. Output inconsistent with the current case is
rejected and the full nine-section rule-based report remains available. Material
facts or safeguard edits invalidate earlier overview selections.

Ordinary structured answers are handled locally. This version does not send
ambiguous free-text answers to a model automatically. It does not call the API
for every question, navigation event, rerun, refresh or report download.

## Request budget and fallback

A typical opted-in completion targets one initial understanding call and one
optional overview call. This is an engineering target, not a provider allowance.

- The per-assessment default is three attempted requests; the operator can lower
  it to `0`, `1` or `2`. The implementation caps it at three.
- Input allowance defaults to `7000`; it is conservatively checked using UTF-8
  bytes plus message overhead as a token-budget ceiling. This is not an exact
  model-token count. Input settings are bounded to `256–16384`.
- Requested output defaults to `1800` tokens and is bounded to `128–4096`.
- The HTTP I/O timeout defaults to `12` seconds and is bounded to `2–30`.
- Requests and failures are cached by purpose, actual prompt, relevant source
  signature, provider, model and generation settings within the active session.
  Repeated reruns do not resubmit a completed attempt. A material report change
  invalidates its report selection without repeating unchanged understanding.
- Provider rate limits, quota failures, rejected credentials and unsupported
  configuration stop further calls for that assessment session. There are no
  automatic retry loops and no paid fallback provider.
- A process-local guard permits at most two concurrent provider calls and twelve
  starts per minute, with a cooldown after rate/quota failures. Busy visitors can
  continue deterministically instead of waiting through repeated retries.

Missing configuration, no consent, input excess, budget exhaustion, timeout,
provider failure, invalid JSON and failed proposal/report validation all retain
deterministic functionality. Errors shown to the user do not include raw provider
response bodies, credentials or complete case prompts.

Attempt counts are stored as non-evidential assessment history and therefore
survive normal browser autosave, refresh/resume and JSON export/import. API keys,
raw response caches and consent controls are not exported. Completed responses
and overview selections are retained in server-session memory only; refreshing
does not automatically consume another request to recreate them. A later
explicit request can consume the remaining allowance.

These controls are not account authentication or guaranteed organisation-wide
quotas. JSON is user-editable, a new assessment can have a new budget, process
restart loses the shared in-memory guard, and multiple deployment processes do
not share one limiter. Provider-enforced account limits remain necessary. Never
enable paid billing on the assumption that application controls guarantee zero
charges.

## Checks

Run the complete regression suite from the repository root:

```bash
python -m unittest discover -s tests -v
python -m pip check
git diff --check
```

Focused optional-AI checks use mocked providers and controlled responses:

```bash
python -m unittest tests.test_ai_provider tests.test_ai_usage tests.test_ai_understanding tests.test_ai_report tests.test_ai_ui -v
```

These tests use controlled responses and exercise consent gates, attribution, unsupported facts, malformed output,
timeouts, limits, rerun reuse, changed facts and contradictory report wording.
They do not establish live API connectivity or current free-tier access. Browser
tests must separately exercise the full no-key fallback journey, confirmation,
editing, refresh/resume, actual JSON upload/download and report download.
