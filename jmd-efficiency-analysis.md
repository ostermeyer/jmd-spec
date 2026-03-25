# JMD Efficiency Analysis

Benchmark Results, Performance Data, and Projections

This document provides the quantitative evidence behind JMD. The format specification explains the design; this document shows what the design produces when measured. For full methodology, prompts, and raw results, see [BENCHMARKS.md](BENCHMARKS.md).

---

## 1. Output Token Efficiency

When a language model generates structured data, every token costs the same: the same GPU time, the same energy, the same money. The question is not whether tokens are expensive — they are — but how many of them the structure itself requires.

JSON uses matched delimiters: opening and closing braces for objects, brackets for arrays, quotes for every key, commas between every value. A model generating JSON must produce all of these. JMD uses heading depth for hierarchy, bare keys for fields, and line endings for delimiters. The structural overhead is smaller by design.

The measurement confirms this. Across six models from three providers, tested on identical data and validated by parsing and ground-truth comparison, JMD requires **25–34% fewer output tokens** than pretty-printed JSON. Data fidelity is 100%: JMD introduces no data loss compared to JSON.

Shorter output translates directly to shorter generation. The model runs fewer steps because there are fewer tokens to produce. This is the mechanism behind a second measurement: **13–31% less server processing time** per request. The reduction is real compute saved, not a measurement artefact.

### Why Minification Doesn't Help

The obvious question is whether minified JSON closes the gap. It does not — and the reason is structural.

When instructed to produce minified JSON, five of six models tested ignored the instruction and produced pretty-printed JSON. Three models produced byte-identical output for both JSON variants. This is not a prompting failure. Autoregressive models reproduce patterns learned during training, and those patterns are overwhelmingly pretty-printed. The whitespace preference is deep.

More importantly: minification would not save compute even if it worked. Each generation step costs the same GPU time regardless of which token is produced. A model outputting `{` instead of `{\n` + indentation has not shortened the generation process — it has chosen different tokens at the same cost. Measurements confirm comparable or higher server processing time per token for minified JSON, because the model attends to more context while suppressing its formatting instincts.

JMD saves compute by eliminating structural tokens entirely: headings replace brace pairs, bare keys replace quoted keys, line endings replace comma-delimiters. The model runs fewer steps because there are fewer steps to run.

### A Self-Reinforcing Effect

JMD's efficiency has a compounding property. As JMD patterns appear more frequently in training data and inference logs, BPE tokenizers will begin merging them into single tokens — exactly as they have already done for common JSON patterns. Growing adoption makes JMD increasingly efficient to generate, which makes it more attractive to adopt, which increases adoption.

---

## 2. Parser and Serializer Performance

JMD is not only cheaper to generate — it is faster to process.

A C-accelerated JMD parser outperforms Python's C-accelerated `json.loads()` by **1.4–2.9×** across payloads from single objects to 500-record collections. The advantage is largest for small objects, where JMD's line-oriented grammar requires no delimiter matching, no escape processing, and no look-ahead for the common case. A plain `key: value` line is parsed with a single pass. JSON requires tracking nested brace depth at every character.

A C-accelerated JMD serializer outperforms `json.dumps()` by **1.6–6.0×**, and remains **1.6–4.4× faster** even against programmatically minified JSON. Serialization is fast because JMD writes bare keys without quoting, emits no delimiters or commas, and requires no indentation computation — the heading prefix replaces the recursive whitespace tracking that JSON pretty-printing demands.

For most REST and agentic scenarios, network latency and inference time dominate. Parser throughput does not affect end-to-end latency in these cases. It matters where volume is high and latency budgets are tight: high-throughput processing pipelines, edge deployments, and real-time analytics over streamed JMD.

---

## 3. Streaming: Time to First Useful Byte

JMD's structural choice — hierarchy through heading depth rather than matched delimiters — has a streaming consequence that no JSON variant can match.

