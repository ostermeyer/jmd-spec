#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Phase 6b: Deep Nesting Stress Test — JMD Heading Depth vs. JSON Braces.

Tests whether LLMs maintain syntactic and structural correctness as nesting
depth increases, comparing three format conditions:

  A (jmd_classic):  Standard JMD headings (###, ####, #####, ...)
  B (jmd_numeric):  Numeric depth prefix for depth ≥ 4 (4# Label, 5# Label)
  C (json):         Standard pretty-printed JSON

Scenario: Filesystem Tree
  /project/src/core/internal/handlers/.../file.go
  Each directory has metadata (owner, permissions, modified) and 2-3 entries.
  Only one subdirectory continues deeper — keeps tree narrow (~3 nodes/level).

Depths tested: 2, 3, 4, 5, 6, 8, 10
  depth=2  → 2 directory levels (~6 nodes)
  depth=10 → 10 directory levels (~25 nodes)

Metrics:
  1. Parse rate: syntactically valid output?
  2. Structural depth correctness: correct nesting depth achieved?
  3. Data completeness: all expected nodes present?
  4. Depth degradation curve: at which depth does quality drop?

Usage:
    python -m benchmark.run_phase6b_nesting
    python -m benchmark.run_phase6b_nesting --dry-run
    python -m benchmark.run_phase6b_nesting --n-runs 5 --depths 2 3 4 5 6
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmark.llm_client import create_client, get_pricing
from benchmark.simulated_apis.filesystem import FilesystemAPI

# ── Models ──────────────────────────────────────────────────────────────────

DEFAULT_MODELS = [
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

CONDITIONS = ["jmd_classic", "jmd_numeric", "json"]
DEFAULT_DEPTHS = [2, 3, 4, 5, 6, 8, 10]

# ── Primers ─────────────────────────────────────────────────────────────────

JMD_CLASSIC_PRIMER = """\
You are an API agent. You communicate using JMD (JSON Markdown).

JMD rules:
- # Label starts the root object
- ## key opens a nested object; heading depth = nesting level
- ## key[] declares an array; items start with -
- Fields: key: value (no braces, no quotes on keys)
- Deeper nesting uses more # characters: ###, ####, #####, etc.

Example (filesystem with 3 levels):
# Directory
name: project
type: directory
owner: alice
permissions: drwxr-xr-x
modified: 2026-01-15T10:30:00Z
## entries[]
- name: src
  type: directory
  owner: alice
  permissions: drwxr-xr-x
  modified: 2026-01-14T09:00:00Z
  ### entries[]
  - name: main.go
    type: file
    owner: alice
    permissions: -rw-r--r--
    modified: 2026-01-14T09:00:00Z
    size_bytes: 2048
    file_type: source
    content_hash: sha256:abcd1234
  - name: utils
    type: directory
    owner: bob
    permissions: drwxr-xr-x
    modified: 2026-01-13T14:00:00Z
    #### entries[]
    - name: config.yaml
      type: file
      owner: bob
      permissions: -rw-r--r--
      modified: 2026-01-13T14:00:00Z
      size_bytes: 512
      file_type: config
      content_hash: sha256:ef567890
- name: README.md
  type: file
  owner: alice
  permissions: -rw-r--r--
  modified: 2026-01-10T08:00:00Z
  size_bytes: 4096
  file_type: documentation
  content_hash: sha256:11223344

IMPORTANT: Use the correct number of # for each nesting level. Root = #, first nested entries = ##, deeper entries = ###, etc. Each additional level of directory nesting adds one more #.\
"""

JMD_NUMERIC_PRIMER = """\
You are an API agent. You communicate using JMD (JSON Markdown).

JMD rules:
- # Label starts the root object
- ## key opens a nested object; heading depth = nesting level
- ## key[] declares an array; items start with -
- Fields: key: value (no braces, no quotes on keys)
- For depth 1-3, use standard headings: #, ##, ###
- For depth 4 and deeper, use NUMERIC PREFIX syntax: 4# key, 5# key, 6# key, etc.
  The number indicates the heading depth, followed by a single #.

Example (filesystem with 4 levels):
# Directory
name: project
type: directory
owner: alice
permissions: drwxr-xr-x
modified: 2026-01-15T10:30:00Z
## entries[]
- name: src
  type: directory
  owner: alice
  permissions: drwxr-xr-x
  modified: 2026-01-14T09:00:00Z
  ### entries[]
  - name: core
    type: directory
    owner: bob
    permissions: drwxr-xr-x
    modified: 2026-01-13T14:00:00Z
    4# entries[]
    - name: main.go
      type: file
      owner: bob
      permissions: -rw-r--r--
      modified: 2026-01-13T14:00:00Z
      size_bytes: 2048
      file_type: source
      content_hash: sha256:abcd1234
    - name: internal
      type: directory
      owner: deploy
      permissions: drwx------
      modified: 2026-01-12T11:00:00Z
      5# entries[]
      - name: handler.go
        type: file
        owner: deploy
        permissions: -rw-------
        modified: 2026-01-12T11:00:00Z
        size_bytes: 1024
        file_type: source
        content_hash: sha256:deadbeef

IMPORTANT: Use ### for depth 3, then 4# for depth 4, 5# for depth 5, etc. Never write #### or deeper — always use the numeric prefix for depth ≥ 4.\
"""

JSON_PRIMER = """\
You are an API agent. You communicate using JSON.

Return a valid JSON object representing a filesystem tree.
Each node has: name, type ("directory" or "file"), owner, permissions, modified.
Directories also have an "entries" array containing child nodes.
Files also have: size_bytes, file_type, content_hash.

Always produce valid, properly nested JSON with correct bracket matching.\
"""

# ── Result dataclass ───────────────────────────────────────────────────────


@dataclass
class TrialResult:
    model: str
    condition: str
    depth: int
    seed: int
    raw_output: str
    parses: bool
    max_depth_found: int
    depth_correct: bool
    nodes_expected: int
    nodes_found: int
    completeness_pct: float
    input_tokens: int
    output_tokens: int
    server_ms: float
    cost_usd: float


# ── Detection / validation ──────────────────────────────────────────────────

def _extract_content(text: str) -> str:
    """Strip code fences if present."""
    text = text.strip()
    fence = re.search(r"```(?:markdown|jmd|json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


def _check_parses_jmd(text: str) -> bool:
    """Check if text looks like valid JMD (starts with heading)."""
    content = _extract_content(text)
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        return line.startswith("#") or re.match(r"\d+#\s", line) is not None
    return False


def _check_parses_json(text: str) -> bool:
    """Check if text is valid JSON."""
    content = _extract_content(text)
    try:
        json.loads(content)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def _measure_jmd_depth(text: str) -> int:
    """Find the maximum heading depth in JMD output."""
    content = _extract_content(text)
    max_depth = 0
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Numeric heading: "5# Label"
        m = re.match(r"(\d+)#\s", line)
        if m:
            max_depth = max(max_depth, int(m.group(1)))
            continue
        # Classic heading: "##### Label"
        m = re.match(r"(#{1,15})\s", line)
        if m:
            max_depth = max(max_depth, len(m.group(1)))
    return max_depth


def _measure_json_depth(text: str) -> int:
    """Find the maximum nesting depth of 'entries' arrays in JSON."""
    content = _extract_content(text)
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return 0
    return _json_depth(data)


def _json_depth(node, current: int = 1) -> int:
    """Recursively find max depth via entries arrays."""
    if isinstance(node, dict):
        entries = node.get("entries", [])
        if entries:
            return max(_json_depth(e, current + 1) for e in entries)
        return current
    return current


def _count_nodes_jmd(text: str) -> int:
    """Count how many filesystem nodes appear in JMD output."""
    content = _extract_content(text)
    count = 0
    for line in content.split("\n"):
        line = line.strip()
        # Heading lines (# Directory, ## File, 5# Directory, etc.)
        if re.match(r"(#{1,15}|\d+#)\s+(Directory|File)", line, re.IGNORECASE):
            count += 1
        # Array items with "- name:" indicate a node
        if re.match(r"-\s+name:", line):
            count += 1
    return count


def _count_nodes_json(text: str) -> int:
    """Count filesystem nodes in JSON output."""
    content = _extract_content(text)
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return 0
    return _count_json_nodes(data)


def _count_json_nodes(node) -> int:
    if isinstance(node, dict):
        count = 1  # this node
        for e in node.get("entries", []):
            count += _count_json_nodes(e)
        return count
    return 0


# ── Trial runner ────────────────────────────────────────────────────────────

print_lock = threading.Lock()


def _get_primer(condition: str) -> str:
    return {
        "jmd_classic": JMD_CLASSIC_PRIMER,
        "jmd_numeric": JMD_NUMERIC_PRIMER,
        "json": JSON_PRIMER,
    }[condition]


def _build_prompt(api: FilesystemAPI, condition: str) -> str:
    """Build the user prompt describing the filesystem to reconstruct."""
    depth = api.get_depth()
    nodes = api.get_all_nodes_flat()

    lines = [
        f"Below is a flat listing of {len(nodes)} filesystem entries (directories and files).",
        f"The directory tree has {depth} levels of nesting.",
        "Each entry's parent directory is indicated by 'parent_path'.",
        "",
        "Reconstruct the FULL nested directory tree as a single document.",
        "Every node must appear with ALL its fields.",
        "Directories have an 'entries' array/list containing their children.",
        "",
        "Filesystem listing:",
    ]

    for node in nodes:
        path = node["path"]
        parent = "/".join(path.rsplit("/", 1)[:-1]) or "/"
        ntype = node["type"]

        if ntype == "directory":
            lines.append(
                f"- [{ntype}] {path}/ — owner: {node['owner']}, "
                f"permissions: {node['permissions']}, modified: {node['modified']} "
                f"(parent: {parent})"
            )
        else:
            lines.append(
                f"- [{ntype}] {path} — owner: {node['owner']}, "
                f"permissions: {node['permissions']}, modified: {node['modified']}, "
                f"size: {node['size_bytes']}B, file_type: {node['file_type']}, "
                f"hash: {node['content_hash']} "
                f"(parent: {parent})"
            )

    if condition == "json":
        lines.append("\nReturn the nested tree as a single JSON object.")
    elif condition == "jmd_numeric":
        lines.append(
            "\nReturn the nested tree as JMD. Use ### for depth 3, "
            "then 4# for depth 4, 5# for depth 5, etc."
        )
    else:
        lines.append(
            "\nReturn the nested tree as JMD with heading depth indicating nesting level."
        )

    return "\n".join(lines)


def _run_trial(
    client,
    model: str,
    condition: str,
    depth: int,
    seed: int,
    pricing: tuple[float, float],
) -> TrialResult:
    """Run a single trial: generate filesystem tree at given depth."""
    api = FilesystemAPI()
    api.reset(seed, depth=depth)

    system_prompt = _get_primer(condition)
    user_prompt = _build_prompt(api, condition)

    expected_nodes = api.get_total_nodes()

    result = client.complete(system_prompt, user_prompt)

    raw = result.text
    cost = (result.input_tokens * pricing[0]
            + result.output_tokens * pricing[1]) / 1_000_000

    if condition == "json":
        parses = _check_parses_json(raw)
        max_depth = _measure_json_depth(raw)
        nodes_found = _count_nodes_json(raw)
    else:
        parses = _check_parses_jmd(raw)
        max_depth = _measure_jmd_depth(raw)
        nodes_found = _count_nodes_jmd(raw)

    depth_correct = max_depth >= depth
    completeness = (nodes_found / expected_nodes * 100) if expected_nodes > 0 else 0.0

    return TrialResult(
        model=model,
        condition=condition,
        depth=depth,
        seed=seed,
        raw_output=raw[:3000],  # truncate for storage
        parses=parses,
        max_depth_found=max_depth,
        depth_correct=depth_correct,
        nodes_expected=expected_nodes,
        nodes_found=nodes_found,
        completeness_pct=round(completeness, 1),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        server_ms=result.server_processing_ms,
        cost_usd=cost,
    )


def _run_model_trials(
    model: str,
    n_runs: int,
    depths: list[int],
    seed_base: int,
) -> list[TrialResult]:
    """Run all conditions × depths × runs for one model."""
    pricing = get_pricing(model)
    client = create_client(model, temperature=0.0, max_tokens=8192)
    results: list[TrialResult] = []
    short = SHORT_NAMES.get(model, model)

    for condition in CONDITIONS:
        for depth in depths:
            for run_id in range(n_runs):
                seed = seed_base + depth * 100 + run_id
                t0 = time.monotonic()
                try:
                    trial = _run_trial(client, model, condition, depth, seed, pricing)
                    elapsed = time.monotonic() - t0
                    results.append(trial)

                    with print_lock:
                        print(
                            f"  {short:8s} | {condition:12s} | d={depth:2d} | "
                            f"run {run_id + 1:2d} | parse={'OK' if trial.parses else 'FAIL':4s} | "
                            f"depth={trial.max_depth_found:2d}/{depth:2d} | "
                            f"nodes={trial.nodes_found:2d}/{trial.nodes_expected:2d} | "
                            f"${trial.cost_usd:.4f} | {elapsed:.1f}s"
                        )
                except Exception as e:
                    elapsed = time.monotonic() - t0
                    with print_lock:
                        print(
                            f"  {short:8s} | {condition:12s} | d={depth:2d} | "
                            f"run {run_id + 1:2d} | ERROR: {e} | {elapsed:.1f}s"
                        )

    return results


# ── Aggregation ─────────────────────────────────────────────────────────────

def _aggregate(results: list[TrialResult]) -> dict:
    """Aggregate results by model × condition × depth."""
    groups: dict[str, dict[str, dict[int, list[TrialResult]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for r in results:
        groups[r.model][r.condition][r.depth].append(r)

    summary: dict = {"models": {}, "totals": {}}
    summary["totals"] = {
        "trials": len(results),
        "total_cost_usd": round(sum(r.cost_usd for r in results), 4),
        "total_input_tokens": sum(r.input_tokens for r in results),
        "total_output_tokens": sum(r.output_tokens for r in results),
    }

    for model, cond_map in groups.items():
        model_data: dict = {}
        for condition, depth_map in cond_map.items():
            cond_data: dict = {}
            for depth, trials in sorted(depth_map.items()):
                n = len(trials)
                cond_data[str(depth)] = {
                    "n_trials": n,
                    "parse_rate_pct": round(100 * sum(t.parses for t in trials) / n, 1),
                    "depth_correct_pct": round(100 * sum(t.depth_correct for t in trials) / n, 1),
                    "avg_completeness_pct": round(sum(t.completeness_pct for t in trials) / n, 1),
                    "avg_nodes_found": round(sum(t.nodes_found for t in trials) / n, 1),
                    "avg_nodes_expected": round(sum(t.nodes_expected for t in trials) / n, 1),
                    "avg_max_depth_found": round(sum(t.max_depth_found for t in trials) / n, 1),
                    "avg_cost_usd": round(sum(t.cost_usd for t in trials) / n, 4),
                    "avg_server_ms": round(sum(t.server_ms for t in trials) / n, 1),
                }
            model_data[condition] = cond_data
        summary["models"][model] = model_data

    return summary


# ── Cost estimation ─────────────────────────────────────────────────────────

def _estimate(n_runs: int, depths: list[int], models: list[str]) -> tuple[float, float]:
    """Estimate cost and runtime."""
    total_cost = 0.0
    calls_per_model = n_runs * len(CONDITIONS) * len(depths)

    for model in models:
        pin, pout = get_pricing(model)
        for depth in depths:
            # Filesystem: ~3 nodes/level, prompt ~80 chars/node, output ~120 chars/node
            nodes = 3 * depth
            tokens_in = 500 + nodes * 25    # primer + flat listing
            tokens_out = 300 + nodes * 40   # nested reconstruction
            calls = n_runs * len(CONDITIONS)
            cost = calls * (tokens_in * pin + tokens_out * pout) / 1_000_000
            total_cost += cost

    # ~5s per call, sequential within model, parallel across models
    runtime_s = calls_per_model * 5
    runtime_min = runtime_s / 60

    return total_cost, runtime_min


# ── Summary printing ────────────────────────────────────────────────────────

def _print_summary(summary: dict, depths: list[int]) -> None:
    """Print formatted summary tables."""
    print("\n" + "=" * 80)
    print("SUMMARY: Deep Nesting Stress Test (Phase 6b)")
    print("=" * 80)

    col_w = max(6, max(len(f"d={d}") for d in depths) + 2)

    # Parse rate by depth
    print("\nParse Rate by Depth:")
    header = f"{'Model':<10s} {'Condition':<14s}" + "".join(f"{'d=' + str(d):>{col_w}s}" for d in depths)
    print(header)
    print("-" * len(header))
    for model, cond_map in summary["models"].items():
        short = SHORT_NAMES.get(model, model)
        for condition, depth_map in cond_map.items():
            vals = "".join(
                f"{str(int(depth_map.get(str(d), {}).get('parse_rate_pct', 0))) + '%':>{col_w}s}"
                for d in depths
            )
            print(f"{short:<10s} {condition:<14s}{vals}")

    # Depth correctness
    print("\nDepth Correctness by Depth:")
    print(header)
    print("-" * len(header))
    for model, cond_map in summary["models"].items():
        short = SHORT_NAMES.get(model, model)
        for condition, depth_map in cond_map.items():
            vals = "".join(
                f"{str(int(depth_map.get(str(d), {}).get('depth_correct_pct', 0))) + '%':>{col_w}s}"
                for d in depths
            )
            print(f"{short:<10s} {condition:<14s}{vals}")

    # Completeness
    print("\nData Completeness (avg %) by Depth:")
    print(header)
    print("-" * len(header))
    for model, cond_map in summary["models"].items():
        short = SHORT_NAMES.get(model, model)
        for condition, depth_map in cond_map.items():
            vals = "".join(
                f"{str(int(depth_map.get(str(d), {}).get('avg_completeness_pct', 0))) + '%':>{col_w}s}"
                for d in depths
            )
            print(f"{short:<10s} {condition:<14s}{vals}")

    # Totals
    t = summary["totals"]
    print(f"\nTotal: {t['trials']} trials, ${t['total_cost_usd']:.2f}, "
          f"{t['total_input_tokens']:,} in / {t['total_output_tokens']:,} out tokens")


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6b: Deep Nesting Stress Test")
    parser.add_argument("--n-runs", type=int, default=10)
    parser.add_argument("--seed-base", type=int, default=6200)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--depths", nargs="+", type=int, default=DEFAULT_DEPTHS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="benchmark_results/phase6b_nesting_results.json")
    args = parser.parse_args()

    models = []
    for m in args.models:
        found = [k for k, v in SHORT_NAMES.items() if v.lower() == m.lower()]
        models.append(found[0] if found else m)

    cost_est, time_est = _estimate(args.n_runs, args.depths, models)
    n_calls = args.n_runs * len(CONDITIONS) * len(args.depths) * len(models)

    print(f"Phase 6b: Deep Nesting Stress Test (Filesystem)")
    print(f"  Models: {', '.join(SHORT_NAMES.get(m, m) for m in models)}")
    print(f"  Depths: {args.depths}")
    print(f"  Runs per cell: {args.n_runs}")
    print(f"  Conditions: {', '.join(CONDITIONS)}")
    print(f"  Total API calls: {n_calls}")
    print(f"  Estimated cost: ${cost_est:.2f}")
    print(f"  Estimated runtime: ~{time_est:.0f} min (parallel across models)")

    if args.dry_run:
        print("\n[DRY RUN — exiting]")
        return

    print(f"\nRunning trials (parallel across models)...\n")

    all_results: list[TrialResult] = []
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {
            pool.submit(_run_model_trials, model, args.n_runs, args.depths, args.seed_base): model
            for model in models
        }
        for future in as_completed(futures):
            model = futures[future]
            try:
                model_results = future.result()
                all_results.extend(model_results)
            except Exception as e:
                print(f"\nERROR running {model}: {e}")

    if not all_results:
        print("No results collected.")
        return

    summary = _aggregate(all_results)

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw_trials = [
        {
            "model": t.model,
            "condition": t.condition,
            "depth": t.depth,
            "seed": t.seed,
            "parses": t.parses,
            "max_depth_found": t.max_depth_found,
            "depth_correct": t.depth_correct,
            "nodes_expected": t.nodes_expected,
            "nodes_found": t.nodes_found,
            "completeness_pct": t.completeness_pct,
            "input_tokens": t.input_tokens,
            "output_tokens": t.output_tokens,
            "server_ms": t.server_ms,
            "cost_usd": round(t.cost_usd, 6),
            "raw_output": t.raw_output,
        }
        for t in all_results
    ]

    output = {
        "phase": "6b",
        "name": "Deep Nesting Stress Test (Filesystem)",
        "n_runs": args.n_runs,
        "depths": args.depths,
        "models": models,
        "conditions": CONDITIONS,
        "summary": summary,
        "trials": raw_trials,
    }

    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nResults saved to {output_path}")

    _print_summary(summary, args.depths)


if __name__ == "__main__":
    main()
