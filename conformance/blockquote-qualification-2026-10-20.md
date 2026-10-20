# Array-item blockquotes — decision and qualification, 2026-10-20

## Approved rule

Andreas approved canonical two-space indentation for blockquotes belonging
directly to fields of an array object item, with continued parser acceptance of
legacy unindented input. The goal is visible membership in the item, consistent
with Markdown list continuation. Parser acceptance alone is not evidence of
canonical generator conformance.

A first field is emitted as:

```jmd
# Comment[]
- message:
  > Please review.
```

Subsequent fields use the same two-space indentation before their key and before
each quote marker. Paragraph breaks are `  >`. A separate bare item opener
before an available first field remains accepted input; generators emit the
compact first-field form. Empty objects and items beginning with nested
structures retain their bare opener. Frontmatter, ordinary objects and objects
opened by a heading retain unindented quotes.

The spec now states this in sections 8.3, 9.1, 11 and 22.1. The formal grammar
includes multiline first fields and multiline continuation fields.

## Verified baseline

Fresh fetches preceded implementation on 2026-10-20:

| Repository | Baseline | Upstream / state before this change |
| --- | --- | --- |
| jmd-spec | 43760b57f43300401fd82c0bfcba5ff4a598b07d | main = origin/main; clean |
| jmd-impl | c772046f34271f60ae83e42abff23d9382c8b687 | main = origin/main; earlier local Unicode fix and regression test present |
| jmd-mcp-smartsuite | 1ba904459c0731bc4f604373dba6486831a26577 | main = origin/main; earlier local live-feedback follow-ups present |
| jmd-impl/vendor/jmd-spec | 2573b1bbdf3d5b8d4e8d3723130420c4ef38429e | detached, clean, existing gitlink retained; remote fetched |

All three main branches had ahead 0 / behind 0. The gitlink remains at the old
fixture snapshot until a separately requested commit/integration step can pin
the new spec commit. Tests in this pass explicitly use the edited sibling
specification via JMD_FIXTURES. Default tests against the old vendor snapshot
still compare against its old canonical blockquote bytes.

No version was selected or bumped, no dependency lock changed, no runtime
updated, and no commit or push was performed.

## Implementation surface and independent evidence

Python and native C serializers each have separate homogeneous-object-array and
mixed-array paths. All four paths now keep the first field on the item-marker
line and select two-space quote indentation. Their ordinary object-field paths
remain unindented. The shared C multiline helper takes the immediate field scope
explicitly; both object and array callers supply it.

Python, C and streaming parsers already support both quote layouts; no parser
production code was changed for this rule.

Spec fixtures:

- Updated array-record-multiline and blockquote-selected-array to canonical
  indented quotes; retained their original bytes as tolerance fixtures.
- Added canonical first-field, paragraph-break, nested-array/headed-child,
  mixed-array/quoted-key, and explicitly selected one-line quote cases.
- Added tolerance cases for separate openers, legacy unindented quotes and
  mixed space/tab indentation.
- Expected JSON values and canonical JMD bytes are independent fixture oracles.

The new jmd-impl test_array_blockquote_layout.py adds 32 normalization cases
across both backends, field positions, separate openers and indentation forms.
Eight line-by-line streaming cases verify immediate content events, paragraph
breaks, literal quote/list content, and transitions to later fields and items.

## Results

Ruff passed; strict Mypy passed over jmd and both new test modules (32 files).
The C extension was rebuilt for CPython 3.14 before qualification.

Native serializer SHA-256:
aede5adea3a0231ed9258908365e423492fbef8a1fc914c1843ef0d2113b5fb3.

Command after Ruff and Mypy:

```sh
JMD_FIXTURES=/home/andreas/Workspace/jmd-spec/conformance .venv/bin/pytest -q -rs
```

Result: **2,371 passed, 3 skipped**. The three existing skips concern the
unresolved stream-folding semantics of repeated headings (nested, promote and
three); none skips the new blockquote coverage.

A separate SmartSuite comment projection check, using the local JMD source
through PYTHONPATH, verified exact canonical bytes and both parser round-trips
with each serializer backend. SmartSuite's installed dependency remains 0.10.2.
Its old test expecting `-message:` and its repeated note frontmatter issue remain
separate integration work. This pass does not claim a completed dependency
upgrade or qualification of other JMD implementations.

