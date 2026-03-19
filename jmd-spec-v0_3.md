# JMD – JSON Markdown
## Format Specification v0.3

Copyright (c) 2026 Andreas Ostermeyer <andreas@ostermeyer.de>. All rights reserved.
Licensed under CC BY-NC-SA 4.0 — see LICENSE-SPEC for details.

---

## 1. Overview

JMD (JSON Markdown) is a lossless data serialization format for the era of LLM-driven infrastructure, designed for workflows where structured data moves between servers and language models.

LLM compute cost scales directly with token count — for both consumed input and generated output. JMD reduces tokens at both ends. As **input**, a JMD document contains 19–29% fewer tokens than its pretty-printed JSON equivalent (the real-world API default); once the data is in context, the reasoning cost is identical regardless of format. As **output**, JMD is the only format that is both token-efficient and reliably generatable — LLMs cannot produce minified JSON consistently, reproducing pretty-printed patterns regardless of instruction. Quantitative benchmark results are provided in the companion document *JMD Efficiency Analysis*.

**The design philosophy** behind JMD is to work with the natural behavior of language models, not against it. LLMs are autoregressive text generators trained on vast corpora of Markdown, code, and structured documents. They have deeply internalized patterns like headings for hierarchy, `key: value` for fields, `- ` for list items, and blank lines for section boundaries. JMD does not invent new syntax for these structures — it formalizes the patterns that LLMs already produce when generating structured output. Every syntax decision in this specification passes a single test: *Would an LLM produce this naturally, without special instruction?* Where the answer is no, the design is reconsidered. This methodology is called *AI Whispering* throughout this specification.

JMD is a **tetradic protocol** for the full lifecycle of structured data in LLM-native systems:

| Root Marker | Mode | Purpose |
| --- | --- | --- |
| `# Label` | **Data** | Bidirectional data transport |
| `#! Label` | **Schema** | Structure contracts and type validation |
| `#? Label` | **Query** | Query by Example: intuitive data selection |
| `#- Label` | **Delete** | Resource deletion |

These four modes share the same syntax foundation. An LLM that can produce a JMD data document can produce a schema, query, or delete document with no additional training — only a different root marker.

**One document, one mode.** A JMD document has exactly one root marker, and therefore exactly one mode. Mixing modes within a single document is not permitted. This is a deliberate design decision, not a parser constraint: each mode corresponds to a distinct semantic operation (analogous to distinct HTTP methods), and a document with a single, unambiguous intention is easier to route, validate, and audit than a multi-operation bundle. Sequences of operations are composed by producing multiple documents, not by combining modes.

**Lossless** means:

- Every valid JMD data document maps to exactly one JSON value (unambiguous parsing).
- Every JSON value can be represented in JMD (complete coverage).
- The roundtrip JSON → JMD → JSON preserves the JSON value.

Multiple valid JMD representations may exist for the same JSON value (different key orderings, different number formatting within RFC 8259 constraints). This is by design: LLMs generate text sequentially in the order that is natural for the content, and JMD does not penalize this.

Three properties distinguish JMD from JSON. The first two are co-equal design goals; the third is a structural consequence of the same syntax choice:

**Compute efficiency.** LLM compute cost scales with token count at both ends of the pipeline. As **input**, JMD eliminates quoted keys and structural delimiters entirely — not just whitespace — achieving 19–29% fewer tokens than pretty-printed JSON (the real-world API default). Once parsed, the reasoning cost is identical regardless of format; the gain is at the tokenization boundary. As **output**, JMD is the only efficient format LLMs can reliably generate: they reproduce pretty-printed patterns regardless of instruction, making minification impractical. Quantitative benchmark results are provided in the companion document *JMD Efficiency Analysis*.

**Native streamability.** JMD's line-oriented syntax allows a receiver to process each field as soon as its line is complete — no closing delimiters required. JSON cannot offer this without buffering or non-standard extensions. For large collections and multi-agent pipelines, the streaming advantage is substantial.

Compute efficiency and streamability are not independent — they are two manifestations of the same design choice: hierarchy through heading depth rather than through matched delimiters. The same syntax that eliminates braces and quotes also eliminates the need for closing delimiters. Neither goal is subordinate to the other; both guide every syntax decision in this specification.

**Tetradic protocol.** JMD covers the full data lifecycle with a single, unified syntax: data transport (`#`), schema contracts (`#!`), Query by Example (`#?`), and resource deletion (`#-`). An LLM that understands one mode understands all four — the root marker is the only difference. JSON requires separate tooling ecosystems for each of these concerns.

**Sustainability implications.** The compute efficiency described above has consequences beyond cost savings. LLM inference is GPU-bound, and GPU clusters are among the most energy-intensive computing systems ever deployed. Structured data output — the domain where JMD replaces JSON — accounts for a significant share of LLM inference volume (tool calls, API responses, agent-to-agent communication, retrieval pipelines). Reducing per-request GPU time through structural simplification translates directly to reduced energy consumption and, at infrastructure scale, reduced hardware provisioning. Every GPU that does not need to be provisioned is a data centre that does not need to be built. Quantitative projections are provided in the companion document *JMD Efficiency Analysis*.

Together, these properties make JMD a natural fit for the infrastructure that is emerging around LLM agents: MCP servers, tool-calling pipelines, Server-Sent Events, and chained agentic workflows where one tool's output becomes the next tool's input.

**REST integration.** JMD can serve as a drop-in alternative to JSON in REST APIs via content negotiation (`application/jmd`). Because every completed JMD line is independently parseable, a standard HTTP chunked transfer response is inherently streaming — no protocol changes, wrapper formats, or separate streaming endpoints required. Media type definitions, HTTP method mappings, and content negotiation patterns are defined in the companion document *JMD over HTTP — REST Integration Proposal*.

