#!/usr/bin/env python3
"""Streaming chain benchmark — measures real TTFUB advantage in agentic workflows.

Compares two execution modes for a 3-step chain:
1. BATCH:     complete() → wait for full response → parse → next step
2. STREAMING: complete_streaming() → incremental parse → next step starts earlier

For JMD, streaming parse uses jmd_stream() which yields FIELD events line-by-line.
For JSON, streaming parse waits for complete json.loads() — no incremental parsing.

This directly measures the wall-clock advantage of JMD's streamability.

Usage:
    python -m benchmark.run_streaming_chain
    python -m benchmark.run_streaming_chain --n-runs 5
    python -m benchmark.run_streaming_chain --models sonnet
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmark.config import BenchmarkConfig
from benchmark.formats import get_format
from benchmark.llm_client import LLMClient, create_client, get_pricing
from benchmark.primers import get_primer
from benchmark.runner import count_tokens, extract_code_fence, try_parse, parse_safe
from benchmark.scenarios import ALL_SCENARIOS
from benchmark.scenarios.base import Scenario, SYSTEM_PROMPT_TEMPLATE, USER_MESSAGE_TEMPLATE

MODELS = ["claude-sonnet-4-6", "gpt-5.4", "mistral-large-latest"]
SHORT = {
    "claude-sonnet-4-6": "Sonnet", "gpt-5.4": "GPT-5.4",
    "mistral-large-latest": "Mistral",
}
FORMATS = ["json_pretty", "jmd"]


# ── TTFUB measurement ─────────────────────────────────────────────────────

def _extract_fence_content(accumulated: str, tag: str) -> str | None:
    """Extract content after ```<tag>\\n from accumulated text. Returns None if fence not found."""
    import re
    m = re.search(r"```" + re.escape(tag) + r"\s*\n", accumulated, re.IGNORECASE)
    if m:
        return accumulated[m.end():]
    return None


def _ttfub_jmd_streaming(chunks: list[tuple[str, float]]) -> float:
    """Time to first useful byte for JMD: first FIELD event from jmd_stream().

    JMD can yield fields incrementally — as soon as one heading + field line
    is complete, jmd_stream() yields a FIELD event. No need to wait for the
    closing fence.
    """
    from jmd import jmd_stream
    accumulated = ""
    for text, ts in chunks:
        accumulated += text
        # Extract content inside the code fence (```markdown ... )
        content = _extract_fence_content(accumulated, "markdown")
        if content is None:
            continue
        try:
            for event in jmd_stream(content):
                if event.type == "FIELD":
                    return ts
        except Exception:
            continue
    return chunks[-1][1] if chunks else 0.0


def _ttfub_json_streaming(chunks: list[tuple[str, float]]) -> float:
    """Time to first useful byte for JSON: first successful json.loads().

    JSON has no incremental parser — must wait for the complete closing brace
    AND the closing ``` fence.
    """
    import re
    accumulated = ""
    for text, ts in chunks:
        accumulated += text
        # Must find a COMPLETE fenced JSON block (opening + content + closing ```)
        m = re.search(r"```(?:json)?\s*\n(.*?)```", accumulated, re.DOTALL | re.IGNORECASE)
        if m:
            try:
                json.loads(m.group(1).strip())
                return ts
            except json.JSONDecodeError:
                continue
    return chunks[-1][1] if chunks else 0.0


# ── Step results ──────────────────────────────────────────────────────────

@dataclass
class StreamingStepResult:
    model: str
    step_name: str
    format_name: str
    mode: str                    # "batch" or "streaming"
    wall_clock_s: float          # total time for this step
    ttfub_s: float               # time to first useful byte (streaming only, 0 for batch)
    server_processing_ms: float
    input_tokens: int
    output_tokens: int
    syn_valid: bool
    sem_correct: bool
    sem_score: float


@dataclass
class StreamingChainResult:
    scenario: str
    model: str
    format_name: str
    mode: str
    run_id: int
    steps: list[StreamingStepResult]
    chain_complete: bool

    @property
    def total_wall_clock(self) -> float:
        return sum(s.wall_clock_s for s in self.steps)

    @property
    def total_server_ms(self) -> float:
        return sum(s.server_processing_ms for s in self.steps)

    @property
    def total_ttfub(self) -> float:
        return sum(s.ttfub_s for s in self.steps)

    @property
    def e2e_sem_score(self) -> float:
        active = [s for s in self.steps if s.syn_valid]
        if not active:
            return 0.0
        score = 1.0
        for s in active:
            score *= s.sem_score
        return score


