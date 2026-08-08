# JMD over JSONC

## Companion Specification — Draft 0.1 (ST-Pilot)

Copyright (c) 2026 Andreas Ostermeyer <andreas@ostermeyer.de>.
Licensed under CC BY 4.0 — see [LICENSE](LICENSE) for details.

**Status:** Draft. Promoted from `jmd-sublime/specs/` to this repository
so it sits with the other companion specifications; the mapping itself is
still being validated against real Sublime Text configuration files. The
reference implementation is `jmd/_jsonc*.py` in
[jmd-sublime](https://github.com/ostermeyer/jmd-sublime); the core parsers
(`jmd-impl`, `jmd-js`) do not yet recognise the comment markers this
document defines.

---

## 1. Overview

This document defines a lossless mapping between JSONC documents and JMD,
the JSON Markdown format. JSONC is JSON extended with line comments
(`// …`), block comments (`/* … */`) and trailing commas — the format
Sublime Text uses for the bulk of its configuration files
(`.sublime-settings`, `.sublime-keymap`, `.sublime-color-scheme`,
`.sublime-theme`, `.sublime-mousemap`, `.sublime-build`,
`.sublime-completions`, `.sublime-menu`, `.sublime-commands`).

**Scope:** This mapping targets JSONC as ST consumes it: the JSON value
model (objects, arrays, strings, numbers, booleans, null) plus comments
and trailing commas as the only out-of-spec extensions. Configuration
files that go beyond JSONC (template substitution, embedded code) are
out of scope.

**Relation to the JMD core specification:** JMD's lossless guarantee is
defined over the JSON value space. Comments are not part of the JSON
value space — they are file-level metadata. This companion extends the
JMD syntax with two **comment markers** that carry comment metadata
through the round-trip; the markers are recognized only in this
companion's context, not by the core JMD spec.

The two new comment markers are mode-marker variants of the same
family as the core's `# `, `#? `, `#! `, `#- `:

* `#/ <text>`     — single-line comment, sequence-level element
* `#* Comment`    — block-comment-section, body in `>`-blockquote

Both markers carry depth-prefix (`##/`, `###/`, `##*`, …) reflecting
their nesting level inside the JMD document, mirroring the core
heading-depth convention so an LLM consuming the document keeps the
depth-overview without further cues.

This companion additionally **constrains** the core JMD frontmatter
syntax: frontmatter delimiters (`---`) are mandatory in this
companion's context, including for documents with no frontmatter
content. Rationale: core JMD permits the `---` markers but does not
require them, identifying frontmatter positionally (everything before
the first `# Heading`). That works syntactically but is fragile
cognitively — LLMs reading or writing such documents can conflate
frontmatter fields with body fields, since both are `key: value`
shaped. Mandatory delimiters restore the visual boundary and remove
the ambiguity. The constraint is companion-scoped; core JMD documents
remain unaffected.

---

## 2. Mapping Rules

### 2.1 Objects → Sections

Every JSONC object maps to a JMD section. The root object becomes the
document's root heading; nested objects become sub-sections at the
appropriate depth.

```jsonc
// Root object
{
    "name": "Bob",
    "address": {
        "city": "Owschlag"
    }
}
```

```jmd
---
---
# Root

name: Bob

## address
city: Owschlag
```

The root heading label is supplied by the caller (typically the file's
type — `Settings`, `Keymap`, `ColorScheme`). It is **not** derived from
the JSONC source, which has no equivalent slot.

### 2.2 Object members → Fields

String-keyed object members map to JMD fields. Keys requiring quoting
in JMD (whitespace, structural-prefix collisions, …) follow the core
JMD quoting rules; otherwise they appear bare.

```jsonc
{
    "tab_size": 4,
    "translate_tabs_to_spaces": true
}
```

```jmd
---
---
# Settings

tab_size: 4
translate_tabs_to_spaces: true
```

### 2.3 Arrays → Array fields or array sub-sections

Short scalar arrays use the inline array-field form (`field[]:` followed
by bullet items). Arrays of objects use a sub-section heading (`## field[]`)
followed by bullet items per object, mirroring the core JMD array
patterns.

```jsonc
{
    "rulers": [80, 100],
    "build_systems": [
        { "name": "Python", "cmd": ["python3", "$file"] },
        { "name": "Make",   "cmd": ["make"] }
    ]
}
```

```jmd
---
---
# Project

rulers[]:
- 80
- 100

## build_systems[]
- name: Python
  cmd[]:
  - python3
  - $file
- name: Make
  cmd[]:
  - make
```

### 2.4 Scalars

JSONC scalars (string, number, boolean, null) round-trip through JMD's
scalar grammar without information loss. Strings that JSON requires to
be quoted but JMD accepts bare (no whitespace, no structural prefix)
are emitted bare on the JMD side; the JSONC serializer re-quotes them.

### 2.5 Line comments → `#/` markers

A JSONC line comment (`// text`) maps to a JMD `#/`-marker on its own
line. The depth-prefix matches the nesting level of the surrounding
section — a comment inside a depth-2 section uses `##/`, inside
depth-3 uses `###/`, etc.

The comment occupies its **literal sequence position**: a comment
written before a field appears before it in JMD; a trailing comment
on the same line as a field becomes a `#/`-marker on the line
following that field. Trailing-on-same-line semantics (line-position)
is the only data-loss in this mapping; sequence-order is preserved
exactly.

```jsonc
{
    // How many spaces a tab is equivalent to.
    "tab_size": 4,

    "rulers": [80, 100]  // ruler positions
}
```

```jmd
---
---
# Settings

#/ How many spaces a tab is equivalent to.
tab_size: 4

rulers[]:
- 80
- 100
#/ ruler positions
```

### 2.6 Block comments → `#*` markers

A JSONC block comment (`/* … */`) maps to a JMD `#*`-section with the
fixed label `Comment`. The comment body appears as a `>`-blockquote;
each source line becomes one blockquote line. The block-section is
**always** followed by a blank line before the next data element,
following Markdown's blockquote-termination convention.

The depth-prefix follows the same rule as line comments: `#*` at
depth 1, `##*` at depth 2, etc.

The label slot is optional. Three forms are valid: ``#*`` (no
label, terse), ``#* comment`` (lowercase), ``#* Comment``
(canonical). Conformant generators emit the canonical form;
conformant parsers accept all three. Other labels are invalid —
JSONC has no label slot, so a free label could not round-trip
back. Spec §4.2 has the formal grammar.

