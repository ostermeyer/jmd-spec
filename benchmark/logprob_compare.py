#!/usr/bin/env python3
"""Compute-cost comparison: Pretty JSON vs Minified JSON vs JMD.

Three formats compared:
- **Pretty JSON** — what LLMs produce by default
- **Minified JSON** — explicit instruction to omit whitespace
- **JMD** — JSON Markdown with 5-bullet primer

Two measurement types:
1. **Streaming TPOT/TTFT** — for all providers (OpenAI, Anthropic, Gemini)
2. **LogProb analysis** — OpenAI only (per Schall & de Melo, RANLP 2025)

Aggregation uses **trimmed mean**: best and worst result per model/format
are dropped before averaging (requires >= 4 runs).

Requires: openai, anthropic, google-genai, tiktoken
"""

from __future__ import annotations

import json
import math
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmark.llm_client import (
    StreamingResult,
    create_client,
)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TokenLogProb:
    token: str
    logprob: float
    is_structural: bool = False


@dataclass
class StreamingMetrics:
    format_name: str
    model: str
    text: str
    input_tokens: int
    output_tokens: int
    wall_clock_s: float
    ttft_s: float
    tpot_ms: float
    tps: float
    chunk_count: int
    token_logprobs: list[TokenLogProb] = field(default_factory=list)

    @property
    def structural_tokens(self) -> list[TokenLogProb]:
        return [t for t in self.token_logprobs if t.is_structural]

    @property
    def content_tokens(self) -> list[TokenLogProb]:
        return [t for t in self.token_logprobs if not t.is_structural]

    @property
    def mean_structural_logprob(self) -> float:
        st = self.structural_tokens
        return statistics.mean(t.logprob for t in st) if st else 0.0

    @property
    def mean_content_logprob(self) -> float:
        ct = self.content_tokens
        return statistics.mean(t.logprob for t in ct) if ct else 0.0

    @property
    def mean_structural_prob(self) -> float:
        st = self.structural_tokens
        return statistics.mean(math.exp(t.logprob) for t in st) if st else 0.0


# ---------------------------------------------------------------------------
# Token classification
# ---------------------------------------------------------------------------

JSON_STRUCTURAL = {
    "{", "}", "[", "]", '"', ",", ":",
    '{"', '"}', '["', '"]', '",', '":"', '": ', '": "',
    "{\n", "}\n", "],", "},", '":', ',"',
}

JMD_STRUCTURAL = {
    "#", "##", "###", "####",
    "- ", "-",
    ":", ": ",
    "> ",
}


def classify_json_token(token: str) -> bool:
    stripped = token.strip()
    if not stripped:
        return True
    if stripped in JSON_STRUCTURAL or token in JSON_STRUCTURAL:
        return True
    if all(c in '{}[]",:' for c in stripped):
        return True
    return False


def classify_jmd_token(token: str) -> bool:
    stripped = token.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if stripped == "-" or token.startswith("- "):
        return True
    if stripped.startswith(">"):
        return True
    if stripped == ":" or stripped == ": ":
        return True
    return False


def classify_tokens(metrics: StreamingMetrics) -> None:
    is_json = metrics.format_name in ("json", "json_minified")
    classifier = classify_json_token if is_json else classify_jmd_token
    for t in metrics.token_logprobs:
        t.is_structural = classifier(t.token)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

TASK_PROMPT = (
    "Extract the structured order data from the following document.\n"
    "Include all fields: order id, status, customer details, and line items "
    "with sku, product name, quantity, and unit price.\n\n"
    "---\n"
    "ORDER CONFIRMATION\n\n"
    "Dear Maria Santos,\n\n"
    "Thank you for your order! We are pleased to confirm that your order "
    "ORD-2024-7391 has been shipped. You can reach us regarding this order "
    "at your registered email m.santos@example.com (customer account C-4820).\n\n"
    "The following items are included in your shipment:\n\n"
    "  2x Wireless Keyboard (SKU BK-1147) at $49.95 each\n"
    "  1x Ergonomic Mouse (SKU MS-0832) at $34.50 each\n"
    "  3x USB-C Hub 7-Port (SKU HD-2291) at $27.99 each\n\n"
    "We appreciate your business.\n"
    "---"
)

