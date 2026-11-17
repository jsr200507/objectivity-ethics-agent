"""Save/resume controls with acknowledged local storage and portable JSON.

The browser bridge is optional. If it is unavailable, validated JSON export and
import remain usable; no session-state-only persistence claim is made.
"""

from copy import deepcopy

import streamlit as st

from .address import AddressState
from .browser_storage import browser_storage
from .models import Assessment, Context
from .progress import MAX_PROGRESS_BYTES, ProgressError, ProgressSnapshot, export_progress, import_progress
from .review import ReviewState
from .save_state import BrowserSaveState


CONTROLLER = "_browser_save_state"
INTENT = "_progress_intent"


def install_progress(snapshot: ProgressSnapshot) -> None:
    """Restore source records, never widget values or imported conclusions."""
    st.session_state.assessment = deepcopy(snapshot.assessment)
    st.session_state.review_state = deepcopy(snapshot.review)
    st.session_state.address_state = deepcopy(snapshot.address)
    st.session_state.view = snapshot.view
    st.session_state.widget_generation = st.session_state.get("widget_generation", 0) + 1
    for key in ("edit_answer_id", "edit_review_id", "edit_address_id"):
        st.session_state[key] = None
    st.session_state.example_loaded = False
    st.session_state.reset_pending = False
    st.session_state.pop("_pending_resume", None)
    st.session_state.pop("_pending_import", None)
    st.session_state["_progress_notice"] = "Progress restored. Evaluations and reports are recalculated from the recorded answers."
    if snapshot.warnings:
        st.session_state["_progress_notice"] += " " + " ".join(snapshot.warnings)


def _new_progress() -> None:
    install_progress(ProgressSnapshot(Assessment(), ReviewState(), AddressState(), "scenario"))
    st.session_state["_progress_notice"] = "A new assessment has been started."


def _has_progress() -> bool:
    assessment = st.session_state.assessment
    return bool(
        assessment.scenario.strip() or assessment.confirmed or assessment.answers or assessment.archive
        or assessment.context != Context()
        or st.session_state.review_state.answers or st.session_state.review_state.archive
        or st.session_state.address_state.answers or st.session_state.address_state.archive
    )


def _current_json() -> str:
    return export_progress(
        st.session_state.assessment, st.session_state.review_state,
        st.session_state.address_state, st.session_state.view,
    )


def _controller() -> BrowserSaveState:
    if CONTROLLER not in st.session_state:
        st.session_state[CONTROLLER] = BrowserSaveState()
    return st.session_state[CONTROLLER]


def _queue(kind: str, snapshot: ProgressSnapshot | None = None) -> None:
    if INTENT in st.session_state:
        st.session_state["_progress_notice"] = "A confirmed save operation is already pending. Wait for its result before starting another."
        st.rerun()
    st.session_state[INTENT] = {"kind": kind, "snapshot": snapshot}
    st.rerun()


def _perform_intent(controller: BrowserSaveState) -> None:
    intent = st.session_state.get(INTENT)
    if not intent:
        return
    kind = intent["kind"]
    # JSON import/session reset still work without the bridge. Unknown browser
    # data is never deleted or overwritten blindly while a read is unavailable.
    if not controller.available:
        if kind == "clear":
            _new_progress()
            st.session_state["_progress_notice"] += " No browser deletion was attempted; any saved browser copy may remain."
        elif kind == "import":
            install_progress(intent["snapshot"])
            st.session_state["_progress_notice"] += " Restored into this session only; use Download progress until browser saving is available."
        elif kind == "replace":
            st.session_state["_progress_notice"] = "Browser saving is unavailable. Use Download progress."
        st.session_state.pop(INTENT, None)
        st.rerun()
    if controller.busy:
        return
    if kind == "clear":
        controller.request("clear", purpose="clear")
    elif kind == "import":
        snapshot = intent["snapshot"]
        controller.request("write", export_progress(snapshot.assessment, snapshot.review, snapshot.address, snapshot.view), purpose="import")
    else:
        controller.request("write", _current_json(), purpose="replace")