```jsonc
{
    /* Default surface colors for the editor.
       Used by widgets if no explicit override is set. */
    "globals": {
        "foreground": "#fff"
    }
}
```

```jmd
---
---
# ColorScheme

#* Comment
> Default surface colors for the editor.
> Used by widgets if no explicit override is set.

## globals
foreground: "#fff"
```

### 2.7 Trailing commas

JSONC permits a trailing comma after the last item in an object or
array. The comma carries no information; it is silently dropped on
parse and never emitted on serialize. JMD has no trailing-comma
notion.

---

## 3. Round-trip guarantees

**JSONC → JMD → JSONC:** byte-equivalent for the JSON value content.
Comments are preserved with their sequence-order intact. The single
permitted lossy case is **trailing-on-same-line** comments, which
become same-position-on-following-line in the JMD intermediate and
re-emerge as following-line comments in the JSONC output. This is
explicit in §2.5.

**JMD → JSONC → JMD:** byte-equivalent. No information is lost in
this direction.

Whitespace between data tokens (blank lines, indentation choices) is
**not** preserved. Both serializers emit canonical whitespace per the
respective format conventions.

---

## 4. Syntax extensions — formal

This section formalizes the syntax extensions and constraints that
this companion adds to core JMD. They are scoped to this companion's
context: core JMD parsers are not required to recognize the comment
markers (they SHOULD silently skip unknown `#`-prefixed mode-markers
under parser-tolerance), and core JMD documents are not required to
emit mandatory frontmatter delimiters.

### 4.0 Mandatory frontmatter delimiters

Every document in this companion MUST frame its frontmatter with
`---` delimiters, even when the frontmatter is empty.

```
Document     ::= FrontmatterFrame Body
FrontmatterFrame ::= "---" "\n" frontmatter-content "---" "\n"
frontmatter-content ::= ( Field "\n" )*    ; possibly empty
```

* The opening `---` is the first non-blank line of the document.
* The closing `---` precedes the first body heading.
* `frontmatter-content` may be empty; the two delimiters then sit on
  consecutive lines.
* Conformant generators MUST emit both delimiters. Conformant
  parsers MUST require both delimiters and reject documents lacking
  them with a clear error pointing at the missing frame.

This deviates from core JMD, which identifies frontmatter
positionally and treats `---` markers as optional. The companion's
mandatory-frame rule exists because in real-world authoring (LLM
or human), the syntactic similarity between `key: value` frontmatter
fields and `key: value` body fields creates conflation hazards.
Mandatory delimiters convert a positional boundary into a
syntactic one.

### 4.1 Line-comment marker

```
LineComment ::= "#" "#"* "/" " " text-line "\n"
```

* Hash-prefix repetition encodes depth (1 hash = depth 1, 2 = depth 2, …).
* Mandatory single space after `/`.
* `text-line` is arbitrary text up to the line terminator; no escapes,
  no continuation.
* The marker is a sequence-level element: it occupies a position in
  its parent section's content sequence between fields and sub-sections.
* Single-line only — multi-line comment text uses the block-comment
  marker instead.

### 4.2 Block-comment marker

