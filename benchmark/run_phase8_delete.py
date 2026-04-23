#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Phase 8: Delete Documents — JMD #- vs. JSON delete operations.

Tests whether LLMs can produce correct delete documents from
natural-language instructions and business scenarios.

Two arms:
  Arm A (Instructed): Translate a specific delete instruction into a delete document
  Arm B (Task-driven): Given a business scenario, the LLM decides what to delete

Delete test cases:
  D1  Single delete by ID
  D2  Bulk delete by ID list
  D3  Conditional single (employee with lowest salary)
  D4  Conditional bulk (all inactive employees)
  D5  Nested condition bulk (employees in a specific city)
  D6  Offboarding scenario
  D7  Department dissolution
  D8  Compliance cleanup (missing phone)
  D9  Budget restructuring
  D10 Project wind-down

Metrics:
  1. Parse rate: syntactically valid delete document?
  2. Correct marker: uses #- (JMD) or {"_action": "delete"} (JSON)?
  3. ID accuracy: correct employee IDs targeted?
  4. Format correctness: bulk format when multiple targets?

Usage:
    python -m benchmark.run_phase8_delete
    python -m benchmark.run_phase8_delete --dry-run
    python -m benchmark.run_phase8_delete --n-runs 3
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

JMD_DELETE_PRIMER = """\
You are a data management agent. You communicate using JMD (JSON Markdown) Delete documents.

To request deletion of resources, write a JMD delete document using #- as the root marker.

Delete syntax:
- Single resource:
  #- Employee
  id: 5

- Bulk deletion (list of IDs):
  #- []
  - 3
  - 7
  - 9

- Bulk deletion with labels:
  #- Employee[]
  - id: 3
  - id: 7

The body uses the same syntax as JMD data documents (#). The only difference is the #- root marker, which signals deletion intent.

Return ONLY the JMD delete document. No explanation.\
"""

JSON_DELETE_PRIMER = """\
You are a data management agent. You write JSON delete operations.

To request deletion of resources, write a JSON object with "_action": "delete".

Delete syntax:
- Single resource:
  {"_action": "delete", "resource": "Employee", "id": 5}

- Bulk deletion:
  {"_action": "delete", "resource": "Employee", "ids": [3, 7, 9]}

Return ONLY the JSON delete object. No explanation.\
"""


# ── Delete definitions ──────────────────────────────────────────────────────

@dataclass
class DeleteDef:
    """Definition of a benchmark delete task."""
    id: str
    name: str
    arm: str  # "instructed" or "task_driven"
    complexity: str
    nl_instruction: str
    expected_ids_fn: callable  # (employees) -> set[int]
    is_bulk: bool  # expected to produce bulk format?
    # Arm B: required concepts in the output
    required_concepts: set[str] = field(default_factory=set)


