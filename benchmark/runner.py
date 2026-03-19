"""Chain runner — executes scenarios step by step, collects metrics."""

from __future__ import annotations

import re
from typing import Any

import tiktoken

from .config import BenchmarkConfig
from .formats import Format, get_format
from .llm_client import LLMClient
from .metrics import (
    ChainResult,
    MetricsCollector,
    StepMetrics,
    StreamingMetrics,
    ValidationResult,
)
from .primers import get_primer
from .scenarios.base import Scenario, SYSTEM_PROMPT_TEMPLATE, USER_MESSAGE_TEMPLATE, USER_MESSAGE_TEMPLATE_FREETEXT

_TOKENIZER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_TOKENIZER.encode(text))


# ---------------------------------------------------------------------------
# Code fence extraction
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"```(?:json|jmd|markdown|yaml)\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_ANY_FENCE_RE = re.compile(r"```\w*\s*\n(.*?)```", re.DOTALL)


def extract_code_fence(text: str, format_name: str) -> tuple[str | None, str]:
    """Extract content from code fences, with fallbacks.

    Returns (extracted_text, method) where method is "exact", "any_fence", or "none".
    """
    # Try exact format fence
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip(), "exact"

    # Try any fence
    m = _ANY_FENCE_RE.search(text)
    if m:
        return m.group(1).strip(), "any_fence"

    return None, "none"


def try_parse(text: str, fmt: Format) -> tuple[bool, str]:
    """Try parsing, return (success, error_message)."""
    try:
        fmt.deserialize(text)
        return True, ""
    except Exception as e:
        return False, str(e)


def parse_safe(text: str, fmt: Format) -> Any:
    try:
        return fmt.deserialize(text)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Single chain execution
# ---------------------------------------------------------------------------

def run_chain(
    scenario: Scenario,
    fmt: Format,
    format_key: str,
    primer_variant: str,
    run_id: int,
    llm_client: LLMClient,
    config: BenchmarkConfig,
) -> ChainResult:
    """Execute a full scenario chain, return metrics."""
    api = scenario.api
    api.reset(config.get_seed(run_id))

    primer = get_primer(format_key, primer_variant)
    carry_forward: dict = {}
    step_metrics: list[StepMetrics] = []
    chain_broken = False

    for i, step in enumerate(scenario.steps):
        if chain_broken:
            step_metrics.append(StepMetrics(
                run_id=run_id, scenario=scenario.name,
                format_name=format_key, primer_variant=primer_variant,
                step_index=i, step_name=step.name,
                input_tokens=0, output_tokens=0,
                payload_bytes=0, payload_tokens=0,
                wall_clock_s=0.0, syn_valid=False,
                sem_correct=False, sem_score=0.0,
                cost_usd=0.0, skipped=True,
                model=config.model,
            ))
            continue

        # Build prompt
        api_data = step.get_api_response(api, carry_forward)
        payload = fmt.serialize(api_data, step.label)

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            format_primer=primer,
            scenario_instructions=step.system_prompt_extra,
            format_name=fmt.name,
            fence_tag=fmt.fence_tag,
        )

        template = USER_MESSAGE_TEMPLATE_FREETEXT if not step.expects_structured else USER_MESSAGE_TEMPLATE
        user_msg = template.format(
            api_response=payload,
            format_name=fmt.name,
            fence_tag=fmt.fence_tag,
            step_instruction=step.user_message_template,
        )

        # Call LLM
        result = llm_client.complete(system_prompt, user_msg)

        # Parse response
        if step.expects_structured:
            extracted, fence_method = extract_code_fence(result.text, fmt.name)
            if extracted is None:
                extracted = result.text.strip()
            syn_ok, parse_error = try_parse(extracted, fmt)
            parsed = parse_safe(extracted, fmt) if syn_ok else None
        else:
            # Free-text response (summary steps)
            extracted = result.text.strip()
            fence_method = "freetext"
            syn_ok = True
            parse_error = ""
            parsed = extracted

        # Validate
        sem_result = step.validator(parsed, api) if syn_ok else ValidationResult(False, 0.0, "parse failure")

        cost = config.cost_usd(result.input_tokens, result.output_tokens)

        step_metrics.append(StepMetrics(
            run_id=run_id, scenario=scenario.name,
            format_name=format_key, primer_variant=primer_variant,
            step_index=i, step_name=step.name,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            payload_bytes=len(payload.encode("utf-8")),
            payload_tokens=count_tokens(payload),
            wall_clock_s=result.wall_clock_s,
            server_processing_ms=result.server_processing_ms,
            syn_valid=syn_ok, sem_correct=sem_result.valid,
            sem_score=sem_result.score, cost_usd=cost,
            raw_output=result.text,
            extracted_text=extracted,
            fence_method=fence_method,
            parse_error=parse_error,
            sem_reason=sem_result.reason,
            model=config.model,
        ))

        # Carry forward or break
        if syn_ok and step.expects_structured:
            carry_forward = step.extract_for_next(parsed)
        elif not syn_ok:
            chain_broken = True

    return ChainResult(
        scenario=scenario.name,
        format_name=format_key,
        primer_variant=primer_variant,
        run_id=run_id,
        steps=step_metrics,
    )


