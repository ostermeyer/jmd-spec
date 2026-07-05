---
title: "JMD: A Text-Based Structured Data Format for LLM-Driven Infrastructure"
abbrev: JMD
docname: draft-ostermeyer-jmd-00
category: info
submissiontype: independent
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
  CommonMark:
    title: CommonMark Specification
    author:
      - ins: J. MacFarlane
    target: https://spec.commonmark.org/
    date: 2024
  JMD-SPEC:
    title: JMD Specification v0.3.5
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
(RFC 8259) using a subset of Markdown syntax -- headings for hierarchy,
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
settings, but its design -- driven by machine-to-machine exchange between
programs that can buffer complete documents -- is suboptimal for LLM
consumption and generation:

- **Token inefficiency.** JSON's structural overhead (quoted keys, braces,
  brackets, comma separators) consumes tokens that carry no data payload.
  For pretty-printed JSON -- the real-world baseline, since LLMs cannot
  reliably produce minified JSON -- the overhead is approximately 19 percent of
  total tokens relative to JMD for the same data on average (10 to 22
  percent depending on the model tokenizer). At LLM inference scale,
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
- The canonical parse result -- the envelope -- returned by a conforming
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

This section defines the canonical generator language of JMD in ABNF
{{!RFC5234}}. The grammar operates on Unicode code points after UTF-8
{{!RFC3629}} decoding. A conforming generator MUST produce output
matching this grammar; a conforming parser MUST accept this grammar
plus the tolerance variations enumerated in Section {{conformance}}.

~~~ abnf
jmd-document    = [BOM] [frontmatter] root-heading *body-element

BOM             = %xFEFF

frontmatter     = 1*frontmatter-line
frontmatter-line = ( fm-field / fm-bare-key ) EOL
fm-field        = key kv-sep value
fm-bare-key     = key

root-heading    = "#" [mode-mark] SP ( array-sigil / label ) EOL
mode-mark       = "?" / "!" / "-"
array-sigil     = "[]"
label           = 1*label-char
label-char      = SP / VCHAR / uni-char

body-element    = heading-line / bare-field / multiline-field /
                  array-item / indent-field / blank-line

heading-line    = object-heading / array-heading /
                  sub-array-heading / scalar-heading / level-pop
heading-prefix  = 2*"#" SP
object-heading  = heading-prefix key EOL
array-heading   = heading-prefix key array-sigil EOL
sub-array-heading = heading-prefix array-sigil EOL
scalar-heading  = heading-prefix key kv-sep value EOL
level-pop       = 1*"#" EOL

bare-field      = key kv-sep value EOL
multiline-field = key ":" EOL blockquote-block
blockquote-block = 1*blockquote-line
blockquote-line = ( "> " *line-char / ">" ) EOL

array-item      = scalar-item / object-item
scalar-item     = "- " value EOL
object-item     = ( "-" / "- " key kv-sep value ) EOL
indent-field    = INDENT key kv-sep value EOL
INDENT          = 2SP

key             = bare-key / json-string
bare-key        = 1*( ALPHA / DIGIT / "_" / "-" )

value           = json-string / json-number / "true" / "false" /
                  "null" / bare-string
bare-string     = 1*line-char

kv-sep          = ":" SP
blank-line      = EOL
EOL             = LF
line-char       = SP / VCHAR / uni-char
uni-char        = %x80-D7FF / %xE000-10FFFF

json-string     = DQUOTE *json-char DQUOTE
json-char       = json-unescaped / json-escaped
json-unescaped  = %x20-21 / %x23-5B / %x5D-D7FF / %xE000-10FFFF
json-escaped    = "\" ( %x22 / "\" / "/" / "b" / "f" / "n" /
                  "r" / "t" / "u" 4HEXDIG )
json-number     = ["-"] json-int [json-frac] [json-exp]
json-int        = "0" / ( %x31-39 *DIGIT )
json-frac       = "." 1*DIGIT
json-exp        = ( "e" / "E" ) ["+" / "-"] 1*DIGIT
~~~

The rules `json-string` and `json-number` are equivalent to the
`string` and `number` productions of Sections 7 and 6 of {{!RFC8259}}.
The core rules `ALPHA`, `DIGIT`, `HEXDIG`, `SP`, `LF`, `VCHAR`, and
`DQUOTE` are those of {{!RFC5234}}, Appendix B.1.

## Prose Constraints   {#prose-constraints}

The following constraints are normative but not expressed in the ABNF:

1. A `bare-string` MUST NOT be produced where the same character
   sequence would match `json-number`, `true`, `false`, or `null`;
   such values MUST be emitted as `json-string`. A `bare-string` MUST
   NOT begin with `"` (%x22), `# ` (%x23.20), or `- ` (%x2D.20), and
   MUST NOT be exactly `-`. A scalar array item whose string content
   contains `: ` (%x3A.20) MUST be emitted as `json-string` -- an
   unquoted item matching the `key kv-sep value` pattern denotes an
   object item, not a string.

2. `frontmatter-line` and `bare-field` share a surface syntax; they
   are distinguished by position. Lines before the root heading are
   frontmatter; lines after it are body fields.

3. Heading depth expresses nesting: a heading with N `#` characters
   opens (or, for `level-pop`, returns to) a scope at depth N. The
   parser maintains a depth-indexed scope stack; hierarchy is never
   expressed by indentation. An `indent-field` is valid only while an
   array object item is open, and appends a field to that item.

4. A `level-pop` (anonymous heading) at depth N returns to the scope
   established at depth N, closing all deeper scopes. At depth 1 it
   returns to the root scope. An anonymous heading never opens an
   object; an object keyed by the empty string is expressed with a
   quoted empty key (`## ""`).

5. A `blank-line` resets the scope stack to the root scope, except
   within an array body where a blank line followed by an array item
   is cosmetic.

6. Trailing spaces and tabs on any line are insignificant and MUST be
   stripped before interpretation; a string value with significant
   leading or trailing whitespace MUST be emitted as `json-string`.
   A conforming generator MUST NOT emit trailing whitespace.

7. `EOL` is a bare LF in canonical form. A conforming parser MUST
   accept an optional CR immediately preceding LF (CRLF tolerance);
   a CR not followed by LF MUST be rejected with a parse error. A
   single leading `BOM` (U+FEFF) MUST be consumed and ignored; a
   conforming generator MUST NOT emit one.

8. `INDENT` is exactly two spaces in canonical form; a conforming
   parser MUST accept any non-empty run of spaces and/or horizontal
   tabs as an indent.

## The One-Document Rule   {#one-document}

A JMD byte sequence -- a file, an HTTP message body {{RFC9110}}, a
Server-Sent-Events event payload, an MCP message -- contains exactly
one document. Multiplexing
is the transport's responsibility: one framing unit, one document.
After the root heading, a second labelled depth-1 heading or a mode
marker MUST be rejected with a parse error; it MUST NOT be silently
ignored and MUST NOT open a second document.

# Canonical Parse Result   {#parse-result}

A conforming parser returns every successfully parsed document as an
**envelope** with exactly four members:

mode:
: One of `data`, `query`, `schema`, `delete`, derived from the mode
  marker of the root heading. Absence of a marker denotes `data`.

label:
: The root heading's label text with the mode marker and any trailing
  `[]` sigil stripped. Labels are opaque: they carry no parser
  semantics and are never serialized into the value.

frontmatter:
: A JSON object holding the frontmatter fields. Always present; empty
  (`{}`) when the document has no frontmatter. A parser MUST preserve
  unknown frontmatter keys and surface them to the application layer;
  dropping them before the application can inspect them is
  non-conformant.

value:
: The JSON value denoted by the document body.

Expressed as a JSON shape:

~~~ json
{ "mode": "data", "label": "Order",
  "frontmatter": {}, "value": { "id": 42 } }
~~~

## Prose Is a Parse Error

A body line that is not a field, an indented continuation, an array
item, a blockquote line, a heading, or a thematic break MUST be
rejected with a parse error. It MUST NOT be silently dropped and MUST
NOT be returned as an empty or partial value. This rule is what makes
the format's failure mode a visible error rather than silent data
loss.

## Roundtrip Contract

Every valid data document denotes exactly one JSON value. Every JSON
value has at least one JMD representation, and exactly one canonical
representation (Section {{core-grammar}}). The roundtrip
JSON -> JMD -> JSON preserves the value up to the normalization
freedoms of {{!RFC8259}} (object member order, number formatting).
Multiple valid JMD representations may denote the same value;
interoperability requires agreement on the value, not on the byte
sequence.

# Document Modes   {#document-modes}

The root heading's mode marker selects one of four document modes.
All four share the complete body grammar of Section {{core-grammar}};
the marker is the only syntactic difference, and it appears at
position zero, before any content.

