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
OBJECTIVITY_AI_TIMEOUT_SECONDS = 30
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
- The HTTP I/O timeout defaults to `30` seconds and is bounded to `2–60`.
  An explicitly configured timeout is respected; an existing setting of `12`
  does not automatically become `30`.
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

## Groq connectivity hotfix — GPT-OSS 120B

The operator reports an active Groq Free Plan and successful Playground use of
`openai/gpt-oss-120b`. This confirms their reported account/model access, but not
the separate Streamlit-to-Groq connection. No deployment credential was available
in this workspace, and no live inference call was made during this hotfix.

The baseline mapped HTTP 403, HTTP 5xx and most connection errors to the same
`unavailable` message. That message cannot establish the deployed root cause.
The hotfix distinguishes DNS/network, proxy, TLS, timeout, HTTP 400/401/403/404/
429/5xx, invalid JSON, truncated output, runtime errors, and application schema or
evidence rejection. An application validation rejection means JSON was returned;
it is not labelled as a network failure. Server warnings contain only the fixed
category and allowlisted technical fields, never error bodies, keys or prompts.

Hosted Groq documentation requests were rejected by this workspace's proxy (403).
Groq's official Python SDK documentation was readable and checked at commit
[`55066d94acca028c3cb74e050f2711b80ade6298`](https://github.com/groq/groq-python/tree/55066d94acca028c3cb74e050f2711b80ade6298):

- [Chat request parameters](https://github.com/groq/groq-python/blob/55066d94acca028c3cb74e050f2711b80ade6298/src/groq/types/chat/completion_create_params.py)
  list GPT-OSS 120B, JSON-object mode, `max_completion_tokens`, and GPT-OSS
  `reasoning_effort` values `low`, `medium` and `high` (default `medium`).
- [Chat resource](https://github.com/groq/groq-python/blob/55066d94acca028c3cb74e050f2711b80ade6298/src/groq/resources/chat/completions.py)
  uses `/openai/v1/chat/completions`.
- [Response documentation](https://github.com/groq/groq-python/blob/55066d94acca028c3cb74e050f2711b80ade6298/src/groq/types/chat/chat_completion.py)
  distinguishes `stop` from `length` (token limit).

JSON-object mode is retained. The deprecated `max_tokens` alias is replaced by
`max_completion_tokens`; deprecation alone does not prove it caused this failure.
GPT-OSS requests explicitly use low reasoning effort to conserve latency and the
existing output allowance. Reasoning-format/include-reasoning combinations are
not added. The client identifies itself with a fixed User-Agent, keeps normal CA
verification/proxy handling and rejects redirects. Truncated or ungrounded output
is still rejected. None of these changes proves the live connection is repaired.

### One explicit operator check in Streamlit Cloud

1. Create a **separate** test app from `fix/groq-api-connectivity`, entrypoint
   `app.py`, Python `3.12`; do not repoint existing deployments automatically.
2. Copy the existing server-side Groq settings into that app's Secrets, including
   `GROQ_API_KEY`, provider `groq` and free-tier confirmation. Add:

   ```toml
   OBJECTIVITY_AI_MODEL = "openai/gpt-oss-120b"
   OBJECTIVITY_AI_TIMEOUT_SECONDS = 30
   OBJECTIVITY_AI_DIAGNOSTICS_ENABLED = true
   OBJECTIVITY_AI_DIAGNOSTIC_TOKEN = "REPLACE_WITH_A_SEPARATE_RANDOM_OPERATOR_CODE"
   ```

   Replace the access-code placeholder with a private value of at least 16
   characters. It must be different from the API key. Never put the API key in
   the browser input, repository, screenshots or diagnostic feedback.
3. On Scenario Input, expand **Operator: Groq connectivity diagnostic**, enter
   the separate code and select **Run one fictional Groq check** once.
4. The check sends one built-in fictional scenario, using the same provider,
   parameters and source-validation pipeline. It reports configuration, HTTPS,
   authenticated completion-envelope response, JSON parsing, and full fictional
   source validation separately. Only a 2xx completion response establishes the
   authenticated-response check. A 403 or 5xx response does not establish it.
5. Record only the category, stage statuses and safe technical fields. These
   include HTTP status, a bounded request ID when available, finish reason and
   exception class. The same safe failure category is available in app logs.
   No raw generated content or confidential assessment is displayed or sent.

The probe has a separate one-request session allowance and shares the process
rate/concurrency guard. Reruns and repeat clicks reuse its success or failure.
It does not change assessment answers or their request budget. After changing
Secrets, deliberately reload into a fresh session before checking again; there
are no automatic retries. Disable `OBJECTIVITY_AI_DIAGNOSTICS_ENABLED` and remove
the diagnostic token after verification.

If stages 1–5 pass, one real fictional API/understanding request has succeeded.
If JSON succeeds but the final stage fails, investigate application schema or
attribution compatibility without disabling grounding checks. A successful
fictional probe does not verify real scenario facts or guarantee every model
response will pass validation. Use a fresh fictional assessment with normal AI
consent for the next end-to-end check.

Targeted checks (mocked; no API quota consumed):

```bash
python -m unittest tests.test_groq_connectivity tests.test_ai_provider tests.test_ai_usage tests.test_ai_ui -v
```