A JMD receiver can parse each field as soon as its line is complete. The first `key: value` line in a streamed response yields a parseable field event immediately. No closing delimiter is required, because there is no opening delimiter to close.

JSON cannot offer this. A JSON parser must accumulate enough structure to yield a key-value pair: the opening brace, the first key with its surrounding quotes, the colon, and the value. For large documents, the closing `}` arrives only after the entire payload has been received.

Time-to-first-useful-byte (TTFUB) — measured from the start of streaming to the first parseable field event — across three realistic API scenarios:

| Scenario | Payload | JMD TTFUB | JSON TTFUB | Speedup |
|---|---|---|---|---|
| E-commerce | ~500 tokens | 1.6 s | 2.5 s | **1.5×** |
| DevOps triage | ~800 tokens | 1.4 s | 3.4 s | **2.4×** |
| Data pipeline | ~1,500 tokens | 1.5 s | 23.1 s | **15×** |

The advantage scales with payload size. For large documents, JSON's first useful byte arrives only after significant buffering. JMD's first useful byte arrives with the first line.

A partial JMD document is not broken output — it contains all fields received so far, in order, parseable as-is. A partial JSON document is a parse error.

---

## 4. Beyond APIs: JMD as a Native Format

Most structured data formats draw a sharp line between machine consumption and human readability. JSON requires a pretty-printer to be readable; minified JSON is practically illegible. YAML is human-readable but notoriously error-prone for machines.

JMD does not draw this line. A JMD document is readable as Markdown — headings, key-value pairs, lists — and parseable as structured data without any transformation. The same bytes serve both consumers.

This has an implication that extends beyond REST APIs. When language models respond in conversational contexts — chat interfaces, assistant replies, inline tool responses — they already reach for exactly this structure: headings for sections, `key: value` for structured fields, bullet lists for sequences. They do this naturally, without instruction, because it is what they have learned works.

JMD formalizes that natural tendency into a specification. A chat response organized as JMD is simultaneously readable by the human receiving it and parseable by the application processing it — with no conversion step, no code block wrapper, no format negotiation. The format that LLMs produce naturally in conversation is the same format that machines can consume directly.

---

## 5. The Obvious Question

If JMD is more efficient, more streamable, and more reliably generatable than JSON — why does JSON still stand unchallenged? Why did no one arrive here sooner?

These are fair questions, and they deserve honest answers. Three counter-arguments are worth taking seriously.

---

### Counter-argument 1: LLMs are trained on JSON, not JMD

As inference logs accumulate and Tool Calling produces vast quantities of JSON, future model generations will be trained on increasingly JSON-heavy data. Does this not mean that JSON will become *more* natural for models to generate over time — and JMD *less* so?

The argument sounds compelling until you examine its premise. Markdown is not a niche format in training data. It is arguably more pervasive than JSON: documentation, wikis, README files, technical writing, chat interfaces, note-taking tools — all Markdown. JMD is not a new syntax that models must learn. It is formalized Markdown: the structural patterns that models already reach for when asked to organize information without format constraints.

The deeper question is whether we want models to operate in two structural languages simultaneously — Markdown for prose and explanation, JSON for structured data — when a single format could serve both purposes efficiently. The cognitive and computational overhead of maintaining two distinct structural modes is real. JMD collapses this duality: the format a model produces naturally in conversation is the same format a machine can consume directly. That is not a coincidence to be designed around; it is a property to be exploited.

The risk that JSON dominance in Tool Calling training data erodes JMD's naturalness is real and worth monitoring. It is not, however, an argument against JMD — it is an argument for establishing JMD as a training data presence as early as possible. Which is, in part, what this publication is for.

---

### Counter-argument 2: Constrained Decoding solves the syntax problem

Major LLM providers now offer constrained decoding for structured outputs: grammar constraints applied at inference time that make syntactically invalid JSON literally unproducible. With constrained decoding, JSON syntax validity reaches 100% — eliminating the 4.4 percentage point advantage JMD shows in the benchmarks.

