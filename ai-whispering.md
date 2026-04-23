# *AI Whispering*

Copyright (c) 2026 Andreas Ostermeyer <andreas@ostermeyer.de>.
Licensed under CC BY 4.0 — see [LICENSE](LICENSE) for details.

---

*AI Whispering* is a practice. Not a framework, not a methodology — a practice.
It is the accumulated skill of working with large language models in a way that
produces reliable, efficient results: not by mastering them, but by understanding
them.

The practitioner who whispers does not fight the model. They observe what it
naturally does, understand why, and work within those tendencies rather than
against them. This requires two things: empiricism and empathy.

---

## Natural Tendencies

LLMs are not neutral text transformers. Training on enormous corpora instills
strong structural preferences. When asked to organize data without format
constraints, models from different providers and architectures converge on the
same patterns: headings for hierarchy, `key: value` for fields, bullet lists for
sequences, prose for explanation.

These tendencies are not accidental. They reflect what the models have seen work —
the accumulated signal of how humans write structured content. A model reaching
for a heading is doing something intelligent. Recognizing this is the first step.

The *AI Whisperer* does not treat these tendencies as noise to suppress. They are
signal. They are building material.

---

## Context, Not Commands

The standard response to LLM unreliability is prompt engineering: more
instructions, more examples, more explicit rules. This works, up to a point.
But it treats the symptom.

LLMs do not fail primarily because they lack instructions. They fail because they
lack *context* — situational understanding of what they are being asked to do and
why. A model that understands its situation draws on its strengths. A model given
instructions without context complies imperfectly, under pressure, at scale.

The *AI Whisperer* asks a different question: what does this model need to
understand its situation? Then they provide that, and step back. Natural tendencies
take care of the rest.

---

## The Cost of Friction

When a format or instruction runs against natural model tendencies, the model
complies imperfectly. Syntax errors accumulate at structure boundaries. Edge cases
fail silently. Retries become necessary.

This is usually framed as a reliability problem. It is also a resource problem.

Friction has a computational cost. Every malformed response, every retry, every
validation failure that propagates downstream — these consume GPU cycles. At scale,
the aggregate is significant. A model working against its own tendencies is a model
working harder than necessary to produce a result that could have come easily.

*Sustainable Software Engineering* is the discipline of building software that
consumes the minimum necessary resources to achieve its goal. In an AI-native
system, this means designing so that models can fulfill their tasks the way they
naturally would — without friction, without fighting, without waste.

A system built on *AI Whispering* principles does not spend compute overcoming its
own design decisions. It produces correct results more often, in fewer steps, with
less energy.

---

## JMD: A Case Study

JMD (JSON Markdown) is a structured data format shaped entirely by this practice.
Each syntax decision was driven by the same question: what does the model already
want to produce?

### Heading Depth as Scope

JSON tracks nesting by brace-counting. This is trivial for a parser. For a
generative model it is surprisingly error-prone: the outermost `{` is the very
first token of the document and its matching `}` is the very last — sometimes
with megabytes of content in between. The model must hold that obligation open
across the entire generation, while simultaneously producing semantically coherent
content.

JMD uses heading level as scope depth. `## key` opens a nested object; `### key`
opens an object nested inside that. The current scope is always visible in the most
recent heading line — the model does not maintain a stack.

This was not derived from watching models fail at JSON. It was anticipated, based
on understanding how models handle stateful generation. The benchmarks confirmed it:
99.7% syntax validity across 720-chain tests, versus 95.6% for pretty-printed JSON.
The largest gains were exactly where brace-matching errors are most likely —
deeply nested structures.

### The Array Marker

`## key[]` and the mode markers (`#!`, `#?`, `#-`) are the only elements that
required new conventions. Everything else in JMD is existing Markdown. The `[]`
suffix is short, visually distinct, and consistent with array notation that appears
throughout the models' training data.

The bullet syntax for array items emerged from observation: models naturally reach
for bullet lists when producing sequences. The design formalized the indentation
rule for multi-field items rather than inventing something new.

### The Four Document Modes

`#`, `#!`, `#?`, `#-` — data, schema, query, delete. A single character at
position zero sets the context for everything that follows. The model commits to a
mode before generating a single field.

This is the context principle in miniature. A model that has committed to schema
mode at position zero generates a schema. It does not drift. The commitment is
early, unambiguous, and self-reinforcing. Validation across three providers showed
100% mode-switch reliability.

The alternative — verbose mode keywords like `@schema`, `@query` — would also
work. But it would require a model to produce an unfamiliar token at the most
consequential position in its output. A punctuation suffix on an existing pattern
is a lower bar.

### Epistemic Frontmatter

LLMs have internal representations of their own uncertainty. This is not
incidental — it is a consequence of training on human-generated content where
hedging, sourcing, and qualification are pervasive. Models know, in some functional
sense, when they are on solid ground and when they are not.

JMD provides a formalized location for this: `confidence`, `source`, and
`uncertain` fields in a preamble above the root heading. The format does not create
the behavior. It provides the channel.

The result: 98.5% spontaneous adoption of `confidence` and `source` fields across
270 JMD-generating steps, without instruction. Downstream, documents with
frontmatter showed 100% conflict recognition versus 17.4% without, and a 41%
reduction in hallucination rates under strict prompting conditions. What was already
in the model could now be communicated explicitly rather than lost as prose.

### What Was Not Built

*AI Whispering* produces decisions by elimination as much as by adoption.

**Conditional delete** was considered and rejected. When given a delete task that
requires criteria evaluation, models naturally decompose it: query first, inspect
the result, then generate a targeted delete for the resolved IDs. Building a
compact filter syntax would mean teaching models to compress a two-step process
they prefer to make explicit. The friction was a signal.

**Minified JSON** was measured and rejected. When instructed to produce minified
JSON, five of six tested models produced pretty-printed JSON regardless. The
preference for whitespace is deep. Designing around it would require a format
that consistently overrides a strong training signal. JMD achieves better token
efficiency than pretty-printed JSON while staying within the natural generation
range.

**XML-style tags** were considered and rejected. Closing tags that must match
opening tags reproduce the same error mode as JSON brace-balancing, with the
additional complication of repeated tag names. Heading-depth syntax has no such
requirement.

Each rejected option was asking the model to work against itself. Each rejection
made JMD simpler and the system more efficient.

### The Numbers

The results of designing this way are measurable:

- **99.7%** syntax validity across 720-chain benchmark tests (vs. 95.6% for JSON)
- **31–38%** fewer output tokens than pretty-printed JSON
- **4.1–5.7×** faster streaming time-to-first-usable-byte in multi-step chains
- **1.8×** faster parse throughput than `json.loads` (C-optimized JMD parser)
- **2.1×** faster serialize throughput than `json.dumps` (C-optimized serializer)

These are not incidental. They are the measurable consequence of a format that
asks nothing of the model that the model does not already want to give — and
infrastructure that reflects the same principle: do the minimum necessary work
to achieve the correct result. Einstein is credited with a similar formulation:
make everything as simple as possible, but not simpler.

---

## The Broader Application

JMD is a structured data format. But the practice that shaped it is not about
structured data formats.

The same questions apply wherever LLMs are put to work: what does this model
already understand? What context does it need to do this well? Where is the design
asking it to work against itself?

The answers are empirical — observable, testable, revisable. The practice is
available to anyone willing to pay attention.

---

*JMD's benchmark results — validation across 7 models, 3 providers, and
approximately 3,500 API calls — are documented in [`BENCHMARKS.md`](BENCHMARKS.md).*
