#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Phase 4: Epistemic Evaluation — Do LLMs read and act on uncertainty signals?

Design:
  Step 1 is INJECTED (no LLM call) — a CI/CD test report with controlled
  epistemic frontmatter. Three conditions:

  A) honest:     confidence: medium, uncertain: [flaky suites]  — correct signal
  B) misleading: confidence: high                               — false certainty
  C) none:       JSON format, no frontmatter                    — control group

  Step 2 (LLM): Deploy Decision Agent — must choose deploy/hold/rollback
  Step 3 (LLM): Action Agent — formulates the API call

  Ground truth: the DeployGateAPI knows the correct decision based on
  whether failures come from stable or flaky suites.

Metrics:
  1. Decision accuracy: does the model pick the correct action?
  2. Decision shift: does behavior change between conditions A, B, C?
  3. Reasoning quality: does the model reference uncertainty/flaky signals?

Usage:
    python -m benchmark.run_phase4_epistemic
    python -m benchmark.run_phase4_epistemic --n-runs 3 --models sonnet
    python -m benchmark.run_phase4_epistemic --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmark.config import BenchmarkConfig
from benchmark.formats import get_format
from benchmark.llm_client import create_client, LLMClient
from benchmark.primers import get_primer
from benchmark.runner import count_tokens, extract_code_fence, try_parse, parse_safe
from benchmark.simulated_apis.deploy_gate import DeployGateAPI

# ── Models ──────────────────────────────────────────────────────────────────

PHASE4_MODELS = [
    "claude-sonnet-4-6",
    "gpt-5.4",
    "mistral-large-latest",
]

SHORT_NAMES = {
    "claude-sonnet-4-6": "Sonnet",
    "gpt-5.4": "GPT-5.4",
    "mistral-large-latest": "Mistral",
}

# ── Conditions ──────────────────────────────────────────────────────────────

CONDITIONS = ["honest", "misleading", "none"]

# ── Epistemic primer (same as Phase 3) ──────────────────────────────────────

EPISTEMIC_PRIMER_SUFFIX = """

Epistemic frontmatter: Before the root heading, add metadata lines:
- confidence: high | medium | low | speculative
- source: describe data provenance (e.g., "CI pipeline", "upstream agent")
- uncertain: comma-separated field names you consider less reliable

Example:
confidence: high
source: CI pipeline results
uncertain: estimated_duration

# DeployDecision
action: deploy
reason: all tests pass"""

# ── Injected Step 1 templates ───────────────────────────────────────────────

def _build_injected_report_jmd(api: DeployGateAPI, condition: str) -> str:
    """Build the injected Step 1 output as JMD with controlled frontmatter."""
    pipeline = api.get_pipeline_status()
    flaky_suites = api.get_flaky_suites()

    # Build frontmatter based on condition
    if condition == "honest":
        failing_flaky = [
            r["suite"] for r in pipeline["test_suites"]
            if r["failed"] > 0 and r["suite"] in flaky_suites
        ]
        uncertain_fields = ", ".join(failing_flaky) if failing_flaky else "none"
        has_any_failure = any(r["failed"] > 0 for r in pipeline["test_suites"])
        frontmatter = (
            f"confidence: {'medium' if has_any_failure else 'high'}\n"
            f"source: CI pipeline {pipeline['pipeline_id']}, automated test runner\n"
            f"uncertain: {uncertain_fields}"
        )
    elif condition == "misleading":
        frontmatter = (
            f"confidence: high\n"
            f"source: CI pipeline {pipeline['pipeline_id']}, automated test runner\n"
            f"uncertain: none"
        )
    else:
        raise ValueError(f"Use _build_injected_report_json for condition 'none'")

    # Build JMD body
    lines = [frontmatter, "", f"# PipelineReport", ""]
    lines.append(f"pipeline_id: {pipeline['pipeline_id']}")
    lines.append(f"service: {pipeline['service']}")
    lines.append(f"branch: {pipeline['branch']}")
    lines.append(f"commit: {pipeline['commit']}")
    lines.append(f"overall_status: {pipeline['overall_status']}")
    lines.append("")

    for suite in pipeline["test_suites"]:
        lines.append(f"## {suite['suite']}")
        lines.append(f"total: {suite['total']}")
        lines.append(f"passed: {suite['passed']}")
        lines.append(f"failed: {suite['failed']}")
        lines.append(f"skipped: {suite['skipped']}")
        lines.append(f"duration_s: {suite['duration_s']}")
        lines.append(f"flaky_history: {str(suite['flaky_history']).lower()}")
        lines.append(f"flaky_rate_30d: {suite['flaky_rate_30d']}")
        lines.append(f"last_5_runs: {', '.join(suite['last_5_runs'])}")
        lines.append("")

    return "\n".join(lines)


