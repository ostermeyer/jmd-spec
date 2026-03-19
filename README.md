# JMD — JSON Markdown

A structured data format for LLM-driven infrastructure. JMD is what language models produce naturally when asked to organize data — formalized into a specification.

---

## The Problem with JSON

Language models generate JSON reliably — until the document is large, deeply nested, or streamed. At that point, the format works against the model: brace pairs must be opened and closed across hundreds or thousands of tokens, with the matching delimiter sometimes megabytes away. Syntax errors accumulate at structure boundaries. Partial documents are unparseable.

JMD solves this by replacing matched delimiters with heading depth. The current scope is always visible in the most recent heading line. There is nothing to close.

---

## A Quick Example

A JMD document looks like this:

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

The equivalent JSON requires 43% more tokens — and cannot be streamed field by field.

---

## Why JMD

Benchmarks show:

**Efficient.** 25–34% fewer output tokens than pretty-printed JSON, across six models from three providers. 13–31% less server processing time. Real compute saved, not cosmetic compression.

**Streamable.** Every completed line is a parseable field event. The first useful byte arrives with the first line — not after the closing `}`. For large payloads, the streaming advantage reaches 15×.

**Complete.** JMD is a tetradic protocol: data (`#`), schema (`#!`), query (`#?`), and delete (`#-`) share one syntax. An LLM that knows one mode knows all four.

---

## Teaching JMD to an LLM

The minimal instruction that produces correct JMD output — validated across Claude, GPT, and Gemini:

```text
JMD rules:
- # Label starts the root object; ## key opens nested objects (depth = nesting)
- ## key[] declares an array; items start with - (no sub-headings per item)
- key: value for fields, no other markup
- Array objects: - key: value, indented continuation lines
- > blockquotes for multiline text
```

Five rules. No examples required.

---

## Documents

| Document | Description |
|---|---|
| [jmd-spec-v0_3.md](jmd-spec-v0_3.md) | Full format specification |
| [ai-whispering.md](ai-whispering.md) | The design methodology behind JMD |
| [jmd-efficiency-analysis.md](jmd-efficiency-analysis.md) | Benchmark results, performance data, and projections |
| [BENCHMARKS.md](BENCHMARKS.md) | Methodology, prompts, and raw results |

---

## Status

The specification is stable at v0.3. A Python reference implementation is available at [jmd](https://github.com/ostermeyer/jmd), including a C-accelerated parser and serializer.

---

## License

The JMD specification is licensed under [CC BY-NC-SA 4.0](LICENSE). Commercial use requires a separate agreement.