This is true. But constrained decoding is not free.

It requires a grammar parser running in parallel with inference, tracking parse state at every token step and restricting the probability distribution to grammatically valid continuations. This adds latency, memory overhead, and — critically — forces the model to occasionally choose tokens it would not otherwise choose, which can degrade output quality in subtle ways. It introduces friction at the most compute-intensive point in the pipeline.

More fundamentally, constrained decoding addresses only one of JMD's three structural advantages. It does not reduce the token count. A syntactically perfect JSON document still requires 25–34% more output tokens than an equivalent JMD document — which means 25–34% more generation steps, 25–34% more GPU time, 25–34% more energy drawn. And it does not make JSON streamable. A perfectly valid JSON document with constrained decoding is still a document that cannot yield its first field until the last byte is received.

JMD achieves 99.7% syntax validity without any runtime constraints, without a parallel grammar parser, and without restricting the model's generation freedom — while simultaneously delivering the token efficiency and streaming properties that constrained decoding cannot touch. The comparison is not between JMD and broken JSON. It is between JMD and an infrastructure that adds complexity and compute to fix a problem that JMD avoids by design.

---

### Counter-argument 3: The true end-to-end efficiency gain is hard to measure

Server processing time and output token counts are measurable. End-to-end latency in a real production system — with network overhead, load balancing, input processing, and application logic — is harder to isolate. If the bottleneck is elsewhere, a 25% reduction in output processing time may translate to a smaller fraction of total wall-clock time.

This is a legitimate methodological limitation, and we do not claim otherwise.

What we can say is that the measured savings are real, reproducible, and available at the layer where they are measured. For teams whose workloads are inference-bound — which is increasingly common as agentic systems grow in depth and breadth — the savings translate directly. For teams whose bottleneck lies elsewhere, the savings are smaller in proportion, but they remain non-zero.

The honest answer to this counter-argument is also an invitation: the measurements reported here were made with the tools available to an independent researcher. The full picture — production telemetry, infrastructure-level power draw, end-to-end latency distributions across real workloads — requires the instrumentation of the providers and large-scale operators who run this infrastructure. We publish this work explicitly to invite that collaboration. If the true efficiency gain is smaller than the benchmarks suggest, we want to know. If it is larger, the world should know. Either way, the measurement is worth making.

---

### What remains

Of these three counter-arguments, only one survives scrutiny as a fundamental challenge: JSON's network effects as an incumbent. Every language has a JSON library. Every developer knows JSON. Every framework parses JSON. These are not technical advantages — they are adoption advantages, accumulated over two decades. They are real, and they will not dissolve quickly.

But network effects are overcome by one mechanism: a sufficiently compelling reason to switch, arriving at the right moment. The right moment for JMD is now — when LLM-driven infrastructure is being built from scratch, before JSON's incumbency in agentic systems has fully calcified, and while the efficiency and climate implications of format choices are only beginning to be understood.

There is a second reason the incumbency argument is weaker today than it would have been five years ago: the implementation barrier has collapsed. The standard response to "but there's no JMD library for my language" used to be "someone needs to write one" — a project measured in weeks. Today, with LLM-assisted development tools like Claude Code, a production-ready JMD library is a matter of hours, not weeks. The Python reference implementation, the C-accelerated parser and serializer, the benchmark suite, and the MCP server implementations in this repository were built without a single line of hand-written code. A developer encountering JMD for the first time can have a working implementation in their language of choice before the end of the day.

JMD's human readability — which is not its primary design goal, and carries little weight in the machine-to-machine communication for which the format was designed — turns out to matter precisely here. When bootstrapping an implementation, a developer can read and understand JMD test cases, debug parse errors, and verify output without a working parser. The format is self-documenting in a way that minified JSON is not, and that a binary format never could be. This accelerates implementation and reduces errors during the one phase where human comprehension of the format actually counts.

