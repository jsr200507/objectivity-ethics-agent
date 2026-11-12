# Objectivity Ethics Assistant

A Python and Streamlit assistant focused exclusively on the fundamental principle
of **Objectivity**. It supports, rather than replaces, professional judgment.

Phase 1 provides scenario entry, explicit context confirmation, and adaptive
clarification. It does **not** evaluate threats, conclude whether safeguards are
sufficient, or generate an assessment report. It uses free, open-source packages,
with no paid APIs, subscriptions, services or API keys.

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
the ACCA/IESBA framework has been fully applied. Broader ethical evaluation and
professionally reviewed source content belong to later phases.

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
or application-written scenario file in Phase 1. Use anonymised details and avoid
entering confidential information. **Start a new scenario** requires confirmation
before discarding the current session.

## Code structure

- `app.py`: deployment entry point.
- `objectivity/models.py`: context, answers and revision history, independent of Streamlit.
- `objectivity/questions.py`: conditional question bank, selection and invalidation rules.
- `objectivity/examples.py`: editable, authored CFO example.
- `objectivity/ui.py`: Streamlit forms, progress and review views.
- `tests/test_engine.py`: pure domain and branching tests.
- `tests/test_app.py`: Streamlit AppTest interaction tests.

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
