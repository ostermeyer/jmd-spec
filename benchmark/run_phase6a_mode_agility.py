#!/usr/bin/env python3
"""Phase 6a: Mode Agility — Can LLMs Switch Between JMD Document Modes?

Tests whether LLMs correctly switch between all four JMD document modes
(#, #!, #?, #-) plus Error documents within a single multi-step workflow.

Scenario: Inventory Management
  Step 1: Define a schema (#!)
  Step 2: Create/read inventory items (#)
  Step 3: Query for low-stock items (#?)
  Step 4: Delete a discontinued item (#-)
  Step 5: Handle an invalid request (# Error)

Conditions:
  A (full_primer):   JMD primer with all four modes explained
  B (data_only):     JMD primer with only # data mode — model must infer the rest
  C (json_baseline): Same workflow but JSON — conventional markers for modes

Metrics:
  1. Switch reliability: % correct root markers per step
  2. Syntax correctness: does the output parse?
  3. Situational awareness: correct mode choice without explicit instruction
  4. Content accuracy: correct data in each response

Usage:
    python -m benchmark.run_phase6a_mode_agility
    python -m benchmark.run_phase6a_mode_agility --n-runs 5 --models sonnet
    python -m benchmark.run_phase6a_mode_agility --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
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

from benchmark.config import BenchmarkConfig
from benchmark.llm_client import create_client, LLMClient, get_pricing
from benchmark.simulated_apis.inventory import InventoryAPI

# ── Models ──────────────────────────────────────────────────────────────────

PHASE6A_MODELS = [
    "claude-sonnet-4-6",
    "gpt-5.4",
    "mistral-large-latest",
]

SHORT_NAMES = {
    "claude-sonnet-4-6": "Sonnet",
    "claude-haiku-4-5": "Haiku",
    "gpt-5.4": "GPT-5.4",
    "mistral-large-latest": "Mistral",
    "gemini-2.5-flash": "Flash",
}

CONDITIONS = ["full_primer", "data_only", "json_baseline"]

# ── Steps in the workflow ───────────────────────────────────────────────────

STEP_NAMES = ["schema", "data", "query", "delete", "error"]
EXPECTED_JMD_MARKERS = {
    "schema": "#!",
    "data": "#",
    "query": "#?",
    "delete": "#-",
    "error": "# Error",
}

# ── Primers ─────────────────────────────────────────────────────────────────

FULL_JMD_PRIMER = """\
You are an API agent. You communicate using JMD (JSON Markdown).

JMD is a tetradic protocol with four document modes:

