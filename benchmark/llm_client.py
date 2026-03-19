"""Multi-provider LLM client with normal and streaming modes.

Supports Anthropic (Claude), OpenAI (GPT/o-series), and Google (Gemini).
Provider is auto-detected from the model name.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    wall_clock_s: float
    server_processing_ms: float = 0.0  # Server-side processing time from API headers


@dataclass
class StreamingResult:
    text: str
    input_tokens: int
    output_tokens: int
    wall_clock_s: float
    chunks: list[tuple[str, float]] = field(default_factory=list)  # (text, timestamp)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class LLMClient(ABC):
    """Provider-agnostic LLM client interface."""

    @abstractmethod
    def complete(self, system_prompt: str, user_message: str) -> LLMResult: ...

    @abstractmethod
    def complete_streaming(self, system_prompt: str, user_message: str) -> StreamingResult: ...


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------

class AnthropicClient(LLMClient):
    def __init__(self, model: str, temperature: float, max_tokens: int) -> None:
        import anthropic
        self._client = anthropic.Anthropic()
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_message: str) -> LLMResult:
        t0 = time.monotonic()
        raw = self._client.messages.with_raw_response.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        wall_clock = time.monotonic() - t0
        response = raw.parse()

        # Server processing time from upstream header (ms)
        server_ms = float(raw.headers.get("x-envoy-upstream-service-time", 0))

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        return LLMResult(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            wall_clock_s=wall_clock,
            server_processing_ms=server_ms,
        )

    def complete_streaming(self, system_prompt: str, user_message: str) -> StreamingResult:
        chunks: list[tuple[str, float]] = []
        full_text = ""
        input_tokens = 0
        output_tokens = 0

        t0 = time.monotonic()
        with self._client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for event in stream:
                if hasattr(event, "type"):
                    if event.type == "content_block_delta" and hasattr(event, "delta"):
                        delta = event.delta
                        if hasattr(delta, "text"):
                            ts = time.monotonic() - t0
                            chunks.append((delta.text, ts))
                            full_text += delta.text
                    elif event.type == "message_delta" and hasattr(event, "usage"):
                        output_tokens = event.usage.output_tokens
                    elif event.type == "message_start" and hasattr(event, "message"):
                        input_tokens = event.message.usage.input_tokens

        wall_clock = time.monotonic() - t0

        return StreamingResult(
            text=full_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            wall_clock_s=wall_clock,
            chunks=chunks,
        )


# ---------------------------------------------------------------------------
# OpenAI (GPT-4o, GPT-4.1, o-series)
# ---------------------------------------------------------------------------

class OpenAIClient(LLMClient):
    def __init__(self, model: str, temperature: float, max_tokens: int) -> None:
        from openai import OpenAI
        self._client = OpenAI()
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    @staticmethod
    def _supports_temperature(model: str) -> bool:
        """Some OpenAI models (nano, reasoning) don't support temperature."""
        no_temp = ("nano", "o1", "o3", "o4")
        return not any(k in model for k in no_temp)

    def complete(self, system_prompt: str, user_message: str) -> LLMResult:
        t0 = time.monotonic()
        kwargs: dict[str, Any] = dict(
            model=self._model,
            max_completion_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        if self._supports_temperature(self._model):
            kwargs["temperature"] = self._temperature
        raw = self._client.chat.completions.with_raw_response.create(**kwargs)
        wall_clock = time.monotonic() - t0
        response = raw.parse()

        # Server processing time from OpenAI header (ms)
        server_ms = float(raw.headers.get("openai-processing-ms", 0))

        text = response.choices[0].message.content or ""
        usage = response.usage

        return LLMResult(
            text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            wall_clock_s=wall_clock,
            server_processing_ms=server_ms,
        )

    def complete_streaming(self, system_prompt: str, user_message: str) -> StreamingResult:
        chunks: list[tuple[str, float]] = []
        full_text = ""
        input_tokens = 0
        output_tokens = 0

        t0 = time.monotonic()
        kwargs: dict[str, Any] = dict(
            model=self._model,
            max_completion_tokens=self._max_tokens,
            stream=True,
            stream_options={"include_usage": True},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        if self._supports_temperature(self._model):
            kwargs["temperature"] = self._temperature
        stream = self._client.chat.completions.create(**kwargs)
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                ts = time.monotonic() - t0
                text = chunk.choices[0].delta.content
                chunks.append((text, ts))
                full_text += text
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens

        wall_clock = time.monotonic() - t0

        return StreamingResult(
            text=full_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            wall_clock_s=wall_clock,
            chunks=chunks,
        )


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

class GeminiClient(LLMClient):
    """Google Gemini client using the google-genai SDK.

    Prefers AI Studio (GEMINI_API_KEY or GOOGLE_API_KEY) because it returns
    server-timing headers needed for benchmarking. Falls back to Vertex AI
    (GOOGLE_CLOUD_PROJECT) only if no API key is set.
    """

    MAX_RETRIES = 8
    RETRY_BASE_DELAY = 15.0  # seconds

    def __init__(self, model: str, temperature: float, max_tokens: int) -> None:
        import os
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if api_key:
            # AI Studio — returns server-timing header
            self._client = genai.Client(api_key=api_key)
            self.RETRY_BASE_DELAY = 10.0
        else:
            project = os.environ.get("GOOGLE_CLOUD_PROJECT")
            if project:
                location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
                self._client = genai.Client(
                    vertexai=True, project=project, location=location,
                )
                self.RETRY_BASE_DELAY = 5.0
            else:
                self._client = genai.Client()
        self._model_name = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    @staticmethod
    def _is_retryable(e: Exception) -> bool:
        """Check if exception is a retryable API error (rate-limit or overload)."""
        msg = str(e)
        cls = type(e).__name__
        return (
            "429" in msg or "503" in msg
            or "ResourceExhausted" in cls
            or "ServerError" in cls
            or "UNAVAILABLE" in msg
            or "high demand" in msg
        )

    def _retry_on_rate_limit(self, fn: Any) -> Any:
        """Call fn(), retrying on rate-limit and server overload errors."""
        for attempt in range(self.MAX_RETRIES):
            try:
                return fn()
            except Exception as e:
                if self._is_retryable(e):
                    delay = self.RETRY_BASE_DELAY * (attempt + 1)
                    print(f" [retry {attempt+1}/{self.MAX_RETRIES} in {delay:.0f}s]", end="", flush=True)
                    time.sleep(delay)
                else:
                    raise
        # Final attempt without catching
        return fn()

    @staticmethod
    def _extract_server_timing(response: Any) -> float:
        """Extract server processing time from Google's server-timing header."""
        import re
        http = getattr(response, "sdk_http_response", None)
        if http and hasattr(http, "headers"):
            st = http.headers.get("server-timing", "")
            m = re.search(r"dur=(\d+(?:\.\d+)?)", st)
            if m:
                return float(m.group(1))
        return 0.0

    def complete(self, system_prompt: str, user_message: str) -> LLMResult:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self._temperature,
            max_output_tokens=self._max_tokens,
        )

        t0 = time.monotonic()
        response = self._retry_on_rate_limit(
            lambda: self._client.models.generate_content(
                model=self._model_name,
                contents=user_message,
                config=config,
            )
        )
        wall_clock = time.monotonic() - t0

        text = response.text or ""
        usage = response.usage_metadata
        server_ms = self._extract_server_timing(response)

        return LLMResult(
            text=text,
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
            wall_clock_s=wall_clock,
            server_processing_ms=server_ms,
        )

    def complete_streaming(self, system_prompt: str, user_message: str) -> StreamingResult:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self._temperature,
            max_output_tokens=self._max_tokens,
        )

        chunks: list[tuple[str, float]] = []
        full_text = ""
        input_tokens = 0
        output_tokens = 0

        t0 = time.monotonic()

        def _do_stream() -> Any:
            return self._client.models.generate_content_stream(
                model=self._model_name,
                contents=user_message,
                config=config,
            )

        stream = self._retry_on_rate_limit(_do_stream)
        for chunk in stream:
            if chunk.text:
                ts = time.monotonic() - t0
                chunks.append((chunk.text, ts))
                full_text += chunk.text
            if chunk.usage_metadata:
                input_tokens = chunk.usage_metadata.prompt_token_count or 0
                output_tokens = chunk.usage_metadata.candidates_token_count or 0

        wall_clock = time.monotonic() - t0

        return StreamingResult(
            text=full_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            wall_clock_s=wall_clock,
            chunks=chunks,
        )