The case for JMD is not that JSON is broken. It is that JSON was designed for a different era — complete document exchange between code consumers — and that the era of LLM agents demands something different. The benchmarks show what that difference is worth. The implementation tools exist to close the library gap in hours. The question is whether the industry moves before the opportunity closes.

---

## 6. What the Numbers Mean — An Invitation to Calculate



The measurements in Sections 1–4 are exactly that: measurements. They were made on real models, with real API calls, under controlled and documented conditions. They do not depend on assumptions about market size, adoption rates, or infrastructure growth.

But measurements taken in isolation do not speak for themselves. Someone has to connect them to the world they describe — and that work belongs to every reader who runs inference at scale, plans infrastructure, or thinks about the footprint of the systems they build.

This section does not present forecasts. It presents two calculation frameworks derived directly from the measured data — one for the climate, one for the invoice — and invites you to apply your own assumptions to both.

---

### Framework 1: Carbon

The efficiency gains measured in Sections 1–3 reduce the GPU time required per structured inference request. Reduced GPU time means reduced energy draw. Reduced energy draw means reduced CO₂ emissions. The chain is direct and uncontroversial; the uncertainty lies entirely in the scale assumptions.

The calculation has four parameters:

| Parameter | Description | Baseline assumption |
|---|---|---|
| **Inference capacity** | GPU power allocated to LLM inference (MW) | 350 MW (global 2026 est.) |
| **Structured output share** | Fraction of inference that is structured data output | 40% |
| **JMD processing savings** | Reduction in server processing time per request | 25% (measured lower bound) |
| **Grid carbon intensity** | CO₂ per kWh of electricity consumed | 400 g/kWh |

```
CO₂ reduction potential (t/yr) =
    Inference capacity (MW)
  × Structured output share
  × JMD processing savings
  × 8,760 hours/year
  × Grid carbon intensity (t/kWh)
```

With the baseline assumptions:

```
350 MW × 0.40 × 0.25 × 8,760 h × 0.0004 t/kWh = ~122,000 t CO₂/yr
```

**One important note on what this measures — and what it does not.** The baseline uses GPU processing time, which is the directly measured variable. It excludes cooling and facility overhead, which typically add 20–50% to the energy draw of a GPU cluster (expressed as PUE — Power Usage Effectiveness). A data center operating at PUE 1.4 should multiply the result accordingly: the 122,000-tonne baseline becomes approximately 171,000 tonnes. Network transfer savings from shorter payloads and the embodied carbon of hardware that need not be manufactured add further — but are harder to quantify. The baseline figure is therefore a lower bound, not a complete accounting.

**Your numbers.** If you operate an inference cluster, you know your actual power draw, your PUE, and your structured output fraction better than any external estimate. Substitute them. A team running 10 MW of inference at PUE 1.4, 60% structured output, 30% savings, and a 200 g/kWh grid:

```
10 MW × 1.4 (PUE) × 0.60 × 0.30 × 8,760 h × 0.0002 t/kWh = ~4,414 t CO₂/yr
```

That is 4,414 tonnes per year — from one team's decision to change a serialization format. Not from hardware upgrades. Not from a switch to renewable energy. From the structure of the output.

---

### Framework 2: Cost

The same tokens that carry no payload also carry no justification — not for the climate, and not for the invoice.

Every structural token JMD eliminates — every brace, every quoted key, every comma — is a token your infrastructure paid to generate and will never pay to use. At scale, this is not a rounding error.

The cost calculation requires no infrastructure knowledge. You need only three numbers you likely already know:

| Parameter | Description | Example |
|---|---|---|
| **Requests per day** | Structured API calls per day | 1,000,000 |
| **Output tokens per request** | Average output tokens in structured responses | 500 |
| **Price per output token** | Your provider's output token price | $0.000010 |

