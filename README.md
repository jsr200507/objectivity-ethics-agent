# Objectivity Ethics Assistant

A Python and Streamlit assistant focused exclusively on the fundamental principle
of **Objectivity**. It supports, rather than replaces, professional judgment.

Phase 1 provides scenario entry, explicit context confirmation, and adaptive
clarification. Phase 2 adds evidence-linked identification and provisional
evaluation of familiarity, intimidation and self-interest threats. Phase 3 adds
adaptive action planning, conditional assessment of safeguard effectiveness,
residual-threat reasoning and a downloadable Ethical Assessment Report.
It uses free, open-source packages, with no paid APIs, subscriptions, services or
API keys. There is no generative AI or independent fact verification.

Save & Resume adds acknowledged browser-local autosave for submitted progress,
plus validated JSON backups that work without browser storage. The assessment
rules and the three-phase workflow are unchanged.

## Run locally

Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On Windows, activate the virtual environment with `.venv\Scripts\activate`.
Open the local URL printed by Streamlit. Stop the app with Ctrl+C.

For a headless environment:

```bash
python -m streamlit run app.py --server.headless true
```

## Use the assistant

1. Enter a scenario, or choose **Load CFO / revenue recognition example**.
2. Review the suggested context. Answer one focused question at a time for
   missing or ambiguous details, correct suggestions with the **Edit** controls,
   then select **Confirm reviewed context**. The complete editor is optional.
3. Answer the single active follow-up and select **Save and continue**. Use
   **Why this question?** to inspect its trigger and purpose.
4. Use **Review previous answers** to edit an answer, or **Edit scenario or
   context** when the situation changes. Relevant follow-ups are recalculated.
5. Select **Review potential threats** when clarification is complete. Review
   supporting evidence, significance reasoning, missing information and the
   provisional reasonable and informed third party assessment. Additional
   evaluation questions appear one at a time only when relevant.
6. When the evaluation questions are answered, select **Address Threats**.
   Record actions against each supported potential threat. Distinguish a proposal
   from reported implementation, the evidence supporting it, and any reported
   external check. Additional questions depend on the action selected.
7. Use **Add a supporting action** if several measures are needed for a threat.
   Use **Review Address answers** to revise actions or implementation evidence.
8. Select **Generate Ethical Assessment Report**. Review the current conditional
   conclusions and download a Markdown copy. Incomplete information produces an
   interim assessment, not an invented assurance of acceptability.
9. Use **Download progress** for a portable JSON backup. On reopening the same
   app in the same browser profile, choose **Resume previous assessment**. Use
   **Import progress** to restore a JSON backup in another session or browser.

Step 2 first suggests context using free, local English rules: the
professional role, relevant people/groups/organisations and roles, professional
activities, relationships, financial/performance incentives and reported pressure.
Title and actor patterns combine with professional-action, ownership, incentive
and request/consequence rules; there are no complete-scenario lookup answers.
The optional **How were the suggestions obtained?** panel shows literal source
excerpts for every supported field. Missing, ambiguous or conflicting details
remain unresolved until clarified or explicitly recorded as not known. Every
suggestion remains editable and requires user confirmation before assessment.

The default interface shows a concise summary instead of a mandatory six-field
form. Only one context question is active. Questions prioritise the role and
decision, then weak or missing party lists, relationships, financial beneficiaries
and reported pressure. Known details are retained; a generic title or ambiguous
beneficiary can prompt a targeted clarification. Unfamiliar job titles and
activities can be supplied directly without matching a recognised phrase.

**I don't know yet** records a genuine uncertainty, instead of treating an
extraction failure as an established lack of information. Explicitly answered
uncertainties are not repeatedly asked. Equivalent structured answers are reused
in the subsequent clarification stage; new questions about contact, financial
links, responsibility or consequences still appear when needed.

Financial clarification distinguishes the user's/household's interest, a family
member's interest, the organisation's interest, and another person's interest.
Where necessary, a follow-up records the recipient and financial connection.
A sister's shareholding or a director's consulting fee is not automatically a
personal benefit for the user. Free-text explanations are kept as the user's
account, not interpreted as evidence. A family tie does not establish closeness,
and promotion does not automatically establish a monetary benefit.

