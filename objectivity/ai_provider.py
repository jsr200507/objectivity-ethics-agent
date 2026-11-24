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
import ssl
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
    "dns_error": "DNS resolution failed. Check the server's DNS and outbound network access.",
    "network_error": "A network connection to Groq could not be completed. Check outbound access and proxy settings.",
    "proxy_error": "The HTTPS proxy rejected the connection before Groq could be reached. Check the server's proxy policy.",
    "tls_error": "TLS certificate validation or the SSL connection failed. Check server CA certificates and proxy settings; keep TLS verification enabled.",
    "bad_request": "Groq rejected the request (HTTP 400). Check the model's supported parameters and configured token limits.",
    "forbidden": "Access was denied (HTTP 403). Check project permissions, service restrictions and server egress access.",
    "provider_error": "Groq or its gateway returned an HTTP 5xx error. Try a new explicit diagnostic later; no automatic retry is made.",
    "redirect_blocked": "The API redirected the request. Credentials were not forwarded; check the endpoint and proxy.",
    "invalid_json": "An HTTP response was received, but the completion was not a valid JSON object.",
    "invalid_response": "An HTTP response was received, but its completion envelope was missing or unsupported.",
    "response_truncated": "The completion reached its token limit. Check the output allowance and reasoning effort; no partial JSON was accepted.",
    "generation_invalid_json": "Groq reported JSON generation failure. Local guidance is retained; this is not a network failure.",
    "application_validation": "Groq returned JSON, but application schema or evidence checks rejected it. Local guidance is retained.",
    "runtime_error": "A provider-client runtime error occurred. Consult the safe operator diagnostic or server logs.",
}


class AIProviderError(Exception):
    """A sanitised failure that never includes credentials, prompts or raw bodies."""

    def __init__(self, code: str, **details):
        self.code = code if code in _MESSAGES else "unavailable"
        self.diagnostic = safe_diagnostics(details)
        super().__init__(_MESSAGES[self.code])


def safe_diagnostics(details):
    """Allow only fixed technical fields, never raw messages, prompts or bodies."""
    if type(details) is not dict:
        return {}
    result = {}
    status = details.get('http_status')
    if type(status) is int and 100 <= status <= 599:
        result['http_status'] = status
    if details.get('completion_received') is True:
        result['completion_received'] = True
    for key in ('exception_type',):
        value = details.get(key)
        if isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', value):
            result[key] = value
    value = details.get('request_id')
    if isinstance(value, str) and re.fullmatch(r'(?:req_[A-Za-z0-9_-]{8,80}|[0-9a-fA-F-]{16,64})', value):
        result['request_id'] = value
    if isinstance(details.get('finish_reason'), str) and details['finish_reason'] in {'stop', 'length', 'tool_calls', 'function_call', 'content_filter'}:
        result['finish_reason'] = details['finish_reason']
    if isinstance(details.get('response_origin'), str) and details['response_origin'] in {'provider', 'proxy'}:
        result['response_origin'] = details['response_origin']
    if isinstance(details.get('provider_code'), str) and details['provider_code'] in {'json_validate_failed', 'context_length_exceeded', 'model_not_found', 'model_decommissioned', 'invalid_api_key', 'rate_limit_exceeded'}:
        result['provider_code'] = details['provider_code']
    return result


def provider_error_message(code):
    return _MESSAGES.get(code, _MESSAGES['unavailable'])


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
        return min(60.0, max(2.0, result)) if math.isfinite(result) else 30.0
    except (TypeError, ValueError, OverflowError):
        return 30.0