## Separate existing finding: C parser truncates long blockquotes

Core acceptance property: parsing a blockquote preserves every content line,
regardless of whether its length crosses 256 lines.

Source: jmd-impl/jmd/_cparser_multiline.c, parse_blockquote. Fixed arrays hold
256 parts; later lines are consumed without being appended.

Read-only boundary reproduction with direct array-item blockquotes:

| Input lines | C parser result | Python parser result |
| --- | --- | --- |
| 255 | 255 | 255 |
| 256 | 256 | 256 |
| 257 | 256 | 257 |
| 300 | 256 | 300 |

At the end of the syntax task, the native parser was unchanged and this
confirmed data-loss defect remained open. Andreas subsequently authorized its
repair and an audit for the same mechanism. The follow-up below closes the
multiline truncation finding; the earlier 2,371-test result alone did not.

## Authorized follow-up: remove silent multiline truncation

Status: **closed in the local working tree**, not released.

A fresh fetch before this follow-up confirmed jmd-impl c772046f and jmd-spec
43760b57 still matched origin/main (ahead 0 / behind 0); the vendored spec remained
at 2573b1bb. Earlier local changes were retained.

The same fixed 256-part arrays occurred in parse_blockquote and
parse_block_scalar. Thus all three input forms were affected: canonical
blockquotes, tolerated literal blocks (`|`) and tolerated folded blocks (`>`).

Both functions now share a geometrically growing vector of borrowed source
slices. Checked arithmetic bounds the vector allocation and output buffer.
Append failure does not advance the input cursor; allocation or Unicode creation
failure returns NULL with an exception. All exits free owned scratch storage.
Whitespace normalization, paragraph folding and trailing-blank trimming retain
their existing semantics. The production change is confined to
jmd-impl/jmd/_cparser_multiline.c (278 lines).

### Evidence after repair

- test_multiline_capacity.py: 58 cases covering both backends, all three forms,
  255/256/257/300/1,025/8,193 content lines, Unicode, blank runs crossing the old
  boundary, later fields, array-item boundaries, first/continuation fields and
  legacy/canonical quote indentation. A 1,025-field object checks cache eviction
  independently of multiline storage.
- Before the repair: 22 failures, 36 passes. All failures were native data loss;
  the Python controls and cases below the limit passed.
- test_multiline_allocator.py and multiline_allocator_probe.c compile the real
  production translation unit with test-only allocator wrappers. All seven
  failure points for each of the three forms are exercised: five vector growth
  allocations, output allocation and Unicode construction. Each raises
  MemoryError, frees scratch storage, preserves the expected input cursor and
  allows a successful subsequent parse. Two impossible-size guards are checked
  without attempting huge allocations. No test hooks enter the shipped module.
- The probe compiled with -Wall -Wextra -Werror. Qualification ran on Linux,
  CPython 3.14; the probe explicitly skips Windows because its compiler command
  uses POSIX LDSHARED. Windows fault injection was not qualified here.
- Ruff passed; strict Mypy passed over jmd and all four new Python test modules
  (34 files).
- Full suite with PYTHONMALLOC=debug and the edited sibling JMD_FIXTURES:
  **2,451 passed, 3 skipped**. The same three existing repeated-heading stream
  folding skips remain; no multiline test was skipped.
- Independent differential probe: 360 cases from seed 20261020, varied blank
  runs, Unicode, punctuation and 513-byte lines, with 1–2,399 lines per value,
  agreed with the separate Python parser and retained the following field.
- Negative controls: integers of 31/32/33/127/128/1,000 digits retained their
  numeric type and full value.

Loaded native parser SHA-256:
1e0afe2c6878b9d2d2e1bd297b144fe03fcac98d518f340cb75d20a2a76f37a6.

Loaded native serializer SHA-256 remained:
aede5adea3a0231ed9258908365e423492fbef8a1fc914c1843ef0d2113b5fb3.

### Audit of other bounded C-parser storage

The audit covered all six _cparser*.c translation units and the private header.
Object and array accumulation uses Python dictionaries/lists; it has no separate
fixed C content buffer. All direct multiline callers propagate failure.

