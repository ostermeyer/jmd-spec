# SPDX-License-Identifier: Apache-2.0
"""Format Fidelity Test — measures format accuracy independently of data reasoning.

Unlike the chain benchmark (which tests extraction + reasoning + serialization),
this test isolates pure format fidelity:

  1. Give the model a concrete data structure
  2. Ask it to reproduce that data in JMD / JSON
  3. Parse the output
  4. Deep-compare every value against the input

Any difference is a FORMAT error, not a hallucination or reasoning error.

Two test dimensions:
  - Format Fidelity: Does the output parse at all? (syntax)
  - Data Fidelity:   Are all values identical to the input? (roundtrip)
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure repo root is on path for jmd imports
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from jmd import JMDParser, JMDSerializer  # noqa: E402

from .llm_client import create_client, get_pricing  # noqa: E402
from .primers import get_primer  # noqa: E402


# ---------------------------------------------------------------------------
# Test data — deterministic, covers all JMD/JSON types
# ---------------------------------------------------------------------------

TEST_PAYLOADS: dict[str, dict[str, Any]] = {
    "flat_object": {
        "label": "User",
        "data": {
            "id": "USR-42",
            "name": "Maria Schmidt",
            "email": "maria@example.com",
            "age": 34,
            "active": True,
            "score": 98.5,
            "notes": None,
        },
    },
    "nested_object": {
        "label": "Order",
        "data": {
            "order_id": "ORD-001337",
            "status": "confirmed",
            "total": 249.95,
            "currency": "EUR",
            "customer": {
                "name": "Andreas Müller",
                "email": "andreas@example.de",
                "tier": "premium",
            },
            "shipping_address": {
                "street": "Hauptstraße 42",
                "city": "Berlin",
                "zip": "10115",
                "country": "DE",
            },
        },
    },
    "array_of_objects": {
        "label": "Products",
        "data": {
            "products": [
                {
                    "id": "PROD-1000",
                    "name": "Premium Widget",
                    "price": 29.99,
                    "rating": 4.7,
                    "in_stock": True,
                },
                {
                    "id": "PROD-1001",
                    "name": "Ultra Gadget",
                    "price": 149.50,
                    "rating": 4.2,
                    "in_stock": False,
                },
                {
                    "id": "PROD-1002",
                    "name": "Classic Device",
                    "price": 89.00,
                    "rating": 4.9,
                    "in_stock": True,
                },
            ]
        },
    },
    "mixed_types": {
        "label": "Config",
        "data": {
            "app_name": "TestSuite",
            "version": "2.1.0",
            "debug": False,
            "max_retries": 3,
            "timeout_ms": 5000,
            "tags": ["production", "v2", "stable"],
            "endpoints": [
                {"path": "/api/users", "method": "GET", "auth": True},
                {"path": "/api/health", "method": "GET", "auth": False},
            ],
            "metadata": {
                "created": "2026-03-15",
                "author": "test-harness",
                "checksum": "a1b2c3d4",
            },
        },
    },
    "multiline_text": {
        "label": "Article",
        "data": {
            "title": "Format Fidelity",
            "author": "Test Suite",
            "body": (
                "This is the first paragraph of the article.\n"
                "It spans multiple lines to test multiline handling.\n"
                "\n"
                "This is the second paragraph.\n"
                "It also has multiple lines."
            ),
            "tags": ["benchmark", "testing"],
        },
    },
}


# ---------------------------------------------------------------------------
# Deep comparison
# ---------------------------------------------------------------------------

@dataclass
class CompareResult:
    identical: bool
    total_fields: int
    matched_fields: int
    mismatches: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.matched_fields / self.total_fields if self.total_fields else 0.0


def _normalize(value: Any) -> Any:
    """Normalize values for comparison (handle string/number coercion)."""
    if isinstance(value, str):
        # Try to parse as number (JMD parser may return strings for numbers)
        try:
            if "." in value:
                return float(value)
            return int(value)
        except (ValueError, TypeError):
            pass
        # Normalize boolean strings
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        if value.lower() == "null" or value.lower() == "none":
            return None
    return value


def deep_compare(
    expected: Any, actual: Any, path: str = "$"
) -> CompareResult:
    """Deep-compare two data structures, field by field."""
    total = 0
    matched = 0
    mismatches: list[str] = []

    def _compare(exp: Any, act: Any, p: str) -> None:
        nonlocal total, matched

        exp = _normalize(exp)
        act = _normalize(act)

        if isinstance(exp, dict) and isinstance(act, dict):
            for key in exp:
                total += 1
                if key not in act:
                    mismatches.append(f"{p}.{key}: MISSING (expected {exp[key]!r})")
                else:
                    matched += 1
                    _compare(exp[key], act[key], f"{p}.{key}")
            for key in act:
                if key not in exp:
                    mismatches.append(f"{p}.{key}: EXTRA (got {act[key]!r})")
        elif isinstance(exp, list) and isinstance(act, list):
            total += 1
            if len(exp) != len(act):
                mismatches.append(
                    f"{p}: array length {len(exp)} vs {len(act)}"
                )
                matched += 1  # structure present, count partially
            else:
                matched += 1
            for i in range(min(len(exp), len(act))):
                _compare(exp[i], act[i], f"{p}[{i}]")
        else:
            total += 1
            # Compare values with type coercion
            if _values_equal(exp, act):
                matched += 1
            else:
                mismatches.append(f"{p}: {exp!r} vs {act!r}")

    _compare(expected, actual, path)
    return CompareResult(
        identical=len(mismatches) == 0,
        total_fields=total,
        matched_fields=matched,
        mismatches=mismatches,
    )


def _values_equal(a: Any, b: Any) -> bool:
    """Compare values with reasonable tolerance."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 0.01
        except (ValueError, TypeError):
            return False
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    return str(a) == str(b)


