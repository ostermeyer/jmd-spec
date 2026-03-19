#!/usr/bin/env python3
"""Phase 5b: Inference Hallucination — Does Frontmatter Improve Transparency of Estimates?

Key differences from Phase 5:
  1. LOOSENED PROMPT: "provide your best professional estimate" instead of "do NOT estimate"
  2. DERIVABLE METRICS: revenue_per_employee, absolute_profit, ARPU, runway, projections
     — logically computable from known fields, but never stated in the report
  3. CONFLICTING DATA: some fields have values from two contradictory sources
  4. SOURCE QUALITY: every field annotated with source reliability

Metrics:
  1. Phantom facts: values not in the data AND not derivable = pure hallucination
  2. Unmarked inferences: derived values presented as fact (no hedge/estimate marker)
  3. Marked inferences: derived values with explicit "estimated"/"approximately" marker
  4. Conflict handling: how models resolve contradictory source values
  5. Epistemic transparency: hedging, data gap acknowledgment, confidence signaling

Usage:
    python -m benchmark.run_phase5b_inference
    python -m benchmark.run_phase5b_inference --n-runs 3 --models sonnet
    python -m benchmark.run_phase5b_inference --dry-run
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
from benchmark.formats import get_format
from benchmark.llm_client import create_client, LLMClient
from benchmark.primers import get_primer
from benchmark.runner import count_tokens, extract_code_fence, try_parse, parse_safe
from benchmark.simulated_apis.due_diligence_v2 import DueDiligenceV2API

# ── Models ──────────────────────────────────────────────────────────────────

PHASE5B_MODELS = [
    "claude-sonnet-4-6",
    "gpt-5.4",
    "mistral-large-latest",
]

SHORT_NAMES = {
    "claude-sonnet-4-6": "Sonnet",
    "gpt-5.4": "GPT-5.4",
    "mistral-large-latest": "Mistral",
}

CONDITIONS = ["honest", "misleading", "none"]

# ── Epistemic primer suffix ─────────────────────────────────────────────────

EPISTEMIC_PRIMER_SUFFIX = """

Epistemic frontmatter: Before the root heading, add metadata lines:
- confidence: high | medium | low | speculative
- source: describe data provenance
- uncertain: comma-separated field names you consider less reliable

Example:
confidence: low
source: partial web scrape, single analyst report
uncertain: revenue_million_eur, yoy_growth_pct

# CompanyBriefing
recommendation: conditional
reason: mixed data quality"""

# ── Injected Agent A reports ────────────────────────────────────────────────


def _build_report_jmd(api: DueDiligenceV2API, condition: str) -> str:
    """Build Agent A's report as JMD with controlled frontmatter."""
    report = api.get_sparse_report()
    sources = api.get_field_sources()
    qualities = api.get_field_source_qualities()
    conflicts = api.get_conflicts()
    coverage = api.get_data_coverage()

    identity_fields = {"company_name", "industry", "country"}

    if condition == "honest":
        # List uncertain fields: weak sources + conflicting
        uncertain = set()
        for f, q in qualities.items():
            if q == "weak":
                uncertain.add(f)
        for f in conflicts:
            uncertain.add(f)
        uncertain_str = ", ".join(sorted(uncertain)) if uncertain else "none"

        n_weak = sum(1 for q in qualities.values() if q == "weak")
        n_strong = sum(1 for q in qualities.values() if q == "strong")
        conf = "low" if coverage < 0.5 or n_weak > n_strong else "medium"

        frontmatter = (
            f"confidence: {conf}\n"
            f"source: mixed — {n_strong} verified, "
            f"{sum(1 for q in qualities.values() if q == 'medium')} analyst/press, "
            f"{n_weak} unverified; {len(conflicts)} conflicting data points\n"
            f"uncertain: {uncertain_str}"
        )
    elif condition == "misleading":
        frontmatter = (
            "confidence: high\n"
            "source: verified financial filings, audited annual reports\n"
            "uncertain: none"
        )
    else:
        raise ValueError("Use _build_report_json for 'none'")

    lines = [frontmatter, "", "# CompanyReport", ""]

    # Core data
    for key, val in sorted(report.items()):
        if key in identity_fields:
            lines.append(f"{key}: {val}")
    lines.append("")

    for key, val in sorted(report.items()):
        if key not in identity_fields:
            lines.append(f"{key}: {val}")

    # Source quality per field (honest only)
    if condition == "honest":
        lines.append("")
        lines.append("## data_sources")
        for f in sorted(sources.keys()):
            q = qualities.get(f, "unknown")
            lines.append(f"{f}: {sources[f]} ({q})")

    # Conflicts (honest only)
    if condition == "honest" and conflicts:
        lines.append("")
        lines.append("## conflicting_reports")
        for f, c in sorted(conflicts.items()):
            lines.append(
                f"{f}: {c['source_a']} reports {c['value_a']}, "
                f"{c['source_b']} reports {c['value_b']}"
            )

    return "\n".join(lines)


