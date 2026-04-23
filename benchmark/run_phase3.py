#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Phase 3 benchmark — Agentic multi-model chain.

Measures the real-world advantage of JMD in agentic workflows:
- Server processing time across a 3-LLM chain
- Parse latency (client-side)
- Epistemic frontmatter (confidence, uncertain, source) — JMD only
- End-to-end semantic fidelity across the chain
- Correlation between self-reported confidence and actual correctness

Three LLMs are chained: output of LLM₁ → parse → input of LLM₂ → parse → input of LLM₃.
All 6 permutations of (Sonnet, GPT-5.4, Gemini 2.5 Pro) are tested.

Usage:
    python -m benchmark.run_phase3
    python -m benchmark.run_phase3 --n-runs 3          # quick test
    python -m benchmark.run_phase3 --scenarios ecommerce
    python -m benchmark.run_phase3 --dry-run
"""

from __future__ import annotations

import argparse
import itertools
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
from benchmark.formats import Format, get_format
from benchmark.llm_client import LLMClient, create_client, get_pricing
from benchmark.primers import get_primer
from benchmark.runner import count_tokens, extract_code_fence, try_parse, parse_safe
from benchmark.scenarios import ALL_SCENARIOS
from benchmark.scenarios.base import Scenario, SYSTEM_PROMPT_TEMPLATE, USER_MESSAGE_TEMPLATE

# ── Models ──────────────────────────────────────────────────────────────────

PHASE3_MODELS = [
    "claude-sonnet-4-6",
    "gpt-5.4",
    "mistral-large-latest",
]

SHORT_NAMES = {
    "claude-sonnet-4-6": "Sonnet",
    "gpt-5.4": "GPT-5.4",
    "mistral-large-latest": "Mistral",
    "gemini-2.5-flash": "Gemini-Flash",
}

PHASE3_FORMATS = ["json_pretty", "jmd"]

# ── Epistemic JMD primer ───────────────────────────────────────────────────

EPISTEMIC_PRIMER_SUFFIX = """

Epistemic frontmatter: Before the root heading, add metadata lines:
- confidence: high | medium | low | speculative
- source: describe data provenance (e.g., "product database", "inference from step 1")
- uncertain: comma-separated field names you consider less reliable

Example:
confidence: high
source: product database
uncertain: estimated_delivery

