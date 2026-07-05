# JMD Roadmap

This document describes the current state of the specification and the direction of planned work. It is a living document — priorities may shift based on community feedback and adoption.

---

## Current Status — v0.3.5

The specification version is maintained in exactly one place — the README status line — and referenced everywhere else.

v0.3.5 (2026-07) is a consolidation release. It resolves the normative self-contradictions introduced by the v0.3.4 level-pop transition (§8.6a, §22.1, §22.2 and the recommended test cases now consistently describe the level-pop as canonical, `---` as parser-consumed decoration), unifies anonymous-heading semantics (root: opens root scope; depth ≥ 2: level-pop; `{"": …}` via quoted empty key `## ""`), adds the normative lexical layer §11.2 (canonical LF, CRLF tolerance, lone CR as parse error, BOM consumption, trailing-whitespace trimming, tolerant INDENT), the one-document rule (§18.0), a Security Considerations section (§24) including the structure-injection rule, an updated EBNF covering all four mode markers and the level-pop, and the reframing of `# Error` from reserved label to convention (§17). **Honest compatibility note:** two changes are breaking relative to v0.3.3 — a deep anonymous heading no longer opens a `""`-keyed object (it pops), and a second root heading or mid-document mode marker is now a parse error instead of implementation-defined behavior. Both breaks close silent-data-loss classes; both were already the behavior of the JavaScript reference implementation.

v0.3.4 (unreleased working state) replaced the withdrawn `---` item separator with the **level-pop**: an anonymous heading at depth *D* returns to the scope at depth *D*. The change was made in §8.6 but not propagated through the rest of the document; v0.3.5 completes it.

Previous refinements:
- v0.3.3: formalized three parser-tolerance rules drawn from observed LLM behavior — array promotion for repeated headings without `[]` (§7.4), tolerance of stray `---` markers around the frontmatter block (§3.5.1), and tolerance of YAML-style block-scalar syntax (`key: |`, `key: >`) as an alternative to the canonical blockquote form (§5.2) — each paired with a generator-strict canonical form, plus three structured error conditions for §7.4 (sigil conflict, repeated explicit array, repeated scalar key). Documents valid under v0.3.2 remain valid under v0.3.3.

- v0.3.2: de-normativized QBE filter syntax (§13) and schema type vocabulary (§14), moving both to a non-normative Appendix A.
- v0.3.1: inline Markdown rule (§5.1), frontmatter preservation and application-layer policies (§3.5, §23.7).

What exists today:

- Full format specification ([jmd-spec-v0_3.md](jmd-spec-v0_3.md) — currently v0.3.5)
- Benchmark methodology and raw results ([BENCHMARKS.md](BENCHMARKS.md), [benchmark_results/](benchmark_results/))
- Python reference implementation with C-accelerated parser and serializer ([jmd-impl](https://github.com/ostermeyer/jmd-impl), v0.4.4)
- JavaScript reference implementation, pure ESM, zero dependencies ([jmd-js](https://github.com/ostermeyer/jmd-js), v0.1.2)
- Design rationale ([ai-whispering.md](ai-whispering.md))
- Performance analysis ([jmd-efficiency-analysis.md](jmd-efficiency-analysis.md))
- Research preprint (forthcoming on arXiv)

---

## Near Term

**Current push (recorded 2026-07-04).**
The token-efficient-format field is consolidating rapidly: TOON; JTON
and ONTO (arXiv, April 2026); LAPIS (February 2026); and the first
independent benchmark study of the category, "Notation Matters"
(arXiv 2605.29676, May 2026). JMD's window to contribute direction is
now. Sequenced response:

1. **July 2026** — v0.3.5 consolidation release; revised IANA template
   and reviewer follow-up; `draft-ostermeyer-jmd-00` submitted to the
   IETF Datatracker; announcement on relevant IETF lists (dispatch@).
2. **July–August** — reference-implementation conformance fixes, then
   **benchmark wave 2**: re-implemented and re-measured from scratch
   against v0.3.5, with TOON, JTON, ONTO, and YAML baselines and with
   streaming and generatability as first-class measured dimensions —
   the dimensions where JMD differentiates and which no existing study
   measures.
3. **~Mid-August** — arXiv preprint on wave-2 results.
4. **August–October** — DISPATCH session request for IETF 127
   (San Francisco, November 2026; scheduling opens 2026-08-17),
   presented with wave-2 numbers.

Honest constraint driving this order: superiority claims are made
*after* wave 2, not before — the field's other entrants publish
100%-validity claims of their own, and the only durable contribution
is the measurement that holds up.

**Broader model coverage**
The current benchmark covers six models from four providers. Priority is extending coverage to open-weight models — Llama, Qwen, Mistral, Phi, Gemma — run locally via Ollama and similar, to establish whether the behavioral alignment properties hold independent of provider-specific training choices.

**Implementations in additional languages**
JavaScript is available as of v0.1.2 ([jmd-js](https://github.com/ostermeyer/jmd-js)). Go and Rust remain open. See [CONTRIBUTING.md](CONTRIBUTING.md) for details on what a useful implementation looks like.

**Framework adapters**
Adapters for LangChain, LlamaIndex, and Pydantic AI that make JMD available as a structured output format without requiring manual prompt engineering.

---

## Medium Term

**Calibration benchmark for epistemic frontmatter**
The current benchmark measures adoption rates and downstream effects of epistemic fields. It does not measure calibration — whether the confidence and uncertainty signals models produce are accurate. A calibration benchmark is the logical next step for the RQ3 findings.

**Specification v0.4**
A further minor revision driven by adoption feedback beyond the refinements in v0.3.x. Candidate topics: a streaming-parser specification (event vocabulary, conformance for stream-based backends — note that multi-document streams are off the table since the one-document rule, spec §18.0: one framing unit, one document), a **dedicated error root marker** promoting Error to a first-class document mode (decision recorded 2026-07-03; working candidate `#~`, e.g. `#~ ValidationError`; final character choice after the marker-generation benchmark in the next benchmark wave — candidates `#~`, `#*`), calibration conventions for epistemic frontmatter, additional directive/descriptive frontmatter keys that emerge from production MCP servers, refinements to the JMD-over-XML companion specification, and a potential companion specification for rich-text content (`jmd-richtext`). The error marker is additive; `# Error` remains recognized as a convention during a deprecation window. v0.4 will otherwise remain a strict superset of v0.3.x.

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
The core syntax is stable. Any future version will be a strict superset of v0.3.5. (The v0.3.5 consolidation itself contains two narrow, documented breaks relative to v0.3.3 — see Current Status — both closing silent-data-loss classes.)

**A centralized registry or package index**
JMD is a specification, not a managed ecosystem. Implementations live in their own repositories.

**Governance structures before there is a community**
Process follows people, not the other way around.