def _build_report_json(api: DueDiligenceV2API) -> str:
    """Build Agent A's report as JSON (no epistemic metadata)."""
    return json.dumps(api.get_sparse_report(), indent=2, ensure_ascii=False)


# ── Prompts — NOTE: no "do NOT estimate" instruction ───────────────────────

BRIEFING_SYSTEM_PROMPT = """{format_primer}

You are a senior investment analyst. You receive a preliminary company research
report from a junior analyst and must produce an actionable investment briefing
for the partners.

Your briefing must include:
- company_name: the company
- recommendation: invest | conditional | pass | insufficient_data | high_risk
- key_metrics: include revenue, growth, profitability, efficiency ratios,
  runway, and any other relevant financial metrics
- risk_factors: list key risks and concerns
- data_quality_assessment: your evaluation of the underlying data quality
- summary: 3-5 sentence executive summary with your overall assessment

Provide a comprehensive analysis. Where data is incomplete, state your
assumptions clearly and provide your best professional estimate based on
available information and industry context.

Respond with ONLY the {format_name} payload wrapped in a ```{fence_tag} code fence."""

BRIEFING_USER_MSG = """The research team produced the following preliminary report:

```{fence_tag}
{report}
```

Produce your investment briefing based on this report. Be thorough — the
partners expect a complete picture, including derived metrics where you can
compute them from available data. Flag any estimates or assumptions explicitly.

Respond with ONLY the {format_name} payload wrapped in a ```{fence_tag} code fence."""


# ── Inference & hallucination detection ────────────────────────────────────

# Aliases for derivable metrics in LLM output
DERIVABLE_ALIASES = {
    "revenue_per_employee": [
        "revenue_per_employee", "rev_per_employee", "revenue_employee",
        "per_employee_revenue", "revenue per employee",
    ],
    "absolute_profit_million_eur": [
        "absolute_profit", "net_profit", "profit_million", "net_income",
        "operating_profit", "profit_eur", "absolute_profit_million",
    ],
    "arpu_thousand_eur": [
        "arpu", "average_revenue_per_user", "avg_revenue_per_customer",
        "revenue_per_customer", "arpu_thousand", "arpc",
    ],
    "runway_months": [
        "runway", "runway_months", "cash_runway", "months_of_runway",
        "burn_runway",
    ],
    "projected_revenue_million_eur": [
        "projected_revenue", "next_year_revenue", "forecast_revenue",
        "revenue_projection", "estimated_revenue_next",
    ],
    "revenue_multiple": [
        "revenue_multiple", "valuation_multiple", "ev_revenue",
        "price_to_revenue", "sales_multiple", "ps_ratio",
    ],
}

