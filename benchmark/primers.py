"""JMD primer variants for system prompts.

Assessment feedback: test 2-3 primer variants to quantify primer effect
on JMD correctness. The primer is part of the overhead JMD must recoup
through payload savings.
"""

PRIMERS: dict[str, dict[str, str]] = {
    # --- JSON primers (identical for pretty/minified) ---
    "json": {
        "minimal": (
            "You communicate with REST APIs using JSON."
        ),
        "standard": (
            "You are an API agent. You communicate with REST APIs using JSON.\n"
            "When you receive data, it will be in JSON format.\n"
            "When you need to send data to an API, produce valid JSON."
        ),
        "example": (
            "You are an API agent. You communicate with REST APIs using JSON.\n"
            "When you receive data, it will be in JSON format.\n"
            "When you need to send data to an API, produce valid JSON."
        ),
        "strict": (
            "You are an API agent. You communicate with REST APIs using JSON.\n"
            "When you receive data, it will be in JSON format.\n"
            "When you need to send data to an API, produce valid JSON."
        ),
    },

    # --- YAML primers ---
    "yaml": {
        "minimal": (
            "You communicate with REST APIs using YAML."
        ),
        "standard": (
            "You are an API agent. You communicate with REST APIs using YAML.\n"
            "When you receive data, it will be in YAML format.\n"
            "When you need to send data to an API, produce valid YAML."
        ),
        "example": (
            "You are an API agent. You communicate with REST APIs using YAML.\n"
            "When you receive data, it will be in YAML format.\n"
            "When you need to send data to an API, produce valid YAML."
        ),
        "strict": (
            "You are an API agent. You communicate with REST APIs using YAML.\n"
            "When you receive data, it will be in YAML format.\n"
            "When you need to send data to an API, produce valid YAML."
        ),
    },

    # --- JMD primers (4 variants) ---
    "jmd": {
        "minimal": (
            "You communicate with REST APIs using JMD (JSON Markdown). "
            "JMD uses Markdown headings for hierarchy. # root, ## nested objects, "
            "## key[] for arrays, - for items. key: value syntax. "
            "No braces or quotes on keys."
        ),
        "standard": (
            "You are an API agent. You communicate with REST APIs using "
            "JMD (JSON Markdown).\n"
            "JMD uses Markdown headings for hierarchy: # for root, "
            "## for nested objects,\n"
            "## key[] for arrays, - for array items. Fields use key: value syntax.\n"
            "Array items: - key: val on first line, indented continuation for more fields. No braces, no quotes on keys.\n"
            "When you need to send data to an API, produce valid JMD."
        ),
        "example": (
            "You are an API agent. You communicate with REST APIs using "
            "JMD (JSON Markdown).\n"
            "JMD maps to JSON using Markdown syntax. Example:\n"
            "# Order\n"
            "id: 42\n"
            "status: pending\n"
            "## customer\n"
            "name: Jane Doe\n"
            "## items[]\n"
            "- sku: A1\n"
            "  qty: 2\n"
            "  price: 19.99\n"
            "- sku: B2\n"
            "  qty: 1\n"
            "  price: 49.99\n\n"
            "No braces, no quotes on keys. Headings define scope."
        ),
        "strict": (
            "You are an API agent. You communicate with REST APIs using "
            "JMD (JSON Markdown).\n\n"
            "JMD rules:\n"
            "- EVERY response MUST start with # Label (the root object heading)\n"
            "- ## key opens a nested object; depth = heading level\n"
            "- ## key[] declares an array; items start with -\n"
            "- Fields: key: value (no braces, no quotes on keys)\n"
            "- Array object items: - first_key: val on first line, then indented continuation fields\n"
            "- > blockquote for multiline text (on its own line, not inline)\n\n"
            "Example — flat object:\n"
            "# Availability\n"
            "product_id: PROD-42\n"
            "in_stock: true\n"
            "quantity: 7\n\n"
            "Example — nested object with array:\n"
            "# Order\n"
            "id: 42\n"
            "status: pending\n"
            "## customer\n"
            "name: Jane Doe\n"
            "## items[]\n"
            "- sku: A1\n"
            "  qty: 2\n"
            "  price: 19.99\n"
            "- sku: B2\n"
            "  qty: 1\n"
            "  price: 49.99"
        ),
    },
}


def get_primer(format_name: str, variant: str) -> str:
    """Return the primer text for a given format and variant."""
    if format_name.startswith("json"):
        return PRIMERS["json"][variant]
    if format_name == "yaml":
        return PRIMERS["yaml"][variant]
    return PRIMERS["jmd"][variant]