Each summary detail can be edited independently. **Edit all context details
(optional)** retains direct control over all fields, scenario edits and fresh
suggestion previews. Confirming that complete editor explicitly acknowledges any
Unknown fields left there. Focused edits require confirmation again and refresh
dependent assessment answers. User-confirmed accounts remain unverified.

Suggestions are generated when you continue from scenario entry or load the CFO
example. They are stored as **unconfirmed draft context**, so browser autosave and
JSON export/import preserve them together with submitted clarification progress. Reruns, restored
progress and editing previously confirmed context do not overwrite corrections.
Use **Preview fresh suggestions** in Step 2 to extract from an edited scenario
or revisit an older saved assessment. The preview changes nothing until you
select fields and explicitly acknowledge replacement. Applying saves those
suggestions as an unconfirmed draft, retains your other submitted fields, and
archives existing answers for reconsideration. Dependent Phase 2/3 answers and
conclusions are invalidated by the existing dependency checks. Confirm again to
continue. An unchanged selection leaves the assessment intact.

Only the fields you confirm and the subsequent structured selections drive
threat identification and question selection. Extraction itself does not identify
a threat, prove a fact or establish misconduct. Confirmation means a user-confirmed
account, never independent verification. Unknown, Not applicable and Other remain
valid choices and do not become negative findings.

The CFO sample uses the same rules as pasted scenarios for all six fields.
An explicit professional association is recorded as **Other** with details when
personal ties are unspecified; a job title does not establish that a relationship
is exclusively professional. A counterpart's bonus is distinguished from the
user's financial interest. Career incentives without stated monetary benefit are
recorded as **Other**, not invented personal financial benefits. An instruction
to favour a professional outcome can suggest reported pressure, while a routine
request to assess an issue cannot. No request proves coercion, bias or misconduct.
Extra free-text answers in subsequent phases are not automatically interpreted.

Personal pay, commissions, shareholdings and explicit financial incentives are
classified separately from organisational profit targets, fees and other
commercial interests. Both can be suggested together using the existing **Both
commercial and personal interests** selection, which retains both clarification
paths and report logic. Multiword descriptions such as
"annual performance bonus" do not change who receives the incentive. A quoted
counterpart's benefit is not silently assigned to the user.

Reported instructions to defer accounting recognition, conceal information or
withhold it from auditors and other accountability recipients can suggest
pressure. Routine requests to assess an issue and protective instructions not to
conceal it are distinguished where the wording supports that distinction. These
remain reported instructions, not completed changes, explicit threats, verified
facts or misconduct findings. Possible future recovery mentioned by a manager
remains that person's claim.

The suggested activity retains supported requests about accounting timing,
amount and disclosure alongside the underlying professional work. Parties
include explicit plural roles and recipients of information, including people
from whom information would be withheld. Clear generic/descriptive references
are deduplicated; distinct or ambiguous organisations are not automatically
treated as the same entity. Auditor type and personal relationships are not
invented.

This is deliberately limited rule-based assistance, not unrestricted language
understanding or generative AI. Unfamiliar roles/phrasing, attribution, pronouns,
negation and multi-party context can still be missed or misclassified. Multiple
explicit activities are retained; unresolved alternatives remain Unknown. Source
excerpts show wording, not verification. Always check the suggestions and their
scope. No new dependencies, external model, paid API or API key are required.

Progress shows answered questions among those currently applicable. The total
can grow or shrink as answers change. "Current clarification complete" means
only that there are no more questions selected by this version's rules. It does
not mean that threats are acceptable, that the information is complete, or that
the ACCA/IESBA framework has been fully applied. Continue to Phase 2 for a
conditional evaluation, then to the separate Address stage and report.

## Phase 2: identification and evaluation

The authored rules follow the conceptual-framework sequence **Identify,
Evaluate, Address**. Phase 2 implements the first two stages; Phase 3 considers
the recorded actions separately. Each initial finding shows
its supporting structured choices, source field/question IDs, reasoning,
unresolved information, and an implementation rule ID. These IDs are not
ACCA/IESBA paragraph references. No professional validation or complete Code
compliance is claimed.