def _bridge_event(controller: BrowserSaveState, event: str) -> None:
    intent = st.session_state.get(INTENT)
    if (
        intent and event.endswith(":failed") and controller.mode == "conflict"
        and event.split(":", 1)[0] != intent["kind"]
    ):
        # A confirmed operation may have waited behind an autosave. Never apply
        # that old confirmation to a newly discovered assessment from another tab.
        st.session_state.pop(INTENT, None)
        st.session_state["_progress_notice"] = "The browser copy changed while saving. The pending replacement or deletion was cancelled; review the saved copy and confirm again."
        st.rerun()
    if event == "clear":
        _new_progress()
        st.session_state["_progress_notice"] = "The saved browser assessment was deleted. A new assessment has been started."
    elif event.startswith("import") and intent and intent["kind"] == "import":
        install_progress(intent["snapshot"])
        if event.endswith(":failed"):
            if controller.mode == "conflict":
                st.session_state["_progress_notice"] += " The newer browser copy was not overwritten. Download progress to retain this imported session."
            else:
                st.session_state["_progress_notice"] += " Browser saving was not confirmed. Download progress to retain this imported session."
    elif event == "clear:failed":
        st.session_state["_progress_notice"] = "Browser deletion was not confirmed. The current assessment has been retained."
    if event.split(":", 1)[0] in {"clear", "import", "replace"}:
        st.session_state.pop(INTENT, None)
    st.rerun()


def _saved_snapshot(controller: BrowserSaveState) -> ProgressSnapshot | None:
    if controller.saved_data is None:
        return None
    try:
        return import_progress(controller.saved_data)
    except ProgressError as error:
        controller.mode = "corrupt"
        controller.error = f"Saved progress could not be restored: {error}"
        return None


def _resume(controller: BrowserSaveState, snapshot: ProgressSnapshot) -> None:
    controller.resume(export_progress(snapshot.assessment, snapshot.review, snapshot.address, snapshot.view))
    install_progress(snapshot)
    st.rerun()


def _saved_choices(controller: BrowserSaveState, snapshot: ProgressSnapshot | None) -> bool:
    """True means a saved copy needs an explicit choice before workflow edits."""
    if controller.mode not in {"choice", "conflict", "corrupt"}:
        return False
    if controller.mode == "conflict":
        st.warning("Another tab or window changed the browser save. This session has not overwritten it. Download this session before choosing which version to keep.")
    elif controller.mode == "corrupt":
        st.warning(controller.error or "The browser copy is corrupt or incompatible. It has not been overwritten.")
    else:
        st.info("A previous assessment is saved in this browser. Resume it or start a new assessment.")
    if snapshot is not None:
        if st.button("Resume previous assessment"):
            if _has_progress():
                st.session_state["_pending_resume"] = snapshot
                st.rerun()
            _resume(controller, snapshot)
    pending = st.session_state.get("_pending_resume")
    if pending:
        st.warning("Replace the current session's progress with the browser-saved assessment?")
        if st.button("Confirm resume and replace current progress"):
            _resume(controller, pending)
        if st.button("Cancel resume"):
            st.session_state.pop("_pending_resume", None)
            st.rerun()
    if controller.mode == "conflict" and _has_progress():
        if st.button("Keep this session instead"):
            st.session_state["_confirm_browser_replace"] = True
        if st.session_state.get("_confirm_browser_replace"):
            st.warning("Replace the existing browser copy with this session? The other copy will be overwritten only if it has not changed again.")
            if st.button("Confirm replace browser copy"):
                st.session_state.pop("_confirm_browser_replace", None)
                _queue("replace")
            if st.button("Cancel browser replacement"):
                st.session_state.pop("_confirm_browser_replace", None)
                st.rerun()
    if st.button("Start new assessment"):
        st.session_state.reset_pending = True
    return controller.mode == "choice"