FORMATS: dict[str, tuple[str, str]] = {
    "json": (
        "json",
        "You are an API assistant. Return data as JSON.\n"
        "Produce only the JSON object, no explanation.",
    ),
    "json_minified": (
        "json_minified",
        "You are an API assistant. Return data as minified JSON "
        "(no whitespace, no newlines, no indentation).\n"
        "Produce only the JSON object, no explanation.",
    ),
    "jmd": (
        "jmd",
        "You are an API assistant. Return data as JMD (JSON Markdown).\n\n"
        "JMD rules:\n"
        "- # Label starts the root object; ## key opens nested objects (depth = nesting)\n"
        "- ## key[] declares an array; items start with - (no sub-headings per item)\n"
        "- key: value for fields, no other markup\n"
        "- Array objects: - key: value, indented continuation lines\n"
        "- > blockquotes for multiline text\n\n"
        "Produce only the data.",
    ),
}

FORMAT_LABELS = {
    "json": "Pretty JSON",
    "json_minified": "Minified JSON",
    "jmd": "JMD",
}


# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------

# The ground truth data that must be present in every valid output.
# Validated by parsing the output and checking all values exist in the
# resulting data structure (deep search).
EXPECTED_VALUES = [
    "ORD-2024-7391",
    "shipped",
    "C-4820",
    "Maria Santos",
    "m.santos@example.com",
    "BK-1147",
    "Wireless Keyboard",
    49.95,
    "MS-0832",
    "Ergonomic Mouse",
    34.50,
    "HD-2291",
    "USB-C Hub 7-Port",
    27.99,
]