# Product
id: PROD-42
name: Widget Pro
estimated_delivery: 3-5 days"""

# ── Confidence mapping ──────────────────────────────────────────────────────

CONFIDENCE_SCORES = {
    "high": 1.0,
    "medium": 0.66,
    "low": 0.33,
    "speculative": 0.1,
}

# ── Result dataclasses ─────────────────────────────────────────────────────

@dataclass
class StepResult:
    model: str
    step_index: int
    step_name: str
    input_tokens: int
    output_tokens: int
    payload_tokens: int
    server_processing_ms: float
    wall_clock_s: float
    parse_time_ms: float
    syn_valid: bool
    sem_correct: bool
    sem_score: float
    cost_usd: float
    fence_method: str
    sem_reason: str
    # Epistemic frontmatter (JMD only)
    confidence: str = ""           # "high", "medium", "low", "speculative", or ""
    confidence_score: float = -1.0 # numeric mapping, -1 = not provided
    uncertain_fields: list[str] | None = None
    source: str = ""
    # Error provenance
    error_origin: str = ""         # "format" or "model" or ""


@dataclass
class ChainResult:
    scenario: str
    format_name: str
    permutation: list[str]
    run_id: int
    steps: list[StepResult]
    chain_complete: bool
    e2e_sem_score: float = 0.0     # end-to-end semantic score

    @property
    def total_server_ms(self) -> float:
        return sum(s.server_processing_ms for s in self.steps)

    @property
    def total_parse_ms(self) -> float:
        return sum(s.parse_time_ms for s in self.steps)

    @property
    def total_wall_clock_s(self) -> float:
        return sum(s.wall_clock_s for s in self.steps)

    @property
    def total_tokens(self) -> int:
        return sum(s.input_tokens + s.output_tokens for s in self.steps)

    @property
    def total_cost(self) -> float:
        return sum(s.cost_usd for s in self.steps)

    @property
    def avg_confidence_score(self) -> float:
        scores = [s.confidence_score for s in self.steps if s.confidence_score >= 0]
        return sum(scores) / len(scores) if scores else -1.0


# ── Frontmatter extraction ─────────────────────────────────────────────────

def extract_frontmatter(text: str, format_key: str) -> dict[str, Any]:
    """Extract epistemic frontmatter from a JMD response.

    Returns dict with keys: confidence, confidence_score, uncertain_fields, source.
    For non-JMD formats, returns empty/default values.
    """
    result: dict[str, Any] = {
        "confidence": "",
        "confidence_score": -1.0,
        "uncertain_fields": None,
        "source": "",
    }
    if format_key != "jmd":
        return result

    try:
        from jmd import JMDParser
        parser = JMDParser()
        parser.parse(text)
        fm = parser.frontmatter

        if "confidence" in fm:
            conf = str(fm["confidence"]).lower().strip()
            result["confidence"] = conf
            result["confidence_score"] = CONFIDENCE_SCORES.get(conf, -1.0)

        if "uncertain" in fm:
            raw = str(fm["uncertain"])
            result["uncertain_fields"] = [f.strip() for f in raw.split(",") if f.strip()]

        if "source" in fm:
            result["source"] = str(fm["source"])

    except Exception:
        pass  # frontmatter extraction is best-effort

    return result


def classify_error(syn_ok: bool, sem_correct: bool, fence_method: str) -> str:
    """Classify where an error originated: format-level or model-level."""
    if syn_ok and sem_correct:
        return ""
    if not syn_ok:
        return "format"   # parse failure — format/syntax issue
    return "model"         # parsed OK but semantically wrong — model's fault


# ── Chain execution ─────────────────────────────────────────────────────────

def run_agentic_chain(
    scenario: Scenario,
    fmt: Format,
    format_key: str,
    permutation: list[str],
    clients: dict[str, LLMClient],
    run_id: int,
    seed: int,
) -> ChainResult:
    """Execute a 3-step chain with a different LLM at each step."""
    api = scenario.api
    api.reset(seed)

    # For JMD: append epistemic primer instructions
    base_primer = get_primer(format_key, "strict")
    if format_key == "jmd":
        primer = base_primer + EPISTEMIC_PRIMER_SUFFIX
    else:
        primer = base_primer

    carry_forward: dict = {}
    step_results: list[StepResult] = []
    chain_broken = False

    # Use first 3 structured steps
    structured_steps = [s for s in scenario.steps if s.expects_structured][:3]

    for i, step in enumerate(structured_steps):
        model = permutation[i]
        client = clients[model]
        config = BenchmarkConfig(model=model)

        if chain_broken:
            step_results.append(StepResult(
                model=model, step_index=i, step_name=step.name,
                input_tokens=0, output_tokens=0, payload_tokens=0,
                server_processing_ms=0.0, wall_clock_s=0.0, parse_time_ms=0.0,
                syn_valid=False, sem_correct=False, sem_score=0.0,
                cost_usd=0.0, fence_method="skipped", sem_reason="chain broken",
                error_origin="propagated",
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
        user_msg = USER_MESSAGE_TEMPLATE.format(
            api_response=payload,
            format_name=fmt.name,
            fence_tag=fmt.fence_tag,
            step_instruction=step.user_message_template,
        )

        # Call LLM
        result = client.complete(system_prompt, user_msg)

        # Parse response — measure parse time
        t_parse = time.monotonic()
        extracted, fence_method = extract_code_fence(result.text, fmt.name)
        if extracted is None:
            extracted = result.text.strip()
        syn_ok, parse_error = try_parse(extracted, fmt)
        parsed = parse_safe(extracted, fmt) if syn_ok else None
        parse_time_ms = (time.monotonic() - t_parse) * 1000

        # Extract epistemic frontmatter (JMD only)
        fm = extract_frontmatter(extracted, format_key) if syn_ok else {
            "confidence": "", "confidence_score": -1.0,
            "uncertain_fields": None, "source": "",
        }

        # Validate
        from benchmark.metrics import ValidationResult
        sem_result = step.validator(parsed, api) if syn_ok else ValidationResult(False, 0.0, "parse failure")

        # Classify error origin
        error_origin = classify_error(syn_ok, sem_result.valid, fence_method)

        cost = config.cost_usd(result.input_tokens, result.output_tokens)

        step_results.append(StepResult(
            model=model, step_index=i, step_name=step.name,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            payload_tokens=count_tokens(payload),
            server_processing_ms=result.server_processing_ms,
            wall_clock_s=result.wall_clock_s,
            parse_time_ms=parse_time_ms,
            syn_valid=syn_ok, sem_correct=sem_result.valid,
            sem_score=sem_result.score, cost_usd=cost,
            fence_method=fence_method, sem_reason=sem_result.reason,
            confidence=fm["confidence"],
            confidence_score=fm["confidence_score"],
            uncertain_fields=fm["uncertain_fields"],
            source=fm["source"],
            error_origin=error_origin,
        ))

        # Carry forward or break
        if syn_ok:
            carry_forward = step.extract_for_next(parsed)
        else:
            chain_broken = True

    # End-to-end semantic score: product of per-step scores
    # Reflects compounding — a 0.8 × 0.9 × 0.7 chain = 0.504 overall
    active_steps = [s for s in step_results if s.fence_method != "skipped"]
    if active_steps:
        e2e = 1.0
        for s in active_steps:
            e2e *= s.sem_score
    else:
        e2e = 0.0

    return ChainResult(
        scenario=scenario.name,
        format_name=format_key,
        permutation=list(permutation),
        run_id=run_id,
        steps=step_results,
        chain_complete=not chain_broken,
        e2e_sem_score=e2e,
    )


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3: Agentic multi-model chain benchmark")
    parser.add_argument("--n-runs", type=int, default=5)
    parser.add_argument("--models", type=str, default=None,
                        help="Comma-separated model IDs (default: sonnet,gpt-5.4,gemini)")
    parser.add_argument("--formats", type=str, default=None)
    parser.add_argument("--scenarios", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default="benchmark_results")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Resolve models
    if args.models:
        short_map = {
            "sonnet": "claude-sonnet-4-6",
            "gpt": "gpt-5.4",
            "mistral": "mistral-large-latest",
            "gemini": "gemini-2.5-flash",
        }
        models = [short_map.get(m.strip(), m.strip()) for m in args.models.split(",")]
    else:
        models = list(PHASE3_MODELS)

    formats = args.formats.split(",") if args.formats else list(PHASE3_FORMATS)

    scenarios = ALL_SCENARIOS
    if args.scenarios:
        names = args.scenarios.split(",")
        scenarios = {k: v for k, v in ALL_SCENARIOS.items() if k in names}

    # All permutations of model ordering
    permutations = list(itertools.permutations(models))

    total_chains = len(permutations) * len(formats) * len(scenarios) * args.n_runs
    print("=" * 70)
    print("Phase 3 Benchmark — Agentic Multi-Model Chain")
    print("=" * 70)
    print(f"  Models:       {[SHORT_NAMES.get(m, m) for m in models]}")
    print(f"  Permutations: {len(permutations)}")
    print(f"  Formats:      {formats}")
    print(f"  Scenarios:    {list(scenarios.keys())}")
    print(f"  Runs:         {args.n_runs}")
    print(f"  Total:        {total_chains} chains")
    print()

    # Show permutations
    for i, perm in enumerate(permutations):
        names = [SHORT_NAMES.get(m, m) for m in perm]
        print(f"  P{i+1}: {' → '.join(names)}")
    print()

    # Cost estimate
    est_total = 0.0
    for model in models:
        inp, out = get_pricing(model)
        steps_per_model = total_chains
        est = steps_per_model * (2000 * inp + 800 * out) / 1_000_000
        est_total += est
        print(f"  {SHORT_NAMES.get(model, model):12s}  ~${est:.2f}")
    print(f"  {'TOTAL':12s}  ~${est_total:.2f}")
    print()

    if args.dry_run:
        print("DRY RUN — no API calls.")
        return

    # Create clients (one per model, reused across permutations)
    clients: dict[str, LLMClient] = {}
    for model in models:
        clients[model] = create_client(model, temperature=0.0, max_tokens=4096)
        print(f"  Client ready: {SHORT_NAMES.get(model, model)}")
    print()

    # Run all chains
    all_results: list[ChainResult] = []
    t_start = time.monotonic()
    chain_num = 0

    for run_id in range(args.n_runs):
        for perm in permutations:
            for fkey in formats:
                fmt = get_format(fkey)
                for sname, scenario in scenarios.items():
                    chain_num += 1
                    perm_names = [SHORT_NAMES.get(m, m) for m in perm]
                    label = "→".join(perm_names)

                    t0 = time.monotonic()
                    result = run_agentic_chain(
                        scenario, fmt, fkey, list(perm),
                        clients, run_id, seed=42 + run_id,
                    )
                    elapsed = time.monotonic() - t0
                    all_results.append(result)

                    status = "OK" if result.chain_complete else "BROKEN"
                    srv_ms = result.total_server_ms
                    conf = result.avg_confidence_score
                    conf_str = f"conf={conf:.2f}" if conf >= 0 else "conf=n/a"
                    print(
                        f"  [{chain_num:3d}/{total_chains}] "
                        f"{label} {sname}/{fkey} run={run_id} "
                        f"srv={srv_ms:.0f}ms e2e={result.e2e_sem_score:.2f} "
                        f"{conf_str} {elapsed:.1f}s ${result.total_cost:.4f} {status}"
                    )

    total_elapsed = time.monotonic() - t_start

    # ── Summary ─────────────────────────────────────────────────────────
    _print_summary(all_results, formats, permutations, total_elapsed)

    # Save results
    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, "phase3_results.json")
    _save_results(all_results, out_path)
    print(f"\n  Results saved: {out_path}")


def _print_summary(
    all_results: list[ChainResult],
    formats: list[str],
    permutations: list[tuple],
    total_elapsed: float,
) -> None:
    print("\n" + "=" * 70)
    print("PHASE 3 RESULTS")
    print("=" * 70)

    # ── Per-format summary ──────────────────────────────────────────────
    for fkey in formats:
        chains = [r for r in all_results if r.format_name == fkey]
        complete = [r for r in chains if r.chain_complete]
        n = len(chains)
        n_ok = len(complete)
        if not complete:
            print(f"\n  {fkey}: {n} chains, {n_ok} complete — no data")
            continue

        avg_srv = sum(r.total_server_ms for r in complete) / n_ok
        avg_parse = sum(r.total_parse_ms for r in complete) / n_ok
        avg_wall = sum(r.total_wall_clock_s for r in complete) / n_ok
        avg_tokens = sum(r.total_tokens for r in complete) / n_ok
        avg_e2e = sum(r.e2e_sem_score for r in complete) / n_ok
        total_cost = sum(r.total_cost for r in chains)

        print(f"\n  {fkey.upper()}: {n_ok}/{n} chains complete")
        print(f"    Avg server time:    {avg_srv:8.0f} ms")
        print(f"    Avg parse time:     {avg_parse:8.1f} ms")
        print(f"    Avg wall clock:     {avg_wall:8.1f} s")
        print(f"    Avg tokens:         {avg_tokens:8.0f}")
        print(f"    Avg E2E sem score:  {avg_e2e:8.3f}")
        print(f"    Total cost:         ${total_cost:7.2f}")

    # ── Delta: JMD vs JSON ──────────────────────────────────────────────
    json_chains = [r for r in all_results if r.format_name == "json_pretty" and r.chain_complete]
    jmd_chains = [r for r in all_results if r.format_name == "jmd" and r.chain_complete]
    if json_chains and jmd_chains:
        json_srv = sum(r.total_server_ms for r in json_chains) / len(json_chains)
        jmd_srv = sum(r.total_server_ms for r in jmd_chains) / len(jmd_chains)
        json_tok = sum(r.total_tokens for r in json_chains) / len(json_chains)
        jmd_tok = sum(r.total_tokens for r in jmd_chains) / len(jmd_chains)
        json_e2e = sum(r.e2e_sem_score for r in json_chains) / len(json_chains)
        jmd_e2e = sum(r.e2e_sem_score for r in jmd_chains) / len(jmd_chains)

        print("\n  DELTA (JMD vs JSON):")
        print(f"    Server time:    {jmd_srv - json_srv:+.0f} ms ({(jmd_srv/json_srv - 1)*100:+.1f}%)")
        print(f"    Tokens:         {jmd_tok - json_tok:+.0f} ({(jmd_tok/json_tok - 1)*100:+.1f}%)")
        print(f"    E2E sem score:  {jmd_e2e:.3f} vs {json_e2e:.3f} ({(jmd_e2e/json_e2e - 1)*100:+.1f}%)" if json_e2e > 0 else "")

    # ── Epistemic frontmatter analysis (JMD only) ──────────────────────
    jmd_steps = [s for r in all_results if r.format_name == "jmd" for s in r.steps if s.fence_method != "skipped"]
    if jmd_steps:
        with_conf = [s for s in jmd_steps if s.confidence != ""]
        adoption_rate = len(with_conf) / len(jmd_steps) * 100

        print("\n  EPISTEMIC FRONTMATTER (JMD only):")
        print(f"    Adoption rate:  {len(with_conf)}/{len(jmd_steps)} steps ({adoption_rate:.0f}%)")

        if with_conf:
            # Confidence distribution
            from collections import Counter
            dist = Counter(s.confidence for s in with_conf)
            print(f"    Distribution:   {dict(dist)}")

            # Correlation: confidence vs actual sem_score
            print(f"\n    {'Confidence':14s} {'Count':>6s} {'Avg sem_score':>14s} {'Avg actual':>11s}")
            print("    " + "-" * 50)
            for level in ["high", "medium", "low", "speculative"]:
                steps_at_level = [s for s in with_conf if s.confidence == level]
                if steps_at_level:
                    avg_sem = sum(s.sem_score for s in steps_at_level) / len(steps_at_level)
                    avg_conf = CONFIDENCE_SCORES[level]
                    print(f"    {level:14s} {len(steps_at_level):6d} {avg_conf:14.2f} {avg_sem:11.3f}")

            # Uncertain field analysis
            with_uncertain = [s for s in with_conf if s.uncertain_fields]
            if with_uncertain:
                all_uncertain = [f for s in with_uncertain for f in s.uncertain_fields]
                uncertain_dist = Counter(all_uncertain)
                print(f"\n    Uncertain fields reported: {len(with_uncertain)}/{len(with_conf)} steps")
                print(f"    Most cited: {uncertain_dist.most_common(5)}")

    # ── Error provenance ────────────────────────────────────────────────
    all_active_steps = [s for r in all_results for s in r.steps if s.fence_method != "skipped"]
    error_steps = [s for s in all_active_steps if s.error_origin]
    if error_steps:
        from collections import Counter
        origins = Counter(s.error_origin for s in error_steps)
        print("\n  ERROR PROVENANCE:")
        print(f"    Total errors:   {len(error_steps)}/{len(all_active_steps)} steps")
        for origin, count in origins.most_common():
            pct = count / len(error_steps) * 100
            print(f"    {origin:12s}    {count:4d} ({pct:.0f}%)")

        # Per-format error rates
        for fkey in formats:
            fmt_steps = [s for r in all_results if r.format_name == fkey for s in r.steps if s.fence_method != "skipped"]
            fmt_errors = [s for s in fmt_steps if s.error_origin]
            fmt_format = sum(1 for s in fmt_errors if s.error_origin == "format")
            fmt_model = sum(1 for s in fmt_errors if s.error_origin == "model")
            print(f"    {fkey:14s}  format={fmt_format} model={fmt_model} total={len(fmt_errors)}/{len(fmt_steps)}")

    # ── Per-permutation breakdown ───────────────────────────────────────
    print(f"\n  {'Permutation':30s} {'Format':12s} {'Srv ms':>8s} {'E2E sem':>8s} {'Tokens':>8s} {'OK':>4s}")
    print("  " + "-" * 75)
    for perm in permutations:
        perm_label = " → ".join(SHORT_NAMES.get(m, m) for m in perm)
        for fkey in formats:
            chains = [
                r for r in all_results
                if r.format_name == fkey and r.permutation == list(perm) and r.chain_complete
            ]
            if not chains:
                print(f"  {perm_label:30s} {fkey:12s} {'—':>8s} {'—':>8s} {'—':>8s}   0")
                continue
            nc = len(chains)
            avg_srv = sum(r.total_server_ms for r in chains) / nc
            avg_e2e = sum(r.e2e_sem_score for r in chains) / nc
            avg_tok = sum(r.total_tokens for r in chains) / nc
            print(f"  {perm_label:30s} {fkey:12s} {avg_srv:8.0f} {avg_e2e:8.3f} {avg_tok:8.0f} {nc:4d}")

    print(f"\n  Wall clock: {total_elapsed:.0f}s ({total_elapsed/60:.1f}min)")


def _save_results(results: list[ChainResult], path: str) -> None:
    data = []
    for r in results:
        data.append({
            "scenario": r.scenario,
            "format": r.format_name,
            "permutation": r.permutation,
            "permutation_short": [SHORT_NAMES.get(m, m) for m in r.permutation],
            "run_id": r.run_id,
            "chain_complete": r.chain_complete,
            "e2e_sem_score": r.e2e_sem_score,
            "avg_confidence_score": r.avg_confidence_score,
            "total_server_ms": r.total_server_ms,
            "total_parse_ms": r.total_parse_ms,
            "total_wall_clock_s": r.total_wall_clock_s,
            "total_tokens": r.total_tokens,
            "total_cost": r.total_cost,
            "steps": [
                {
                    "model": s.model,
                    "model_short": SHORT_NAMES.get(s.model, s.model),
                    "step_name": s.step_name,
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                    "payload_tokens": s.payload_tokens,
                    "server_processing_ms": s.server_processing_ms,
                    "wall_clock_s": s.wall_clock_s,
                    "parse_time_ms": s.parse_time_ms,
                    "syn_valid": s.syn_valid,
                    "sem_correct": s.sem_correct,
                    "sem_score": s.sem_score,
                    "cost_usd": s.cost_usd,
                    "fence_method": s.fence_method,
                    "sem_reason": s.sem_reason,
                    "confidence": s.confidence,
                    "confidence_score": s.confidence_score,
                    "uncertain_fields": s.uncertain_fields,
                    "source": s.source,
                    "error_origin": s.error_origin,
                }
                for s in r.steps
            ],
        })
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    main()