| Threat | Identification basis | Factors affecting significance |
| --- | --- | --- |
| Familiarity | A confirmed close or continuing personal relationship linked, or potentially linked, to the user's judgment | Current contact and continuing ties; making, recommending, supervising or reviewing the decision; unresolved responsibility |
| Intimidation | An explicit, implied, or separately supported reported link between pressure and a professional decision | Nature of consequences, responsibility, and reported changes to work; unsupported interpretation is not enough to establish the link |
| Self-interest | A recorded connection between a commercial/personal financial interest and the decision | Commercial dependence, direct personal outcome, responsibility and unresolved links |

The rules distinguish **Potential threat requiring evaluation**, **Insufficient
information**, and **Threat requiring action before proceeding**. They never use
numerical ethics scores or declare misconduct. Examples of conservative
action-required triggers include a close active relationship intersecting with
decision responsibility, pressure with a known consequence and decision
responsibility, a reported pressure-related work change, or a significant
commercial/direct personal incentive intersecting with decision responsibility.
These are conditional implementation decisions, not universal professional
thresholds or conclusions about the effectiveness of any response.

Unknown/Other answers remain gaps. Missing links do not generate invented
threats. No identified threat is not an assurance that threats are absent. No
reported change to work does not remove possible future influence; a reported
change does not establish that the work was technically wrong. When several
threats are supported, the review explains possible interaction without treating
the same underlying event as independent corroboration.

The reasonable and informed third party test is explained and applied
conditionally to the account. No actual independent third party reviews the
case. Context is a **user-confirmed account**, selected answers are **recorded
user answers**, and the narrative is a **reported account**. Limited extraction
only proposes context before confirmation; ethical reasoning does not otherwise
interpret the narrative.
No independently verified evidence has been obtained by the app.

If responsibility was already asked in Phase 1, it is reused, including an
Unknown answer. Otherwise it is clarified only where a potential threat is
supported. A further question records any basis for believing threats are
addressed. Confidence, disclosure, documentation and proposed safeguards trigger
a targeted challenge; none automatically lowers the outcome. Claiming changed
circumstances does not establish new facts: edit the relevant structured answers
to support reassessment. The initial evaluation examines assumptions; the Address
stage then considers specific actions and the evidence of their effectiveness.

Findings are computed afresh on every rerun. Changes to the underlying context
or structured answers archive the dependent evaluation answers; changing an
explanation alone does not drive reasoning. Current and superseded evaluation
answers can be reviewed separately from Phase 1 history.

### Remaining boundaries

- The authored rules cover these three threat types within the available
  structured choices; they do not exhaust every circumstance that can affect
  Objectivity, assess every fundamental principle, or independently validate facts.
- A conditional audit-independence/non-assurance-service boundary is shown for
  audit-related work. The app does not infer audit scope from unrestricted text.
- There is no durable storage, external fact verification, document authentication
  or language-model feature. Reports remain conditional professional-judgment
  support and are not certified ethical opinions.
- Current authoritative standards, applicable jurisdiction and circumstances,
  and professional judgment must inform real decisions. Rule content needs
  professional review and maintenance; no fabricated source citations are used.

## Try the three paths

For each test, enter a scenario and role, parties and decision. Select the context
below and confirm it. The optional CFO example activates all three paths together.

| Path | Context selections | Answers to try | Expected difference |
| --- | --- | --- | --- |
| Familiarity | Close personal relationship; No known interest; No reported pressure | Frequent personal contact → decision involvement | Choose Little or no current personal contact instead to see a continuing-ties question. Answer No to end that branch. |
| Self-interest | No relevant relationship; Commercial interest; No reported pressure | Contract renewal or client retention → commercial dependence | Edit interests to Personal financial interest to see personal benefit and financial-outcome questions instead. |
| Intimidation | No relevant relationship; No known interest; Reported pressure or threatened consequences | Explicitly stated → consequence → work changed? | Select My interpretation only instead to see a supporting-information question. No further supporting information ends that branch without asserting the pressure is absent. |

Edit a saved answer through the review panel to test a different branch. When a
structured choice changes, dependent answers are archived and must be answered
again if their questions return. Editing explanation text alone preserves later
answers because text is not interpreted. Context changes reset the affected
topic; changing the scenario, role, parties or decision resets all follow-ups.
Superseded answers remain visible in read-only session history.