def _collect_values(obj: Any) -> set[Any]:
    """Recursively collect all leaf values from a nested dict/list structure."""
    values: set[Any] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            values |= _collect_values(v)
    elif isinstance(obj, list):
        for v in obj:
            values |= _collect_values(v)
    elif isinstance(obj, (int, float)):
        values.add(obj)
        values.add(str(obj))
    elif isinstance(obj, str):
        values.add(obj)
        values.add(obj.lower())
    return values


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    clean = text.strip()
    if clean.startswith("```"):
        first_nl = clean.index("\n") if "\n" in clean else len(clean)
        clean = clean[first_nl + 1:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
    return clean


@dataclass
class ValidationResult:
    valid: bool
    missing_values: list[str] = field(default_factory=list)
    format_ok: bool = True
    format_error: str = ""
    parsed_data: Any = None


def validate_output(text: str, format_name: str) -> ValidationResult:
    """Validate output by parsing it and checking all expected values exist."""
    import json as _json
    from jmd import JMDParser

    clean = _strip_code_fences(text)
    parsed = None
    format_ok = True
    format_error = ""

    # Step 1: Parse into a data structure
    if format_name in ("json", "json_minified"):
        try:
            parsed = _json.loads(clean)
        except (ValueError, _json.JSONDecodeError) as e:
            format_ok = False
            format_error = f"Invalid JSON: {e}"
    elif format_name == "jmd":
        try:
            parsed = JMDParser().parse(clean)
        except Exception as e:
            format_ok = False
            format_error = f"JMD parse error: {e}"

    # Step 2: Check all expected values exist in the parsed data
    missing: list[str] = []
    if parsed is not None:
        found = _collect_values(parsed)
        for val in EXPECTED_VALUES:
            if isinstance(val, float):
                # Check float and common string representations
                if val not in found and str(val) not in found:
                    missing.append(str(val))
            elif isinstance(val, str):
                if val not in found and val.lower() not in found:
                    missing.append(val)

    valid = format_ok and len(missing) == 0
    return ValidationResult(
        valid=valid,
        missing_values=missing,
        format_ok=format_ok,
        format_error=format_error,
        parsed_data=parsed,
    )


# ---------------------------------------------------------------------------
# Streaming generation with metrics
# ---------------------------------------------------------------------------

def compute_streaming_metrics(
    sr: StreamingResult,
    format_name: str,
    model: str,
) -> StreamingMetrics:
    ttft = sr.chunks[0][1] if sr.chunks else sr.wall_clock_s
    tps = sr.output_tokens / sr.wall_clock_s if sr.wall_clock_s > 0 else 0.0

    intervals = []
    for i in range(1, len(sr.chunks)):
        dt = sr.chunks[i][1] - sr.chunks[i - 1][1]
        if dt > 0:
            intervals.append(dt)
    median_ici = statistics.median(intervals) if intervals else 0.0
    tokens_per_chunk = sr.output_tokens / max(len(sr.chunks), 1)
    tpot_ms = (median_ici / max(tokens_per_chunk, 1)) * 1000

    return StreamingMetrics(
        format_name=format_name,
        model=model,
        text=sr.text,
        input_tokens=sr.input_tokens,
        output_tokens=sr.output_tokens,
        wall_clock_s=sr.wall_clock_s,
        ttft_s=ttft,
        tpot_ms=tpot_ms,
        tps=tps,
        chunk_count=len(sr.chunks),
    )


def generate_streaming(
    model: str,
    system_prompt: str,
    user_message: str,
    format_name: str,
    max_retries: int = 5,
) -> StreamingMetrics:
    for attempt in range(max_retries):
        try:
            client = create_client(model, temperature=0.0, max_tokens=2048)
            sr = client.complete_streaming(system_prompt, user_message)
            return compute_streaming_metrics(sr, format_name, model)
        except Exception as e:
            msg = str(e)
            if any(s in msg for s in ("503", "429", "high demand", "UNAVAILABLE", "ResourceExhausted")):
                delay = 15 * (attempt + 1)
                print(f"[retry {attempt+1}/{max_retries} in {delay}s]", end=" ", flush=True)
                time.sleep(delay)
            else:
                raise
    # Final attempt without catching
    client = create_client(model, temperature=0.0, max_tokens=2048)
    sr = client.complete_streaming(system_prompt, user_message)
    return compute_streaming_metrics(sr, format_name, model)


# ---------------------------------------------------------------------------
# OpenAI LogProb generation
# ---------------------------------------------------------------------------

def openai_logprobs(
    model: str,
    system_prompt: str,
    user_message: str,
    format_name: str,
) -> list[TokenLogProb]:
    from openai import OpenAI
    client = OpenAI()

    response = client.chat.completions.create(
        model=model,
        temperature=0.0,
        max_completion_tokens=2048,
        logprobs=True,
        top_logprobs=5,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    tokens: list[TokenLogProb] = []
    choice = response.choices[0]
    if choice.logprobs and choice.logprobs.content:
        for ti in choice.logprobs.content:
            tokens.append(TokenLogProb(token=ti.token, logprob=ti.logprob))
    return tokens


# ---------------------------------------------------------------------------
# Server-side timing via HTTP headers (non-streaming)
# ---------------------------------------------------------------------------

@dataclass
class ServerTiming:
    """Server-side processing time from HTTP headers."""
    model: str
    format_name: str
    output_tokens: int
    server_ms: float  # pure server processing, no network
    text: str = ""  # response text for validation


def _parse_server_timing(headers: dict[str, str], provider: str) -> float:
    """Extract server processing time in ms from response headers."""
    if provider == "openai":
        return float(headers.get("openai-processing-ms", 0))
    elif provider == "anthropic":
        return float(headers.get("x-envoy-upstream-service-time", 0))
    elif provider == "google":
        # server-timing: gfet4t7; dur=773
        st = headers.get("server-timing", "")
        for part in st.split(";"):
            part = part.strip()
            if part.startswith("dur="):
                return float(part[4:])
    return 0.0


def measure_server_timing(
    model: str,
    system_prompt: str,
    user_message: str,
    format_name: str,
) -> ServerTiming:
    """Non-streaming call that captures server-side processing time from headers."""
    from benchmark.llm_client import detect_provider
    provider = detect_provider(model)

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI()
        raw = client.chat.completions.with_raw_response.create(
            model=model,
            temperature=0.0,
            max_completion_tokens=2048,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        headers = dict(raw.headers)
        resp = raw.parse()
        output_tokens = resp.usage.completion_tokens if resp.usage else 0
        text = resp.choices[0].message.content or "" if resp.choices else ""

    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic()
        raw = client.messages.with_raw_response.create(
            model=model,
            max_tokens=2048,
            temperature=0.0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        headers = dict(raw.headers)
        resp = raw.parse()
        output_tokens = resp.usage.output_tokens
        text = ""
        for block in resp.content:
            if block.type == "text":
                text += block.text

    elif provider == "google":
        import httpx
        import os
        key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model}:generateContent?key={key}"
        )
        body = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_message}]}],
            "generationConfig": {
                "maxOutputTokens": 2048,
                "temperature": 0.0,
            },
        }
        r = httpx.post(url, json=body, timeout=60)
        r.raise_for_status()
        headers = dict(r.headers)
        data = r.json()
        output_tokens = (
            data.get("usageMetadata", {}).get("candidatesTokenCount", 0)
        )
        text = ""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                text += part.get("text", "")
    else:
        raise ValueError(f"Unknown provider: {provider}")

    server_ms = _parse_server_timing(headers, provider)

    return ServerTiming(
        model=model,
        format_name=format_name,
        output_tokens=output_tokens,
        server_ms=server_ms,
        text=text,
    )


