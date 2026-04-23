#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Phase 2 benchmark runner — parallel multi-model execution.

Usage:
    python -m benchmark.run_phase2
    python -m benchmark.run_phase2 --n-runs 5          # quick test
    python -m benchmark.run_phase2 --models haiku,sonnet  # subset
    python -m benchmark.run_phase2 --formats jmd        # JMD only
    python -m benchmark.run_phase2 --dry-run            # no LLM calls
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmark.config import BenchmarkConfig
from benchmark.formats import get_format
from benchmark.llm_client import create_client, get_pricing
from benchmark.metrics import ChainResult, MetricsCollector
from benchmark.runner import run_chain
from benchmark.scenarios import ALL_SCENARIOS

# Phase 2 model set
PHASE2_MODELS = [
    "claude-sonnet-4-6",
    "gpt-5.4",
    "mistral-large-latest",
    "gemini-2.5-flash",
]

PHASE2_FORMATS = ["json_pretty", "jmd"]

_print_lock = threading.Lock()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def _run_model(
    model: str,
    formats: list[str],
    scenarios: dict,
    n_runs: int,
    primer: str,
) -> list[ChainResult]:
    """Run all chains for one model. Called in a worker thread."""
    config = BenchmarkConfig(model=model, n_runs=n_runs)
    llm = create_client(model, config.temperature, config.max_tokens)
    results: list[ChainResult] = []

    total = len(formats) * len(scenarios) * n_runs
    done = 0

    for run_id in range(n_runs):
        for fkey in formats:
            fmt = get_format(fkey)
            for sname, scenario in scenarios.items():
                done += 1
                t0 = time.monotonic()
                result = run_chain(
                    scenario, fmt, fkey, primer,
                    run_id, llm, config,
                )
                elapsed = time.monotonic() - t0
                results.append(result)

                status = "OK" if result.complete else "BROKEN"
                syn = sum(1 for s in result.steps if s.syn_valid)
                sem = sum(1 for s in result.steps if s.sem_correct)
                n_steps = len(result.steps)
                _log(
                    f"  [{model:28s}] {done:3d}/{total} "
                    f"{sname}/{fkey} run={run_id} "
                    f"syn={syn}/{n_steps} sem={sem}/{n_steps} "
                    f"${result.total_cost:.4f} {elapsed:.1f}s {status}"
                )

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2: Parallel multi-model benchmark")
    parser.add_argument("--n-runs", type=int, default=30)
    parser.add_argument("--models", type=str, default=None,
                        help="Comma-separated model IDs or short names (haiku,sonnet,gpt,gemini)")
    parser.add_argument("--formats", type=str, default=None,
                        help="Comma-separated format names (default: json_pretty,jmd)")
    parser.add_argument("--scenarios", type=str, default=None)
    parser.add_argument("--primer", type=str, default="strict")
    parser.add_argument("--output-dir", type=str, default="benchmark_results")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Resolve models
    if args.models:
        short_map = {
            "haiku": "claude-haiku-4-5",
            "sonnet": "claude-sonnet-4-6",
            "gpt": "gpt-5.4",
            "gemini": "gemini-2.5-flash",
            "flash": "gemini-2.5-flash",
            "mistral": "mistral-large-latest",
        }
        models = []
        for m in args.models.split(","):
            m = m.strip()
            models.append(short_map.get(m, m))
    else:
        models = list(PHASE2_MODELS)

    formats = args.formats.split(",") if args.formats else list(PHASE2_FORMATS)

    scenarios = ALL_SCENARIOS
    if args.scenarios:
        names = args.scenarios.split(",")
        scenarios = {k: v for k, v in ALL_SCENARIOS.items() if k in names}

    # Print plan
    total_chains = len(models) * len(formats) * len(scenarios) * args.n_runs
    print("=" * 70)
    print("Phase 2 Benchmark — Parallel Multi-Model")
    print("=" * 70)
    print(f"  Models:    {models}")
    print(f"  Formats:   {formats}")
    print(f"  Scenarios: {list(scenarios.keys())}")
    print(f"  Runs:      {args.n_runs}")
    print(f"  Primer:    {args.primer}")
    print(f"  Total:     {total_chains} chains ({len(models)} models in parallel)")

    # Cost estimate
    est_total = 0.0
    for model in models:
        inp, out = get_pricing(model)
        # ~2000 input + ~800 output tokens per step, 5 steps per chain
        chains_per_model = len(formats) * len(scenarios) * args.n_runs
        steps = chains_per_model * 5
        est = steps * (2000 * inp + 800 * out) / 1_000_000
        est_total += est
        print(f"  {model:30s}  ~${est:.2f}")
    print(f"  {'ESTIMATED TOTAL':30s}  ~${est_total:.2f}")
    print()

    if args.dry_run:
        print("DRY RUN — no API calls.")
        return

    # Run models in parallel
    t_start = time.monotonic()
    all_results: list[ChainResult] = []

    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {
            pool.submit(_run_model, model, formats, scenarios, args.n_runs, args.primer): model
            for model in models
        }
        for future in as_completed(futures):
            model = futures[future]
            try:
                results = future.result()
                all_results.extend(results)
                _log(f"\n  >>> {model} finished: {len(results)} chains\n")
            except Exception as e:
                _log(f"\n  >>> {model} FAILED: {e}\n")

    elapsed = time.monotonic() - t_start

    # Collect into MetricsCollector for reporting
    collector = MetricsCollector()
    for r in all_results:
        collector.record_chain(r)

    # Summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    # Per-model × format summary
    print(f"\n{'Model':30s} {'Format':12s} {'Chains':>6s} {'Syn%':>6s} {'Sem%':>6s} {'Tokens':>8s} {'Cost':>8s}")
    print("-" * 80)

    for model in models:
        for fkey in formats:
            chains = [
                r for r in all_results
                if r.format_name == fkey
                and r.steps and r.steps[0].model == model
            ]
            if not chains:
                continue
            n = len(chains)
            syn_ok = sum(1 for c in chains for s in c.steps if s.syn_valid)
            syn_total = sum(len(c.steps) for c in chains)
            sem_ok = sum(1 for c in chains for s in c.steps if s.sem_correct)
            tokens = sum(c.total_tokens for c in chains)
            cost = sum(c.total_cost for c in chains)
            syn_pct = 100 * syn_ok / syn_total if syn_total else 0
            sem_pct = 100 * sem_ok / syn_total if syn_total else 0
            print(f"{model:30s} {fkey:12s} {n:6d} {syn_pct:5.1f}% {sem_pct:5.1f}% {tokens:8,d} ${cost:7.2f}")

    total_tokens = sum(c.total_tokens for c in all_results)
    total_cost = sum(c.total_cost for c in all_results)
    print("-" * 80)
    print(f"{'TOTAL':30s} {'':12s} {len(all_results):6d} {'':6s} {'':6s} {total_tokens:8,d} ${total_cost:7.2f}")
    print(f"\nWall clock: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    # Save raw results as JSON
    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, "phase2_results.json")
    _save_results(all_results, out_path)
    print(f"Results saved: {out_path}")


def _save_results(results: list[ChainResult], path: str) -> None:
    """Save results as JSON for later analysis."""
    data = []
    for r in results:
        data.append({
            "model": r.steps[0].model if r.steps else "",
            "scenario": r.scenario,
            "format": r.format_name,
            "primer": r.primer_variant,
            "run_id": r.run_id,
            "complete": r.complete,
            "total_tokens": r.total_tokens,
            "total_cost": r.total_cost,
            "steps": [
                {
                    "name": s.step_name,
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                    "payload_tokens": s.payload_tokens,
                    "wall_clock_s": s.wall_clock_s,
                    "server_processing_ms": s.server_processing_ms,
                    "syn_valid": s.syn_valid,
                    "sem_correct": s.sem_correct,
                    "sem_score": s.sem_score,
                    "cost_usd": s.cost_usd,
                    "fence_method": s.fence_method,
                    "sem_reason": s.sem_reason,
                }
                for s in r.steps
            ],
        })
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    main()
