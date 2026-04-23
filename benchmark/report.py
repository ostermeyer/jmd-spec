# SPDX-License-Identifier: Apache-2.0
"""Reporting: CSV export, console summary, primer comparison."""

from __future__ import annotations

import csv
import os
from typing import Any

from .metrics import MetricsCollector, mean_std, wilson_ci


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_steps_csv(collector: MetricsCollector, path: str) -> None:
    """One row per step × run × format."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    fields = [
        "scenario", "format_name", "primer_variant", "run_id",
        "step_index", "step_name", "input_tokens", "output_tokens",
        "total_tokens", "payload_bytes", "payload_tokens",
        "wall_clock_s", "syn_valid", "sem_correct", "sem_score",
        "cost_usd", "skipped",
        "fence_method", "parse_error", "sem_reason",
        "raw_output", "extracted_text",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for chain in collector.chains:
            for step in chain.steps:
                writer.writerow({
                    "scenario": step.scenario,
                    "format_name": step.format_name,
                    "primer_variant": step.primer_variant,
                    "run_id": step.run_id,
                    "step_index": step.step_index,
                    "step_name": step.step_name,
                    "input_tokens": step.input_tokens,
                    "output_tokens": step.output_tokens,
                    "total_tokens": step.total_tokens,
                    "payload_bytes": step.payload_bytes,
                    "payload_tokens": step.payload_tokens,
                    "wall_clock_s": f"{step.wall_clock_s:.3f}",
                    "syn_valid": step.syn_valid,
                    "sem_correct": step.sem_correct,
                    "sem_score": f"{step.sem_score:.2f}",
                    "cost_usd": f"{step.cost_usd:.6f}",
                    "skipped": step.skipped,
                    "fence_method": step.fence_method,
                    "parse_error": step.parse_error,
                    "sem_reason": step.sem_reason,
                    "raw_output": step.raw_output,
                    "extracted_text": step.extracted_text,
                })


def export_streaming_csv(collector: MetricsCollector, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    fields = ["scenario", "format_name", "run_id", "step_name", "total_time_s", "ttfub_s"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for sm in collector.streaming:
            writer.writerow({
                "scenario": sm.scenario,
                "format_name": sm.format_name,
                "run_id": sm.run_id,
                "step_name": sm.step_name,
                "total_time_s": f"{sm.total_time_s:.3f}",
                "ttfub_s": f"{sm.ttfub_s:.3f}",
            })


# ---------------------------------------------------------------------------
# Console report
# ---------------------------------------------------------------------------

def print_report(collector: MetricsCollector, formats: list[str]) -> None:
    """Print three-way comparison table to console."""
    scenarios = sorted(set(c.scenario for c in collector.chains))

    for scenario in scenarios:
        # Only include main benchmark runs (default primer)
        default_chains = [
            c for c in collector.chains
            if c.scenario == scenario
        ]

        print(f"\n{'='*75}")
        print(f"  {scenario.upper()} CHAIN")
        print(f"{'='*75}")

        # Header
        col_width = 18
        header = f"{'':25s}"
        for fk in formats:
            header += f"{fk:>{col_width}s}"
        print(header)
        print("-" * (25 + col_width * len(formats)))

        # Collect per-format stats
        format_stats: dict[str, dict[str, Any]] = {}
        for fk in formats:
            chains = [c for c in default_chains if c.format_name == fk]
            if not chains:
                continue

            n = len(chains)
            total_tokens_list = [c.total_tokens for c in chains]
            wall_clock_list = [c.total_wall_clock for c in chains]
            cost_list = [c.total_cost for c in chains]
            completions = sum(1 for c in chains if c.complete)

            all_steps = [s for c in chains for s in c.steps if not s.skipped]
            syn_valid = sum(1 for s in all_steps if s.syn_valid)
            sem_correct = sum(1 for s in all_steps if s.sem_correct)
            total_steps = len(all_steps)

            tok_mean, tok_std = mean_std([float(t) for t in total_tokens_list])
            wc_mean, wc_std = mean_std(wall_clock_list)
            cost_mean, _ = mean_std(cost_list)
            comp_lo, comp_hi = wilson_ci(completions, n)
            syn_lo, syn_hi = wilson_ci(syn_valid, total_steps) if total_steps else (0, 0)
            sem_lo, sem_hi = wilson_ci(sem_correct, total_steps) if total_steps else (0, 0)

            format_stats[fk] = {
                "n": n,
                "tok_mean": tok_mean,
                "tok_std": tok_std,
                "wc_mean": wc_mean,
                "wc_std": wc_std,
                "cost_mean": cost_mean,
                "completions": completions,
                "comp_ci": (comp_lo, comp_hi),
                "syn_rate": syn_valid / total_steps if total_steps else 0,
                "syn_ci": (syn_lo, syn_hi),
                "sem_rate": sem_correct / total_steps if total_steps else 0,
                "sem_ci": (sem_lo, sem_hi),
            }

        if not format_stats:
            print("  (no data)")
            continue

        # N
        row = f"{'N':25s}"
        for fk in formats:
            if fk in format_stats:
                row += f"{format_stats[fk]['n']:>{col_width}d}"
            else:
                row += f"{'—':>{col_width}s}"
        print(row)

        # Total tokens
        row = f"{'Total tokens':25s}"
        for fk in formats:
            if fk in format_stats:
                s = format_stats[fk]
                row += f"{s['tok_mean']:>10.0f} ±{s['tok_std']:>5.0f} "
            else:
                row += f"{'—':>{col_width}s}"
        print(row)

        # Delta vs first format
        base_key = formats[0] if formats[0] in format_stats else None
        if base_key:
            row = f"{'  vs ' + base_key:25s}"
            for fk in formats:
                if fk == base_key:
                    row += f"{'baseline':>{col_width}s}"
                elif fk in format_stats:
                    delta = (format_stats[fk]["tok_mean"] - format_stats[base_key]["tok_mean"]) / format_stats[base_key]["tok_mean"] * 100
                    row += f"{delta:>+{col_width-1}.1f}%"
                else:
                    row += f"{'—':>{col_width}s}"
            print(row)

        # Wall clock
        row = f"{'Wall clock (s)':25s}"
        for fk in formats:
            if fk in format_stats:
                s = format_stats[fk]
                row += f"{s['wc_mean']:>10.1f} ±{s['wc_std']:>5.1f} "
            else:
                row += f"{'—':>{col_width}s}"
        print(row)

        # Cost
        row = f"{'Cost (USD)':25s}"
        for fk in formats:
            if fk in format_stats:
                cost_str = f"${format_stats[fk]['cost_mean']:.4f}"
                row += f"{cost_str:>{col_width}s}"
            else:
                row += f"{'—':>{col_width}s}"
        print(row)

        # Chain completion
        row = f"{'Chain completion':25s}"
        for fk in formats:
            if fk in format_stats:
                s = format_stats[fk]
                ci = s["comp_ci"]
                val = f"{s['completions']}/{s['n']} [{ci[0]:.0%}-{ci[1]:.0%}]"
                row += f"{val:>{col_width}s}"
            else:
                row += f"{'—':>{col_width}s}"
        print(row)

        # Syn validity
        row = f"{'Syn. validity':25s}"
        for fk in formats:
            if fk in format_stats:
                s = format_stats[fk]
                ci = s["syn_ci"]
                val = f"{s['syn_rate']:.0%} [{ci[0]:.0%}-{ci[1]:.0%}]"
                row += f"{val:>{col_width}s}"
            else:
                row += f"{'—':>{col_width}s}"
        print(row)

        # Sem correctness
        row = f"{'Sem. correctness':25s}"
        for fk in formats:
            if fk in format_stats:
                s = format_stats[fk]
                ci = s["sem_ci"]
                val = f"{s['sem_rate']:.0%} [{ci[0]:.0%}-{ci[1]:.0%}]"
                row += f"{val:>{col_width}s}"
            else:
                row += f"{'—':>{col_width}s}"
        print(row)

    # --- TTFUB ---
    if collector.streaming:
        print(f"\n{'='*75}")
        print("  STREAMING TTFUB")
        print(f"{'='*75}")

        col_width = 18
        header = f"{'':25s}"
        for fk in formats:
            header += f"{fk:>{col_width}s}"
        print(header)
        print("-" * (25 + col_width * len(formats)))

        scenarios_with_streaming = sorted(set(s.scenario for s in collector.streaming))
        for scenario in scenarios_with_streaming:
            row = f"{scenario:25s}"
            for fk in formats:
                entries = [s for s in collector.streaming if s.scenario == scenario and s.format_name == fk]
                if entries:
                    ttfub_mean, ttfub_std = mean_std([e.ttfub_s for e in entries])
                    row += f"{ttfub_mean:>10.3f}s ±{ttfub_std:>.3f}s"
                else:
                    row += f"{'—':>{col_width}s}"
            print(row)


def print_primer_report(collector: MetricsCollector) -> None:
    """Print primer variant comparison."""
    primer_chains = [c for c in collector.chains if c.scenario == "ecommerce" and c.format_name == "jmd"]
    if not primer_chains:
        return

    variants = sorted(set(c.primer_variant for c in primer_chains))
    if len(variants) < 2:
        return

    print(f"\n{'='*75}")
    print("  JMD PRIMER COMPARISON (E-Commerce)")
    print(f"{'='*75}")

    col_width = 18
    header = f"{'':25s}"
    for v in variants:
        header += f"{v:>{col_width}s}"
    print(header)
    print("-" * (25 + col_width * len(variants)))

    # Row: N
    row = f"{'N':25s}"
    for v in variants:
        chains = [c for c in primer_chains if c.primer_variant == v]
        row += f"{len(chains):>{col_width}d}"
    print(row)

    # Row: Syn validity
    row = f"{'Syn. validity':25s}"
    for v in variants:
        chains = [c for c in primer_chains if c.primer_variant == v]
        steps = [s for c in chains for s in c.steps if not s.skipped]
        rate = sum(1 for s in steps if s.syn_valid) / len(steps) if steps else 0
        row += f"{rate:>{col_width}.0%}"
    print(row)

    # Row: Sem correctness
    row = f"{'Sem. correctness':25s}"
    for v in variants:
        chains = [c for c in primer_chains if c.primer_variant == v]
        steps = [s for c in chains for s in c.steps if not s.skipped]
        rate = sum(1 for s in steps if s.sem_correct) / len(steps) if steps else 0
        row += f"{rate:>{col_width}.0%}"
    print(row)

    # Row: Chain completion
    row = f"{'Chain completion':25s}"
    for v in variants:
        chains = [c for c in primer_chains if c.primer_variant == v]
        completions = sum(1 for c in chains if c.complete)
        val = f"{completions}/{len(chains)}"
        row += f"{val:>{col_width}s}"
    print(row)
