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

## 5. Economic Impact

The token reduction described above — 25–34% fewer output tokens per structured request — is not only a performance metric. It is a cost metric, and at scale, the cost implications are substantial.

A mid-size technology company running one million structured API calls per day, using mid-tier models at approximately $10 per million output tokens, spends roughly $1.8M per year on output tokens for structured data alone. JMD's 30% reduction translates to **approximately $550,000 saved per year** — without changing infrastructure, without changing providers, without retraining anything.

At global scale, the calculation compounds. The AI inference market is growing rapidly, with structured data output — tool calls, API responses, agent-to-agent communication, retrieval pipelines — representing an estimated 40% of total inference volume. Applying JMD's measured savings to that share:

| Year | Global inference market | Structured output | JMD saving potential |
|------|------------------------|-------------------|----------------------|
| 2026 | ~$25B                 | ~$10B            | ~$3B/yr             |
| 2028 | ~$70B                 | ~$28B            | ~$8B/yr             |
| 2030 | ~$180B                | ~$72B            | ~$22B/yr            |

These projections carry significant uncertainty — they depend on market growth rates, the fraction of inference that is structured, and above all on JMD adoption. The adoption dependency is not a weakness of the argument; it is its point. Every team that adopts JMD shifts these numbers. The aggregate saving is the sum of individual decisions.

### Capital Expenditure

The operational savings above are one dimension. There is a second, larger one.

Global investment in AI data center infrastructure is estimated at approximately $600B for 2026 alone — hardware, construction, power, and installation. JMD's 25–33% compute reduction means that existing hardware can serve a proportionally larger workload. Planned capacity that would otherwise be needed may not need to be built. Under conservative assumptions, JMD-level efficiency applied at scale could reduce the required infrastructure investment by $150–200B in 2026 — bringing the effective requirement closer to $400B than $600B.

Data centers are not paid for upfront. They are financed over 10–20 year terms and depreciated over similar horizons. Financing costs, operational expenditure over the asset lifetime, and eventual replacement investments typically amount to 3–4 times the initial capital outlay. A data center that is not built therefore avoids not only its construction cost but an estimated $500–800B in lifetime costs over its operational life — though this figure carries substantial uncertainty and depends heavily on energy prices, interest rates, and utilization assumptions.

There is a third possibility alongside cost reduction and demand growth: efficiency as an enabler. Applications that today sit at the boundary of economic feasibility — longer context windows, denser agentic pipelines, real-time processing at scale — become viable when the compute budget stretches further. JMD does not make hardware faster; it makes the same hardware go further. For engineers and architects, this means the boundary of what is buildable today shifts — without waiting for the next GPU generation.

One important caveat belongs here: efficiency gains do not always translate into reduced consumption. When compute becomes cheaper per unit, demand for compute tends to rise — the same dynamic that caused coal consumption to increase after the steam engine became more efficient. It is plausible, perhaps likely, that JMD adoption would enable more AI applications rather than fewer data centers. The actual savings depend on whether the efficiency gain is absorbed by new demand or retained as reduced infrastructure need. Both outcomes represent real value; they are simply different kinds of value.

---

## 6. Environmental Impact

The same compute reduction that drives cost savings also drives energy savings. GPU clusters running LLM inference are among the most energy-intensive computing systems ever deployed. A single H100 GPU draws approximately 700 W under load; major providers operate tens of thousands of them; the number of large-scale inference deployments is projected to grow from roughly 50 in 2026 to over 300 by 2030.

Applying JMD's 25% mean processing time reduction to the structured-output share of that infrastructure — 40% of inference volume, 400 g CO₂/kWh as a conservative grid average — the projected environmental impact:

| Year | Est. inference capacity | JMD saving potential | CO₂ reduction potential |
|------|------------------------|---------------------|------------------------|
| 2026 | ~350 MW | ~35 MW | **~120,000 t/yr** |
| 2028 | ~1,500 MW | ~150 MW | **~500,000 t/yr** |
| 2030 | ~5,000 MW | ~500 MW | **~1,500,000 t/yr** |

These figures account only for inference energy. They exclude the embodied carbon of GPUs that would not need to be manufactured if existing hardware serves more requests per watt, and the cooling and facility overhead that scales with GPU power draw.

As with the economic projections, the numbers are adoption-dependent. The 1.5 million tonnes by 2030 is not a forecast — it is a potential, realized only if the format is used. This is what *Sustainable Software Engineering* looks like at infrastructure scale: not a policy, not a hardware upgrade, but a format decision made by developers, one API at a time.

---

## 7. Three Pillars

The benchmark evidence supports three complementary claims:

**Compute efficiency.** 13–31% less server processing time and 25–34% fewer output tokens. Not cosmetic compression — a shorter generation process. Fewer tokens to produce means fewer generation steps; fewer generation steps means less GPU time; less GPU time means lower cost and lower energy draw. Format fidelity testing confirms 100% data fidelity across all models tested: JMD introduces no data loss compared to JSON.

**Streaming.** Every completed JMD line is immediately parseable. A partial JMD document contains all fields received so far. JSON cannot match this without non-standard extensions. The structural advantage scales with payload size and is particularly significant for multi-step agentic pipelines, where one tool's partial output can unblock the next tool without waiting for document completion.

**Unified protocol.** JMD covers the full data lifecycle with a single syntax: data transport (`#`), schema contracts (`#!`), Query by Example (`#?`), and resource deletion (`#-`). An LLM that produces a JMD data document already knows how to produce a query, schema, or delete — the root marker is the only difference. JSON requires separate tooling ecosystems for each concern.

These three properties are not independent features. They are structural consequences of a single design choice: hierarchy through Markdown heading depth rather than matched delimiters. A format that asks nothing of the model that the model does not already want to give.