```
BlockComment    ::= BlockCommentHead "\n"
                    ( ">" " " text-line "\n" )+
                    "\n"   ; blank line terminates the body
BlockCommentHead ::= "#" "#"* "*" ( " " ( "Comment" | "comment" ) )?
```

* Hash-prefix repetition encodes depth, identically to line comments.
* The optional label slot accepts the case-insensitive token
  `Comment`. Three forms are valid:
  * `#*`              — no label, terse form.
  * `#* comment`      — lowercase label, parser-tolerant.
  * `#* Comment`      — canonical form.
  Conformant generators emit the canonical form. Conformant parsers
  accept all three. Any other label (e.g. `#* History`) is invalid:
  JSONC has no label slot to round-trip the choice through, so a
  free label would create a lossy field by definition.
* Body is one or more `>`-prefixed blockquote lines, following the
  core JMD blockquote convention (Spec §9).
* Body terminates at the first non-`>` line, including the
  conventional blank line.
* The block-section is itself a sequence-level element in the
  parent's content sequence.

### 4.3 Position semantics

Both markers are **sequence-level** elements: they occupy positions
in their parent section's content sequence interleaved with fields
and sub-sections. A comment written between two fields stays
between them; a comment at the end of a section stays at the end.

Comments do **not** create their own scope — they do not nest things
under them, do not introduce sub-sections beyond their own body
(block comments only), and do not affect the parsing of subsequent
elements.

---

## 5. ST-relevant JSONC files — coverage

This pilot mapping covers all ST configuration files that use the
JSONC format:

| File type                  | Extension                | Notes                              |
|----------------------------|--------------------------|------------------------------------|
| Settings                   | `.sublime-settings`      | Most common; user-facing.          |
| Keymap                     | `.sublime-keymap`        | OS-distribution-aware overrides.   |
| Color scheme               | `.sublime-color-scheme`  | New-format; `.tmTheme` is XML.     |
| Theme                      | `.sublime-theme`         | UI theme rules.                    |
| Mouse map                  | `.sublime-mousemap`      | Mouse binding overrides.           |
| Menu                       | `.sublime-menu`          | Menu layout.                       |
| Commands                   | `.sublime-commands`      | Command palette entries.           |
| Build system               | `.sublime-build`         | Build-system definition.           |
| Completions                | `.sublime-completions`   | Auto-completion entries.           |
| Project                    | `.sublime-project`       | Project file (folders + settings). |

ST configuration files in non-JSONC formats are covered by sister
companions:

* YAML: `.sublime-syntax` — see `jmd-over-yaml.md` (forthcoming).
* XML: `.sublime-snippet`, `.tmPreferences`, `.tmTheme` — see the
  existing `jmd-over-xml.md` companion in the main spec repository.

---

## 6. Open questions

This is a draft. The following points are pending validation against
real ST files and real round-trip exercises:

1. **Empty-key handling.** ST occasionally allows `""` as a key in
   keymap binding contexts. JMD allows quoted-empty keys in principle;
   we want to confirm this round-trips through both directions.
2. **Number-precision.** JSONC numbers can have arbitrary precision in
   the source; Python's `json` module loads them as `int` or `float`,
   losing precision in the float case. This is a JSON-side limitation,
   not specific to this mapping, but worth a note in the parser docs.
3. **Block-comment-with-asterisk-borders.** Some style conventions use
   `/* * line one\n * line two\n */` with a leading `*` on each line.
   The mapping defined here treats these as content (the `*` becomes
   part of the blockquote text). A future refinement could detect and
   strip the convention; not done here for simplicity.
4. **Scalars / arrays / comments after a sub-section.** JMD's
   heading-depth semantics attach all content to the most recently
   opened section unless an explicit depth-marker resets the
   context. When a JSONC source places a scalar field, scalar
   array, or comment **after** a nested object at the same depth,
   the emitter writes it in **scalar-heading form** with the
   parent's depth-prefix — e.g. ``# font: null`` at depth 1, after
   a ``## globals`` sub-section, signals to the parser that
   ``font: null`` is a field of the depth-1 root, not of
   ``globals``. The parser honours the depth-prefix on all
   ``#``-prefixed markers (sections, scalar-headings, comment
   markers) as a return-to-shallower-context trigger. This makes
   round-trip ordering byte-stable for the relative position of
   scalars and sub-sections.
5. **File-level leading comments.** ST configuration files
   sometimes carry a copyright / usage header above the root
   ``{``. The parser silently skips these. A future refinement
   could collect them into a ``preamble`` field on
   :class:`JsoncDoc` and emit them either as a JMD frontmatter
   field or as comments before the root heading; not done here
   pending real-world demand.
6. **Array-internal comments.** Comments inside a JSONC array
   (around items rather than between fields of an object) have no
   clean JMD position when the array is rendered as bullet items.
   The parser drops them silently. The bullet-form would need a
   sibling ``#/`` line under the bullet, which collides with the
   continuation-indent convention; left as future work.