| Marker | Mode   | Purpose |
|--------|--------|---------------------------------------------|
| `#`    | data   | Structured data transport |
| `#?`   | query  | Query by Example -- selection criteria |
| `#!`   | schema | Structure contracts and type declarations |
| `#-`   | delete | Resource deletion by identifier |

Only data documents are in bijection with JSON values. In query and
schema documents, field values are **raw strings**: the parser returns
them verbatim (after the scalar rules of Section {{core-grammar}}) and
MUST NOT attempt structured interpretation of filter or type
expressions. Their semantics are application-defined; common
conventions are collected non-normatively in {{JMD-SPEC}}, Appendix A.

Delete documents identify resources to remove, either as a single
object body carrying identifying fields or as a root array (`#- []`)
of such objects (bulk delete). Because a delete document carries
destructive intent in the document itself, Section
{{security-considerations}} applies specifically to this mode.

Error responses are data documents using the label `Error` by
convention, carrying `status`, `code`, and optional `message`,
`suggestion`, and `context` fields. The label is a convention, not a
reservation: whether a response is an error is determined first by
the transport's error signal where one exists, and only second by the
label. A future revision is expected to promote errors to a dedicated
mode marker.

# Streaming   {#streaming}

JMD is line-oriented: every completed line is an independently
processable event, and no closing delimiter is ever required. A
streaming parser emits SAX-style events as each line's terminator
arrives:

| Line | Event | Payload |
|------|-------|---------|
| root heading (after frontmatter) | DOCUMENT_START | mode, label, frontmatter |
| `key: value` | FIELD | key, parsed value |
| `key:` (empty value) | FIELD_START | key; value follows as multiline |
| `> text` | FIELD_CONTENT | incremental multiline content |
| `## key` | OBJECT_START | key |
| `## key[]` | ARRAY_START | key |
| `-` / `- key: value` | ITEM_START | new object item |
| `- value` | ITEM_VALUE | parsed scalar item |
| anonymous heading | scope closures | implicit OBJECT_END / ARRAY_END events |
| blank line (non-cosmetic) | SCOPE_RESET | implicit closures to root |

DOCUMENT_START carries the complete envelope header; body events do
not re-transmit it. Scopes close implicitly on shallower headings,
level-pops, non-cosmetic blank lines, and end of input.

**Lookahead.** Streaming requires a single line of lookahead in
exactly one case: a blank line inside an array body defers its scope
decision until the next non-blank line is known (cosmetic before an
array item; SCOPE_RESET otherwise). No other construct requires
lookahead or buffering.

**Framing and truncation.** Each framing unit carries exactly one
document (Section {{one-document}}). A receiver MAY act on events
before the document is complete, subject to the truncation-safety
requirement of Section {{security-considerations}}. An error cannot
be signalled in-band after a partial document; transports signal
mid-stream failure through their own mechanisms.

# Conformance   {#conformance}

JMD defines two conformance levels, applying the robustness principle
as a formal requirement: be conservative in what you generate, liberal
in what you accept.

## Generator Conformance (Strict)

A conforming generator MUST produce output matching the grammar of
Section {{core-grammar}} including its prose constraints. In
particular it MUST: label the root heading; quote all values and keys
that the mandatory-quoting rules require; emit bare `-` array items
with a level-pop after any record that opened a nested sub-structure
and is followed by further records; emit LF line endings, two-space
indents, no trailing whitespace, and no byte order mark; and emit
untrusted content only as quoted strings (Section
{{security-considerations}}).

## Parser Conformance (Tolerant)

A conforming parser MUST accept everything a conforming generator
produces, and additionally MUST accept:

- anonymous root headings (empty label);
- thematic breaks (`---`): consumed as decoration within array
  bodies, tolerated around the frontmatter block -- never an item
  separator, never a scope terminator;
- depth-qualified and depth+1 array items (`## -`, `## - key: value`);
- cosmetic blank lines before headings and between array items;
- YAML-style block-scalar introductions (`key: |`, `key: >`) as an
  alternative to the empty-value multiline form;
- repeated sibling headings without `[]` promoted to an array,
  subject to the three structured error conditions of {{JMD-SPEC}}
  Section 7.4;
- CRLF line endings, a single leading BOM, and tolerant indent forms
  (Section {{core-grammar}}, prose constraints 7 and 8).

A parser MUST reject with a visible parse error: prose in the body
(Section {{parse-result}}), a lone CR, a second root heading or
mid-document mode marker (Section {{one-document}}), and the
structured error conditions of array promotion. Silent dropping of
input is non-conformant in every case.