```
Annual cost saving ($) =
    Requests per day
  × 365
  × Output tokens per request
  × JMD output token savings (25–34%)
  × Price per output token
```

With the example values and a conservative 30% savings:

```
1,000,000 × 365 × 500 × 0.30 × $0.000010 = $547,500/yr
```

Half a million dollars per year. No infrastructure change. No provider switch. No retraining. A format decision.

**Your numbers.** The formula above is the complete model. Substitute your own request volume, token counts, and pricing. Teams with deeper nesting or larger payloads will see savings toward the upper end of the 25–34% range; flat structures with short values will see savings toward the lower end. Both endpoints are measured.

Note that this calculation covers output tokens only. Input token savings (19–29% measured, see Section 1) add a further reduction that depends on your input-to-output token ratio.

---

### The Adoption Variable

Both calculations above assume full adoption — every structured request uses JMD. In reality, adoption will be partial and gradual.

This is also where both calculations become personal.

If your team adopts JMD, you shift the adoption fraction. Your CO₂ saving is real and immediate. Your cost saving appears in next month's invoice. If you contribute an implementation for a widely-used framework, you shift it further. If you include JMD in a specification or talk about it at a conference, you shift it further still.

There is a third dimension to adoption that neither calculation above captures. As JMD patterns appear more frequently in training data and inference logs, BPE tokenizers will begin merging common JMD sequences into single tokens — exactly as they have already done for common JSON patterns like `{"` or `": "`. This means that the 25–34% output token savings measured today are the floor, not the ceiling. Growing adoption makes JMD increasingly efficient to generate, which makes it more attractive to adopt, which increases adoption further. The calculations above will become more favorable over time — in direct proportion to how widely the format is used.

The optimistic numbers — the ones that represent what JMD could achieve if the industry moves — are not forecasts. They are targets. They become real in proportion to individual decisions, each one compounding into the aggregate — and each one making the next decision slightly cheaper to justify.

---

### An Invitation

JMD was built on a simple observation: language models already produce this format naturally. The specification did not invent new behavior — it formalized existing behavior, measured it, and made it reproducible.

The implications above follow the same logic. The savings are not hypothetical — they are measured, repeatable, and available today. The question is only whether they are captured at scale.

We are working toward a foundation for sustainable AI infrastructure — an organization dedicated to making compute efficiency a first-class concern in LLM-driven systems: funding research, building tooling, and establishing the institutional capacity to make the optimistic numbers real.

If you want to be part of that — as an adopter, a contributor, or a founding member — we would like to hear from you.

→ [andreas@ostermeyer.de](mailto:andreas@ostermeyer.de)

---

## 7. Three Pillars

The benchmark evidence supports three complementary claims:

**Compute efficiency.** 13–31% less server processing time and 25–34% fewer output tokens. Not cosmetic compression — a shorter generation process. Fewer tokens to produce means fewer generation steps; fewer generation steps means less GPU time; less GPU time means lower cost and lower energy draw. Format fidelity testing confirms 100% data fidelity across all models tested: JMD introduces no data loss compared to JSON.

**Streaming.** Every completed JMD line is immediately parseable. A partial JMD document contains all fields received so far. JSON cannot match this without non-standard extensions. The structural advantage scales with payload size and is particularly significant for multi-step agentic pipelines, where one tool's partial output can unblock the next tool without waiting for document completion.

**Unified protocol.** JMD covers the full data lifecycle with a single syntax: data transport (`#`), schema contracts (`#!`), Query by Example (`#?`), and resource deletion (`#-`). An LLM that produces a JMD data document already knows how to produce a query, schema, or delete — the root marker is the only difference. JSON requires separate tooling ecosystems for each concern.

These three properties are not independent features. They are structural consequences of a single design choice: hierarchy through Markdown heading depth rather than matched delimiters. A format that asks nothing of the model that the model does not already want to give.