## Phase 3: Address and report

The Address stage presents the actual potential threats identified from the
current account, with the structured facts supporting them. It does not treat
every concern as proven bias. Action choices cover eliminating the circumstances,
removal from the decision, independent review, escalation, disclosure,
documentation, and declining or ending the activity where necessary. Choices
and follow-ups are conditional on the threat and the user's preceding answers.
Users can add supporting actions rather than being limited to a single measure.

Implementation, timing, scope, authority, independence, effectiveness and
supporting evidence are distinct matters. Merely reporting a concern, documenting
it, requesting a review or describing a proposed safeguard cannot establish that
the threat has been addressed. Reported external checking remains a **user
account of an external check**, not independent verification by this application.
Actions that have not worked leave a residual threat. Unknown details and
unresolved earlier facts remain explicit.

Residual conclusions apply the reasonable and informed third party test
conditionally. The app may identify evidence supporting reduction where the
recorded implementation and effectiveness checks support it; it never declares
automatic compliance. Where the evidence is insufficient, acceptability is not
established. Prior work affected by pressure needs attention even if the user is
subsequently removed from the decision or the activity is ended. A measure
addressing one incentive or threat does not automatically address other
commercial/personal incentives or interacting threats.

The report contains the scenario and confirmed context; reported facts and
uncertainties; potential threats and supporting evidence; initial significance
and combined-threat reasoning; the reasonable and informed third party test;
proposed versus implemented actions; remaining threats and missing evidence;
a conditional conclusion; prioritised next steps; and scope and professional
judgment limitations. Engine references are presented in natural language rather
than internal field names. Free-text contributions are quoted as user accounts,
not treated as interpreted or authenticated evidence.

Reports are rebuilt from current answers on every report-view rerun, including
downloads. Changing upstream context or structured Phase 1/2 answers invalidates
dependent Address answers and preserves their history. Editing action choices
reopens affected follow-ups. No stale conclusion is silently reused. A downloaded
file is a revision-specific snapshot and must be regenerated after changes.

### Try the CFO scenario through all phases

Load the example, review and confirm the context, and answer the Phase 1 questions:
implied pressure; loss of a contract; no changed work; frequent personal contact;
supervision/review responsibility; contract renewal; unknown commercial
dependence. Review the three potential threats and record whether any claim is
being made that they are already addressed. Then open **Address Threats**.

Compare a requested or proposed review with an implemented review. Try an
ineffective measure, inadequate reviewer independence or missing evidence, and
check that acceptability remains unestablished. Record distinct actions against
all relevant threats; familiarity measures must not silently eliminate the
contract-related pressure or commercial incentive. Generate an interim report,
edit an earlier answer, and regenerate it to inspect the changed reasoning.

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

Each browser save stores the scenario, confirmed or draft context, submitted
Step 2 clarification records, active answers
and superseded history from all three phases, supporting-action slots and current
workflow stage. It excludes widget state, evaluations and reports. Restoration
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
New exports use schema 2 to include context clarification source records.
Schema 1 backups and browser saves remain importable; they do not acquire
invented clarification answers or confirmation. The browser storage slot is
unchanged. Older deployed versions cannot read schema 2 until updated. The
records contain source answers and dependency bindings, not trusted conclusions.
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

The integrated application has been exercised in Chromium through all three
phases, refresh and explicit resume, closing/reopening a persistent browser
profile, confirmed clearing, actual JSON download/upload, and stale-tab conflict
protection. These local tests do not establish that a live hosted deployment has
been updated or independently tested. Further browser checks restarted the backend
at the same origin, restored edited safeguard answers and superseded history,
preserved corrupt copies until confirmed clearing, and verified usable JSON
downloads when storage was blocked or full.

## Code structure