# ---------------------------------------------------------------------------
# Dry-run (no LLM calls)
# ---------------------------------------------------------------------------

def dry_run_chain(
    scenario: Scenario,
    fmt: Format,
    format_key: str,
    primer_variant: str,
    run_id: int,
    config: BenchmarkConfig,
) -> None:
    """Print prompts and expected payloads without calling the LLM."""
    api = scenario.api
    api.reset(config.get_seed(run_id))

    primer = get_primer(format_key, primer_variant)
    carry_forward: dict = {}

    print(f"\n{'='*70}")
    print(f"DRY RUN: {scenario.name} | {format_key} | primer={primer_variant} | run={run_id}")
    print(f"{'='*70}")

    for i, step in enumerate(scenario.steps):
        api_data = step.get_api_response(api, carry_forward)
        payload = fmt.serialize(api_data, step.label)

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            format_primer=primer,
            scenario_instructions=step.system_prompt_extra,
            format_name=fmt.name,
            fence_tag=fmt.fence_tag,
        )

        template = USER_MESSAGE_TEMPLATE_FREETEXT if not step.expects_structured else USER_MESSAGE_TEMPLATE
        user_msg = template.format(
            api_response=payload,
            format_name=fmt.name,
            fence_tag=fmt.fence_tag,
            step_instruction=step.user_message_template,
        )

        payload_tokens = count_tokens(payload)
        system_tokens = count_tokens(system_prompt)
        user_tokens = count_tokens(user_msg)

        print(f"\n--- Step {i+1}: {step.name} ---")
        print(f"  Payload: {len(payload)} bytes, {payload_tokens} tokens")
        print(f"  System prompt: {system_tokens} tokens")
        print(f"  User message: {user_tokens} tokens")
        print(f"  Total input estimate: {system_tokens + user_tokens} tokens")
        print(f"  Payload preview ({fmt.name}):")
        preview = payload[:500]
        if len(payload) > 500:
            preview += "\n... (truncated)"
        for line in preview.split("\n"):
            print(f"    {line}")

        # Simulate carry-forward with expected answers
        if step.expects_structured:
            # Use expected answers for carry-forward in dry run
            if scenario.name == "ecommerce" and i == 0:
                carry_forward = {"top3_ids": api.get_expected_top3() if hasattr(api, "get_expected_top3") else []}
            elif scenario.name == "ecommerce" and i == 1:
                carry_forward = {"best_product_id": api.get_expected_best_available() if hasattr(api, "get_expected_best_available") else None}
            else:
                carry_forward = {}


# ---------------------------------------------------------------------------
# TTFUB streaming measurement
# ---------------------------------------------------------------------------

