# Objectivity Ethics Assistant

A Python and Streamlit assistant focused exclusively on the fundamental principle
of **Objectivity**. It follows **Identify → Evaluate → Address** and supports,
rather than replaces, professional judgment.

The scenario-driven workflow begins with a concise, prefilled summary for review,
then combines threat identification and evaluation in a guided stage. It adds
evidence-linked assessment of existing actions, residual-threat reasoning and a
downloadable Ethical Assessment Report. It uses free, open-source packages and
runs without API keys, subscriptions or external services. Optional, consented
AI assistance can suggest scenario facts and organise approved report wording.
Ethical evaluation, safeguard effectiveness and conclusions remain deterministic.
AI is disabled by default; no facts or conclusions are independently verified by
the application.

## Run locally

Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On Windows, activate the virtual environment with `.venv\Scripts\activate`.
Open the local URL printed by Streamlit. Stop the app with Ctrl+C. For a headless
environment, use `python -m streamlit run app.py --server.headless true`.
A cloud workspace's localhost is not necessarily accessible from another machine;
use that workspace's supported port-forwarding mechanism when available.

`app.py` remains the Streamlit entry point. The development-container launch
command also targets `app.py`.

## Optional AI assistance

The complete local workflow remains available without AI configuration. The
optional Groq-compatible adapter requires a server-side key, an explicitly
selected model, operator confirmation of an eligible free-tier configuration,
and user consent before case information can leave the application. A key alone
does not enable requests; a lecturer never needs to supply a key.

Current free-tier, model, regional and data-handling information could not be
verified: bounded requests to Groq's official documentation returned the network
proxy error `Tunnel connection failed: 403 Forbidden`. No live credential or
inference call was tested. There is no default model or guaranteed free quota.
Keep AI unconfigured until the operator has checked the current official terms,
account plan and model availability. See [configuration, consent, limits and
verification details](docs/optional-ai.md).

Initial assistance produces structured, evidence-linked candidate records for
Step 1 review. Optional report assistance selects and orders approved,
case-specific wording variants; it does not perform unrestricted report rewriting
or replace the full nine-section deterministic report. Invalid output, timeouts,
rate limits and exhausted allowances retain local functionality and progress.
The normal opted-in target is one understanding request and one optional overview
request, with a configurable hard maximum of three attempts per assessment.

## Current user workflow

**Scenario Input → Step 1: Understand Your Scenario → Step 2: Identify & Evaluate
Threats → Step 3: Address Threats → Final Ethical Assessment Report**

1. Enter a scenario and select **Review scenario**, or choose **Try CFO example**.
   If optional AI is configured, initial assistance requires the separate
   **I consent to optional external AI-assisted understanding of this scenario.**
   checkbox before submitting **Review scenario**. The authored CFO example loads
   locally without an external request.
   Step 1 automatically prefills six concise summary sections: professional role
   and decision; people and relationships; financial, commercial and career
   interests; reported pressure or influence; material uncertainties; and actions
   already mentioned. Uncertain information is highlighted. The original narrative
   and detailed source records stay in optional expandable sections.
2. Use **Correct or add details** if anything is missing or inaccurate. Inspect
   **Source excerpts and detailed records**, correct an individual fact's meaning,
   evidence status or parties, or add a missing party or explicitly typed fact.
   Tick **These records reflect my account, including uncertainties.**, then select
   **Confirm scenario and continue**. This is one account-confirmation step, not
   independent verification of the events.
3. In **Step 2: Identify & Evaluate Threats**, the active material question is the
   main interaction. It names the relevant threats, explains **Why this question?**
   and how the answer could affect the evaluation. Select **Record answer and
   reassess** to update the findings. Known facts are reused; an explicit
   **Unknown** remains a limitation and is not repeatedly asked. Where no material
   clarification is needed, the app explains the evaluation without inventing a
   question.
4. Review the current threat categories, scenario-specific mechanisms, acceptable-
   level assessments and uncertainties. Supporting sources and the hypothetical
   reasonable and informed third party reasoning are available in an expander.
   Use **Review scenario summary** to revisit the account. Material corrections
   return to Step 1 for confirmation and recalculate dependent findings.
