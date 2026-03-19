#!/usr/bin/env python3
"""Tokenization analysis: structural vs content tokens in JMD, JSON, YAML.

Measures the "signal-to-noise ratio" of each format — how many tokens carry
actual data vs how many are pure structural overhead.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import tiktoken

# ---------------------------------------------------------------------------
# Test payloads — same data in 3 formats
# ---------------------------------------------------------------------------

PAYLOADS = {
    "small": {
        "label": "Small (user profile, 4 fields)",
        "jmd": (
            "# [user]\n"
            "name: Alice Müller\n"
            "email: alice@example.com\n"
            "age: 34\n"
            "city: Berlin"
        ),
        "json_min": '{"user":{"name":"Alice Müller","email":"alice@example.com","age":34,"city":"Berlin"}}',
        "json_pretty": json.dumps(
            {"user": {"name": "Alice Müller", "email": "alice@example.com", "age": 34, "city": "Berlin"}},
            indent=2,
        ),
    },
    "medium": {
        "label": "Medium (order, 3 items, nested)",
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
        "json_min": '{"order":{"id":"ORD-2024-7891","status":"shipped","customer":{"name":"Bob Schmidt","email":"bob@example.com"},"items":[{"name":"Wireless Mouse","price":29.99,"qty":2},{"name":"USB-C Hub","price":49.95,"qty":1},{"name":"Monitor Stand","price":79.00,"qty":1}],"shipping":{"street":"Hauptstraße 42","city":"München","zip":"80331","country":"DE","method":"express"},"payment":{"method":"credit_card","last4":"4242","status":"charged"}}}',
        "json_pretty": json.dumps(
            {"order": {"id": "ORD-2024-7891", "status": "shipped",
                       "customer": {"name": "Bob Schmidt", "email": "bob@example.com"},
                       "items": [
                           {"name": "Wireless Mouse", "price": 29.99, "qty": 2},
                           {"name": "USB-C Hub", "price": 49.95, "qty": 1},
                           {"name": "Monitor Stand", "price": 79.00, "qty": 1},
                       ],
                       "shipping": {"street": "Hauptstraße 42", "city": "München", "zip": "80331", "country": "DE", "method": "express"},
                       "payment": {"method": "credit_card", "last4": "4242", "status": "charged"}}},
            indent=2,
        ),
    },
    "large": {
        "label": "Large (catalog, 6 products)",
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
        "json_min": '{"catalog":{"store":"TechShop Pro","currency":"EUR","updated":"2026-03-10","products":[{"name":"Mechanical Keyboard","sku":"KB-MEC-001","price":149.99,"category":"peripherals","in_stock":true,"description":"Premium mechanical keyboard with Cherry MX switches"},{"name":"4K Monitor","sku":"MON-4K-002","price":599.00,"category":"displays","in_stock":true,"description":"27-inch 4K IPS display with HDR600"},{"name":"Ergonomic Mouse","sku":"MS-ERG-003","price":89.95,"category":"peripherals","in_stock":true,"description":"Vertical ergonomic mouse reducing wrist strain"},{"name":"Thunderbolt Dock","sku":"DK-TB4-004","price":279.00,"category":"accessories","in_stock":false,"description":"Thunderbolt 4 docking station with dual 4K"},{"name":"Noise-Cancelling Headset","sku":"HS-ANC-005","price":199.00,"category":"audio","in_stock":true,"description":"ANC headset with boom mic for calls and music"},{"name":"Webcam 4K","sku":"WC-4K-006","price":159.00,"category":"peripherals","in_stock":true,"description":"4K webcam with AI autofocus and background blur"}]}}',
        "json_pretty": json.dumps(
            {"catalog": {"store": "TechShop Pro", "currency": "EUR", "updated": "2026-03-10", "products": [
                {"name": "Mechanical Keyboard", "sku": "KB-MEC-001", "price": 149.99, "category": "peripherals", "in_stock": True, "description": "Premium mechanical keyboard with Cherry MX switches"},
                {"name": "4K Monitor", "sku": "MON-4K-002", "price": 599.00, "category": "displays", "in_stock": True, "description": "27-inch 4K IPS display with HDR600"},
                {"name": "Ergonomic Mouse", "sku": "MS-ERG-003", "price": 89.95, "category": "peripherals", "in_stock": True, "description": "Vertical ergonomic mouse reducing wrist strain"},
                {"name": "Thunderbolt Dock", "sku": "DK-TB4-004", "price": 279.00, "category": "accessories", "in_stock": False, "description": "Thunderbolt 4 docking station with dual 4K"},
                {"name": "Noise-Cancelling Headset", "sku": "HS-ANC-005", "price": 199.00, "category": "audio", "in_stock": True, "description": "ANC headset with boom mic for calls and music"},
                {"name": "Webcam 4K", "sku": "WC-4K-006", "price": 159.00, "category": "peripherals", "in_stock": True, "description": "4K webcam with AI autofocus and background blur"},
            ]}},
            indent=2,
        ),
    },
}


# ---------------------------------------------------------------------------
# Tokenization helpers
# ---------------------------------------------------------------------------

# JSON structural characters
JSON_STRUCTURAL = set('{}[]",')
# JMD structural patterns (headings markers, colons as separators, dashes as list markers)
JMD_STRUCTURAL_RE = re.compile(r'^#{1,6}\s|\[\]$|^\s*-\s', re.MULTILINE)


def classify_tokens_json(text: str, enc: tiktoken.Encoding) -> dict:
    """Classify JSON tokens as structural vs content."""
    tokens = enc.encode(text)
    structural = 0
    content = 0
    whitespace = 0

    for tok_id in tokens:
        tok_str = enc.decode([tok_id])
        stripped = tok_str.strip()

        if not stripped:
            whitespace += 1
        elif all(c in JSON_STRUCTURAL for c in stripped):
            structural += 1
        elif stripped == ':':
            structural += 1
        else:
            # Mixed tokens (e.g. ',"name') — count as structural if mostly structural
            struct_chars = sum(1 for c in tok_str if c in JSON_STRUCTURAL or c == ':')
            if struct_chars > len(tok_str) / 2:
                structural += 1
            else:
                content += 1

    return {"total": len(tokens), "structural": structural, "content": content, "whitespace": whitespace}


def classify_tokens_jmd(text: str, enc: tiktoken.Encoding) -> dict:
    """Classify JMD tokens as structural vs content."""
    tokens = enc.encode(text)
    structural = 0
    content = 0
    whitespace = 0

    # Get the raw text for each token
    for tok_id in tokens:
        tok_str = enc.decode([tok_id])
        stripped = tok_str.strip()

        if not stripped:
            whitespace += 1
        elif stripped.startswith('#'):
            structural += 1
        elif stripped in ('[]', '-', '- ', ':', '##', '###', '####'):
            structural += 1
        else:
            content += 1

    return {"total": len(tokens), "structural": structural, "content": content, "whitespace": whitespace}


def count_tokens_anthropic(text: str) -> int:
    """Count tokens using Anthropic's API."""
    import anthropic
    client = anthropic.Anthropic()
    result = client.messages.count_tokens(
        model="claude-haiku-4-5-20251001",
        messages=[{"role": "user", "content": text}],
    )
    return result.input_tokens