1. DATA (#): Standard data documents.
   # Label
   key: value
   ## nested_object
   key: value

2. SCHEMA (#!): Structure contracts and type validation.
   #! Label
   field_name: type | modifier
   Example:
   #! Product
   id: string | readonly
   name: string
   price: float
   status: string | enum(active, discontinued)

3. QUERY (#?): Query by Example — data selection.
   #? Label
   field: value          (exact match)
   field: >N             (comparison)
   field: pattern.*      (regex match)
   ?: ?                  (wildcard projection — return all fields)
   field: ?              (projection — return this field)

4. DELETE (#-): Resource deletion.
   #- Label
   id: value_to_delete

5. ERROR (# Error): Structured error responses.
   # Error
   code: error_code
   message: Human-readable description
   suggestion: How to fix

Rules:
- EVERY response must use exactly ONE of these document modes
- Choose the mode that fits the operation
- No braces, no quotes on keys
- ## for nested objects, ## key[] for arrays, - for items\
"""

DATA_ONLY_JMD_PRIMER = """\
You are an API agent. You communicate using JMD (JSON Markdown).

JMD rules:
- EVERY response MUST start with # Label (the root object heading)
- ## key opens a nested object; depth = heading level
- ## key[] declares an array; items start with -
- Fields: key: value (no braces, no quotes on keys)
- Array object items: - first_key: val on first line, then indented continuation fields

Example:
# Order
id: 42
status: pending
## customer
name: Jane Doe
## items[]
- sku: A1
  qty: 2\
"""

JSON_BASELINE_PRIMER = """\
You are an API agent. You communicate using JSON.

For different operations, use these conventions:
- Data responses: standard JSON objects
- Schema definitions: JSON Schema format
- Queries: use a JSON object with filter criteria
- Deletions: use {"_action": "delete", "id": "..."}
- Errors: use {"error": "code", "message": "...", "suggestion": "..."}

Always produce valid JSON.\
"""


# ── Result dataclass ────────────────────────────────────────────────────────

@dataclass
class StepResult:
    step: str
    raw_output: str
    correct_marker: bool
    parses: bool
    content_correct: bool
    marker_found: str  # what marker was actually detected


@dataclass
class TrialResult:
    model: str
    condition: str
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

    @property
    def parse_rate(self) -> float:
        if not self.steps:
            return 0.0
        return sum(1 for s in self.steps if s.parses) / len(self.steps)

    @property
    def content_accuracy(self) -> float:
        if not self.steps:
            return 0.0
        return sum(1 for s in self.steps if s.content_correct) / len(self.steps)


# ── Detection helpers ───────────────────────────────────────────────────────

def _detect_jmd_marker(text: str) -> str:
    """Detect which JMD root marker is used in the output."""
    text = text.strip()
    # Check for code fence and extract content
    fence_match = re.search(r"```(?:markdown|jmd)?\s*\n(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#! "):
            return "#!"
        if line.startswith("#? "):
            return "#?"
        if line.startswith("#- "):
            return "#-"
        if line.lower().startswith("# error"):
            return "# Error"
        if line.startswith("# "):
            return "#"
    return "none"


def _detect_json_mode(text: str) -> str:
    """Detect which JSON convention was used."""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return "unparseable"

    if isinstance(data, dict):
        if "_action" in data and data.get("_action") == "delete":
            return "delete"
        if "error" in data:
            return "error"
        if "$schema" in data or "properties" in data or "type" in data:
            return "schema"
        # Query detection: look for filter-like structures
        if any(isinstance(v, dict) and ("$gt" in v or "$lt" in v or "$regex" in v) for v in data.values()):
            return "query"
    return "data"


def _check_parses(text: str, condition: str) -> bool:
    """Check if the output parses as valid JMD or JSON."""
    text = text.strip()
    # Extract from code fence
    fence_match = re.search(r"```(?:markdown|jmd|json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    if condition == "json_baseline":
        try:
            json.loads(text)
            return True
        except (json.JSONDecodeError, ValueError):
            return False
    else:
        # JMD: must start with a heading marker
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            return line.startswith("#")
        return False


def _check_content(step: str, text: str, api: InventoryAPI, condition: str) -> bool:
    """Basic content correctness check per step."""
    text_lower = text.lower()

    if step == "schema":
        # Should contain field names from the schema
        schema = api.get_schema()
        field_names = list(schema["fields"].keys())
        found = sum(1 for f in field_names if f in text_lower)
        return found >= len(field_names) * 0.5  # at least half the fields

    elif step == "data":
        # Should contain actual item data
        items = api.list_items()
        if not items:
            return False
        # Check if at least one item ID appears
        return any(item["id"].lower() in text_lower for item in items)

    elif step == "query":
        # Should reference quantity or min_quantity or reorder
        return any(kw in text_lower for kw in ["quantity", "min_quantity", "reorder", "stock"])

    elif step == "delete":
        # Should reference the item to delete
        target = api.get_item_to_delete()
        return target.lower() in text_lower

    elif step == "error":
        # Should contain error indication
        return any(kw in text_lower for kw in ["error", "not_found", "not found", "does not exist", "invalid"])

    return False


# ── Build prompts per step ──────────────────────────────────────────────────

def _build_step_prompts(api: InventoryAPI, condition: str) -> list[tuple[str, str]]:
    """Return list of (step_name, user_message) tuples for the workflow."""
    items = api.list_items()
    target_delete = api.get_item_to_delete()
    nonexistent = api.get_nonexistent_id()
    schema = api.get_schema()

    if condition == "json_baseline":
        fmt_hint = "Respond in JSON."
    else:
        fmt_hint = "Respond in JMD."

    prompts = []

    # Step 1: Schema
    field_desc = ", ".join(f"{n} ({p['type']})" for n, p in list(schema["fields"].items())[:4])
    prompts.append(("schema", (
        f"Define the schema for an InventoryItem with these fields (and more as appropriate): "
        f"{field_desc}, etc. Mark id, total_value, and reorder_needed as readonly. "
        f"Use a schema document format. {fmt_hint}"
    )))

    # Step 2: Data — return items needing reorder
    reorder_ids = api.get_items_needing_reorder()
    if reorder_ids:
        prompts.append(("data", (
            f"Here is the current inventory data:\n\n"
            + "\n".join(f"- {api.get_item(rid)['name']} (ID: {rid}, qty: {api.get_item(rid)['quantity']}, "
                        f"min: {api.get_item(rid)['min_quantity']})" for rid in reorder_ids[:3])
            + f"\n\nReturn a data document listing these items with their full details. {fmt_hint}"
        )))
    else:
        # Fallback: just list first 3 items
        prompts.append(("data", (
            f"Return the inventory data for these items: "
            + ", ".join(item["id"] for item in items[:3])
            + f". Include all fields. {fmt_hint}"
        )))

    # Step 3: Query
    prompts.append(("query", (
        f"Write a query to find all inventory items where the quantity is less than "
        f"the minimum quantity (i.e., items needing reorder). "
        f"Return only the id, name, quantity, and min_quantity fields. "
        f"Use a query document format. {fmt_hint}"
    )))

    # Step 4: Delete
    prompts.append(("delete", (
        f"Item {target_delete} has been discontinued and must be removed from "
        f"the inventory system. Generate the appropriate deletion document. {fmt_hint}"
    )))

    # Step 5: Error
    prompts.append(("error", (
        f"Attempt to retrieve item {nonexistent}. This item does not exist in the system. "
        f"Respond with an appropriate structured error document including the error code, "
        f"a message, and a suggestion for the user. {fmt_hint}"
    )))

    return prompts


# ── Single trial ────────────────────────────────────────────────────────────

def _run_trial(
    client: LLMClient,
    model: str,
    condition: str,
    seed: int,
    pricing: tuple[float, float],
) -> TrialResult:
    """Run a complete 5-step workflow trial."""
    api = InventoryAPI()
    api.reset(seed)

    # Select system prompt
    if condition == "full_primer":
        system = FULL_JMD_PRIMER
    elif condition == "data_only":
        system = DATA_ONLY_JMD_PRIMER
    else:
        system = JSON_BASELINE_PRIMER

    prompts = _build_step_prompts(api, condition)

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

        # Detect marker
        if condition == "json_baseline":
            detected = _detect_json_mode(raw)
            expected_map = {
                "schema": "schema",
                "data": "data",
                "query": "query",
                "delete": "delete",
                "error": "error",
            }
            correct_marker = detected == expected_map.get(step_name, "")
        else:
            detected = _detect_jmd_marker(raw)
            correct_marker = detected == EXPECTED_JMD_MARKERS.get(step_name, "")

        parses = _check_parses(raw, condition)
        content_ok = _check_content(step_name, raw, api, condition)

        step_results.append(StepResult(
            step=step_name,
            raw_output=raw[:500],  # truncate for storage
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
        condition=condition,
        seed=seed,
        steps=step_results,
        input_tokens=total_in,
        output_tokens=total_out,
        server_ms=total_server_ms,
        cost_usd=cost,
    )


# ── Parallel model runner ──────────────────────────────────────────────────

print_lock = threading.Lock()


def _run_model_trials(
    model: str,
    n_runs: int,
    seed_base: int,
) -> list[TrialResult]:
    """Run all conditions x runs for a single model."""
    pricing = get_pricing(model)
    client = create_client(model, temperature=0.0, max_tokens=4096)
    short = SHORT_NAMES.get(model, model)
    results: list[TrialResult] = []

    for cond in CONDITIONS:
        for run_id in range(n_runs):
            seed = seed_base + run_id
            t0 = time.monotonic()
            trial = _run_trial(client, model, cond, seed, pricing)
            elapsed = time.monotonic() - t0
            results.append(trial)

            switch = trial.switch_reliability
            parse = trial.parse_rate
            markers = [s.marker_found for s in trial.steps]

            with print_lock:
                print(
                    f"  {short:8s} | {cond:14s} | run {run_id+1:2d} | "
                    f"switch={switch:.0%} parse={parse:.0%} | "
                    f"markers={markers} | "
                    f"${trial.cost_usd:.4f} | {elapsed:.1f}s"
                )

    return results


# ── Aggregation ─────────────────────────────────────────────────────────────

def _aggregate(results: list[TrialResult]) -> dict:
    """Aggregate trial results into summary statistics."""
    summary: dict = {"models": {}, "totals": {}}

    total_cost = sum(r.cost_usd for r in results)
    total_in = sum(r.input_tokens for r in results)
    total_out = sum(r.output_tokens for r in results)
    summary["totals"] = {
        "trials": len(results),
        "total_cost_usd": round(total_cost, 4),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
    }

    # Group by model x condition
    from collections import defaultdict
    groups: dict[str, dict[str, list[TrialResult]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        groups[r.model][r.condition].append(r)

    for model, cond_map in groups.items():
        short = SHORT_NAMES.get(model, model)
        model_summary: dict = {}
        for cond, trials in cond_map.items():
            n = len(trials)

            # Per-step breakdown
            step_stats: dict[str, dict] = {}
            for step in STEP_NAMES:
                step_results = [
                    s for t in trials for s in t.steps if s.step == step
                ]
                if step_results:
                    step_stats[step] = {
                        "correct_marker_pct": round(
                            100 * sum(1 for s in step_results if s.correct_marker) / len(step_results), 1
                        ),
                        "parse_pct": round(
                            100 * sum(1 for s in step_results if s.parses) / len(step_results), 1
                        ),
                        "content_correct_pct": round(
                            100 * sum(1 for s in step_results if s.content_correct) / len(step_results), 1
                        ),
                        "markers_seen": dict(Counter(s.marker_found for s in step_results)),
                    }

            avg_switch = sum(t.switch_reliability for t in trials) / n
            avg_parse = sum(t.parse_rate for t in trials) / n
            avg_content = sum(t.content_accuracy for t in trials) / n
            avg_cost = sum(t.cost_usd for t in trials) / n
            avg_server_ms = sum(t.server_ms for t in trials) / n

            model_summary[cond] = {
                "n_trials": n,
                "avg_switch_reliability_pct": round(100 * avg_switch, 1),
                "avg_parse_rate_pct": round(100 * avg_parse, 1),
                "avg_content_accuracy_pct": round(100 * avg_content, 1),
                "avg_cost_usd": round(avg_cost, 4),
                "avg_server_ms": round(avg_server_ms, 1),
                "per_step": step_stats,
            }

        summary["models"][short] = model_summary

    return summary


# ── Cost estimation ─────────────────────────────────────────────────────────

def _estimate_cost(n_runs: int, models: list[str]) -> tuple[float, float]:
    """Estimate total cost and runtime."""
    # Each trial: 5 API calls, ~800 input + ~400 output tokens each
    tokens_per_step_in = 800
    tokens_per_step_out = 400
    steps = 5
    conditions = len(CONDITIONS)

    total_cost = 0.0
    for model in models:
        pin, pout = get_pricing(model)
        calls = n_runs * conditions * steps
        cost = (
            calls * tokens_per_step_in * pin / 1_000_000
            + calls * tokens_per_step_out * pout / 1_000_000
        )
        total_cost += cost

    # Runtime: ~3s per API call, parallel across models
    calls_per_model = n_runs * conditions * steps
    runtime_s = calls_per_model * 3  # sequential within model
    runtime_min = runtime_s / 60

    return total_cost, runtime_min


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6a: Mode Agility benchmark")
    parser.add_argument("--n-runs", type=int, default=10)
    parser.add_argument("--seed-base", type=int, default=600)
    parser.add_argument("--models", nargs="+", default=PHASE6A_MODELS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="benchmark_results/phase6a_mode_agility_results.json")
    args = parser.parse_args()

    models = args.models
    # Resolve short names
    name_map = {v.lower(): k for k, v in SHORT_NAMES.items()}
    models = [name_map.get(m.lower(), m) for m in models]

    cost_est, time_est = _estimate_cost(args.n_runs, models)
    print(f"Phase 6a: Mode Agility — Inventory Management")
    print(f"  Models: {', '.join(SHORT_NAMES.get(m, m) for m in models)}")
    print(f"  Runs per condition: {args.n_runs}")
    print(f"  Conditions: {', '.join(CONDITIONS)}")
    print(f"  Steps per trial: {len(STEP_NAMES)}")
    print(f"  Total API calls: {args.n_runs * len(CONDITIONS) * len(STEP_NAMES) * len(models)}")
    print(f"  Estimated cost: ${cost_est:.2f}")
    print(f"  Estimated runtime: {time_est:.1f} min (parallel across models)")
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
                model_results = future.result()
                all_results.extend(model_results)
            except Exception as e:
                print(f"\nERROR running {model}: {e}")

    # Aggregate
    summary = _aggregate(all_results)

    # Save raw + summary
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw_data = []
    for r in all_results:
        raw_data.append({
            "model": r.model,
            "condition": r.condition,
            "seed": r.seed,
            "switch_reliability": r.switch_reliability,
            "parse_rate": r.parse_rate,
            "content_accuracy": r.content_accuracy,
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
        "phase": "6a",
        "name": "Mode Agility — Inventory Management",
        "n_runs": args.n_runs,
        "seed_base": args.seed_base,
        "models": [SHORT_NAMES.get(m, m) for m in models],
        "conditions": CONDITIONS,
        "summary": summary,
        "trials": raw_data,
    }

    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nResults saved to {output_path}")

    # Print summary table
    print("\n" + "=" * 80)
    print("SUMMARY: Mode Agility (Phase 6a)")
    print("=" * 80)
    print(f"{'Model':<10} {'Condition':<16} {'Switch%':>8} {'Parse%':>8} {'Content%':>9} {'Cost':>8}")
    print("-" * 65)

    for model_name, cond_map in summary["models"].items():
        for cond, stats in cond_map.items():
            print(
                f"{model_name:<10} {cond:<16} "
                f"{stats['avg_switch_reliability_pct']:>7.1f}% "
                f"{stats['avg_parse_rate_pct']:>7.1f}% "
                f"{stats['avg_content_accuracy_pct']:>8.1f}% "
                f"${stats['avg_cost_usd']:>7.4f}"
            )

    print("-" * 65)
    t = summary["totals"]
    print(f"Total: {t['trials']} trials, ${t['total_cost_usd']:.4f}")

    # Per-step breakdown
    print("\nPer-Step Marker Correctness:")
    print(f"{'Model':<10} {'Condition':<16} ", end="")
    for step in STEP_NAMES:
        print(f"{step:>10}", end="")
    print()
    print("-" * 76)

    for model_name, cond_map in summary["models"].items():
        for cond, stats in cond_map.items():
            print(f"{model_name:<10} {cond:<16} ", end="")
            for step in STEP_NAMES:
                pct = stats["per_step"].get(step, {}).get("correct_marker_pct", 0)
                print(f"{pct:>9.0f}%", end="")
            print()


if __name__ == "__main__":
    main()