def measure_ttfub(
    scenario: Scenario,
    fmt: Format,
    format_key: str,
    primer_variant: str,
    run_id: int,
    llm_client: LLMClient,
    config: BenchmarkConfig,
) -> StreamingMetrics | None:
    """Measure time-to-first-useful-byte via streaming.

    Uses jmd_stream() for JMD and ijson for JSON (assessment feedback).
    """
    api = scenario.api
    api.reset(config.get_seed(run_id))

    # Use step 0 (largest payload)
    step = scenario.steps[0]
    api_data = step.get_api_response(api, {})
    payload = fmt.serialize(api_data, step.label)

    primer = get_primer(format_key, primer_variant)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        format_primer=primer,
        scenario_instructions=step.system_prompt_extra,
        format_name=fmt.name,
        fence_tag=fmt.fence_tag,
    )
    user_msg = USER_MESSAGE_TEMPLATE.format(
        api_response=payload,
        format_name=fmt.name,
        fence_tag=fmt.fence_tag,
        step_instruction=step.user_message_template,
    )

    result = llm_client.complete_streaming(system_prompt, user_msg)

    if not result.chunks:
        return None

    # Measure TTFUB based on format
    ttfub = _compute_ttfub(result.chunks, format_key)

    return StreamingMetrics(
        scenario=scenario.name,
        format_name=format_key,
        run_id=run_id,
        step_name=step.name,
        total_time_s=result.wall_clock_s,
        ttfub_s=ttfub,
    )


def _compute_ttfub(chunks: list[tuple[str, float]], format_key: str) -> float:
    """Compute TTFUB from streaming chunks."""
    if format_key == "jmd":
        return _ttfub_jmd(chunks)
    elif format_key == "yaml":
        return _ttfub_yaml(chunks)
    else:
        return _ttfub_json(chunks)


def _ttfub_jmd(chunks: list[tuple[str, float]]) -> float:
    """TTFUB for JMD: first FIELD event from jmd_stream()."""
    import sys
    from pathlib import Path
    repo = str(Path(__file__).resolve().parent.parent)
    if repo not in sys.path:
        sys.path.insert(0, repo)
    from jmd import jmd_stream

    accumulated = ""
    for text, ts in chunks:
        accumulated += text
        # Feed accumulated text to streaming parser
        try:
            for event in jmd_stream(accumulated):
                if event.type == "FIELD":
                    return ts
        except Exception:
            continue
    # Fallback: first chunk timestamp
    return chunks[0][1] if chunks else 0.0


def _ttfub_yaml(chunks: list[tuple[str, float]]) -> float:
    """TTFUB for YAML: first successful key-value parse from yaml.safe_load()."""
    import yaml

    accumulated = ""
    for text, ts in chunks:
        accumulated += text
        try:
            parsed = yaml.safe_load(accumulated)
            if isinstance(parsed, dict) and parsed:
                return ts
            if isinstance(parsed, list) and parsed:
                return ts
        except Exception:
            continue
    return chunks[-1][1] if chunks else 0.0


def _ttfub_json(chunks: list[tuple[str, float]]) -> float:
    """TTFUB for JSON: first key-value from ijson incremental parser.

    Assessment feedback: use ijson instead of json.loads() accumulation.
    """
    try:
        import ijson
    except ImportError:
        # Fallback: first successful json.loads
        import json
        accumulated = ""
        for text, ts in chunks:
            accumulated += text
            try:
                json.loads(accumulated)
                return ts
            except json.JSONDecodeError:
                continue
        return chunks[-1][1] if chunks else 0.0

    import io

    accumulated = ""
    for text, ts in chunks:
        accumulated += text
        # Try incremental parse
        try:
            buf = io.BytesIO(accumulated.encode("utf-8"))
            for prefix, event, value in ijson.parse(buf):
                if event in ("string", "number", "boolean", "null"):
                    return ts
        except Exception:
            continue

    return chunks[-1][1] if chunks else 0.0


# ---------------------------------------------------------------------------
# Main benchmark orchestrator
# ---------------------------------------------------------------------------