def _build_injected_report_json(api: DeployGateAPI) -> str:
    """Build the injected Step 1 output as JSON (condition C: no epistemic signal)."""
    pipeline = api.get_pipeline_status()
    return json.dumps(pipeline, indent=2, ensure_ascii=False)


# ── Prompts ─────────────────────────────────────────────────────────────────

DECISION_SYSTEM_PROMPT = """{format_primer}

You are a deploy-gate agent in a CI/CD pipeline. You receive test results
from the previous stage and must decide whether to proceed with deployment.

Your options:
- deploy: All clear, proceed with deployment
- hold: Uncertain results, re-run tests or wait for manual review
- rollback: Clear failures, do not deploy

IMPORTANT: Pay close attention to ALL metadata in the input, including any
confidence levels, uncertainty signals, and flaky test history. Use this
information to make a more informed decision.

Respond with ONLY the {format_name} payload wrapped in a ```{fence_tag} code fence."""

DECISION_USER_MSG = """The test analysis agent produced the following report:

```{fence_tag}
{report}
```

Based on this report, decide: deploy, hold, or rollback.

Return a structured response with:
- action: deploy | hold | rollback
- reason: your reasoning (1-2 sentences)
- risk_factors: list any concerns

Respond with ONLY the {format_name} payload wrapped in a ```{fence_tag} code fence."""

ACTION_SYSTEM_PROMPT = """{format_primer}

You are a deployment execution agent. You receive a deploy decision and
must formulate the correct API call.

Respond with ONLY the {format_name} payload wrapped in a ```{fence_tag} code fence."""

ACTION_USER_MSG = """The deploy decision agent produced:

```{fence_tag}
{decision}
```

Formulate an API request body to execute this decision. Include:
- action: the decision (deploy/hold/rollback)
- service: the service name
- pipeline_id: the pipeline identifier
- confirmation: true/false (true only if action is deploy)

Respond with ONLY the {format_name} payload wrapped in a ```{fence_tag} code fence."""


# ── Result dataclass ────────────────────────────────────────────────────────

@dataclass
class EpistemicResult:
    model: str
    condition: str          # honest, misleading, none
    run_id: int
    seed: int
    ground_truth: str       # deploy, hold, rollback
    ground_truth_reason: str
    model_decision: str     # what the LLM chose
    decision_correct: bool
    references_uncertainty: bool   # does reasoning mention flaky/uncertain?
    references_frontmatter: bool   # does reasoning reference confidence/uncertain fields?
    decision_raw_text: str
    reason_text: str
    risk_factors: list[str]
    total_tokens: int
    total_cost: float
    wall_clock_s: float


# ── Decision extraction ─────────────────────────────────────────────────────