5. Select **Review existing actions** to open **Step 3: Address Threats**:
   “What steps, if any, have you already taken to address these concerns?” Actions
   recognised in the scenario are prefilled for review. Describe an action and
   explicitly choose its type, status and threat coverage rather than repeating
   facts already recorded. **No relevant action has been taken** and **Existing
   actions are not known** are available where relevant.
6. Answer only the action-evidence questions currently material to effectiveness.
   Correct earlier evidence through the action editor as new information emerges.
   Review current protection, residual concerns and scenario-specific next steps.
   If the recorded circumstances already justify an acceptable-level assessment,
   the app explains why and does not force additional safeguards or an artificial
   implementation questionnaire.
7. Select **Generate Objectivity report** and download Markdown if required.
   If configured, **Optional AI-assisted report overview** requires its own
   external-processing consent and explicit request. It cannot change ethical
   findings or reported action stages; the full deterministic report remains
   available whether or not assistance succeeds.
   Revisit source facts or actions to recalculate the report. A downloaded report
   is a revision-specific snapshot and must be regenerated after material changes.
8. Use **Download progress** for a portable JSON backup. On reopening the same app
   in the same browser profile, choose **Resume previous assessment**. Use
   **Import progress** to restore a backup elsewhere.

The stage indicator explains where you are in the journey. On explicit navigation,
the current stage is brought into view so its question is visible; ordinary
record-editing reruns do not force a scroll jump. Identify and Evaluate share one
user-facing stage while remaining distinct reasoning operations and report
sections. Only submitted form values are saved; unsubmitted text and unsaved edits
are not part of autosave or exported progress.

## Evidence and Objectivity reasoning

The local understanding provider, optionally supplemented by validated AI
proposals, identifies actors, professional activities,
relationships, actual beneficiaries, reported influence and existing actions.
Supported narrative proposals retain literal source excerpts. The provider does
not issue ethical verdicts. Users must review the concise account before the
main ethical assessment. Source validation and attribution rules reduce specific
errors; they do not prove that every interpretation is accurate. Authored reasoning
rules consume the source ledger and generate distinct threat instances tied to
the relevant actor, decision and source information.

| Potential threat | Evidence-supported mechanism |
| --- | --- |
| Self-interest | A reported financial or other interest potentially connected to the decision, with the actual beneficiary retained |
| Familiarity | A family or explicitly close personal connection relevant to professional judgment; employment alone does not establish participation in the work |
| Intimidation | Reported pressure or influence that could deter objective judgment; a request is not automatically coercion or a completed change to work |
| Self-review | An explicit connection between earlier work and subsequent assessment of that work |
| Advocacy | An explicit promotion or representation of a position that must subsequently be assessed objectively |

Only supported categories appear. Multiple incentives or parties can create
separate instances within the same category; the user's bonus, a sister's
shareholding, a director's fee and firm income are not interchangeable sources.
A family connection does not establish closeness, employment does not establish
participation, and another person's financial benefit does not establish the
user's ownership. Self-review and advocacy are not added merely because the other
three categories appear. Combined-threat reasoning considers interactions without
treating repeated descriptions of one event as independent corroboration.

Reported narrative, user-supplied corrections, disputed accounts and explicit
unknowns remain distinguishable. AI suggestions remain candidate accounts until
reviewed. User review means the records reflect the user's
account; it is **not independent verification**. Possible future recovery or an
assurance by management remains an attributed claim. Extra explanatory text is
retained as reported context and is not automatically interpreted into new facts.

Evaluation distinguishes **At an acceptable level**, **Not at an acceptable
level** and **Acceptability not established**. These are evidence-linked,
conditional outcomes, not numerical ethics scores or declarations of misconduct.
Missing information or no identified threat is not assurance that threats are
absent. A reported change to work differs from
possible future influence and does not itself prove technical error.

An acceptable-level outcome requires specific recorded circumstances that remove
or sufficiently narrow the source's route to influence this decision. Examples
include an explicitly unrelated financial interest, or no current involvement
with no earlier work affected. A historical relationship without current ties
cannot justify that outcome if a relevant participation or financial link remains
unresolved. These considered threats remain visible in the evaluation and report,
with the supporting reasons; they are not silently discarded. User confidence,
confirmation and reported implementation alone cannot establish acceptability.

The reasonable and informed third party test asks how a hypothetical reasonable
and informed person would assess the recorded circumstances and protective
measures. It is applied conditionally to the particular decision and sources;
no actual independent third party has reviewed the application's findings.

