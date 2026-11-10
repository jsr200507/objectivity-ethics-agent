"""A minimal Objectivity ethics coursework assistant."""

import streamlit as st


st.set_page_config(page_title="Objectivity Ethics Assistant", page_icon="⚖️")

st.title("Objectivity Ethics Assistant")
st.write(
    "An assistant for ACCA Advanced Audit coursework, focusing exclusively on "
    "the fundamental principle of Objectivity: exercising professional judgment "
    "without bias, conflicts of interest, or undue influence."
)
st.caption("This prototype records your scenario; it does not provide AI analysis.")

with st.form("assessment"):
    scenario = st.text_area(
        "Describe an ethical scenario",
        placeholder="Describe the situation and any potential threats to objectivity…",
        height=200,
    )
    submitted = st.form_submit_button("Start Assessment")

if submitted:
    if scenario.strip():
        st.success("Scenario received. Your assessment has been started.")
        st.subheader("Your scenario")
        st.text(scenario)
    else:
        st.warning("Please enter an ethical scenario before starting the assessment.")
