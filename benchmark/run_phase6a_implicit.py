#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Phase 6a-implicit: Situational Mode Awareness — Do LLMs Choose the Right Mode?

Follow-up to Phase 6a. The original experiment used explicit prompts like
"Use a schema document format" — models selected the right marker because the
prompt told them to. This test uses IMPLICIT prompts that describe the *task*
without naming the *mode*:

  Explicit: "Define the schema... Use a schema document format."
  Implicit: "What fields and types should an InventoryItem have?"

  Explicit: "Write a query to find... Use a query document format."
  Implicit: "Which items are running low on stock?"

  Explicit: "Generate the appropriate deletion document."
  Implicit: "INV-2002 is discontinued. Remove it from the system."

  Explicit: "Respond with an appropriate structured error document."
  Implicit: "Get me item INV-9999."

This isolates whether the full_primer teaches *mode selection* (situational
awareness) or merely *marker syntax* (prompt compliance).

Design:
  - Only full_primer condition (the only one where mode switching works)
  - Two prompt styles: explicit (from Phase 6a) vs implicit (new)
  - Same 5 steps, same inventory data, same detection logic

Usage:
    python -m benchmark.run_phase6a_implicit
    python -m benchmark.run_phase6a_implicit --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmark.llm_client import create_client, LLMClient, get_pricing
from benchmark.simulated_apis.inventory import InventoryAPI

# Reuse detection helpers and primer from the main Phase 6a runner
from benchmark.run_phase6a_mode_agility import (
    FULL_JMD_PRIMER,
    STEP_NAMES,
    EXPECTED_JMD_MARKERS,
    SHORT_NAMES,
    StepResult,
    _detect_jmd_marker,
    _check_parses,
    _check_content,
)

PHASE6A_MODELS = [
    "claude-sonnet-4-6",
    "gpt-5.4",
    "mistral-large-latest",
]

PROMPT_STYLES = ["explicit", "implicit"]


# ── Prompt builders ─────────────────────────────────────────────────────────

def _build_explicit_prompts(api: InventoryAPI) -> list[tuple[str, str]]:
    """Same prompts as Phase 6a full_primer — names the mode explicitly."""
    schema = api.get_schema()
    target_delete = api.get_item_to_delete()
    nonexistent = api.get_nonexistent_id()
    reorder_ids = api.get_items_needing_reorder()
    items = api.list_items()

    field_desc = ", ".join(f"{n} ({p['type']})" for n, p in list(schema["fields"].items())[:4])

    prompts = []

    prompts.append(("schema", (
        f"Define the schema for an InventoryItem with these fields (and more as appropriate): "
        f"{field_desc}, etc. Mark id, total_value, and reorder_needed as readonly. "
        f"Use a schema document format. Respond in JMD."
    )))

    if reorder_ids:
        prompts.append(("data", (
            f"Here is the current inventory data:\n\n"
            + "\n".join(f"- {api.get_item(rid)['name']} (ID: {rid}, qty: {api.get_item(rid)['quantity']}, "
                        f"min: {api.get_item(rid)['min_quantity']})" for rid in reorder_ids[:3])
            + f"\n\nReturn a data document listing these items with their full details. Respond in JMD."
        )))
    else:
        prompts.append(("data", (
            f"Return the inventory data for these items: "
            + ", ".join(item["id"] for item in items[:3])
            + f". Include all fields. Respond in JMD."
        )))

    prompts.append(("query", (
        f"Write a query to find all inventory items where the quantity is less than "
        f"the minimum quantity (i.e., items needing reorder). "
        f"Return only the id, name, quantity, and min_quantity fields. "
        f"Use a query document format. Respond in JMD."
    )))

    prompts.append(("delete", (
        f"Item {target_delete} has been discontinued and must be removed from "
        f"the inventory system. Generate the appropriate deletion document. Respond in JMD."
    )))

    prompts.append(("error", (
        f"Attempt to retrieve item {nonexistent}. This item does not exist in the system. "
        f"Respond with an appropriate structured error document including the error code, "
        f"a message, and a suggestion for the user. Respond in JMD."
    )))

    return prompts