def _define_deletes() -> list[DeleteDef]:
    """Define 5 instructed + 5 task-driven delete tasks."""
    return [
        # ── Arm A: Instructed (NL → Delete document) ─────────────────

        DeleteDef(
            id="D1", name="Single delete by ID", arm="instructed",
            complexity="basic",
            nl_instruction="Delete employee with ID 5.",
            expected_ids_fn=lambda emps: {5},
            is_bulk=False,
        ),
        DeleteDef(
            id="D2", name="Bulk delete by ID list", arm="instructed",
            complexity="basic",
            nl_instruction="Delete employees with IDs 2, 6, and 8.",
            expected_ids_fn=lambda emps: {2, 6, 8},
            is_bulk=True,
        ),
        DeleteDef(
            id="D3", name="Conditional single (lowest salary)", arm="instructed",
            complexity="intermediate",
            nl_instruction=(
                "Delete the employee with the lowest salary."
            ),
            expected_ids_fn=lambda emps: {
                min(emps, key=lambda e: e["salary"])["id"]
            },
            is_bulk=False,
        ),
        DeleteDef(
            id="D4", name="Conditional bulk (inactive)", arm="instructed",
            complexity="intermediate",
            nl_instruction="Delete all inactive employees.",
            expected_ids_fn=lambda emps: {
                e["id"] for e in emps if not e["active"]
            },
            is_bulk=True,  # may be single if only 1 inactive
        ),
        DeleteDef(
            id="D5", name="Nested condition (city)", arm="instructed",
            complexity="advanced",
            nl_instruction=(
                "Delete all employees whose address city is Paris."
            ),
            expected_ids_fn=lambda emps: {
                e["id"] for e in emps
                if e["address"]["city"] == "Paris"
            },
            is_bulk=True,
        ),

        # ── Arm B: Task-driven (Agent decides what to delete) ────────

        DeleteDef(
            id="D6", name="Offboarding", arm="task_driven",
            complexity="strategic",
            nl_instruction=(
                "You are an HR system administrator. Employee Eva Garcia "
                "(ID 3) has left the company effective immediately. "
                "Write a delete document to remove her record."
            ),
            expected_ids_fn=lambda emps: {3},
            is_bulk=False,
            required_concepts={"3", "id"},
        ),
        DeleteDef(
            id="D7", name="Department dissolution", arm="task_driven",
            complexity="strategic",
            nl_instruction=(
                "The board has decided to dissolve the HR department and "
                "outsource all HR functions. Write a delete document to "
                "remove all HR department employees from the directory."
            ),
            expected_ids_fn=lambda emps: {
                e["id"] for e in emps if e["department"] == "HR"
            },
            is_bulk=True,
            required_concepts={"hr"},
        ),
        DeleteDef(
            id="D8", name="Compliance cleanup", arm="task_driven",
            complexity="strategic",
            nl_instruction=(
                "GDPR audit: all employee records without a phone number "
                "must be flagged for deletion until contact data is provided. "
                "Write a delete document for these incomplete records."
            ),
            expected_ids_fn=lambda emps: {
                e["id"] for e in emps if e["phone"] is None
            },
            is_bulk=True,
            required_concepts={"phone"},
        ),
        DeleteDef(
            id="D9", name="Budget restructuring", arm="task_driven",
            complexity="strategic",
            nl_instruction=(
                "Budget crisis: management decided to let go of all Junior-level "
                "employees. Write a delete document to remove them."
            ),
            expected_ids_fn=lambda emps: {
                e["id"] for e in emps if e["level"] == "Junior"
            },
            is_bulk=True,
            required_concepts={"junior"},
        ),
        DeleteDef(
            id="D10", name="Project wind-down", arm="task_driven",
            complexity="strategic",
            nl_instruction=(
                "The 'Atlas' project is being shut down. All employees "
                "who are exclusively assigned to Atlas (their only project) "
                "should be removed from the directory. Write the delete document."
            ),
            expected_ids_fn=lambda emps: {
                e["id"] for e in emps
                if len(e["projects"]) == 1
                and e["projects"][0]["name"] == "Atlas"
            },
            is_bulk=True,
            required_concepts={"atlas"},
        ),
    ]


# ── Result dataclass ──────────────────────────────────────────────────────

@dataclass
class TrialResult:
    model: str
    format_name: str
    delete_id: str
    delete_name: str
    arm: str
    seed: int
    raw_output: str
    parses: bool
    correct_marker: bool
    # ID accuracy
    expected_ids: list[int] = field(default_factory=list)
    extracted_ids: list[int] = field(default_factory=list)
    id_precision: float = 0.0
    id_recall: float = 0.0
    id_f1: float = 0.0
    id_exact_match: bool = False
    # Arm B: concept presence
    required_concepts_present: int = 0
    required_concepts_total: int = 0
    concept_coverage_pct: float = 0.0
    # Shared
    input_tokens: int = 0
    output_tokens: int = 0
    server_ms: float = 0.0
    cost_usd: float = 0.0


# ── Parsing / evaluation helpers ─────────────────────────────────────────