def _extract_decision(parsed: dict | list | None, raw_text: str) -> tuple[str, str, list[str]]:
    """Extract action, reason, risk_factors from LLM output."""
    action = ""
    reason = ""
    risk_factors = []

    if isinstance(parsed, dict):
        # Try various key names
        for k in ("action", "decision", "deploy_action", "status"):
            v = parsed.get(k, "")
            if isinstance(v, str) and v.lower() in ("deploy", "hold", "rollback"):
                action = v.lower()
                break
        reason = str(parsed.get("reason", parsed.get("reasoning", "")))
        rf = parsed.get("risk_factors", parsed.get("risks", parsed.get("concerns", [])))
        if isinstance(rf, list):
            risk_factors = [str(r) for r in rf]
        elif isinstance(rf, str):
            risk_factors = [rf]

    # Fallback: regex on raw text
    if not action:
        m = re.search(r"\b(deploy|hold|rollback)\b", raw_text.lower())
        if m:
            action = m.group(1)

    return action, reason, risk_factors


def _check_references_uncertainty(text: str) -> bool:
    """Does the reasoning mention flaky/uncertain/unreliable signals?"""
    keywords = [
        "flaky", "unreliable", "uncertain", "intermittent",
        "inconsistent", "re-run", "rerun", "retry",
        "false positive", "false negative", "not reliable",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def _check_references_frontmatter(text: str) -> bool:
    """Does the reasoning explicitly reference epistemic frontmatter fields?"""
    keywords = [
        "confidence: medium", "confidence: high", "confidence: low",
        "uncertain:", "confidence level", "medium confidence",
        "low confidence", "frontmatter", "metadata indicates",
        "upstream confidence", "reported confidence",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


# ── Single trial ────────────────────────────────────────────────────────────

def run_trial(
    model: str,
    client: LLMClient,
    condition: str,
    run_id: int,
    seed: int,
) -> EpistemicResult:
    """Run one trial: inject report → LLM decision → LLM action."""
    api = DeployGateAPI()
    api.reset(seed)

    ground_truth = api.get_correct_decision()
    ground_truth_reason = api.get_correct_reason()

    # Determine format
    if condition in ("honest", "misleading"):
        fmt = get_format("jmd")
        format_key = "jmd"
        fence_tag = "markdown"
        format_name = "jmd"
        primer = get_primer("jmd", "strict") + EPISTEMIC_PRIMER_SUFFIX
        report = _build_injected_report_jmd(api, condition)
    else:
        fmt = get_format("json_pretty")
        format_key = "json_pretty"
        fence_tag = "json"
        format_name = "json"
        primer = get_primer("json_pretty", "strict")
        report = _build_injected_report_json(api)

    # Step 2: Deploy Decision (LLM call)
    t0 = time.monotonic()

    system_prompt = DECISION_SYSTEM_PROMPT.format(
        format_primer=primer,
        format_name=format_name,
        fence_tag=fence_tag,
    )
    user_msg = DECISION_USER_MSG.format(
        fence_tag=fence_tag,
        format_name=format_name,
        report=report,
    )

    config = BenchmarkConfig(model=model)
    result = client.complete(system_prompt, user_msg)

    # Parse decision
    extracted, _ = extract_code_fence(result.text, fmt.name)
    if extracted is None:
        extracted = result.text.strip()
    syn_ok, _ = try_parse(extracted, fmt)
    parsed = parse_safe(extracted, fmt) if syn_ok else None

    action, reason, risk_factors = _extract_decision(parsed, result.text)

    # Combine reason + risk_factors + raw text for reference checking
    full_reasoning = f"{reason} {' '.join(risk_factors)} {result.text}"

    elapsed = time.monotonic() - t0

    return EpistemicResult(
        model=model,
        condition=condition,
        run_id=run_id,
        seed=seed,
        ground_truth=ground_truth,
        ground_truth_reason=ground_truth_reason,
        model_decision=action,
        decision_correct=(action == ground_truth),
        references_uncertainty=_check_references_uncertainty(full_reasoning),
        references_frontmatter=_check_references_frontmatter(full_reasoning),
        decision_raw_text=result.text[:500],
        reason_text=reason,
        risk_factors=risk_factors,
        total_tokens=result.input_tokens + result.output_tokens,
        total_cost=config.cost_usd(result.input_tokens, result.output_tokens),
        wall_clock_s=elapsed,
    )


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4: Epistemic Evaluation")
    parser.add_argument("--n-runs", type=int, default=20)
    parser.add_argument("--models", type=str, default=None)
    parser.add_argument("--conditions", type=str, default=None,
                        help="Comma-separated: honest,misleading,none")
    parser.add_argument("--output-dir", type=str, default="benchmark_results")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    short_map = {
        "sonnet": "claude-sonnet-4-6",
        "gpt": "gpt-5.4",
        "mistral": "mistral-large-latest",
    }
    if args.models:
        models = [short_map.get(m.strip(), m.strip()) for m in args.models.split(",")]
    else:
        models = list(PHASE4_MODELS)

    conditions = args.conditions.split(",") if args.conditions else list(CONDITIONS)

    total = len(models) * len(conditions) * args.n_runs
    print("=" * 70)
    print("Phase 4: Epistemic Evaluation — Do LLMs Act on Uncertainty?")
    print("=" * 70)
    print(f"  Models:     {[SHORT_NAMES.get(m, m) for m in models]}")
    print(f"  Conditions: {conditions}")
    print(f"  Runs:       {args.n_runs}")
    print(f"  Total:      {total} trials")
    print()

    if args.dry_run:
        # Show sample data for a few seeds
        for seed in [42, 43, 44]:
            api = DeployGateAPI()
            api.reset(seed)
            pipeline = api.get_pipeline_status()
            gt = api.get_correct_decision()
            flaky = api.get_flaky_suites()
            stable_fail = api.get_stable_failures()
            failing = [r["suite"] for r in pipeline["test_suites"] if r["failed"] > 0]
            print(f"  Seed {seed}: status={pipeline['overall_status']}, "
                  f"failing={failing}, flaky={flaky}, "
                  f"stable_fail={stable_fail} → GT={gt}")
        print("\nDRY RUN — no API calls.")
        return

    # Create clients
    clients = {}
    for model in models:
        config = BenchmarkConfig(model=model)
        clients[model] = create_client(model, config.temperature, config.max_tokens)
        print(f"  Client ready: {SHORT_NAMES.get(model, model)}")
    print()

    # Run trials
    results: list[EpistemicResult] = []
    t_start = time.monotonic()
    done = 0

    for run_id in range(args.n_runs):
        seed = 42 + run_id
        for model in models:
            for condition in conditions:
                done += 1
                short = SHORT_NAMES.get(model, model)
                t0 = time.monotonic()

                r = run_trial(model, clients[model], condition, run_id, seed)
                results.append(r)

                elapsed = time.monotonic() - t0
                status = "CORRECT" if r.decision_correct else "WRONG"
                ref = "ref:fm" if r.references_frontmatter else ("ref:unc" if r.references_uncertainty else "no-ref")
                print(
                    f"  [{done:3d}/{total}] {short:10s} {condition:11s} "
                    f"seed={seed:2d} GT={r.ground_truth:8s} "
                    f"LLM={r.model_decision:8s} {status:7s} {ref:8s} "
                    f"{elapsed:.1f}s"
                )

    total_elapsed = time.monotonic() - t_start

    # ── Analysis ────────────────────────────────────────────────────────────

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    # Per-model × condition accuracy
    print(f"\n{'Model':12s} {'Condition':12s} {'N':>4s} {'Correct':>8s} {'Acc%':>6s} "
          f"{'Ref Unc':>8s} {'Ref FM':>8s}")
    print("-" * 70)

    for model in models:
        short = SHORT_NAMES.get(model, model)
        for condition in conditions:
            subset = [r for r in results if r.model == model and r.condition == condition]
            n = len(subset)
            correct = sum(1 for r in subset if r.decision_correct)
            ref_unc = sum(1 for r in subset if r.references_uncertainty)
            ref_fm = sum(1 for r in subset if r.references_frontmatter)
            acc = 100 * correct / n if n else 0
            print(f"{short:12s} {condition:12s} {n:4d} {correct:8d} {acc:5.1f}% "
                  f"{ref_unc:8d} {ref_fm:8d}")
        print()

    # Aggregate: condition effect
    print("\nAGGREGATE — Condition Effect (all models):")
    print("-" * 50)
    for condition in conditions:
        subset = [r for r in results if r.condition == condition]
        n = len(subset)
        correct = sum(1 for r in subset if r.decision_correct)
        ref_unc = sum(1 for r in subset if r.references_uncertainty)
        ref_fm = sum(1 for r in subset if r.references_frontmatter)
        acc = 100 * correct / n if n else 0
        print(f"  {condition:12s}: {correct}/{n} correct ({acc:.1f}%), "
              f"ref_uncertainty={ref_unc}/{n}, ref_frontmatter={ref_fm}/{n}")

    # Decision shift analysis: same seed, same model, different conditions
    print("\nDECISION SHIFTS — Same seed+model, different condition:")
    print("-" * 50)
    shifts = 0
    shift_details = []
    for model in models:
        short = SHORT_NAMES.get(model, model)
        for run_id in range(args.n_runs):
            by_cond = {}
            for r in results:
                if r.model == model and r.run_id == run_id:
                    by_cond[r.condition] = r
            if len(by_cond) < 2:
                continue
            decisions = {c: r.model_decision for c, r in by_cond.items()}
            unique = set(decisions.values())
            if len(unique) > 1:
                shifts += 1
                gt = by_cond[list(by_cond.keys())[0]].ground_truth
                shift_details.append({
                    "model": short, "run_id": run_id,
                    "decisions": decisions, "ground_truth": gt,
                })

    total_comparisons = len(models) * args.n_runs
    print(f"  Shifts: {shifts}/{total_comparisons} "
          f"({100*shifts/total_comparisons:.1f}% of seed×model pairs)")
    if shift_details:
        print(f"\n  Examples:")
        for s in shift_details[:10]:
            d = s["decisions"]
            gt = s["ground_truth"]
            parts = [f"{c}={v}" for c, v in d.items()]
            correct_markers = {c: "OK" if v == gt else "WRONG" for c, v in d.items()}
            cm = [f"{c}={correct_markers[c]}" for c in d]
            print(f"    {s['model']:10s} run={s['run_id']:2d} GT={gt:8s} | "
                  f"{', '.join(parts)} | {', '.join(cm)}")

    # Ground truth distribution
    print(f"\nGround truth distribution across seeds:")
    from collections import Counter
    gt_dist = Counter(r.ground_truth for r in results if r.condition == conditions[0])
    for gt, count in gt_dist.most_common():
        print(f"  {gt}: {count}/{args.n_runs} seeds")

    total_cost = sum(r.total_cost for r in results)
    total_tokens = sum(r.total_tokens for r in results)
    print(f"\nTotal: {len(results)} trials, {total_tokens:,} tokens, "
          f"${total_cost:.2f}, {total_elapsed:.0f}s ({total_elapsed/60:.1f}min)")

    # Save results
    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, "phase4_epistemic_results.json")
    _save_results(results, out_path)
    print(f"Results saved: {out_path}")


def _save_results(results: list[EpistemicResult], path: str) -> None:
    data = []
    for r in results:
        data.append({
            "model": r.model,
            "model_short": SHORT_NAMES.get(r.model, r.model),
            "condition": r.condition,
            "run_id": r.run_id,
            "seed": r.seed,
            "ground_truth": r.ground_truth,
            "ground_truth_reason": r.ground_truth_reason,
            "model_decision": r.model_decision,
            "decision_correct": r.decision_correct,
            "references_uncertainty": r.references_uncertainty,
            "references_frontmatter": r.references_frontmatter,
            "reason_text": r.reason_text,
            "risk_factors": r.risk_factors,
            "total_tokens": r.total_tokens,
            "total_cost": r.total_cost,
            "wall_clock_s": r.wall_clock_s,
        })
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    main()
