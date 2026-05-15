# JMD Roadmap

This document describes the current state of the specification and the direction of planned work. It is a living document — priorities may shift based on community feedback and adoption.

---

## Current Status — v0.3.3 (stable)

The specification is stable. The core syntax, document modes, and epistemic frontmatter are defined and will not change in breaking ways. The benchmark suite is complete.

v0.3.3 is a non-breaking refinement of v0.3.2. It formalizes three parser-tolerance rules drawn from observed LLM behavior: array promotion for repeated headings without `[]` (§7.4), tolerance of stray `---` markers around the frontmatter block (§3.5.1), and tolerance of YAML-style block-scalar syntax (`key: |`, `key: >`) as an alternative to the canonical blockquote form (§5.2). Each rule is paired with a generator-strict canonical form so that round-trips converge to a single representation. The §7.4 rule additionally specifies three structured error conditions that were previously implementation-defined (sigil conflict, repeated explicit array, repeated scalar key) — closing the most common silent-data-loss class in early JMD implementations. Documents valid under v0.3.2 remain valid under v0.3.3.

Previous refinements:
- v0.3.2: de-normativized QBE filter syntax (§13) and schema type vocabulary (§14), moving both to a non-normative Appendix A. Structural grammar remains normative; filter and type dialects are recommended conventions that applications may adopt, extend, or replace.
- v0.3.1: inline Markdown rule (§5.1), frontmatter preservation and application-layer policies (§3.5, §23.7).

What exists today:

- Full format specification ([jmd-spec-v0_3.md](jmd-spec-v0_3.md) — currently v0.3.3)
- Benchmark methodology and raw results ([BENCHMARKS.md](BENCHMARKS.md), [benchmark_results/](benchmark_results/))
- Python reference implementation with C-accelerated parser and serializer ([jmd-impl](https://github.com/ostermeyer/jmd-impl), v0.4.4)
- JavaScript reference implementation, pure ESM, zero dependencies ([jmd-js](https://github.com/ostermeyer/jmd-js), v0.1.2)
- Design rationale ([ai-whispering.md](ai-whispering.md))
- Performance analysis ([jmd-efficiency-analysis.md](jmd-efficiency-analysis.md))
- Research preprint (forthcoming on arXiv)

---

## Near Term

**Broader model coverage**
The current benchmark covers seven models from four providers. Priority is extending coverage to open-weight models — Llama, Qwen, Mistral, Phi, Gemma — run locally via Ollama and similar, to establish whether the behavioral alignment properties hold independent of provider-specific training choices.

**Implementations in additional languages**
JavaScript is available as of v0.1.2 ([jmd-js](https://github.com/ostermeyer/jmd-js)). Go and Rust remain open. See [CONTRIBUTING.md](CONTRIBUTING.md) for details on what a useful implementation looks like.

**Framework adapters**
Adapters for LangChain, LlamaIndex, and Pydantic AI that make JMD available as a structured output format without requiring manual prompt engineering.

---

## Medium Term

**Calibration benchmark for epistemic frontmatter**
The current benchmark measures adoption rates and downstream effects of epistemic fields. It does not measure calibration — whether the confidence and uncertainty signals models produce are accurate. A calibration benchmark is the logical next step for the RQ3 findings.

**Specification v0.4**
A further minor revision driven by adoption feedback beyond the refinements in v0.3.3. Candidate topics: a streaming-parser specification (event vocabulary, document-boundary semantics for multi-document streams, conformance for stream-based backends), calibration conventions for epistemic frontmatter, additional directive/descriptive frontmatter keys that emerge from production MCP servers, refinements to the JMD-over-XML companion specification, and a potential companion specification for rich-text content (`jmd-richtext`). No breaking changes planned — v0.4 will remain a strict superset of v0.3.3.

**MCP server**
A Model Context Protocol server that exposes JMD parsing, serialization, and validation as tools, enabling JMD-native communication in MCP-based agentic systems.

---

## Longer Term

**Foundation for Sustainable AI Infrastructure**
JMD is one concrete instantiation of a broader principle: systems that align with natural model behavior consume less compute, produce more reliable outputs, and communicate more faithfully. The longer-term goal is an organizational home for this work — funding research, building tooling, and establishing compute efficiency as a first-class concern in LLM-driven systems.

If this direction interests you — as a researcher, engineer, or potential founding member — reach out: [andreas@ostermeyer.de](mailto:andreas@ostermeyer.de)

---

## What Is Not Planned

**Breaking changes to v0.3.x syntax**
The core syntax is stable. Any future version will be a strict superset.

**A centralized registry or package index**
JMD is a specification, not a managed ecosystem. Implementations live in their own repositories.

**Governance structures before there is a community**
Process follows people, not the other way around.