# ---------------------------------------------------------------------------
# Mistral
# ---------------------------------------------------------------------------

class MistralClient(LLMClient):
    """Mistral client via OpenAI-compatible API.

    Uses x-envoy-upstream-service-time header for server processing time
    (same header as Anthropic).
    """

    def __init__(self, model: str, temperature: float, max_tokens: int) -> None:
        import os
        from openai import OpenAI
        self._client = OpenAI(
            api_key=os.environ["MISTRAL_API_KEY"],
            base_url="https://api.mistral.ai/v1",
        )
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_message: str) -> LLMResult:
        t0 = time.monotonic()
        raw = self._client.chat.completions.with_raw_response.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        wall_clock = time.monotonic() - t0
        response = raw.parse()

        # Server processing time — same envoy header as Anthropic
        server_ms = float(raw.headers.get("x-envoy-upstream-service-time", 0))

        text = response.choices[0].message.content or ""
        usage = response.usage

        return LLMResult(
            text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            wall_clock_s=wall_clock,
            server_processing_ms=server_ms,
        )

    def complete_streaming(self, system_prompt: str, user_message: str) -> StreamingResult:
        chunks: list[tuple[str, float]] = []
        full_text = ""
        input_tokens = 0
        output_tokens = 0

        t0 = time.monotonic()
        stream = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            stream=True,
            stream_options={"include_usage": True},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                ts = time.monotonic() - t0
                text = chunk.choices[0].delta.content
                chunks.append((text, ts))
                full_text += text
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens

        wall_clock = time.monotonic() - t0

        return StreamingResult(
            text=full_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            wall_clock_s=wall_clock,
            chunks=chunks,
        )