@dataclass(frozen=True)
class AIConfig:
    api_key: str = field(default="", repr=False)
    provider: str = "groq"
    model: str = ""
    free_tier_confirmed: bool = False
    max_requests: int = 3
    max_input_tokens: int = 7000
    max_output_tokens: int = 1800
    timeout_seconds: float = 30.0

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
            timeout_seconds=_seconds(values.get("OBJECTIVITY_AI_TIMEOUT_SECONDS", 30)),
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
            raise AIProviderError('invalid_json')
        result = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise AIProviderError("invalid_json") from None
    if not isinstance(result, dict):
        raise AIProviderError("invalid_json")
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
        self.diagnostic = {}

    def generate(self, system: str, user: str) -> dict:
        config = self.config
        self.diagnostic = {}
        if not config.enabled:
            raise AIProviderError(config.disabled_reason)
        if not isinstance(system, str) or not isinstance(user, str):
            raise AIProviderError("input_limit")
        # UTF-8 bytes + message overhead form a deliberately conservative
        # token-budget check. Exact provider tokenisation is model-specific.
        if len((system + user).encode("utf-8")) + 256 > config.max_input_tokens:
            raise AIProviderError("input_limit")
        payload = {
            "model": config.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
            "max_completion_tokens": config.max_output_tokens,
            "temperature": 0,
        }
        if config.model in {'openai/gpt-oss-120b', 'openai/gpt-oss-20b'}:
            payload['reasoning_effort'] = 'low'
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        request = Request(ENDPOINT, data=body, method="POST", headers={
            "Authorization": "Bearer " + config.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ObjectivityEthicsAssistant/1.0",
        })
        try:
            with self._transport(request, timeout=config.timeout_seconds) as response:
                status = getattr(response, 'status', 200)
                headers = getattr(response, 'headers', {})
                self.diagnostic = safe_diagnostics({'http_status': status, 'response_origin': 'provider',
                    'request_id': headers.get('x-request-id') if headers else None})
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise AIProviderError("invalid_response")
            envelope = strict_json_object(raw.decode("utf-8", errors="strict"))
            choices = envelope.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise AIProviderError("invalid_response")
            self.diagnostic['completion_received'] = True
            finish = choices[0].get('finish_reason')
            self.diagnostic.update(safe_diagnostics({'finish_reason': finish}))
            if finish == 'length':
                raise AIProviderError('response_truncated')
            if finish not in {None, "stop"}:
                raise AIProviderError("invalid_response")
            message = choices[0].get("message")
            if not isinstance(message, dict):
                raise AIProviderError("invalid_response")
            return strict_json_object(message.get("content"))
        except AIProviderError as error:
            raise AIProviderError(error.code, **{**self.diagnostic, **error.diagnostic}) from None
        except HTTPError as error:
            code = {400: "bad_request", 401: "credentials_rejected", 402: "quota_exhausted", 403: "forbidden", 404: "unsupported", 429: "rate_limit"}.get(error.code,
                'provider_error' if 500 <= error.code <= 599 else 'redirect_blocked' if 300 <= error.code <= 399 else 'unavailable')
            details = {'http_status': error.code, 'response_origin': 'provider', 'exception_type': type(error).__name__}
            if error.headers:
                details['request_id'] = error.headers.get('x-request-id')
            # Read only a bounded machine code; never retain or display bodies.
            try:
                envelope = strict_json_object(error.read(8193).decode('utf-8'))
                details['provider_code'] = envelope.get('error', {}).get('code')
            except Exception:
                pass
            details = safe_diagnostics(details)
            if details.get('provider_code') == 'json_validate_failed':
                code = 'generation_invalid_json'
            self.diagnostic = details
            raise AIProviderError(code, **details) from None
        except (TimeoutError, socket.timeout) as error:
            raise AIProviderError("timeout", **self.diagnostic, exception_type=type(error).__name__) from None
        except ssl.SSLError as error:
            raise AIProviderError('tls_error', **self.diagnostic, exception_type=type(error).__name__) from None
        except URLError as error:
            reason = error.reason
            code = 'timeout' if isinstance(reason, (TimeoutError, socket.timeout)) else 'tls_error' if isinstance(reason, ssl.SSLError) else 'dns_error' if isinstance(reason, socket.gaierror) else 'network_error'
            details = {'exception_type': type(reason).__name__}
            proxy = re.search(r'tunnel connection failed:\s*(\d{3})', str(reason), re.I)
            if proxy:
                code = 'proxy_error'
                details.update(http_status=int(proxy[1]), response_origin='proxy')
            raise AIProviderError(code, **details) from None
        except socket.gaierror as error:
            raise AIProviderError('dns_error', exception_type=type(error).__name__) from None
        except OSError as error:
            raise AIProviderError('network_error', **self.diagnostic, exception_type=type(error).__name__) from None
        except (ValueError, TypeError, UnicodeError, RecursionError) as error:
            raise AIProviderError('invalid_json', **self.diagnostic, exception_type=type(error).__name__) from None