def _extract_jmd_delete(raw: str) -> tuple[bool, bool, set[int]]:
    """Parse a JMD delete document, return (parses, correct_marker, ids).

    Tolerant of code fences and minor formatting variations.
    """
    text = raw.strip()

    # Detect "nothing to delete" responses (valid when expected set is empty)
    nothing_phrases = [
        "nothing to delete", "no employees", "no records",
        "there is nothing", "there are no", "no deletions",
        "nothing matches", "no matching",
    ]
    text_lower = text.lower()
    if any(p in text_lower for p in nothing_phrases):
        # Check if there's still a #- marker somewhere
        has_marker = any(
            line.strip().startswith("#-")
            for line in text.split("\n")
        )
        if not has_marker:
            # Valid "empty delete" — parses OK, marker N/A, no IDs
            return True, True, set()

    # Strip code fences
    if "```" in text:
        lines = text.split("\n")
        inside = False
        extracted = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                # Content after opening ``` on same line (e.g. ```#- Employee[])
                remainder = stripped[3:].strip()
                if not inside and remainder:
                    # Language tag like ```markdown — skip
                    if not remainder.startswith("#"):
                        inside = True
                        continue
                    extracted.append(remainder)
                inside = not inside
                continue
            if inside:
                extracted.append(line)
        if extracted:
            text = "\n".join(extracted).strip()

    lines = text.split("\n")

    # Find #- marker
    correct_marker = False
    ids: set[int] = set()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#-"):
            correct_marker = True
            break

    if not correct_marker:
        return False, False, set()

    # Extract IDs from the document
    for line in lines:
        stripped = line.strip()

        # id: N
        m = re.match(r"(?:- )?id:\s*(\d+)", stripped)
        if m:
            ids.add(int(m.group(1)))
            continue

        # Bare list item: - N
        m = re.match(r"-\s+(\d+)\s*$", stripped)
        if m:
            ids.add(int(m.group(1)))
            continue

    return bool(ids) or correct_marker, correct_marker, ids


def _extract_json_delete(raw: str) -> tuple[bool, bool, set[int]]:
    """Parse a JSON delete document, return (parses, correct_marker, ids)."""
    text = raw.strip()

    # Strip code fences
    if "```" in text:
        lines = text.split("\n")
        inside = False
        extracted = []
        for line in lines:
            if line.strip().startswith("```"):
                inside = not inside
                continue
            if inside:
                extracted.append(line)
        if extracted:
            text = "\n".join(extracted).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON in the text
        m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if not m:
            return False, False, set()
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return False, False, set()

    if not isinstance(data, dict):
        return False, False, set()

    # Check for delete marker
    action = data.get("_action", data.get("action", "")).lower()
    correct_marker = action == "delete"

    # Extract IDs
    ids: set[int] = set()

    # Single: {"id": N}
    if "id" in data:
        try:
            ids.add(int(data["id"]))
        except (ValueError, TypeError):
            pass

    # Bulk: {"ids": [N, ...]}
    if "ids" in data:
        for item in data["ids"]:
            try:
                ids.add(int(item))
            except (ValueError, TypeError):
                if isinstance(item, dict) and "id" in item:
                    try:
                        ids.add(int(item["id"]))
                    except (ValueError, TypeError):
                        pass

    # Also check "employees" array
    if "employees" in data:
        for item in data["employees"]:
            if isinstance(item, dict) and "id" in item:
                try:
                    ids.add(int(item["id"]))
                except (ValueError, TypeError):
                    pass
            elif isinstance(item, (int, float)):
                ids.add(int(item))

    return True, correct_marker, ids


# ── Trial runner ──────────────────────────────────────────────────────────

print_lock = threading.Lock()