def count_tokens_gemini(text: str) -> int:
    """Count tokens using Gemini's API."""
    from google import genai
    client = genai.Client()
    result = client.models.count_tokens(
        model="gemini-3.1-flash-lite-preview",
        contents=text,
    )
    return result.total_tokens


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    enc_gpt = tiktoken.encoding_for_model("gpt-4o")  # cl100k_base

    formats = ["jmd", "json_min", "json_pretty"]
    fmt_labels = {"jmd": "JMD", "json_min": "JSON min", "json_pretty": "JSON pretty"}

    # ===================================================================
    # Part 1: Token counts across all three tokenizers
    # ===================================================================
    print("=" * 90)
    print("  TOKEN COUNTS BY TOKENIZER")
    print("  (Same data, 3 formats, 3 tokenizers)")
    print("=" * 90)

    col_w = 14
    print(f"\n  {'':30s}", end="")
    for fmt in formats:
        print(f"  {fmt_labels[fmt]:^{col_w * 3 + 4}s}", end="")
    print()
    print(f"  {'':30s}", end="")
    for _ in formats:
        print(f"  {'OpenAI':>{col_w}s}{'Claude':>{col_w}s}{'Gemini':>{col_w}s}  ", end="")
    print()
    print("  " + "-" * (30 + (col_w * 3 + 4) * len(formats)))

    for size, payload in PAYLOADS.items():
        print(f"  {payload['label']:30s}", end="")
        for fmt in formats:
            text = payload[fmt]
            tok_gpt = len(enc_gpt.encode(text))
            tok_claude = count_tokens_anthropic(text)
            tok_gemini = count_tokens_gemini(text)
            print(f"  {tok_gpt:>{col_w}d}{tok_claude:>{col_w}d}{tok_gemini:>{col_w}d}  ", end="")
        print()

    # Delta rows
    print()
    print(f"  {'DELTA vs JSON minified':30s}", end="")
    for fmt in formats:
        print(f"  {'OpenAI':>{col_w}s}{'Claude':>{col_w}s}{'Gemini':>{col_w}s}  ", end="")
    print()
    print("  " + "-" * (30 + (col_w * 3 + 4) * len(formats)))

    for size, payload in PAYLOADS.items():
        print(f"  {payload['label']:30s}", end="")
        json_min_text = payload["json_min"]
        base_gpt = len(enc_gpt.encode(json_min_text))
        base_claude = count_tokens_anthropic(json_min_text)
        base_gemini = count_tokens_gemini(json_min_text)

        for fmt in formats:
            text = payload[fmt]
            tok_gpt = len(enc_gpt.encode(text))
            tok_claude = count_tokens_anthropic(text)
            tok_gemini = count_tokens_gemini(text)

            d_gpt = (tok_gpt - base_gpt) / base_gpt * 100
            d_claude = (tok_claude - base_claude) / base_claude * 100
            d_gemini = (tok_gemini - base_gemini) / base_gemini * 100

            print(f"  {d_gpt:>+13.1f}%{d_claude:>+13.1f}%{d_gemini:>+13.1f}%  ", end="")
        print()

    # ===================================================================
    # Part 2: Structural vs Content token analysis (OpenAI tokenizer)
    # ===================================================================
    print(f"\n\n{'=' * 90}")
    print("  STRUCTURAL vs CONTENT TOKENS (OpenAI tokenizer)")
    print("  structural = format overhead ({}\",:[]) | content = actual data")
    print("=" * 90)

    print(f"\n  {'':30s}  {'Total':>8s}  {'Struct':>8s}  {'Content':>8s}  {'WS':>6s}  {'Signal%':>8s}")
    print("  " + "-" * 80)

    for size, payload in PAYLOADS.items():
        print(f"\n  {payload['label']}")
        for fmt in ["jmd", "json_min", "json_pretty"]:
            text = payload[fmt]
            if fmt == "jmd":
                stats = classify_tokens_jmd(text, enc_gpt)
            else:
                stats = classify_tokens_json(text, enc_gpt)

            total = stats["total"]
            signal_pct = stats["content"] / total * 100 if total else 0
            print(
                f"    {fmt_labels[fmt]:26s}  "
                f"{total:>8d}  {stats['structural']:>8d}  {stats['content']:>8d}  "
                f"{stats['whitespace']:>6d}  {signal_pct:>7.1f}%"
            )

    # ===================================================================
    # Part 3: Bytes vs Tokens efficiency
    # ===================================================================
    print(f"\n\n{'=' * 90}")
    print("  BYTES vs TOKENS (OpenAI tokenizer)")
    print("  bytes/token = encoding density — higher means more data per token")
    print("=" * 90)

    print(f"\n  {'':30s}  {'Bytes':>8s}  {'Tokens':>8s}  {'B/tok':>8s}")
    print("  " + "-" * 60)

    for size, payload in PAYLOADS.items():
        print(f"\n  {payload['label']}")
        for fmt in ["jmd", "json_min", "json_pretty"]:
            text = payload[fmt]
            byte_len = len(text.encode("utf-8"))
            tok_count = len(enc_gpt.encode(text))
            bpt = byte_len / tok_count if tok_count else 0
            print(f"    {fmt_labels[fmt]:26s}  {byte_len:>8d}  {tok_count:>8d}  {bpt:>8.2f}")


if __name__ == "__main__":
    main()
