"""Optional server-side JSON provider adapter, without an SDK or paid dependency.

Configuration is supplied by the caller from environment variables or Streamlit
Secrets. A key alone never enables requests: the operator must explicitly name a
model and confirm their eligible free-tier configuration. The application cannot
verify an account's billing plan, regional eligibility or current free quota.
"""
from dataclasses import dataclass, field
import json
import math
import re
import socket
from typing import Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
MAX_RESPONSE_BYTES = 1024 * 1024
_MODEL = re.compile(r"^[A-Za-z0-9_./:-]{1,160}$")
_MESSAGES = {
    "missing_credentials": "AI assistance is not configured; deterministic guidance remains available.",
    "free_tier_unconfirmed": "The operator has not confirmed an eligible free-tier configuration.",
    "unsupported": "The configured provider, model or response format is unavailable.",
    "input_limit": "The case exceeds the configured AI input allowance.",
    "rate_limit": "The provider's rate limit was reached; deterministic guidance remains available.",
    "quota_exhausted": "The provider's available quota was exhausted; no paid fallback was used.",
    "credentials_rejected": "The provider did not accept the configured credentials.",
    "timeout": "The AI request timed out; deterministic guidance remains available.",
    "unavailable": "The AI provider is unavailable; deterministic guidance remains available.",
    "malformed": "The AI response was not valid supported JSON.",
}


class AIProviderError(Exception):
    """A sanitised failure that never includes credentials, prompts or raw bodies."""

    def __init__(self, code: str):
        self.code = code if code in _MESSAGES else "unavailable"
        super().__init__(_MESSAGES[self.code])


def _integer(value, default, minimum, maximum):
    try:
        if isinstance(value, bool):
            return default
        return min(maximum, max(minimum, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def _seconds(value):
    try:
        result = float(value)
        return min(30.0, max(2.0, result)) if math.isfinite(result) else 12.0
    except (TypeError, ValueError, OverflowError):
        return 12.0


@dataclass(frozen=True)
class AIConfig:
    api_key: str = field(default="", repr=False)
    provider: str = "groq"
    model: str = ""
    free_tier_confirmed: bool = False
    max_requests: int = 3
    max_input_tokens: int = 7000
    max_output_tokens: int = 1800
    timeout_seconds: float = 12.0

    def __post_init__(self):
        for name in ('api_key', 'provider', 'model'):
            value = getattr(self, name)
            object.__setattr__(self, name, value.strip() if isinstance(value, str) else '')
        object.__setattr__(self, 'provider', self.provider.lower())
        object.__setattr__(self, 'free_tier_confirmed', self.free_tier_confirmed is True)
        object.__setattr__(self, 'max_requests', _integer(self.max_requests, 3, 0, 3))
        object.__setattr__(self, 'max_input_tokens', _integer(self.max_input_tokens, 7000, 256, 16384))
        object.__setattr__(self, 'max_output_tokens', _integer(self.max_output_tokens, 1800, 128, 4096))
        object.__setattr__(self, 'timeout_seconds', _seconds(self.timeout_seconds))

    @classmethod
    def from_mapping(cls, values: Mapping):
        def text(name, default=""):
            value = values.get(name, default)
            return value.strip() if isinstance(value, str) else default

        confirmed = values.get("OBJECTIVITY_AI_FREE_TIER_CONFIRMED", False)
        return cls(
            api_key=text("GROQ_API_KEY"),
            provider=text("OBJECTIVITY_AI_PROVIDER", "groq").lower(),
            model=text("OBJECTIVITY_AI_MODEL"),
            free_tier_confirmed=confirmed is True or isinstance(confirmed, str) and confirmed.lower().strip() == "true",
            max_requests=_integer(values.get("OBJECTIVITY_AI_MAX_REQUESTS", 3), 3, 0, 3),
            max_input_tokens=_integer(values.get("OBJECTIVITY_AI_MAX_INPUT_TOKENS", 7000), 7000, 256, 16384),
            max_output_tokens=_integer(values.get("OBJECTIVITY_AI_MAX_OUTPUT_TOKENS", 1800), 1800, 128, 4096),
            timeout_seconds=_seconds(values.get("OBJECTIVITY_AI_TIMEOUT_SECONDS", 12)),
        )

    @property
    def enabled(self):
        return self.disabled_reason == ""

    @property
    def disabled_reason(self):
        if self.provider != "groq":
            return "unsupported"
        if not self.api_key or len(self.api_key) > 4096 or "\r" in self.api_key or "\n" in self.api_key or not self.model:
            return "missing_credentials"
        if not _MODEL.fullmatch(self.model):
            return "unsupported"
        if self.free_tier_confirmed is not True:
            return "free_tier_unconfirmed"
        if self.max_requests < 1:
            return "quota_exhausted"
        return ""


class JSONProvider(Protocol):
    def generate(self, system: str, user: str) -> dict: ...


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("nonstandard JSON number")


def strict_json_object(text: str) -> dict:
    """Parse bounded JSON without executable or permissive deserialisation."""
    try:
        if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_RESPONSE_BYTES:
            raise AIProviderError('malformed')
        result = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise AIProviderError("malformed") from None
    if not isinstance(result, dict):
        raise AIProviderError("malformed")
    return result


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a server-side credential to a redirected host.
        return None


def _open(request, *, timeout):
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


class GroqProvider:
    """Groq-compatible adapter. Availability and free access require operator checks."""

    def __init__(self, config: AIConfig, transport=None):
        self.config = config
        self._transport = transport or _open

    def generate(self, system: str, user: str) -> dict:
        config = self.config
        if not config.enabled:
            raise AIProviderError(config.disabled_reason)
        if not isinstance(system, str) or not isinstance(user, str):
            raise AIProviderError("input_limit")
        # UTF-8 bytes + message overhead form a deliberately conservative
        # token-budget check. Exact provider tokenisation is model-specific.
        if len((system + user).encode("utf-8")) + 256 > config.max_input_tokens:
            raise AIProviderError("input_limit")
        body = json.dumps({
            "model": config.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
            "max_tokens": config.max_output_tokens,
            "temperature": 0,
        }, ensure_ascii=False, allow_nan=False).encode("utf-8")
        request = Request(ENDPOINT, data=body, method="POST", headers={
            "Authorization": "Bearer " + config.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with self._transport(request, timeout=config.timeout_seconds) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise AIProviderError("malformed")
            envelope = strict_json_object(raw.decode("utf-8", errors="strict"))
            choices = envelope.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise AIProviderError("malformed")
            if choices[0].get("finish_reason") not in {None, "stop"}:
                raise AIProviderError("malformed")
            message = choices[0].get("message")
            if not isinstance(message, dict):
                raise AIProviderError("malformed")
            return strict_json_object(message.get("content"))
        except AIProviderError:
            raise
        except HTTPError as error:
            code = {400: "unsupported", 401: "credentials_rejected", 402: "quota_exhausted", 404: "unsupported", 429: "rate_limit"}.get(error.code, "unavailable")
            raise AIProviderError(code) from None
        except (TimeoutError, socket.timeout):
            raise AIProviderError("timeout") from None
        except URLError as error:
            code = "timeout" if isinstance(error.reason, (TimeoutError, socket.timeout)) else "unavailable"
            raise AIProviderError(code) from None
        except (ValueError, TypeError, UnicodeError, OSError, RecursionError):
            raise AIProviderError("malformed") from None