def _reset_controls() -> None:
    if st.button("Start a new scenario"):
        st.session_state.reset_pending = True
    if st.session_state.get("reset_pending"):
        st.warning("Discard the current assessment and delete any saved browser assessment? Download progress first if you need to keep it.")
        if st.button("Discard and start again"):
            _queue("clear")
        if st.button("Keep current scenario"):
            st.session_state.reset_pending = False
            st.rerun()


def _portable_controls(current_json: str | None) -> None:
    st.subheader("Save & Resume")
    if current_json is not None:
        st.download_button(
            "Download progress", current_json,
            file_name="objectivity-assessment-progress.json", mime="application/json",
        )
    with st.expander("Import progress"):
        uploaded = st.file_uploader(
            "Choose a progress JSON file", type=["json"],
            key=f"progress_import_{st.session_state.widget_generation}",
        )
        staged = None
        if uploaded is not None:
            try:
                if uploaded.size > MAX_PROGRESS_BYTES:
                    raise ProgressError("Progress file exceeds the 2 MiB size limit.")
                staged = import_progress(uploaded.getvalue())
            except ProgressError as error:
                st.error(f"Nothing was imported: {error}")
            else:
                st.caption("The file was validated. Stored conclusions are not restored; source answers will be reassessed.")
                if st.button("Import progress"):
                    st.session_state["_pending_import"] = staged
        pending = st.session_state.get("_pending_import")
        if pending:
            st.warning("Importing replaces this session and, when available, the browser-saved assessment. Download existing progress first.")
            if st.button("Confirm import and replace progress"):
                _queue("import", pending)
            if st.button("Cancel import"):
                st.session_state.pop("_pending_import", None)
                st.rerun()


def render_save_resume() -> bool:
    """Render sidebar controls; return True if a previous copy awaits selection."""
    controller = _controller()
    _perform_intent(controller)
    current_json = None
    try:
        current_json = _current_json()
    except ProgressError as error:
        st.warning(f"This progress cannot currently be saved: {error}")
    if (
        not controller.busy and controller.mode == "active" and _has_progress()
        and current_json is not None and current_json != controller.last_saved_data
    ):
        controller.request("write", current_json, purpose="autosave")
    response = browser_storage(controller.command)
    event = controller.consume(response)
    if event:
        _bridge_event(controller, event)
    snapshot = _saved_snapshot(controller) if controller.mode in {"choice", "conflict"} else None
    if controller.mode == "checking":
        st.caption("Checking browser storage. Saving is not yet confirmed; Download progress is available as a fallback.")
    elif controller.mode == "unavailable":
        st.warning("Browser autosave is unavailable. Use Download progress and Import progress to save and resume.")
        if controller.error:
            st.caption(controller.error)
    elif controller.mode == "active":
        if controller.busy:
            st.caption("Saving submitted progress in this browser…")
        elif controller.last_saved_data is not None and controller.last_saved_data == current_json:
            st.caption("Submitted progress saved in this browser.")
        else:
            st.caption("Browser autosave is available for submitted progress.")
    _portable_controls(current_json)
    blocked = _saved_choices(controller, snapshot)
    if controller.saved_data is not None and controller.mode in {"corrupt", "conflict", "choice"}:
        st.download_button(
            "Download saved browser copy", controller.saved_data.encode("utf-8", errors="replace"),
            file_name="objectivity-browser-copy.json", mime="application/json",
        )
    _reset_controls()
    st.caption(
        "Browser storage and exported JSON may contain sensitive scenario details. Use fictional "
        "or anonymised cases. Browser data may be lost if storage is cleared or in private browsing. "
        "Only submitted forms are saved; unsaved text is not included. No permanent server storage."
    )
    if st.session_state.get("_progress_notice"):
        st.info(st.session_state["_progress_notice"])
    return blocked or INTENT in st.session_state
