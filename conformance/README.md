# JMD Conformance Test Suite

This directory contains the canonical test fixtures for the JMD format
specification. Every conforming implementation — `jmd-format` on PyPI,
`jmd-format` on npm, and any future port to other languages — is expected
to pass these tests.

## Layout

Fixtures are organized by document mode:

    conformance/
    ├── data/        # # Label — data documents
    ├── schema/      # #! Label — schema documents (planned)
    ├── query/       # #? Label — query documents (planned)
    ├── delete/      # #- Label — delete documents (planned)
    ├── tolerance/   # parser-tolerance cases (non-canonical input)
    └── must-fail/   # inputs a conforming parser MUST reject

## Fixture Format

Each fixture is a pair of files that share a base name:

    <name>.jmd       # the canonical JMD document
    <name>.json      # the JSON value the document represents

`<name>.jmd` is the byte-exact form a conforming serializer must produce.
`<name>.json` is the value a conforming parser must extract. Both files
end with a single newline.

Mode, label, and frontmatter live in the `.jmd` file only (the `.json`
represents only the data value). A test runner parses the `.jmd` to
learn these — Parse-test validates the data, Serialize-test
reconstructs the full `.jmd` from the `.json` value plus the extracted
mode, label, and frontmatter.

## The Three Tests

For each fixture, a conforming implementation must pass:

1. **Parse** — `parse(jmd).value` deep-equals the value in `.json`.
2. **Serialize** — `serialize(value, label, frontmatter)` equals `.jmd`
   byte-for-byte, where `value` comes from `.json` and `label` and
   `frontmatter` are reconstructed from the `.jmd` root heading and
   preamble.
3. **Round-trip** — `parse(serialize(parse(jmd).value, ...))` yields the
   same value. Follows structurally from 1 and 2.

## Tolerance Fixtures

The `tolerance/` subdirectory contains fixtures that exercise
parser-tolerance rules — inputs a conforming generator would not emit
(the canonical output is in `data/`), but that a conforming parser MUST
accept. Examples include depth-qualified array items (`## -`, §8.6a) and
depth+1 items (`## - key: val` under a depth-1 array heading, §8.6b).

Only the **Parse** test applies: `parse(jmd).value` deep-equals the
value in `.json`. The Serialize and Round-trip tests are not run against
tolerance fixtures, because serializing the parsed value re-canonicalizes
it (to bare `-` items with thematic-break separators) and so will not
match the non-canonical input byte-for-byte.

## Must-Fail Fixtures

The `must-fail/` subdirectory contains JMD inputs that a conforming
parser MUST reject with a structured error. Fixture format:

    <name>.jmd            # input the parser must reject
    <name>.error.json     # structured description of the expected error

`<name>.error.json` carries a minimal structured description:

```json
{
  "kind": "repeated_scalar_key",
  "line": 5,
  "key": "x"
}
```

The `kind` field identifies the error category and MUST match across
all backends. The `line` field identifies the offending source line.
Additional fields (`key`, `depth`, `form`) are category-specific and
advisory; backends MAY include implementation-specific extras.

The Must-Fail test asserts only that parsing raises an error and that
the error's structured description matches the expected `kind` and
`line`. Error message wording and exception class identity are
implementation-specific.

The canonical error kinds for v0.3.5 are:

| `kind` | Specification section |
|---|---|
| `sigil_conflict` | §7.4.2(a) |
| `repeated_explicit_array` | §7.4.2(b) |
| `repeated_scalar_key` | §7.4.2(c) |
| `prose_in_body` | §3.6.2, §11.2 |
| `lone_carriage_return` | §11.2 |
| `second_root_heading` | §18.0 |
| `mode_marker_mid_document` | §18.0 |

Additional kinds will be added as the specification gains new
structured-error categories.

## Canonical Form

The canonical form is the output any conforming serializer must produce
given a value, a label, and optional frontmatter. Both `jmd-format` on
PyPI (Python) and `jmd-format` on npm (JavaScript) emit byte-identical
documents for the same input:

- **Object fields** appear in insertion order. When a nested object or
  array is followed by more scalar fields of the same object, those
  scalars are emitted as scalar-valued headings (`## key: value`) — this
  is how the format expresses scope return within an insertion-ordered
  stream.
- **A blank line** precedes each nested heading (object or array) inside
  an object scope. The document opens with the root heading on its first
  line with no leading blank.
- **Numbers** are formatted as the shortest round-trippable decimal
  representation (JavaScript `String(n)`, Python `str(n)`). For typical
  JSON-sourced values the two agree byte-for-byte.
- **Strings** are bare unless quoting is required (§6.1) or the string
  starts with a double quote, contains a newline, or contains a tab.
  Internal double quotes and backslashes are left bare — the parser is
  tolerant enough to accept them, matching the Python C-accelerated
  serializer.
- **Arrays of objects** place the first scalar field on the `- ` line;
  remaining scalar fields follow as 2-space-indented continuation
  lines; nested structures come last as headings at the item's depth.
  When items contain nested structures, a thematic break (`---`) on its
  own line — preceded by one blank line and followed directly by the
  next `- ` — separates successive items (§8.6).
- **Root arrays** use `# <label>[]`; when no meaningful label is
  available, the canonical form is `# []`.
- **Multiline strings** (any string containing `\n`) use the blockquote
  (`> `) form.
- **Frontmatter** appears above the root heading, separated by one
  blank line.
- **Document termination.** The serializer returns its output without a
  trailing newline (matching the Python reference byte-for-byte). The
  `.jmd` fixture files add a single trailing newline as the customary
  POSIX line terminator.

## Running the Tests

The JavaScript implementation (`jmd-js`) expects this directory at
`../jmd-spec/conformance/` relative to its repo root, or at a path
given by `JMD_FIXTURES`. The Python implementation will adopt the
same convention.

## Adding Fixtures

New fixtures are welcome. A fixture should isolate a single aspect of
the format — keep each example minimal. Name it after what it tests
(`arrays-object`, not `order-example`). Pair the `.jmd` and `.json`
files, and verify round-trip locally before submitting.
