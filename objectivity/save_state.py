"""Session-only coordinator for acknowledged, conditional browser writes.

This module does not hold an assessment or infer persistence from session state.
Only a matching successful browser acknowledgement marks a payload as saved.
"""

from dataclasses import dataclass, field
from uuid import uuid4


def _command(op: str, token: str | None = None, data: str | None = None) -> dict:
    command = {"id": uuid4().hex, "op": op}
    if op != "read":
        command["expected_token"] = token
    if op == "write":
        command["data"] = data
    return command


@dataclass
class BrowserSaveState:
    command: dict = field(default_factory=lambda: _command("read"))
    busy: bool = True
    mode: str = "checking"
    token: str | None = None
    saved_data: str | None = None
    last_saved_data: str | None = None
    error: str = ""
    purpose: str = "read"
    handled_id: str = ""

    @property
    def available(self) -> bool:
        return self.mode not in {"checking", "unavailable"}

    def request(self, op: str, data: str | None = None, purpose: str = "autosave") -> None:
        if self.busy:
            raise ValueError("A browser operation is still pending.")
        if op not in {"read", "write", "clear"}:
            raise ValueError("Unsupported browser operation.")
        if op == "write" and not isinstance(data, str):
            raise ValueError("A browser write requires serialized progress.")
        self.command = _command(op, self.token, data)
        self.purpose = purpose
        self.busy = True

    def consume(self, response) -> str | None:
        """Return the completed operation purpose, or None for stale/no events."""
        if not isinstance(response, dict) or response.get("id") != self.command["id"]:
            return None
        if response.get("op") != self.command["op"] or self.handled_id == response["id"]:
            return None
        status = response.get("status")
        if status not in {"ok", "conflict", "unavailable", "corrupt"}:
            return None
        token, data = response.get("token"), response.get("data")
        if token is not None and (not isinstance(token, str) or not token or len(token) > 256):
            return None
        if data is not None and not isinstance(data, str):
            return None
        self.handled_id = response["id"]
        self.busy = False
        self.error = str(response.get("reason") or "")[:500]
        if status == "unavailable":
            self.mode = "unavailable"
            return self.purpose + ":failed"
        self.token, self.saved_data = token, data
        if status in {"conflict", "corrupt"}:
            if status == "corrupt" and self.saved_data is None:
                raw = response.get("raw")
                if isinstance(raw, str) and len(raw.encode("utf-8", errors="replace")) <= 2 * 1024 * 1024:
                    self.saved_data = raw
            self.mode = status
            return self.purpose + ":failed"
        if self.command["op"] == "read":
            if data is not None and token is None:
                self.mode = "unavailable"
                self.error = "The browser did not provide a valid saved-copy identifier. Use Download progress."
                return self.purpose + ":failed"
            self.mode = "choice" if data is not None else "active"
        elif self.command["op"] == "write":
            # A well-formed ack must describe the exact submitted payload.
            if token is None or data != self.command["data"]:
                self.mode = "unavailable"
                self.error = "The browser did not confirm the submitted progress. Use Download progress."
                return self.purpose + ":failed"
            self.mode = "active"
            self.last_saved_data = data
        else:
            if data is not None or token is None:
                self.mode = "unavailable"
                self.error = "The browser did not confirm removal of the saved assessment."
                return self.purpose + ":failed"
            self.mode = "active"
            self.last_saved_data = None
        return self.purpose

    def resume(self, normalized_data: str) -> None:
        """Explicit user selection adopts the existing browser assessment."""
        if self.mode not in {"choice", "conflict"} or self.saved_data is None:
            raise ValueError("There is no saved assessment to resume.")
        self.mode = "active"
        # Normalization may archive stale answers. Persist that normalized state
        # on the next acknowledged autosave rather than pretending it was stored.
        self.last_saved_data = self.saved_data
        self.error = ""