JMD uses a subset of Markdown syntax — headings, blockquotes, and line breaks — to encode JSON's full type system. The choice of Markdown is not motivated by human readability but by the fact that LLMs are trained on vast amounts of Markdown and can generate it reliably and efficiently.

**Core syntax principle:** Heading depth defines data hierarchy. A heading at depth N establishes scope for all following content until the next heading at depth N or shallower, or until a blank line resets scope to root. This directly mirrors the Markdown section model that LLMs have deeply internalized, where a `##` heading governs everything that follows until the next `##` or `#`, and blank lines separate top-level sections.

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

```markdown
page: 2
size: 50

# Orders
total: 4832
page: 2
pages: 97
page_size: 50

## data[]
- id: 1
  status: pending
  total: 84.99
```

Frontmatter fields are syntactically identical to bare fields — no new syntax is required. The parser treats any `key: value` lines before the first `#` heading as document metadata. A blank line between frontmatter and the root heading is optional but recommended for readability.

Frontmatter fields are **not serialized** into the JSON output. They are transport-level metadata consumed by the parser or middleware, analogous to HTTP headers.

**Defined frontmatter fields:**

| Field | Applicable mode | Meaning |
| --- | --- | --- |
| `format` | all | JMD version identifier (e.g., `jmd/1.0`) |
| `schema` | all | URI reference to an external schema definition |
| `page` | `#?` | Requested page number (1-based) |
| `size` | `#?` | Requested number of results per page |
| `count` | `#?` | Request only the count of matching documents (value omitted or `true`) |
| `confidence` | `#` | Epistemic confidence level: `high`, `medium`, `low`, or `speculative` |
| `source` | `#` | Data provenance — free-form bare string describing where the data originates (e.g., `database`, `vector search`, `clinical guidelines 2024`, `user input`) |
| `uncertain` | `#` | Comma-separated list of field names the generator considers uncertain |

**Epistemic frontmatter** allows a generator to communicate its self-assessment of the data it produces. This is particularly valuable in LLM-generated responses, where the model operates with a persona and has a contextual understanding of how it arrived at each value.

The `confidence` field uses defined levels to enable consistent machine processing:

| Level | Condition |
| --- | --- |
| `high` | Data from verified or authoritative source |
| `medium` | Strong inference or single reliable source |
| `low` | Weak, incomplete, or potentially outdated basis |
| `speculative` | No reliable basis — included as best effort |

The `source` field is deliberately **not** an enum. The generator expresses data provenance in its own terms — a RAG agent might write `source: vector search, 3 documents matched`, a database adapter writes `source: postgresql`, a medical assistant writes `source: clinical guidelines 2024`. The receiver interprets this contextually. This reflects the fact that LLMs operate with personas and have a subjective perspective on the data they produce — formalizing this perspective rather than suppressing it makes the metadata more honest and more useful.

The `uncertain` field names specific fields whose values the generator considers less reliable than the overall `confidence` level suggests. This allows a generator to say "I am generally confident, but these particular values are weak."

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

A conforming parser MUST accept and pass through defined frontmatter fields. Unknown frontmatter fields MUST be ignored, not rejected — this ensures forward compatibility as new fields are defined in future versions.

A conforming generator SHOULD omit frontmatter entirely when no document-level metadata is needed. The absence of frontmatter is the common case for data documents. Epistemic frontmatter is always optional — a document without `confidence` or `source` fields simply carries no explicit self-assessment.

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

### 8.6 Thematic Break as Array Item Separator

When an array of objects contains items with nested sub-structures (child objects or child arrays), the boundary between consecutive items is visually ambiguous: a reader must count heading levels to determine where one record ends and the next begins. JMD uses the **thematic break** (`---`) as an explicit visual separator between such items.

#### Syntax

A thematic break is a line containing three or more hyphens (`---`), following the CommonMark specification (Section 4.1). It is a universally recognized Markdown convention for a horizontal rule or section divider.

#### Semantics

Within an array body, a `---` line:

1. **Closes** the current array item's scope — all nested sub-structures (child arrays, child objects) are terminated.
2. **Signals** that the next `- key: value` or bare `-` line starts a new item in the same parent array.
3. Has **no effect** on the heading-depth stack — it is purely a visual and scope separator within the current array.

A `---` line outside of an array with nested-object items has no effect and is ignored by the parser.

#### Canonical Form

The serializer emits a `---` separator between array items **if and only if** the array contains objects with nested sub-structures (dicts or lists as field values). For flat object arrays and scalar arrays, no separator is emitted.

#### Example

```markdown
## teams[]
- name: Alpha
  status: Active

### members[]
- Alice
- Bob

---

- name: Beta
  status: Active

### members[]
- Charlie
```

Serializes to:

```json
{
  "teams": [
    {"name": "Alpha", "status": "Active", "members": ["Alice", "Bob"]},
    {"name": "Beta", "status": "Active", "members": ["Charlie"]}
  ]
}
```

The record boundary between Alpha and Beta is immediately visible — no heading-level counting required.

#### Flat Arrays (Unchanged)

Arrays of flat objects do not emit thematic breaks:

```markdown
## items[]
- sku: A1
  qty: 2
- sku: B3
  qty: 1
```

#### Design Rationale

