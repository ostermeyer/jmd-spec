# JMD – JSON Markdown
## Format Specification v0.3.4

Copyright (c) 2026 Andreas Ostermeyer <andreas@ostermeyer.de>.
Licensed under CC BY 4.0 — see [LICENSE](LICENSE) for details.
Code samples in this document are licensed under Apache 2.0 — see [LICENSE-CODE](LICENSE-CODE).

---

## 1. Overview

JMD (JSON Markdown) is a lossless data serialization format for the era of LLM-driven infrastructure, designed for workflows where structured data moves between servers and language models.

LLM compute cost scales directly with token count — for both consumed input and generated output. JMD reduces tokens at both ends. As **input**, a JMD document contains 19–29% fewer tokens than its pretty-printed JSON equivalent (the real-world API default); once the data is in context, the reasoning cost is identical regardless of format. As **output**, JMD is the only format that is both token-efficient and reliably generatable — LLMs cannot produce minified JSON consistently, reproducing pretty-printed patterns regardless of instruction. Quantitative benchmark results are provided in the companion document *JMD Efficiency Analysis*.

**The design philosophy** behind JMD is to work with the natural behavior of language models, not against it. LLMs are autoregressive text generators trained on vast corpora of Markdown, code, and structured documents. They have deeply internalized patterns like headings for hierarchy, `key: value` for fields, `- ` for list items, and blank lines for section boundaries. JMD does not invent new syntax for these structures — it formalizes the patterns that LLMs already produce when generating structured output. Every syntax decision in this specification passes a single test: *Would an LLM produce this naturally, without special instruction?* Where the answer is no, the design is reconsidered. This methodology is called *AI Whispering* throughout this specification.

JMD uses a subset of Markdown syntax — headings, blockquotes, and line breaks — to encode JSON's full type system. The choice of Markdown is not motivated by human readability but by the fact that LLMs are trained on vast amounts of Markdown and can generate it reliably and efficiently.

**Core syntax principle:** Heading depth defines data hierarchy. A heading at depth N establishes scope for all following content until the next heading at depth N or shallower, or until a blank line resets scope to root. This directly mirrors the Markdown section model that LLMs have deeply internalized, where a `##` heading governs everything that follows until the next `##` or `#`, and blank lines separate top-level sections.

### 1.1 Purpose

JMD is a text-based, structured data format.

Any useful data format must support the four canonical operations on data:

| Operation | JMD document mode | Root marker |
|---|---|---|
| **Create / Update** (write) | Data | `#` |
| **Read** | Data (as response to a read request) | `#` |
| **Query** (read with filter) | Query by Example | `#?` |
| **Delete** | Delete | `#-` |

A schema document (`#!`) is not an operation — it is a contract describing the shape of data exchanged by the operations above.

JMD is transport-agnostic: the operation is carried by the document's root marker, not by any surrounding protocol.

**One document, one mode.** A JMD document has exactly one root marker, and therefore exactly one mode. Mixing modes within a single document is not permitted. Each mode corresponds to a distinct operation; a document with a single, unambiguous intention is easier to route, validate, and audit than a multi-operation bundle. Sequences of operations are composed by producing multiple documents, not by combining modes.

**Lossless** means:

- Every valid JMD data document maps to exactly one JSON value (unambiguous parsing).
- Every JSON value can be represented in JMD (complete coverage).
- The roundtrip JSON → JMD → JSON preserves the JSON value.

Multiple valid JMD representations may exist for the same JSON value (different key orderings, different number formatting within RFC 8259 constraints). This is by design: LLMs generate text sequentially in the order that is natural for the content, and JMD does not penalize this.

Three properties distinguish JMD from JSON. The first two are co-equal design goals; the third is a structural consequence of the same syntax choice:

**Compute efficiency.** LLM compute cost scales with token count at both ends of the pipeline. As **input**, JMD eliminates quoted keys and structural delimiters entirely — not just whitespace — achieving 19–29% fewer tokens than pretty-printed JSON (the real-world API default). Once parsed, the reasoning cost is identical regardless of format; the gain is at the tokenization boundary. As **output**, JMD is the only efficient format LLMs can reliably generate: they reproduce pretty-printed patterns regardless of instruction, making minification impractical. Quantitative benchmark results are provided in the companion document *JMD Efficiency Analysis*.

**Native streamability.** JMD's line-oriented syntax allows a receiver to process each field as soon as its line is complete — no closing delimiters required. JSON cannot offer this without buffering or non-standard extensions. For large collections and multi-agent pipelines, the streaming advantage is substantial.

Compute efficiency and streamability are not independent — they are two manifestations of the same design choice: hierarchy through heading depth rather than through matched delimiters. The same syntax that eliminates braces and quotes also eliminates the need for closing delimiters. Neither goal is subordinate to the other; both guide every syntax decision in this specification.

**Full CRUD surface in one syntax.** JMD covers create, read, update, query, and delete — the complete set of operations on structured data — with a single unified syntax. An LLM that understands one mode understands all four; the root marker is the only difference. JSON requires separate tooling ecosystems for each of these concerns.

**Sustainability implications.** The compute efficiency described above has consequences beyond cost savings. LLM inference is GPU-bound, and GPU clusters are among the most energy-intensive computing systems ever deployed. Structured data output — the domain where JMD replaces JSON — accounts for a significant share of LLM inference volume (tool calls, API responses, agent-to-agent communication, retrieval pipelines). Reducing per-request GPU time through structural simplification translates directly to reduced energy consumption and, at infrastructure scale, reduced hardware provisioning. Every GPU that does not need to be provisioned is a data centre that does not need to be built. Quantitative projections are provided in the companion document *JMD Efficiency Analysis*.

Together, these properties make JMD a natural fit for the infrastructure that is emerging around LLM agents: MCP servers, tool-calling pipelines, Server-Sent Events, and chained agentic workflows where one tool's output becomes the next tool's input.

**Not limited to LLM contexts.** JMD is a general-purpose structured data format. Anywhere JSON serves today — configuration files, service-to-service APIs, log payloads, document storage, data interchange between non-LLM systems — JMD is an equally valid choice. It carries no LLM-specific assumptions in its grammar; the line-oriented streaming and token-efficient encoding are structural benefits that happen to matter intensely in LLM pipelines but cost nothing when the data flows between ordinary services. A codebase may adopt JMD incrementally: speak JMD natively in new interfaces, translate at boundaries to legacy JSON consumers, or continue with JSON where no benefit justifies the change.

**REST integration.** JMD can serve as a drop-in alternative to JSON in REST APIs via content negotiation (`application/jmd`). Because every completed JMD line is independently parseable, a standard HTTP chunked transfer response is inherently streaming — no protocol changes, wrapper formats, or separate streaming endpoints required. Media type definitions, HTTP method mappings, content negotiation patterns, and related conventions are proposed in the companion document *JMD over HTTP — REST Integration Proposal*, as recommendations for implementers rather than normative requirements.

**Design goals:**

- LLM-native: optimized for compute efficiency and natural LLM generation behavior
- Lossless roundtrip: JSON → JMD → JSON preserves the value
- No constraints that conflict with sequential LLM text generation
- Compute-efficient compared to JSON: fewer tokens, less server processing time per request (no redundant `{}`, `""` on keys, `:` pairs)
- Streamable by design: each completed line advances the parse state (co-equal with compute efficiency)
- Unambiguous grammar; parseable line by line with minimal state (heading depth stack)
- No indentation-based hierarchy: nesting expressed entirely through heading depth (indentation used only for list item continuation within arrays)
- Generator-strict, parser-tolerant: serializers produce canonical syntax; parsers accept natural LLM variations (see Section 20)
- Self-describing via schema documents and query templates

---

## 2. Type Mapping

JMD encodes all six JSON types:

| JSON Type | JMD Representation |
|-----------|-------------------|
| `string`  | Unquoted bare value, or `"quoted"` when ambiguous |
| `number`  | Bare numeric literal (`42`, `3.14`, `-7`, `1e10`) |
| `boolean` | Bare `true` or `false` |
| `null`    | Bare `null` |
| `object`  | Heading scope with key-value fields |
| `array`   | `[]`-suffixed key with list items |

### 2.1 Scalar Disambiguation

Bare values are parsed by attempting JSON literal parsing in this order: `null`, `true`, `false`, number, string.

A value **must** be quoted if it is a string that would otherwise parse as another type:

```
count: 42              → number 42
label: 42              → number 42   ← WRONG if string intended
label: "42"            → string "42" ← CORRECT
active: true           → boolean true
state: "true"          → string "true"
data: null             → null
note: "null"           → string "null"
```

Strings that are unambiguously strings need not be quoted:

```
city: Berlin           → string "Berlin"
status: pending        → string "pending"
```

---

## 3. Document Structure

### 3.1 Heading-Scope Model

JMD's hierarchy is expressed entirely through Markdown heading depth. A heading at depth N opens a scope: all following content belongs to that scope until the next heading at depth N or shallower.

- `#` — root scope (depth 1)
- `##` — first-level keys (depth 2)
- `###` — second-level keys (depth 3)
- `####` and deeper — further nesting levels

Within a scope, **bare fields** (`key: value` lines without heading prefix) belong to the current innermost object scope. This eliminates the need for heading prefixes on every field and mirrors how content naturally follows a heading in Markdown documents.

**Blank lines reset scope to root.** A blank line (empty line or line containing only whitespace) closes all open scopes and returns the parser to the root object scope (`#`). Any bare fields after a blank line belong to the root object. This mirrors the Markdown convention where blank lines separate top-level sections, and formalizes a behavior that LLMs naturally exhibit when generating structured documents (see Section 7.2a for full rationale).

### 3.2 Root Object

A document representing a JSON object begins with a single `#` heading. The heading text is the semantic label (ignored during JSON serialization; used for readability and LLM context).

```markdown
# Order
id: 42
status: pending
```

Serializes to:

```json
{"id": 42, "status": "pending"}
```

Bare fields immediately after `#` belong to the root object. No `##` prefix is needed for simple scalar fields at root level — though `##` may be used to explicitly mark top-level fields. After a deeper heading has opened a nested scope, there are two ways to return to root scope: a `##` scalar heading (see Section 7.2) or a blank line (see Section 7.2a).

### 3.2a Anonymous Headings (Empty Labels)

A heading with no label text — e.g., a line containing only `#` followed by a space — is a valid **anonymous heading**. It opens a scope with an empty string as the label. At root level, an anonymous heading is equivalent to any labeled root heading: it opens the root object scope. At deeper levels, an anonymous heading like `##` followed by a space opens an anonymous nested object (keyed by `""`).

```markdown
#
id: 42
status: pending
```

Serializes to:

```json
{"id": 42, "status": "pending"}
```

**Rationale:** LLMs sometimes produce headings without labels — particularly at root level, where the label is semantically irrelevant. A parser that rejects bare headings would fail on syntactically reasonable LLM output. Since labels carry no serialization semantics at root level, accepting an empty label imposes no ambiguity. A conforming parser MUST accept anonymous headings. A conforming generator SHOULD produce labeled headings for readability, but MAY produce anonymous headings when no meaningful label exists.

### 3.2.1 Label Namespacing

The root label carries no serialization semantics and is therefore not a source of technical collision. However, in large MCP ecosystems where multiple servers expose JMD documents, a reverse-domain naming convention is recommended to avoid ambiguity for human readers and tooling:

```markdown
# com.example.shop.Order
# io.github.user.Invoice
# api.service.v2.Customer
```

A label may contain dots, hyphens, and slashes. It is treated as opaque text by the parser. Tooling may use the label for display, routing hints, or schema lookup — but this is outside the JMD core specification.

Short unqualified labels (`# Order`, `# User`) remain valid and are appropriate within a single well-defined server context.

### 3.3 Root Array

A document representing a JSON array at root level uses the special heading `# []`:

```markdown
# []
- name: Alice
  age: 30
- name: Bob
  age: 25
```

Serializes to:

```json
[{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
```

### 3.4 Empty Root Structures

An empty root object or array is a root heading followed by no fields or items:

```markdown
# Empty
```

Serializes to `{}`.

```markdown
# []
```

Serializes to `[]`.

### 3.5 Document Frontmatter

Fields that appear *before* the first heading in a JMD document are **frontmatter** — document-level metadata that applies to the entire document, not to any specific data scope.

Frontmatter fields are syntactically identical to bare fields — no new syntax is required. The parser treats any `key: value` lines before the first `#` heading as document metadata. A blank line between frontmatter and the root heading is optional but recommended for readability.

Frontmatter fields are **not serialized** into the JSON output. They are transport-level metadata passed through to the implementation, analogous to HTTP headers.

**JMD does not define a fixed set of frontmatter keys.** The parser collects all frontmatter fields into a key-value map and makes them available to the implementation; the implementation decides which keys it recognizes and how it interprets their values. This makes frontmatter a fully open extension point — different implementations may use entirely different frontmatter vocabularies for their specific needs.

**Example: pagination.** A query server might use `page` and `page-size` to control result delivery:

```markdown
page: 2
page-size: 50

#? Orders
status: active
```

**Example: epistemic metadata.** An LLM generator can communicate its self-assessment of the data it produces — its confidence, the provenance of the data, and which specific fields it considers uncertain:

```markdown
confidence: high
source: customer database
uncertain: phone, email

# Customer
id: 42
name: Müller
city: Berlin
phone: 030-12345
email: mueller@example.de
```

Common epistemic conventions (not mandated by JMD):

| Field | Meaning |
| --- | --- |
| `confidence` | Self-assessed reliability: `high`, `medium`, `low`, or `speculative` |
| `source` | Data provenance — free-form string (e.g., `database`, `vector search`, `clinical guidelines 2024`) |
| `uncertain` | Comma-separated list of field names the generator considers less reliable than the overall confidence level |

These conventions reflect the fact that LLMs operate with personas and have a subjective perspective on the data they produce — formalizing this perspective rather than suppressing it makes the metadata more honest and more useful. But they are examples of how the frontmatter channel can be used, not part of the JMD format itself.

**Frontmatter in responses.** The frontmatter channel is not exclusive to requests. A server returning a paginated result set SHOULD place pagination metadata (`total`, `page`, `pages`, `page-size`) in the response frontmatter rather than the document body. This keeps metadata structurally distinct from data — body fields like `total: 84.99` on an order line item are not confused with `total: 4832` describing the result set size. More importantly, a response document travels through a pipeline: its frontmatter is immediately available to the next agent in the chain as document-level metadata, without requiring that agent to understand the document's data schema.

A conforming parser MUST collect all frontmatter fields into a key-value map and make them available to the implementation. A conforming parser MUST NOT reject unknown frontmatter keys, and MUST NOT silently drop them before the application layer can inspect them.

**Two roles, one channel.** Frontmatter keys serve two functionally distinct roles, and the distinction matters for how unknown keys should be handled:

- **Descriptive keys** (metadata such as `source`, `confidence`, `author`, `schema-version`) extend the semantics of the document for downstream observers. They describe the document without changing how it is processed. For descriptive keys, silent tolerance of unknown names is *desirable*: forward-compatibility requires that older receivers do not break when newer documents add fields they have not seen.
- **Directive keys** (operational modifiers such as `page-size`, `select`, `sort`, `confirm`) control *how* the receiver processes the document. A dropped directive causes the receiver to perform an operation the sender did not intend — for example, a `dry-run: true` directive sent to a destructive operation and silently discarded is a genuine safety hazard, not an interoperability feature.

The JMD parser MUST NOT distinguish these two roles at parse time — both kinds of key are preserved in the frontmatter map with their raw values. The distinction is made at the **application layer**, which inspects the preserved keys and decides how to handle unknown ones. Three levels of strictness are available, and the choice is per-operation:

| Level | Application behavior | Typical use |
| --- | --- | --- |
| Silent tolerance | Unknown key is ignored without signalling | Uncritical reads, maximal forward-compatibility |
| Observable tolerance | Unknown key is ignored but echoed in the response frontmatter (see Section 23.7) | Default for most operations; the sender can detect a silent drop |
| Strict refusal | Unknown key causes the application to reject the operation with a structured error (Section 17) | Destructive operations (delete, drop), safety-critical modifiers |

Strict refusal at the application layer is **not** a parser conformance violation. The parser accepted the key; the application chose not to act on it. This separation is exactly what the layered conformance model is for: the parser guarantees syntactic interoperability, the application enforces semantic safety where it matters.

A conforming generator SHOULD omit frontmatter entirely when no metadata is needed. The absence of frontmatter is the common case for data documents.

### 3.5.1 Frontmatter Marker Tolerance

LLMs trained on YAML-prefixed Markdown ecosystems (Jekyll, Hugo, Astro, Obsidian) frequently emit a `---` marker before and after a frontmatter block by reflex. JMD requires no such markers — frontmatter is delimited by document position (everything before the first heading is frontmatter; the first heading ends it).

A conforming parser MUST accept stray `---` lines around the frontmatter block as decorative noise and consume them without semantic effect:

- A line containing **three or more hyphens** (`---`, `----`, `-----`, …) **before** any frontmatter field, including as the **first** line of the document.
- A line containing **three or more hyphens** **between** the last frontmatter field and the root heading.

Both forms below parse identically:

```markdown
---
confidence: high
source: ledger
---

# Order
id: 42
```

```markdown
confidence: high
source: ledger

# Order
id: 42
```

A conforming generator MUST NOT emit such markers. The canonical form omits them. This rule exists solely to accommodate the established LLM reflex without rejecting documents that would otherwise be syntactically correct.

**Interaction with §8.6 (Level-Pop).** §8.6 structures arrays with anonymous-heading level-pops, not `---`. A `---` is pure decoration both at document scope before the first heading (this tolerance) and within an array body (§8.6). The two do not conflict.

### 3.6 Canonical Parse Result

A conforming JMD parser returns every parsed document as a uniform **envelope** with four fields:

| Field | Type | Description |
|---|---|---|
| `mode` | string | `"data"`, `"schema"`, `"query"`, or `"delete"` — determined by the root marker |
| `label` | string | Root heading label, with mode-mark and `[]` sigil stripped |
| `frontmatter` | object | Map of frontmatter fields; the empty object `{}` when no frontmatter is present |
| `value` | object \| array | Parsed document body |

The envelope is the single entry point of the parser API. Applications that need only the body inspect `value`; applications that need document-level metadata inspect `mode`, `label`, and `frontmatter`. No information about the document is conveyed through side channels.

#### 3.6.1 Field Semantics

**`mode`** is derived from the root heading prefix and uses these exact lowercase string literals:

| Root marker | `mode` |
|---|---|
| `#` (no mark) | `"data"` |
| `#!` | `"schema"` |
| `#?` | `"query"` |
| `#-` | `"delete"` |

**`label`** is the root heading's bare label text, after the following normalizations:

- The mode-mark character (`!`, `?`, `-`) is stripped — it is already carried in `mode`.
- A trailing `[]` sigil is stripped — the array nature of the body is carried by `value` being a list.
- The empty string `""` is a valid label. Anonymous root headings (`#`, `# []`, `#- []`) all produce `label: ""`.

