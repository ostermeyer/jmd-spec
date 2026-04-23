---
title: "JMD: A Text-Based Structured Data Format for LLM-Driven Infrastructure"
abbrev: JMD
docname: draft-ostermeyer-jmd-00
category: info
ipr: trust200902
area: Applications and Real-Time
workgroup: Independent Submission
keyword:
  - structured data
  - serialization format
  - llm
  - agentic systems
  - streaming
  - media type
stand_alone: yes
pi:
  toc: yes
  sortrefs: yes
  symrefs: yes

author:
  -
    ins: A. Ostermeyer
    name: Andreas Ostermeyer
    organization: (individual)
    email: andreas@ostermeyer.de

normative:
  RFC2119:
  RFC3629:
  RFC6838:
  RFC8174:
  RFC8259:

informative:
  RFC6839:
  RFC9110:
  RFC7230:
  CommonMark:
    title: CommonMark Specification
    author:
      - ins: J. MacFarlane
    target: https://spec.commonmark.org/
    date: 2024
  JMD-SPEC:
    title: JMD Specification v0.3.2
    author:
      - ins: A. Ostermeyer
    target: https://github.com/ostermeyer/jmd-spec/blob/main/jmd-spec-v0_3.md
    date: 2026
  JMD-HTTP:
    title: "JMD over HTTP: REST Integration Proposal"
    author:
      - ins: A. Ostermeyer
    target: https://github.com/ostermeyer/jmd-spec/blob/main/jmd-over-http.md
    date: 2026

--- abstract

This document defines JMD (JSON Markdown), a text-based structured data
format designed for use in LLM-driven infrastructure, including tool-calling
pipelines, MCP (Model Context Protocol) servers, REST APIs consumed by LLM
agents, and multi-agent workflows. JMD encodes the full JSON type system
(RFC 8259) using a subset of Markdown syntax — headings for hierarchy,
`key: value` lines for object fields, bullet lists for array items, and
blockquotes for multiline strings. The format is line-oriented and
streamable: every completed line is an independent, parseable event. JMD
documents are in bijection with JSON values, and the roundtrip
JSON -> JMD -> JSON preserves the value.

This document specifies the JMD grammar, the canonical parse result
(envelope), the four document modes (data, query, schema, delete), the
streaming event model, and the media type registration for
`application/jmd`.

--- middle

# Introduction

## Motivation

Large Language Models (LLMs) consume and produce structured data in a wide
range of infrastructure scenarios: API responses, tool-call arguments and
results, agent-to-agent messages, schema descriptions, and configuration
data. JSON {{RFC8259}} is the predominant structured data format in these
settings, but its design — driven by machine-to-machine exchange between
programs that can buffer complete documents — is suboptimal for LLM
consumption and generation:

- **Token inefficiency.** JSON's structural overhead (quoted keys, braces,
  brackets, comma separators) consumes tokens that carry no data payload.
  For pretty-printed JSON — the real-world baseline, since LLMs cannot
  reliably produce minified JSON — the overhead is 19 to 29 percent of
  total tokens relative to JMD for the same data. At LLM inference scale,
  token count translates directly to compute cost and energy consumption.

- **Streaming hostility.** JSON uses matched delimiters for hierarchy. An
  object is only structurally valid once the closing brace arrives; an
  array only once the closing bracket arrives. A partially received JSON
  document is syntactically invalid. Streaming JSON parsers exist but are
  workarounds for the grammar, not solutions: they require additional
  buffering logic and, in the case of NDJSON, abandon standard JSON syntax.

- **LLM generation variance.** LLMs produce JSON variants that diverge
  from the specification in ways that cause parse failures: trailing
  commas, unquoted keys, single quotes around strings, comments,
  concatenated documents. These are not bugs in the model; they reflect
  the heterogeneity of JSON-like content in training data.

JMD addresses these properties by encoding the same JSON type system
using a subset of Markdown syntax that LLMs produce reliably and that
is inherently line-streamable.

## Design Principles

JMD is designed to satisfy the following properties:

1. **Lossless bijection with JSON.** Every JMD data document maps to
   exactly one JSON value. Every JSON value has at least one JMD
   representation. The roundtrip JSON -> JMD -> JSON preserves the value.

2. **Streaming by construction.** Every completed line is an
   independently processable event. No closing delimiters are required.
   Parsers maintain bounded state (a depth-indexed scope stack).

3. **LLM-native generation.** Every syntactic element reflects a pattern
   that LLMs produce naturally from their training on Markdown corpora:
   headings for hierarchy, bullets for lists, blockquotes for prose,
   blank lines for section separation.

4. **Generator-strict, parser-tolerant.** Serializers produce a canonical
   form; parsers accept the natural variations that LLMs exhibit
   (anonymous headings, depth-qualified item markers, cosmetic blank
   lines, and other variations enumerated in {{JMD-SPEC}}).

5. **Transport-agnostic.** The format is independent of any particular
   transport protocol. It is suitable for HTTP, Server-Sent Events, MCP
   tool calls, WebSocket frames, plain files, and pipeline stdout/stdin.

## Scope of This Document

This document specifies:

- The JMD grammar (Section {{core-grammar}})
- The canonical parse result — the envelope — returned by a conforming
  parser (Section {{parse-result}})
- The four document modes and their interpretation (Section
  {{document-modes}})
- The streaming event model (Section {{streaming}})
- The media type registration for `application/jmd`
  (Section {{iana-considerations}})
- Security considerations (Section {{security-considerations}})

The complete JMD specification, including non-normative recommendations
for filter-expression and type-expression conventions used in query and
schema documents, is published as {{JMD-SPEC}}. A companion proposal for
integration with HTTP-based REST APIs is published as {{JMD-HTTP}}.

# Terminology

## Requirement Words

{::boilerplate bcp14-tagged}

## Definitions

The following terms are used throughout this document:

Document:
: A complete JMD source text, beginning with an optional frontmatter
  block and a single root heading, followed by zero or more body elements.

Root heading:
: The first heading in a document, at heading depth 1 (a line beginning
  with exactly one `#` character followed by a mode marker and/or space
  and label text). The root heading determines the document mode.

Mode marker:
: An optional character (`!`, `?`, or `-`) appearing immediately after
  the `#` of the root heading, distinguishing schema, query, and delete
  documents from data documents respectively. Absence of a mode marker
  denotes a data document.

Body:
: The content of a document following the root heading, consisting of
  bare fields, headings, array items, blockquotes, and blank lines.

Bare field:
: A `key: value` line without a heading prefix, belonging to the
  innermost open object scope.

Scope:
: An object or array context opened by a heading or array marker. Scopes
  form a stack; fields and items belong to the scope at the top of the
  stack. Scopes close when a heading at the same or shallower depth
  arrives, when a blank line precedes a bare field, or at end of input.

Frontmatter:
: Zero or more `key: value` lines and bare-key lines preceding the root
  heading, carrying document-level metadata that is preserved by the
  parser but not included in the document body value.

Envelope:
: The canonical return value of a conforming parser: an object containing
  the mode, label, frontmatter, and value of the document. Defined in
  Section {{parse-result}}.

Conforming parser:
: An implementation that accepts any document produced by a conforming
  generator, plus the parser-tolerance variations enumerated in Section
  {{conformance}}, and returns the envelope defined in Section
  {{parse-result}}.

Conforming generator:
: An implementation that produces output matching the canonical grammar
  defined in Section {{core-grammar}}.

# Core Grammar   {#core-grammar}

*\[This section will contain the formal grammar in ABNF form,
corresponding to Section 11 of {{JMD-SPEC}}. To be expanded in the
next draft revision.\]*

# Canonical Parse Result   {#parse-result}

*\[This section will formalize Section 3.6 of {{JMD-SPEC}}: the envelope
shape, field semantics, prose-in-body parse error, and roundtrip
contract. To be expanded in the next draft revision.\]*

# Document Modes   {#document-modes}

*\[This section will consolidate the normative parts of Sections 13, 14,
15 of {{JMD-SPEC}}: data, query, schema, delete modes; their shared body
grammar; and the principle that values in query and schema documents are
raw strings whose semantic interpretation is application-defined. To be
expanded in the next draft revision.\]*

# Streaming   {#streaming}

*\[This section will specify the event model (DOCUMENT_START with
envelope header, field events, scope events, document end), the SAX-style
streaming discipline, and the line-boundary contract. To be expanded in
the next draft revision.\]*

# Conformance   {#conformance}

*\[This section will enumerate the generator-strict requirements and the
parser-tolerance variations, corresponding to Section 22 of
{{JMD-SPEC}}. To be expanded in the next draft revision.\]*

# IANA Considerations   {#iana-considerations}

IANA is requested to register the media type `application/jmd` in the
Standards Tree per {{RFC6838}}. The registration template is reproduced
below.

*\[The full registration template from `iana/application-jmd.md` will be
inlined here. To be completed in the next draft revision.\]*

A future revision of this document may additionally request registration
of `+jmd` as a structured syntax suffix per {{RFC6839}}.

# Security Considerations   {#security-considerations}

*\[This section will consolidate and expand the security considerations
currently summarized in the IANA registration template: injection risk
in downstream rendering contexts; bounded resource consumption and
recommended depth limits; content confusion with Markdown; absence of
active content, external references, and implicit network access;
streaming parse safety under truncation. To be expanded in the next
draft revision.\]*

--- back

# Acknowledgments   {#acknowledgments .unnumbered}

*\[To be filled. The spec owes debts to JSON (RFC 8259), CommonMark,
YAML (as a negative example of complexity), and — most directly — to
the corpus of Markdown on which LLMs are trained. Early benchmark
participants and implementers will be acknowledged by name when the
draft stabilizes.\]*

# Companion Documents   {#companion .unnumbered}

- The JMD Specification {{JMD-SPEC}} contains the normative grammar
  with extensive examples, the non-normative convention appendix for
  query and schema expressions, and the design rationale.
- The JMD-over-HTTP proposal {{JMD-HTTP}} describes how JMD composes
  with HTTP-based REST APIs, including content negotiation, method
  mappings, and streaming over chunked transfer encoding.