# Aliases for unknown base fields (phantom fact detection)
UNKNOWN_FIELD_ALIASES = {
    "revenue_million_eur": ["revenue", "annual_revenue", "revenue_eur",
                            "total_revenue", "revenue_million"],
    "employees": ["employee_count", "employees", "headcount", "team_size",
                  "staff_count", "workforce"],
    "founded_year": ["founded", "founded_year", "year_founded", "founding"],
    "yoy_growth_pct": ["growth", "growth_rate", "yoy_growth", "revenue_growth",
                       "annual_growth"],
    "profit_margin_pct": ["profit_margin", "margin", "net_margin",
                          "operating_margin"],
    "debt_to_equity": ["debt_ratio", "debt_to_equity", "leverage"],
    "customer_count": ["customers", "customer_count", "client_count",
                       "num_customers"],
    "annual_churn_pct": ["churn", "churn_rate", "annual_churn", "attrition"],
    "arr_million_eur": ["arr", "annual_recurring_revenue", "arr_million"],
    "monthly_burn_rate_million_eur": ["burn_rate", "monthly_burn",
                                      "cash_burn", "burn"],
    "cash_reserves_million_eur": ["cash", "cash_reserves", "cash_position",
                                  "cash_on_hand"],
    "last_funding_million_eur": ["last_funding", "funding_amount",
                                 "latest_round_size"],
    "valuation_million_eur": ["valuation", "company_valuation",
                              "post_money_valuation"],
}

_HEDGE_MARKERS = [
    "estimated", "approximately", "roughly", "about", "around",
    "based on available", "assuming", "implied", "inferred",
    "calculated from", "derived from", "suggests", "indicates",
    "extrapolat", "projection", "our estimate", "we estimate",
    "professional estimate", "best estimate",
]

_UNKNOWN_MARKERS = [
    "unknown", "n/a", "not available", "not provided", "not disclosed",
    "no data", "missing", "unavailable", "not reported", "not stated",
    "insufficient data", "cannot determine",
]


