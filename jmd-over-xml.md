# JMD over XML

## Companion Specification — Draft 0.4

Copyright (c) 2026 Andreas Ostermeyer <andreas@ostermeyer.de>. All rights reserved.
Licensed under CC BY-NC-SA 4.0 — see LICENSE-SPEC for details.

---

## 1. Overview

This document defines a lossless mapping between XML documents and JMD, the JSON
Markdown format defined in the JMD Format Specification. It is a companion document
to the core JMD specification and does not modify it.

**Scope:** This mapping targets *data XML* — XML used for machine-to-machine data
exchange, where elements contain either child elements or text content, but not both
interleaved. Examples include OOXML (WordprocessingML, DrawingML, SpreadsheetML),
SOAP, XRechnung, XBRL, NETCONF, Maven POM, and Android resource files.

**Out of scope:** *Document XML* with mixed content — text nodes interleaved with
element nodes within the same parent (e.g. `<p>Hello <b>world</b></p>` in ODF,
XHTML, or HTML). Mixed content has no equivalent in the JSON value space and
therefore cannot be represented in JMD without loss.

**Relation to the JMD core specification:** JMD's lossless guarantee is defined
over the JSON value space: every valid JMD data document maps to exactly one JSON
value. This companion defines a parallel guarantee over the XML infoset: every
data XML document maps to exactly one JMD document, and back, preserving element
names, attributes, text content, namespace bindings, and document order.

This companion targets XML as its serialization goal, not JSON. A JMD over XML
document is therefore not expected to satisfy the JSON-bijection invariant of the
core specification — repeated sibling headings with the same label are valid and
lossless within this mapping.

The JMD syntax is unchanged. No new syntax elements are introduced. The mapping
is defined by four rules, each using only standard Markdown constructs in their
natural meaning.

---

## 2. Mapping Rules

### 2.1 Elements → Headings

Every XML element maps to a JMD heading. The heading label is the element's
qualified name (prefix:localname), preserving the namespace prefix exactly as
written in the source document.

Heading depth reflects nesting depth in the XML tree:

- Root element → `# qname`
- Child elements → next heading level (`##`, `###`, ...)

There is no depth limit. XML documents with nesting beyond six levels (the
conventional Markdown `######` boundary) use extended heading markers
(`#######`, `########`, ...). JMD parsers must support arbitrary heading
depth.

Document order is preserved by heading order. Repeated sibling elements with
the same qualified name produce repeated headings at the same depth — this is
valid in JMD over XML:

```xml
<w:body>
  <w:p w:rsidR="00000001"/>
  <w:tbl/>
  <w:p w:rsidR="00000002"/>
</w:body>
```

```markdown
## w:body

### w:p
"w:rsidR": 00000001

### w:tbl

### w:p
"w:rsidR": 00000002
```

### 2.2 Attributes → Fields

Each XML attribute maps to a JMD key-value field immediately under the heading
of its element. The key is the attribute's qualified name.

Attribute keys containing characters outside `[a-zA-Z0-9_-]` — including the
colon in namespace-qualified names — are quoted per JMD Section 4.2:

```xml
<w:p w:rsidR="00B84FB8">
  <w:pStyle w:val="Normal"/>
</w:p>
```

```markdown
## w:p
"w:rsidR": 00B84FB8

### w:pStyle
"w:val": Normal
```

Namespace declarations (`xmlns:prefix="uri"`) are treated as regular attributes:

```xml
<w:document
  xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
```

```markdown
# w:document
"xmlns:w": http://schemas.openxmlformats.org/wordprocessingml/2006/main
"xmlns:r": http://schemas.openxmlformats.org/officeDocument/2006/relationships
```

### 2.3 Text Content → Implicit Attribute

Text content is treated as an implicit attribute of its element, using the
reserved key `_` (unquoted).

**Text-only element without other attributes** — use the compact scalar heading form:

```xml
<w:t>Hello</w:t>
```

```markdown
### w:t: Hello
```

**Text content coexisting with explicit attributes** — use the reserved key `_`:

```xml
<w:t xml:space="preserve"> World</w:t>
```

```markdown
### w:t
"xml:space": preserve
_: " World"
```

**Disambiguation:** If an XML element has a literal attribute named `_`, that
attribute is written as the quoted key `"_"`, keeping the unquoted `_`
exclusively for text content:

```xml
<elem _="meta"> World</elem>
```

```markdown
### elem
"_": meta
_: " World"
```

