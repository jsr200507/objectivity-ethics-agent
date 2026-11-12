# Objectivity Ethics Assistant

A Python and Streamlit assistant focused exclusively on the fundamental principle
of **Objectivity**. It supports, rather than replaces, professional judgment.

Phase 1 provides scenario entry, explicit context confirmation, and adaptive
clarification. Phase 2 adds evidence-linked identification and provisional
evaluation of familiarity, intimidation and self-interest threats. It does **not**
conclude whether safeguards are sufficient or generate a final assessment report.
It uses free, open-source packages, with no paid APIs, subscriptions, services or
API keys. There is no generative AI or independent fact verification.

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
2. Review the editable role, parties, professional decision, relationship,
   interests and pressure fields. Confirm that they reflect your account.
3. Answer the single active follow-up and select **Save and continue**. Use
   **Why this question?** to inspect its trigger and purpose.
4. Use **Review previous answers** to edit an answer, or **Edit scenario or
   context** when the situation changes. Relevant follow-ups are recalculated.
5. Select **Review potential threats** when clarification is complete. Review
   supporting evidence, significance reasoning, missing information and the
   provisional reasonable and informed third party assessment. Additional
   evaluation questions appear one at a time only when relevant.

The example's context is authored sample data, not extracted from its narrative.
For other scenarios, fields start empty or Unknown. Only structured selections
control routing: free-text scenarios, notes and explanations are retained but not
automatically interpreted. Confirmation means a user-confirmed account, never
independent verification. Unknown, Not applicable and Other are valid options;
Unknown and Other do not become negative findings.

Progress shows answered questions among those currently applicable. The total
can grow or shrink as answers change. "Current clarification complete" means
only that there are no more questions selected by this version's rules. It does
not mean that threats are acceptable, that the information is complete, or that
the ACCA/IESBA framework has been fully applied. Continue to Phase 2 for a
conditional evaluation; addressing threats remains outside this release.

## Phase 2: identification and evaluation

The authored rules follow the conceptual-framework sequence **Identify,
Evaluate, Address**, implementing the first two stages only. Each finding shows
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
user answers**, and the narrative is a **reported account** that is not parsed.
No independently verified evidence has been obtained by the app.

If responsibility was already asked in Phase 1, it is reused, including an
Unknown answer. Otherwise it is clarified only where a potential threat is
supported. A further question records any basis for believing threats are
addressed. Confidence, disclosure, documentation and proposed safeguards trigger
a targeted challenge; none automatically lowers the outcome. Claiming changed
circumstances does not establish new facts: edit the relevant structured answers
to support reassessment. This is examination of assumptions, not Phase 3
safeguard selection or sufficiency evaluation.

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
- There are no Phase 3 safeguards, final reports, durable storage, external
  verification or language-model features.
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

## State and privacy

`st.session_state` holds the confirmed context, current answers, revision number
and superseded answer history. Saved answers survive ordinary Streamlit reruns.
Submit forms to save changes; unsaved form drafts are not assessment answers.
Progress is **not durable** across browser refreshes, disconnections, server
restarts or deployment updates. There is no database, user account, import/export
or application-written scenario file. Use anonymised details and avoid
entering confidential information. **Start a new scenario** requires confirmation
before discarding the current session.

## Code structure

- `app.py`: deployment entry point.
- `objectivity/models.py`: context, answers and revision history, independent of Streamlit.
- `objectivity/questions.py`: conditional question bank, selection and invalidation rules.
- `objectivity/examples.py`: editable, authored CFO example.
- `objectivity/ui.py`: Streamlit forms, progress and review views.
- `objectivity/evaluation.py`: pure, deterministic threat/significance reasoning and evidence links.
- `objectivity/review.py`: conditional evaluation questions and review-answer invalidation/history.
- `objectivity/evaluation_ui.py`: read-only provisional finding presentation.
- `tests/test_engine.py`: pure domain and branching tests.
- `tests/test_app.py`: Streamlit AppTest interaction tests.
- `tests/test_evaluation.py`, `tests/test_review.py`, `tests/test_phase2_app.py`: Phase 2 reasoning, follow-up and interaction regressions.

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

The existing Streamlit deployment can retain `app.py` and the unchanged
`requirements.txt`. Phase 2 adds only standard-library modules and uses the same
Streamlit dependency. Local startup and tests validate compatibility with the
installed runtime; they do not mean changes have been committed, pushed or
deployed, or establish the status of a live hosted instance.