def _build_implicit_prompts(api: InventoryAPI) -> list[tuple[str, str]]:
    """Implicit prompts — describe the task, never name the mode or document type."""
    schema = api.get_schema()
    target_delete = api.get_item_to_delete()
    target_item = api.get_item(target_delete)
    nonexistent = api.get_nonexistent_id()
    reorder_ids = api.get_items_needing_reorder()
    items = api.list_items()

    field_desc = ", ".join(f"{n} ({p['type']})" for n, p in list(schema["fields"].items())[:4])

    prompts = []

    # Schema — ask about structure, not "define a schema"
    prompts.append(("schema", (
        f"What fields and types should an InventoryItem have? It needs at least: "
        f"{field_desc}, and a few more. The fields id, total_value, and reorder_needed "
        f"should not be directly editable. Respond in JMD."
    )))

    # Data — ask for the items, don't say "data document"
    if reorder_ids:
        prompts.append(("data", (
            f"Here are some inventory items that need attention:\n\n"
            + "\n".join(f"- {api.get_item(rid)['name']} (ID: {rid}, qty: {api.get_item(rid)['quantity']}, "
                        f"min: {api.get_item(rid)['min_quantity']})" for rid in reorder_ids[:3])
            + f"\n\nGive me the full details for these items. Respond in JMD."
        )))
    else:
        prompts.append(("data", (
            f"Give me the full details for items "
            + ", ".join(item["id"] for item in items[:3])
            + f". Respond in JMD."
        )))

    # Query — describe what you want to find, don't say "query"
    prompts.append(("query", (
        f"Which inventory items are running low — where the current quantity "
        f"is below the minimum threshold? I only need the id, name, quantity, "
        f"and min_quantity. Respond in JMD."
    )))

    # Delete — say what should happen, don't say "deletion document"
    prompts.append(("delete", (
        f"{target_item['name']} ({target_delete}) is discontinued. "
        f"Remove it from the inventory. Respond in JMD."
    )))

    # Error — just ask for something that doesn't exist
    prompts.append(("error", (
        f"Get me the details for item {nonexistent}. Respond in JMD."
    )))

    return prompts


# ── Trial runner ────────────────────────────────────────────────────────────

@dataclass
class TrialResult:
    model: str
    prompt_style: str
    seed: int
    steps: list[StepResult]
    input_tokens: int
    output_tokens: int
    server_ms: float
    cost_usd: float

    @property
    def switch_reliability(self) -> float:
        if not self.steps:
            return 0.0
        return sum(1 for s in self.steps if s.correct_marker) / len(self.steps)


print_lock = threading.Lock()


def _run_trial(
    client: LLMClient,
    model: str,
    prompt_style: str,
    seed: int,
    pricing: tuple[float, float],
) -> TrialResult:
    api = InventoryAPI()
    api.reset(seed)

    system = FULL_JMD_PRIMER

    if prompt_style == "explicit":
        prompts = _build_explicit_prompts(api)
    else:
        prompts = _build_implicit_prompts(api)

    total_in = 0
    total_out = 0
    total_server_ms = 0.0
    step_results: list[StepResult] = []

    for step_name, user_msg in prompts:
        result = client.complete(system, user_msg)
        total_in += result.input_tokens
        total_out += result.output_tokens
        total_server_ms += result.server_processing_ms

        raw = result.text
        detected = _detect_jmd_marker(raw)
        correct_marker = detected == EXPECTED_JMD_MARKERS.get(step_name, "")
        parses = _check_parses(raw, "full_primer")
        content_ok = _check_content(step_name, raw, api, "full_primer")

        step_results.append(StepResult(
            step=step_name,
            raw_output=raw[:500],
            correct_marker=correct_marker,
            parses=parses,
            content_correct=content_ok,
            marker_found=detected,
        ))

    cost = (
        total_in * pricing[0] / 1_000_000
        + total_out * pricing[1] / 1_000_000
    )

    return TrialResult(
        model=model,
        prompt_style=prompt_style,
        seed=seed,
        steps=step_results,
        input_tokens=total_in,
        output_tokens=total_out,
        server_ms=total_server_ms,
        cost_usd=cost,
    )


