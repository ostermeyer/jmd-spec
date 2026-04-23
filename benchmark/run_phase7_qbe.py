#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Phase 7: Query-by-Example — JMD #? vs. MongoDB-style JSON Queries.

Tests whether LLMs can translate natural-language questions into
correct JMD QBE queries (#?) and MongoDB-style JSON filter queries.

10 query types of increasing complexity:
  Q1  Simple equality       (department = Engineering)
  Q2  Comparison            (salary > 100000)
  Q3  Boolean filter        (active = false)
  Q4  Alternation/regex     (department in Engineering, Sales)
  Q5  Nested object         (address.city = Berlin)
  Q6  Projection            (name, email of active employees)
  Q7  Array condition       (skill = Python)
  Q8  Negation              (department != HR)
  Q9  Combined filters      (active + level + salary)
  Q10 Count + pagination    (count of Marketing employees)

Metrics:
  1. Parse rate: syntactically valid query?
  2. Execution rate: query executes without error?
  3. Precision: what fraction of returned results are correct?
  4. Recall: what fraction of expected results are returned?
  5. F1: harmonic mean of precision and recall
  6. Exact match: returned set == expected set?

Usage:
    python -m benchmark.run_phase7_qbe
    python -m benchmark.run_phase7_qbe --dry-run
    python -m benchmark.run_phase7_qbe --n-runs 3
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
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmark.llm_client import create_client, get_pricing
from benchmark.qbe_executor import execute_jmd_qbe, execute_json_query
from benchmark.simulated_apis.employees import EmployeeDirectoryAPI

# ── Models ──────────────────────────────────────────────────────────────────

DEFAULT_MODELS = [
    "claude-sonnet-4-6",
    "gpt-5.4",
    "mistral-large-latest",
]

SHORT_NAMES = {
    "claude-sonnet-4-6": "Sonnet",
    "gpt-5.4": "GPT-5.4",
    "mistral-large-latest": "Mistral",
}

FORMATS = ["jmd", "json"]

# ── Primers ─────────────────────────────────────────────────────────────────

JMD_QBE_PRIMER = """\
You are a data query agent. You communicate using JMD (JSON Markdown) Query-by-Example.

To query data, write a JMD query document using #? as the root marker.
Write an example of the data you want, with filter conditions instead of literal values.

Query syntax:
- #? Label starts a query document
- field: value — equality filter
- field: > 100 — comparison (>, >=, <, <=)
- field: pending|active — regex alternation (matches either)
- field: !value — negation (NOT equal)
- field: !cancelled — NOT cancelled
- field: ? — projection (return this field, no filter)
- ## nested_object — filter on nested object fields
- ## array[] with - item conditions — EXISTS: at least one item matches
- Frontmatter before #? for pagination: page: 1, size: 10
- Bare "count" in frontmatter for count-only queries

Examples:

Find active users in Berlin, show name and email:
#? User
active: true
name: ?
email: ?
## address
city: Berlin

Find orders over $50 in pending or processing status:
#? Order
status: pending|processing
total: > 50

Count cancelled orders:
count

#? Order
status: cancelled

Return ONLY the JMD query document. No explanation.\
"""

JSON_QUERY_PRIMER = """\
You are a data query agent. You write MongoDB-style JSON filter queries.

To query data, write a JSON object with filter conditions.

Query syntax:
- {"field": "value"} — equality
- {"field": {"$gt": 100}} — comparison ($gt, $gte, $lt, $lte)
- {"field": {"$in": ["val1", "val2"]}} — IN list
- {"field": {"$ne": "value"}} — NOT equal
- {"field": {"$regex": "pattern"}} — regex match
- {"address.city": "Berlin"} — nested field (dot notation)
- {"$count": true} — count only
- {"$page": 1, "$size": 10} — pagination

For array element matching, use the field name directly:
- {"skills": "Python"} — array contains "Python"

Return ONLY the JSON query object. No explanation.\
"""


# ── Query definitions ──────────────────────────────────────────────────────

@dataclass
class QueryDef:
    """Definition of a benchmark query."""
    id: str
    name: str
    arm: str  # "instructed" or "task_driven"
    complexity: str
    nl_question: str
    expected_fn: callable | None = None  # (employees) -> set[int] — Arm A only
    required_filter_fields: set[str] = field(default_factory=set)  # Arm B: must-have filters
    selectivity_check: callable | None = None  # Arm B: (employees, result_ids) -> bool


def _define_queries() -> list[QueryDef]:
    """Define 5 instructed + 5 task-driven queries."""
    return [
        # ── Arm A: Instructed (NL → Query translation) ─────────────────

        QueryDef(
            id="A1", name="Simple equality", arm="instructed",
            complexity="basic",
            nl_question="Find all employees in the Engineering department.",
            expected_fn=lambda emps: {
                e["id"] for e in emps if e["department"] == "Engineering"
            },
        ),
        QueryDef(
            id="A2", name="Comparison", arm="instructed",
            complexity="basic",
            nl_question="Find all employees with a salary above 100000.",
            expected_fn=lambda emps: {
                e["id"] for e in emps if e["salary"] > 100000
            },
        ),
        QueryDef(
            id="A3", name="Nested + alternation", arm="instructed",
            complexity="intermediate",
            nl_question=(
                "Find all employees in Engineering or Sales "
                "whose address city is Berlin."
            ),
            expected_fn=lambda emps: {
                e["id"] for e in emps
                if e["department"] in ("Engineering", "Sales")
                and e["address"]["city"] == "Berlin"
            },
        ),
        QueryDef(
            id="A4", name="Array condition", arm="instructed",
            complexity="advanced",
            nl_question="Find all employees who have Python as one of their skills.",
            expected_fn=lambda emps: {
                e["id"] for e in emps if "Python" in e["skills"]
            },
        ),
        QueryDef(
            id="A5", name="Combined filters", arm="instructed",
            complexity="advanced",
            nl_question=(
                "Find active employees at Senior or Lead level "
                "with a salary above 80000."
            ),
            expected_fn=lambda emps: {
                e["id"] for e in emps
                if e["active"]
                and e["level"] in ("Senior", "Lead")
                and e["salary"] > 80000
            },
        ),

        # ── Arm B: Task-driven (Agent decides what to query) ──────────

        QueryDef(
            id="B1", name="Capacity planning", arm="task_driven",
            complexity="strategic",
            nl_question=(
                "You are an HR analyst. The CEO asks whether the Engineering "
                "team has enough senior capacity for a large upcoming project. "
                "Write a query to get the data you need to answer this."
            ),
            required_filter_fields={"department", "level"},
            # Selective = not ALL employees returned (some filtering happened)
            selectivity_check=lambda emps, ids: len(ids) < len(emps),
        ),
        QueryDef(
            id="B2", name="Budget review", arm="task_driven",
            complexity="strategic",
            nl_question=(
                "You are a finance controller. The board wants to know which "
                "employees earn above 120000. Write a query to identify them."
            ),
            required_filter_fields={"salary"},
            selectivity_check=lambda emps, ids: len(ids) < len(emps),
        ),
        QueryDef(
            id="B3", name="Onsite staffing", arm="task_driven",
            complexity="strategic",
            nl_question=(
                "A client in Berlin needs onsite support next week. "
                "You need to find available employees in Berlin. "
                "Write a query to get the relevant data."
            ),
            required_filter_fields={"address"},  # address.city or nested address
            # Berlin might not appear for all seeds — empty result is valid
            selectivity_check=lambda emps, ids: len(ids) < len(emps),
        ),
        QueryDef(
            id="B4", name="Skill matching", arm="task_driven",
            complexity="strategic",
            nl_question=(
                "We are staffing a new Machine Learning project and need "
                "people with Python or Machine Learning skills. "
                "Write a query to find candidates."
            ),
            required_filter_fields={"skills"},
            selectivity_check=lambda emps, ids: len(ids) < len(emps),
        ),
        QueryDef(
            id="B5", name="Data quality audit", arm="task_driven",
            complexity="strategic",
            nl_question=(
                "HR compliance audit: we need to identify all employees "
                "who have no phone number on file. "
                "Write a query to find incomplete records."
            ),
            required_filter_fields={"phone"},
            selectivity_check=lambda emps, ids: len(ids) >= 0,  # Could be 0
        ),
    ]


# ── Result dataclass ──────────────────────────────────────────────────────

@dataclass
class TrialResult:
    model: str
    format_name: str
    query_id: str
    query_name: str
    arm: str  # "instructed" or "task_driven"
    seed: int
    raw_output: str
    parses: bool
    executes: bool
    # Arm A metrics
    expected_ids: list[int] = field(default_factory=list)
    returned_ids: list[int] = field(default_factory=list)
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    exact_match: bool = False
    # Arm B metrics
    required_fields_present: int = 0
    required_fields_total: int = 0
    relevance_pct: float = 0.0
    selective: bool = False  # Not all, not none (unless expected)
    # Shared
    input_tokens: int = 0
    output_tokens: int = 0
    server_ms: float = 0.0
    cost_usd: float = 0.0


# ── Trial runner ──────────────────────────────────────────────────────────

print_lock = threading.Lock()


def _build_context(api: EmployeeDirectoryAPI, format_name: str) -> str:
    """Build the data context to show the LLM (schema + sample)."""
    employees = api.get_employees()

    # Show a compact schema and 2 sample records
    lines = [
        "You have access to an Employee Directory with 10 employee records.",
        "Each employee has these fields:",
        "  id (integer), name (string), email (string),",
        "  department (Engineering|Sales|Marketing|HR|Finance|Operations),",
        "  role (string), level (Junior|Mid|Senior|Lead|Principal),",
        "  salary (number, range 35000-220000), currency (EUR|USD),",
        "  start_date (date), active (boolean),",
        "  skills (array of strings, e.g. Python, JavaScript, Docker),",
        "  address (object: street, city, zip, country),",
        "  projects (array of objects: name, role, hours_per_week),",
        "  manager_id (integer or null), phone (string or null)",
        "",
        "Here are 2 sample records so you know the data shape:",
    ]

    if format_name == "jmd":
        for emp in employees[:2]:
            lines.append(f"  - id: {emp['id']}, name: {emp['name']}, "
                         f"department: {emp['department']}, level: {emp['level']}, "
                         f"salary: {emp['salary']}, active: {str(emp['active']).lower()}, "
                         f"skills: {emp['skills']}, "
                         f"address.city: {emp['address']['city']}")
    else:
        for emp in employees[:2]:
            lines.append(f"  {json.dumps({k: emp[k] for k in ('id', 'name', 'department', 'level', 'salary', 'active')}, ensure_ascii=False)}")
            lines.append(f"    skills: {json.dumps(emp['skills'])}")
            lines.append(f"    address.city: {json.dumps(emp['address']['city'])}")

    return "\n".join(lines)


def _run_trial(
    client,
    model: str,
    format_name: str,
    query_def: QueryDef,
    employees: list[dict],
    context: str,
    seed: int,
    pricing: tuple[float, float],
) -> TrialResult:
    """Run a single QBE trial."""
    if format_name == "jmd":
        system_prompt = JMD_QBE_PRIMER
    else:
        system_prompt = JSON_QUERY_PRIMER

    user_prompt = f"{context}\n\nWrite a query for:\n{query_def.nl_question}"

    result = client.complete(system_prompt, user_prompt)
    raw = result.text
    cost = (result.input_tokens * pricing[0]
            + result.output_tokens * pricing[1]) / 1_000_000

    trial = TrialResult(
        model=model,
        format_name=format_name,
        query_id=query_def.id,
        query_name=query_def.name,
        arm=query_def.arm,
        seed=seed,
        raw_output=raw[:2000],
        parses=False,
        executes=False,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        server_ms=result.server_processing_ms,
        cost_usd=cost,
    )

    # Execute query
    returned_ids_set: set[int] = set()
    try:
        if format_name == "jmd":
            qr = execute_jmd_qbe(raw, employees)
            trial.parses = True
        else:
            qr = execute_json_query(raw, employees)
            trial.parses = True

        trial.executes = True
        returned_ids_set = set(qr.matching_ids)
    except Exception:
        pass

    trial.returned_ids = sorted(returned_ids_set)

    if query_def.arm == "instructed":
        # Arm A: exact match against ground truth
        expected_ids = query_def.expected_fn(employees)
        trial.expected_ids = sorted(expected_ids)

        if returned_ids_set and expected_ids:
            tp = len(returned_ids_set & expected_ids)
            trial.precision = round(tp / len(returned_ids_set), 4) if returned_ids_set else 0
            trial.recall = round(tp / len(expected_ids), 4) if expected_ids else 0
            if trial.precision + trial.recall > 0:
                trial.f1 = round(2 * trial.precision * trial.recall / (trial.precision + trial.recall), 4)
        elif not returned_ids_set and not expected_ids:
            trial.precision = trial.recall = trial.f1 = 1.0

        trial.exact_match = returned_ids_set == expected_ids

    else:
        # Arm B: relevance and selectivity check
        raw_lower = raw.lower()

        # Check required filter fields
        trial.required_fields_total = len(query_def.required_filter_fields)
        for rf in query_def.required_filter_fields:
            # Check if the field name appears in the query output
            # For nested fields like "address", also check "address.city", "city"
            if rf == "address":
                if any(kw in raw_lower for kw in ("address", "city", "stadt")):
                    trial.required_fields_present += 1
            elif rf == "skills":
                if any(kw in raw_lower for kw in ("skills", "python", "machine learning", "ml")):
                    trial.required_fields_present += 1
            else:
                if rf in raw_lower:
                    trial.required_fields_present += 1

        trial.relevance_pct = round(
            100 * trial.required_fields_present / trial.required_fields_total, 1
        ) if trial.required_fields_total else 100.0

        # Selectivity check
        if query_def.selectivity_check and trial.executes:
            trial.selective = query_def.selectivity_check(employees, trial.returned_ids)

    return trial


def _run_model_trials(
    model: str,
    n_runs: int,
    seed_base: int,
    queries: list[QueryDef],
) -> list[TrialResult]:
    """Run all formats × queries × runs for one model."""
    pricing = get_pricing(model)
    client = create_client(model, temperature=0.0, max_tokens=2048)
    results: list[TrialResult] = []
    short = SHORT_NAMES.get(model, model)

    for format_name in FORMATS:
        for run_id in range(n_runs):
            seed = seed_base + run_id
            api = EmployeeDirectoryAPI()
            api.reset(seed)
            employees = api.get_employees()
            context = _build_context(api, format_name)

            for qdef in queries:
                t0 = time.monotonic()
                try:
                    trial = _run_trial(
                        client, model, format_name, qdef,
                        employees, context, seed, pricing,
                    )
                    elapsed = time.monotonic() - t0
                    results.append(trial)

                    with print_lock:
                        if trial.arm == "instructed":
                            status = "EXACT" if trial.exact_match else f"P={trial.precision:.0%} R={trial.recall:.0%}"
                        else:
                            status = f"rel={trial.relevance_pct:.0f}% sel={'Y' if trial.selective else 'N'}"
                        print(
                            f"  {short:8s} | {format_name:4s} | run {run_id + 1:2d} | "
                            f"{qdef.id:3s} {qdef.name:<20s} | "
                            f"{'OK' if trial.parses else 'FAIL':4s} | "
                            f"{status:12s} | ${trial.cost_usd:.4f} | {elapsed:.1f}s"
                        )
                except Exception as e:
                    elapsed = time.monotonic() - t0
                    with print_lock:
                        print(
                            f"  {short:8s} | {format_name:4s} | run {run_id + 1:2d} | "
                            f"{qdef.id:3s} {qdef.name:<20s} | "
                            f"ERROR: {e} | {elapsed:.1f}s"
                        )

    return results


# ── Aggregation ────────────────────────────────────────────────────────────

def _aggregate(results: list[TrialResult]) -> dict:
    """Aggregate results by model × format × query, split by arm."""

    # Split by arm
    arm_a = [r for r in results if r.arm == "instructed"]
    arm_b = [r for r in results if r.arm == "task_driven"]

    summary: dict = {"arm_a": {}, "arm_b": {}, "by_model_format": {}, "totals": {}}

    summary["totals"] = {
        "trials": len(results),
        "total_cost_usd": round(sum(r.cost_usd for r in results), 4),
        "total_input_tokens": sum(r.input_tokens for r in results),
        "total_output_tokens": sum(r.output_tokens for r in results),
    }

    # Arm A: by model × format × query
    groups_a: dict[str, list[TrialResult]] = defaultdict(list)
    for r in arm_a:
        short = SHORT_NAMES.get(r.model, r.model)
        key = f"{short}|{r.format_name}|{r.query_id}"
        groups_a[key].append(r)

    for key, trials in sorted(groups_a.items()):
        n = len(trials)
        summary["arm_a"][key] = {
            "n_trials": n,
            "parse_rate_pct": round(100 * sum(t.parses for t in trials) / n, 1),
            "exec_rate_pct": round(100 * sum(t.executes for t in trials) / n, 1),
            "exact_match_pct": round(100 * sum(t.exact_match for t in trials) / n, 1),
            "avg_precision": round(sum(t.precision for t in trials) / n, 4),
            "avg_recall": round(sum(t.recall for t in trials) / n, 4),
            "avg_f1": round(sum(t.f1 for t in trials) / n, 4),
        }

    # Arm B: by model × format × query
    groups_b: dict[str, list[TrialResult]] = defaultdict(list)
    for r in arm_b:
        short = SHORT_NAMES.get(r.model, r.model)
        key = f"{short}|{r.format_name}|{r.query_id}"
        groups_b[key].append(r)

    for key, trials in sorted(groups_b.items()):
        n = len(trials)
        summary["arm_b"][key] = {
            "n_trials": n,
            "parse_rate_pct": round(100 * sum(t.parses for t in trials) / n, 1),
            "exec_rate_pct": round(100 * sum(t.executes for t in trials) / n, 1),
            "avg_relevance_pct": round(sum(t.relevance_pct for t in trials) / n, 1),
            "selective_pct": round(100 * sum(t.selective for t in trials) / n, 1),
        }

    # Overall by model × format (both arms)
    model_format: dict[str, list[TrialResult]] = defaultdict(list)
    for r in results:
        short = SHORT_NAMES.get(r.model, r.model)
        key = f"{short}|{r.format_name}"
        model_format[key].append(r)

    for key, trials in sorted(model_format.items()):
        n = len(trials)
        a_trials = [t for t in trials if t.arm == "instructed"]
        b_trials = [t for t in trials if t.arm == "task_driven"]
        na = len(a_trials)
        nb = len(b_trials)
        summary["by_model_format"][key] = {
            "n_trials": n,
            "parse_rate_pct": round(100 * sum(t.parses for t in trials) / n, 1),
            "exec_rate_pct": round(100 * sum(t.executes for t in trials) / n, 1),
            "arm_a_exact_match_pct": round(100 * sum(t.exact_match for t in a_trials) / na, 1) if na else 0,
            "arm_a_avg_f1": round(sum(t.f1 for t in a_trials) / na, 4) if na else 0,
            "arm_b_avg_relevance_pct": round(sum(t.relevance_pct for t in b_trials) / nb, 1) if nb else 0,
            "arm_b_selective_pct": round(100 * sum(t.selective for t in b_trials) / nb, 1) if nb else 0,
            "avg_cost_usd": round(sum(t.cost_usd for t in trials) / n, 6),
        }

    return summary


# ── Cost estimation ────────────────────────────────────────────────────────

def _estimate(n_runs: int, models: list[str], n_queries: int) -> tuple[float, float, int]:
    """Estimate cost, runtime, total calls."""
    total_calls = len(models) * len(FORMATS) * n_runs * n_queries
    avg_in = 800   # primer + context + question
    avg_out = 150  # query document

    total_cost = 0.0
    for model in models:
        pin, pout = get_pricing(model)
        n_calls = len(FORMATS) * n_runs * n_queries
        total_cost += n_calls * (avg_in * pin + avg_out * pout) / 1_000_000

    runtime_min = (n_runs * n_queries * len(FORMATS) * 4) / 60  # ~4s per call, parallel models
    return total_cost, runtime_min, total_calls


# ── Summary printing ──────────────────────────────────────────────────────

def _print_summary(summary: dict, queries: list[QueryDef]) -> None:
    """Print formatted summary tables."""
    print("\n" + "=" * 90)
    print("SUMMARY: Query-by-Example Test (Phase 7)")
    print("=" * 90)

    # Overall by model × format
    print("\n┌─ Overall by Model × Format ──────────────────────────────────────────────┐")
    print(f"{'Cell':<20s} {'Parse':>6s} {'Exec':>6s} │ {'A:Exact':>8s} {'A:F1':>6s} │ {'B:Relev':>8s} {'B:Sel':>6s}")
    print("-" * 72)
    for key, cell in sorted(summary["by_model_format"].items()):
        print(
            f"{key:<20s} "
            f"{cell['parse_rate_pct']:5.0f}% "
            f"{cell['exec_rate_pct']:5.0f}% │ "
            f"{cell['arm_a_exact_match_pct']:6.1f}% "
            f"{cell['arm_a_avg_f1']:5.1%} │ "
            f"{cell['arm_b_avg_relevance_pct']:6.1f}% "
            f"{cell['arm_b_selective_pct']:5.1f}%"
        )

    # Arm A: By query
    arm_a_queries = [q for q in queries if q.arm == "instructed"]
    print("\n┌─ Arm A: Instructed Queries (Exact Match) ──────────────────────────────┐")
    for qdef in arm_a_queries:
        jmd_cells = [c for k, c in summary["arm_a"].items() if f"|jmd|{qdef.id}" in k]
        json_cells = [c for k, c in summary["arm_a"].items() if f"|json|{qdef.id}" in k]
        jmd_exact = sum(c["exact_match_pct"] for c in jmd_cells) / len(jmd_cells) if jmd_cells else 0
        json_exact = sum(c["exact_match_pct"] for c in json_cells) / len(json_cells) if json_cells else 0
        jmd_f1 = sum(c["avg_f1"] for c in jmd_cells) / len(jmd_cells) if jmd_cells else 0
        json_f1 = sum(c["avg_f1"] for c in json_cells) / len(json_cells) if json_cells else 0
        print(
            f"  {qdef.id:3s} {qdef.name:<22s} [{qdef.complexity:12s}]  "
            f"JMD: {jmd_exact:5.1f}% exact, F1={jmd_f1:.1%}  │  "
            f"JSON: {json_exact:5.1f}% exact, F1={json_f1:.1%}"
        )

    # Arm B: By query
    arm_b_queries = [q for q in queries if q.arm == "task_driven"]
    print("\n┌─ Arm B: Task-Driven Queries (Relevance + Selectivity) ─────────────────┐")
    for qdef in arm_b_queries:
        jmd_cells = [c for k, c in summary["arm_b"].items() if f"|jmd|{qdef.id}" in k]
        json_cells = [c for k, c in summary["arm_b"].items() if f"|json|{qdef.id}" in k]
        jmd_rel = sum(c["avg_relevance_pct"] for c in jmd_cells) / len(jmd_cells) if jmd_cells else 0
        json_rel = sum(c["avg_relevance_pct"] for c in json_cells) / len(json_cells) if json_cells else 0
        jmd_sel = sum(c["selective_pct"] for c in jmd_cells) / len(jmd_cells) if jmd_cells else 0
        json_sel = sum(c["selective_pct"] for c in json_cells) / len(json_cells) if json_cells else 0
        print(
            f"  {qdef.id:3s} {qdef.name:<22s} [{qdef.complexity:12s}]  "
            f"JMD: {jmd_rel:5.1f}% relev, {jmd_sel:5.1f}% sel  │  "
            f"JSON: {json_rel:5.1f}% relev, {json_sel:5.1f}% sel"
        )

    # Totals
    t = summary["totals"]
    print(f"\nTotal: {t['trials']} trials, ${t['total_cost_usd']:.2f}, "
          f"{t['total_input_tokens']:,} in / {t['total_output_tokens']:,} out tokens")


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 7: QBE Benchmark")
    parser.add_argument("--n-runs", type=int, default=10)
    parser.add_argument("--seed-base", type=int, default=7000)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="benchmark_results/phase7_qbe_results.json")
    args = parser.parse_args()

    queries = _define_queries()
    cost_est, time_est, total_calls = _estimate(args.n_runs, args.models, len(queries))

    print(f"Phase 7: Query-by-Example (Employee Directory)")
    print(f"  Models: {', '.join(SHORT_NAMES.get(m, m) for m in args.models)}")
    print(f"  Formats: {', '.join(FORMATS)}")
    print(f"  Queries: {len(queries)}")
    print(f"  Runs per cell: {args.n_runs}")
    print(f"  Total API calls: {total_calls}")
    print(f"  Estimated cost: ${cost_est:.2f}")
    print(f"  Estimated runtime: ~{time_est:.0f} min")

    if args.dry_run:
        print("\n[DRY RUN — exiting]")
        return

    print(f"\nRunning trials...\n")

    all_results: list[TrialResult] = []
    with ThreadPoolExecutor(max_workers=len(args.models)) as pool:
        futures = {
            pool.submit(_run_model_trials, model, args.n_runs, args.seed_base, queries): model
            for model in args.models
        }
        for future in as_completed(futures):
            model = futures[future]
            short = SHORT_NAMES.get(model, model)
            try:
                model_results = future.result()
                all_results.extend(model_results)
                with print_lock:
                    print(f"\n  ✓ Completed {short} ({len(model_results)} trials)")
            except Exception as e:
                with print_lock:
                    print(f"\n  ✗ ERROR {short}: {e}")

    if not all_results:
        print("No results collected.")
        return

    summary = _aggregate(all_results)

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw_trials = []
    for t in all_results:
        trial_data = {
            "model": t.model,
            "format": t.format_name,
            "query_id": t.query_id,
            "query_name": t.query_name,
            "arm": t.arm,
            "seed": t.seed,
            "parses": t.parses,
            "executes": t.executes,
            "returned_ids": t.returned_ids,
            "input_tokens": t.input_tokens,
            "output_tokens": t.output_tokens,
            "server_ms": t.server_ms,
            "cost_usd": round(t.cost_usd, 6),
            "raw_output": t.raw_output,
        }
        if t.arm == "instructed":
            trial_data.update({
                "exact_match": t.exact_match,
                "precision": t.precision,
                "recall": t.recall,
                "f1": t.f1,
                "expected_ids": t.expected_ids,
            })
        else:
            trial_data.update({
                "relevance_pct": t.relevance_pct,
                "required_fields_present": t.required_fields_present,
                "required_fields_total": t.required_fields_total,
                "selective": t.selective,
            })
        raw_trials.append(trial_data)

    output = {
        "phase": "7",
        "name": "Query-by-Example (Employee Directory)",
        "n_runs": args.n_runs,
        "models": args.models,
        "formats": FORMATS,
        "queries": [{"id": q.id, "name": q.name, "complexity": q.complexity,
                     "question": q.nl_question} for q in queries],
        "summary": summary,
        "trials": raw_trials,
    }

    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nResults saved to {output_path}")

    _print_summary(summary, queries)


if __name__ == "__main__":
    main()