# ---------------------------------------------------------------------------
# Single fidelity test
# ---------------------------------------------------------------------------

@dataclass
class FidelityResult:
    payload_name: str
    format_name: str
    model: str
    # Format fidelity
    syn_valid: bool
    parse_error: str
    # Data fidelity
    data_identical: bool
    data_score: float
    total_fields: int
    matched_fields: int
    mismatches: list[str]
    # Metrics
    input_tokens: int
    output_tokens: int
    wall_clock_s: float
    cost_usd: float
    raw_output: str


import re

_FENCE_RE = re.compile(
    r"```(?:json|jmd|markdown)\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_ANY_FENCE_RE = re.compile(r"```\w*\s*\n(.*?)```", re.DOTALL)


def _extract_fenced(text: str) -> str:
    """Extract content from code fences."""
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    m = _ANY_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def run_fidelity_test(
    payload_name: str,
    payload: dict[str, Any],
    format_name: str,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> FidelityResult:
    """Run a single format fidelity test."""
    data = payload["data"]
    label = payload["label"]

    # Serialize input data in the target format
    if format_name == "jmd":
        input_serialized = JMDSerializer().serialize(data, label=label)
        fence_tag = "markdown"
        primer = get_primer("jmd", "minimal")
    else:
        input_serialized = json.dumps(data, indent=2, ensure_ascii=False)
        fence_tag = "json"
        primer = "You are a data formatting assistant. Return data as JSON."

    system_prompt = f"""{primer}

IMPORTANT: Reproduce the EXACT data below in {format_name.upper()} format.
Do NOT add, remove, or modify any values. Do NOT rename keys.
Do NOT add commentary. Return ONLY the data in a ```{fence_tag} code fence."""

    user_msg = f"""Here is the data. Reproduce it exactly in {format_name.upper()} format.

```{fence_tag}
{input_serialized}
```

Return ONLY the {format_name.upper()} payload in a ```{fence_tag} code fence. No other text."""

    # Call LLM
    client = create_client(model, temperature, max_tokens)
    pricing_in, pricing_out = get_pricing(model)

    t0 = time.monotonic()
    result = client.complete(system_prompt, user_msg)
    wall_clock = time.monotonic() - t0

    cost = (
        result.input_tokens * pricing_in / 1_000_000
        + result.output_tokens * pricing_out / 1_000_000
    )

    # Extract and parse
    extracted = _extract_fenced(result.text)

    try:
        if format_name == "jmd":
            parsed = JMDParser().parse(extracted)
        else:
            parsed = json.loads(extracted)
        syn_valid = True
        parse_error = ""
    except Exception as e:
        parsed = None
        syn_valid = False
        parse_error = str(e)

    # Compare
    if parsed is not None:
        cmp = deep_compare(data, parsed)
    else:
        cmp = CompareResult(
            identical=False, total_fields=0, matched_fields=0,
            mismatches=["parse failure — no comparison possible"],
        )

    return FidelityResult(
        payload_name=payload_name,
        format_name=format_name,
        model=model,
        syn_valid=syn_valid,
        parse_error=parse_error,
        data_identical=cmp.identical,
        data_score=cmp.score,
        total_fields=cmp.total_fields,
        matched_fields=cmp.matched_fields,
        mismatches=cmp.mismatches,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        wall_clock_s=wall_clock,
        cost_usd=cost,
        raw_output=result.text,
    )


# ---------------------------------------------------------------------------
# Full test suite
# ---------------------------------------------------------------------------

def run_fidelity_suite(
    models: list[str],
    formats: list[str] | None = None,
    payloads: dict[str, dict[str, Any]] | None = None,
) -> list[FidelityResult]:
    """Run full fidelity test suite across models, formats, and payloads."""
    if formats is None:
        formats = ["json_pretty", "jmd"]
    if payloads is None:
        payloads = TEST_PAYLOADS

    results: list[FidelityResult] = []
    total = len(models) * len(formats) * len(payloads)
    n = 0

    for model in models:
        for fmt in formats:
            fmt_name = "json" if fmt.startswith("json") else fmt
            for pname, payload in payloads.items():
                n += 1
                print(
                    f"  [{n}/{total}] {model} / {fmt} / {pname} ...",
                    end="", flush=True,
                )
                r = run_fidelity_test(pname, payload, fmt_name, model)
                results.append(r)

                status = "OK" if r.data_identical else "MISMATCH"
                if not r.syn_valid:
                    status = "PARSE_FAIL"
                print(
                    f" {status}"
                    f" (score={r.data_score:.0%},"
                    f" {r.output_tokens} tok,"
                    f" ${r.cost_usd:.4f})"
                )
                if r.mismatches:
                    for m in r.mismatches[:5]:
                        print(f"      {m}")
                    if len(r.mismatches) > 5:
                        print(f"      ... +{len(r.mismatches)-5} more")

    return results


def print_summary(results: list[FidelityResult]) -> None:
    """Print summary table."""
    # Group by model × format
    from collections import defaultdict
    groups: dict[tuple[str, str], list[FidelityResult]] = defaultdict(list)
    for r in results:
        groups[(r.model, r.format_name)].append(r)

    print("\n" + "=" * 80)
    print("FORMAT FIDELITY SUMMARY")
    print("=" * 80)
    print(
        f"{'Model':<25} {'Format':<10} {'Syntax':<10} {'Data 100%':<12}"
        f"{'Avg Score':<12} {'Tokens':<10} {'Cost':<8}"
    )
    print("-" * 80)

    for (model, fmt), rr in sorted(groups.items()):
        n = len(rr)
        syn_ok = sum(1 for r in rr if r.syn_valid)
        data_ok = sum(1 for r in rr if r.data_identical)
        avg_score = sum(r.data_score for r in rr) / n if n else 0
        total_tok = sum(r.output_tokens for r in rr)
        total_cost = sum(r.cost_usd for r in rr)

        print(
            f"{model:<25} {fmt:<10} {syn_ok}/{n:<8} {data_ok}/{n:<10}"
            f"  {avg_score:>6.1%}      {total_tok:<10} ${total_cost:.4f}"
        )

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Format Fidelity Test — pure format/data accuracy"
    )
    parser.add_argument(
        "--models", nargs="+",
        default=["claude-haiku-4-5"],
        help="Models to test",
    )
    parser.add_argument(
        "--formats", nargs="+",
        default=["json_pretty", "jmd"],
        help="Formats to test",
    )
    parser.add_argument(
        "--payloads", nargs="+",
        default=None,
        help="Payload names (default: all)",
    )
    args = parser.parse_args()

    payloads = TEST_PAYLOADS
    if args.payloads:
        payloads = {k: v for k, v in TEST_PAYLOADS.items() if k in args.payloads}

    print("Format Fidelity Test")
    print(f"  Models:   {args.models}")
    print(f"  Formats:  {args.formats}")
    print(f"  Payloads: {list(payloads.keys())}")
    print()

    results = run_fidelity_suite(args.models, args.formats, payloads)
    print_summary(results)


if __name__ == "__main__":
    main()
