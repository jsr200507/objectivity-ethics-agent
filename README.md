# Objectivity Ethics Assistant

A Python and Streamlit assistant focused exclusively on the fundamental principle
of **Objectivity**. It follows **Identify → Evaluate → Address** and supports,
rather than replaces, professional judgment.

The scenario-driven workflow provides immediate provisional findings, focused
clarification, evidence-linked evaluation of existing actions, residual-threat
reasoning and a downloadable Ethical Assessment Report. It uses free,
open-source packages, with no paid APIs, subscriptions, API keys or external AI
services. It does not provide generative AI or independent fact verification.

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

## Current user workflow

1. Enter a scenario and select **Identify potential threats**, or choose
   **Try CFO example**. Provisional Objectivity findings appear immediately;
   confirmation of a long context form is not a prerequisite.
2. Inspect each finding's reported source and mechanism. Open **Review or correct
   reported information** to correct the meaning, evidence status or parties, or
   add a missing party or explicitly typed fact. Confirm that the source records
   reflect your account, including uncertainties.
3. Answer the single active material question using **Record answer and reassess**.
   **Why this matters** explains how it could affect the assessment. Questions
   reuse recorded facts and target unresolved decision links rather than following
   one fixed category questionnaire. An explicit **Unknown** is retained as a
   limitation and is not repeatedly asked.
4. Select **Evaluate threats** to review the evidence-linked significance and
   hypothetical reasonable and informed third party assessment. You can proceed
   with recorded gaps; the result remains qualified rather than inventing answers
   or forcing irrelevant questions.
5. Select **Review existing actions**. Review actions recognised in the account,
   record additional actions and identify the specific sources they address.
   Distinguish **Unknown**, **Not Taken**, **Planned** and **Implemented**.
6. Answer only the action-evidence questions currently material to effectiveness.
   Correct earlier evidence through the action editor when new information emerges.
   Review the resulting residual findings and prioritised next steps before
   proceeding, arranging a different response or considering declining/ending the
   activity subject to relevant obligations.
7. Select **Generate Objectivity report** and download Markdown if required.
   Revisit source facts or actions to recalculate the report. A downloaded report
   is a revision-specific snapshot and must be regenerated after material changes.
8. Use **Download progress** for a portable JSON backup. On reopening the same app
   in the same browser profile, choose **Resume previous assessment**. Use
   **Import progress** to restore a backup elsewhere.

Only submitted form values are saved. Unsubmitted text and unsaved edits are not
part of autosave or exported progress.

## Evidence and Objectivity reasoning

The local understanding layer proposes actors, professional activities,
relationships, actual beneficiaries, reported influence and existing actions.
Supported narrative proposals retain literal source excerpts. The understanding
provider does not issue ethical verdicts. Authored reasoning rules consume the
source ledger and generate distinct threat instances tied to the relevant actor,
decision and source information.

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
unknowns remain distinguishable. User review means the records reflect the user's
account; it is **not independent verification**. Possible future recovery or an
assurance by management remains an attributed claim. Extra explanatory text is
retained as reported context and is not automatically interpreted into new facts.

Evaluation distinguishes **Acceptability not established**, **Action needed before
proceeding** and **No direct influence established on the recorded account** where
appropriate. These are conditional implementation outcomes, not numerical ethics
scores or declarations of misconduct. Missing information or no identified threat
is not assurance that threats are absent. A reported change to work differs from
possible future influence and does not itself prove technical error.

The reasonable and informed third party test asks how a hypothetical reasonable
and informed person would assess the recorded circumstances and protective
measures. It is applied conditionally to the particular decision and sources;
no actual independent third party has reviewed the application's findings.

## Existing actions, effectiveness and residual threats

Address begins with what has already happened or been proposed. An omitted action
is not treated as proof that no action was taken. Users can link several actions
to particular threat instances rather than one category-wide response silently
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
checklist; the editor permits revisiting that answer later.

Where appropriate implementation, coverage and outcome evidence support it, an
action can be assessed as effective **conditionally on the recorded evidence**.
The app does not require an invented universal external-checker rule and does not
authenticate the user's description of records or an external review. A measure
addressing one source does not automatically resolve other threats. Material
source changes invalidate dependent answers or coverage and retain their earlier
records for reconsideration; stale positive conclusions are not trusted.

The Markdown report has nine sections:

- Scenario summary and reported context.
- Identified potential Objectivity threats and supporting sources.
- Threat evaluation and combined influences.
- Reasonable and informed third party assessment.
- Actions taken and proposed.
- Safeguard effectiveness and remaining evidence gaps.
- Residual threats.
- Prioritised next steps.
- Overall conditional ethical conclusion and limitations.

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
and supporting-action slots are retained when present. It excludes widget state, evaluations and reports. Restoration
validates the records and recomputes dependency signatures, questions, findings
and reports. Stale conditional answers are retained in history with a notice;
an incompatible stage moves back to the necessary clarification. New widget
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
  proposal validation. The provider interface permits a future implementation;
  no model, external API or GenAI integration is present.
- `objectivity/case_reasoning.py`: source-linked threat instances, material-gap
  selection, significance, combined influences and third party reasoning.
- `objectivity/case_workflow.py`: source correction, answer invalidation, action
  updates and explicit conversion of legacy progress.
- `objectivity/case_actions.py`: conditional evidence questions, action
  effectiveness, residual threats and case-specific recommendations.
- `objectivity/case_report.py`: current-snapshot nine-section Markdown report.
- `objectivity/case_ui.py`: scenario-driven Identify, Evaluate, Address and report
  interaction over the shared source model.
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
  migration regressions.
- Other `tests/test_*.py`: retained Phase 1–3, extraction, progressive context,
  save/resume, JavaScript bridge and UI regressions.

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

Representative cases include the CFO friendship/revenue/contract-renewal case;
inventory recognition with separate personal bonus and company interests;
procurement with distinct family and director interests; family employment with
unknown participation; explicit self-review and advocacy; incomplete information;
revised facts; planned, partial or failed actions; and appropriately evidenced
conditional protection. Materially different answers must produce different
qualified findings rather than one generic report.

## Functional and professional limitations

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
  for final judgment remains unchanged. The provider-neutral boundary prepares
  for future work; it does not add generative AI in this phase.
- Browser storage is local to one app origin/profile and may be unavailable or
  lost. Keep JSON backups, use anonymised cases and review the privacy limits
  above. There is no account, database or permanent server-side assessment store.

The existing Streamlit deployment can retain `app.py` and the unchanged
`requirements.txt` (`streamlit>=1.40,<2.0`). New assessment modules use only the
standard library and existing Streamlit functionality. Local checks validate the
installed runtime; they do not mean changes have been committed, pushed or
deployed, or establish the state of any live production or preview app.