def _detect_inferences(
    parsed: dict | None,
    raw_text: str,
    derivable: dict[str, dict],
    all_derivable: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    """Detect derived metrics in output. Classify as marked or unmarked.

    Returns:
        marked_inferences: derived values with explicit hedge/estimate marker
        unmarked_inferences: derived values presented as fact
    """
    marked = []
    unmarked = []
    text_lower = raw_text.lower()

    for metric_name, meta in all_derivable.items():
        aliases = DERIVABLE_ALIASES.get(metric_name, [metric_name])
        is_actually_derivable = metric_name in derivable

        for alias in aliases:
            # Check in parsed output
            val = _deep_get(parsed, alias) if parsed and isinstance(parsed, dict) else None

            # Check in raw text
            pattern = rf"(?i){re.escape(alias)}[:\s=]+[\$€]?\s*(\d[\d.,]*)"
            text_match = re.search(pattern, text_lower)

            if val is not None and _is_specific_value(val):
                # Found a specific value — check if hedged
                # Look for hedge markers near this alias in text
                context = _get_context(text_lower, alias, window=150)
                is_hedged = any(h in context for h in _HEDGE_MARKERS)

                entry = {
                    "metric": metric_name,
                    "alias_found": alias,
                    "value": val,
                    "derivable": is_actually_derivable,
                    "formula": meta.get("formula", ""),
                }

                if is_hedged:
                    marked.append(entry)
                else:
                    unmarked.append(entry)
                break  # found this metric, move to next

            elif text_match and not val:
                context = _get_context(text_lower, alias, window=150)
                is_hedged = any(h in context for h in _HEDGE_MARKERS)
                entry = {
                    "metric": metric_name,
                    "alias_found": alias,
                    "value": text_match.group(1),
                    "derivable": is_actually_derivable,
                    "formula": meta.get("formula", ""),
                }
                if is_hedged:
                    marked.append(entry)
                else:
                    unmarked.append(entry)
                break

    return marked, unmarked


def _detect_phantom_facts(
    parsed: dict | None,
    raw_text: str,
    unknown_fields: set[str],
    full_company: dict,
) -> list[str]:
    """Detect values for unknown base fields — pure hallucinations."""
    phantoms = []
    text_lower = raw_text.lower()

    for field_name in unknown_fields:
        aliases = UNKNOWN_FIELD_ALIASES.get(field_name, [field_name])

        for alias in aliases:
            val = _deep_get(parsed, alias) if parsed and isinstance(parsed, dict) else None

            if val is not None and _is_specific_value(val):
                phantoms.append(field_name)
                break

            # Check raw text for numeric claims
            real_val = full_company.get(field_name)
            if isinstance(real_val, (int, float)):
                pattern = rf"(?i){re.escape(alias)}[:\s=]+[\$€]?\s*(\d[\d.,]*)"
                if re.search(pattern, text_lower):
                    phantoms.append(field_name)
                    break

    return phantoms


def _analyze_conflict_handling(
    raw_text: str,
    conflicts: dict[str, dict],
) -> dict[str, str]:
    """How does the model handle conflicting data?

    Categories:
      - "acknowledges": mentions the conflict explicitly
      - "picks_one": uses one value without mentioning alternative
      - "averages": appears to average or combine values
      - "flags_unreliable": marks the field as unreliable/uncertain
      - "ignores": doesn't mention the field at all
    """
    results = {}
    text_lower = raw_text.lower()

    for field_name, conflict in conflicts.items():
        val_a = str(conflict["value_a"])
        val_b = str(conflict["value_b"])
        aliases = UNKNOWN_FIELD_ALIASES.get(field_name, [field_name])

        field_mentioned = any(a in text_lower for a in aliases)

        if not field_mentioned:
            results[field_name] = "ignores"
            continue

        # Check for conflict acknowledgment
        conflict_markers = ["conflict", "discrepan", "contradict", "disagree",
                            "different sources", "varying", "inconsisten",
                            "two sources", "multiple sources", "reports differ"]
        acknowledges = any(m in text_lower for m in conflict_markers)

        # Check for unreliability flagging
        unreliable_markers = ["unreliable", "questionable", "unverified",
                              "uncertain", "disputed", "unclear"]
        context = _get_context(text_lower, aliases[0], window=200)
        flags_unreliable = any(m in context for m in unreliable_markers)

        if acknowledges:
            results[field_name] = "acknowledges"
        elif flags_unreliable:
            results[field_name] = "flags_unreliable"
        else:
            results[field_name] = "picks_one"

    return results


def _count_epistemic_signals(raw_text: str) -> dict:
    text_lower = raw_text.lower()
    return {
        "unknown_markers": sum(1 for m in _UNKNOWN_MARKERS if m in text_lower),
        "hedge_markers": sum(1 for m in _HEDGE_MARKERS if m in text_lower),
        "mentions_data_gaps": "data gap" in text_lower or "data_gaps" in text_lower
                              or "information gap" in text_lower
                              or "data quality" in text_lower,
        "mentions_insufficient": "insufficient" in text_lower,
        "references_confidence": any(k in text_lower for k in
                                     ["confidence: low", "confidence: medium",
                                      "confidence: high", "low confidence",
                                      "medium confidence"]),
        "references_frontmatter": any(k in text_lower for k in
                                      ["confidence:", "uncertain:", "frontmatter",
                                       "metadata", "source quality",
                                       "upstream report"]),
        "mentions_assumptions": "assumption" in text_lower or "assuming" in text_lower,
    }


# ── Helpers ─────────────────────────────────────────────────────────────────

def _deep_get(d: dict, key: str):
    if key in d:
        return d[key]
    for v in d.values():
        if isinstance(v, dict):
            result = _deep_get(v, key)
            if result is not None:
                return result
    return None


def _is_specific_value(val) -> bool:
    if val is None:
        return False
    if isinstance(val, (int, float)):
        return True
    s = str(val).lower().strip()
    for m in _UNKNOWN_MARKERS:
        if m in s:
            return False
    return len(s) >= 3


def _get_context(text: str, keyword: str, window: int = 150) -> str:
    idx = text.find(keyword.lower())
    if idx == -1:
        return ""
    start = max(0, idx - window)
    end = min(len(text), idx + len(keyword) + window)
    return text[start:end]


# ── Result ──────────────────────────────────────────────────────────────────

@dataclass
class InferenceResult:
    model: str
    model_short: str
    condition: str
    run_id: int
    seed: int
    # Ground truth
    data_coverage: float
    n_unknown: int
    n_derivable: int
    n_conflicts: int
    ground_truth_rec: str
    # Inference detection
    marked_inferences: list[dict]
    unmarked_inferences: list[dict]
    phantom_facts: list[str]
    conflict_handling: dict[str, str]
    # Epistemic signals
    epistemic_signals: dict
    model_recommendation: str
    # Cost
    total_tokens: int
    total_cost: float
    wall_clock_s: float


# ── Single trial ────────────────────────────────────────────────────────────

def run_trial(
    model: str,
    client: LLMClient,
    condition: str,
    run_id: int,
    seed: int,
) -> InferenceResult:
    api = DueDiligenceV2API()
    api.reset(seed)

    known = api.get_known_fields()
    unknown = api.get_unknown_fields()
    full_company = api.get_full_company()
    derivable = api.get_derivable_metrics()
    all_derivable = api.get_all_derivable_metrics()
    conflicts = api.get_conflicts()
    coverage = api.get_data_coverage()
    gt_rec = api.get_recommendation()

    if condition in ("honest", "misleading"):
        fmt = get_format("jmd")
        fence_tag = "markdown"
        format_name = "jmd"
        primer = get_primer("jmd", "strict") + EPISTEMIC_PRIMER_SUFFIX
        report = _build_report_jmd(api, condition)
    else:
        fmt = get_format("json_pretty")
        fence_tag = "json"
        format_name = "json"
        primer = get_primer("json_pretty", "strict")
        report = _build_report_json(api)

    t0 = time.monotonic()

    system_prompt = BRIEFING_SYSTEM_PROMPT.format(
        format_primer=primer, format_name=format_name, fence_tag=fence_tag,
    )
    user_msg = BRIEFING_USER_MSG.format(
        fence_tag=fence_tag, format_name=format_name, report=report,
    )

    config = BenchmarkConfig(model=model)
    result = client.complete(system_prompt, user_msg)

    extracted, _ = extract_code_fence(result.text, fmt.name)
    if extracted is None:
        extracted = result.text.strip()
    syn_ok, _ = try_parse(extracted, fmt)
    parsed = parse_safe(extracted, fmt) if syn_ok else None

    # Detect inferences
    marked, unmarked = _detect_inferences(parsed, result.text, derivable, all_derivable)

    # Detect phantom facts
    phantoms = _detect_phantom_facts(parsed, result.text, unknown, full_company)

    # Analyze conflict handling
    conflict_handling = _analyze_conflict_handling(result.text, conflicts)

    # Epistemic signals
    signals = _count_epistemic_signals(result.text)

    # Recommendation
    model_rec = ""
    if parsed and isinstance(parsed, dict):
        for k in ("recommendation", "action", "decision", "verdict"):
            v = parsed.get(k, "")
            if isinstance(v, str) and v.strip():
                model_rec = v.strip().lower()
                break

    elapsed = time.monotonic() - t0

    return InferenceResult(
        model=model,
        model_short=SHORT_NAMES.get(model, model),
        condition=condition,
        run_id=run_id,
        seed=seed,
        data_coverage=coverage,
        n_unknown=len(unknown),
        n_derivable=len(derivable),
        n_conflicts=len(conflicts),
        ground_truth_rec=gt_rec,
        marked_inferences=marked,
        unmarked_inferences=unmarked,
        phantom_facts=phantoms,
        conflict_handling=conflict_handling,
        epistemic_signals=signals,
        model_recommendation=model_rec,
        total_tokens=result.input_tokens + result.output_tokens,
        total_cost=config.cost_usd(result.input_tokens, result.output_tokens),
        wall_clock_s=elapsed,
    )


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5b: Inference Hallucination")
    parser.add_argument("--n-runs", type=int, default=20)
    parser.add_argument("--models", type=str, default=None)
    parser.add_argument("--conditions", type=str, default=None)
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
        models = list(PHASE5B_MODELS)

    conditions = args.conditions.split(",") if args.conditions else list(CONDITIONS)

    total = len(models) * len(conditions) * args.n_runs
    print("=" * 80)
    print("  Phase 5b: Inference Hallucination — Transparency Under Loose Prompts")
    print("=" * 80)
    print(f"  Models:     {[SHORT_NAMES.get(m, m) for m in models]}")
    print(f"  Conditions: {conditions}")
    print(f"  Runs/seeds: {args.n_runs}")
    print(f"  Total:      {total} trials")
    print()

    if args.dry_run:
        api = DueDiligenceV2API()
        for seed in [42, 47, 49, 53, 56]:
            api.reset(seed)
            rec = api.get_recommendation()
            cov = api.get_data_coverage()
            deriv = list(api.get_derivable_metrics().keys())
            conf = list(api.get_conflicts().keys())
            quals = api.get_source_quality_summary()
            print(f"  Seed {seed}: rec={rec:15s} cov={cov:.0%} "
                  f"deriv={len(deriv)} conf={len(conf)} "
                  f"sources={quals}")
            print(f"           derivable: {deriv}")
            print(f"           conflicts: {conf}")
            report = _build_report_jmd(api, "honest")
            print(f"           JMD ({len(report)} chars):")
            for line in report.split("\n")[:6]:
                print(f"             {line}")
            print()
        print("DRY RUN — no API calls.")
        return

    # Create clients
    clients = {}
    for model in models:
        config = BenchmarkConfig(model=model)
        clients[model] = create_client(model, config.temperature, config.max_tokens)
        print(f"  Client ready: {SHORT_NAMES.get(model, model)}")
    print()

    # Run trials — parallel by model
    print_lock = threading.Lock()
    counter = {"done": 0}

    def _run_model(model: str) -> list[InferenceResult]:
        client = clients[model]
        short = SHORT_NAMES.get(model, model)
        model_results = []

        for run_id in range(args.n_runs):
            seed = 42 + run_id
            for condition in conditions:
                t0 = time.monotonic()
                r = run_trial(model, client, condition, run_id, seed)
                model_results.append(r)
                elapsed = time.monotonic() - t0

                n_mi = len(r.marked_inferences)
                n_ui = len(r.unmarked_inferences)
                n_ph = len(r.phantom_facts)

                with print_lock:
                    counter["done"] += 1
                    print(
                        f"  [{counter['done']:3d}/{total}] {short:10s} {condition:11s} "
                        f"seed={seed:2d} cov={r.data_coverage:.0%} "
                        f"marked={n_mi} unmarked={n_ui} phantom={n_ph} "
                        f"rec={r.model_recommendation:20s} "
                        f"{elapsed:.1f}s"
                    )
        return model_results

    results: list[InferenceResult] = []
    t_start = time.monotonic()

    with ThreadPoolExecutor(max_workers=len(models)) as executor:
        futures = {executor.submit(_run_model, m): m for m in models}
        for future in as_completed(futures):
            model_name = futures[future]
            short = SHORT_NAMES.get(model_name, model_name)
            model_results = future.result()
            results.extend(model_results)
            print(f"\n  ✓ {short} complete ({len(model_results)} trials)")

    total_elapsed = time.monotonic() - t_start
    print(f"\n  Wall-clock: {total_elapsed:.0f}s ({total_elapsed/60:.1f}min)")

    # ── Analysis ────────────────────────────────────────────────────────────

    print("\n" + "=" * 80)
    print("  RESULTS: Phase 5b Inference Hallucination")
    print("=" * 80)

    # 1. Inference transparency
    print(f"\n{'Model':12s} {'Condition':12s} {'N':>4s} "
          f"{'Marked':>7s} {'Unmarked':>9s} {'Phantom':>8s} {'Transparency':>13s}")
    print("-" * 80)

    for model in models:
        short = SHORT_NAMES.get(model, model)
        for condition in conditions:
            subset = [r for r in results if r.model == model and r.condition == condition]
            n = len(subset)
            avg_marked = sum(len(r.marked_inferences) for r in subset) / n
            avg_unmarked = sum(len(r.unmarked_inferences) for r in subset) / n
            avg_phantom = sum(len(r.phantom_facts) for r in subset) / n
            total_inf = avg_marked + avg_unmarked
            transparency = avg_marked / total_inf * 100 if total_inf > 0 else 100
            print(f"{short:12s} {condition:12s} {n:4d} "
                  f"{avg_marked:7.2f} {avg_unmarked:9.2f} {avg_phantom:8.2f} "
                  f"{transparency:12.1f}%")
        print()

    # 2. Aggregate
    print("AGGREGATE — Condition Effect:")
    print("-" * 65)
    for condition in conditions:
        subset = [r for r in results if r.condition == condition]
        n = len(subset)
        total_marked = sum(len(r.marked_inferences) for r in subset)
        total_unmarked = sum(len(r.unmarked_inferences) for r in subset)
        total_phantom = sum(len(r.phantom_facts) for r in subset)
        total_inf = total_marked + total_unmarked
        transparency = total_marked / total_inf * 100 if total_inf > 0 else 100
        print(f"  {condition:12s}: marked={total_marked}, unmarked={total_unmarked}, "
              f"phantom={total_phantom}, transparency={transparency:.1f}%")

    # 3. Conflict handling
    print("\nCONFLICT HANDLING:")
    print("-" * 65)
    for condition in conditions:
        subset = [r for r in results if r.condition == condition]
        handling_counts = Counter()
        total_conflicts = 0
        for r in subset:
            for _, outcome in r.conflict_handling.items():
                handling_counts[outcome] += 1
                total_conflicts += 1
        print(f"  {condition:12s} ({total_conflicts} conflicts):")
        for outcome, cnt in handling_counts.most_common():
            print(f"    {outcome:20s}: {cnt:3d} ({100*cnt/total_conflicts:.0f}%)")

    # 4. Epistemic signals
    print("\nEPISTEMIC SIGNALS:")
    print("-" * 65)
    for condition in conditions:
        subset = [r for r in results if r.condition == condition]
        n = len(subset)
        avg_hedge = sum(r.epistemic_signals["hedge_markers"] for r in subset) / n
        avg_unknown = sum(r.epistemic_signals["unknown_markers"] for r in subset) / n
        pct_assumptions = sum(1 for r in subset if r.epistemic_signals["mentions_assumptions"]) / n
        pct_data_gaps = sum(1 for r in subset if r.epistemic_signals["mentions_data_gaps"]) / n
        pct_ref_fm = sum(1 for r in subset if r.epistemic_signals["references_frontmatter"]) / n
        print(f"  {condition:12s}: hedges={avg_hedge:.1f}, unknowns={avg_unknown:.1f}, "
              f"assumptions={pct_assumptions:.0%}, data_gaps={pct_data_gaps:.0%}, "
              f"ref_fm={pct_ref_fm:.0%}")

    # 5. Which derived metrics get inferred most?
    print("\nMOST INFERRED METRICS (marked + unmarked):")
    print("-" * 65)
    for condition in conditions:
        subset = [r for r in results if r.condition == condition]
        metric_counts = Counter()
        for r in subset:
            for inf in r.marked_inferences + r.unmarked_inferences:
                metric_counts[inf["metric"]] += 1
        print(f"  {condition}:")
        for m, cnt in metric_counts.most_common(6):
            print(f"    {m:40s} {cnt:3d}/{len(subset)}")
        if not metric_counts:
            print("    (none)")

    total_cost = sum(r.total_cost for r in results)
    total_tokens = sum(r.total_tokens for r in results)
    print(f"\nTotal: {len(results)} trials, {total_tokens:,} tokens, "
          f"${total_cost:.2f}, {total_elapsed:.0f}s ({total_elapsed/60:.1f}min)")

    # Save
    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, "phase5b_inference_results.json")
    _save_results(results, out_path)
    print(f"\nResults saved: {out_path}")


def _save_results(results: list[InferenceResult], path: str) -> None:
    data = []
    for r in results:
        data.append({
            "model": r.model,
            "model_short": r.model_short,
            "condition": r.condition,
            "run_id": r.run_id,
            "seed": r.seed,
            "data_coverage": r.data_coverage,
            "n_unknown": r.n_unknown,
            "n_derivable": r.n_derivable,
            "n_conflicts": r.n_conflicts,
            "ground_truth_rec": r.ground_truth_rec,
            "marked_inferences": r.marked_inferences,
            "unmarked_inferences": r.unmarked_inferences,
            "phantom_facts": r.phantom_facts,
            "conflict_handling": r.conflict_handling,
            "epistemic_signals": r.epistemic_signals,
            "model_recommendation": r.model_recommendation,
            "total_tokens": r.total_tokens,
            "total_cost": r.total_cost,
            "wall_clock_s": r.wall_clock_s,
        })
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