def _build_context(api: EmployeeDirectoryAPI, format_name: str) -> str:
    """Build the data context showing all employees (needed for conditional deletes)."""
    employees = api.get_employees()

    lines = [
        "You have access to an Employee Directory with 10 employee records.",
        "Here is the current data:",
        "",
    ]

    if format_name == "jmd":
        for emp in employees:
            active_str = str(emp["active"]).lower()
            phone_str = emp["phone"] if emp["phone"] else "null"
            projects_str = ", ".join(p["name"] for p in emp["projects"])
            lines.append(
                f"  id: {emp['id']}, name: {emp['name']}, "
                f"department: {emp['department']}, level: {emp['level']}, "
                f"salary: {emp['salary']}, active: {active_str}, "
                f"phone: {phone_str}, "
                f"city: {emp['address']['city']}, "
                f"skills: {emp['skills']}, "
                f"projects: [{projects_str}]"
            )
    else:
        for emp in employees:
            projects_str = ", ".join(p["name"] for p in emp["projects"])
            compact = {
                "id": emp["id"], "name": emp["name"],
                "department": emp["department"], "level": emp["level"],
                "salary": emp["salary"], "active": emp["active"],
                "phone": emp["phone"],
                "address.city": emp["address"]["city"],
                "projects": [p["name"] for p in emp["projects"]],
            }
            lines.append(f"  {json.dumps(compact, ensure_ascii=False)}")

    return "\n".join(lines)


def _run_trial(
    client,
    model: str,
    format_name: str,
    delete_def: DeleteDef,
    employees: list[dict],
    context: str,
    seed: int,
    pricing: tuple[float, float],
) -> TrialResult:
    """Run a single delete trial."""
    if format_name == "jmd":
        system_prompt = JMD_DELETE_PRIMER
    else:
        system_prompt = JSON_DELETE_PRIMER

    user_prompt = f"{context}\n\n{delete_def.nl_instruction}"

    result = client.complete(system_prompt, user_prompt)
    raw = result.text
    cost = (result.input_tokens * pricing[0]
            + result.output_tokens * pricing[1]) / 1_000_000

    trial = TrialResult(
        model=model,
        format_name=format_name,
        delete_id=delete_def.id,
        delete_name=delete_def.name,
        arm=delete_def.arm,
        seed=seed,
        raw_output=raw[:2000],
        parses=False,
        correct_marker=False,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        server_ms=result.server_processing_ms,
        cost_usd=cost,
    )

    # Parse the output
    if format_name == "jmd":
        parses, correct_marker, extracted_ids = _extract_jmd_delete(raw)
    else:
        parses, correct_marker, extracted_ids = _extract_json_delete(raw)

    trial.parses = parses
    trial.correct_marker = correct_marker
    trial.extracted_ids = sorted(extracted_ids)

    # Compute expected IDs
    expected_ids = delete_def.expected_ids_fn(employees)
    trial.expected_ids = sorted(expected_ids)

    # ID accuracy
    if extracted_ids and expected_ids:
        tp = len(extracted_ids & expected_ids)
        trial.id_precision = round(tp / len(extracted_ids), 4) if extracted_ids else 0
        trial.id_recall = round(tp / len(expected_ids), 4) if expected_ids else 0
        if trial.id_precision + trial.id_recall > 0:
            trial.id_f1 = round(
                2 * trial.id_precision * trial.id_recall
                / (trial.id_precision + trial.id_recall), 4
            )
    elif not extracted_ids and not expected_ids:
        trial.id_precision = trial.id_recall = trial.id_f1 = 1.0

    trial.id_exact_match = extracted_ids == expected_ids

    # Arm B: concept coverage
    if delete_def.arm == "task_driven" and delete_def.required_concepts:
        raw_lower = raw.lower()
        trial.required_concepts_total = len(delete_def.required_concepts)
        for concept in delete_def.required_concepts:
            if concept.lower() in raw_lower:
                trial.required_concepts_present += 1
        trial.concept_coverage_pct = round(
            100 * trial.required_concepts_present / trial.required_concepts_total, 1
        )

    return trial