1. **Markdown familiarity.** `---` is universally recognized as a section divider. LLMs trained on Markdown produce and consume it naturally — this is AI Whispering applied to visual structure.
2. **Visual strength.** A horizontal rule is a stronger visual signal than a heading-level difference (`#` vs. `##`). It does not require counting characters to parse visually.
3. **Token-neutral.** The `---` separator adds one token per inter-item boundary, replacing the depth-qualified `## -` marker (also one token). Net token impact: zero.

**Note on YAML:** In YAML, `---` is a document separator. JMD builds on Markdown, not YAML, so `---` follows CommonMark semantics (horizontal rule). This distinction should be noted when communicating with developers experienced in YAML.

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
# products[]
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

## 13. Query by Example (QBE)

JMD includes a query dialect based on the Query by Example paradigm. A QBE query is a JMD document that describes the *shape and conditions* of desired results. The LLM writes an example of what it wants — using the same structure as a data document, with filter conditions in place of literal values.

QBE is the most LLM-native query form possible: the model does not learn a query language — it writes a data document and annotates it. The filter syntax uses regex patterns and comparison operators that LLMs know from their training on code and SQL, not from any QBE-specific convention.

### 13.1 Document Mode

The root marker `#?` signals a query document:

```markdown
#? Order
status: pending
```

Pagination and count requests are expressed as frontmatter — fields before the `#?` heading (see Section 3.5). They control the *delivery* of results, not the selection:

```markdown
count

#? Order
status: pending
```

Returns only the count of matching orders — no data. The bare field `count` (with no value) requests a count. This allows the LLM to assess result set size before requesting data.

```markdown
page: 1
size: 50

#? Order
status: pending
total: > 50
```

Returns the first 50 matching orders. The response includes pagination metadata in the envelope (see Section 16):

```markdown
# Orders
total: 4832
page: 1
pages: 97
page_size: 50

## data[]
- id: 1
  status: pending
  total: 84.99
- id: 2
  status: active
  total: 120.00
```

The LLM sees `total: 4832` before the first data record arrives — because JMD is streaming and envelope fields precede the data array. It can close the connection, narrow the query, or request the next page.

### 13.2 Projection

`?` as a field value means: *return this field, apply no filter condition.*

```markdown
#? User
name: ?
email: ?
active: true
```

Meaning: return `name` and `email` of all users where `active = true`.

`?: ?` inside an object scope means: *project all remaining fields of this object.*

```markdown
#? User
active: true
## address
city: Berlin
?: ?
```

Returns all users where active=true and address.city=Berlin, projecting the full address object.

### 13.3 Filter Conditions

A field value in a query document is interpreted as a filter condition. The condition syntax combines three mechanisms that LLMs already know:

**Literal values** are equality conditions:

```markdown
status: pending
city: Berlin
active: true
```