def _run_model_trials(model: str, n_runs: int, seed_base: int) -> list[TrialResult]:
    pricing = get_pricing(model)
    client = create_client(model, temperature=0.0, max_tokens=4096)
    short = SHORT_NAMES.get(model, model)
    results: list[TrialResult] = []

    for style in PROMPT_STYLES:
        for run_id in range(n_runs):
            seed = seed_base + run_id
            t0 = time.monotonic()
            trial = _run_trial(client, model, style, seed, pricing)
            elapsed = time.monotonic() - t0
            results.append(trial)

            markers = [s.marker_found for s in trial.steps]
            switch = trial.switch_reliability

            with print_lock:
                print(
                    f"  {short:8s} | {style:10s} | run {run_id+1:2d} | "
                    f"switch={switch:.0%} | markers={markers} | "
                    f"${trial.cost_usd:.4f} | {elapsed:.1f}s"
                )

    return results


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6a-implicit: Situational Mode Awareness")
    parser.add_argument("--n-runs", type=int, default=10)
    parser.add_argument("--seed-base", type=int, default=700)
    parser.add_argument("--models", nargs="+", default=PHASE6A_MODELS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="benchmark_results/phase6a_implicit_results.json")
    args = parser.parse_args()

    models = args.models
    name_map = {v.lower(): k for k, v in SHORT_NAMES.items()}
    models = [name_map.get(m.lower(), m) for m in models]

    total_calls = args.n_runs * len(PROMPT_STYLES) * len(STEP_NAMES) * len(models)
    cost_est = 0.0
    for model in models:
        pin, pout = get_pricing(model)
        calls = args.n_runs * len(PROMPT_STYLES) * len(STEP_NAMES)
        cost_est += calls * 800 * pin / 1_000_000 + calls * 400 * pout / 1_000_000

    print(f"Phase 6a-implicit: Situational Mode Awareness")
    print(f"  Models: {', '.join(SHORT_NAMES.get(m, m) for m in models)}")
    print(f"  Runs per style: {args.n_runs}")
    print(f"  Prompt styles: {', '.join(PROMPT_STYLES)}")
    print(f"  Total API calls: {total_calls}")
    print(f"  Estimated cost: ${cost_est:.2f}")
    print()

    if args.dry_run:
        print("Dry run — exiting.")
        return

    print("Running trials (parallel across models)...\n")

    all_results: list[TrialResult] = []
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {
            pool.submit(_run_model_trials, model, args.n_runs, args.seed_base): model
            for model in models
        }
        for future in as_completed(futures):
            model = futures[future]
            try:
                all_results.extend(future.result())
            except Exception as e:
                print(f"\nERROR running {model}: {e}")

    # ── Aggregate ───────────────────────────────────────────────────────
    from collections import defaultdict
    groups: dict[str, dict[str, list[TrialResult]]] = defaultdict(lambda: defaultdict(list))
    for r in all_results:
        groups[SHORT_NAMES.get(r.model, r.model)][r.prompt_style].append(r)

    summary: dict = {}
    for model_name, style_map in groups.items():
        model_summary: dict = {}
        for style, trials in style_map.items():
            n = len(trials)
            avg_switch = sum(t.switch_reliability for t in trials) / n

            step_stats: dict[str, dict] = {}
            for step in STEP_NAMES:
                step_results = [s for t in trials for s in t.steps if s.step == step]
                if step_results:
                    step_stats[step] = {
                        "correct_marker_pct": round(
                            100 * sum(1 for s in step_results if s.correct_marker) / len(step_results), 1
                        ),
                        "markers_seen": dict(Counter(s.marker_found for s in step_results)),
                    }

            model_summary[style] = {
                "n_trials": n,
                "avg_switch_reliability_pct": round(100 * avg_switch, 1),
                "per_step": step_stats,
            }
        summary[model_name] = model_summary

    # ── Save ────────────────────────────────────────────────────────────
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw_data = []
    for r in all_results:
        raw_data.append({
            "model": r.model,
            "prompt_style": r.prompt_style,
            "seed": r.seed,
            "switch_reliability": r.switch_reliability,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "server_ms": r.server_ms,
            "cost_usd": r.cost_usd,
            "steps": [
                {
                    "step": s.step,
                    "correct_marker": s.correct_marker,
                    "parses": s.parses,
                    "content_correct": s.content_correct,
                    "marker_found": s.marker_found,
                    "raw_output": s.raw_output,
                }
                for s in r.steps
            ],
        })

    output = {
        "phase": "6a-implicit",
        "name": "Situational Mode Awareness — Explicit vs Implicit Prompts",
        "n_runs": args.n_runs,
        "seed_base": args.seed_base,
        "models": [SHORT_NAMES.get(m, m) for m in models],
        "prompt_styles": PROMPT_STYLES,
        "summary": summary,
        "trials": raw_data,
    }

    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nResults saved to {output_path}")

    # ── Print summary ───────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SUMMARY: Situational Mode Awareness (Phase 6a-implicit)")
    print("=" * 80)

    print(f"\n{'Model':<10} {'Style':<12} {'Switch%':>8}")
    print("-" * 35)
    for model_name, style_map in summary.items():
        for style, stats in style_map.items():
            print(f"{model_name:<10} {style:<12} {stats['avg_switch_reliability_pct']:>7.1f}%")

    print(f"\nPer-Step Marker Correctness:")
    print(f"{'Model':<10} {'Style':<12} ", end="")
    for step in STEP_NAMES:
        print(f"{step:>10}", end="")
    print()
    print("-" * 72)
    for model_name, style_map in summary.items():
        for style, stats in style_map.items():
            print(f"{model_name:<10} {style:<12} ", end="")
            for step in STEP_NAMES:
                pct = stats["per_step"].get(step, {}).get("correct_marker_pct", 0)
                print(f"{pct:>9.0f}%", end="")
            print()

    # Show what markers were actually used in implicit
    print(f"\nMarker Distribution (implicit only):")
    for model_name, style_map in summary.items():
        if "implicit" in style_map:
            stats = style_map["implicit"]
            print(f"\n  {model_name}:")
            for step in STEP_NAMES:
                step_info = stats["per_step"].get(step, {})
                markers = step_info.get("markers_seen", {})
                print(f"    {step:>8}: {markers}")


if __name__ == "__main__":
    main()