def _run_model_trials(
    model: str,
    n_runs: int,
    seed_base: int,
    deletes: list[DeleteDef],
) -> list[TrialResult]:
    """Run all formats × deletes × runs for one model."""
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

            for ddef in deletes:
                t0 = time.monotonic()
                try:
                    trial = _run_trial(
                        client, model, format_name, ddef,
                        employees, context, seed, pricing,
                    )
                    elapsed = time.monotonic() - t0
                    results.append(trial)

                    with print_lock:
                        marker_ok = "M:Y" if trial.correct_marker else "M:N"
                        id_ok = "EXACT" if trial.id_exact_match else f"P={trial.id_precision:.0%} R={trial.id_recall:.0%}"
                        print(
                            f"  {short:8s} | {format_name:4s} | run {run_id + 1:2d} | "
                            f"{ddef.id:3s} {ddef.name:<28s} | "
                            f"{'OK' if trial.parses else 'FAIL':4s} | "
                            f"{marker_ok} | {id_ok:12s} | "
                            f"${trial.cost_usd:.4f} | {elapsed:.1f}s"
                        )
                except Exception as e:
                    elapsed = time.monotonic() - t0
                    with print_lock:
                        print(
                            f"  {short:8s} | {format_name:4s} | run {run_id + 1:2d} | "
                            f"{ddef.id:3s} {ddef.name:<28s} | "
                            f"ERROR: {e} | {elapsed:.1f}s"
                        )

    return results


# ── Aggregation ────────────────────────────────────────────────────────────

def _aggregate(results: list[TrialResult]) -> dict:
    """Aggregate results by model × format × delete, split by arm."""

    arm_a = [r for r in results if r.arm == "instructed"]
    arm_b = [r for r in results if r.arm == "task_driven"]

    summary: dict = {"arm_a": {}, "arm_b": {}, "by_model_format": {}, "totals": {}}

    summary["totals"] = {
        "trials": len(results),
        "total_cost_usd": round(sum(r.cost_usd for r in results), 4),
        "total_input_tokens": sum(r.input_tokens for r in results),
        "total_output_tokens": sum(r.output_tokens for r in results),
    }

    # Arm A: by model × format × delete
    groups_a: dict[str, list[TrialResult]] = defaultdict(list)
    for r in arm_a:
        short = SHORT_NAMES.get(r.model, r.model)
        key = f"{short}|{r.format_name}|{r.delete_id}"
        groups_a[key].append(r)

    for key, trials in sorted(groups_a.items()):
        n = len(trials)
        summary["arm_a"][key] = {
            "n_trials": n,
            "parse_rate_pct": round(100 * sum(t.parses for t in trials) / n, 1),
            "marker_rate_pct": round(100 * sum(t.correct_marker for t in trials) / n, 1),
            "id_exact_match_pct": round(100 * sum(t.id_exact_match for t in trials) / n, 1),
            "avg_id_precision": round(sum(t.id_precision for t in trials) / n, 4),
            "avg_id_recall": round(sum(t.id_recall for t in trials) / n, 4),
            "avg_id_f1": round(sum(t.id_f1 for t in trials) / n, 4),
        }

    # Arm B: by model × format × delete
    groups_b: dict[str, list[TrialResult]] = defaultdict(list)
    for r in arm_b:
        short = SHORT_NAMES.get(r.model, r.model)
        key = f"{short}|{r.format_name}|{r.delete_id}"
        groups_b[key].append(r)

    for key, trials in sorted(groups_b.items()):
        n = len(trials)
        summary["arm_b"][key] = {
            "n_trials": n,
            "parse_rate_pct": round(100 * sum(t.parses for t in trials) / n, 1),
            "marker_rate_pct": round(100 * sum(t.correct_marker for t in trials) / n, 1),
            "id_exact_match_pct": round(100 * sum(t.id_exact_match for t in trials) / n, 1),
            "avg_id_precision": round(sum(t.id_precision for t in trials) / n, 4),
            "avg_id_recall": round(sum(t.id_recall for t in trials) / n, 4),
            "avg_id_f1": round(sum(t.id_f1 for t in trials) / n, 4),
            "avg_concept_coverage_pct": round(sum(t.concept_coverage_pct for t in trials) / n, 1),
        }

    # Overall by model × format
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
            "marker_rate_pct": round(100 * sum(t.correct_marker for t in trials) / n, 1),
            "id_exact_match_pct": round(100 * sum(t.id_exact_match for t in trials) / n, 1),
            "arm_a_exact_pct": round(100 * sum(t.id_exact_match for t in a_trials) / na, 1) if na else 0,
            "arm_b_exact_pct": round(100 * sum(t.id_exact_match for t in b_trials) / nb, 1) if nb else 0,
            "avg_cost_usd": round(sum(t.cost_usd for t in trials) / n, 6),
        }

    return summary