**Regex patterns** are used for pattern matching. Any value that contains regex metacharacters (`|`, `.`, `*`, `+`, `?`, `^`, `$`, `[`, `]`, `(`, `)`, `\`) is interpreted as a regex pattern and matched against the field value:

```markdown
status: pending|active|processing
name: .*Corp.*
sku: ^A\d+
email: .*@example\.com$
city: Berlin|München|Hamburg
```

The regex dialect is PCRE-compatible. A pattern must match the entire field value (implicit anchoring), unless explicit `.*` is used. LLMs produce regex reliably from extensive training on programming languages, and regex provides all common query operations — alternation (OR), wildcards, character classes, anchoring — in a single, well-defined syntax.

**Comparison operators** are used for numeric and date range filters. A value starting with `>`, `>=`, `<`, or `<=` is a comparison condition:

```markdown
total: > 50
qty: >= 10
price: < 100.00
created: >= 2026-01-01
```

A conforming parser MUST accept optional whitespace between the operator and the value (e.g., both `>50` and `> 50` are valid). LLMs naturally insert spaces after operators.

**Negation** inverts any condition. A value starting with `!` negates the following condition:

```markdown
deleted: !true
status: !cancelled
sku: !^LEGACY.*
```

The `!` prefix composes with all other condition types: `!true` (not equal), `!cancelled` (not equal), `!^LEGACY.*` (regex negation).

### 13.4 Filter Summary

| Condition | Syntax | Example |
|---|---|---|
| Equality | bare value | `status: pending` |
| Regex pattern | regex metacharacters | `status: pending\|active` |
| Greater than | `>` prefix | `total: > 50` |
| Greater or equal | `>=` prefix | `score: >= 90` |
| Less than | `<` prefix | `price: < 100` |
| Less or equal | `<=` prefix | `qty: <= 5` |
| Negation | `!` prefix | `deleted: !true` |
| Negated regex | `!` + regex | `sku: !^LEGACY.*` |
| Projection | `?` | `email: ?` |
| Wildcard projection | `?: ?` | All remaining fields |

### 13.5 Array Conditions

An array condition in a query acts as an **EXISTS** predicate: match documents where at least one array item satisfies all sub-conditions.

```markdown
#? Order
status: pending
## items[]
- sku: ^A\d+
  qty: > 1
```

Meaning: *orders where status=pending AND at least one item has sku matching `^A\d+` and qty > 1.*

Array items with all fields as `?` project the full array:

```markdown
## items[]
- sku: ?
  price: ?
```

### 13.6 Complete QBE Example

Query:

```markdown
page: 1
size: 25

#? Order
status: pending|processing
total: > 50.0
## tags[]
- express
## items[]
- sku: ?
  qty: ?
  price: > 10.0
## address
city: ?
?: ?
```

In prose: *Find orders where status is pending or processing, total > 50, tagged "express", containing at least one item with price > 10 — return sku and qty of matching items, and the full address. Return page 1 with 25 results.*

### 13.7 QBE Grammar Extension (EBNF)

```ebnf
query_document  ::= frontmatter? "#? " label NEWLINE query_body

frontmatter     ::= (frontmatter_field NEWLINE)+ BLANK_LINE?
frontmatter_field ::= key ": " value
                    | key                    (* bare key with no value, e.g. 'count' *)

query_body      ::= (query_element | BLANK_LINE)*

query_element   ::= query_heading | query_bare_field | query_array_item

query_heading   ::= query_object_heading | query_array_heading
query_object_heading  ::= heading_prefix key NEWLINE
query_array_heading   ::= heading_prefix key "[]" NEWLINE

query_bare_field ::= key ": " condition NEWLINE
                   | wildcard_projection

query_array_item ::= "-" NEWLINE
                   | "- " key ": " condition NEWLINE
query_indent_field ::= INDENT key ": " condition NEWLINE

condition       ::= projection | filter_expr
projection      ::= "?"
filter_expr     ::= negation? (comparison | regex_or_literal)
negation        ::= "!"
comparison      ::= comp_op " "? scalar
comp_op         ::= ">" | ">=" | "<" | "<="
regex_or_literal ::= (* A value containing regex metacharacters
                        (|.*+?^$[]()\) is treated as a regex pattern.
                        A value without metacharacters is an equality match. *)

wildcard_projection  ::= "?: ?" NEWLINE
```

### 13.8 Design Rationale

QBE deliberately omits sorting, aggregation, grouping, and computed expressions. An LLM receiving a result set can sort, filter, count, sum, and group as a reasoning step — these are cognitive operations, not data transport operations. QBE's sole purpose is to reduce the result set to a size that fits the LLM's context window. Everything beyond that is the LLM's job.

The choice of regex as the primary pattern language reflects the design philosophy of working with the LLM's existing capabilities. LLMs produce regex fluently from extensive training on programming languages, documentation, and Stack Overflow. Regex provides alternation (OR), wildcards, character classes, and anchoring in a single, universally understood syntax — eliminating the need for format-specific operators. The comparison operators (`>`, `>=`, `<`, `<=`) are the only addition, because numeric range comparisons cannot be expressed in regex.

Pagination is expressed as frontmatter — fields before the `#?` heading — because it controls the *delivery* of results, not their *selection*. This is both structurally correct (transport metadata belongs outside the query body) and LLM-native: an LLM naturally writes preamble information before the main content, just as it would write a header before a document body. The frontmatter uses the same `key: value` syntax the LLM already knows from JMD data fields — no new syntax is required. This keeps the query body clean: every field in the body is either a filter or a projection, with no meta-concerns mixed in.

### 13.9 QBE and the Four Operations

In a JMD-native MCP or API context, the four canonical operations map cleanly:

| Operation | Input | Output |
|---|---|---|
| `read(path)` | path string | JMD data document |
| `write(path, body)` | path + JMD data document | confirmation |
| `query(body)` | JMD query document (`#?`) | JMD result document |
| `delete(path, body)` | path + JMD delete document (`#-`) | confirmation |

This gives an LLM a complete, minimal interface to any data source using only JMD documents as the communication format. Each operation corresponds to a document mode: `#` for data (read/write), `#?` for query, `#!` for schema, and `#-` for delete.

---

## 14. Schema Documents

A JMD schema document describes the expected structure and types of a data document. It uses the root marker `#!` and is convertible to and from JSON Schema.

### 14.1 Root Marker

```markdown
#! Order
```

### 14.2 Field Types

A schema field specifies its JSON type as the value:

| JMD Schema Syntax | JSON Schema type |
|---|---|
| `key: string` | `{"type": "string"}` |
| `key: number` | `{"type": "number"}` |
| `key: integer` | `{"type": "integer"}` |
| `key: boolean` | `{"type": "boolean"}` |
| `key: null` | `{"type": "null"}` |

### 14.3 Schema Modifiers

Schema fields support modifiers that follow the base type or enum. Modifiers are **keywords** — reserved words with defined meaning that are not available as type names or enum values.

**Defined keywords:**

| Keyword | Position | Meaning |
| --- | --- | --- |
| `optional` | after type/enum | Field may be omitted (not required) |
| `readonly` | after type/enum | Field is read-only — must not be included in write operations |

**Default values** use `= value` after the type (before or after keywords):

```markdown
status: pending|active|shipped = pending
retries: integer = 3
```

**Format hints** follow the base type as a keyword. They describe the expected shape of a string value:

| Format hint | Meaning |
| --- | --- |
| `email` | Email address |
| `date` | ISO 8601 date (`2026-03-12`) |
| `datetime` | ISO 8601 date-time (`2026-03-12T14:30:00Z`) |
| `uri` | URI / URL |

Format hints are **semantic context for the LLM**, not validation constraints. A parser is not required to validate that a `string email` value is actually a valid email address.

**Enum constraints** use a pipe-separated list of values without delimiters:

```markdown
status: pending|active|shipped|cancelled
role: admin|user|guest
priority: low|medium|high|critical = medium
```

The pipe character `|` makes enums visually distinct from format hints and base types. An LLM recognizes the alternation pattern from regex training.

**Combining modifiers:**

```markdown
id: integer readonly
notes: string optional
email: string email optional
created_at: string datetime readonly
due_date: string date optional
status: pending|active|shipped = pending
priority: low|medium|high|critical = medium optional
```

The order after the type is: format hint, default, keywords. A parser SHOULD accept modifiers in any order.

### 14.4 Nested Objects

Nested objects use headings at deeper levels:

```markdown
#! Order
id: integer
## address
street: string
city: string
zip: string
country: string optional
```

### 14.5 Arrays

Array fields use the `[]` sigil. The item type follows as a bare field or heading:

```markdown
## tags[]: string

## items[]: object
- sku: string
  qty: integer
  price: number
```

### 14.6 Entity References

The `->` marker declares that a field references another entity:

```markdown
#! Order
id: integer
customer: -> Customer
warehouse: -> Warehouse optional
```

`-> Customer` means: this field holds a reference to a `Customer` entity. The marker is a **semantic hint**, not a validation constraint — it does not require a corresponding `#! Customer` schema to exist.

**How references are serialized in data documents:** The schema declares the *relationship*; the generator decides the *representation*. A reference field may appear in data as a bare ID, a URI, or an inline-resolved object:

```markdown
# Order
customer: 42
```

```markdown
# Order
## customer
id: 42
name: Müller
city: Berlin
```

Both are valid data for the same `customer: -> Customer` schema field. This is analogous to OData NavigationProperties, where the client decides via `$expand` whether to inline-resolve or return a reference. In JMD, the generator makes this decision autonomously.

**Array references** use the standard array sigil:

```markdown
#! Order
items: []-> OrderItem
tags: []-> Tag optional
```

Serialized as a list of IDs (`items: [101, 102, 103]`) or as an inline-resolved array of objects — the generator decides.

**Self-references** work naturally:

```markdown
#! Category
name: string
parent: -> Category optional
```

### 14.7 Complete Schema Example

```markdown
#! Order
id: integer readonly
status: pending|active|shipped|cancelled = pending
total: number
paid: boolean
notes: string optional
description: string optional
email: string email optional
created_at: string datetime readonly
customer: -> Customer

## address
street: string
city: string
zip: string
country: string optional
### geo
lat: number
lng: number

## tags[]: string

## items[]: object
- sku: string
  qty: integer
  price: number
```

### 14.8 Schema Grammar (EBNF)

```ebnf
schema_document  ::= "#! " label NEWLINE schema_body
schema_body      ::= (schema_element | BLANK_LINE)*

schema_element   ::= schema_heading | schema_bare_field

schema_heading   ::= heading_prefix key NEWLINE
                    | heading_prefix key "[]: " type_expr NEWLINE
                    | heading_prefix key "[]" NEWLINE

schema_bare_field ::= key ": " type_expr NEWLINE

type_expr        ::= (base_type format_hint? | enum_expr | ref_type | "[]" ref_type)
                     default_value? modifier*

base_type        ::= "string" | "number" | "integer" | "boolean" | "null" | "object"
format_hint      ::= " " ("email" | "date" | "datetime" | "uri")
enum_expr        ::= scalar ("|" scalar)+
ref_type         ::= "-> " label
default_value    ::= " = " scalar
modifier         ::= " optional" | " readonly"
```

### 14.9 Schema and the Four Operations

In an MCP context, schema documents serve as the contract for all four operations. The LLM receives the schema as context and generates a conforming JMD document:

| Operation | Schema role |
|---|---|
| `read(path)` | Schema describes what the response will look like |
| `write(path, body)` | Schema validates the body before submission |
| `query(body)` | Schema describes filterable and projectable fields |
| `delete(path, body)` | Schema identifies which fields serve as resource identifiers |

---

## 15. Delete Documents

A JMD delete document signals the intent to remove one or more resources. It uses the root marker `#-` and shares the same syntax foundation as all other JMD document modes.

### 15.1 Root Marker

```markdown
#- Order
```

The `#-` marker is parsed as a depth-1 heading with mode prefix `-`, analogous to `#?` (query) and `#!` (schema). The label identifies the resource type being deleted.

### 15.2 Single Resource Deletion

A delete document for a single resource contains the identifier fields necessary to locate the target:

```markdown
#- Order
id: 42
```

The body is a standard JMD object — the same syntax as a `# Order` data document. The `#-` root marker is the only difference. This means an LLM that can produce a data document can produce a delete document by changing one character in the root marker.

### 15.3 Bulk Deletion

Bulk deletion uses a root array:

```markdown
#- []
- abc123
- def456
- ghi789
```

The items are resource identifiers — typically scalar values (IDs, keys). For resources identified by composite keys, object items may be used:

```markdown
#- []
- table: orders
  id: 42
- table: orders
  id: 43
- table: customers
  id: 7
```

### 15.4 Delete Response

The response to a delete operation is a standard JMD data document confirming what was deleted:

```markdown
# Deleted
id: 42
resource: orders
```

For bulk deletion:

```markdown
# Deleted
count: 3
resource: orders
```

A server MAY echo the full deleted resource(s) if the data is still available, or return a minimal confirmation. The response format is not prescribed — it is a standard JMD data document (`#`), not a delete document (`#-`).

### 15.5 Delete Grammar (EBNF)

A delete document reuses the data document grammar from Section 11 without modification. The root marker is the only syntactic difference.

```ebnf
delete_document  ::= "#- " label NEWLINE body
                   | "#- []" NEWLINE bulk_delete_body

bulk_delete_body ::= (array_item | BLANK_LINE)*
                     (* Scalar items are resource identifiers (IDs, keys).
                        Object items are composite-key identifiers.
                        Same syntax as array items in data documents — see Section 11. *)
```

`body` is the data document body defined in Section 11. The delete body contains identifier fields — literal values that locate the target resource. For bulk deletion, `array_item` follows the same rules as in data documents (scalar items or object items with indented fields).

Conditional deletion (delete by filter, analogous to SQL `DELETE WHERE`) is intentionally not part of this specification. LLM agents operating on data naturally perform a two-step workflow: query first (`#?`) to verify the match set, then delete (`#- []`) with the resolved identifiers. This pattern is both safer — the agent sees what it will delete before deleting — and LLM-native: models trained to handle destructive operations prefer to verify before acting.

### 15.6 Design Rationale

1. **Explicit intent.** Delete is a destructive operation. A dedicated root marker (`#-`) makes the intent unambiguous at the document level — no path-suffix conventions or HTTP method inspection required.

2. **LLM-native.** The hyphen in `#-` visually suggests "removal" and follows the Markdown convention where `-` marks list items (things to be processed). An LLM can produce `#- Order\nid: 42` as naturally as `# Order\nid: 42`.

3. **Transport-agnostic.** The `#-` marker carries the delete intent within the document itself. This works over HTTP, MCP, WebSocket, or any other transport — the consumer does not need to inspect HTTP methods or path patterns to understand the operation.

4. **Completes CRUD.** With `#-`, JMD covers the full lifecycle: Create and Update via `#` (data), Read via `#` (data response), Query via `#?`, Schema via `#!`, Delete via `#-`.

---

## 16. Collection Responses and Pagination

Collection responses commonly wrap array data in an envelope object that carries pagination metadata alongside the items. In JMD, this pattern is expressed naturally using the heading-scope model: pagination fields are scalar fields at root level, and the array is a named field within the same document:

```markdown
# Orders
total: 142
page: 2
page_size: 20

## data[]
-
id: 1
status: pending
total: 84.99
-
id: 2
status: shipped
total: 120.00
```

The root marker `# Orders` (not `# []`) signals that this is an enveloped collection, not a bare array. A bare array response (`# []`) carries items only, with no envelope metadata.

Pagination is requested via frontmatter in the query document (see Section 3.5):

```markdown
page: 2
size: 20

#? Order
status: active
```

Pagination metadata in the response envelope (`total`, `page`, `pages`, `page_size`) MUST appear as root-level fields *before* the data array. This ensures the consumer receives result set metadata before the first data record arrives — a streaming guarantee that allows early decisions (close connection, narrow query, request next page).

The schema for an enveloped collection:

```markdown
#! Orders
total: integer
page: integer
page_size: integer
## data[]: object
-
id: integer
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
| `# Label` | `DOCUMENT_START` | Document label, mode |
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

The complete event sequence for a typical Order document:

```
DOCUMENT_START  "Order"
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

3. **Query by Example.** JMD is a tetradic protocol: data, query, schema, and delete share one syntax. An LLM that can produce a JMD data document can produce a query (`#?`), schema (`#!`), or delete (`#-`) with only a different root marker. JSON requires separate tooling ecosystems for each concern.

These three pillars are not independent features bolted onto a data format — they are structural consequences of the same design choice. JMD's design methodology — *AI Whispering*, the systematic validation of every syntax decision against the natural generation behaviour of LLMs — is what makes these three properties co-emerge from a single design.

Quantitative benchmark results, methodology details, and alternative format experiments are provided in the companion document *JMD Efficiency Analysis*.

---

## 19. Document Mode Summary

All JMD document modes at a glance:

| Root Marker | Mode | Description |
|---|---|---|
| `# Label` | **Data** | Standard data document |
| `# []` | **Data (root array)** | Root-level array |
| `#? Label` | **Query** | QBE query document |
| `#! Label` | **Schema** | Structure and type definition |
| `#- Label` | **Delete** | Resource deletion |
| `#- []` | **Delete (bulk)** | Bulk resource deletion |

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

**Full query language / custom operators:** Existing query syntaxes (MongoDB's `$gt`/`$in`/`$regex`, GraphQL filters, OData `$filter`) each define a bespoke operator vocabulary that an LLM must memorize as an opaque convention. JMD's QBE avoids this entirely: filter conditions use regex (which LLMs know from code) and comparison operators (which LLMs know from every programming language). There is no JMD-specific operator vocabulary to learn. A full query language would also tempt implementers to push computation into the query layer (aggregation, joins, subqueries) — capabilities the LLM already has natively and that would bloat the format specification for marginal benefit.

**Matched delimiters in query syntax:** An early QBE design considered function-call operators like `in(a, b, c)` and `not(value)`. These were rejected because matched delimiters — opening and closing parentheses that must be balanced — contradict a core JMD design principle. JMD eliminates `{}` and `[]` from data syntax precisely because closure-based constructs are token-inefficient and impede streaming. Reintroducing matched delimiters in the query dialect would undermine this principle. The prefix negation operator `!` and regex alternation `a|b|c` achieve the same expressiveness without any closing delimiter.

**Fenced code blocks for multiline strings:** An earlier version of JMD included fenced code blocks (triple-backtick delimiters) as a second multiline string form alongside blockquotes. Fenced blocks were intended for raw text — code, config, logs — where Markdown interpretation should be suppressed. They were removed in v0.3 for a fundamental reason: fenced blocks are the only Markdown construct that uses matched delimiters (an opening fence and a closing fence). This directly contradicts JMD's core anti-delimiter principle — the same principle that motivates the elimination of `{}`, `[]`, and `()` throughout the format. More importantly, matched delimiters break the streaming guarantee: a parser must buffer all content between the opening and closing fence, unable to emit any events until the closing fence arrives. Every other JMD construct is a position marker — a line that self-identifies its role without reference to any future line. Fenced blocks are the sole exception, and removing them makes JMD's streaming guarantee complete and unconditional. Blockquotes handle all multiline use cases, including code and raw text. The `>` prefix on each line is a position marker, not a delimiter pair, and each line can be processed independently as it arrives.

**Emoji semantics:** Unicode emoji characters (🚀, ✅, ❌) and Markdown-style emoji shortcodes (`:rocket:`, `:white_check_mark:`) are valid string content in JMD. Both forms pass through the parser unmodified — the parser does not convert shortcodes to Unicode or vice versa. JMD assigns no syntactic meaning to emojis; they are transparent data. If a receiving system wants to render `:rocket:` as 🚀 or interpret ✅ as a boolean status, that is application-level logic outside the JMD specification. This is consistent with JMD's general rule that Markdown rendering is not applied to string content (Section 22.2).

**Native date/time types:** JSON has no date type; ISO 8601 strings are the established convention. JMD inherits this: `created: 2024-03-08T14:30:00Z` is parsed as an unambiguous string. Adding a typed date sigil would solve a problem that tooling already handles at the application layer.

**Binary data:** Out of scope for a text-based format. Base64 strings are the appropriate fallback where binary data must be represented.

**References and anchors:** YAML's anchor/alias mechanism adds parsing complexity and is rarely needed in LLM-generated output. JMD prefers explicit repetition over implicit reference.

**Linked data and cross-document references (JSON-LD style):** Formal link semantics between documents — typed resource references, URI resolution, RDF-style predicates — are explicitly out of scope. JMD's `->` entity reference (Section 14.7) covers the practical need: declaring that a field references another entity so that an LLM or system can resolve it through sequential `read` calls. This is a lightweight semantic hint, not a linked-data model. Full JSON-LD-style semantics (RDF triples, `@context`, URI expansion) would impose a conceptual framework that adds complexity without benefit for the primary use case of LLM-to-system communication.

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

**Why regex as QBE filter syntax?** LLMs have extensive training on regular expressions from programming languages, documentation, and code review. Regex is not a QBE-specific convention — it is a pre-existing skill that QBE reuses. This matters for two reasons. First, the LLM needs no QBE-specific training to write filter patterns: `status: pending|shipped` and `sku: ^LEGACY.*` are patterns it would produce in any programming context. Second, the self-reinforcing tokenizer effect applies: as JMD QBE documents appear in training corpora, the characteristic pattern of `key: regex` within a `#?` document becomes increasingly familiar, making QBE generation more reliable over time. The initial unfamiliarity of seeing regex in a data-document context is a transitional cost that adoption itself eliminates — the same flywheel that drives JMD's core token efficiency (Section 1) applies to its query dialect.

**Why free-form fields in error documents?** Error documents serve two audiences: machines (routing, retry logic, monitoring) and LLMs (understanding what went wrong and how to recover). The `status` and `code` fields serve machines; `message`, `suggestion`, and `context` serve LLMs. Like the epistemic `source` field in frontmatter, the free-form error fields carry the generator's perspective rather than a standardized vocabulary. A database server writes `suggestion: Check foreign key constraints`; an LLM-powered API writes `suggestion: The customer name looks like a typo — did you mean "Müller"?`. Prescribing the content of these fields would suppress the very information that makes them valuable. The error code vocabulary is similarly left to domain convention rather than specification mandate, because error taxonomies are inherently domain-specific and will converge through usage patterns rather than top-down standardization.

**Why no comments?** JMD deliberately omits comments. Every other JMD construct maps bijectively to JSON; comments would be the sole exception — silently discarded during serialization, invisible in the JSON roundtrip, yet adding parser complexity at every grammar level. JMD's primary audience is LLMs, which read all tokens and gain nothing from out-of-band annotations. Where metadata about data is valuable, it belongs in a data field (`_note: ...`) that survives serialization. See Section 18 for the full rationale.

**Why epistemic frontmatter with free-form `source`?** LLMs operate with personas and have a contextual self-understanding of how they arrived at each piece of data. A medical assistant knows it drew on clinical guidelines; a RAG agent knows it matched three documents; a database adapter knows it queried PostgreSQL. Forcing these diverse perspectives into a fixed enum (`training`, `search`, `logic`) would lose the very information that makes the metadata valuable. Instead, `confidence` uses defined levels (for consistent machine processing), while `source` is a free-form bare string that carries the generator's own description of data provenance. The receiver — whether human, system, or another LLM — interprets this contextually. This is not non-deterministic in a problematic sense; it is *personal* in the sense that it reflects the generator's perspective honestly. The `uncertain` field bridges document-level and field-level granularity without per-field annotation syntax: the generator lists which fields it considers weak, and the receiver can act accordingly.

**Why `->` for entity references?** An earlier design considered `ref(Customer)` with function-call syntax. This was rejected for the same reason as `in()` and `not()` in QBE: matched delimiters (parentheses) contradict JMD's core anti-delimiter principle. The arrow `->` is delimiter-free, visually self-explanatory ("points to"), and deeply familiar to LLMs from ER diagrams, UML associations, type annotations, and pointer notation across programming languages. It is typically a single token in BPE tokenizers. The `->` marker is a semantic hint, not a validation constraint — the schema declares the relationship, the generator decides the representation (bare ID, URI, or inline-resolved object). This mirrors OData NavigationProperties and keeps the schema layer lightweight: no resolution rules, no join semantics, no circular-dependency handling. The LLM resolves references through sequential `read` calls, which is the natural agentic pattern.

**Why `optional` and `readonly` as keywords instead of sigils?** An earlier design used `?` as a trailing sigil for optional fields (`notes: string?`). While compact and familiar from programming languages, sigils are opaque to readers who are not programmers — and JMD schemas are meant to be read and understood by LLMs and humans alike. The keyword `optional` is self-documenting: its meaning is immediate and unambiguous in any context. The same principle applies to `readonly`. Using full English keywords also maintains consistency with the rest of JMD's design, which favors readable constructs over terse notation. The minor cost in token count (one word vs. one character) is negligible in schema documents, which are typically small and read once, not transmitted repeatedly.

**Why delimiter-free enums?** An earlier design used `string(pending|active|shipped)` with parentheses around enum values. This contradicts JMD's core anti-delimiter principle — the same principle that led to rejecting `ref()`, `in()`, and `not()`. The delimiter-free form `pending|active|shipped` uses the pipe character as alternation, which LLMs know from regex. The base type `string` is implicit for enum values (all enum members are strings). This is both more concise and consistent with the delimiter-free philosophy that runs through the entire specification.

**Why format hints as keywords, not formal validation?** Schema format hints (`string email`, `string datetime`) are semantic context for the LLM, not validation rules for a parser. An LLM that reads `email: string email` understands "this field should contain an email address" — it does not need a regex validator to enforce this. Keeping format hints as informational keywords rather than formal constraints keeps the schema layer lightweight and avoids the complexity trap of schema validation languages like JSON Schema's `format` keyword, where the boundary between "annotation" and "assertion" has caused years of specification debate.

**Why `#!` for schema?** The `!` sigil is conventionally associated with declarations and directives (shebang lines, YAML directives, DOCTYPE). It is visually distinct from `#?` (query) and `#` (data), making document mode immediately recognizable.

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
- Support document frontmatter: fields before the first heading are document-level metadata, not serialized into JSON (Section 3.5). Unknown frontmatter fields MUST be ignored.
- Recognize all four document modes: `#` (data), `#?` (query), `#!` (schema), `#-` (delete). The `#-` root marker MUST be parsed as a depth-1 heading with mode prefix `-` (Section 15).
- Parse `#-` delete documents using the same syntax rules as data documents — the body is a standard JMD object or array.
- Reject structurally invalid input with a clear error indicating the offending line. Tolerant variations (Section 22.1) are NOT structurally invalid.
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
- **Frontmatter:** `page: 1` and `size: 50` before `#? Order` heading are parsed as metadata, not serialized into JSON
- **Frontmatter with bare key:** `count` before `#? Order` heading is a valid bare frontmatter field
- **No frontmatter:** document starting directly with `# Order` has no frontmatter (common case)
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
- **Schema entity reference:** `customer: -> Customer` parsed as reference type in schema
- **Schema optional reference:** `warehouse: -> Warehouse optional` parsed as optional reference type
- **Schema array reference:** `items: []-> OrderItem` parsed as array of references
- **Schema self-reference:** `parent: -> Category optional` within `#! Category` is valid (no circularity check)
- **Schema enum without delimiters:** `status: pending|active|shipped` parsed as enum type
- **Schema enum with default:** `status: pending|active|shipped = pending` parsed as enum with default value
- **Schema format hint:** `email: string email` parsed as string type with email format hint
- **Schema readonly:** `id: integer readonly` parsed as integer type with readonly modifier
- **Schema optional:** `notes: string optional` parsed as optional string field
- **Schema combined modifiers:** `created_at: string datetime readonly` parsed with format hint and readonly
- **Epistemic frontmatter:** `confidence: high` and `source: database` before `# Customer` are parsed as metadata, not serialized into JSON
- **Uncertain fields:** `uncertain: zip, phone` in frontmatter is a valid bare string frontmatter field
- **Epistemic frontmatter absent:** document without `confidence`/`source` fields has no epistemic metadata (common case)
- **Error document minimal:** `# Error` with `status: 404` and `code: not_found` is a valid error document
- **Error document with free-form fields:** `suggestion` and `context` are parsed as regular bare string fields
- **Error document with errors array:** `## errors[]` with `- field: x` + indented `reason: y`, `value: z` parsed correctly
- **Streaming error:** `# Error` after partial data document closes all open scopes
- **QBE equality filter:** `#? Order` with `status: pending` matches documents where status equals "pending"
- **QBE regex filter:** `status: pending|active` treated as regex pattern (contains `|` metacharacter); `name: .*Corp.*` matches by wildcard
- **QBE comparison — greater than:** `total: > 50` parsed as numeric comparison condition, not a string value
- **QBE comparison — all operators:** `>=`, `<`, `<=` parsed correctly; optional whitespace between operator and value (`>50` and `> 50` are both valid)
- **QBE projection:** `email: ?` means "return this field"; literal `?` is a projection marker, not a string value
- **QBE wildcard projection:** `?: ?` within an object scope means "project all remaining fields of this object"
- **QBE negation:** `deleted: !true` (negated equality), `status: !cancelled` (negated literal), `sku: !^LEGACY.*` (negated regex)
- **QBE array EXISTS:** `## items[]` with `- sku: ^A\d+` + indented `qty: > 1` means at least one array item satisfies all sub-conditions
- **QBE combined:** document with frontmatter pagination, equality, regex, comparison, projection, and array condition all parsed correctly in one document (Section 13.6)
- **QBE mode detection:** `#?` root marker detected; label extracted; body parsed as query (conditions, not data values)
- **Delete document single:** `#- Order` with `id: 42` parsed as object `{'id': 42}` with delete mode detected
- **Delete document bulk:** `#- []` with scalar items parsed as list of identifiers with delete mode detected
- **Delete document composite key:** `#- []` with object items (`- table: orders` + indented `id: 42`) parsed correctly
- **Delete root marker:** `#-` recognized as depth-1 heading with mode prefix `-`, label extracted correctly
- **Delete body syntax:** `#- Order` body uses identical syntax rules as `# Order` data document (fields, nested objects, blockquotes)

---

*JMD Specification v0.3 – Draft*