**`frontmatter`** is the map of frontmatter fields preserved verbatim (Section 3.5). Scalar values are parsed per Section 5; bare-key frontmatter (a line containing only a key with no `:`) is encoded as the boolean `true`. When the document has no frontmatter, `frontmatter` is the empty object `{}` — never `null`, never absent.

**`value`** is the parsed document body. Its runtime type is determined by the root-array sigil:

- Root without `[]` → `value` is an object (possibly empty `{}`)
- Root with `[]` → `value` is an array (possibly empty `[]`)

`value` is never `null` or absent for a validly parsed document.

#### 3.6.2 Prose in Body is a Parse Error

A document body containing prose — a bare line that is neither a key-value field, an indented continuation, a bullet (`-`), a blockquote (`>`), a heading, nor a thematic break (`---`) — MUST be rejected with a parse error.

```markdown
# Answer

42
```

This is valid Markdown (a heading followed by a paragraph) but not valid JMD: the line `42` is prose, not a JMD structural element. A parser MUST NOT silently drop prose or return an empty `value`. The correct response is a structured parse error identifying the offending line.

**Rationale.** JMD formalizes Markdown structures for data. Bare prose under a heading is a content construct of Markdown that has no meaning in the JMD data grammar. Accepting such input silently would hide a mode error — the caller wrote Markdown text where JMD data was expected — and would cause data loss downstream. Rejecting it explicitly makes the layer boundary visible: *this input is Markdown, not JMD; use a different path to transmit prose.*

#### 3.6.3 Round-Trip Contract

For any valid JMD document, the envelope round-trips losslessly:

```
parse(serialize(envelope)) ≡ envelope   (byte-identical for canonical input)
serialize(parse(source))   ≡ source     (up to canonical normalization)
```

The serializer accepts an envelope directly as its input. Implementations MAY additionally offer convenience signatures that take `(value, mode, label, frontmatter)` as separate parameters; the envelope form is the canonical shape.

---

## 4. Keys

### 4.1 Simple Keys

Keys are bare identifiers in a `key: value` line:

```
name: Alice
```

Within a heading scope, the heading itself carries the key for an object or array:

```
## address
street: Hauptstraße 1
city: Berlin
```

### 4.2 Keys with Special Characters

Keys containing spaces, colons, or other characters outside `[a-zA-Z0-9_-]` are quoted. Quoted keys are JSON strings and follow JSON string escaping rules (RFC 8259):

```
"content-type": application/json
"full name": Alice Example
"x:custom": value
"line\nbreak": value
```

### 4.3 Key Depth

Key depth is determined by heading level:

- Bare `key: value` after `#` → depth 1 (root object fields)
- `## key` → depth 1 (explicit root-level scope)
- `### key` → depth 2 (within a `##` scope)
- `#### key` → depth 3 (within a `###` scope)

There is no artificial limit on heading depth. Deeper headings express deeper nesting.

---

## 5. Scalar Values

A scalar field is a key-value pair on a single line:

```markdown
id: 42
ratio: 3.14
enabled: true
token: null
name: Alice
code: "404"
```

Scalar fields may also appear as **scalar headings** that explicitly mark their depth level:

```markdown
## total: 84.99
```

A scalar heading is syntactically a heading with a `key: value` payload. It carries no child scope. Scalar headings are used to return to a specific depth after a deeper scope (see Section 7.2).

Quoted string values are JSON strings and follow JSON string escaping rules (RFC 8259). The escape sequences `\"`, `\\`, `\/`, `\b`, `\f`, `\n`, `\r`, `\t`, and `\uXXXX` are interpreted per JSON, not per Markdown. A JMD parser **must not** apply Markdown rendering to string content.

### 5.1 Inline Markdown in Scalar Values

JMD uses Markdown *structure* — headings, lists, blockquotes, thematic breaks — as data syntax. Markdown *formatting* — bold (`**...**`), italic (`*...*`, `_..._`), inline code (`` `...` ``), links (`[text](url)`), strikethrough (`~~...~~`) — is **not** JMD syntax. It is content, and it belongs in a different place.

**Generator rule (SHOULD).** A conforming JMD generator SHOULD NOT emit inline Markdown formatting inside scalar values, whether bare or quoted. For strings that require rich-text formatting, use the blockquote multiline form (Section 9.1), which is JMD's designated channel for formatted prose. Scalar values should be plain data.

**Parser rule (MUST).** A conforming JMD parser MUST treat all string content as literal — bare values, quoted strings, and blockquote multiline values alike. The parser does not interpret, render, strip, or validate Markdown formatting tokens. A string value containing `**`, `*`, `` ` ``, `[`, or `~` is a valid JSON string and roundtrips unchanged. This preserves the lossless bijection with JSON: every JSON string, including strings that happen to contain Markdown-like characters, can be represented in JMD.

**Rationale.** The two rules together implement generator-strict, parser-tolerant (Section 22.1) for the specific case of Markdown content vs. JMD structure. The asymmetry matters because JMD is built on Markdown primitives: an LLM trained on Markdown holds both "data structure" and "prose formatting" patterns in the same latent space, and the boundary between them is not sharp by default. Permitting inline Markdown in scalar values blurs that boundary — and once it is blurred, the generator drifts from JMD-mode into ordinary-Markdown-mode and begins producing constructs that JMD does not support: `*` bullets instead of `-`, numbered lists (`1.`, `2.`), setext headings (underline with `===` or `---`), indented code blocks, and other native Markdown forms. Each of these is a genuine JMD parse error, and each originates from mode confusion rather than from syntactic error.

Restricting inline formatting to the blockquote channel keeps the generator's mental model sharp: *scalar fields are plain data; rich text goes in `>` blocks.* This is also the rule encoded in JMD's minimum-viable primer (five bullets, ~80 tokens), which has been validated at 99.7% syntax validity in cross-model benchmarks. This specification formalizes what the empirically successful primer already tells the generator.

**What this does not forbid.** A value that *contains* a character which happens to be a Markdown metacharacter — `rate: 2 * x`, `expr: **ptr`, `regex: ^[a-z]+$`, `url: https://example.com/*` — is not Markdown formatting; it is incidental character content. Such values are valid scalar data and MUST be accepted by the parser. The generator rule concerns *intentional formatting markup*, not *characters that visually resemble formatting markup*. When in doubt, the parser's literal-content rule applies.

### 5.2 Multi-Line Block-Scalar Syntax Tolerance

The canonical form for multi-line string values is the blockquote form (§9.1):

```markdown
key:
> line one
> line two
```

LLMs trained on YAML — where multi-line string syntax uses the block-scalar forms `key: |` (literal) and `key: >` (folded) — frequently emit these forms by reflex. A conforming parser MUST accept them as parser-tolerant alternatives.

Note on terminology: the block-scalar syntax spans multiple input lines, but the resulting scalar value is multi-line only for the literal form. The folded form produces a single-line string value (with words joined by spaces). "Multi-line" describes the input syntax, not the resulting value.

**Literal form (`|`):**

```markdown
key: |
  line one
  line two
```

parses to the multi-line string `"line one\nline two"`. Newlines between indented lines are preserved.

**Folded form (`>`):**

```markdown
key: >
  line one
  line two
```

parses to the single-line string `"line one line two"`. Newlines between non-empty indented lines are folded to a single space; a blank line within the block preserves a newline.

**Parser rules:**

- The line containing `key: |` or `key: >` opens the block. Following lines indented by two or more spaces belong to the value.
- The first non-indented line terminates the block.
- Indentation is normalized: the leading whitespace of the first indented line is stripped from each line in the block.
- A trailing blank line at the end of the block is dropped.

**Generator rule (SHOULD).** A conforming generator SHOULD emit multi-line string values using the blockquote form, not the block-scalar forms. The block scalars are parser-tolerance only; a round-trip canonicalizes a `|`-input to its blockquote equivalent.

**Rationale.** The blockquote form is JMD-native. The block-scalar forms exist in this specification because LLM generators emit them naturally — rejecting them would produce frequent parse failures on otherwise structurally correct documents. Per §22.1 (Generator-strict, Parser-tolerant), the parser accommodates what generators naturally produce.

**Out of scope.** YAML's chomping indicators (`|+`, `|-`, `>+`, `>-`), the explicit indentation indicator (e.g. `|2`), and folded-mode's many edge cases (more-indented lines preserving their newlines, multi-paragraph folding behavior) are not part of this tolerance. The two unmarked forms cover the LLM reflex; chomping and explicit indentation are YAML-specific features without observed LLM-reflex pressure.

---

## 6. String Escaping Rules

A bare string value must be quoted whenever it could be misinterpreted by a parser. Section 2.1 covers type ambiguity (e.g. `"42"`, `"true"`). This section covers **structural ambiguity**: cases where the string content could be mistaken for JMD syntax.

### 6.1 Mandatory Quoting Triggers

A string value **must** be quoted if it:

| Condition | Bare (wrong) | Quoted (correct) |
|---|---|---|
| Starts with `# ` (a pound sign followed by a space) | `title: # Heading` | `title: "# Heading"` |
| Starts with `- ` | `note: - item` | `note: "- item"` |
| Is exactly `-` | `sep: -` | `sep: "-"` |
| Parses as another type | `code: 42` | `code: "42"` |

The same rules apply to string values at any scope depth and to array items.

**Note:** Only the two-character sequence `# ` (pound sign followed by a space) triggers mandatory quoting, not a bare `#`. A string like `#hotfix` or `#tag` begins with `#` but is not a valid JMD heading (which requires at least one space after the `#` characters), and therefore does not require quoting. When in doubt, quoting is always safe.

### 6.2 Array Item Quoting

Scalar array items follow the same rules:

```markdown
## lines[]
- normal string
- "# this looks like a header"
- "- this looks like a list item"
- "true"
```

### 6.3 Parser Responsibility

A **parser** encountering an unquoted value that starts with a structural prefix (`# `, `- `) must treat the entire line as a parse error rather than silently misinterpreting it. A **generator** (including an LLM) is responsible for quoting proactively. When in doubt, quoting is always safe and never changes the parsed value.

### 6.4 Key Escaping

Keys containing structural characters are quoted per Section 4.2. No additional escaping is needed for keys.

---

## 7. Nested Objects

A nested object is encoded as a heading whose depth is one level deeper than its parent, followed by bare key-value fields:

```markdown
# Order
id: 42
## address
street: Hauptstraße 1
city: Berlin
zip: "10115"
### geo
lat: 52.52
lng: 13.40
```

Serializes to:

```json
{
  "id": 42,
  "address": {
    "street": "Hauptstraße 1",
    "city": "Berlin",
    "zip": "10115",
    "geo": {"lat": 52.52, "lng": 13.40}
  }
}
```

The heading `## address` opens a depth-2 scope. Bare fields `street`, `city`, `zip` belong to address. The heading `### geo` opens a depth-3 scope within address. Fields `lat`, `lng` belong to geo.

### 7.1 Scope Rules

1. A heading at depth N closes all open scopes at depth N or deeper.
2. Bare fields (`key: value`) belong to the innermost open object scope.
3. A heading at depth N opens a new scope as a child of the scope at depth N-1.
4. A blank line closes **all** open scopes and returns to root scope (`#`).

These rules mean that no explicit "close scope" syntax is needed — scope is implicitly closed by the next heading at the same or shallower depth, or by a blank line. The blank line rule provides a lightweight mechanism for returning to root scope without requiring a heading prefix.

### 7.2 Scope Return via Scalar Heading

After a deep scope, returning to a shallower level for a scalar field requires a heading at the target depth:

```markdown
# Order
id: 42
## address
street: Hauptstraße 1
city: Berlin
### geo
lat: 52.52
lng: 13.40
## total: 84.99
```

Here, `## total: 84.99` is a **scalar heading**: it closes the `### geo` and `## address` scopes and adds `total` as a root-level field. Without the `##` prefix, `total` would be parsed as a field within the `### geo` scope.

**Rule:** Bare fields always belong to the innermost open scope. To place a field at a shallower scope, use a heading at the desired depth.

### 7.2a Scope Return via Blank Line

A blank line resets the parser scope to the root object. Any bare fields following a blank line belong to the root scope, regardless of how deeply nested the preceding content was:

```markdown
# Order
id: 42
## address
street: Hauptstraße 1
city: Berlin
### geo
lat: 52.52
lng: 13.40

total: 84.99
currency: EUR
```

Serializes to:

```json
{
  "id": 42,
  "address": {
    "street": "Hauptstraße 1",
    "city": "Berlin",
    "geo": {"lat": 52.52, "lng": 13.40}
  },
  "total": 84.99,
  "currency": "EUR"
}
```

The blank line after `lng: 13.40` closes both the `### geo` and `## address` scopes. The fields `total` and `currency` are root-level fields — no `##` prefix is needed.

**Blank lines before headings are cosmetic.** When a blank line is followed by a heading, the heading itself determines scope via its depth — the blank line has no additional effect. This means generators may freely insert blank lines before headings for visual separation without altering semantics:

```markdown
# Order
id: 42

## address
street: Hauptstraße 1

## tags[]
- express
```

Here the blank line before `## address` resets to root, and `## address` immediately opens a depth-2 scope — the result is the same as without the blank line. The blank line before `## tags[]` behaves identically.

**Blank lines within array bodies do not reset scope.** Within an array scope (between `## key[]` and the next heading or blank line that is not followed by a `-` item), blank lines between items are cosmetic and do not close the array:

```markdown
## items[]
- sku: A1
  qty: 2

- sku: B3
  qty: 1
```

Here the blank line between the two items is cosmetic — both items belong to `items[]`. The parser treats a blank line followed by `-` as a visual separator within the array, not as a scope reset. A blank line followed by a bare field (not `-`) or EOF does reset scope.

#### Rationale: Why blank lines are semantically significant

This rule was not introduced to impose a new constraint on LLM generators. It formalizes a behavior that LLMs already exhibit naturally.

**LLMs have an internalized model of document structure.** When a language model generates a JMD document, it does not place blank lines randomly. It has a deep, training-derived sense of when a structural unit is complete and a new one begins. This sense is inherited from the vast Markdown corpus in pretraining data, where blank lines consistently separate semantic sections. When an LLM finishes generating an `## address` block and moves on to a different top-level concern, it produces a blank line — not because it was instructed to, but because that is the structural pattern it has internalized.

**JMD aligns the format with the generator's natural behavior.** The core design philosophy of JMD is not to educate the LLM about a new format, but to design a format that captures what the LLM already does. Heading-based scoping works because LLMs naturally produce Markdown headings. Bare fields work because LLMs naturally write key-value lines after headings. And blank-line scope reset works because LLMs naturally separate structural blocks with blank lines.

**The alternative — ignoring blank lines — creates a latent error class.** If blank lines were purely cosmetic, a generator that produces:

```markdown
## address
street: Hauptstraße 1
city: Berlin

name: Customer
```

would silently assign `name` to `address` rather than to the root object. The generator "meant" to return to root scope (hence the blank line), but the format ignores this intent. Making blank lines semantic turns this silent data corruption into correct behavior: the blank line closes `address`, and `name` is correctly a root-level field.

**The error direction is safe.** An accidental blank line within a nested block would promote a field to root scope. This produces an unexpected root-level field — which is detectable and diagnosable. The alternative (a missing blank line) keeps the field in the nested scope, which matches the "no blank line means same scope" rule. Both error directions are preferable to silent misattribution.

### 7.3 Empty Nested Objects

A heading with no value and no subsequent bare fields or deeper headings serializes to an empty object. The parser recognizes this when the next line is a heading at the same or shallower depth, or is EOF:

```markdown
# Order
## metadata
## id: 42
```

Serializes to:

```json
{"metadata": {}, "id": 42}
```

### 7.4 Repeated Headings as Implicit Arrays

LLMs trained on Markdown have a strong reflex to express a sequence of similar structured items as a sequence of headings at the same depth, without an enclosing `[]` array marker:

```markdown
# Canvas
## Op
type: rect
## Op
type: text
## Op
type: path
```

A naive tree-building parser would map this to `{"Canvas": {"Op": {...}}}` with last-write-wins object-key semantics — silently discarding the first two `Op` blocks. This is the most common silent data-loss class in early JMD implementations.

JMD specifies the behavior as **array promotion**: a parser treats the second and later occurrences of a same-label heading at the same depth in the same parent scope as items of an implicit array, promoting the first occurrence retroactively. The example above maps to:

```json
{
  "Canvas": {
    "Op": [
      {"type": "rect"},
      {"type": "text"},
      {"type": "path"}
    ]
  }
}
```

This rule is symmetric to §8.6b (Depth+1 Items as Natural LLM Pattern): both rules recognize an LLM-natural variant of an array construction and map it parser-tolerantly to the canonical array representation.

#### 7.4.1 Parser Behavior

A conforming parser MUST apply array promotion when all three conditions hold:

1. **Same parent scope.** The repeated heading occurs within the same enclosing object scope as the first occurrence.
2. **Same depth.** The repeated heading is at the same depth level.
3. **Same label, no `[]` sigil.** Both occurrences use the same label text with no trailing `[]`.

When all three conditions are met, the parser promotes the existing object value at that key to a single-element array containing the first object, then appends the second object. Subsequent same-key occurrences are appended.

The promotion is decided at the moment the parser encounters the second occurrence — no lookahead is required. A streaming parser emits `object_start` / `object_end` event pairs for each occurrence and need not buffer; a tree-building parser performs the promotion as a constant-cost edit when the second occurrence is seen.

#### 7.4.2 Error Conditions

Three constellations involving repeated keys MUST be rejected with a structured parse error:

**a) Sigil conflict.** A key appears once without `[]` and once with `[]` (in either order):

```markdown
## Op
type: rect
## Op[]
- type: text
```

The author's intent is ambiguous — promote-to-array vs. explicit-array. The parser MUST emit a structured error identifying both occurrences.

**b) Repeated explicit array.** A key appears twice with the `[]` sigil at the same depth in the same parent:

```markdown
## Op[]
- type: rect
## Op[]
- type: text
```

This is a redeclaration. The parser MUST emit a structured error. (Both items in one array would be written as items of a single `## Op[]` block.)

**c) Repeated scalar key.** A scalar field key — whether emitted as a bare field (`x: 10`) or as a scalar heading (`## x: 10`, §7.2) — appears twice in the same object scope, in any combination:

```markdown
## point
x: 10
## x: 20
```

The parser MUST emit a structured error. Scalar fields are plain key-value pairs without array-promotion semantics; silent overwrite is exactly the data-loss this section is designed to prevent. The rule applies symmetrically across the two scalar-field forms — they are equivalent at the data level, so repetition across the forms is treated the same as repetition within one form.

#### 7.4.3 Generator Behavior

A conforming generator MUST emit arrays canonically — with the `[]` sigil and item form (§8.3 or §8.6b):

```markdown
## Op[]
- type: rect
- type: text
- type: path
```

The promoted-array form (repeated headings without `[]`) is parser-tolerance only. A round-trip canonicalizes: input with repeated headings yields output with `[]` array.

#### 7.4.4 Single-Element Arrays

A key that appears exactly once without `[]` is parsed as a single object, not as a single-element array. Authors who require a single-element array MUST use the explicit `[]` form:

```markdown
## Ops[]
- type: rect
```

This avoids the lookahead that "parse as single object now, promote later if a sibling appears" would require, and keeps streaming-parser and tree-building behavior identical. The `[]` sigil is the disambiguator: with sigil → array (zero, one, or many items); without sigil → object (single occurrence) or promoted array (multiple occurrences).

---

## 8. Arrays

### 8.1 Array Key

An array field is denoted by appending `[]` to the key in a heading:

```
## tags[]
```

### 8.2 Array of Scalars

Items are list entries (`-`):

```markdown
## tags[]
- backend
- api
- "404"
```

Serializes to:

```json
{"tags": ["backend", "api", "404"]}
```

### 8.3 Array of Objects

Each item is introduced by `- ` followed by its first field. Additional fields follow on indented continuation lines (2+ spaces):

```markdown
## items[]
- sku: A1
  qty: 2
  price: 29.99
- sku: B3
  qty: 1
  price: 24.99
```

Serializes to:

```json
{
  "items": [
    {"sku": "A1", "qty": 2, "price": 29.99},
    {"sku": "B3", "qty": 1, "price": 24.99}
  ]
}
```

This is standard Markdown list continuation: indented lines belong to the current list item. LLMs produce this pattern naturally and reliably — it is the most deeply internalized Markdown convention for multi-line list items.

**Parse rules:**

- `- key: value` starts a new object item with its first field.
- Indented `key: value` lines (2+ leading spaces) are additional fields of the current item.
- A new `- `, a heading, a scope-resetting blank line, or EOF ends the current item.
- The indentation level is not significant beyond "2+ spaces". The parser does not track or enforce consistent indentation depth — any line starting with 2+ spaces followed by a `key: value` pattern belongs to the current item.

**Bare `-`** on its own line remains valid for items that have no first-line field (e.g., items consisting entirely of nested sub-structures):

```markdown
## items[]
-
### details
sku: A1
qty: 2
```

**Disambiguation:** After `- `, if the content matches a `key: value` pattern (bare or quoted key, followed by `: `, followed by a value), it is parsed as the first field of an object item. Otherwise, it is a scalar item. Scalar strings that look like `key: value` must be quoted: `- "name: Alice"`.

An item's scope extends until the next `-`, a thematic break (`---`), `## -`, a heading at the array's depth or shallower, a scope-resetting blank line, or EOF.

### 8.4 Array of Arrays (Sub-Arrays)

A nested array is introduced by a heading with `[]` at one depth deeper than its parent array:

```markdown
## matrix[]
### []
- 1
- 2
### []
- 3
- 4
```

Serializes to:

```json
{"matrix": [[1, 2], [3, 4]]}
```

`### []` is an **anonymous sub-array heading**: it opens a sub-array within the `## matrix[]` scope. Each `### []` heading starts a new inner array.

### 8.5 Array of Arrays of Objects

```markdown
## schedule[]
### []
- day: Mon
  time: "09:00"
- day: Tue
  time: "10:00"
### []
- day: Wed
  time: "14:00"
```

Serializes to:

```json
{
  "schedule": [
    [{"day": "Mon", "time": "09:00"}, {"day": "Tue", "time": "10:00"}],
    [{"day": "Wed", "time": "14:00"}]
  ]
}
```

### 8.6 Level-Pop (Returning to an Outer Array)

When an array of objects contains items with nested sub-structures (child objects or child arrays), a problem arises: after the nested structure has been written at a deeper heading level, how does the *next* item return to the **outer** array? Going **deeper** is self-describing — a `##`/`###` heading declares its own depth. Coming back **up** needs an equally self-describing signal. JMD uses the **level-pop**.

#### Syntax

A **level-pop** is an **anonymous heading** (§3.2a): a line containing only `#` characters (`#`, `##`, `###`, …) with no label.

#### Semantics

An anonymous heading at depth *D* **pops the scope stack back to depth *D*** and continues there. It is the depth-aware generalization of the blank-line reset (§3.3): a blank line returns to the root; an anonymous `#`×*D* returns to depth *D*.

- A **labelled** heading at depth *D* *opens* a scope at depth *D*.
- An **anonymous** heading at depth *D* *returns to* the scope already established at depth *D*.

So within an array whose heading is at depth *D*, after an item has opened a deeper sub-structure, an anonymous heading `#`×*D* closes that sub-structure (and any deeper ones, in a single step) and returns to the array — the next `- ` line is then a new item of *that* array.

#### Canonical Form