### 2.4 Empty Elements

An element with no attributes, no text content, and no child elements maps to
a heading with no fields:

```xml
<w:b/>
```

```markdown
#### w:b
```

---

## 3. Complete Example

The following WordprocessingML fragment illustrates all four mapping rules:

**XML:**

```xml
<w:document
  xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>
    <w:p w:rsidR="00B84FB8">
      <w:pPr>
        <w:pStyle w:val="Normal"/>
        <w:jc w:val="center"/>
      </w:pPr>
      <w:r>
        <w:rPr>
          <w:b/>
          <w:color w:val="FF0000"/>
        </w:rPr>
        <w:t>Hello</w:t>
      </w:r>
      <w:r>
        <w:t xml:space="preserve"> World</w:t>
      </w:r>
    </w:p>
    <w:tbl/>
    <w:p w:rsidR="00B84FB9"/>
  </w:body>
</w:document>
```

**JMD:**

```markdown
# w:document
"xmlns:w": http://schemas.openxmlformats.org/wordprocessingml/2006/main
"xmlns:r": http://schemas.openxmlformats.org/officeDocument/2006/relationships

## w:body

### w:p
"w:rsidR": 00B84FB8

#### w:pPr

##### w:pStyle
"w:val": Normal

##### w:jc
"w:val": center

#### w:r

##### w:rPr

###### w:b

###### w:color
"w:val": FF0000

##### w:t: Hello

#### w:r

##### w:t
"xml:space": preserve
_: " World"

### w:tbl

### w:p
"w:rsidR": 00B84FB9
```

---

## 4. Schema Extensions

The JMD schema document (`#!`) can be extended to declare the XML serialization
role of each field — distinguishing XML attributes from XML child elements, and
identifying the text-content field. This information is required for lossless
JMD→XML serialization.

Schema extensions for XML are appended to the standard `#!` document under the
heading `## xml`:

```markdown
#! w:p
"w:rsidR": string optional
## xml
attributes: "w:rsidR"
```

| Schema field | Meaning |
| --- | --- |
| `attributes` | Space-separated list of keys that serialize as XML attributes |
| `text` | Key that serializes as XML text content (default: `_`) |
| `namespace` | Default namespace URI for this element |

When no schema is present, a JMD→XML serializer may apply heuristics: quoted
keys containing `:` are treated as attributes; the `_` key serializes as text
content; all other keys are treated as child elements.

---

## 5. Lossless Guarantee

A roundtrip XML → JMD → XML preserves:

- Element qualified names and nesting structure
- Attribute qualified names and values
- Text content
- Namespace prefix bindings
- Document order of elements within each parent
- Empty elements

The following are not preserved (XML specification, not this mapping):

- Attribute order within an element (XML attributes are unordered)
- XML declaration (`<?xml version="1.0"?>`)
- Processing instructions
- XML comments
- CDATA section boundaries (content is preserved, CDATA wrapping is not)
- Insignificant whitespace between elements
- Redundant namespace re-declarations: a namespace prefix already declared on
  an ancestor element that is re-declared identically on a descendant is
  dropped. The XML infoset is unchanged; only the redundant declaration is
  omitted. This matches the behavior of canonical XML (C14N).

---

## 6. AI Whispering

This mapping was designed under the AI Whispering methodology defined in the
core JMD specification: every syntax decision passes the test *"Would an LLM
produce this naturally, without special instruction?"*

The mapping consists of four rules, each using a standard Markdown construct
in its natural meaning:

- **Qualified names as heading labels** — LLMs know `w:body`, `a:spPr`,
  `c:chart` from OOXML documentation and code. When asked to describe XML
  structure in Markdown, they naturally write these as headings.
- **Quoted keys for namespace-qualified attributes** — LLMs follow JMD's own
  quoting rules instinctively: colons in keys trigger quoting.
- **`_` for text content** — The underscore as a default or implicit slot is
  deeply familiar from Python, destructuring, and i18n. LLMs reach for
  `_: value` naturally when representing implicit content.
- **Repeated headings for repeated elements** — When an LLM describes a
  sequence of XML elements in Markdown, it writes one heading per element
  in document order. It does not invent array syntax spontaneously. The
  mapping aligns with this natural behavior.

The result is the simplest possible mapping: every XML element is a heading,
every attribute is a field, text content is an implicit field. No arrays,
no ordered lists, no tag fields, no special cases. Four rules, no exceptions.
