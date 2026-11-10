# Objectivity Ethics Assistant

A minimal Python and Streamlit application for ACCA Advanced Audit coursework,
focused exclusively on the fundamental principle of **Objectivity**.

Enter an ethical scenario and click **Start Assessment** to see your scenario
and a confirmation message. Empty submissions receive a prompt to enter a
scenario. This prototype does not assess scenarios or implement AI functionality.
It uses free, open-source Python packages and requires no paid APIs, services,
or API keys.

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

Scenario text is only displayed in the current Streamlit session; this app does
not write it to a database or file. Avoid entering real client or confidential
information into coursework examples.
