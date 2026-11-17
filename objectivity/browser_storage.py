"""Local, dependency-free Streamlit bridge to browser storage.

The browser acknowledges successful writes only after a verified localStorage
round trip. Returning ``None`` means the frontend has not acknowledged anything;
it must never be interpreted as evidence that progress was saved.
"""

from pathlib import Path

import streamlit.components.v1 as components


STORAGE_KEY = "objectivity-ethics-assistant.progress.v1"
MAX_STORAGE_BYTES = 2 * 1024 * 1024

_component = components.declare_component(
    "objectivity_browser_storage",
    path=str(Path(__file__).with_name("browser_component")),
)


def browser_storage(command: dict, key: str = "objectivity_browser_storage") -> dict | None:
    """Submit one command and return the last frontend response, if available.

    The controller must match response ``id`` to the current command. It must
    retain the acknowledged token for compare-and-swap writes, including the
    new token returned by clear (which stores a content-free tombstone).
    """
    value = _component(command=command, key=key, default=None)
    return value if isinstance(value, dict) else None