## Existing actions, effectiveness and residual threats

Address begins with the conversational prompt about what has already happened or
been proposed, with reported actions prefilled for review. An omitted action is
not treated as proof that no action was taken. Distinct source statuses are
**Not Taken**, **Planned**, **Implemented** and **Unknown**; effectiveness supported
by appropriate evidence is a derived, conditional finding rather than a status a
user can grant an action. Users can link several actions to particular threat
instances rather than one category-wide response silently
covering all sources.

Implementation and effectiveness are separate. A requested review remains
**Planned**. Reported completion remains **Implemented** until the action-specific
record supports coverage, timing, outcome and the relevant protective mechanism.
For independent review this includes independence, competence and authority;
removal needs an independent replacement where relevant. Prior work already
affected may need reassessment even if someone is removed from the decision.
Selecting that records exist is insufficient without a description of the
supporting records and what they demonstrate.

Disclosure, escalation and documentation can support a response, but are not
automatically effective safeguards. The resulting protective measure needs its
own assessment. A known weakness, partial implementation, continuing influence,
missing scope or explicit Unknown prevents an unsupported positive conclusion.
Evidence questions stop at a material blocker instead of completing an irrelevant
checklist; the editor permits revisiting that answer later. If no action has been
taken, recommendations explain practical responses for the specific sources and
remain recommendations. They do not count as completed measures or reduce a threat.

Where appropriate implementation, coverage and outcome evidence support it, an
action can be assessed as effective **conditionally on the recorded evidence**.
The app does not require an invented universal external-checker rule and does not
authenticate the user's description of records or an external review. A measure
addressing one source does not automatically resolve other threats. Material
source changes invalidate dependent answers or coverage and retain their earlier
records for reconsideration; stale positive conclusions are not trusted.

Where existing protective circumstances already justify an acceptable-level
assessment, Address records that basis and whether additional action is needed.
It does not force new safeguards for those sources. A different unresolved or
unacceptable threat still needs its own response; protection of one source cannot
clear the whole case.

The Markdown report preserves the complete reasoning chain. Its nine sections
include explicit **IDENTIFY**, **EVALUATE** and **ADDRESS** labels:

- Scenario summary and reported context.
- Identified potential Objectivity threats and supporting sources.
- Threat evaluation and combined influences.
- Reasonable and informed third party assessment.
- Existing and planned actions, recommended responses, and any justified basis
  for no additional safeguards.
- Safeguard effectiveness and remaining evidence gaps.
- Residual threats.
- Prioritised next steps.
- Overall conditional ethical conclusion and limitations.

An actions/safeguards section is always present, including when no new safeguards
are indicated. It explains the existing conditions supporting that result.
Recommended but unimplemented measures remain distinct from completed actions.

Reports are recomputed from current source records and use professional wording,
without internal question or fact keys. They summarise reasoning rather than
reproduce the full question transcript. Original sources, edits and superseded
answers remain in progress data.

## Previous saved assessments

The previous Phase 1–3 guided workflow remains available for compatibility through
**Previous guided assessment (optional)** and **Previous guided example
(optional)**. Existing saved stages, structured context, answer editing,
superseded history and reports can continue there.

For an existing saved assessment, **Reassess this saved case with the
scenario-driven workflow** offers an explicit opt-in conversion. Original
Phase 1–3 source answers and archives remain intact; retained history is not a
trusted conclusion. Clear structured information is reused as reported source
information. Ambiguous ownership or category-level action coverage requires
review before the new assessment can rely on it. The previous workflow's three
threat categories are not silently expanded into unsupported new findings.

## Save & Resume

`st.session_state` still holds the active assessment. A small, self-contained
Streamlit component saves a versioned JSON snapshot to this browser's
`localStorage` after submitted progress or the workflow stage changes. A save is
reported as complete only after the browser acknowledges writing and reading
back that exact snapshot. Nothing relies on session state alone surviving a
refresh. There is no database, account, paid service, external script or permanent
server-side assessment file.

When a browser copy exists, **Resume previous assessment** is an explicit choice;
it is not silently loaded over work already in the current session. Replacing
current work, importing progress, or starting over requires confirmation.
**Start new assessment** / **Start a new scenario** clears the saved assessment
only after confirmation and acknowledgement. A content-free coordination record
remains; it contains no scenario or answers. If deletion cannot be confirmed, the
app says so and retains the current assessment.

