# JMD — JSON Markdown

A structured data format for LLM-driven infrastructure. JMD is what language
models produce naturally when asked to organize data — formalized into a
specification, benchmarked across seven models from four providers.

---

## The Problem with JSON

Language models generate JSON reliably — until the document is large, deeply
nested, or streamed. At that point, the format works against the model: brace
pairs must be opened and closed across hundreds or thousands of tokens, with the
matching delimiter sometimes megabytes away. Syntax errors accumulate at
structure boundaries. Partial documents are unparseable.

JMD solves this by replacing matched delimiters with heading depth. The current
scope is always visible in the most recent heading line. There is nothing to
close.

---

## A Quick Example

```markdown
# Order
order_id: 4521
status: confirmed
created: 2026-03-19

## customer
name: Anna Müller
email: anna@example.com

## items[]
- product: Laptop Stand
  qty: 1
  price: 49.90
- product: USB Hub
  qty: 2
  price: 19.95
```

---

## What the Benchmarks Show

Tested across seven models from four providers (Anthropic, OpenAI, Mistral,
Google), approximately 6,000 API calls, three independent domain scenarios:

**99.7% syntax validity** across 720 five-step agentic chains — versus 95.6%
for JSON. A 4.4% per-step error rate compounds to a ~20% chain failure rate
under JSON; under JMD it is ~1.5%.

**8–18% fewer output tokens** in production chain execution; **22% fewer
payload tokens** when passing outputs between agents (consistent across
providers). A separate format fidelity test showed 28–34% savings in pure
structural overhead.

**Up to 15× faster streaming** time-to-first-usable-byte. Every completed JMD
line is a parseable field event. A partial JMD document is not a broken document
— it contains all fields received so far. A partial JSON document is a parse
error.

**98.5% spontaneous adoption** of optional epistemic metadata fields
(`confidence`, `source`, `uncertain`) when named in the primer — without
instruction to use them. Their presence reduced downstream hallucination rates
by 41% and raised conflict acknowledgment from 48% to 99% in realistic
prompting conditions.

Full methodology, all prompts, and raw results: [BENCHMARKS.md](BENCHMARKS.md)

---

## Teaching JMD to an LLM

Five rules. Approximately 80 tokens. No examples required for preliminary
testing; the extended primer (~130 tokens, one worked example) is recommended
for production use.

```text
JMD rules:
- # Label starts the root object; ## key opens nested objects (depth = nesting)
- ## key[] declares an array; items start with - (no sub-headings per item)
- key: value for fields, no other markup
- Array objects: - key: value, indented continuation lines
- > blockquotes for multiline text
```

Validated across Claude, GPT-5.4, Mistral Large, and Gemini 2.5 Flash.

---

## Complete Protocol

JMD is a tetradic protocol — one syntax covers the full data lifecycle:

| Marker | Mode   | Purpose                              |
|--------|--------|--------------------------------------|
| `#`    | Data   | Structured data transport            |
| `#!`   | Schema | Field contracts and type declarations|
| `#?`   | Query  | Query by Example — filter criteria   |
| `#-`   | Delete | Resource deletion by identifier      |

A model that produces a JMD data document already knows how to produce a query,
schema, or delete. The root marker is the only difference, and it appears at
position zero before any field is generated.

---

## Documents

| Document | Description |
|---|---|
| [jmd-spec-v0_3.md](jmd-spec-v0_3.md) | Full format specification |
| [BENCHMARKS.md](BENCHMARKS.md) | Methodology, all prompts, and raw results |
| [ai-whispering.md](ai-whispering.md) | The design practice behind JMD |
| [jmd-efficiency-analysis.md](jmd-efficiency-analysis.md) | Performance data and projections |

---

## Implementation

A Python reference implementation with C-accelerated parser and serializer is
available at [jmd-impl](https://github.com/ostermeyer/jmd-impl).

Parser throughput: **1.7–2.1× faster than `json.loads`** across payload sizes.
Serializer throughput: comparable gains over `json.dumps`.

---

## Status

Specification stable at v0.3. Benchmarks completed. A research preprint
describing the empirical findings is forthcoming on arXiv.

---

## License

The JMD specification is licensed under
[CC BY-NC-SA 4.0](LICENSE). Commercial use requires a separate agreement.
Code in this repository is licensed under [MIT](LICENSE-CODE).