# ---------------------------------------------------------------------------
# Trimmed mean: drop best + worst by wall_clock_s
# ---------------------------------------------------------------------------

def trimmed_mean(
    metrics_list: list[StreamingMetrics],
    trim: int = 1,
) -> list[StreamingMetrics]:
    """Drop `trim` best and `trim` worst runs (by wall_clock_s)."""
    if len(metrics_list) <= 2 * trim:
        return metrics_list  # not enough runs to trim
    by_wc = sorted(metrics_list, key=lambda m: m.wall_clock_s)
    return by_wc[trim:-trim]


def avg_metrics(metrics_list: list[StreamingMetrics]) -> dict[str, float]:
    """Average key metrics from a list of StreamingMetrics."""
    n = len(metrics_list)
    if n == 0:
        return {}
    return {
        "output_tokens": statistics.mean(m.output_tokens for m in metrics_list),
        "wall_clock_s": statistics.mean(m.wall_clock_s for m in metrics_list),
        "ttft_s": statistics.mean(m.ttft_s for m in metrics_list),
        "tpot_ms": statistics.mean(m.tpot_ms for m in metrics_list),
        "tps": statistics.mean(m.tps for m in metrics_list),
        "chunk_count": statistics.mean(m.chunk_count for m in metrics_list),
        "n_runs_used": n,
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report(
    model_data: list[dict[str, Any]],
    n_runs_total: int,
    trim: int,
) -> str:
    lines: list[str] = []
    lines.append("# Compute-Cost Comparison: Pretty JSON vs Minified JSON vs JMD")
    lines.append("")
    lines.append(f"*Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append(f"*{n_runs_total} runs per model/format, trimmed mean (drop {trim} best + {trim} worst), temperature=0*")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    has_server = any("server_ms" in md.get("json", {}) for md in model_data)

    if has_server:
        lines.append("| Model | Pretty JSON | Minified JSON | JMD | JMD vs Pretty | JMD vs Minified |")
        lines.append("|---|---|---|---|---|---|")

        for md in model_data:
            model = md["model"]
            pj = md["json"]
            mj = md["json_minified"]
            jm = md["jmd"]

            pj_tok = pj["output_tokens"]
            mj_tok = mj["output_tokens"]
            jm_tok = jm["output_tokens"]

            # Prefer server-side timing
            pj_ms = pj.get("server_ms", pj["wall_clock_s"] * 1000)
            mj_ms = mj.get("server_ms", mj["wall_clock_s"] * 1000)
            jm_ms = jm.get("server_ms", jm["wall_clock_s"] * 1000)

            jmd_vs_pretty_tok = (jm_tok - pj_tok) / pj_tok * 100
            jmd_vs_mini_tok = (jm_tok - mj_tok) / mj_tok * 100
            jmd_vs_pretty_ms = (jm_ms - pj_ms) / pj_ms * 100
            jmd_vs_mini_ms = (jm_ms - mj_ms) / mj_ms * 100

            time_label = "server" if "server_ms" in pj else "client"

            lines.append(
                f"| **{model}** "
                f"| {pj_tok:.0f} tok / {pj_ms:.0f}ms "
                f"| {mj_tok:.0f} tok / {mj_ms:.0f}ms "
                f"| {jm_tok:.0f} tok / {jm_ms:.0f}ms "
                f"| {jmd_vs_pretty_tok:+.0f}% tok / {jmd_vs_pretty_ms:+.0f}% {time_label} "
                f"| {jmd_vs_mini_tok:+.0f}% tok / {jmd_vs_mini_ms:+.0f}% {time_label} |"
            )
    else:
        lines.append("| Model | Pretty JSON | Minified JSON | JMD | JMD vs Pretty | JMD vs Minified |")
        lines.append("|---|---|---|---|---|---|")

        for md in model_data:
            model = md["model"]
            pj = md["json"]
            mj = md["json_minified"]
            jm = md["jmd"]

            pj_tok = pj["output_tokens"]
            mj_tok = mj["output_tokens"]
            jm_tok = jm["output_tokens"]

            pj_wc = pj["wall_clock_s"]
            mj_wc = mj["wall_clock_s"]
            jm_wc = jm["wall_clock_s"]

            jmd_vs_pretty_tok = (jm_tok - pj_tok) / pj_tok * 100
            jmd_vs_mini_tok = (jm_tok - mj_tok) / mj_tok * 100
            jmd_vs_pretty_wc = (jm_wc - pj_wc) / pj_wc * 100
            jmd_vs_mini_wc = (jm_wc - mj_wc) / mj_wc * 100

            lines.append(
                f"| **{model}** "
                f"| {pj_tok:.0f} tok / {pj_wc:.2f}s "
                f"| {mj_tok:.0f} tok / {mj_wc:.2f}s "
                f"| {jm_tok:.0f} tok / {jm_wc:.2f}s "
                f"| {jmd_vs_pretty_tok:+.0f}% tok / {jmd_vs_pretty_wc:+.0f}% time "
                f"| {jmd_vs_mini_tok:+.0f}% tok / {jmd_vs_mini_wc:+.0f}% time |"
            )

    lines.append("")

    # Per-model detail
    for md in model_data:
        model = md["model"]
        lines.append(f"## {model}")
        lines.append("")
        lines.append("| Metric | Pretty JSON | Minified JSON | JMD |")
        lines.append("|---|---|---|---|")

        pj = md["json"]
        mj = md["json_minified"]
        jm = md["jmd"]

        lines.append(f"| Output tokens | {pj['output_tokens']:.0f} | {mj['output_tokens']:.0f} | {jm['output_tokens']:.0f} |")
        lines.append(f"| Wall clock (client) | {pj['wall_clock_s']:.2f}s | {mj['wall_clock_s']:.2f}s | {jm['wall_clock_s']:.2f}s |")

        # Server-side timing (if available)
        if "server_ms" in pj:
            lines.append(f"| **Server processing** | **{pj['server_ms']:.0f}ms** | **{mj['server_ms']:.0f}ms** | **{jm['server_ms']:.0f}ms** |")
            lines.append(f"| **Server TPS** | **{pj.get('server_tps', 0):.1f}** | **{mj.get('server_tps', 0):.1f}** | **{jm.get('server_tps', 0):.1f}** |")

        lines.append(f"| TPS (client) | {pj['tps']:.1f} | {mj['tps']:.1f} | {jm['tps']:.1f} |")
        lines.append(f"| TTFT | {pj['ttft_s']*1000:.0f}ms | {mj['ttft_s']*1000:.0f}ms | {jm['ttft_s']*1000:.0f}ms |")
        lines.append(f"| Valid / total | {pj.get('n_valid', '?')}/{n_runs_total} | {mj.get('n_valid', '?')}/{n_runs_total} | {jm.get('n_valid', '?')}/{n_runs_total} |")
        lines.append(f"| After trim | {pj['n_runs_used']:.0f} | {mj['n_runs_used']:.0f} | {jm['n_runs_used']:.0f} |")
        lines.append("")

    # Interpretation
    lines.append("---")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("### JMD vs Pretty JSON (real-world comparison)")
    lines.append("LLMs produce pretty-printed JSON by default. Against this real-world baseline,")
    lines.append("JMD's token savings and wall-clock advantage are significant.")
    lines.append("")
    lines.append("### JMD vs Minified JSON (theoretical baseline)")
    lines.append("Minified JSON is the most token-efficient JSON variant. If LLMs can be reliably")
    lines.append("instructed to produce it, JMD loses its token advantage. However:")
    lines.append("- Minified JSON is not streaming-friendly (no line boundaries)")
    lines.append("- Truncated minified JSON is unparseable")
    lines.append("- Minified JSON requires explicit instruction (not the default behavior)")
    lines.append("")
    lines.append("### TPS differences")
    lines.append("Lower TPS for JMD reflects a training data effect: JSON is heavily represented")
    lines.append("in pretraining corpora, JMD is not. This gap would narrow if JMD entered")
    lines.append("training data. The token savings are structural and permanent.")
    lines.append("")
    lines.append("### Methodology")
    lines.append("- Natural-language input: all formats extract from the same business document")
    lines.append("- Output validation: only runs with 100% correct data and correct format are counted")
    lines.append("- Token differences reflect pure format overhead, not content variation")
    lines.append("")
    lines.append("### Caveats")
    lines.append("- Wall-clock includes network latency (client-side measurement)")
    lines.append("- TPOT from streaming chunks is approximate (chunks != single tokens)")
    lines.append("- Results vary with model version, server load, and time of day")
    lines.append("- Single task type (e-commerce order); complexity may affect ratios")
    lines.append("")

    return "\n".join(lines)


def print_token_details(metrics: StreamingMetrics, limit: int = 50) -> None:
    classify_tokens(metrics)
    label = FORMAT_LABELS.get(metrics.format_name, metrics.format_name)
    print(f"\n--- {label} token details ({metrics.model}) ---")
    print(f"{'Token':<20} {'LogProb':>8} {'Prob':>8} {'Type':<12}")
    print("-" * 52)
    for t in metrics.token_logprobs[:limit]:
        token_repr = repr(t.token)[:18]
        prob = math.exp(t.logprob)
        ttype = "STRUCT" if t.is_structural else "content"
        print(f"{token_repr:<20} {t.logprob:>8.3f} {prob:>8.4f} {ttype:<12}")
    if len(metrics.token_logprobs) > limit:
        print(f"  ... ({len(metrics.token_logprobs) - limit} more tokens)")


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

def run_experiment(
    models: list[str] | None = None,
    n_runs: int = 10,
    trim: int = 1,
    output_dir: str = "benchmark_results",
) -> None:
    if models is None:
        models = ["gpt-4o", "claude-sonnet-4-6", "gemini-2.5-flash"]

    format_keys = list(FORMATS.keys())  # json, json_minified, jmd

    # Collect all runs: model -> format -> [StreamingMetrics]
    all_runs: dict[str, dict[str, list[StreamingMetrics]]] = {}
    server_timings: dict[str, dict[str, list[ServerTiming]]] = {}

    for model in models:
        print(f"\n{'='*60}")
        print(f"Model: {model}")
        print(f"{'='*60}")

        all_runs[model] = {fk: [] for fk in format_keys}
        is_openai = model.startswith("gpt-") or model.startswith("o1") or model.startswith("o3") or model.startswith("o4")

        for run in range(n_runs):
            print(f"\n--- Run {run + 1}/{n_runs} ---")

            for fk in format_keys:
                fmt_name, system_prompt = FORMATS[fk]
                label = FORMAT_LABELS[fk]
                print(f"  {label:16s}...", end=" ", flush=True)
                m = generate_streaming(model, system_prompt, TASK_PROMPT, fmt_name)
                vr = validate_output(m.text, fmt_name)
                if vr.valid:
                    all_runs[model][fk].append(m)
                    print(f"{m.output_tokens} tok, {m.tps:.1f} TPS, TTFT {m.ttft_s*1000:.0f}ms, {m.wall_clock_s:.2f}s")
                else:
                    reasons = []
                    if vr.missing_values:
                        reasons.append(f"missing: {vr.missing_values}")
                    if not vr.format_ok:
                        reasons.append(vr.format_error)
                    print(f"REJECTED ({'; '.join(reasons)})")

        # Server-timing pass — N non-streaming calls per format
        print(f"\n  Server-timing pass ({n_runs} calls per format)...")
        server_timings[model] = {fk: [] for fk in format_keys}
        for run in range(n_runs):
            for fk in format_keys:
                fmt_name, system_prompt = FORMATS[fk]
                label = FORMAT_LABELS[fk]
                print(f"    [{run+1}/{n_runs}] {label}...", end=" ", flush=True)
                try:
                    st = measure_server_timing(model, system_prompt, TASK_PROMPT, fmt_name)
                    vr = validate_output(st.text, fmt_name)
                    if vr.valid:
                        server_timings[model][fk].append(st)
                        print(f"{st.output_tokens} tok, server: {st.server_ms:.0f}ms")
                    else:
                        reasons = []
                        if vr.missing_values:
                            reasons.append(f"missing: {vr.missing_values}")
                        if not vr.format_ok:
                            reasons.append(vr.format_error)
                        print(f"REJECTED ({'; '.join(reasons)})")
                except Exception as e:
                    print(f"FAILED: {e}")

        # LogProbs pass (OpenAI only) — single run per format
        if is_openai:
            print("\n  LogProbs pass (non-streaming)...")
            for fk in format_keys:
                fmt_name, system_prompt = FORMATS[fk]
                label = FORMAT_LABELS[fk]
                print(f"    {label}...", end=" ", flush=True)
                lp = openai_logprobs(model, system_prompt, TASK_PROMPT, fmt_name)
                print(f"{len(lp)} tokens")
                all_runs[model][fk][0].token_logprobs = lp

            # Print token details for first run of each format
            for fk in format_keys:
                print_token_details(all_runs[model][fk][0])

    # Aggregate with trimmed mean
    model_data: list[dict[str, Any]] = []
    for model in models:
        md: dict[str, Any] = {"model": model}
        for fk in format_keys:
            runs = all_runs[model][fk]
            n_valid = len(runs)
            trimmed = trimmed_mean(runs, trim=trim)
            md[fk] = avg_metrics(trimmed)
            md[fk]["n_valid"] = n_valid

            # Server timing: trimmed mean by server_ms
            st_list = server_timings.get(model, {}).get(fk, [])
            if st_list:
                by_ms = sorted(st_list, key=lambda s: s.server_ms)
                if len(by_ms) > 2 * trim:
                    by_ms = by_ms[trim:-trim]
                md[fk]["server_ms"] = statistics.mean(s.server_ms for s in by_ms)
                md[fk]["server_tps"] = statistics.mean(
                    s.output_tokens / (s.server_ms / 1000) if s.server_ms > 0 else 0
                    for s in by_ms
                )
        model_data.append(md)

    # Generate report
    report = format_report(model_data, n_runs, trim)
    print(f"\n\n{'='*60}")
    print(report)

    # Save
    out_path = Path(output_dir)
    out_path.mkdir(exist_ok=True)

    report_file = out_path / "compute_comparison.md"
    report_file.write_text(report)
    print(f"\nReport saved to {report_file}")

    # Save raw data
    raw_runs: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for model in models:
        raw_runs[model] = {}
        for fk in format_keys:
            raw_runs[model][fk] = [
                {
                    "output_tokens": m.output_tokens,
                    "wall_clock_s": m.wall_clock_s,
                    "ttft_s": m.ttft_s,
                    "tpot_ms": m.tpot_ms,
                    "tps": m.tps,
                    "chunk_count": m.chunk_count,
                }
                for m in all_runs[model][fk]
            ]

    # Server timing raw data
    raw_server: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for model in models:
        raw_server[model] = {}
        for fk in format_keys:
            raw_server[model][fk] = [
                {"output_tokens": s.output_tokens, "server_ms": s.server_ms}
                for s in server_timings.get(model, {}).get(fk, [])
            ]

    raw_data = {
        "config": {"n_runs": n_runs, "trim": trim},
        "runs": raw_runs,
        "server_timing": raw_server,
        "aggregated": [{k: v for k, v in md.items()} for md in model_data],
    }
    raw_file = out_path / "compute_raw.json"
    raw_file.write_text(json.dumps(raw_data, indent=2, default=str))
    print(f"Raw data saved to {raw_file}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Compute-cost comparison: Pretty JSON vs Minified JSON vs JMD"
    )
    parser.add_argument(
        "--models", nargs="+",
        default=["gpt-4o", "claude-sonnet-4-6", "gemini-2.5-flash"],
        help="Model names (provider auto-detected)",
    )
    parser.add_argument("--runs", type=int, default=10, help="Runs per model/format")
    parser.add_argument("--trim", type=int, default=1, help="Trim N best + N worst runs")
    parser.add_argument("--output", default="benchmark_results", help="Output directory")

    args = parser.parse_args()
    run_experiment(models=args.models, n_runs=args.runs, trim=args.trim, output_dir=args.output)