Each browser save stores the current scenario, actor and source-fact ledger,
submitted clarification answers, actions and evidence responses, source revisions
and superseded history, review status and workflow stage. Legacy context, answers
and supporting-action slots are retained when present. It excludes widget state,
evaluations and reports. Non-evidential AI request counts and understanding-mode
notes are retained in source history to preserve the assessment's allowance across
refresh/import. API keys, consent controls and raw completed response caches are
not exported; response reuse is held in server-session memory only. Restoration
validates the records and recomputes dependency signatures, questions, findings
and reports. Stale conditional answers are retained in history with a notice;
an incompatible stage moves back to review. A case whose source account is not
confirmed returns to the Step 1 summary before evaluation or the report. New widget
generations prevent old form selections appearing in a restored assessment.

Only **submitted** progress is saved. Use Continue / Save in forms: unsubmitted
text and unsaved edits are not included in autosave or export. This feature does
not add draft-text interpretation or change evidence status.

### Portable backups and validation

**Download progress** exports UTF-8 JSON. **Import progress** first validates it
without changing current work, then requires confirmation before restoration.
The format has an application name, schema version and compatible rules version.
New exports use **schema 3**, with scenario-driven source records in a separate
`objectivity-case-v1` envelope. Schema 1 and 2 backups and browser saves remain
importable and can continue in the previous guided workflow. They do not acquire
invented answers, verification or conclusions. The browser storage slot is
unchanged. Older application versions cannot read schema 3 until updated.
Exports contain source answers and dependency bindings, not trusted conclusions.
It uses allowlisted fields, structured-choice validation and bounded parsing:
2 MiB maximum, bounded text/history/action counts and nesting. Duplicate fields,
nonstandard numbers, unsupported versions, invalid evidence-status claims and
malformed structures are rejected. There is no pickle, executable evaluation or
arbitrary object deserialization. Imported conclusions are never accepted.

Corrupt or incompatible browser copies are preserved until an explicit choice
to clear them. A bounded raw browser-copy download is offered where available.
JSON import/export remains available if local storage, coordination support or
the component is blocked. A missing acknowledgement never means a save succeeded.

### Reliability and privacy limits

- Browser autosave requires the locally served component to have a same-origin
  parent, usable local storage, Web Locks and browser cryptography. It works in
  the tested Chromium environment. Unsupported or blocked storage falls back to
  JSON backups; there is no claim that every browser or hosted embedding works.
- One assessment is saved per browser profile and app origin (scheme, hostname
  and port). Different origins/profiles do not share it; use JSON to transfer it.
  Writes and clearing use an exclusive browser lock and a saved-version token.
  A stale tab cannot silently overwrite a newer copy. The app pauses autosave on
  conflict and asks which version to keep. A replacement/deletion waiting behind
  a conflicting autosave is cancelled and needs a fresh confirmation.
- With explicit consent, scenario information and later validated assessment
  clauses may be sent to the configured external provider. Use fictional or
  appropriately anonymised cases and review the provider's current data terms;
  browser-local storage does not describe that external processing.
- Browser-local data and exported JSON may contain sensitive scenario details.
  Use fictional or anonymised cases. Storage is not encrypted or access-controlled
  by an application account; someone using the same browser profile may read it.
  Progress sent to the app for processing remains in the active server session,
  not permanent application storage.
- Clearing site data, browser policies, storage quotas and private browsing can
  remove or prevent saves. Private browsing may appear to work until its windows
  close. Keep a JSON backup of anything important.
- JSON files are editable records of user accounts, not authenticated evidence
  or proof that actions or independent checks actually occurred. All professional
  judgment and verification limitations continue to apply.

The existing storage bridge has local Chromium coverage for refresh and explicit
resume, closing/reopening a persistent browser profile, confirmed clearing, actual
JSON download/upload, stale-tab conflicts, corrupt copies and blocked/full storage.
The scenario-driven workflow adds source-codec, restoration and schema-migration
regressions. Local tests do not establish that a hosted deployment has been updated
or that every browser or embedding supports the storage component.

## Code structure

- `app.py`: unchanged Streamlit/deployment entry point.
- `objectivity/case_model.py`: provider-neutral actors, source facts, actions,
  revisions, material questions and derived reasoning contracts.