Records of an array stay **bare `-` items** with plain `key: value` fields; their sub-structures are deeper headings. The serializer emits a level-pop `#`×*D* (where *D* is the array's heading depth) **after** any record that opened a sub-structure **and** that is followed by further records. The last record needs no pop — end-of-scope closes it. Flat object arrays and scalar arrays need no level-pop at all.

#### Example

```markdown
# Api[]
- name: clockodo
  auth: headers
## headers[]
- name: X-Api-User
  value: alice
#
- name: ifs
  auth: oauth2
```

Parses to:

```json
[
  {"name": "clockodo", "auth": "headers",
   "headers": [{"name": "X-Api-User", "value": "alice"}]},
  {"name": "ifs", "auth": "oauth2"}
]
```

The `#` after the `## headers[]` sub-array pops back to the depth-1 `# Api[]` array, so `- name: ifs` is a new API record, not another header.

#### Multi-Level Pop

A single anonymous heading closes *arbitrary* nesting in one step — `#`×*D* returns straight to depth *D* no matter how deep the current scope is:

```markdown
# x[]
- name: a
## h[]
- name: h1
### g[]
- gg
##
- name: h2
#
- name: b
```

`##` returns to depth 2 (the `## h[]` array → next item `h2`); `#` returns to depth 1 (the `# x[]` array → next item `b`):

```json
[
  {"name": "a", "h": [{"name": "h1", "g": ["gg"]}, {"name": "h2"}]},
  {"name": "b"}
]
```

#### Flat Arrays Need No Pop

Arrays of flat objects (no record opens a sub-structure) and scalar arrays use bare `-` items and never need a level-pop:

```markdown
## items[]
- sku: A1
  qty: 2
- sku: B3
  qty: 1
```

#### Design Rationale

1. **Self-describing.** Each `#`×*D* declares its own target depth. The parser tracks no state, and a generator cannot "forget to close" the way an indentation- or balanced-delimiter scheme can — the depth is *in the marker*.
2. **One-shot.** One marker pops through any number of nested levels to the named depth.
3. **Consistent with the core principle.** JMD's hierarchy *is* heading depth (§1). The level-pop stays entirely within that model — it is the natural inverse of opening a deeper heading, and a strict generalization of the blank-line reset.
4. **Clean records.** Item and field lines carry no depth bookkeeping (`- name`, `auth:`); only the pop carries a depth.

#### Thematic Break (`---`) — Decoration Only

A line of three or more hyphens (`---`) is a CommonMark horizontal rule. JMD treats it as **pure decoration**: outside an array it is the frontmatter marker tolerated under §3.5.1; **within an array body it has no structural effect and is skipped** by a conforming parser. It is **not** an item separator. (Earlier drafts used `---` as a separator; it was withdrawn because it carries no depth information and is therefore ambiguous in nested object-arrays — the level-pop replaces it.)


### 8.6a Depth-Qualified Array Items (Parser Tolerance)

A conforming parser MUST also accept **depth-qualified item markers** as an alternative to thematic breaks. When an array of objects contains nested arrays, a heading-prefixed `-` at the target depth explicitly starts a new item in the outer array:

```markdown
## groups[]
- name: A
### members[]
- Alice
- Bob
## - name: B
### members[]
- Charlie
```

`## - name: B` closes the `### members[]` scope, starts a new item in the `## groups[]` array, and sets the item's first field. Without the `## ` prefix, bare `-` after `### members[]` would add an item to `members`, not `groups`.

**Rule:** `## -`, `## - key: val`, `### -`, etc. start a new item in the array declared at that heading depth. Bare `-` or `- key: val` starts a new item in the innermost open array.

A conforming generator SHOULD emit thematic breaks as the canonical separator; depth-qualified markers are accepted for backward compatibility and parser tolerance.

### 8.6b Depth+1 Items as Natural LLM Pattern

LLMs trained on Markdown have a strong preference for expressing array items one heading level deeper than the array heading. Given an array declared at depth 1 (`# products[]`), a model naturally writes items at depth 2 (`## -` or `## - name: Widget`), following the Markdown intuition that content under a heading belongs at a deeper level.

This pattern is valid JMD and is functionally equivalent to bare `-` items:

```markdown
The canonical generator form is bare `-` records with the level-pop (§8.6); depth-qualified markers (`## -`, `### -`, …) are accepted as parser tolerance only and are never emitted.
## - name: Widget
  price: 29.99
  sku: A1
## - name: Gadget
  price: 49.99
  sku: B3
```

Serializes identically to:

```markdown
# products[]
- name: Widget
  price: 29.99
  sku: A1
- name: Gadget
  price: 49.99
  sku: B3
```

Both produce:

```json
[
  {"name": "Widget", "price": 29.99, "sku": "A1"},
  {"name": "Gadget", "price": 49.99, "sku": "B3"}
]
```

Depth+1 items are not merely a disambiguation mechanism for nested arrays — they are the most natural way for LLMs to express array items, because the Markdown heading hierarchy implies that items "inside" an array belong at the next heading level. Benchmark testing confirms that LLMs produce depth+1 items consistently, even when bare `-` would be unambiguous.

**A conforming parser MUST accept depth+1 items** (`## -` or `## - key: val` for an array at depth 1) as equivalent to bare items. A conforming generator MAY produce either form; bare `-` is more compact, but depth+1 items are equally valid.

### 8.7 Heterogeneous Arrays

JSON arrays may contain mixed types. JMD supports this by allowing different item forms within the same array body:

```markdown
## mixed[]
- 42
- hello
- true
- null
- name: Alice
### []
- 1
- 2
```

Serializes to:

```json
{"mixed": [42, "hello", true, null, {"name": "Alice"}, [1, 2]]}
```

### 8.8 Empty Arrays

An array key with no items following it serializes to an empty array. The parser recognizes this when the next line is a heading at the same or shallower depth, or EOF:

```markdown
# Order
## tags[]
## id: 42
```

Serializes to:

```json
{"tags": [], "id": 42}
```

---

## 9. Multiline String Values

A field value may span multiple lines when the content exceeds a single line. JMD supports two multiline forms, both native Markdown constructs that LLMs produce reliably without special prompting.

### 9.1 Rich Text (Blockquote Form)

Blockquote multiline values are JMD's **designated channel for rich-text content**. They are the one place in a JMD document where inline Markdown formatting — bold, italic, inline code, links, lists — is expected and appropriate (see Section 5.1 for why scalar values should remain plain data).

For formatted text that may contain inline Markdown (bold, italic, links, lists), use blockquote syntax. The field key appears on its own line with an empty value, followed by one or more `> `-prefixed lines:

```markdown
# Article
title: The Future of AI Communication
published: 2026-03-11
body:
> The emergence of **structured formats** for LLM communication
> marks a turning point in how we think about
> *machine-to-machine* data exchange.
>
> Key findings:
> - Token efficiency improved by 30%
> - Error rates dropped significantly
```

Serializes to:

```json
{
  "title": "The Future of AI Communication",
  "published": "2026-03-11",
  "body": "The emergence of **structured formats** for LLM communication\nmarks a turning point in how we think about\n*machine-to-machine* data exchange.\n\nKey findings:\n- Token efficiency improved by 30%\n- Error rates dropped significantly"
}
```

**Parse rules:**

- The key line MUST have an empty value (nothing after the colon and space, i.e. `key:` alone on its line, or `key:` followed by only trailing whitespace).
- All immediately following lines starting with `> ` belong to the field value.
- The block ends at the first line that does not start with `>`.
- A line containing only `>` represents a blank line (paragraph break) within the value.
- Inline Markdown (emphasis, links, lists) is preserved verbatim in the parsed string value.
- Each blockquote prefix (the `>` character and the following space) is stripped; the remainder is the content.
- Leading and trailing blank lines within the block are trimmed.

**Important distinction — inline `>` is NOT a blockquote:**

A field with a non-empty value that happens to start with `>` is a regular scalar string, not a blockquote:

```markdown
body: > This is NOT a blockquote
```

This parses as the literal string value `"> This is NOT a blockquote"`. In standard Markdown, blockquotes are block-level constructs that begin at the start of a line — not inline within a key-value pair. JMD follows this convention exactly: blockquote mode is entered only when the key has an empty value and the *next line* starts with `>`.

```markdown
body:
> This IS a blockquote — key has empty value, > starts on its own line
> Second line of the blockquote
```

A conforming generator MUST NOT produce inline blockquotes (`key: > text`). A conforming parser MUST treat `key: > text` as a scalar string with literal value `"> text"`.

**Streaming:** Each blockquote line is an independent parse event. No buffering is required. The parser emits content incrementally as lines arrive.

### 9.2 Single-Line Multiline (Escape Form)

For short multiline content where streaming is critical, quoted strings with JSON escape sequences remain valid:

```markdown
note: "First line\nSecond line\nThird line"
```

This form is fully streamable as a single-line value and is appropriate when the content is short or when maximum streaming granularity is required.

### 9.3 Choosing the Right Form

| Content type | Form | Streaming | Markdown |
| --- | --- | --- | --- |
| Articles, descriptions, AI-generated analysis | blockquote (`>`) | Line-by-line | Preserved |
| Code, config, templates, logs | blockquote (`>`) | Line-by-line | Preserved |
| Short strings with newlines | `"...\n..."` escape | Immediate | None |

### 9.4 Design Rationale

Blockquotes are the native Markdown construct for embedded prose, and LLMs produce them reliably without special instruction. Live testing across three major LLMs confirms that a minimal hint ("use blockquotes for multiline text") triggers the exact `>` prefix pattern that JMD formalizes.

Blockquotes preserve JMD's streaming property completely: each `>` line is a position marker that self-identifies as multiline content. No closing delimiter is needed — the block ends at the first line that does not start with `>`. This makes blockquotes structurally identical to other JMD constructs: every completed line advances the parse state independently.

Single-line values remain the default for fields that fit on one line. Multiline forms are reserved for content that genuinely requires multiple lines. A conforming parser MUST accept both forms (blockquote and escape) for any string field. A conforming generator SHOULD use blockquotes for multiline content and single-line values for everything else.

---

## 10. Complete Example

### JMD

```markdown
# Order
id: 42
status: "pending"
paid: false
notes: null
description:
> Ships within **2 business days**
> from our central warehouse.
>
> Please note: fragile items may require
> additional handling time.

## address
street: Hauptstraße 1
city: Berlin
zip: "10115"
### geo
lat: 52.52
lng: 13.40

## tags[]
- express
- fragile

## items[]
- sku: A1
  qty: 2
  price: 29.99
- sku: B3
  qty: 1
  price: 24.99

## matrix[]
### []
- 1
- 2
### []
- 3
- 4

total: 84.99
```

### Equivalent JSON

```json
{
  "id": 42,
  "status": "pending",
  "paid": false,
  "notes": null,
  "description": "Ships within **2 business days**\nfrom our central warehouse.\n\nPlease note: fragile items may require\nadditional handling time.",
  "address": {
    "street": "Hauptstraße 1",
    "city": "Berlin",
    "zip": "10115",
    "geo": {"lat": 52.52, "lng": 13.40}
  },
  "tags": ["express", "fragile"],
  "items": [
    {"sku": "A1", "qty": 2, "price": 29.99},
    {"sku": "B3", "qty": 1, "price": 24.99}
  ],
  "matrix": [[1, 2], [3, 4]],
  "total": 84.99
}
```

Note how the document uses several JMD features:

- **Multiline string via blockquote:** The `description` field uses blockquote lines to express rich text with inline Markdown (**bold**). The empty `>` line produces a paragraph break in the serialized value. Each `>` line is independently streamable.
- **Blank lines** separate top-level blocks naturally. The blank line after the blockquote block ends the `description` value. The blank line after `lng: 13.40` closes both `### geo` and `## address`, returning to root scope. The blank line before `## tags[]` is cosmetic (the heading sets its own scope). The blank line after the last `### []` block returns to root, so `total: 84.99` is a bare root-level field — no `##` prefix needed.
- **Headings** (`## address`, `## tags[]`, etc.) explicitly set scope depth. A scalar heading like `## total: 84.99` would also work for scope return, but the blank line makes it unnecessary here.

Simple root-level fields at the beginning (`id`, `status`, etc.) need no heading prefix because they are within the `#` root scope before any `##` heading opens a deeper scope.

---

## 11. Grammar (EBNF)

The following grammar defines the syntax of JMD data documents.

Heading depth determines hierarchy. A heading at depth N (encoded as N `#` characters followed by a space) opens a scope as a child of the scope at depth N-1. Bare fields belong to the innermost open object scope. Blank lines reset scope to root (see Section 7.2a).

```ebnf
(* ===== Document ===== *)

document        ::= frontmatter? root_heading NEWLINE body
root_heading    ::= "# []" | "# " label?

(* ===== Frontmatter ===== *)
(* Fields before the first heading are document-level metadata.
   They are NOT serialized into the JSON output. See Section 3.5. *)

frontmatter     ::= (frontmatter_field NEWLINE)+ BLANK_LINE?
frontmatter_field ::= key ": " value
                    | key                    (* bare key, e.g. 'count' *)
label           ::= label_char+
label_char      ::= (* any character except NEWLINE *)
                     (* An absent label (anonymous heading) is valid;
                        it is treated as an empty string. See Section 3.2a. *)

body            ::= (element | SCOPE_RESET)*
element         ::= heading_element | bare_field | array_item | indent_field

(* A blank line resets scope to root. Within array bodies,
   a blank line followed by '-' is cosmetic (see Section 7.2a). *)
SCOPE_RESET     ::= BLANK_LINE

(* ===== Heading Elements ===== *)

heading_element ::= scalar_heading | object_heading | array_heading
                   | sub_array_heading | depth_item

heading_prefix  ::= "#"+ " "
                     (* N '#' characters followed by a space, where N >= 2.
                        N determines the heading depth.
                        A heading_prefix with no following content is an
                        anonymous heading — see Section 3.2a. *)

scalar_heading  ::= heading_prefix key ": " value NEWLINE
object_heading  ::= heading_prefix key? NEWLINE
array_heading   ::= heading_prefix key "[]" NEWLINE
sub_array_heading ::= heading_prefix "[]" NEWLINE
depth_item      ::= heading_prefix "-" NEWLINE
                   | heading_prefix "- " key ": " value NEWLINE

(* ===== Bare Fields ===== *)

bare_field      ::= key ": " value NEWLINE
                   | key ": " NEWLINE multiline_value

(* ===== Multiline Values ===== *)

multiline_value ::= blockquote_block

blockquote_block ::= blockquote_line+
                     (* Each line starts with '> ' or is exactly '>'.
                        The block ends at the first line that does not
                        start with '>'. Fully streamable. *)
blockquote_line  ::= "> " bare_string_char* NEWLINE
                   | ">" NEWLINE
                     (* A line containing only '>' is a paragraph break
                        within the value. *)

(* ===== Array Items ===== *)

array_item      ::= scalar_item | object_item
scalar_item     ::= "- " value NEWLINE
                     (* value MUST NOT match 'key ": " value' pattern;
                        strings that look like key-value pairs must be quoted. *)
object_item     ::= "-" NEWLINE
                   | "- " key ": " value NEWLINE
                     (* First field on the '- ' line. Additional fields
                        follow as indented continuation lines. *)

indent_field    ::= INDENT key ": " value NEWLINE
                     (* INDENT = 2+ space characters. Indented fields
                        belong to the current array item. The exact
                        indentation depth is not significant — any line
                        starting with 2+ spaces followed by a key: value
                        pattern is a continuation field. *)
INDENT          ::= " " " " " "*
                     (* Two or more space characters. *)

(* ===== Keys ===== *)

key             ::= bare_key | quoted_key
bare_key        ::= bare_key_char+
bare_key_char   ::= ALPHA | DIGIT | "_" | "-"
quoted_key      ::= json_string

ALPHA           ::= [a-zA-Z]

(* ===== Values ===== *)

value           ::= json_string | number | "true" | "false" | "null" | bare_string

bare_string     ::= bare_string_char+
                     (* MUST NOT parse as null, true, false, or number.
                        MUST NOT start with '"', '#', or '- '.
                        MUST NOT be exactly '-'.
                        See Section 6 for full disambiguation rules. *)
bare_string_char ::= (* any character except NEWLINE *)

(* ===== JSON Strings — RFC 8259 ===== *)

json_string     ::= '"' json_char* '"'
json_char       ::= unescaped | escaped
unescaped       ::= (* U+0020 .. U+0021 | U+0023 .. U+005B | U+005D .. U+10FFFF *)
escaped         ::= "\" escape_char
escape_char     ::= '"' | "\" | "/" | "b" | "f" | "n" | "r" | "t"
                   | "u" HEX HEX HEX HEX

HEX             ::= DIGIT | "A" | "B" | "C" | "D" | "E" | "F"
                           | "a" | "b" | "c" | "d" | "e" | "f"

(* ===== Numbers — RFC 8259 ===== *)

number          ::= "-"? int frac? exp?
int             ::= "0" | onenine DIGIT*
onenine         ::= "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"
DIGIT           ::= "0" | onenine
frac            ::= "." DIGIT+
exp             ::= exp_e exp_sign? DIGIT+
exp_e           ::= "e" | "E"
exp_sign        ::= "+" | "-"

(* ===== Whitespace ===== *)

NEWLINE         ::= U+000A
BLANK_LINE      ::= NEWLINE           (* a line containing only whitespace or nothing;
                                         semantically resets scope to root level *)
```

### 11.1 Parser State Model

A JMD parser maintains a **scope stack** — a stack of open scopes, each tagged with its heading depth and type (object or array). The parser processes lines as follows:

0. **Frontmatter** (lines before the first heading): Any `key: value` or bare `key` lines encountered before the first `#` heading are document-level metadata (see Section 3.5). They are stored separately and not serialized into the JSON output.
1. **Heading line** (`#`+ space ...): Determine heading depth N. Pop all scopes with depth ≥ N. Open a new scope at depth N.
2. **Bare field** (`key: value`): Add field to the innermost open object scope.
3. **Bare field with empty value** (`key:`): If the next line starts with `>`, enter multiline mode for this field (see rule 7).
4. **`- key: val`** (object item): Start a new item in the innermost open array scope with its first field. If content after `- ` matches `key: value` pattern, it is an object item; otherwise it is a scalar item (`- value`). Additional fields follow as indented continuation lines (see rule 8).
5. **Bare `-`** (object item with no first-line field): Start a new item in the innermost open array scope.
6. **Depth-qualified `-`** (e.g., `## -` or `## - key: val`): Pop scopes back to depth N, then start a new item in the array at depth N.
7. **Blockquote line** (`>` ...): Append content (after stripping `>` prefix) to the current multiline field. A line containing only `>` appends a blank line. The multiline field ends when a line not starting with `>` is encountered. Each blockquote line emits a streaming event independently.
8. **Indented field** (2+ spaces followed by `key: value`): Add field to the current array item. This is the Markdown list continuation pattern — indented lines belong to the current `- ` item. The exact indentation depth is not significant; any line starting with 2+ spaces followed by a `key: value` pattern is a continuation field.
9. **Blank line**: Pop all scopes, returning to root scope (depth 1). **Exception:** within an array body, if the next non-blank line is `-` or `- value`, the blank line is cosmetic (visual separator between array items) and does not reset scope.

This model uses indentation in exactly one context: list item continuation within arrays (rule 8). This is not hierarchy-encoding indentation — it means only "this field belongs to the current `- ` item." All hierarchy is still expressed exclusively through heading depth.

---

## 12. Conversion Rules Summary

| Construct | JMD Syntax |
|-----------|-----------|
| Document frontmatter | `key: value` lines before the first `#` heading (not serialized) |
| Root object | `# Label` |
| Root array | `# []` |
| Scalar field (in scope) | `key: value` |
| Scalar heading (scope return) | `## key: value` |
| Blank line (scope reset to root) | Empty line between blocks |
| Quoted key | `"key name": value` |
| Nested object | `## key` / `### key` (heading depth = nesting depth + 1) |
| Empty object | `## key` with no following fields or deeper headings |
| Array | `## key[]` / `### key[]` + list items |
| Empty array | `## key[]` with no items |
| Array of scalars | `- value` |
| Array of objects | `- key: val` + indented `key: val` continuation lines, or `-` + bare fields |
| Sub-array | `### []` (one depth deeper than parent array) |
| Depth-qualified item | `## -` / `## - key: val` (item in array at specified depth) |
| Heterogeneous array | Mixed `- value`, `-` + fields, `### []` |
| Multiline string (rich text) | Blockquote lines: `key:` followed by `>` lines |
| Multiline string (inline) | Quoted value with JSON escapes: `"line 1\nline 2"` |
| Ambiguous string | Quoted value: `"42"`, `"true"`, `"null"` |

---

## 13. Query by Example (QBE) Documents

JMD defines a **query document mode** for expressing *what data is desired*. A query document uses the root marker `#?` and shares the complete body syntax of a data document — nested headings, bare fields, arrays, bullets, blockquotes, frontmatter. JMD itself assigns no filter-semantic interpretation to field values. The consuming application determines what filter, projection, or pagination semantics apply.

### 13.1 Document Mode

The root marker `#?` signals a query document:

```markdown
#? Order
status: pending
total: > 50
```

Body syntax is identical to Sections 7–9. Each field-value pair is a string parsed per Sections 2.1 and 5. The envelope (§3.6) reports `mode: "query"`, `label: "Order"`, `frontmatter: {...}`, and `value: {status: "pending", total: "> 50"}` — with the values preserved verbatim as strings.

### 13.2 Values Are Raw Strings

A conforming JMD parser returns query document values verbatim. The value `"> 50"` in `total: > 50` is the string `"> 50"`; it is not parsed into a comparison object, operator tuple, or filter AST by JMD. The parser reports the raw string in `value`; any structured interpretation is performed by the application that consumes the envelope.

This is a deliberate design decision:

- Different applications have fundamentally different filter semantics (SQL `WHERE`, Firestore queries, MongoDB `$gt`/`$in`, OData `$filter`, SmartSuite filter DSL, GraphQL where-clauses, …). Freezing one dialect as the JMD parse contract would unnecessarily exclude the others.
- Applications that want structured interpretation of query values implement their own parser over the raw string, producing whatever filter representation their target backend requires.
- JMD's role is carrier: deliver the document structure and string contents; leave semantic interpretation to the application layer.

### 13.3 Recommended Conventions

A common QBE dialect — equality, comparison operators (`>`, `>=`, `<`, `<=`), contains (`~`), negation (`!`), projection (`?`), EXISTS-style array semantics — is collected non-normatively in **Appendix A.1**. Applications MAY adopt it as-is, extend it, or replace it entirely; documents using any application-specific dialect remain valid JMD as long as they obey the structural grammar.

Request and response metadata (pagination, projection, sort, count, expansion) are conveyed via frontmatter. Recommendations for frontmatter keys are given in §23; they are non-normative SHOULDs.

### 13.4 Four Operations

In a JMD-native MCP or API context, the four canonical operations map cleanly to document modes:

| Operation | Input | Output |
|---|---|---|
| `read(path)` | path string | JMD data document |
| `write(path, body)` | path + JMD data document | confirmation |
| `query(body)` | JMD query document (`#?`) | JMD result document |
| `delete(path, body)` | path + JMD delete document (`#-`) | confirmation |

This gives an LLM a complete, minimal interface to any data source using only JMD documents as the communication format.

---

## 14. Schema Documents

A JMD schema document describes the expected structure of a data document. It uses the root marker `#!` and shares the complete body syntax of a data document — nested headings, bare fields, arrays, bullets. JMD itself assigns no type-semantic interpretation to field values. The consuming application determines what type system, constraints, or validation semantics apply.

### 14.1 Document Mode

The root marker `#!` signals a schema document:

```markdown
#! Order
id: integer
status: pending|active|shipped
customer: -> Customer
```

Body syntax is identical to Sections 7–9. Each field-value pair is a string parsed per Sections 2.1 and 5. The envelope (§3.6) reports `mode: "schema"`, `label: "Order"`, and `value: {id: "integer", status: "pending|active|shipped", customer: "-> Customer"}` — with the values preserved verbatim as strings.

### 14.2 Values Are Raw Strings

A conforming JMD parser returns schema document values verbatim. The value `"integer"` is the string `"integer"`; the value `"-> Customer"` is the string `"-> Customer"`. JMD does not parse these into type ASTs, reference objects, or constraint structures.

This is a deliberate design decision:

- Different applications have fundamentally different type systems (TypeScript type literals, JSON Schema, OData EDM, Protocol Buffers, SmartSuite field types, Firestore security rules, GraphQL schemas, Pydantic models, …). Freezing one as the JMD parse contract would unnecessarily exclude the others.
- Applications that want structured interpretation of schema values implement their own parser over the raw string, producing whatever type representation their target domain requires.
- JMD's role is carrier: deliver the document structure and string contents; leave type interpretation to the application layer.

The previous versions of this section prescribed a specific type vocabulary (base types, modifiers, defaults, enum alternation, entity references, inline object types, binary encoding). In v0.3.2 this prescription was recognized as over-specification: the JMD parser's role is structural, and different applications legitimately need different type systems. The prescribed conventions remain available — see Appendix A.2 — but as recommendations, not requirements.

### 14.3 Recommended Conventions

A common schema dialect — scalar type names (`string`, `integer`, `boolean`, `number`, `null`, `object`), modifiers (`optional`, `readonly`), default values (`= scalar`), enum alternation (`a|b|c`), format hints (`email`, `date`, `datetime`, `uri`), entity references (`->`), inline object types (`object(...)`), and binary content conventions (Base64, `sha256:`) — is collected non-normatively in **Appendix A.2**. Applications MAY adopt it as-is, extend it, or replace it entirely; documents using any application-specific dialect remain valid JMD as long as they obey the structural grammar.

### 14.4 Four Operations

In an MCP context, schema documents serve as the contract for all four operations:

| Operation | Schema role |
|---|---|
| `read(path)` | Schema describes what the response will look like |
| `write(path, body)` | Schema validates the body before submission |
| `query(body)` | Schema describes filterable and projectable fields |
| `delete(path, body)` | Schema identifies which fields serve as resource identifiers |

---

## 15. Delete Documents

A JMD delete document signals the intent to remove a resource. It uses the root marker `#-` and shares the same syntax foundation as all other JMD document modes.

### 15.1 Root Marker

```markdown
#- Order
```

The `#-` marker is parsed as a depth-1 heading with mode prefix `-`, analogous to `#?` (query) and `#!` (schema). The label identifies the resource type being deleted.

### 15.2 Delete Request

A delete document contains the identifier fields necessary to locate the target:

```markdown
#- Order
id: 42
```

The body is a standard JMD object — the same syntax as a `# Order` data document. The `#-` root marker is the only difference. This means an LLM that can produce a data document can produce a delete document by changing one character in the root marker.

### 15.3 Delete Response

The response is the complete JMD data document of the deleted resource — exactly as it would have been returned by a data read before deletion:

```markdown
# Order
id: 42
status: shipped
total: 84.99
paid: true
created_at: 2026-01-15T09:23:00Z

## address
street: Hauptstraße 1
city: Hamburg
zip: 20095
country: Germany

## items[]
- sku: A1
  qty: 2
  price: 29.99
- sku: B3
  qty: 1
  price: 24.99
```

### 15.4 Delete Grammar (EBNF)

A delete document reuses the data document grammar from Section 11 without modification. The root marker is the only syntactic difference.

```ebnf
delete_document  ::= "#- " label NEWLINE body
```

### 15.5 Design Rationale

1. **Explicit intent.** Delete is a destructive operation. A dedicated root marker (`#-`) makes the intent unambiguous at the document level — no path-suffix conventions or HTTP method inspection required.

2. **LLM-native.** The hyphen in `#-` visually suggests "removal" and follows the Markdown convention where `-` marks list items (things to be processed). An LLM can produce `#- Order\nid: 42` as naturally as `# Order\nid: 42`.

3. **Transport-agnostic.** The `#-` marker carries the delete intent within the document itself. This works over HTTP, MCP, WebSocket, or any other transport — the consumer does not need to inspect HTTP methods or path patterns to understand the operation.

4. **Completes CRUD.** With `#-`, JMD covers the full lifecycle: Create and Update via `#` (data), Read via `#` (data response), Query via `#?`, Schema via `#!`, Delete via `#-`.

---

## 16. Collection Responses and Pagination

Collection responses return array data with pagination metadata. In JMD, pagination metadata belongs in the response frontmatter — structurally separate from the document body, and immediately available to the next agent in the pipeline without inspecting the data schema:

```markdown
total: 142
page: 2
pages: 8
page-size: 20

# Orders

## data[]
- id: 1
  status: pending
  total: 84.99
- id: 2
  status: shipped
  total: 120.00
```

The root marker `# Orders` (not `# []`) signals that this is a named collection response. A bare array response (`# []`) carries items only, with no metadata.

Pagination is requested via frontmatter in the query document (see Section 3.5):

```markdown
page: 2
page-size: 20

#? Order
status: active
```

Pagination metadata in the response (`total`, `page`, `pages`, `page-size`) MUST appear as frontmatter — before the root heading. This is a streaming guarantee: the consumer receives result set metadata before the first data record, allowing early decisions (close connection, narrow query, request next page). It also prevents ambiguity with body fields that share names (e.g., `total` as a field on an order line item vs. `total` as result set size).

The schema for a collection response body:

```markdown
#! Orders
## data[]: object
- id: integer
  status: string
  total: number
```

---

## 17. Error Documents

Error documents use the same format as data documents. This ensures that a consumer processing a response stream never needs to switch parsers or handling modes based on external signals.

A JMD error document uses the reserved label `Error`:

```markdown
# Error
status: 404
code: not_found
message: Order 42 does not exist
```

**Defined error fields:**

| Field | Type | Purpose |
| --- | --- | --- |
| `status` | integer | Numeric status code (e.g. HTTP status) |
| `code` | string | Machine-readable error identifier in snake_case |
| `message` | string | Human-readable error description |
| `suggestion` | string | Free-form remediation hint — the generator describes what the caller could do differently |
| `context` | string | Free-form additional context the generator considers relevant for understanding the error |

The `status` and `code` fields are deterministic and machine-routable. The `message`, `suggestion`, and `context` fields are free-form bare strings that the generator fills in from its own perspective — analogous to the epistemic frontmatter fields (Section 3.5). A generator is not required to populate all fields; `status` and `code` are sufficient for a minimal error document.

**Structured error details** use an `errors[]` array for field-level validation failures:

```markdown
# Error
status: 422
code: validation_failed
message: Request body failed schema validation
suggestion: The qty field must be positive. Check whether the source data contains negative inventory values.
context: This endpoint validates against the OrderItem schema, which requires qty >= 1.

## errors[]
- field: items[0].qty
  reason: must be a positive integer
  value: "-3"
- field: address.zip
  reason: does not match expected format
  value: abc
```

Each item in `errors[]` carries `field` (the path to the offending field), `reason` (machine- or human-readable cause), and `value` (the rejected value as a string). Additional fields per error item are permitted and passed through.

**Streaming errors:** In a streaming response, an error occurring mid-stream is signalled by emitting a `# Error` document as the next complete JMD document in the stream. The `# Error` heading implicitly closes all open scopes from the preceding data document. A consumer detects the transition by encountering a new root heading while the previous document's scope is still open.

**Error code vocabulary:** JMD deliberately does not define a standard set of error codes. Error codes are domain-specific — a database API, an e-commerce platform, and a medical records system have fundamentally different failure modes. The `code` field carries whatever snake_case identifier the server defines. Common conventions (`not_found`, `validation_failed`, `unauthorized`, `rate_limited`) will emerge naturally through usage, not through specification mandate.

---

## 18. Streaming

JMD is designed to be streamed and parsed incrementally. This is not an optional feature or a compatibility mode — it is a structural consequence of the format's syntax, and one of its most significant architectural advantages over JSON for LLM-native systems.

### 18.1 Why JSON is Streaming-Hostile

JSON's closure-based syntax requires a complete document before parsing can succeed. Every object needs a closing `}`, every array a closing `]`. These delimiters arrive last, which means a partially received JSON document is syntactically invalid and cannot be acted upon.

This was an acceptable property when APIs were consumed by code that could buffer and wait. It becomes a structural liability when APIs are consumed by LLM agents operating in real-time pipelines, where every millisecond of buffering delay compounds across inference steps, tool calls, and chained workflows.

Streaming JSON parsers exist — `ijson`, `oboe.js`, NDJSON — but they are workarounds for a fundamental design constraint, not solutions. They require additional buffering logic, increase implementation complexity, and in the case of NDJSON, abandon standard JSON syntax entirely in favour of a newline-delimited convention that the broader JSON ecosystem does not recognise.

### 18.2 Why JMD is Structurally Streaming-Native

JMD's line-oriented syntax makes every completed line a self-contained semantic event. No closing delimiter is ever required to make sense of what has been received so far.

The line types and their streaming semantics:

| Line | Event emitted | Information available immediately |
|---|---|---|
| first heading (after frontmatter) | `DOCUMENT_START` | `mode`, `label`, `frontmatter` (full envelope header — see §3.6) |
| `key: value` | `FIELD` | Key name, parsed value |
| `key:` (empty value) | `FIELD_START` | Key name; value follows as multiline |
| `> text` (blockquote) | `FIELD_CONTENT` | Incremental multiline content (streamable) |
| `## key` | `OBJECT_START` | Key name of nested object |
| `## key[]` | `ARRAY_START` | Key name of array |
| `-` or `- key: val, ...` | `ITEM_START` | New object item begins |
| `- value` | `ITEM_VALUE` | Parsed scalar item value |
| blank line (non-cosmetic) | `SCOPE_RESET` | All open scopes closed; parser at root |

A scope closes implicitly when a heading at the same or shallower depth arrives, when a non-cosmetic blank line is encountered, or at EOF. No explicit closing token is ever needed. A consumer can act on each event the moment the line's newline arrives.

The blockquote form for multiline strings preserves this streaming property: each `>` line emits a `FIELD_CONTENT` event independently. Every JMD construct — without exception — is fully streamable. No buffering is ever required.

`SCOPE_RESET` is followed by implicit `OBJECT_END` / `ARRAY_END` events for each scope on the stack, in reverse order. A blank line within an array body that is followed by a `-` item is cosmetic and does not emit `SCOPE_RESET`.

The `DOCUMENT_START` event carries the full envelope header (mode, label, frontmatter) — the same three fields that appear on the envelope returned by a non-streaming parser (§3.6). A receiver that buffers only the first event has complete document-level metadata before any body event arrives. Subsequent events (`FIELD`, `OBJECT_START`, `ARRAY_START`, …) carry only body content; they do not re-transmit the envelope header. This mirrors standard streaming conventions (SAX, Server-Sent Events, gRPC streaming): the header is transmitted once, the body streams.

The complete event sequence for a typical Order document:

```
DOCUMENT_START  mode="data", label="Order", frontmatter={}
FIELD           id = 42
FIELD           status = "pending"
FIELD           paid = false
OBJECT_START    address                    (## address)
FIELD           street = "Hauptstraße 1"
FIELD           city = "Berlin"
FIELD           zip = "10115"
OBJECT_START    geo                        (### geo)
FIELD           lat = 52.52
FIELD           lng = 13.40
SCOPE_RESET                                (blank line → all scopes to root)
OBJECT_END      geo
OBJECT_END      address
ARRAY_START     tags                       (## tags[])
ITEM_VALUE      "express"
ITEM_VALUE      "fragile"
ARRAY_START     items                      (## items[])
ITEM_START                                 (- sku: A1, qty: 2, price: 29.99)
FIELD           sku = "A1"
FIELD           qty = 2
FIELD           price = 29.99
ITEM_END
ITEM_START                                 (- sku: B3, qty: 1, price: 24.99)
FIELD           sku = "B3"
FIELD           qty = 1
FIELD           price = 24.99
ITEM_END
ARRAY_END       items
SCOPE_RESET                                (blank line → return to root)
FIELD           total = 84.99              (bare root-level field)
DOCUMENT_END
```

The parser maintains a scope stack driven by heading depth and blank-line scope resets. No indentation tracking, no look-ahead, no buffering for closing delimiters.

### 18.2a Streaming Advantage by Payload Size

The streaming advantage scales with payload size. For small single-resource responses, the benefit is modest. For large collection queries — the primary data-intensive operation in REST APIs — the advantage becomes substantial, because JMD's streaming parser emits a `FIELD` event from the first completed `key: value` line, while JSON's incremental parsers must accumulate enough structure to yield a key-value pair (opening braces, quoted key string, value). Empirical TTFUB measurements are provided in the companion document *JMD Efficiency Analysis*.

### 18.2b The Middleware Streaming Bottleneck

The streaming measurements above reflect direct LLM-to-consumer scenarios. In a middleware architecture — where a MCP server or API gateway translates between JSON and JMD — the streaming advantage is structurally constrained:

```
LLM  ←→  JMD  ←→  MCP Server  ←→  JSON  ←→  REST API
```

The MCP server cannot begin emitting JMD lines until the complete JSON response has arrived from the upstream API. JSON's closure-based syntax requires all closing delimiters before the document is valid, forcing the middleware to buffer the entire response before conversion. JMD's line-by-line streaming capability is negated by the JSON intermediary.

This is not a flaw in JMD or in the middleware — it is an inherent consequence of translating from a buffered format to a streaming format. The middleware architecture is a necessary transitional step that proves JMD's value proposition with existing JSON APIs. But the full streaming advantage is only realized when the data source speaks JMD natively:

```
LLM  ←→  JMD  ←→  JMD-Native API / Database
```

In this architecture, the server emits JMD lines as it reads database rows — no JSON intermediary, no buffering, true line-by-line streaming from storage to LLM. Framework middleware plugins (FastAPI, Express, Rails) that add `Accept: application/jmd` support to existing APIs are a practical step toward this goal, requiring minimal implementation effort (~100 lines per framework) while enabling the full streaming pipeline.

### 18.3 Streaming over HTTP REST

The streaming benefit is negligible for small single-resource responses. It becomes substantial for collection queries — the primary data-intensive operation in REST APIs.

**The non-streaming JSON case:**

```
Client                          Server
  |                               |
  |-- POST /orders/$query ------->|
  |                               | (evaluates query)
  |                               | (serialises entire result set)
  |                               | (waits for last ] )
  |<-- 200 OK [complete JSON] ----|
  |   (first item processable     |
  |    only after full response   |
  |    has arrived)               |
```

**The JMD streaming case:**

```
Client                          Server
  |                                |
  |-- POST /orders/$query -------->|
  |                                | (begins evaluating query)
  |<-- # [] -----------------------| (document start: immediately)
  |<-- - --------------------------| (item 1 start: first db row)
  |<-- id: 1 ----------------------| (field available: act now)
  |<-- status: pending ------------|
  |   (client routes item 1        |
  |    while server fetches row 2) |
  |<-- ## items[] -----------------|
  |<-- ... ------------------------|
  |<-- ## - -----------------------| (item 2 start)
  |<-- id: 2 ----------------------|
  |   ...                          |
```

The server uses HTTP chunked transfer encoding (`Transfer-Encoding: chunked`). Each line is a chunk boundary. The client's JMD parser fires events as chunks arrive.

**Practical latency impact:** For a query returning 100 orders, the first item is available after the first database row is fetched and serialised — typically tens of milliseconds. With JSON, the first processable item is available after all 100 rows are fetched, serialised, and the closing `]` transmitted. For large result sets or slow backends, this is the difference between seconds and milliseconds for time-to-first-useful-data.

**Early termination:** Because items are processable individually, a consumer that finds what it needs after the first few items can close the connection early. The server stops generating, the network stops transmitting. With JSON, the full response must be received before any item can be processed, making early termination impossible without discarding partially received data.

**Content-Type for streaming collections:**

```http
HTTP/1.1 200 OK
Content-Type: application/jmd
Transfer-Encoding: chunked
X-JMD-Streaming: true
```

The `X-JMD-Streaming` header is advisory: it signals to the client that the response is being generated incrementally, and that the JMD streaming parser should be used rather than buffering the full response.

### 18.4 Streaming over Server-Sent Events

Server-Sent Events (SSE) are a natural transport for JMD in push-based scenarios: live dashboards, real-time monitoring, LLM tool output that should be visible as it is generated.

SSE and JMD compose cleanly because both are line-oriented text protocols. An SSE stream carries a sequence of events; each event carries a `data:` field. A JMD document maps to a single SSE event:

```
data: # Order
data: id: 42
data: status: pending
data: total: 84.99
data:
```

The blank `data:` line terminates the SSE event. The receiver strips the `data: ` prefix from each line, reassembles the content into a JMD source string, and parses it as a complete document.

**SSE transport and JMD blank-line semantics.** JMD uses blank lines as a scope-reset signal (Section 7.2a). SSE uses blank lines as event terminators. These two conventions operate at different layers and do not conflict:

- JMD blank lines appear *inside* the `data:` payload, prefixed with `data: ` (a line containing only `data:` with no trailing text). The SSE parser never sees a raw blank line inside an event — it only sees `data:` lines.
- The SSE event terminator is a *bare* blank line (no `data:` prefix) between events.
- When the receiver reconstructs the JMD source by stripping `data: ` prefixes, a `data:` line produces an empty line, which the JMD parser correctly interprets as a scope reset.

The two protocols are therefore composable without escaping or additional framing.

For high-frequency updates — where individual fields change rather than whole documents — a JMD SSE stream can carry partial documents, one field per event:

```
event: field
data: id: 42

event: field
data: status: processing

event: field
data: ## items[]

event: field
data: - sku: A1, qty: 2
```

This is the most granular streaming mode: each `data:` line is a single JMD parse event. A consumer implementing the streaming parser receives complete semantic events with no additional buffering. This mode is particularly useful for streaming LLM tool output in real time: as the model generates each line of its JMD response, it is immediately visible to the consuming system.

**SSE endpoint convention:**

```
GET /orders/$stream         →  SSE stream of Order events
GET /orders/42/$stream      →  SSE stream for single resource (live updates)
```

The `$stream` path suffix signals that the response is an SSE stream rather than a one-shot HTTP response.

### 18.5 Streaming in MCP Tool Calls

The Model Context Protocol (MCP) defines a message-passing interface between LLM agents and tool servers. A tool call results in a `tool_result` message carrying the tool's output as text. In current practice this text is typically JSON, delivered as a complete document after the tool has finished executing.

JMD changes this interaction in two ways.

**Incremental tool output.** An MCP server generating a JMD response can emit lines as they are produced, rather than buffering until the full response is ready. The agent's context window receives fields as they arrive. For a tool call that reads from a database, the first fields of the first record are in context within milliseconds of the first row being fetched — while the server continues fetching remaining rows.

This is not merely a latency improvement. It changes the agent's reasoning behaviour: the agent can begin planning its next action based on partial results, rather than waiting for a complete response before any reasoning step begins.

**Token budget reduction.** In a long agentic chain, intermediate results often carry more fields than the agent needs. With streaming, a consuming agent can identify which fields are relevant after the first few arrive, and signal to the tool server — via connection close or a protocol-level acknowledgement — that no further output is needed. This reduces both latency and token consumption for the subsequent reasoning step.

**Concrete MCP interaction:**

```
Tool call:  read("/orders?status=pending")

Tool output (streamed, line by line):
  # []
  - id: 1, status: pending, total: 84.99     ← agent sees id+status; begins planning
  - id: 2, status: pending, total: 120.00
  ...
```

The agent does not wait for the `DOCUMENT_END` event. After `ITEM_END` for the first item, it has enough information to decide whether to proceed, filter, or issue a follow-up call.

### 18.6 Streaming in Chained Agentic Workflows

The strongest argument for JMD streaming is not any single interaction but the compound effect across multi-agent pipelines.

Consider a three-step chain:

```
Agent A                 Agent B                 Agent C
reads /orders           filters by criteria     writes to /reports
(JMD source)            (JMD transformation)    (JMD target)
```

**With JSON:**
- Agent A waits for complete JSON response → deserialises
- Agent A serialises complete filtered output → Agent B waits
- Agent B waits for complete input → filters → serialises
- Agent C waits for complete input → writes

Every step is a complete-and-forward cycle. Latency is additive: `T_A + T_B + T_C`.

**With JMD streaming:**
- Agent A begins emitting JMD as first rows arrive
- Agent B begins processing Agent A's output after first item
- Agent B begins emitting to Agent C before Agent A has finished
- Agent C begins writing before Agent B has finished

The pipeline is a continuous flow. Latency is not additive but overlapping: roughly `max(T_A, T_B, T_C)` rather than their sum. For pipelines of five or more steps operating on large collections, this is the difference between a pipeline that takes thirty seconds and one that takes eight.

**This property requires no special protocol support.** It follows directly from JMD's line-oriented syntax: any agent that writes JMD to stdout can be piped to any agent that reads JMD from stdin. The format is its own streaming protocol.

### 18.7 The Structural Basis of the Streaming Advantage

The streaming advantage is not an added feature — it is a structural consequence of the syntax choice.

JSON's closure-based model (`{...}`, `[...]`) was designed for complete document exchange. It is expressive and universally supported, but it encodes hierarchy through delimiters that must arrive in matched pairs. A receiver cannot know whether it has a complete value until the closing delimiter arrives. This is an intrinsic property of the grammar, not an implementation accident.

JMD's heading-based model encodes hierarchy through position: a heading at depth N opens a scope that contains everything at depth N+1 or deeper, until the next heading at depth N or shallower. Scope boundaries are deducible from each line in isolation. A receiver that has seen `## address` knows immediately that the following bare fields belong to `address` — without having seen a closing brace, without lookahead, without buffering.

The same structural property that makes JMD token-efficient for LLMs — Markdown's heading model, which LLMs have deeply internalised — also makes it streaming-native. These are not two separate design goals that happen to coexist. They are two manifestations of the same underlying choice: hierarchy through position rather than through delimiters.

JSON established itself as the dominant API format in an era when APIs were consumed by code. Code is patient: it buffers, waits, and deserialises. LLM agents are not patient in the same way — they operate within inference budgets, latency constraints, and context windows that make every token and every millisecond of wait time visible. JMD is designed for this era.

### 18.8 The Training-Data Question

JMD exists in a world where JSON is deeply entrenched in LLM pretraining data. A fair evaluation must address the question: does JSON's familiarity give it an inherent advantage that a new format cannot overcome?

**Minification is not a practical alternative.** The efficiency argument must distinguish input from output. For **output**, minification is simply unavailable: LLMs cannot reliably produce minified JSON even when explicitly instructed — they reproduce the pretty-printed patterns learned during training. Five of six LLMs tested revert to pretty-printed JSON regardless of instruction. For **input**, minification does reduce token count compared to pretty-printed JSON — and true minified JSON has marginally fewer tokens than JMD for static serialization (~12% fewer). However, APIs return pretty-printed JSON by default, making pretty-printed the real-world baseline. Against that baseline, JMD achieves 19–29% fewer input tokens. Crucially, once structured data has been parsed and sits in the LLM's context window, the reasoning cost is identical regardless of source format — the efficiency advantage is captured entirely at the tokenization boundary.

**JMD's efficiency is structural, not cosmetic.** JMD reduces tokens not by stripping whitespace from the same structure, but by eliminating structural overhead entirely: headings replace nested brace pairs, bare keys replace quoted keys, line breaks replace comma-delimiters. This delivers token savings at both ends — as consumed input and as generated output — making it the only format that is simultaneously efficient and reliably generatable by LLMs.

**The training-data advantage is conceptual, not syntactic.** LLMs have deeply internalized the *concept* of structured data serialization — not the specific syntax of JSON. They can fluently produce novel serialization formats with no measurable penalty, as long as the structural concepts (hierarchy, fields, collections) map to familiar patterns. JMD's Markdown-based syntax maps directly to patterns that LLMs have deeply internalized from training data: headings for hierarchy, `key: value` for fields, `- ` for list items. JMD does not face a syntax-familiarity penalty — it leverages the same deep capability that makes JSON work.

**Three design pillars** emerge as structural consequences of the same underlying choice — hierarchy through Markdown headings rather than through matched delimiters:

1. **Compute efficiency through structural simplification.** JMD reduces token count at both ends of the pipeline — as input (19–29% fewer tokens than pretty-printed JSON, the real-world default) and as output (the only efficient format LLMs can reliably generate). The mechanism is structural: headings replace nested brace pairs, bare keys replace quoted keys, line breaks replace comma-delimiters. Every GPU-millisecond saved per request compounds at infrastructure scale.

2. **Streaming.** Every completed JMD line is immediately parseable. Truncated output degrades gracefully — a partial JMD document contains all fields received so far. JSON cannot offer this without non-standard extensions or workarounds.

3. **Full CRUD surface in one syntax.** Data, query, schema, and delete documents share one structural grammar. An LLM that can produce a JMD data document can produce a query (`#?`), schema (`#!`), or delete (`#-`) with only a different root marker. JSON requires separate tooling ecosystems for each concern.

These three pillars are not independent features bolted onto a data format — they are structural consequences of the same design choice. JMD's design methodology — *AI Whispering*, the systematic validation of every syntax decision against the natural generation behaviour of LLMs — is what makes these three properties co-emerge from a single design.

Quantitative benchmark results, methodology details, and alternative format experiments are provided in the companion document *JMD Efficiency Analysis*.

---

## 19. Document Mode Summary

All JMD document modes at a glance:

| Root Marker | Envelope `mode` | Purpose | Value Interpretation |
|---|---|---|---|
| `# Label` | `"data"` | Standard data document | Values are parsed per §2.1 (null/bool/number/string) |
| `# []` | `"data"` | Root-level array | Items are parsed per §2.1 |
| `#? Label` | `"query"` | Query document (QBE) | Values are raw strings; semantics are application-defined (§13, Appendix A.1) |
| `#! Label` | `"schema"` | Structure/type definition | Values are raw strings; semantics are application-defined (§14, Appendix A.2) |
| `#- Label` | `"delete"` | Resource deletion | Values are parsed per §2.1 (same as data) |
| `#- []` | `"delete"` | Bulk resource deletion | Items are parsed per §2.1 (same as data) |

All modes share the same structural grammar (§3–§9). The body of every JMD document is a JSON value — object or array — with scalar leaves parsed per §2.1. The only per-mode difference is how the consuming application **interprets** the resulting string values: data and delete documents contain payload data; query and schema documents contain expressions in an application-defined sub-language that JMD itself does not parse.

---

## 20. Features Deliberately Omitted

The following features were considered and explicitly excluded from JMD. Each omission is a design decision, not an oversight.

**Comments (inline and block):** An earlier draft included a comment syntax based on Markdown bold (`**...**`). This was removed after careful evaluation against JMD's design priorities. The arguments for removal are:

1. *Comments break bijection.* JMD's core property is a lossless roundtrip with JSON. Comments are the only construct that would have no JSON representation — they are silently discarded during serialization. Every other JMD construct maps to exactly one JSON construct; comments would be the sole exception, creating an asymmetry that complicates both the specification and implementations.

2. *Comments add parser complexity disproportionate to their value.* Supporting comments requires the parser to distinguish comment delimiters inside quoted strings (where they are literal content) from those outside quoted strings (where they are comments). This interaction would necessitate a dedicated specification section and add productions to every level of the EBNF grammar. Omitting comments eliminates an entire class of parsing edge cases.

3. *Comments cost tokens with no data payload.* In an LLM-native format where token efficiency is the primary design goal, every token should carry data. Comments consume tokens that are discarded during serialization — they are pure overhead from the perspective of the JSON roundtrip.

4. *Comments serve the wrong audience.* JMD's primary consumers are LLMs, not humans. LLMs do not need comments to understand structured data — they read and reason over the data itself. The argument that LLMs might use comments to document their generation decisions is appealing in theory, but in practice: (a) LLMs cannot read their own comments during sequential generation — they are already past the token when the comment is emitted; (b) a consuming LLM processes all tokens including comments, so comments do not reduce cognitive load; and (c) if metadata about generation decisions is valuable, it belongs in a dedicated data field (e.g. `_reasoning: "..."`) where it survives the JSON roundtrip and can be processed programmatically.

5. *Comments conflict with the streaming model.* Inline comments require the parser to scan ahead within a line for comment boundaries, adding within-line complexity to what is otherwise a clean line-oriented parse. Block comments between array items or object fields add ambiguity about whether a line is data or metadata.

If an application needs annotations that travel with the data, the correct JMD approach is to use a data field: `_note: annotation text`. This preserves bijection, costs no additional parser complexity, and survives the JSON roundtrip.

**Indentation-based nesting:** An earlier design used 2-space indentation to express nesting depth (hierarchy). This was replaced by the heading-scope model for three reasons: (1) Indentation is not LLM-native for hierarchy — models do not reliably track whitespace depth, especially at deeper nesting levels. (2) Indentation is fragile — whitespace differences are invisible to human reviewers and easily corrupted by editors, copy-paste, or transmission. (3) Indentation is token-inefficient — repeated space characters consume tokens without carrying semantic information. The heading-scope model uses Markdown's own section hierarchy, which LLMs have deeply internalized from training data, to express the same nesting structure without any whitespace sensitivity. Note: JMD does use indentation in one narrow context — list item continuation within arrays (Section 8.3) — but this is not hierarchy-encoding. Indented lines after a `- ` item marker mean "this field belongs to the current item," not "this is nested deeper." This is standard Markdown list continuation, which LLMs produce naturally and reliably.

**Canonical form / deterministic serialization:** JSON objects are unordered by specification, and multiple valid JMD documents can represent the same JSON value (different key order, different number formatting). Mandating a canonical form (e.g. lexicographic key sorting) would conflict with LLM text generation, which is sequential and produces keys in the order natural to the content. JMD deliberately leaves serialization order unconstrained: any syntactically valid document that parses to the correct JSON value is a correct JMD document. (Note: blank lines are semantically significant — they reset scope to root — but placing headings with or without preceding blank lines produces the same result, since headings set scope explicitly.)

**Aggregation (GROUP BY, SUM, COUNT):** An LLM receiving a JMD collection can perform aggregation as a reasoning step without any query syntax. Formalizing aggregation would add syntactic complexity for a capability the LLM already has natively.

**Joins:** A well-designed agentic workflow issues multiple `read` calls and combines results in context. Joins encoded in query syntax would require the LLM to produce more complex and error-prone output, with no benefit over sequential reads.

**Sorting (ORDER BY):** An LLM can sort any result set as a reasoning step. Formalizing sort syntax in QBE would add grammar productions and require the LLM to learn an ordering convention (`_sort: -date`, `+name`?) that varies across every existing query language. Since QBE's purpose is domain reduction — narrowing the result set to context-window size — sort order is irrelevant to that goal. The LLM sorts the reduced set itself, in whatever order its task requires.

**A JMD-normative query language:** Earlier drafts of this specification prescribed a specific QBE dialect as part of §13 (regex-based pattern matching, explicit comparison operators, `~` contains, `!` negation, `?` projection). In v0.3.2 the normative prescription was withdrawn: JMD is a carrier format, and the interpretation of filter expressions is application-defined. The common dialect that was previously normative is preserved non-normatively in Appendix A.1. Freezing one dialect as required would have excluded applications whose backends use different filter semantics (SQL, MongoDB, Firestore, OData, SmartSuite, GraphQL), which is exactly the over-specification this revision corrects.

**Fenced code blocks for multiline strings:** An earlier version of JMD included fenced code blocks (triple-backtick delimiters) as a second multiline string form alongside blockquotes. Fenced blocks were intended for raw text — code, config, logs — where Markdown interpretation should be suppressed. They were removed in v0.3 for a fundamental reason: fenced blocks are the only Markdown construct that uses matched delimiters (an opening fence and a closing fence). This directly contradicts JMD's core anti-delimiter principle — the same principle that motivates the elimination of `{}`, `[]`, and `()` throughout the format. More importantly, matched delimiters break the streaming guarantee: a parser must buffer all content between the opening and closing fence, unable to emit any events until the closing fence arrives. Every other JMD construct is a position marker — a line that self-identifies its role without reference to any future line. Fenced blocks are the sole exception, and removing them makes JMD's streaming guarantee complete and unconditional. Blockquotes handle all multiline use cases, including code and raw text. The `>` prefix on each line is a position marker, not a delimiter pair, and each line can be processed independently as it arrives.

**Emoji semantics:** Unicode emoji characters (🚀, ✅, ❌) and Markdown-style emoji shortcodes (`:rocket:`, `:white_check_mark:`) are valid string content in JMD. Both forms pass through the parser unmodified — the parser does not convert shortcodes to Unicode or vice versa. JMD assigns no syntactic meaning to emojis; they are transparent data. If a receiving system wants to render `:rocket:` as 🚀 or interpret ✅ as a boolean status, that is application-level logic outside the JMD specification. This is consistent with JMD's general rule that Markdown rendering is not applied to string content (Section 22.2).

**Native date/time types:** JSON has no date type; ISO 8601 strings are the established convention. JMD inherits this: `created: 2024-03-08T14:30:00Z` is parsed as an unambiguous string. Adding a typed date sigil would solve a problem that tooling already handles at the application layer.

**Binary data:** Out of scope for a text-based format. Base64 strings are the appropriate fallback where binary data must be represented. See Appendix A.2.8 for recommended encoding conventions (Base64 inline, `sha256:` hash reference).

**References and anchors:** YAML's anchor/alias mechanism adds parsing complexity and is rarely needed in LLM-generated output. JMD prefers explicit repetition over implicit reference.

**Linked data and cross-document references (JSON-LD style):** Formal link semantics between documents — typed resource references, URI resolution, RDF-style predicates — are explicitly out of scope. An entity-reference convention (`->`) is available in Appendix A.2.6 as a lightweight, application-level semantic hint for declaring that a field references another entity. Full JSON-LD-style semantics (RDF triples, `@context`, URI expansion) would impose a conceptual framework that adds complexity without benefit for the primary use case of LLM-to-system communication.

**Streaming aggregation / reactive queries:** Interesting, but a concern for runtime implementations rather than the data format itself.

**Conditional delete (delete by filter):** A `#-` document with QBE-style filter conditions — analogous to SQL `DELETE WHERE` — was considered and rejected. The argument for it is efficiency: a single document instead of a query–delete roundtrip. The argument against it is more fundamental: conditional delete is not LLM-native. LLM agents operating on data naturally verify before destroying — they query first (`#?`), inspect the result set, then issue a `#- []` with the resolved identifiers. This two-step pattern is both safer (the agent sees what it will delete before the destructive action) and aligned with how models trained on agentic workflows reason about irreversible operations. A format that enables one-shot conditional delete without a verification step would work against this natural behavior rather than with it. The two-step workflow also composes cleanly with JMD's existing primitives and requires no new syntax.

---

## 21. Design Rationale

**Why not YAML?** YAML is conceptually similar but carries significant complexity: multiple quoting styles, anchors, aliases, block/flow duality, and a notoriously difficult-to-implement spec. JMD is intentionally minimal.

**Why Markdown headings for hierarchy?** Headings create clear document structure that LLMs are extensively trained on. The Markdown section model — where a heading governs all following content until the next same-or-higher-level heading — is one of the most deeply internalized patterns in LLM training data. JMD uses this exact semantic: heading depth = data depth.

**Why heading-scope instead of indentation?** Indentation-based nesting has three problems in an LLM-native context: (1) LLMs do not reliably count or track whitespace depth, making deep indentation error-prone. (2) Whitespace is invisible and fragile — corrupted by editors, copy-paste, and transmission pipelines. (3) Repeated space characters waste tokens. Heading depth is explicit, robust, and consumes fewer tokens than equivalent indentation. It also aligns with how LLMs naturally structure Markdown documents.

**Why bare fields within scope?** After a heading establishes a scope, every field within that scope belongs to it — just as paragraphs under a heading belong to that section in a Markdown document. Requiring a heading prefix on every field would be redundant and token-wasteful. Bare fields are both more efficient and more natural for LLM generation.

**Why `### []` for sub-arrays?** An alternative syntax `-[]` would rely on indentation to distinguish nesting levels of sub-arrays. In the heading-scope model, sub-arrays use `### []` (anonymous sub-array heading) where heading depth indicates nesting level. This is consistent with the heading-scope principle and unambiguous without indentation.

**Why indented continuation for object items?** In Markdown, list items with multiple lines use indentation to signal continuation: the first line starts with `- `, and subsequent indented lines belong to the same item. This is the standard Markdown list continuation pattern, deeply internalized by LLMs from training on documentation, changelogs, and README files. Live testing confirms this: when asked to produce structured array data in Markdown, LLMs naturally write `- first_field: value` followed by indented `field: value` lines — they never produce comma-separated inline fields unprompted. An earlier JMD design used comma-separated inline fields (`- sku: A1, qty: 2, price: 29.99`), but this was replaced because it violated the AI Whisperer principle: the design forced LLMs to learn a convention they would never produce naturally. The indentation-based continuation pattern is not hierarchy-encoding — it means only "this field belongs to the current `- ` item." All hierarchy is still expressed exclusively through heading depth. The indentation level is not significant beyond "2+ spaces"; the parser does not track or enforce consistent depth.

**Why `## -` for depth-qualified items?** When a bare `-` would be ambiguous (because multiple array scopes are open at different depths), a heading-prefixed `-` explicitly selects the array at the target depth. This naturally extends the heading-scope model to array items and requires no new syntax — only the combination of an existing heading prefix with the existing `-` item marker.

**Why blank lines reset scope to root?** The core design philosophy of JMD is to align the format with how LLMs naturally generate text, rather than imposing rules the model must learn. LLMs trained on Markdown have deeply internalized the convention that blank lines separate top-level sections. When an LLM finishes generating a nested block (e.g. an address object) and moves on to a different top-level concern, it naturally produces a blank line — not because it was instructed to, but because that is the structural pattern embedded in its training data. Making blank lines semantically significant formalizes this existing behavior. The alternative — treating blank lines as cosmetic — would create a latent error class: a generator that inserts a blank line after a nested block "intends" to return to root scope, but the format would silently ignore this intent and keep subsequent bare fields in the nested scope. This is exactly the kind of silent data corruption that JMD's design is meant to prevent. The choice of "return to root" (rather than "return one level up") matches the dominant Markdown pattern, where blank lines separate major sections rather than performing incremental scope adjustments. It is also the simpler, more predictable rule for both generators and parsers.

**Why `[]` sigil?** It directly mirrors JSON array notation and is unambiguous in the context of a heading or key name.

**Why blockquotes as the sole multiline syntax?** An LLM asked to embed text in a Markdown document will instinctively use a blockquote — it is the native Markdown construct for quoted or embedded prose. Live testing across three major LLMs confirms this: a minimal hint ("use blockquotes for multiline text") triggers the exact `>` prefix pattern without further instruction. JMD adopts blockquotes rather than inventing a new multiline syntax (continuation markers, block literals, or indentation-based blocks), because the design goal is to formalize what LLMs already do. An earlier version also included fenced code blocks (triple backticks), but these were removed because they are the only Markdown construct with matched delimiters — an opening fence that requires a closing fence. This contradicts JMD's anti-delimiter principle and, critically, breaks the streaming guarantee: a parser must buffer until the closing fence arrives. Blockquotes have no such limitation. Each `>` line is a position marker — it self-identifies as multiline content without reference to any future line. The block ends at the first line not starting with `>`. This makes blockquotes structurally identical to every other JMD construct: every completed line advances the parse state independently. Removing fenced blocks gives JMD a complete, unconditional streaming guarantee with no exceptions.

**Why frontmatter for document metadata?** Transport-level metadata — pagination parameters, format version, schema references — is structurally distinct from the data payload. Embedding it in the heading line (`#? Order page: 1, size: 50`) would overload the heading with mixed concerns and deviate from how headings work in Markdown (short labels, not parameter lists). Frontmatter — fields before the first heading — is the more LLM-native pattern: LLMs naturally write preamble information before the main content, and the syntax is identical to regular JMD fields. No new construct is required. The parser simply treats `key: value` lines before the first `#` heading as metadata rather than data. This mirrors the YAML frontmatter convention (`---` delimited metadata blocks) that LLMs know well from static site generators, documentation tools, and CMS systems — but without introducing a foreign syntax. JMD frontmatter is just JMD.

**Why QBE for queries?** QBE is not a query language — it is a domain reduction mechanism. Its purpose is to narrow a potentially large result set to a size that fits the LLM's context window. The LLM then performs precise filtering, sorting, aggregation, and transformation as reasoning steps on the reduced set. This distinction is fundamental: a query language must be complete and exact (every expressible query must return exactly the right rows); a domain reduction mechanism only needs to be *sufficient* (the result set must be small enough and must contain the relevant data). This dramatically lowers the bar for what QBE syntax must express. The LLM does not need `ORDER BY` because it can sort. It does not need `GROUP BY` because it can aggregate. It does not need subqueries because it can issue sequential calls. QBE handles the one thing the LLM cannot do for itself: tell the server which subset of data to transmit.

**Why no JMD-normative sub-language for filter and type expressions?** Queries and schemas are both cases where a field value carries a *sub-language expression* (a filter condition, a type specifier) rather than a plain data value. The temptation is to formalize the sub-language in the JMD spec and require parsers to return a structured representation. Earlier drafts did this in §13 and §14, with EBNF grammars and prescribed vocabularies. This was wrong for three compounding reasons: (1) *Applications have genuinely different needs.* A SmartSuite adapter, a TypeScript codegen, a SQL adapter, and an OData bridge each require a different filter and type representation to map cleanly to their target backend — no single spec-mandated AST can serve all of them without imposing conversion overhead on every consumer. (2) *We cannot anticipate future needs.* The set of applications that will consume JMD is unbounded. A frozen AST shape excludes every application whose requirements were not foreseen at spec-authorship time — a prognosis the spec has no business making. (3) *Token inflation defeats JMD's own purpose.* A structured AST for `total: > 50` inflates from ~10 characters to ~70 characters in serialized form, directly contradicting JMD's token-efficiency mandate; and LLMs naturally write the string form, not the AST form, so the AST is a layer of *added* translation cost with no originating benefit. The correct layering is: JMD delivers the document structure and string contents; the application interprets the sub-language strings per its own needs. Common conventions for both QBE and schema are collected non-normatively in Appendix A.

**Why regex autodetection was removed (v0.3.2).** The earlier §13.3 specified: *a value containing regex metacharacters (`|`, `.`, `*`, `+`, `?`, `^`, `$`, `[`, `]`, `(`, `)`, `\`) is interpreted as a regex pattern.* A common LLM input like `name: Max.Mustermann` (a personal name with a literal dot) would silently become a regex where the dot matches any character, producing surprise matches. The autodetection rule failed the AI-Whispering test: it interpreted natural LLM output against the LLM's actual intent. v0.3.2 removes this mechanism entirely — not only from the normative spec but also as a recommended convention. Applications that need regex-based filters SHOULD signal regex intent explicitly (e.g., a `~re:` prefix or `/.../ `-style delimiters), not via content sniffing.

**Why free-form fields in error documents?** Error documents serve two audiences: machines (routing, retry logic, monitoring) and LLMs (understanding what went wrong and how to recover). The `status` and `code` fields serve machines; `message`, `suggestion`, and `context` serve LLMs. Like the epistemic `source` field in frontmatter, the free-form error fields carry the generator's perspective rather than a standardized vocabulary. A database server writes `suggestion: Check foreign key constraints`; an LLM-powered API writes `suggestion: The customer name looks like a typo — did you mean "Müller"?`. Prescribing the content of these fields would suppress the very information that makes them valuable. The error code vocabulary is similarly left to domain convention rather than specification mandate, because error taxonomies are inherently domain-specific and will converge through usage patterns rather than top-down standardization.

**Why no comments?** JMD deliberately omits comments. Every other JMD construct maps bijectively to JSON; comments would be the sole exception — silently discarded during serialization, invisible in the JSON roundtrip, yet adding parser complexity at every grammar level. JMD's primary audience is LLMs, which read all tokens and gain nothing from out-of-band annotations. Where metadata about data is valuable, it belongs in a data field (`_note: ...`) that survives serialization. See Section 18 for the full rationale.

**Why is frontmatter an open extension point?** JMD's frontmatter channel carries transport-level metadata that the implementation — not the format — interprets. Different backends have fundamentally different metadata needs: a query server uses `page` and `page-size` for pagination; a database adapter uses `group` and `sum` for aggregation; an LLM generator uses `confidence` and `source` for epistemic self-assessment. Prescribing a fixed vocabulary would force every implementation to work within a common denominator that fits none of them well. An open channel lets each implementation define exactly the keys it needs, without format changes. The epistemic conventions (`confidence`, `source`, `uncertain`) are a particularly valuable example: LLMs operate with personas and have a contextual self-understanding of how they arrived at each piece of data. Providing a channel for this self-assessment — rather than suppressing it into prose — makes the metadata honest and machine-processable. But these are conventions, not format definitions. `source` is deliberately free-form: a RAG agent writes `source: vector search, 3 documents matched`; a database adapter writes `source: postgresql`; a medical assistant writes `source: clinical guidelines 2024`. The receiver interprets this contextually. Forcing diverse generator perspectives into a fixed enum would lose the very information that makes the field valuable.

**Why `#!` for schema?** The `!` sigil is conventionally associated with declarations and directives (shebang lines, YAML directives, DOCTYPE). It is visually distinct from `#?` (query) and `#` (data), making document mode immediately recognizable.

(Rationales for the specific schema-vocabulary conventions — entity references, keyword modifiers, delimiter-free enums, format hints, inline objects — were previously listed here and have been moved to Appendix A.2 alongside the conventions themselves. The meta-rationale for why no such vocabulary is normative appears above under "Why no JMD-normative sub-language for filter and type expressions?")

**Why generator-strict, parser-tolerant?** JMD is consumed by parsers but generated by LLMs. These two roles have different capabilities: a parser sees the complete text and can apply flexible rules; an LLM generates sequentially and cannot correct earlier output. Postel's Law — "be conservative in what you send, be liberal in what you accept" — is the natural conformance model for this asymmetry. A strict generator ensures interoperability; a tolerant parser ensures reliability with real LLM output. Benchmark testing confirms that tolerant parsing eliminates syntax-related failures without introducing ambiguity: anonymous headings, depth+1 array items, and cosmetic blank lines are all unambiguously parseable. The alternative — requiring LLMs to produce pixel-perfect syntax — forces retry loops, corrective prompting, and post-processing that negate JMD's latency and token advantages.

**Why no canonical form?** LLMs generate text token by token, sequentially, without the ability to retroactively reorder output. A canonical form requiring lexicographic key sorting or normalized number formatting would mean every LLM-generated JMD document needs post-processing — directly contradicting the "LLM-native" design goal. Since JMD parsing is unambiguous regardless of key order, canonicity adds no value to the primary use case and would impose an unnecessary burden on generators.

**Why line-by-line streamability?** JSON was designed for complete document exchange. Its closure-based syntax — every `{` needs a `}`, every `[` needs a `]` — makes partial documents invalid and forces receivers to buffer until the last byte arrives. This was acceptable when APIs were consumed by code that could wait. It is a structural liability when APIs are consumed by LLM agents operating in real-time pipelines. JMD's heading-based syntax makes every completed line a processable event. Token efficiency and streamability are co-equal design goals that reinforce each other: the same heading-based syntax that eliminates delimiter tokens also eliminates the need for closing delimiters, making every completed line independently parseable. Neither property was designed in service of the other — both are first-class consequences of the choice to encode hierarchy through position rather than through matched delimiters.

### 21.1 Known Properties and Trade-offs

The following properties of the heading-scope model are inherent to the design. They are documented here as conscious trade-offs, not as oversights or planned improvements. We believe each trade-off is correctly balanced for JMD's primary use cases — but we recognize that real-world adoption may reveal scenarios we have not anticipated. Community feedback on these trade-offs is explicitly invited: if your use case hits one of these edges hard, we want to hear about it.

**Heading depth at deep nesting levels.** At nesting depth 5, a heading is `###### key` — six `#` characters that must be counted correctly by both generators and parsers. This is more reliable than counting 10 spaces of indentation (the equivalent in an indentation-based format), because `#` characters are visually distinct, tokenized individually, and unambiguously structural. However, at extreme depths, the difference between `#####` and `######` becomes harder to distinguish for human readers and, to a lesser extent, for LLMs. In practice, this is rarely a concern: typical API payloads (REST responses, MCP tool outputs, configuration objects) rarely nest beyond depth 3–4. Deeply nested tree structures (ASTs, recursive graphs) exist but represent a minority of the target use cases for JMD. For these edge cases, the heading model remains correct and parseable — it is merely less visually comfortable than at shallow depths.

**Depth-qualified array items (`## -`) are necessary for nested arrays.** When an array of objects contains nested sub-arrays, bare `-` is ambiguous: it could start a new item in the outer array or in the inner sub-array. The heading-scope model resolves this unambiguously via `## -` (or `### -`, etc.), which explicitly selects the target array by depth. This construct is compositional — it combines two patterns LLMs know well (heading prefixes and list item markers) — and it is required only in the specific case of nested arrays within array-of-objects, which is uncommon in typical payloads. Bare `-` remains sufficient for the vast majority of array usage: scalar arrays, simple object arrays, and the first item of any array before a deeper scope has been opened.

**Token efficiency varies by data shape.** The heading-scope model is optimized for **wide** structures: objects with many fields at each nesting level. In this case, the heading cost is amortized over many bare fields, and the elimination of per-field heading prefixes and indentation produces significant token savings over JSON. For **narrow, deep** structures (1–2 fields per object across many nesting levels), each level requires a heading that is more expensive than 2-space indentation would be. This trade-off is intentional: JMD targets the wide-and-shallow data shapes that dominate API responses, MCP tool outputs, and LLM-generated structured data. Narrow-and-deep structures (ASTs, deeply recursive configs) are a valid but secondary use case. The savings vs. pretty-printed JSON — the only JSON variant that LLMs can reliably produce — increase with payload size because the fixed overhead of heading markers is amortized over more bare fields. Quantitative results are provided in the companion document *JMD Efficiency Analysis*.

**The `[]` sigil on array keys is a programmatic convention, not a Markdown convention.** LLMs generating Markdown would naturally write `## tags` followed by list items, not `## tags[]`. The `[]` suffix is borrowed from programming language syntax (`int[]`, `string[]`, `items[]`), which LLMs know well from code training data — but it is not a Markdown pattern. This deviation is technically necessary: without `[]`, an empty array heading (`## tags` with no items) would be indistinguishable from an empty object heading (`## tags` with no fields), and a streaming parser could not determine in advance whether `-` items or `key: value` fields will follow. The `[]` sigil resolves both ambiguities at the cost of one non-Markdown convention that LLMs must learn — though one that aligns naturally with their programming language training.

**Scalar type disambiguation requires proactive quoting.** In a Markdown-native context, the intuition is "everything is text unless marked otherwise." JMD inverts this for scalar values: bare values are parsed as `null`, `true`, `false`, or number first, and fall back to string only if none match. This means a zip code written as `zip: 10115` is parsed as the number `10115`, not the string `"10115"`. The correct form is `zip: "10115"`. LLMs are familiar with quoting from JSON training data, but in a Markdown-like format, the expectation that bare text might be reinterpreted as a non-string type is a learned requirement. This is not a JMD-specific problem — it is inherent to any untyped format that supports multiple scalar types (YAML has the same issue, notably with `NO` → `false`). JMD's disambiguation order (Section 2.1) is deterministic and simple, and the escape hatch — quoting — is always safe.

---

## 22. Conformance Requirements

### 22.1 The Robustness Principle

JMD is an **asymmetric format**: the primary generator is an LLM, the primary consumer is a parser. These two roles have fundamentally different capabilities and failure modes. A generator (LLM) produces text sequentially and cannot retroactively correct earlier output. A parser has full access to the completed text and can apply flexible interpretation rules.

JMD therefore adopts Postel's Law as a core design principle:

> **Be conservative in what you generate, be liberal in what you accept.**

This is not a loose guideline — it is a formal conformance requirement. JMD defines two conformance levels:

**Generator conformance (strict).** A conforming JMD generator (serializer, LLM primer, code emitter) MUST produce output that matches the canonical grammar defined in Section 11. Specifically:

- Root headings MUST include a label (e.g., `# Order`, not bare `#` followed by a space)
- Root markers `#?`, `#!`, and `#-` MUST be followed by a space and a label
- Array items SHOULD use bare `-` when unambiguous; a thematic break (`---`) MUST be emitted between items that contain nested sub-structures (Section 8.6); depth-qualified items (`## -`) MAY be used as an alternative
- Blank lines SHOULD be used intentionally for scope reset, not inserted arbitrarily
- Keys and values MUST be correctly quoted per Sections 4.2 and 6
- Scalar values (bare or quoted) SHOULD NOT contain inline Markdown formatting (`**bold**`, `*italic*`, `` `code` ``, `[text](url)`, `~~strike~~`); rich-text content belongs in the blockquote multiline form (Sections 5.1, 9.1)

Strict generation ensures maximum interoperability and minimizes the parsing effort for consumers.

**Parser conformance (tolerant).** A conforming JMD parser MUST accept all documents that a strict generator would produce, and additionally MUST accept the following variations that LLMs naturally produce:

- **Anonymous headings** (Section 3.2a): headings with empty labels at any depth
- **Thematic breaks** (Section 8.6): `---` as item separator in arrays with nested sub-structures
- **Depth-qualified array items** (Section 8.6a): `## -` as an alternative to thematic breaks for starting new items in outer arrays
- **Depth+1 array items** (Section 8.6b): items written one heading level deeper than the array heading, even when bare `-` would be unambiguous
- **Cosmetic blank lines before headings**: blank lines followed by a heading have no additional effect beyond the heading's own scope semantics
- **Cosmetic blank lines between array items**: blank lines followed by `-` within an array body are visual separators, not scope resets

A parser MAY reject input that is structurally invalid (e.g., a `-` line outside any array scope), but MUST NOT reject input solely because it uses a tolerant variation listed above. Note that bare fields before the first heading are valid frontmatter (Section 3.5), not structural errors.

**Rationale.** This asymmetry is not a workaround — it is the central design insight for LLM-native formats. LLMs generate text based on deeply internalized patterns from training data. When an LLM writes a bare `#` heading without a label, or uses `## -` for an item that could be bare `-`, it is not making an error — it is following the Markdown conventions it has internalized. A format that rejects this output forces every LLM interaction to include corrective prompting, retry loops, or post-processing. A format that accepts it natively achieves 100% reliability on syntactically reasonable LLM output. Benchmark testing across multiple scenarios confirms that parser-tolerant handling eliminates all syntax-related chain breaks without introducing any parsing ambiguity.

### 22.2 Specific Requirements

An implementation claiming **JMD v0.3** conformance must:

- Implement at least the JMD → JSON direction (parser). Implementing JSON → JMD (serializer) is recommended but not required.
- Parse any syntactically valid JMD data document to the correct JSON value, regardless of key order or number formatting variations.
- Correctly track heading depth and maintain a scope stack to determine field ownership.
- Treat blank lines as scope reset to root level, except within array bodies where a blank line followed by `-` is cosmetic.
- Support bare fields within scope and scalar headings for scope return.
- Support anonymous headings with empty labels (Section 3.2a).
- Support thematic breaks (`---`) as array item separators for arrays with nested sub-structures (Section 8.6).
- Support depth-qualified array items (`## -`, `### -`, etc.) as an alternative to thematic breaks (Section 8.6a), including depth+1 items as described in Section 8.6b.
- Support anonymous sub-array headings (`### []`, `#### []`, etc.).
- Support multiline string values in blockquote form (Section 9).
- Support document frontmatter: fields before the first heading are document-level metadata, not serialized into JSON (Section 3.5). Unknown frontmatter fields MUST be preserved in the parsed frontmatter map and surfaced to the application layer. The parser MUST NOT reject them, and MUST NOT drop them before the application can inspect them. Silent drop at the parser layer is non-conformant; the decision whether to silently tolerate, echo, or reject an unknown frontmatter key belongs to the application layer (Section 3.5).
- Recognize all four document modes: `#` (data), `#?` (query), `#!` (schema), `#-` (delete). The `#-` root marker MUST be parsed as a depth-1 heading with mode prefix `-` (Section 15).
- Parse `#-` delete, `#?` query, and `#!` schema documents using the same syntax rules as data documents — the body is a standard JMD object or array. Values in query and schema documents MUST be returned as raw strings (parsed per §2.1 and §5); the parser MUST NOT attempt structured interpretation of filter or type expressions (Sections 13, 14).
- Return every parsed document as the canonical envelope `{mode, label, frontmatter, value}` (Section 3.6). Frontmatter is always present as an object (empty `{}` when no frontmatter fields are present). The label has the mode-mark and any trailing `[]` sigil stripped.
- Reject structurally invalid input with a clear error indicating the offending line. Tolerant variations (Section 22.1) are NOT structurally invalid.
- Reject prose in the document body with a parse error (§3.6.2). A bare line that is not a key-value field, indented continuation, bullet (`-`), blockquote (`>`), heading, or thematic break (`---`) is invalid JMD and MUST NOT be silently dropped or returned as an empty value.
- Not apply Markdown rendering to string content; only JSON string escaping rules apply. (Note: inline Markdown in blockquote multiline values is preserved as literal text in the parsed string, not rendered.)

Recommended test cases:

- **Anonymous headings:** root heading with empty label, nested heading with empty label (Section 3.2a)
- **Strings with escapes:** `\"`, `\\`, `\n`, `\t`, `\uXXXX`, and literal backslash in bare strings
- **Empty structures:** empty root object, empty root array, empty nested object, empty nested array
- **Deep nesting:** objects nested 5+ levels using heading depth
- **Scope return via scalar heading:** scalar heading at shallower depth after deep nesting
- **Scope return via blank line:** blank line after nested block, followed by bare fields at root
- **Blank line before heading:** cosmetic blank line before `##` heading must not alter semantics
- **Blank line within array:** blank line between `-` items within array body must be cosmetic
- **Blank line ending array:** blank line followed by bare field (not `-`) must close the array scope
- **Object item with first field:** `- sku: A1` followed by indented `qty: 2` on next line
- **Object vs. scalar disambiguation:** `- "name: Alice"` as scalar string vs. `- name: Alice` as object
- **Indented continuation fields:** `- sku: A1` followed by `  qty: 2` and `  price: 29.99` on indented lines
- **Indentation depth insignificant:** 2 spaces, 4 spaces, and mixed indentation all parsed as continuation fields
- **Depth+1 array items:** `## - name: Widget` for items in a `# products[]` array, even without nesting ambiguity (Section 8.6b)
- **Frontmatter (request):** `page: 1` and `page-size: 50` before `#? Order` heading are parsed as metadata, not serialized into JSON
- **Frontmatter (response):** `total: 4832`, `page: 1`, `pages: 97`, `page-size: 50` before `# Orders` heading are parsed as response metadata, not as body fields of the Orders document
- **Frontmatter with bare key:** `count` before `#? Order` heading is a valid bare frontmatter field
- **No frontmatter:** document starting directly with `# Order` has no frontmatter (common case)
- **Unknown frontmatter key preserved:** `dry-run: true` before `#- Order` heading is a valid frontmatter field and MUST be present in the parser output — a parser that drops it before the application layer sees it is non-conformant (Section 3.5, §22.2)
- **Unknown frontmatter key preserved with bare value:** `verbose` (bare key, no value) before `# Order` is preserved in the frontmatter map as `{"verbose": true}` and surfaced to the application layer
- **Application-layer strict refusal is conformant:** an application that rejects a delete operation carrying an unrecognized directive key (e.g. `dry-run: true` on `#- Order`) with a `# Error` response is spec-conformant — the parser accepted the key, the application declined to act on it (Section 3.5)
- **Ignored-keys echo (short form):** a response carrying `ignored-keys: foo, bar` before the root heading is a valid observable-tolerance response
- **Ignored-keys echo (long form):** a response carrying `## ignored-keys[]` with `- foo` and `- bar` items before the root heading is equally valid (Section 23.7)
- **Thematic break separator:** `---` between items of an array with nested sub-structures (Section 8.6)
- **Thematic break roundtrip:** serialize array of objects with nested lists, parse back, verify lossless
- **Thematic break with blank lines:** `---` preceded and followed by blank lines is correctly parsed
- **Thematic break in nested array:** `---` does not affect inner scalar arrays (e.g., Members array breaks before `---`)
- **No thematic break for flat arrays:** serializer does not emit `---` between items of flat object arrays
- **Depth-qualified items with first field:** `## - name: B` after nested arrays (backward compatibility, Section 8.6a)
- **Depth-qualified items:** `## -` after nested arrays within array-of-objects (backward compatibility)
- **Anonymous sub-arrays:** `### []` within `## matrix[]`
- **Heterogeneous arrays:** mixed scalars, objects, and nested arrays in a single array
- **Numeric edge cases:** `0`, `-0`, `1e10`, `1E10`, `-2.5e-3`, `3.14`
- **Strings with newlines:** quoted strings containing `\n`, `\t`, and other escape sequences
- **Key order independence:** same keys in different order must parse to equal JSON values
- **Bare fields vs. heading fields:** both forms producing identical JSON output
- **Multiline blockquote:** `key:` followed by `>` lines, parsed as single string with `\n` separators
- **Multiline blockquote with paragraph break:** `>` line containing only `>` produces blank line in value
- **Multiline blockquote termination:** first non-`>` line ends the blockquote value
- **Multiline mixed with scope:** blockquote value followed by blank line resets scope to root
- **Single-line escape form:** `key: "line 1\nline 2"` remains valid for inline multiline
- **Inline Markdown in bare scalar (parser tolerance):** `title: The **Ultimate** Laptop Stand` parses as the literal string `"The **Ultimate** Laptop Stand"` — the parser does not render or strip the `**` markers (Section 5.1)
- **Inline Markdown in quoted scalar (parser tolerance):** `"note": "See *docs*"` parses as the literal string `"See *docs*"` — the parser does not interpret the `*` markers
- **Inline Markdown in blockquote (preserved verbatim):** `>` lines containing `**bold**`, `` `code` ``, `[link](url)` are preserved byte-for-byte in the parsed string value
- **Incidental metacharacters in scalar values:** `rate: 2 * x`, `expr: **ptr`, `regex: ^[a-z]+$`, and `url: https://example.com/*` are valid scalar data and MUST be accepted by the parser — only the `# ` and `- ` structural prefixes trigger mandatory quoting (Section 6)
- **Filter-like prefixes in data scalars:** `deleted: !true`, `note: > urgent`, `search: ~berlin`, `status: >= 5` in a data document (`#`) are valid scalar strings — the values are `"!true"`, `"> urgent"`, `"~berlin"`, `">= 5"` respectively; the `!`, `>`, `~` characters have no JMD-normative meaning in scalar position
- **Envelope shape for data:** `# Order\nid: 42` returns `{mode: "data", label: "Order", frontmatter: {}, value: {id: 42}}` (§3.6)
- **Envelope shape for schema:** `#! Order\nid: integer` returns `{mode: "schema", label: "Order", frontmatter: {}, value: {id: "integer"}}` — the `#!` mode-mark is in `mode`, not `label`
- **Envelope shape for delete bulk:** `#- []\n- 42\n- 43` returns `{mode: "delete", label: "", frontmatter: {}, value: [42, 43]}` — anonymous bulk delete yields `label: ""` (both the mode-mark and the `[]` sigil are stripped)
- **Envelope shape with frontmatter:** `page: 1\n\n#? Order\nstatus: pending` returns `{mode: "query", label: "Order", frontmatter: {page: 1}, value: {status: "pending"}}`
- **Prose body rejected:** `# Answer\n\n42\n` MUST produce a parse error — the bare line `42` is prose, not a JMD field; silently returning `{}` is non-conformant (§3.6.2)
- **Whitespace-only body accepted:** `# Order\n\n` returns `value: {}` — whitespace and blank lines without non-structural content are not prose and are parsed as empty body
- **Schema document — values are raw strings:** `#! Order` with `id: integer` returns `value: {"id": "integer"}` — the value is the literal string `"integer"`, not a type object; the parser does not interpret schema vocabulary (Section 14, Appendix A.2)
- **Schema document — entity reference is opaque:** `customer: -> Customer` returns `value: {"customer": "-> Customer"}` — parser preserves the arrow-and-label string verbatim
- **Schema document — inline object expression is opaque:** `address: object(street: string, city: string)` returns the full parenthetical expression as a single string value, not a parsed inner schema
- **Frontmatter key-value:** `confidence: high` and `source: database` before `# Customer` are parsed as frontmatter metadata, not serialized into JSON
- **Frontmatter bare string:** `uncertain: zip, phone` in frontmatter is a valid bare string frontmatter field
- **Frontmatter absent:** document without frontmatter fields carries no metadata (common case)
- **Error document minimal:** `# Error` with `status: 404` and `code: not_found` is a valid error document
- **Error document with free-form fields:** `suggestion` and `context` are parsed as regular bare string fields
- **Error document with errors array:** `## errors[]` with `- field: x` + indented `reason: y`, `value: z` parsed correctly
- **Streaming error:** `# Error` after partial data document closes all open scopes
- **Query document — values are raw strings:** `#? Order` with `total: > 50` returns `value: {"total": "> 50"}` — the value is the literal string `"> 50"`, not a parsed comparison; the parser does not interpret filter vocabulary (Section 13, Appendix A.1)
- **Query document — projection marker is opaque:** `email: ?` returns `value: {"email": "?"}` — the `?` is a literal string value, not a parsed projection
- **Query mode detection:** `#?` root marker is recognized; envelope reports `mode: "query"`, `label: "Order"`, with values as raw strings
- **Delete document single:** `#- Order` with `id: 42` parsed as object `{'id': 42}` with delete mode detected
- **Delete document bulk:** `#- []` with scalar items parsed as list of identifiers with delete mode detected
- **Delete document composite key:** `#- []` with object items (`- table: orders` + indented `id: 42`) parsed correctly
- **Delete root marker:** `#-` recognized as depth-1 heading with mode prefix `-`, label extracted correctly
- **Delete body syntax:** `#- Order` body uses identical syntax rules as `# Order` data document (fields, nested objects, blockquotes)

---

## 23. Frontmatter Conventions

Section 3.5 defines frontmatter as an **open extension point**: any `key: value` lines before the root heading are document-level metadata, and unknown frontmatter keys MUST be preserved by the parser and passed through to the application layer (never silently dropped). This openness allows implementations to add query parameters, result metadata, and operational hints without modifying the JMD grammar.

The following conventions standardize the most widely useful frontmatter keys. An implementation that supports these features SHOULD use these names to ensure interoperability and familiar behaviour for LLM agents that have learned the conventions from one server and encounter another.

These are **recommendations** (RFC 2119 SHOULD), not requirements (MUST). An implementation MAY use different keys for proprietary extensions, but SHOULD document the deviation and SHOULD NOT reuse the conventional key names with incompatible semantics.

### 23.1 Pagination

Pagination applies to any document type that may return a large result set. The request keys `page-size:` and `page:` MAY be used with `#` (data), `#?` (query), and `#!` (schema) documents whenever the server supports paged responses.

**Request frontmatter:**

| Key | Type | Meaning |
| --- | --- | --- |
| `page-size` | integer | Maximum number of records per page. Default is implementation-defined. |
| `page` | integer | 1-based page number to return. Omitting `page` implies page 1. |

```markdown
page-size: 50
page: 3

#? Orders
status: active
```

**Response frontmatter:**

The server SHOULD echo pagination metadata before the root heading of the response document, providing the consumer with result-set information before the first data record arrives (streaming guarantee — see Section 16).

| Key | Type | Meaning |
| --- | --- | --- |
| `total` | integer | Total number of records matching the query (across all pages). |
| `page` | integer | The page number returned. |
| `pages` | integer | Total number of pages at the requested `page-size`. |
| `page-size` | integer | The effective page size used (may differ from requested `page-size` if the implementation imposes limits). |

```markdown
total: 830
page: 3
pages: 17
page-size: 50

# Orders
## data[]
- OrderID: 10358
  ...
```

**Why `page-size` and not `size` or `limit`?** Frontmatter is an open extension point — any implementation may define keys for its own needs. Generic names like `size` or `limit` carry no inherent binding to pagination: `size` could equally mean maximum response size in bytes, maximum expand depth, or maximum error count; `limit` is similarly overloaded across rate limiting, result caps, and resource quotas. A key that could mean anything is ambiguous at best and, at worst, blocks future conventions from using the same name for a legitimately different purpose. The name `page-size` is self-documenting and context-bound: it can only mean the number of records per page. This is consistent with JMD's broader naming philosophy — preferring readable, unambiguous identifiers over terse ones (cf. `optional` instead of `?`, `readonly` instead of a sigil in §10).

### 23.2 Count Mode

Count mode is a variant of a query request that returns only the number of matching records, without transmitting the record data itself. It is expressed as a single frontmatter key.

**Request frontmatter:**

| Key | Type | Meaning |
| --- | --- | --- |
| `count` | boolean | If `true`, return only the match count; omit record data. |

```markdown
count: true

#? Orders
status: pending
```

**Response document:**

When `count: true` is requested, the response SHOULD carry `count` as frontmatter — before the root heading — consistent with all other response metadata:

```markdown
count: 142

# Orders
```

### 23.3 Field Projection

Field projection restricts which columns or properties are included in the response. This reduces response size and keeps context windows focused on the fields the caller actually needs.

**Request frontmatter:**

| Key | Type | Meaning |
| --- | --- | --- |
| `select` | string | Comma-separated list of field names to include in each returned record. |

```markdown
select: OrderID, CustomerID, OrderDate
page-size: 50

#? Orders
```

When `select` is present, each returned record SHOULD contain only the listed fields. Fields absent from the list SHOULD be omitted from the response. The projection applies to the record body; frontmatter and metadata fields are unaffected.

If a listed field does not exist in the underlying data, the implementation SHOULD silently omit it rather than returning an error, unless the implementation has a schema that makes the missing field clearly a caller mistake.

### 23.4 Result Ordering

Result ordering controls the sort sequence of returned records.

**Request frontmatter:**

| Key | Type | Meaning |
| --- | --- | --- |
| `sort` | string | Comma-separated list of `<field> [asc\|desc]` clauses. Direction defaults to `asc`. |

```markdown
sort: OrderDate desc, CustomerID asc
page-size: 50

#? Orders
```

Multiple sort columns are listed in priority order (primary sort first). The `asc` direction keyword MAY be omitted; `desc` MUST be explicit.

```markdown
sort: total desc

#? Orders
```

### 23.5 Linked Record Expansion

When a document contains fields that reference other records (see Section 20, entity references), the caller MAY request inline resolution of those references using the `expand` frontmatter key.

**Request frontmatter:**

| Key | Type | Meaning |
| --- | --- | --- |
| `expand` | string | Comma-separated list of field names whose linked records should be resolved inline. |

```markdown
expand: Customer, Employee

#? Orders
status: active
```

Without `expand`, a linked field contains only the reference identifier (bare ID, URI, or other key). With `expand`, the server SHOULD replace the identifier with the full linked record, embedded as a nested JMD object under the field heading.

Expansion is one level deep by default. Use `depth` (Section 23.6) to control recursion.

### 23.6 Expansion Depth

When `expand` is requested, the server expands one level of links by default. The `depth` key controls how many levels of linked records are resolved recursively.

**Request frontmatter:**

| Key | Type | Meaning |
| --- | --- | --- |
| `depth` | integer | Number of link levels to expand. `1` = direct links only (default). `2` = direct links and their links, etc. |

```markdown
expand: Customer
depth: 2

#? Orders
```

Implementations SHOULD enforce a reasonable maximum depth to prevent runaway recursion on circular or deeply connected schemas. A server MAY silently cap `depth` at its maximum supported value rather than returning an error.

### 23.7 Ignored Key Echo

When an application chooses to tolerate unknown directive frontmatter keys (rather than reject them with a structured error), it SHOULD echo the ignored keys in the response frontmatter under the key `ignored-keys`. This makes tolerance *observable*: a sender that included a typo, an unsupported modifier, or a key from a newer spec version can detect the drop without having to compare state before and after the operation.

**Response frontmatter:**

| Key | Type | Meaning |
| --- | --- | --- |
| `ignored-keys` | string or array | Comma-separated list, or array, of frontmatter keys received by the application and not acted on. |

**Short form** (few keys, inline list):

```markdown
ignored-keys: dry-run, limit

# Result
...
```

**Long form** (many keys or programmatic consumption):

```markdown
## ignored-keys[]
- dry-run
- limit
- group_by

# Result
...
```

Either form is valid. A consumer SHOULD accept both.

**Interaction with destructive operations.** Applications performing destructive operations (`#-` delete, schema drop, and similar) MAY instead reject unknown directive keys with a structured error document (Section 17) rather than echo them. This choice is per-operation, not per-server: a server MAY use observable tolerance for reads and strict refusal for deletes within the same session. The selection of policy is a domain decision — the spec does not mandate one policy per operation type. The conventional mapping is:

| Operation | Typical policy |
| --- | --- |
| `#` data read / response | Observable tolerance |
| `#?` query | Observable tolerance |
| `#` data write | Observable tolerance |
| `#!` schema read / publish | Observable tolerance |
| `#-` delete | Strict refusal |
| Destructive admin operations (drop, truncate) | Strict refusal |

**Rationale.** Silent tolerance is useful for forward-compatibility (descriptive keys such as `source`, `confidence`, `author`). But for directive keys, silent tolerance creates a safety hazard: the sender communicates an intention, the receiver discards it, and the outcome looks like success. Echoing ignored keys restores visibility without sacrificing tolerance — the operation still succeeds, but the sender learns that a key was not acted on. For destructive operations, visibility alone is insufficient; the sender must be *prevented* from issuing an operation whose directives the server does not honor, and strict refusal at the application layer is the correct response. Both tiers are compatible with parser tolerance: the parser accepted the input in every case, the application made the semantic decision.

### 23.8 Conventions Summary

| Key | Direction | Meaning |
| --- | --- | --- |
| `page-size` | request | Records per page |
| `page` | request | 1-based page number |
| `count` | request | Return match count only (boolean `true`) |
| `select` | request | Comma-separated list of fields to include |
| `sort` | request | Comma-separated sort specification |
| `expand` | request | Comma-separated list of linked fields to resolve inline |
| `depth` | request | Expansion depth for linked records (default: 1) |
| `total` | response | Total matching records across all pages |
| `page` | response | Page number returned |
| `pages` | response | Total page count |
| `page-size` | response | Effective page size |
| `ignored-keys` | response | Frontmatter keys received by the application and not acted on (Section 23.7) |

All request keys appear before the root heading. All response keys appear before the root heading. Unknown keys in either direction MUST be preserved by the parser and passed to the application layer (Section 3.5); the application then chooses silent tolerance, observable tolerance (Section 23.7), or strict refusal based on the operation's destructiveness.

---

## Appendix A — Recommended Conventions (Non-Normative)

This appendix collects conventions for query and schema documents that JMD implementations MAY adopt. These conventions describe one reasonable dialect for common use cases, but JMD itself does not mandate them: an application that defines its own filter semantics, type system, or expression syntax is fully conformant as long as the structural grammar (§3–§9) is respected.

Earlier revisions of this specification (through v0.3.1) placed the content of this appendix in normative sections §13 and §14. In v0.3.2 the normative prescription was withdrawn, because the applications that use JMD have genuinely different needs — any single dialect frozen into the spec would exclude valid applications whose backends use different semantics. The conventions are preserved here, without normative force, for three reasons: (1) they are still useful defaults for applications without specific requirements; (2) they document a dialect that existing JMD tooling understands; (3) they provide a shared vocabulary that LLM-generated content can target when no application-specific dialect has been specified.

Everything in this appendix is **RECOMMENDED** (RFC 2119 SHOULD), never **REQUIRED** (MUST). Applications MAY adopt, extend, replace, or ignore any part of it. An application that adopts a non-standard dialect SHOULD document the deviation in its own interface documentation.

### A.1 Query Conventions

These conventions describe a minimal filter dialect suitable as a default for query documents (`#? Label`). They cover equality, comparisons, substring matching, negation, projection, and array-existence semantics. The filter syntax deliberately uses constructs LLMs know from SQL, code, and regex training — with one explicit exception noted below.

#### A.1.1 Equality

A bare value after a key is an equality filter:

```markdown
#? Order
status: pending
city: Berlin
active: true
```

Matches orders where `status = "pending"` AND `city = "Berlin"` AND `active = true`.

#### A.1.2 Comparison Operators

A value prefixed with `>`, `>=`, `<`, or `<=` is a numeric or date comparison. Optional whitespace between the operator and the value is permitted (`> 50` and `>50` are both valid):

```markdown
total: > 50
qty: >= 10
price: < 100.00
created: >= 2026-01-01
```

#### A.1.3 Substring (Contains)

A value prefixed with `~` is a case-insensitive substring match:

```markdown
name: ~Corp
city: ~berlin
notes: ~urgent
```

`~Corp` matches any value whose lowercase form contains `"corp"`.

#### A.1.4 Negation

A value prefixed with `!` negates the condition that follows:

```markdown
deleted: !true
status: !cancelled
name: !~Corp
```

`!~Corp` composes negation with contains.

#### A.1.5 Projection

A literal `?` as the value means *return this field but apply no filter*:

```markdown
#? User
name: ?
email: ?
active: true
```

A field with value `?: ?` inside an object scope means *project all remaining fields of this object*:

```markdown
#? User
active: true
## address
city: Berlin
?: ?
```

#### A.1.6 Array EXISTS Semantics

An array in a query document is treated as an EXISTS predicate: the document matches if **at least one** array item satisfies all the sub-conditions.

```markdown
#? Order
status: pending
## items[]
- sku: ~A123
  qty: > 1
```

Matches orders with `status = "pending"` AND at least one item with `sku` containing "a123" AND `qty > 1`.

#### A.1.7 Summary Table

| Condition | Syntax | Example |
|---|---|---|
| Equality | bare value | `status: pending` |
| Greater than | `>` prefix | `total: > 50` |
| Greater or equal | `>=` prefix | `score: >= 90` |
| Less than | `<` prefix | `price: < 100` |
| Less or equal | `<=` prefix | `qty: <= 5` |
| Contains (case-insensitive) | `~` prefix | `name: ~Corp` |
| Negation | `!` prefix | `deleted: !true` |
| Negated contains | `!~` prefix | `name: !~Corp` |
| Projection | `?` | `email: ?` |
| Wildcard projection | `?: ?` | All remaining fields of an object |

#### A.1.8 Why Regex Autodetection Was Removed

Earlier revisions specified: *a value containing regex metacharacters (`|`, `.`, `*`, `+`, `?`, `^`, `$`, `[`, `]`, `(`, `)`, `\`) is interpreted as a regex pattern*. This autodetection rule has been removed entirely — not just from the normative spec, but also as a recommended convention. An LLM writing `name: Max.Mustermann` (a common personal name with a literal dot) would silently produce a regex where the dot matches any character, generating surprise matches. Content-based autodetection fails the AI-Whispering test: it interprets natural LLM output against the LLM's actual intent.

Applications that need regex-based filter semantics SHOULD signal regex intent **explicitly**, e.g. via a dedicated prefix such as `~re:pattern` or delimiters such as `/pattern/`. The specific regex signal is left to the application — different backends have different regex dialects (PCRE, POSIX, JavaScript, ECMA-262), and no single form fits all.

#### A.1.9 Rationale for the A.1 Dialect

The operator vocabulary above is a composition of patterns LLMs produce fluently from their general training — comparison operators from SQL and programming languages, substring-contains as a common pseudo-code construct, negation-as-`!` from every C-family language, and projection-as-`?` from GraphQL and partial-data conventions. None of these require QBE-specific training. The dialect is deliberately narrow: sorting, grouping, and aggregation are LLM reasoning operations performed on the reduced result set, not query constructs. QBE's role is domain reduction, not full query expression.

### A.2 Schema Conventions

These conventions describe a minimal type-expression dialect suitable as a default for schema documents (`#! Label`). They cover scalar types, modifiers, defaults, enums, format hints, entity references, inline object types, and binary-content encoding.

#### A.2.1 Scalar Type Names

| Convention | Meaning | JSON Schema equivalent |
|---|---|---|
| `string` | UTF-8 string | `{"type": "string"}` |
| `number` | JSON number (int or float) | `{"type": "number"}` |
| `integer` | Whole number | `{"type": "integer"}` |
| `boolean` | `true` or `false` | `{"type": "boolean"}` |
| `null` | Null value only | `{"type": "null"}` |
| `object` | Object with unspecified structure | `{"type": "object"}` |

#### A.2.2 Modifiers

| Modifier | Position | Meaning |
|---|---|---|
| `optional` | after the type/enum | Field may be omitted (not required) |
| `readonly` | after the type/enum | Field is read-only — must not be included in write operations |

Example:

```markdown
id: integer readonly
notes: string optional
```

#### A.2.3 Default Values

A default is declared with `= value` after the type (and before or after keyword modifiers):

```markdown
status: pending|active|shipped = pending
retries: integer = 3
```

#### A.2.4 Enum Alternation

A pipe-separated list of scalar values declares an enum. The underlying type is inferred from the values (all strings → string enum; all integers → integer enum; etc.):

```markdown
status: pending|active|shipped|cancelled
role: admin|user|guest
priority: low|medium|high|critical = medium
```

#### A.2.5 Format Hints

Format hints are semantic keywords after a base type. They describe the expected shape of the string value but are **not** validation constraints — a consumer is not required to enforce them:

| Format hint | Meaning |
|---|---|
| `email` | Email address |
| `date` | ISO 8601 date (`2026-03-12`) |
| `datetime` | ISO 8601 date-time (`2026-03-12T14:30:00Z`) |
| `uri` | URI / URL |

Example:

```markdown
email: string email optional
created_at: string datetime readonly
```

#### A.2.6 Entity References

The `->` marker declares a reference to another entity:

```markdown
#! Order
customer: -> Customer
items: []-> OrderItem
warehouse: -> Warehouse optional
```

`-> Customer` means: this field holds a reference to a `Customer` entity. The marker is a semantic hint — it does not require a corresponding `#! Customer` schema to exist, and it imposes no resolution rules. The generator decides, case by case, whether a reference is serialized as a bare ID, a URI, or an inline-resolved object. Self-references (`parent: -> Category` within `#! Category`) are valid.

The `->` form is delimiter-free, which aligns with JMD's broader avoidance of matched delimiters (no parentheses, braces, or brackets in structural positions). The arrow is visually self-explanatory and familiar to LLMs from ER diagrams, UML, type annotations, and pointer notation — typically a single token in BPE tokenizers.

#### A.2.7 Inline Object Types

For edge cases where a nested object must appear inside an item body — where a `##` heading would close the enclosing scope — an inline-object syntax is available:

```markdown
address: object(street: string, city: string, zip: string optional) optional
items[]: object(sku: string, qty: integer, price: number) optional
```

The parenthetical expression lists field specs as comma-separated `key: type_expr` pairs. Modifiers on the containing field follow outside the parentheses. This form is intended for inline / embedded contexts only; at the top level of a schema document, the heading form (`## field[]: type_expr`) is preferred.

This is the one construct in the A.2 conventions that uses matched delimiters (the parentheses), and is accepted as a pragmatic compromise for a narrow situation where no alternative exists within the heading-scope model.

#### A.2.8 Binary Content Encoding

JMD is a text format. Binary payloads are carried via an application-defined text encoding. Two common conventions:

- **Base64**: inline encoding of the raw bytes as a Base64 string. Appropriate for small payloads where the binary content must travel with the document.

  ```markdown
  signature: base64:VGhpcyBpcyBiaW5hcnkgZGF0YQ==
  ```

- **sha256 hash reference**: a hex-encoded SHA-256 hash of the raw bytes. Appropriate for large payloads or content-addressed storage, where the bytes themselves are retrieved out-of-band.

  ```markdown
  attachment: sha256:3a7bd3e2360a3d29eea436fcfb7e44c735d117c42d1c1835420b6b9942dd4f1b
  ```

Neither is prescribed; both are prefix conventions that applications recognize as signaling binary content. A corresponding schema convention is:

```markdown
signature: string base64
attachment: string sha256
```

(where `base64` and `sha256` are treated as informal format hints, not normative additions to A.2.5.)

#### A.2.9 Rationale for the A.2 Dialect

The vocabulary above is designed to be writable by LLMs from general training — scalar type names from every typed language, `optional`/`readonly` as familiar English keywords (more self-documenting than the sigils `?` and `const`), delimiter-free enums via `|` alternation, and `->` for entity references. The design deliberately avoids matched delimiters (except in the narrowly-scoped inline-object form), keeping most of the schema surface parseable line-by-line and streamable.

Applications whose backends need richer type systems (discriminated unions, generic types, branded types, regex patterns as constraints, numeric bounds, length bounds, custom validators) SHOULD extend this vocabulary in their own documentation rather than forcing their needs into the above minimum. JMD's role is to carry the string; the application defines what the string means.

---

*JMD Specification v0.3.4 – Draft*