def run_benchmark(
    config: BenchmarkConfig,
    scenarios: dict[str, Scenario],
    collector: MetricsCollector,
    llm_client: LLMClient,
    dry_run: bool = False,
    streaming_only: bool = False,
    primer_test_only: bool = False,
) -> None:
    """Run the full benchmark suite."""
    formats = {k: get_format(k) for k in config.formats}
    total_chains = len(scenarios) * len(formats) * config.n_runs

    if dry_run:
        # One chain per scenario/format
        for sname, scenario in scenarios.items():
            for fkey, fmt in formats.items():
                dry_run_chain(scenario, fmt, fkey, config.primer_default, 0, config)
        return

    if streaming_only:
        _run_streaming(config, scenarios, formats, collector, llm_client)
        return

    if primer_test_only:
        _run_primer_test(config, scenarios, formats, collector, llm_client)
        return

    # --- Main benchmark: interleaved runs ---
    print(f"\nMain benchmark: {total_chains} chains "
          f"({len(scenarios)} scenarios × {len(formats)} formats × {config.n_runs} runs)")

    chain_num = 0
    for run_id in range(config.n_runs):
        for fkey, fmt in formats.items():
            for sname, scenario in scenarios.items():
                chain_num += 1
                print(f"  [{chain_num}/{total_chains}] "
                      f"{sname}/{fkey} run={run_id} ...", end="", flush=True)

                result = run_chain(
                    scenario, fmt, fkey, config.primer_default,
                    run_id, llm_client, config,
                )
                collector.record_chain(result)

                status = "OK" if result.complete else "BROKEN"
                tokens = result.total_tokens
                print(f" {status} ({tokens} tokens, ${result.total_cost:.4f})")

    # --- Primer comparison ---
    _run_primer_test(config, scenarios, formats, collector, llm_client)

    # --- Streaming TTFUB ---
    try:
        _run_streaming(config, scenarios, formats, collector, llm_client)
    except Exception as e:
        print(f"\nStreaming TTFUB aborted: {e}")


def _run_primer_test(
    config: BenchmarkConfig,
    scenarios: dict[str, Scenario],
    formats: dict[str, Format],
    collector: MetricsCollector,
    llm_client: LLMClient,
) -> None:
    """Test primer variants on e-commerce scenario only."""
    if "jmd" not in formats or "ecommerce" not in scenarios:
        return

    fmt = formats["jmd"]
    scenario = scenarios["ecommerce"]
    n = config.primer_test_n

    print(f"\nPrimer comparison: {len(config.primer_variants)} variants × {n} runs")
    for variant in config.primer_variants:
        if variant == config.primer_default:
            continue  # already tested in main run
        for run_id in range(n):
            print(f"  primer={variant} run={run_id} ...", end="", flush=True)
            result = run_chain(
                scenario, fmt, "jmd", variant,
                run_id, llm_client, config,
            )
            collector.record_chain(result)
            status = "OK" if result.complete else "BROKEN"
            print(f" {status}")


def _run_streaming(
    config: BenchmarkConfig,
    scenarios: dict[str, Scenario],
    formats: dict[str, Format],
    collector: MetricsCollector,
    llm_client: LLMClient,
) -> None:
    """TTFUB streaming measurements."""
    total = len(scenarios) * len(formats) * config.streaming_runs
    print(f"\nStreaming TTFUB: {total} runs")

    for run_id in range(config.streaming_runs):
        for fkey, fmt in formats.items():
            for sname, scenario in scenarios.items():
                print(f"  TTFUB {sname}/{fkey} run={run_id} ...", end="", flush=True)
                sm = measure_ttfub(
                    scenario, fmt, fkey, config.primer_default,
                    run_id, llm_client, config,
                )
                if sm:
                    collector.record_streaming(sm)
                    print(f" TTFUB={sm.ttfub_s:.3f}s total={sm.total_time_s:.3f}s")
                else:
                    print(" SKIP (no chunks)")