def run_chain_batch(
    scenario: Scenario, model: str, client: LLMClient,
    fmt_key: str, run_id: int, seed: int,
) -> StreamingChainResult:
    """Execute chain in batch mode: complete() → parse → next step."""
    api = scenario.api
    api.reset(seed)
    fmt = get_format(fmt_key)
    primer = get_primer(fmt_key, "strict")
    carry_forward: dict = {}
    steps: list[StreamingStepResult] = []
    chain_broken = False
    config = BenchmarkConfig(model=model)

    structured = [s for s in scenario.steps if s.expects_structured][:3]

    for step in structured:
        if chain_broken:
            steps.append(StreamingStepResult(
                model=model, step_name=step.name, format_name=fmt_key,
                mode="batch", wall_clock_s=0, ttfub_s=0,
                server_processing_ms=0, input_tokens=0, output_tokens=0,
                syn_valid=False, sem_correct=False, sem_score=0,
            ))
            continue

        api_data = step.get_api_response(api, carry_forward)
        payload = fmt.serialize(api_data, step.label)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            format_primer=primer, scenario_instructions=step.system_prompt_extra,
            format_name=fmt.name, fence_tag=fmt.fence_tag,
        )
        user_msg = USER_MESSAGE_TEMPLATE.format(
            api_response=payload, format_name=fmt.name,
            fence_tag=fmt.fence_tag, step_instruction=step.user_message_template,
        )

        t0 = time.monotonic()
        result = client.complete(system_prompt, user_msg)
        # Parse
        extracted, _ = extract_code_fence(result.text, fmt.name)
        if extracted is None:
            extracted = result.text.strip()
        syn_ok, _ = try_parse(extracted, fmt)
        parsed = parse_safe(extracted, fmt) if syn_ok else None
        wall = time.monotonic() - t0

        from benchmark.metrics import ValidationResult
        sem = step.validator(parsed, api) if syn_ok else ValidationResult(False, 0.0, "parse failure")

        steps.append(StreamingStepResult(
            model=model, step_name=step.name, format_name=fmt_key,
            mode="batch", wall_clock_s=wall, ttfub_s=0,
            server_processing_ms=result.server_processing_ms,
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
            syn_valid=syn_ok, sem_correct=sem.valid, sem_score=sem.score,
        ))

        if syn_ok:
            carry_forward = step.extract_for_next(parsed)
        else:
            chain_broken = True

    return StreamingChainResult(
        scenario=scenario.name, model=model, format_name=fmt_key,
        mode="batch", run_id=run_id, steps=steps,
        chain_complete=not chain_broken,
    )