# ---------------------------------------------------------------------------
# Provider detection and factory
# ---------------------------------------------------------------------------

# Model prefix → provider
_PROVIDER_PREFIXES: dict[str, str] = {
    "claude-": "anthropic",
    "gpt-": "openai",
    "o1": "openai",
    "o3": "openai",
    "o4": "openai",
    "gemini-": "google",
    "mistral-": "mistral",
}

# Provider → (input_price_per_1M, output_price_per_1M)
PRICING: dict[str, dict[str, tuple[float, float]]] = {
    # Anthropic
    "claude-opus-4-6": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-haiku-4-5": (0.80, 4.00),
    "claude-haiku-3-5-20241022": (0.80, 4.00),
    # OpenAI
    "gpt-5.4": (2.50, 15.00),
    "gpt-5": (1.25, 10.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.02, 0.15),
    "o3-mini": (1.10, 4.40),
    # Google
    "gemini-3.1-pro-preview": (1.25, 10.00),
    "gemini-3.1-flash": (0.15, 3.50),
    "gemini-2.5-flash": (0.15, 3.50),
    "gemini-2.5-flash-lite": (0.075, 0.30),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
    # Mistral
    "mistral-large-latest": (0.50, 1.50),
    "mistral-large-2512": (0.50, 1.50),
    "mistral-medium-latest": (0.40, 2.00),
    "mistral-small-latest": (0.06, 0.18),
}


def detect_provider(model: str) -> str:
    """Detect provider from model name."""
    for prefix, provider in _PROVIDER_PREFIXES.items():
        if model.startswith(prefix):
            return provider
    raise ValueError(
        f"Cannot detect provider for model '{model}'. "
        f"Known prefixes: {list(_PROVIDER_PREFIXES.keys())}"
    )


def get_pricing(model: str) -> tuple[float, float]:
    """Return (input_price, output_price) per 1M tokens for a model.

    Falls back to a rough default if model not in table.
    """
    # Exact match
    if model in PRICING:
        return PRICING[model]
    # Prefix match (e.g. "gpt-4o-2024-11-20" → "gpt-4o")
    for key, price in PRICING.items():
        if model.startswith(key):
            return price
    # Default fallback
    return (3.00, 15.00)


def create_client(model: str, temperature: float, max_tokens: int) -> LLMClient:
    """Factory: create the right LLMClient subclass for the given model."""
    provider = detect_provider(model)
    if provider == "anthropic":
        return AnthropicClient(model, temperature, max_tokens)
    elif provider == "openai":
        return OpenAIClient(model, temperature, max_tokens)
    elif provider == "google":
        return GeminiClient(model, temperature, max_tokens)
    elif provider == "mistral":
        return MistralClient(model, temperature, max_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider}")
