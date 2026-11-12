"""Read-only presentation of provisional findings, never an assessment report."""

import streamlit as st

from .evaluation import Evaluation


def render_findings(evaluation: Evaluation) -> None:
    st.subheader("Identification and significance")
    st.caption(f"Recalculated from the current account · Revision {evaluation.revision}")
    if not evaluation.findings:
        st.info(
            "No potential threat is established from the current structured information. "
            "This is not a finding that threats are absent or that proceeding is acceptable."
        )
    shown_reasons: set[str] = set()
    for finding in evaluation.findings:
        st.markdown(f"### {finding.kind}")
        st.write(f"**{finding.outcome}**")
        st.write(finding.summary)
        for reason in finding.reasoning:
            # Shared assumption challenges apply across findings; explain once.
            if reason not in shown_reasons:
                st.markdown(f"- {reason}")
                shown_reasons.add(reason)
        with st.expander(f"Evidence and rule — {finding.kind}"):
            st.caption(f"Implementation rule {finding.rule_id} · Not a standards paragraph reference")
            for evidence in finding.evidence:
                st.write(f"**{evidence.label}**")
                st.text(evidence.value)
                st.caption(f"{evidence.source} · {evidence.status}")
        if finding.unknowns:
            st.write("**Information still needed**")
            for item in finding.unknowns:
                st.write(f"• {item}")
    if evaluation.interactions:
        st.subheader("How the circumstances may interact")
        for item in evaluation.interactions:
            st.write(item)
    already_shown = {item for finding in evaluation.findings for item in finding.unknowns}
    remaining = [item for item in evaluation.unknowns if item not in already_shown]
    if remaining:
        st.subheader("Unresolved information")
        for item in remaining:
            st.write(f"• {item}")
    st.subheader("Reasonable and informed third party test")
    st.write(evaluation.third_party)
    with st.expander("Evidence status and professional boundaries"):
        st.write(
            "The scenario is a reported narrative, not automatically interpreted evidence. "
            "Confirmed context is a user-confirmed account. Selected answers are recorded "
            "user answers. None has been independently verified by this application. "
            "Free-text explanations do not establish additional structured facts."
        )
        st.write(
            "The conceptual framework is Identify, Evaluate, Address. This release "
            "identifies potential threats and provisionally evaluates significance. "
            "Addressing threats and assessing safeguards belong to a later phase; "
            "an action-required outcome is not a finding of proven bias or misconduct."
        )
        st.write(
            "For audit-related work, separate audit-independence and non-assurance-service "
            "requirements may apply and are outside this Objectivity assessment."
        )
        for item in evaluation.limitations:
            st.write(f"• {item}")
        st.caption(
            "These are authored implementation rules, not quoted ACCA/IESBA provisions "
            "or a professionally validated opinion. The assistant supports, rather than "
            "replaces, professional judgment."
        )