A conformance fixture suite covering the canonical grammar, every
tolerance, and the must-reject cases is maintained with {{JMD-SPEC}}
(directory `conformance/`).

# IANA Considerations   {#iana-considerations}

A provisional registration request for the media type
`application/jmd` per {{RFC6838}} is under review with IANA
(media-types@iana.org, May 2026). Publication of this document is
intended to support promotion of that registration. The registration
template follows; its authoritative source is maintained in the
specification repository (`iana/application-jmd.md`).

Type name:
: application

Subtype name:
: jmd

Required parameters:
: None

Optional parameters:
: None

Encoding considerations:
: JMD is a text format and MUST be encoded as UTF-8 {{!RFC3629}}.
  Documents consisting entirely of ASCII characters are 7-bit safe.

Security considerations:
: See Section {{security-considerations}} of this document.

Interoperability considerations:
: Every valid data document is in bijection with a JSON value
  (Section {{parse-result}}). Line endings and byte order mark
  handling are defined in Section {{core-grammar}}, prose
  constraint 7.

Published specification:
: This document, and {{JMD-SPEC}}.

Applications that use this media type:
: MCP servers for LLM tool integration; REST APIs with LLM agent
  clients; streaming data pipelines with line-level event processing;
  LLM-generated structured output in agentic workflows;
  service-to-service data exchange; configuration files.

Fragment identifier considerations:
: None.

Additional information:
: File extension `.jmd`; no magic number; Macintosh file type TEXT.

Person and email address to contact:
: Andreas Ostermeyer <andreas@ostermeyer.de>

Intended usage:
: COMMON

Restrictions on usage:
: None

Author/Change controller:
: Andreas Ostermeyer <andreas@ostermeyer.de>

A future revision of this document may additionally request
registration of `+jmd` as a structured syntax suffix per {{RFC6839}}.

# Security Considerations   {#security-considerations}

JMD inherits the security posture of `application/json`, with one
format-specific addition (structure injection). The normative
treatment mirrors Section 24 of {{JMD-SPEC}}.

**Structure injection in naive generation.** JMD assigns structural
meaning to line starts. A generator that interpolates untrusted text
into a document without quoting hands that text structural power:
injected headings, fields, frontmatter directives, or an attempted
mode switch. Untrusted content MUST be emitted as quoted strings with
{{!RFC8259}} escaping; a generator MUST NOT interpolate untrusted
text into bare-value, key, label, or frontmatter position. The
one-document rule (Section {{one-document}}) bounds the damage of a
missed quoting step: an injected root heading or mode marker
mid-document is a parse error, not a second, potentially destructive
document.

**Delete documents in pipelines.** A delete document carries
destructive intent in the document itself and can traverse queues,
logs, and relay agents. Sinks SHOULD execute delete documents only
from explicitly allowlisted sources, and treat archived delete
documents as sensitive to replay.

**Parser resource consumption.** Parsing is O(n) time and O(d) stack
depth. The grammar places no bound on depth, line length, or field
count; implementations SHOULD enforce practical, configurable bounds
(a reasonable default depth bound is 32). Exceeding a resource bound
is a resource-limit error, not a conformance violation.

**Content confusion with Markdown.** JMD is not guaranteed to be
valid CommonMark {{CommonMark}} (heading depth beyond six; the mode
markers `#!`, `#?`, `#-` are not ATX headings). Renderers MUST dispatch on the
declared media type, never on content sniffing.

**No active content.** JMD has no scripting, template expansion,
external references, or anchor/alias mechanism; parsing triggers no
network access, code execution, or I/O.

**Privacy.** Documents are opaque structured data; URI-valued fields
are application data that no conforming parser follows.

**Streaming truncation safety.** A receiver acting on events before a
document is complete MUST ensure such actions are safe under
truncation; a truncated document plus a transport error signal MUST
NOT be treated as a complete document.

--- back

# Acknowledgments
{:numbered="false"}

JMD owes structural debts to JSON {{RFC8259}} and CommonMark, and --
most directly -- to the corpus of Markdown on which large language
models are trained. Thanks to the IANA media-types reviewers for
early feedback on the registration request.

# Companion Documents
{:numbered="false"}

- The JMD Specification {{JMD-SPEC}} contains the normative grammar
  with extensive examples, the non-normative convention appendix for
  query and schema expressions, and the design rationale.
- The JMD-over-HTTP proposal {{JMD-HTTP}} describes how JMD composes
  with HTTP-based REST APIs, including content negotiation, method
  mappings, and streaming over chunked transfer encoding.
