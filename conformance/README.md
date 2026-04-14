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
    └── delete/      # #- Label — delete documents (planned)

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

## Canonical Form

The canonical form is the output any conforming serializer must produce
given a JavaScript/JSON value, a label, and optional frontmatter:

- **Object fields** appear in insertion order, but scalar fields precede
  nested structures (objects and arrays). This keeps documents readable
  and avoids scalar headings for scope return.
- **Numbers** are formatted as the shortest round-trippable decimal
  representation (JavaScript `String(n)`, Python `str(n)`).
- **Strings** are bare unless quoting is required by §6.1 (mandatory
  quoting triggers). Ambiguous values (strings parsable as number,
  boolean, or null) are always quoted.
- **Arrays of objects** place the first scalar field on the `- ` line;
  remaining scalar fields follow as 2-space-indented continuation
  lines; nested structures come last as headings at the item's depth.
- **Multiline strings** (any string containing `\n`) use the blockquote
  (`> `) form.
- **Frontmatter** appears above the root heading, separated by one
  blank line.
- The document ends with a single newline.

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
