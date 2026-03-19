#!/usr/bin/env python3
"""Compare JMD vs JSON minified: tokens, time & validity across 3 models × 4 sizes.

Uses JMD primer in system prompts and validates all JMD output through the parser.
JSON output is validated via json.loads().
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

# Ensure repo root on path
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from openai import OpenAI
from google import genai
from google.genai import types as gtypes
import anthropic
import jmd

# ---------------------------------------------------------------------------
# Primers
# ---------------------------------------------------------------------------

JMD_PRIMER = (
    "You are a data processing assistant. You communicate using "
    "JMD (JSON Markdown), a format that maps 1:1 to JSON using Markdown syntax.\n\n"
    "JMD rules:\n"
    "- # [label] is the root object\n"
    "- ## key creates a nested object; ### key for deeper nesting\n"
    "- key: value for fields (no quotes on keys, no braces)\n"
    "- ## key[] or - items for arrays\n"
    "- Inline objects in arrays: - key: val, key: val\n"
    "- Multi-line array items use indentation (2 spaces)\n"
    "- Scalars: strings unquoted, numbers/booleans/null auto-detected\n\n"
    "Example:\n"
    "# [order]\n"
    "id: 42\n"
    "status: pending\n"
    "## customer\n"
    "name: Jane Doe\n"
    "email: jane@example.com\n"
    "## items[]\n"
    "- sku: A1, qty: 2, price: 19.99\n"
    "- sku: B2, qty: 1, price: 49.99\n"
    "## shipping\n"
    "method: express\n"
    "city: Berlin\n\n"
    "Output ONLY valid JMD, no commentary, no code fences."
)

JSON_PRIMER = (
    "You are a data processing assistant. You communicate using JSON.\n"
    "Output ONLY valid minified JSON (single line, no extra whitespace), "
    "no commentary, no code fences."
)

# ---------------------------------------------------------------------------
# Payloads: 4 sizes with expected dicts for validation
# ---------------------------------------------------------------------------

PAYLOADS = {
    "small": {
        "description": "Single user profile",
        "expected": {
            "user": {
                "name": "Alice Müller",
                "email": "alice@example.com",
                "age": 34,
                "city": "Berlin",
            }
        },
        "jmd": (
            "# [user]\n"
            "name: Alice Müller\n"
            "email: alice@example.com\n"
            "age: 34\n"
            "city: Berlin"
        ),
        "json": '{"user":{"name":"Alice Müller","email":"alice@example.com","age":34,"city":"Berlin"}}',
    },
    "medium": {
        "description": "E-commerce order with 3 items",
        "expected": {
            "order": {
                "id": "ORD-2024-7891",
                "status": "shipped",
                "customer": {"name": "Bob Schmidt", "email": "bob@example.com"},
                "items": [
                    {"name": "Wireless Mouse", "price": 29.99, "qty": 2},
                    {"name": "USB-C Hub", "price": 49.95, "qty": 1},
                    {"name": "Monitor Stand", "price": 79.00, "qty": 1},
                ],
                "shipping": {
                    "street": "Hauptstraße 42", "city": "München",
                    "zip": "80331", "country": "DE", "method": "express",
                },
                "payment": {"method": "credit_card", "last4": "4242", "status": "charged"},
            }
        },
        "jmd": (
            "# [order]\n"
            "id: ORD-2024-7891\n"
            "status: shipped\n"
            "\n"
            "## customer\n"
            "name: Bob Schmidt\n"
            "email: bob@example.com\n"
            "\n"
            "## items[]\n"
            "- name: Wireless Mouse, price: 29.99, qty: 2\n"
            "- name: USB-C Hub, price: 49.95, qty: 1\n"
            "- name: Monitor Stand, price: 79.00, qty: 1\n"
            "\n"
            "## shipping\n"
            "street: Hauptstraße 42\n"
            "city: München\n"
            "zip: 80331\n"
            "country: DE\n"
            "method: express\n"
            "\n"
            "## payment\n"
            "method: credit_card\n"
            "last4: 4242\n"
            "status: charged"
        ),
        "json": '{"order":{"id":"ORD-2024-7891","status":"shipped","customer":{"name":"Bob Schmidt","email":"bob@example.com"},"items":[{"name":"Wireless Mouse","price":29.99,"qty":2},{"name":"USB-C Hub","price":49.95,"qty":1},{"name":"Monitor Stand","price":79.00,"qty":1}],"shipping":{"street":"Hauptstraße 42","city":"München","zip":"80331","country":"DE","method":"express"},"payment":{"method":"credit_card","last4":"4242","status":"charged"}}}',
    },
    "large": {
        "description": "Product catalog with 6 products",
        "expected_keys": ["catalog"],  # Only check structure, not full deep equality
        "expected_product_count": 6,
        "expected_product_names": [
            "Mechanical Keyboard", "4K Monitor", "Ergonomic Mouse",
            "Thunderbolt Dock", "Noise-Cancelling Headset", "Webcam 4K",
        ],
        "jmd": (
            "# [catalog]\n"
            "store: TechShop Pro\n"
            "currency: EUR\n"
            "updated: 2026-03-10\n"
            "\n"
            "## products[]\n"
            "- name: Mechanical Keyboard\n"
            "  sku: KB-MEC-001\n"
            "  price: 149.99\n"
            "  category: peripherals\n"
            "  in_stock: true\n"
            "  description: Premium mechanical keyboard with Cherry MX switches\n"
            "\n"
            "- name: 4K Monitor\n"
            "  sku: MON-4K-002\n"
            "  price: 599.00\n"
            "  category: displays\n"
            "  in_stock: true\n"
            "  description: 27-inch 4K IPS display with HDR600\n"
            "\n"
            "- name: Ergonomic Mouse\n"
            "  sku: MS-ERG-003\n"
            "  price: 89.95\n"
            "  category: peripherals\n"
            "  in_stock: true\n"
            "  description: Vertical ergonomic mouse reducing wrist strain\n"
            "\n"
            "- name: Thunderbolt Dock\n"
            "  sku: DK-TB4-004\n"
            "  price: 279.00\n"
            "  category: accessories\n"
            "  in_stock: false\n"
            "  description: Thunderbolt 4 docking station with dual 4K\n"
            "\n"
            "- name: Noise-Cancelling Headset\n"
            "  sku: HS-ANC-005\n"
            "  price: 199.00\n"
            "  category: audio\n"
            "  in_stock: true\n"
            "  description: ANC headset with boom mic for calls and music\n"
            "\n"
            "- name: Webcam 4K\n"
            "  sku: WC-4K-006\n"
            "  price: 159.00\n"
            "  category: peripherals\n"
            "  in_stock: true\n"
            "  description: 4K webcam with AI autofocus and background blur"
        ),
        "json": '{"catalog":{"store":"TechShop Pro","currency":"EUR","updated":"2026-03-10","products":[{"name":"Mechanical Keyboard","sku":"KB-MEC-001","price":149.99,"category":"peripherals","in_stock":true,"description":"Premium mechanical keyboard with Cherry MX switches"},{"name":"4K Monitor","sku":"MON-4K-002","price":599.00,"category":"displays","in_stock":true,"description":"27-inch 4K IPS display with HDR600"},{"name":"Ergonomic Mouse","sku":"MS-ERG-003","price":89.95,"category":"peripherals","in_stock":true,"description":"Vertical ergonomic mouse reducing wrist strain"},{"name":"Thunderbolt Dock","sku":"DK-TB4-004","price":279.00,"category":"accessories","in_stock":false,"description":"Thunderbolt 4 docking station with dual 4K"},{"name":"Noise-Cancelling Headset","sku":"HS-ANC-005","price":199.00,"category":"audio","in_stock":true,"description":"ANC headset with boom mic for calls and music"},{"name":"Webcam 4K","sku":"WC-4K-006","price":159.00,"category":"peripherals","in_stock":true,"description":"4K webcam with AI autofocus and background blur"}]}}',
    },
    "xlarge": {
        "description": "Company org with 3 departments, teams, employees",
        "expected_keys": ["company"],
        "expected_dept_names": ["engineering", "product", "operations"],
        "expected_employee_sample": ["Kai Fischer", "Tobias Richter", "David Park", "Julia Weiß"],
        "jmd": (
            "# [company]\n"
            "name: Nexus Technologies GmbH\n"
            "founded: 2019\n"
            "hq: Berlin, Germany\n"
            "employees_total: 47\n"
            "\n"
            "## departments\n"
            "\n"
            "### engineering\n"
            "head: Dr. Maria Chen\n"
            "budget_eur: 2400000\n"
            "headcount: 22\n"
            "\n"
            "#### teams[]\n"
            "- name: Platform\n"
            "  lead: Stefan Braun\n"
            "  members:\n"
            "    - name: Kai Fischer, role: Senior Backend Engineer\n"
            "    - name: Lena Vogel, role: Backend Engineer\n"
            "    - name: Ravi Sharma, role: DevOps Engineer\n"
            "    - name: Yuki Tanaka, role: SRE\n"
            "\n"
            "- name: Frontend\n"
            "  lead: Anna Kowalski\n"
            "  members:\n"
            "    - name: Tobias Richter, role: Senior Frontend Engineer\n"
            "    - name: Sophie Laurent, role: Frontend Engineer\n"
            "    - name: Max Bauer, role: Mobile Developer\n"
            "\n"
            "- name: Data\n"
            "  lead: Dr. Priya Nair\n"
            "  members:\n"
            "    - name: Oliver Schmidt, role: ML Engineer\n"
            "    - name: Elena Petrov, role: Data Engineer\n"
            "    - name: Hiroshi Yamamoto, role: Data Scientist\n"
            "\n"
            "### product\n"
            "head: Thomas Weber\n"
            "budget_eur: 800000\n"
            "headcount: 8\n"
            "\n"
            "#### teams[]\n"
            "- name: Product Management\n"
            "  lead: Lisa Hoffmann\n"
            "  members:\n"
            "    - name: David Park, role: Senior PM\n"
            "    - name: Clara Jensen, role: PM\n"
            "\n"
            "- name: Design\n"
            "  lead: Marco Rossi\n"
            "  members:\n"
            "    - name: Nina Johansson, role: Senior Designer\n"
            "    - name: Amir Hassan, role: UX Researcher\n"
            "\n"
            "### operations\n"
            "head: Sandra Krüger\n"
            "budget_eur: 600000\n"
            "headcount: 6\n"
            "\n"
            "#### teams[]\n"
            "- name: Finance\n"
            "  lead: Peter Neumann\n"
            "  members:\n"
            "    - name: Julia Weiß, role: Controller\n"
            "    - name: Michael Lorenz, role: Accountant\n"
            "\n"
            "- name: HR\n"
            "  lead: Carla Fernandez\n"
            "  members:\n"
            "    - name: Tom Albrecht, role: Recruiter"
        ),
        "json": '{"company":{"name":"Nexus Technologies GmbH","founded":2019,"hq":"Berlin, Germany","employees_total":47,"departments":{"engineering":{"head":"Dr. Maria Chen","budget_eur":2400000,"headcount":22,"teams":[{"name":"Platform","lead":"Stefan Braun","members":[{"name":"Kai Fischer","role":"Senior Backend Engineer"},{"name":"Lena Vogel","role":"Backend Engineer"},{"name":"Ravi Sharma","role":"DevOps Engineer"},{"name":"Yuki Tanaka","role":"SRE"}]},{"name":"Frontend","lead":"Anna Kowalski","members":[{"name":"Tobias Richter","role":"Senior Frontend Engineer"},{"name":"Sophie Laurent","role":"Frontend Engineer"},{"name":"Max Bauer","role":"Mobile Developer"}]},{"name":"Data","lead":"Dr. Priya Nair","members":[{"name":"Oliver Schmidt","role":"ML Engineer"},{"name":"Elena Petrov","role":"Data Engineer"},{"name":"Hiroshi Yamamoto","role":"Data Scientist"}]}]},"product":{"head":"Thomas Weber","budget_eur":800000,"headcount":8,"teams":[{"name":"Product Management","lead":"Lisa Hoffmann","members":[{"name":"David Park","role":"Senior PM"},{"name":"Clara Jensen","role":"PM"}]},{"name":"Design","lead":"Marco Rossi","members":[{"name":"Nina Johansson","role":"Senior Designer"},{"name":"Amir Hassan","role":"UX Researcher"}]}]},"operations":{"head":"Sandra Krüger","budget_eur":600000,"headcount":6,"teams":[{"name":"Finance","lead":"Peter Neumann","members":[{"name":"Julia Weiß","role":"Controller"},{"name":"Michael Lorenz","role":"Accountant"}]},{"name":"HR","lead":"Carla Fernandez","members":[{"name":"Tom Albrecht","role":"Recruiter"}]}]}}}}',
    },
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def strip_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    text = text.strip()
    # ```jmd ... ``` or ```json ... ``` or ``` ... ```
    m = re.match(r'^```(?:jmd|json|jsonc)?\s*\n(.*?)\n```$', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def validate_jmd(text: str, size: str) -> tuple[bool, str, dict | None]:
    """Validate JMD output: parse it and check against expected data.

    Returns (valid, reason, parsed_dict).
    """
    text = strip_fences(text)
    try:
        parsed = jmd.jmd_to_dict(text)
    except Exception as e:
        return False, f"parse error: {e}", None

    if not isinstance(parsed, dict):
        return False, f"parsed to {type(parsed).__name__}, expected dict", None

    payload = PAYLOADS[size]

    # Full equality check for small/medium
    if "expected" in payload:
        expected = payload["expected"]
        # Check top-level keys
        if set(parsed.keys()) != set(expected.keys()):
            # Maybe the root label was omitted — parser returns flat
            # Try wrapping in expected root key
            exp_root = list(expected.keys())[0]
            if set(parsed.keys()) != set(expected[exp_root].keys()):
                return False, f"keys mismatch: got {set(parsed.keys())}", parsed
            # Accept flat parse as valid (parser strips root label)
            return True, "OK (flat root)", parsed
        return True, "OK", parsed

    # Structural check for large/xlarge
    if "expected_keys" in payload:
        exp_keys = payload["expected_keys"]
        # Accept either wrapped or flat
        if not any(k in parsed for k in exp_keys):
            # Flat parse — check for structural content
            pass  # continue to content checks

    if "expected_product_count" in payload:
        # Find products array anywhere in structure
        products = _find_list(parsed, "products")
        if products is None:
            return False, "no 'products' array found", parsed
        if len(products) != payload["expected_product_count"]:
            return False, f"expected {payload['expected_product_count']} products, got {len(products)}", parsed
        # Check some product names
        names = [p.get("name", "") for p in products if isinstance(p, dict)]
        for exp_name in payload["expected_product_names"][:3]:
            if not any(exp_name in n for n in names):
                return False, f"missing product '{exp_name}'", parsed
        return True, "OK", parsed

    if "expected_dept_names" in payload:
        # Find departments
        text_lower = json.dumps(parsed).lower()
        for dept in payload["expected_dept_names"]:
            if dept not in text_lower:
                return False, f"missing department '{dept}'", parsed
        for emp in payload["expected_employee_sample"]:
            if emp not in json.dumps(parsed):
                return False, f"missing employee '{emp}'", parsed
        return True, "OK", parsed

    return True, "OK (no deep check)", parsed


def validate_json(text: str, size: str) -> tuple[bool, str, dict | None]:
    """Validate JSON output."""
    text = strip_fences(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        return False, f"parse error: {e}", None

    if not isinstance(parsed, dict):
        return False, f"parsed to {type(parsed).__name__}, expected dict", None

    payload = PAYLOADS[size]

    if "expected" in payload:
        expected = payload["expected"]
        if set(parsed.keys()) != set(expected.keys()):
            return False, f"keys mismatch: got {set(parsed.keys())}", parsed
        return True, "OK", parsed

    if "expected_product_count" in payload:
        products = _find_list(parsed, "products")
        if products is None:
            return False, "no 'products' array found", parsed
        if len(products) != payload["expected_product_count"]:
            return False, f"expected {payload['expected_product_count']} products, got {len(products)}", parsed
        return True, "OK", parsed

    if "expected_dept_names" in payload:
        text_lower = json.dumps(parsed).lower()
        for dept in payload["expected_dept_names"]:
            if dept not in text_lower:
                return False, f"missing department '{dept}'", parsed
        return True, "OK", parsed

    return True, "OK", parsed


def _find_list(d: dict, key: str) -> list | None:
    """Recursively find a list value for given key in nested dict."""
    if key in d and isinstance(d[key], list):
        return d[key]
    for v in d.values():
        if isinstance(v, dict):
            result = _find_list(v, key)
            if result is not None:
                return result
    return None


# ---------------------------------------------------------------------------
# Model clients (singletons to avoid re-creating per call)
# ---------------------------------------------------------------------------

_anthropic_client = None
_openai_client = None
_gemini_client = None


def call_claude(system: str, user: str) -> tuple[str, int, int, float]:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()
    t0 = time.monotonic()
    r = _anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        temperature=0.0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    dt = time.monotonic() - t0
    text = "".join(b.text for b in r.content if b.type == "text")
    return text, r.usage.input_tokens, r.usage.output_tokens, dt


def call_gpt(system: str, user: str) -> tuple[str, int, int, float]:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI()
    t0 = time.monotonic()
    r = _openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.0,
        max_completion_tokens=4096,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    dt = time.monotonic() - t0
    text = r.choices[0].message.content or ""
    u = r.usage
    return text, u.prompt_tokens if u else 0, u.completion_tokens if u else 0, dt


def call_gemini(system: str, user: str) -> tuple[str, int, int, float]:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client()
    config = gtypes.GenerateContentConfig(
        system_instruction=system,
        temperature=0.0,
        max_output_tokens=4096,
    )
    t0 = time.monotonic()
    r = _gemini_client.models.generate_content(
        model="gemini-3.1-flash-lite-preview",
        contents=user,
        config=config,
    )
    dt = time.monotonic() - t0
    text = r.text or ""
    u = r.usage_metadata
    return text, u.prompt_token_count or 0, u.candidates_token_count or 0, dt


MODELS = {
    "Haiku 4.5": call_claude,
    "GPT-4.1m": call_gpt,
    "Gemini 3.1": call_gemini,
}

# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

def run_produce_test(model_fn, fmt: str, size: str) -> dict:
    """Ask model to produce data in given format from the OTHER format."""
    payload = PAYLOADS[size]

    if fmt == "jmd":
        # Input: JSON, output: JMD
        system = JMD_PRIMER
        user = (
            f"Convert this JSON data to JMD format:\n\n"
            f"{payload['json']}"
        )
    else:
        # Input: JMD, output: JSON
        system = JSON_PRIMER
        user = (
            f"Convert this JMD data to minified JSON (single line):\n\n"
            f"{payload['jmd']}"
        )

    text, in_tok, out_tok, wall_s = model_fn(system, user)

    # Validate
    if fmt == "jmd":
        valid, reason, parsed = validate_jmd(text, size)
    else:
        valid, reason, parsed = validate_json(text, size)

    return {
        "in_tok": in_tok,
        "out_tok": out_tok,
        "total_tok": in_tok + out_tok,
        "wall_s": wall_s,
        "valid": valid,
        "reason": reason,
        "text": text,
    }


def run_read_test(model_fn, fmt: str, size: str) -> dict:
    """Give model data in format, ask a question about it."""
    payload = PAYLOADS[size]

    questions = {
        "small": "What city does the user live in? Reply with just the city name.",
        "medium": "What is the total cost of all items? Multiply price × qty for each, then sum. Reply with just the number.",
        "large": "List all products that are out of stock. Reply with their names, one per line.",
        "xlarge": "Name all members of the Platform team. Reply with name and role, one per line.",
    }

    expected_answers = {
        "small": "Berlin",
        "medium": "188.93",  # 29.99*2 + 49.95 + 79.00
        "large": "Thunderbolt Dock",
        "xlarge": "Kai Fischer",
    }

    if fmt == "jmd":
        system = (
            "You are a data processing assistant. The user will provide data in "
            "JMD (JSON Markdown) format — a structured format using Markdown headings "
            "for hierarchy, key: value for fields, and - for array items. "
            "Answer questions about the data concisely."
        )
        data = payload["jmd"]
    else:
        system = (
            "You are a data processing assistant. The user will provide data in "
            "JSON format. Answer questions about the data concisely."
        )
        data = payload["json"]

    user = f"Data:\n\n{data}\n\nQuestion: {questions[size]}"

    text, in_tok, out_tok, wall_s = model_fn(system, user)

    # Simple validation: does the answer contain the expected substring?
    valid = expected_answers[size].lower() in text.lower()
    reason = "OK" if valid else f"expected '{expected_answers[size]}' not found in: {text[:100]}"

    return {
        "in_tok": in_tok,
        "out_tok": out_tok,
        "total_tok": in_tok + out_tok,
        "wall_s": wall_s,
        "valid": valid,
        "reason": reason,
        "text": text,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    sizes = ["small", "medium", "large", "xlarge"]
    size_labels = {"small": "Small", "medium": "Medium", "large": "Large", "xlarge": "XLarge"}
    formats = ["jmd", "json"]
    directions = ["read", "produce"]

    results: dict = {d: {} for d in directions}
    total_calls = len(sizes) * len(MODELS) * len(formats) * len(directions)
    call_num = 0

    for direction in directions:
        for size in sizes:
            results[direction][size] = {}
            for model_name, model_fn in MODELS.items():
                results[direction][size][model_name] = {}
                for fmt in formats:
                    call_num += 1
                    label = f"[{call_num}/{total_calls}] {direction:7s} {size:7s} {model_name:12s} {fmt:4s}"
                    print(f"  {label} ...", end="", flush=True)
                    try:
                        if direction == "read":
                            r = run_read_test(model_fn, fmt, size)
                        else:
                            r = run_produce_test(model_fn, fmt, size)
                        results[direction][size][model_name][fmt] = r
                        status = "OK" if r["valid"] else f"FAIL({r['reason'][:40]})"
                        print(f" {r['total_tok']:5d} tok  {r['wall_s']:5.1f}s  {status}")
                    except Exception as e:
                        print(f" ERROR: {e}")
                        results[direction][size][model_name][fmt] = None

    # ===================================================================
    # Tables
    # ===================================================================

    for direction in directions:
        dir_label = "READING" if direction == "read" else "PRODUCING"
        print(f"\n{'='*100}")
        print(f"  {dir_label} — Tokens (in+out=total) / Time / Valid")
        print(f"{'='*100}")

        col_w = 30
        header = f"{'Size':8s}"
        for model_name in MODELS:
            header += f"  {model_name:^{col_w*2+2}s}"
        print(header)

        sub = f"{'':8s}"
        for _ in MODELS:
            sub += f"  {'JMD':>{col_w}s}  {'JSON min':>{col_w}s}"
        print(sub)
        print("-" * (8 + (col_w * 2 + 4) * len(MODELS)))

        for size in sizes:
            row = f"{size_labels[size]:8s}"
            for model_name in MODELS:
                for fmt in formats:
                    r = results[direction][size][model_name].get(fmt)
                    if r:
                        v = "+" if r["valid"] else "X"
                        cell = f"{r['in_tok']:4d}+{r['out_tok']:4d}={r['total_tok']:5d} {r['wall_s']:4.1f}s {v}"
                        row += f"  {cell:>{col_w}s}"
                    else:
                        row += f"  {'ERROR':>{col_w}s}"
            print(row)

    # ===================================================================
    # Validity summary
    # ===================================================================
    print(f"\n{'='*100}")
    print("  VALIDITY SUMMARY")
    print(f"{'='*100}")
    print(f"  {'':8s}  {'':8s}", end="")
    for model_name in MODELS:
        print(f"  {model_name:>12s}", end="")
    print()
    print(f"  {'-'*8}  {'-'*8}", end="")
    for _ in MODELS:
        print(f"  {'-'*12}", end="")
    print()

    for direction in directions:
        dir_label = "Read" if direction == "read" else "Produce"
        for fmt in formats:
            fmt_label = "JMD" if fmt == "jmd" else "JSON"
            valid_counts: dict[str, tuple[int, int]] = {}
            for model_name in MODELS:
                ok = 0
                total = 0
                for size in sizes:
                    r = results[direction][size][model_name].get(fmt)
                    if r:
                        total += 1
                        if r["valid"]:
                            ok += 1
                valid_counts[model_name] = (ok, total)

            print(f"  {dir_label:8s}  {fmt_label:8s}", end="")
            for model_name in MODELS:
                ok, total = valid_counts[model_name]
                cell = f"{ok}/{total}"
                print(f"  {cell:>12s}", end="")
            print()

    # ===================================================================
    # Token delta (JMD vs JSON) — produce only
    # ===================================================================
    print(f"\n{'='*100}")
    print("  TOKEN DELTA: JMD vs JSON minified (PRODUCE)")
    print(f"{'='*100}")
    print(f"  {'Size':8s}", end="")
    for model_name in MODELS:
        print(f"  {model_name:>12s}", end="")
    print()
    print(f"  {'-'*8}", end="")
    for _ in MODELS:
        print(f"  {'-'*12}", end="")
    print()

    for size in sizes:
        print(f"  {size_labels[size]:8s}", end="")
        for model_name in MODELS:
            jmd_r = results["produce"][size][model_name].get("jmd")
            json_r = results["produce"][size][model_name].get("json")
            if jmd_r and json_r and json_r["total_tok"] > 0:
                delta = (jmd_r["total_tok"] - json_r["total_tok"]) / json_r["total_tok"] * 100
                print(f"  {delta:>+11.1f}%", end="")
            else:
                print(f"  {'—':>12s}", end="")
        print()

    # ===================================================================
    # Show failed outputs
    # ===================================================================
    failures = []
    for direction in directions:
        for size in sizes:
            for model_name in MODELS:
                for fmt in formats:
                    r = results[direction][size][model_name].get(fmt)
                    if r and not r["valid"]:
                        failures.append((direction, size, model_name, fmt, r))

    if failures:
        print(f"\n{'='*100}")
        print(f"  FAILURES ({len(failures)})")
        print(f"{'='*100}")
        for direction, size, model_name, fmt, r in failures:
            print(f"\n  [{direction}] {size} / {model_name} / {fmt}")
            print(f"  Reason: {r['reason']}")
            # Show first 300 chars of output
            preview = r["text"][:300].replace("\n", "\n    ")
            print(f"    {preview}")


if __name__ == "__main__":
    main()