def run_chain_streaming(
    scenario: Scenario, model: str, client: LLMClient,
    fmt_key: str, run_id: int, seed: int,
) -> StreamingChainResult:
    """Execute chain in streaming mode: stream → incremental parse → next step."""
    api = scenario.api
    api.reset(seed)
    fmt = get_format(fmt_key)
    primer = get_primer(fmt_key, "strict")
    carry_forward: dict = {}
    steps: list[StreamingStepResult] = []
    chain_broken = False
    config = BenchmarkConfig(model=model)

    structured = [s for s in scenario.steps if s.expects_structured][:3]

    for step in structured:
        if chain_broken:
            steps.append(StreamingStepResult(
                model=model, step_name=step.name, format_name=fmt_key,
                mode="streaming", wall_clock_s=0, ttfub_s=0,
                server_processing_ms=0, input_tokens=0, output_tokens=0,
                syn_valid=False, sem_correct=False, sem_score=0,
            ))
            continue

        api_data = step.get_api_response(api, carry_forward)
        payload = fmt.serialize(api_data, step.label)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            format_primer=primer, scenario_instructions=step.system_prompt_extra,
            format_name=fmt.name, fence_tag=fmt.fence_tag,
        )
        user_msg = USER_MESSAGE_TEMPLATE.format(
            api_response=payload, format_name=fmt.name,
            fence_tag=fmt.fence_tag, step_instruction=step.user_message_template,
        )

        t0 = time.monotonic()
        result = client.complete_streaming(system_prompt, user_msg)
        wall = time.monotonic() - t0

        # Measure TTFUB from streaming chunks
        if fmt_key == "jmd":
            ttfub = _ttfub_jmd_streaming(result.chunks)
        else:
            ttfub = _ttfub_json_streaming(result.chunks)

        # Parse full response for semantics
        extracted, _ = extract_code_fence(result.text, fmt.name)
        if extracted is None:
            extracted = result.text.strip()
        syn_ok, _ = try_parse(extracted, fmt)
        parsed = parse_safe(extracted, fmt) if syn_ok else None

        from benchmark.metrics import ValidationResult
        sem = step.validator(parsed, api) if syn_ok else ValidationResult(False, 0.0, "parse failure")

        steps.append(StreamingStepResult(
            model=model, step_name=step.name, format_name=fmt_key,
            mode="streaming", wall_clock_s=wall, ttfub_s=ttfub,
            server_processing_ms=0,  # not available in streaming mode
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
            syn_valid=syn_ok, sem_correct=sem.valid, sem_score=sem.score,
        ))

        if syn_ok:
            carry_forward = step.extract_for_next(parsed)
        else:
            chain_broken = True

    return StreamingChainResult(
        scenario=scenario.name, model=model, format_name=fmt_key,
        mode="streaming", run_id=run_id, steps=steps,
        chain_complete=not chain_broken,
    )


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Streaming chain benchmark — TTFUB in agentic workflows")
    parser.add_argument("--n-runs", type=int, default=5)
    parser.add_argument("--models", type=str, default=None)
    parser.add_argument("--scenarios", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default="benchmark_results")
    args = parser.parse_args()

    if args.models:
        short_map = {"sonnet": "claude-sonnet-4-6", "gpt": "gpt-5.4", "mistral": "mistral-large-latest"}
        models = [short_map.get(m.strip(), m.strip()) for m in args.models.split(",")]
    else:
        models = list(MODELS)

    scenarios = ALL_SCENARIOS
    if args.scenarios:
        names = args.scenarios.split(",")
        scenarios = {k: v for k, v in ALL_SCENARIOS.items() if k in names}

    total = len(models) * len(FORMATS) * 2 * len(scenarios) * args.n_runs  # ×2 for batch+streaming
    print("=" * 75)
    print("  Streaming Chain Benchmark — TTFUB in Agentic Workflows")
    print("=" * 75)
    print(f"  Models:    {[SHORT.get(m, m) for m in models]}")
    print(f"  Formats:   {FORMATS}")
    print(f"  Scenarios: {list(scenarios.keys())}")
    print(f"  Runs:      {args.n_runs}")
    print(f"  Modes:     batch, streaming")
    print(f"  Total:     {total} chains")
    print()

    # Create clients
    clients: dict[str, LLMClient] = {}
    for model in models:
        clients[model] = create_client(model, temperature=0.0, max_tokens=4096)
        print(f"  Client ready: {SHORT.get(model, model)}")
    print()

    all_results: list[StreamingChainResult] = []
    t_start = time.monotonic()
    chain_num = 0

    for run_id in range(args.n_runs):
        for model in models:
            client = clients[model]
            for fmt_key in FORMATS:
                for sname, scenario in scenarios.items():
                    seed = 42 + run_id

                    # Batch mode
                    chain_num += 1
                    t0 = time.monotonic()
                    batch = run_chain_batch(scenario, model, client, fmt_key, run_id, seed)
                    elapsed = time.monotonic() - t0
                    all_results.append(batch)
                    status = "OK" if batch.chain_complete else "BROKEN"
                    print(
                        f"  [{chain_num:3d}/{total}] {SHORT.get(model,model):8s} "
                        f"{sname}/{fmt_key} BATCH    "
                        f"wall={batch.total_wall_clock:.1f}s {status}"
                    )

                    # Streaming mode
                    chain_num += 1
                    t0 = time.monotonic()
                    stream = run_chain_streaming(scenario, model, client, fmt_key, run_id, seed)
                    elapsed = time.monotonic() - t0
                    all_results.append(stream)
                    status = "OK" if stream.chain_complete else "BROKEN"
                    ttfub_sum = sum(s.ttfub_s for s in stream.steps if s.ttfub_s > 0)
                    print(
                        f"  [{chain_num:3d}/{total}] {SHORT.get(model,model):8s} "
                        f"{sname}/{fmt_key} STREAM   "
                        f"wall={stream.total_wall_clock:.1f}s ttfub_sum={ttfub_sum:.2f}s {status}"
                    )

    total_elapsed = time.monotonic() - t_start

    # ── Summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 75)
    print("  STREAMING CHAIN RESULTS")
    print("=" * 75)

    print(f"\n  {'Model':10s} {'Format':12s} {'Mode':10s} {'Wall (s)':>10s} {'TTFUB (s)':>10s} {'E2E sem':>8s} {'N':>4s}")
    print("  " + "-" * 70)

    for model in models:
        for fmt_key in FORMATS:
            for mode in ["batch", "streaming"]:
                chains = [r for r in all_results
                         if r.model == model and r.format_name == fmt_key
                         and r.mode == mode and r.chain_complete]
                if not chains:
                    continue
                n = len(chains)
                avg_wall = sum(r.total_wall_clock for r in chains) / n
                avg_ttfub = sum(r.total_ttfub for r in chains) / n
                avg_e2e = sum(r.e2e_sem_score for r in chains) / n
                print(
                    f"  {SHORT.get(model,model):10s} {fmt_key:12s} {mode:10s} "
                    f"{avg_wall:10.1f} {avg_ttfub:10.2f} {avg_e2e:8.3f} {n:4d}"
                )

    # ── TTFUB comparison ──────────────────────────────────────────────
    print(f"\n\n  TTFUB COMPARISON — When can the next step start?")
    print("  " + "-" * 70)
    print(f"  {'Model':10s} {'JSON TTFUB':>12s} {'JMD TTFUB':>12s} {'Speedup':>10s} {'JSON wall':>10s} {'JMD wall':>10s} {'Wall Δ':>8s}")
    print("  " + "-" * 70)

    for model in models:
        j_stream = [r for r in all_results if r.model == model
                    and r.format_name == "json_pretty" and r.mode == "streaming" and r.chain_complete]
        m_stream = [r for r in all_results if r.model == model
                    and r.format_name == "jmd" and r.mode == "streaming" and r.chain_complete]
        j_batch = [r for r in all_results if r.model == model
                   and r.format_name == "json_pretty" and r.mode == "batch" and r.chain_complete]
        m_batch = [r for r in all_results if r.model == model
                   and r.format_name == "jmd" and r.mode == "batch" and r.chain_complete]

        if not all([j_stream, m_stream]):
            continue

        j_ttfub = sum(r.total_ttfub for r in j_stream) / len(j_stream)
        m_ttfub = sum(r.total_ttfub for r in m_stream) / len(m_stream)
        speedup = j_ttfub / m_ttfub if m_ttfub > 0 else 0

        j_wall = sum(r.total_wall_clock for r in j_stream) / len(j_stream)
        m_wall = sum(r.total_wall_clock for r in m_stream) / len(m_stream)
        wall_d = (m_wall - j_wall) / j_wall * 100

        print(
            f"  {SHORT.get(model,model):10s} "
            f"{j_ttfub:11.2f}s {m_ttfub:11.2f}s {speedup:9.1f}× "
            f"{j_wall:9.1f}s {m_wall:9.1f}s {wall_d:+7.1f}%"
        )

    print(f"\n  Total wall clock: {total_elapsed:.0f}s ({total_elapsed/60:.1f}min)")

    # Save results
    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, "streaming_chain_results.json")
    save_data = []
    for r in all_results:
        save_data.append({
            "scenario": r.scenario, "model": r.model, "model_short": SHORT.get(r.model, r.model),
            "format": r.format_name, "mode": r.mode, "run_id": r.run_id,
            "chain_complete": r.chain_complete,
            "total_wall_clock_s": r.total_wall_clock,
            "total_ttfub_s": r.total_ttfub,
            "total_server_ms": r.total_server_ms,
            "e2e_sem_score": r.e2e_sem_score,
            "steps": [
                {
                    "step_name": s.step_name, "mode": s.mode,
                    "wall_clock_s": s.wall_clock_s, "ttfub_s": s.ttfub_s,
                    "server_processing_ms": s.server_processing_ms,
                    "input_tokens": s.input_tokens, "output_tokens": s.output_tokens,
                    "syn_valid": s.syn_valid, "sem_score": s.sem_score,
                }
                for s in r.steps
            ],
        })
    with open(out_path, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"  Results saved: {out_path}")


if __name__ == "__main__":
    main()
