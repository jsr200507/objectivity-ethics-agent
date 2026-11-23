"""Session-scoped reuse and small, bounded optional-AI request budgets.

The shared limiter is in-memory only. It is a best-effort process-level control,
not an account-level entitlement or a substitute for provider-enforced quotas.
"""
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import threading
import time

from .ai_provider import AIConfig, AIProviderError, JSONProvider


@dataclass(frozen=True)
class AIResult:
    data: dict | None = None
    status: str = "fallback"
    reason: str = "unavailable"
    reused: bool = False
    attempted: bool = False

    @property
    def mode(self):
        return "AI-assisted" if self.status == "assisted" else "Deterministic fallback"


@dataclass(frozen=True)
class AIRequestEvent:
    purpose: str
    key_digest: str
    status: str
    reason: str


class _SharedLimiter:
    def __init__(self, concurrent=2, per_minute=12, clock=time.monotonic):
        self._slots = threading.BoundedSemaphore(concurrent)
        self._per_minute = per_minute
        self._clock = clock
        self._lock = threading.Lock()
        self._times = deque()
        self._blocked_until = 0.0

    def acquire(self):
        if not self._slots.acquire(blocking=False):
            return False
        with self._lock:
            now = self._clock()
            while self._times and self._times[0] <= now - 60:
                self._times.popleft()
            if now < self._blocked_until or len(self._times) >= self._per_minute:
                self._slots.release()
                return False
            self._times.append(now)
        return True

    def release(self):
        self._slots.release()

    def cooldown(self):
        with self._lock:
            self._blocked_until = max(self._blocked_until, self._clock() + 60)


_GLOBAL_LIMITER = _SharedLimiter()


def _key(purpose, source_key, config, system, user):
    payload = (purpose, source_key, config.provider, config.model,
               config.max_input_tokens, config.max_output_tokens, config.timeout_seconds,
               system, user)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


class AISession:
    """One assessment's request ledger; safe to reuse on Streamlit reruns.

    Source-key and actual-prompt changes invalidate only that cached request.
    Successful responses and failed attempts are both reused rather than retried.
    The caller may retain attempted-event counts in progress source history and
    restore the monotonic budget after refresh/import. No secret is stored here.
    """

    def __init__(self, max_requests=3, attempts=0, *, limiter=None):
        self.max_requests = max(0, min(3, int(max_requests)))
        self.attempts = max(0, int(attempts))
        self.events: list[AIRequestEvent] = []
        self._cache = {}
        self._lock = threading.RLock()
        self._limiter = limiter or _GLOBAL_LIMITER
        self._provider_block = ""

    def restore_budget(self, attempts):
        if type(attempts) is not int or attempts < 0:
            raise ValueError("The restored AI request count must be a nonnegative integer.")
        with self._lock:
            self.attempts = max(self.attempts, attempts)

    def request(self, purpose: str, source_key: str, config: AIConfig,
                provider: JSONProvider | None, system: str, user: str, *, consent=False) -> AIResult:
        if consent is not True:
            return AIResult(reason="consent_required")
        if not config.enabled:
            return AIResult(reason=config.disabled_reason)
        if provider is None:
            return AIResult(reason="unavailable")
        if purpose not in {"understanding", "clarification", "report"}:
            return AIResult(reason="unsupported")
        if not isinstance(source_key, str) or not isinstance(system, str) or not isinstance(user, str):
            return AIResult(reason="input_limit")
        if len((system + user).encode("utf-8")) + 256 > config.max_input_tokens:
            return AIResult(reason="input_limit")
        key = _key(purpose, source_key, config, system, user)
        with self._lock:
            if key in self._cache:
                cached = self._cache[key]
                return AIResult(deepcopy(cached.data), cached.status, cached.reason, True, False)
            if self._provider_block:
                return AIResult(reason=self._provider_block)
            if self.attempts >= min(self.max_requests, config.max_requests, 3):
                return AIResult(reason="assessment_limit")
            if not self._limiter.acquire():
                return AIResult(reason="busy")
            self.attempts += 1
            try:
                data = provider.generate(system, user)
                if not isinstance(data, dict):
                    raise AIProviderError("malformed")
                result = AIResult(deepcopy(data), "assisted", "", attempted=True)
            except AIProviderError as error:
                result = AIResult(reason=error.code, attempted=True)
                if error.code in {"rate_limit", "quota_exhausted", "credentials_rejected", "unsupported"}:
                    self._provider_block = error.code
                if error.code in {"rate_limit", "quota_exhausted"}:
                    self._limiter.cooldown()
            except Exception:
                # Provider implementations must never leak raw error bodies,
                # complete case content or credentials through the UI.
                result = AIResult(reason="unavailable", attempted=True)
            finally:
                self._limiter.release()
            self._cache[key] = result
            self.events.append(AIRequestEvent(purpose, key, result.status, result.reason))
            return deepcopy(result)
