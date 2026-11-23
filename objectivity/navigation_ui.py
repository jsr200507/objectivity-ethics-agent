"""Bring the current guided stage into view after explicit navigation only."""
import streamlit as st


def focus_stage():
    """Reset retained Streamlit scroll without moving ordinary reading/editing.

    This local component contains no case data and makes no network requests.
    It runs once per navigation generation, after the stage has been rendered.
    """
    generation = st.session_state.widget_generation
    stamp = (st.session_state.view, generation)
    if st.session_state.get('_focused_stage') == stamp:
        return
    st.session_state['_focused_stage'] = stamp
    title = {'identify': 'Step 1:', 'case_evaluate': 'Step 2:',
             'case_address': 'Step 3:', 'case_report': 'Final Ethical Assessment Report'}[stamp[0]]
    markup = """<script>
    (() => {
      try {
        const doc = window.parent.document;
        const focus = () => {
          const heading = [...doc.querySelectorAll('h2')].find(node =>
            node.textContent.trim().startsWith('STAGE_TITLE'));
          if (heading) heading.scrollIntoView({block:'start', behavior:'instant'});
          else {
            const main = doc.querySelector('[data-testid="stMain"]');
            if (main) main.scrollTop = 0;
          }
        };
        // Focus after Streamlit has laid out the newly rendered stage.
        requestAnimationFrame(() => requestAnimationFrame(focus));
      } catch (_) { /* Ordinary navigation remains usable if framing blocks DOM access. */ }
    })();
    </script>""".replace('STAGE_TITLE', title) + f'<!-- navigation {int(generation)} -->'
    if hasattr(st, 'iframe'):
        st.iframe(markup, height=1, tab_index=-1)
    else:
        from streamlit.components.v1 import html
        html(markup, height=0, scrolling=False)