- `app.py`: deployment entry point.
- `objectivity/models.py`: context, answers and revision history, independent of Streamlit.
- `objectivity/questions.py`: conditional question bank, selection and invalidation rules.
- `objectivity/examples.py`: editable, authored CFO example.
- `objectivity/extraction.py`: six-field suggestion orchestration and bounded-input validation.
- `objectivity/extraction_entities.py`: local role, person/group/organisation and professional-activity patterns.
- `objectivity/extraction_signals.py`: scoped relationship, financial/performance incentive and reported-pressure rules.
- `objectivity/context_suggestions.py`: explicit selective replacement as an unconfirmed draft, retaining history.
- `objectivity/intake.py`, `objectivity/intake_ui.py`: source-only adaptive context planning, editable summaries and progressive confirmation.
- `objectivity/ui.py`: Streamlit forms, progress and review views.
- `objectivity/evaluation.py`: pure, deterministic threat/significance reasoning and evidence links.
- `objectivity/review.py`: conditional evaluation questions and review-answer invalidation/history.
- `objectivity/evaluation_ui.py`: read-only provisional finding presentation.
- `objectivity/address.py`: adaptive actions, implementation evidence, residual assessment and invalidation/history.
- `objectivity/address_ui.py`: Address interaction and live report/download views.
- `objectivity/report.py`: pure Markdown report generation and natural-language provenance labels.
- `objectivity/progress.py`: bounded, versioned JSON codec and validated reconstruction of source records.
- `objectivity/save_state.py`: acknowledgement and saved-version coordination.
- `objectivity/progress_ui.py`: autosave, resume, confirmation and portable-backup controls.
- `objectivity/browser_storage.py`, `objectivity/browser_component/index.html`: local vanilla-JavaScript storage bridge, without external assets.
- `tests/test_engine.py`: pure domain and branching tests.
- `tests/test_app.py`: Streamlit AppTest interaction tests.
- `tests/test_evaluation.py`, `tests/test_review.py`, `tests/test_phase2_app.py`: Phase 2 reasoning, follow-up and interaction regressions.
- `tests/test_address.py`, `tests/test_report.py`, `tests/test_phase3_app.py`: action effectiveness, report and all-phase interaction regressions.
- `tests/test_progress.py`, `tests/test_save_state.py`, `tests/test_progress_ui.py`, `tests/test_browser_storage.py`: schema, restoration, acknowledgements, UI and storage-bridge regressions.
- `tests/test_extraction*.py`: supported/ambiguous extraction, paraphrases, literal sources, attribution and negation regressions.
- `tests/test_context_suggestions.py`, `tests/test_context_prefill_app.py`, `tests/test_general_prefill_app.py`: editable drafts, selective refresh, confirmation, all-phase invalidation, autosave/resume and JSON portability.
- `tests/test_full_context_extraction_app.py`: full inventory, CFO, procurement and incomplete-scenario regressions, including both interest paths, disclosure instructions, persistence and all-phase reports.
- `tests/test_intake.py`, `tests/test_intake_progress.py`, `tests/test_progressive_context_app.py`: unfamiliar work, adaptive clarification, beneficiary attribution, genuine uncertainty, edits, schema migration and restoration.

Questions are selected by explicit conditions on context and prior answers, not a
fixed questionnaire or keyword matching. Combined circumstances retain all
applicable paths. Each question carries its own rationale and selectable options.

## Run checks

With the virtual environment activated:

```bash
python -m unittest discover -s tests -v
python -m pip check
git diff --check
```

The test runner uses Python's standard-library `unittest` and Streamlit's bundled
AppTest. No additional test dependencies are required. Tests cover distinct and
combined paths, Unknown/Other handling, validation, rerun persistence, answer and
context edits, archive invalidation, cancellation and reset. Streamlit may print
a harmless missing-ScriptRunContext warning when AppTest starts outside a server.
The browser-bridge tests also run the actual JavaScript in Node when available;
those specific JavaScript checks skip if Node is absent. Node is not an
application/runtime dependency. Browser refresh/reopen and real uploads require
the additional manual or headless-browser checks described above; AppTest alone
does not establish browser persistence.

The existing Streamlit deployment can retain `app.py` and the unchanged
`requirements.txt`. Save & Resume adds only standard-library Python modules and
a locally served component using Streamlit's existing v1 component API. No npm
build or new Python dependency is required. Local startup and tests validate compatibility with the
installed runtime; they do not mean changes have been committed, pushed or
deployed, or establish the status of a live hosted instance.