- `objectivity/understanding.py`: local English understanding provider and source
  proposal validation; the application does not require another provider.
- `objectivity/ai_provider.py`: replaceable JSON-provider protocol, optional
  server-side Groq-compatible transport, bounded input/output and safe failures.
- `objectivity/ai_usage.py`: per-assessment request caps, success/failure reuse,
  rerun protection and best-effort process-level concurrency/rate controls.
- `objectivity/ai_understanding.py`: strict schema, literal-source and attribution
  checks for candidate facts; it cannot create ethical verdicts.
- `objectivity/ai_report.py`: bounded selection of approved report clauses and
  wording variants, with stale-source and contradiction checks.
- `objectivity/ai_ui.py`: explicit consent, visible mode, fallback and request
  history coordination; it does not export credentials or raw response caches.
- `objectivity/case_reasoning.py`: source-linked threat instances, material-gap
  selection, significance, combined influences and third party reasoning.
- `objectivity/case_workflow.py`: source correction, answer invalidation, action
  updates and explicit conversion of legacy progress.
- `objectivity/case_actions.py`: conditional evidence questions, action
  effectiveness, residual threats and case-specific recommendations.
- `objectivity/case_report.py`: current-snapshot nine-section Markdown report.
- `objectivity/case_summary.py`: pure, bounded projection of existing case records
  into six readable summary sections; it does not perform new extraction or
  ethical reasoning and does not discard the detailed sources.
- `objectivity/case_ui.py`: concise scenario confirmation, combined guided
  Identify & Evaluate interaction, conversational Address and the final report
  over the shared source model.
- `objectivity/navigation_ui.py`: a local stage-focus helper that keeps new
  questions visible after navigation without moving ordinary record edits.
- `objectivity/case_codec.py`, `objectivity/progress.py`: bounded versioned source
  serialization, legacy compatibility and validated restoration.
- `objectivity/ui.py`, `objectivity/models.py`: application routing and legacy
  assessment state, with the new source case alongside existing state.
- `objectivity/extraction*.py`: reusable role, actor, activity, ownership and
  influence patterns used by local understanding and previous context suggestions.
- `objectivity/intake*.py`, `objectivity/context_suggestions.py`: previous
  progressive context suggestions and clarification.
- `objectivity/questions.py`, `objectivity/evaluation*.py`, `objectivity/review.py`,
  `objectivity/address*.py`, `objectivity/report.py`: previous guided assessment
  logic and UI retained for saved-data compatibility.
- `objectivity/save_state.py`, `objectivity/progress_ui.py`: save acknowledgements,
  saved-version coordination, confirmations and import/export controls.
- `objectivity/browser_storage.py`,
  `objectivity/browser_component/index.html`: local storage bridge without
  external assets or a build step.
- `tests/test_case_*.py`, `tests/test_understanding.py`: new reasoning, source
  attribution, material questioning, action evidence, report, UI, restoration and
  migration, confirmation/editing and no-unnecessary-question regressions.
- `tests/test_ai_*.py`: mocked transport, consent, grounding, request limits,
  rerun reuse, failures, report consistency and complete Streamlit journeys.
- Other `tests/test_*.py`: retained Phase 1–3, extraction, progressive context,
  save/resume, JavaScript bridge and UI regressions.
- `tests/test_property_comparison.py`: representative valuation, career and
  financing interests, attributed assumptions, scoped family participation and
  unfamiliar-context regressions.

## Hybrid provider boundary

`UnderstandingProvider` and `UnderstandingResult` remain the source-contract
boundary. The optional JSON-provider transport can be replaced without rewriting
the evidence model or ethical engine. AI output is schema-validated and grounded
in source excerpts before the existing user-confirmation step; it cannot establish
verification, acceptable-level judgments, implementation, effectiveness or ethical
clearance. The deterministic report and all local assessment stages remain usable.

Complex free-text interpretation is not implemented in this version. Ordinary
Yes, No and Unknown answers, navigation, reruns and downloads do not trigger
model calls. See [optional AI details](docs/optional-ai.md) for request ceilings,
cache boundaries, deployment configuration and remaining limitations.

## Separate Streamlit test application

Create a **new** Streamlit Community Cloud app with these settings:

| Setting | Value |
| --- | --- |
| Repository | `jsr200507/objectivity-ethics-agent` |
| Branch | `dev/hybrid-genai-v5` |
| Main file path | `app.py` |
| Advanced settings — Python | `3.12` |
| Secrets | Leave empty for deterministic mode; optional operator settings are documented below |
| App URL | Choose a new, unused test-app subdomain |

The root `requirements.txt` is installed automatically. No API key, additional
service or paid subscription is required for the complete deterministic workflow.
For optional assistance, use only server-side Secrets after verifying the eligible
free provider/account/model and user-consent requirements in
[the configuration guide](docs/optional-ai.md). Leave existing production and preview
apps unchanged. These settings describe creating a separate test app; they do not
mean one has been deployed.

## Run checks

With the virtual environment activated:

```bash
python -m unittest discover -s tests -v
python -m pip check
git diff --check
```

The test runner uses Python's standard-library `unittest` and Streamlit's bundled
AppTest; there is no new application or test dependency. AppTest may print a
harmless missing-ScriptRunContext warning outside a server. Browser-bridge tests
also exercise the actual JavaScript in Node when available; those checks skip
if Node is absent. Node is not an application/runtime dependency. Real browser
refresh/reopen, storage acknowledgements and file uploads require browser checks;
AppTest alone cannot establish browser persistence.

Focused mocked-AI checks:

```bash
python -m unittest tests.test_ai_provider tests.test_ai_usage tests.test_ai_understanding tests.test_ai_report tests.test_ai_ui -v
```

No automated test requires live credentials or consumes provider quota. Mocked
checks establish controlled behavior, not live provider availability. Real browser
checks separately exercise assisted mode with controlled responses and the
complete no-key fallback journey.

Representative cases include the CFO friendship/revenue/contract-renewal case;
inventory recognition with separate personal bonus and company interests;
procurement with distinct family and director interests; family employment with
unknown participation; a representative property valuation with separate career
and company-financing interests and attributed technical assumptions; explicit
self-review and advocacy; incomplete information;
revised facts; planned, partial or failed actions; and appropriately evidenced
conditional protection; no-clarification cases; and justified acceptable-level
cases needing no additional safeguards. Materially different answers must produce
different qualified findings rather than one generic report.

## Functional and professional limitations

- Live provider connectivity, current free-tier eligibility, model availability
  and data terms remain unverified in this workspace. Configure no external
  assistance until the operator can verify them. The full app remains functional
  with AI disabled.
- AI grounding checks cannot prove unrestricted language interpretations correct.
  Novel ambiguous proposals may be rejected conservatively; the source account
  must still be reviewed. The optional report overview uses approved wording
  rather than arbitrary generated prose and cannot revise the ethical conclusion.
- Local English grammars do not understand unrestricted narratives. Unfamiliar
  wording, actors, pronouns, attribution, negation and multiple decisions may be
  missed or misclassified. Inspect source excerpts and use typed corrections;
  the assistant must not be relied upon to discover every relevant circumstance.
- Repeated questions are avoided only within the fact scopes represented by the
  rules. Free-text explanations are not automatically converted to structured
  evidence or professional conclusions. Explicit Unknown remains a limitation.
- Positive action assessment is conditional on reported evidence and explicit
  coverage. The app does not inspect documents, authenticate outcomes, verify
  facts or provide professional validation or a certified ethical opinion.
- Only Objectivity is assessed. Separate audit-independence and other professional
  requirements may need their own assessment. Current authoritative standards,
  jurisdiction and circumstances must inform real decisions. No fabricated
  ACCA/IESBA paragraph references or complete Code-compliance claims are used.
- Authored rules require maintenance and professional review. Human responsibility
  for final judgment remains unchanged. User confidence, confirmation or a
  proposed action cannot establish ethical acceptability, safeguard effectiveness
  or verified facts.
- Browser storage is local to one app origin/profile and may be unavailable or
  lost. Keep JSON backups, use anonymised cases and review the privacy limits
  above. There is no account, database or permanent server-side assessment store.

The existing Streamlit deployment can retain `app.py` and the unchanged
`requirements.txt` (`streamlit>=1.40,<2.0`). New assessment modules use only the
standard library and existing Streamlit functionality; the optional transport
adds no SDK or paid dependency. Local checks validate the
installed runtime; they do not mean changes have been committed, pushed or
deployed, or establish the state of any live production or preview app.