# ── Cost estimation ────────────────────────────────────────────────────────

def _estimate(n_runs: int, models: list[str], n_deletes: int) -> tuple[float, float, int]:
    """Estimate cost, runtime, total calls."""
    total_calls = len(models) * len(FORMATS) * n_runs * n_deletes
    avg_in = 1200   # primer + full employee listing + instruction
    avg_out = 80    # delete document (compact)

    total_cost = 0.0
    for model in models:
        pin, pout = get_pricing(model)
        n_calls = len(FORMATS) * n_runs * n_deletes
        total_cost += n_calls * (avg_in * pin + avg_out * pout) / 1_000_000

    runtime_min = (n_runs * n_deletes * len(FORMATS) * 3) / 60
    return total_cost, runtime_min, total_calls


# ── Summary printing ──────────────────────────────────────────────────────

def _print_summary(summary: dict, deletes: list[DeleteDef]) -> None:
    """Print formatted summary tables."""
    print("\n" + "=" * 90)
    print("SUMMARY: Delete Documents Test (Phase 8)")
    print("=" * 90)

    # Overall by model × format
    print("\n┌─ Overall by Model × Format ──────────────────────────────────────────────┐")
    print(f"{'Cell':<20s} {'Parse':>6s} {'Marker':>7s} {'ID-Ex':>6s} │ {'A:Exact':>8s} {'B:Exact':>8s}")
    print("-" * 68)
    for key, cell in sorted(summary["by_model_format"].items()):
        print(
            f"{key:<20s} "
            f"{cell['parse_rate_pct']:5.0f}% "
            f"{cell['marker_rate_pct']:5.0f}% "
            f"{cell['id_exact_match_pct']:5.0f}% │ "
            f"{cell['arm_a_exact_pct']:6.1f}% "
            f"{cell['arm_b_exact_pct']:6.1f}%"
        )

    # Arm A: By delete task
    arm_a_defs = [d for d in deletes if d.arm == "instructed"]
    print("\n┌─ Arm A: Instructed Deletes (ID Exact Match) ──────────────────────────────┐")
    for ddef in arm_a_defs:
        jmd_cells = [c for k, c in summary["arm_a"].items() if f"|jmd|{ddef.id}" in k]
        json_cells = [c for k, c in summary["arm_a"].items() if f"|json|{ddef.id}" in k]
        jmd_exact = sum(c["id_exact_match_pct"] for c in jmd_cells) / len(jmd_cells) if jmd_cells else 0
        json_exact = sum(c["id_exact_match_pct"] for c in json_cells) / len(json_cells) if json_cells else 0
        jmd_marker = sum(c["marker_rate_pct"] for c in jmd_cells) / len(jmd_cells) if jmd_cells else 0
        json_marker = sum(c["marker_rate_pct"] for c in json_cells) / len(json_cells) if json_cells else 0
        print(
            f"  {ddef.id:3s} {ddef.name:<30s} [{ddef.complexity:12s}]  "
            f"JMD: {jmd_exact:5.1f}% exact, {jmd_marker:5.1f}% marker  │  "
            f"JSON: {json_exact:5.1f}% exact, {json_marker:5.1f}% marker"
        )

    # Arm B: By delete task
    arm_b_defs = [d for d in deletes if d.arm == "task_driven"]
    print("\n┌─ Arm B: Task-Driven Deletes (ID Exact Match + Concepts) ─────────────────┐")
    for ddef in arm_b_defs:
        jmd_cells = [c for k, c in summary["arm_b"].items() if f"|jmd|{ddef.id}" in k]
        json_cells = [c for k, c in summary["arm_b"].items() if f"|json|{ddef.id}" in k]
        jmd_exact = sum(c["id_exact_match_pct"] for c in jmd_cells) / len(jmd_cells) if jmd_cells else 0
        json_exact = sum(c["id_exact_match_pct"] for c in json_cells) / len(json_cells) if json_cells else 0
        jmd_concept = sum(c["avg_concept_coverage_pct"] for c in jmd_cells) / len(jmd_cells) if jmd_cells else 0
        json_concept = sum(c["avg_concept_coverage_pct"] for c in json_cells) / len(json_cells) if json_cells else 0
        print(
            f"  {ddef.id:3s} {ddef.name:<24s} [{ddef.complexity:12s}]  "
            f"JMD: {jmd_exact:5.1f}% exact, {jmd_concept:5.1f}% concept  │  "
            f"JSON: {json_exact:5.1f}% exact, {json_concept:5.1f}% concept"
        )

    # Totals
    t = summary["totals"]
    print(f"\nTotal: {t['trials']} trials, ${t['total_cost_usd']:.2f}, "
          f"{t['total_input_tokens']:,} in / {t['total_output_tokens']:,} out tokens")


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 8: Delete Documents Benchmark")
    parser.add_argument("--n-runs", type=int, default=10)
    parser.add_argument("--seed-base", type=int, default=8000)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="benchmark_results/phase8_delete_results.json")
    args = parser.parse_args()

    deletes = _define_deletes()
    cost_est, time_est, total_calls = _estimate(args.n_runs, args.models, len(deletes))

    print(f"Phase 8: Delete Documents (Employee Directory)")
    print(f"  Models: {', '.join(SHORT_NAMES.get(m, m) for m in args.models)}")
    print(f"  Formats: {', '.join(FORMATS)}")
    print(f"  Delete tasks: {len(deletes)}")
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
            pool.submit(_run_model_trials, model, args.n_runs, args.seed_base, deletes): model
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
            "delete_id": t.delete_id,
            "delete_name": t.delete_name,
            "arm": t.arm,
            "seed": t.seed,
            "parses": t.parses,
            "correct_marker": t.correct_marker,
            "extracted_ids": t.extracted_ids,
            "expected_ids": t.expected_ids,
            "id_exact_match": t.id_exact_match,
            "id_precision": t.id_precision,
            "id_recall": t.id_recall,
            "id_f1": t.id_f1,
            "input_tokens": t.input_tokens,
            "output_tokens": t.output_tokens,
            "server_ms": t.server_ms,
            "cost_usd": round(t.cost_usd, 6),
            "raw_output": t.raw_output,
        }
        if t.arm == "task_driven":
            trial_data["concept_coverage_pct"] = t.concept_coverage_pct
        raw_trials.append(trial_data)

    output = {
        "phase": "8",
        "name": "Delete Documents (Employee Directory)",
        "n_runs": args.n_runs,
        "models": args.models,
        "formats": FORMATS,
        "deletes": [{"id": d.id, "name": d.name, "complexity": d.complexity,
                     "instruction": d.nl_instruction, "is_bulk": d.is_bulk}
                    for d in deletes],
        "summary": summary,
        "trials": raw_trials,
    }

    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nResults saved to {output_path}")

    _print_summary(summary, deletes)


if __name__ == "__main__":
    main()