| Site | Original error or observation | Status / acceptance property |
| --- | --- | --- |
| Multiline part arrays | Both silently stopped storing at 256 parts while consuming later input. | Repaired and verified above: every content line survives or parsing raises. |
| Numeric float buffer, _cparser_lex.c | char buf[128] has no long-input fallback. A valid decimal of 127 characters becomes float; at 128 and 300 it becomes str. Python returns float in all three cases. | Fixed: checked dynamic fallback preserves numeric type and value beyond the stack buffer; verified through 1,024 characters in the regression suite and longer independent randomized cases. |
| Integer fast-path buffer, _cparser_lex.c | char buf[32] falls back to dynamically allocated storage; normal long integers pass the independent controls. However, failed temporary allocation falls through to a string, and PyLong errors are cleared indiscriminately. | Fixed: scratch/result allocation failures and non-ValueError conversion failures propagate. Fault injection verifies both short and long paths and scratch cleanup. |
| Tokenized LineArray, _cparser_lex.c | Initial capacity 256 already grows; long-input tests exercise that growth successfully. Capacity doubling and byte multiplication have no explicit overflow guard. | Fixed: capacity is bounded before doubling and byte multiplication. Synthetic boundary states verify rejection/clamping without huge allocations; failed growth preserves pointer, capacity, length and existing contents. |
| Key cache, _cparser_runtime.c | Fixed 128 slots evict old owned references rather than discarding fields. | Negative result: a 1,025-field object retains every field and value with both backends. |
| Quoted-string scratch, _cparser_lex.c | Allocation follows input length; allocation failure returns NULL. | No fixed content-cap mechanism found at this site. |

### Follow-up: numeric and line-vector errors repaired

Andreas instructed that the confirmed errors be fixed, not left as documented
follow-up work. A fresh fetch again confirmed the baselines above. All three
errors are now closed in the local working tree.

The numeric repair also exposed and fixed truncation of long integer-like text
at an embedded NUL. Full-input consumption is now checked, so such text remains
a complete string rather than becoming the numeric prefix.

Production changes are in _cparser_lex.c (496 lines). New tests:
test_numeric_capacity.py, test_lexer_allocator.py and lexer_allocator_probe.c.
The numeric suite initially had 22 failures / 89 passes; after repair all 111
cases pass. Fourteen fault/size tests verify scratch allocation, numeric result
construction, short/long integer conversion exceptions, vector initialization,
vector growth and arithmetic bounds. The probe uses the production lexer and
compiles with -Wall -Wextra -Werror; no test hooks enter the shipped extension.

Final verification: Ruff passed; strict Mypy passed (36 files); the full suite
with PYTHONMALLOC=debug and the sibling JMD_FIXTURES passed **2,576 tests with
the same three existing stream-folding skips**. No new test was skipped on this
Linux/CPython 3.14 run. Windows fault injection remains unqualified here.

Independent verification with seed 20261020 compared 600 valid random signed
integers, fractions and exponent forms against json.loads, checking both type
and value. Another 600 embedded-NUL controls retained the complete input string.

Final loaded native parser SHA-256:
45893ec3b24c3c167d857aabcf4f0b8835d269771663abdb2a8a0158100aed1e.

The earlier multiline-only fingerprint and results above remain historical
evidence. This is not a release acceptance or qualification of other JMD
implementations. No commit, push, version bump, runtime update or SmartSuite
live write occurred during those repair passes.

## Accepted patch integration

On 2026-10-20 Andreas accepted the stated qualification scope and remaining
three repeated-heading streaming questions to allow SmartSuite MCP work to
continue. He requested commits and pushes of both repositories with patch
versions: jmd-spec 0.3.7 and jmd-impl 0.11.1. This acceptance does not assert
exhaustive conformance or silently close the skipped questions.

Fresh fetches before integration again confirmed main = origin/main at
43760b57 (spec) and c772046f (implementation), ahead 0 / behind 0, with the
clean detached vendor pin still at 2573b1bb. GitHub releases/tags and PyPI
were checked: core spec 0.3.6 and jmd-format 0.11.0 were the published
baselines; the requested patch versions were unused. The older spec
repository tag v0.4 belongs to the XML companion, not the core format.

Integration commits the specification first, then pins that exact commit in
jmd-impl/vendor/jmd-spec and reruns the default suite against the committed
fixtures. Only repository commits and branch pushes are requested here;
package publication and runtime deployment are separate operations.
