#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Entry point for the JMD vs JSON benchmark suite.

Usage:
    python -m benchmark.run_benchmark                  # full benchmark (Claude)
    python -m benchmark.run_benchmark --model gpt-4o   # use OpenAI
    python -m benchmark.run_benchmark --model gemini-2.5-flash  # use Gemini
    python -m benchmark.run_benchmark --dry-run        # no LLM calls
    python -m benchmark.run_benchmark --n-runs 5       # quick test
    python -m benchmark.run_benchmark --streaming-only # TTFUB only
    python -m benchmark.run_benchmark --primer-test    # primer comparison only
    python -m benchmark.run_benchmark --scenarios ecommerce,devops
    python -m benchmark.run_benchmark --formats json_pretty,jmd
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure repo root is on path for jmd.py import
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmark.config import BenchmarkConfig
from benchmark.formats import get_format
from benchmark.llm_client import create_client, detect_provider
from benchmark.metrics import MetricsCollector
from benchmark.report import export_steps_csv, export_streaming_csv, print_report, print_primer_report
from benchmark.runner import run_benchmark
from benchmark.scenarios import ALL_SCENARIOS


# Provider → (env_var_name, example_prefix)
_API_KEY_MAP: dict[str, tuple[str, str]] = {
    "anthropic": ("ANTHROPIC_API_KEY", "sk-ant-..."),
    "openai": ("OPENAI_API_KEY", "sk-..."),
    "google": ("GOOGLE_API_KEY", "AI..."),
}


def _check_api_key(provider: str) -> None:
    """Ensure the right API key env var is set for the provider."""
    env_var, example = _API_KEY_MAP.get(provider, (None, None))
    if env_var and not os.environ.get(env_var):
        print(f"\nERROR: {env_var} not set.")
        print(f"Export it: export {env_var}={example}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="JMD vs JSON Benchmark Suite")
    parser.add_argument("--n-runs", type=int, default=None, help="Override number of runs (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without LLM calls")
    parser.add_argument("--streaming-only", action="store_true", help="Only run TTFUB streaming tests")
    parser.add_argument("--primer-test", action="store_true", help="Only run primer comparison")
    parser.add_argument("--scenarios", type=str, default=None, help="Comma-separated scenario names")
    parser.add_argument("--formats", type=str, default=None, help="Comma-separated format names")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    parser.add_argument("--model", type=str, default=None, help="Model ID (auto-detects provider)")
    args = parser.parse_args()

    config = BenchmarkConfig()
    if args.n_runs is not None:
        config.n_runs = args.n_runs
    if args.output_dir:
        config.output_dir = args.output_dir
    if args.model:
        config.model = args.model
        config._update_pricing()
    if args.formats:
        config.formats = args.formats.split(",")

    # Detect provider
    provider = detect_provider(config.model)

    # Select scenarios
    scenarios = ALL_SCENARIOS
    if args.scenarios:
        names = args.scenarios.split(",")
        scenarios = {k: v for k, v in ALL_SCENARIOS.items() if k in names}
        if not scenarios:
            print(f"No matching scenarios. Available: {list(ALL_SCENARIOS.keys())}")
            sys.exit(1)

    # Validate formats
    for fk in config.formats:
        try:
            get_format(fk)
        except KeyError:
            print(f"Unknown format: {fk}. Available: json_pretty, json_minified, jmd, yaml")
            sys.exit(1)

    collector = MetricsCollector()

    # Print config summary
    print("JMD vs JSON Benchmark Suite")
    print(f"  Model:      {config.model} ({provider})")
    print(f"  Pricing:    ${config.pricing_input:.2f}/${config.pricing_output:.2f} per 1M tokens")
    print(f"  Runs:       {config.n_runs}")
    print(f"  Formats:    {config.formats}")
    print(f"  Scenarios:  {list(scenarios.keys())}")
    print(f"  Output:     {config.output_dir}")

    if args.dry_run:
        print("\n--- DRY RUN (no LLM calls) ---")
        run_benchmark(config, scenarios, collector, None, dry_run=True)  # type: ignore
        return

    # Check API key
    _check_api_key(provider)

    # Initialize LLM client (auto-selects provider)
    llm_client = create_client(
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )

    # Run benchmark
    run_benchmark(
        config, scenarios, collector, llm_client,
        streaming_only=args.streaming_only,
        primer_test_only=args.primer_test,
    )

    # Export results
    os.makedirs(config.output_dir, exist_ok=True)
    steps_csv = os.path.join(config.output_dir, "benchmark_results_steps.csv")
    streaming_csv = os.path.join(config.output_dir, "benchmark_results_streaming.csv")

    export_steps_csv(collector, steps_csv)
    print(f"\nStep results: {steps_csv}")

    if collector.streaming:
        export_streaming_csv(collector, streaming_csv)
        print(f"Streaming results: {streaming_csv}")

    # Console report
    print_report(collector, config.formats)
    print_primer_report(collector)

    # Total stats
    total_chains = len(collector.chains)
    total_tokens = sum(c.total_tokens for c in collector.chains)
    total_cost = sum(c.total_cost for c in collector.chains)
    print(f"\n{'='*75}")
    print(f"  TOTALS: {total_chains} chains, {total_tokens:,} tokens, ${total_cost:.2f}")
    print(f"{'='*75}")


if __name__ == "__main__":
    main()
