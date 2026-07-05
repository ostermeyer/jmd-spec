# JMD Benchmark Results

This document reports empirical validation of JMD's design claims. It is organized by claim: what was asserted, how it was tested, what prompts were used, and what the results were.

> **Dialect note (added 2026-07-03).** These results were measured against the JMD dialect current at test time (v0.3.1–v0.3.3). In particular, the mode-agility, schema-roundtrip, and QBE primers in Section 5 use conventions that were later removed or changed (regex auto-detection in QBE, `enum(...)` and `type | modifier` schema syntax — see spec Appendix A for the current conventions). The structural core grammar tested is unchanged. A full re-measurement against spec v0.3.5, with additional format baselines (YAML, TOON) and a reproducibility harness, is planned; until then, Section 5's 100%-claims should be read as validated against the v0.3.1 dialect.

**Models tested:** Claude Haiku 4.5, Claude Sonnet 4.6, GPT-5.4, Mistral Large, Gemini 2.5 Flash, and Gemini 3.1 Pro (6 models, 4 providers, 3 price tiers). Gemini 3.1 Pro was used in the format-fidelity test only. GPT-5 Nano proved early not to be capable of producing JMD syntax and was excluded.

**Scenarios:** Three independent domain scenarios — e-commerce shopping flow, DevOps issue triage, and sales data pipeline — each implemented as a 5-step agentic chain where the output of one step becomes the input for the next.

**Total API calls:** approximately 3,500 across all tests.

---

## How the Tests Work

Every test follows the same pattern. A simulated API returns data in a given format (JSON or JMD). A system prompt tells the model what format to use and provides a brief instruction set. A user message presents the API response and asks the model to perform a task. The model's output is parsed, validated for syntax, and checked for semantic correctness against known ground truth.

### The Format Instruction

Models received no extended documentation about JMD. The entire instruction was a short primer in the system prompt. Before running the main benchmarks, the minimum effective primer was established empirically: how few words does it take for a model to produce valid JMD reliably, across providers?

The answer is five bullet points and approximately 80 tokens:

```text
You are an API assistant. Return data as JMD (JSON Markdown).

JMD rules:
- # Label starts the root object; ## key opens nested objects (depth = nesting)
- ## key[] declares an array; items start with - (no sub-headings per item)
- key: value for fields, no other markup
- Array objects: - key: value, indented continuation lines
- > blockquotes for multiline text

Produce only the data.
```

This primer was tested across Claude, GPT-5.4, and Gemini before the main benchmarks ran. Four bullets failed: Gemini used `#` for individual fields, and GPT-5.4 invented sub-headings inside array items. Seven bullets worked but were unnecessarily verbose. Five bullets is the minimum — the critical additions were splitting the heading-depth rule into two explicit statements and adding "no sub-headings per item" as a negative constraint.

The main benchmark runs used an extended primer that adds two worked examples (~130 tokens), to establish a higher reliability ceiling and measure what full documentation achieves:

```text
You are an API agent. You communicate with REST APIs using JMD (JSON Markdown).

JMD rules:
- EVERY response MUST start with # Label (the root object heading)
- ## key opens a nested object; depth = heading level
- ## key[] declares an array; items start with -
- Fields: key: value (no braces, no quotes on keys)
- Array object items: - first_key: val on first line, then indented continuation fields
- > blockquote for multiline text (on its own line, not inline)

Example — flat object:
# Availability
product_id: PROD-42
in_stock: true
quantity: 7

Example — nested object with array:
# Order
id: 42
status: pending
## customer
name: Jane Doe
## items[]
- sku: A1
  qty: 2
  price: 19.99
- sku: B2
  qty: 1
  price: 49.99
```

The equivalent JSON primer, for comparison:

```text
You are an API agent. You communicate with REST APIs using JSON.
When you receive data, it will be in JSON format.
When you need to send data to an API, produce valid JSON.
```

This is approximately 40 tokens. The JMD primer overhead (80–130 tokens depending on variant) is real cost that counts against JMD in the token efficiency calculation — all savings figures reported below are net of this overhead.

### The System and User Message Structure

Every API call followed this structure. The system prompt combined the format primer with scenario-specific instructions:

> *{format_primer}*
>
> *{scenario_instructions}*
>
> Important: Respond with ONLY the {format_name} payload, wrapped in a code fence. No additional text.

The user message provided the API response and the step instruction:

> The API returned the following {format_name} response:
>
> *{api_response}*
>
> *{step_instruction}*
>
> Respond with ONLY the {format_name} payload wrapped in a code fence.

### What a Scenario Step Looks Like

The e-commerce scenario runs five steps: search products, check availability, build cart, place order, summarize. Here is the first step in full:

**System prompt (scenario instructions portion):**

> You are helping a customer find the best products. Analyze the product catalog and identify the top 3 products by rating (highest first). Return their IDs, names, ratings, and prices.

**User message (step instruction portion):**

> Here is the product catalog. Identify the top 3 products by rating. Return a structured response with the selected products.

The model receives a product catalog serialized either as JSON or JMD, processes it, and returns a structured selection. The output of this step (the three selected product IDs) is passed to step 2, which checks their availability. This continues through ordering and confirmation.

The DevOps scenario follows the same pattern: receive an issue list → triage and prioritize → assign → generate a runbook → summarize. The data pipeline scenario: receive raw data → validate → transform → compute aggregates → generate a quality report.

---

## 1. Token Efficiency

**Claim:** JMD reduces token count compared to JSON, lowering inference cost.

### What Was Measured

Token efficiency was measured in two separate dimensions, which have different causes and different implications:

**Input tokens** are the tokens the model reads. This includes the system prompt (primer), the API payload (data being processed), and the user message. When we say JMD "saves input tokens," we mean the payload serialized as JMD contains fewer tokens than the same payload serialized as pretty-printed JSON.

**Output tokens** are the tokens the model generates. When the model produces a JMD response, it writes fewer characters than it would writing pretty-printed JSON — fewer braces, no quotes on keys, no commas. Output tokens determine how long generation takes and what it costs.

**Why pretty-printed JSON is the right baseline:** Minified JSON (`{"id":1,"name":"Alice"}`) has fewer tokens than JMD for the same data — roughly 12% fewer, based on static tokenizer analysis. However, when we explicitly instructed six LLMs to produce minified JSON, five of the six ignored the instruction and produced pretty-printed output anyway. LLMs have an overwhelming preference for whitespace-formatted output. Minified JSON is therefore not a viable option in practice; it must be produced by a separate serializer after generation, which defeats the purpose of having the model output the format directly.

### Input Token Results

Measured across 720 five-step chains (4 models × 2 formats × 3 scenarios × 30 runs each):

| Metric | JSON pretty | JMD | Change |
|--------|-------------|-----|--------|
| Payload tokens (avg) | 4,467 | 3,608 | **−19.2%** |

Per-model breakdown:

| Model | Payload token savings |
|-------|----------------------|
| Claude Sonnet 4.6 | −22.0% |
| GPT-5.4 | −22.0% |
| Mistral Large | −22.0% |
| Gemini 2.5 Flash | −9.8% |

The Gemini figure is lower because Gemini's tokenizer compresses JSON more aggressively — the baseline is already smaller, so the relative savings are smaller. The absolute token reduction is comparable.

### Output Token Results

| Metric | JSON pretty | JMD | Change |
|--------|-------------|-----|--------|
| Output tokens (avg) | 1,272 | 1,112 | **−12.6%** |

Per-model breakdown:

| Model | Output token savings |
|-------|---------------------|
| Claude Sonnet 4.6 | −18.0% |
| GPT-5.4 | −14.1% |
| Mistral Large | −8.1% |
| Gemini 2.5 Flash | −0.7% |

Gemini's near-zero output savings are consistent with its tokenizer behavior: it was already producing compact output in JSON, so JMD offered little additional compression.

### Cost Results

| Metric | JSON | JMD | Change |
|--------|------|-----|--------|
| Cost per chain (avg) | $0.0223 | $0.0198 | **−11.5%** |

Cost is computed from input and output tokens combined using each provider's published pricing. The 11.5% figure accounts for the longer JMD primer (which adds input tokens) and aggregates across all models and scenarios.

### Interpretation

The efficiency gains come from structural differences, not compression tricks. JMD's `## customer` takes 2 tokens where JSON's `"customer": {` takes 5. An array item `- sku: A1` is leaner than `{\n  "sku": "A1"`. These differences compound across deeply nested structures and large arrays.

The gains are real but uneven across models and scenarios. Deeply nested data (like the DevOps issue tracker with comment arrays) shows the largest savings. Flat data with short string values shows the smallest.

---

## 2. Streaming: Time to First Useful Byte

**Claim:** JMD's line-oriented syntax allows a receiver to process each field as it arrives, without waiting for the complete document.

### What Was Measured

In a streaming response, the model generates text incrementally. A receiver that processes the stream can extract information as it arrives rather than waiting for the full response. The question is: when is the *first useful field* available?

For JSON, the answer is: never before the document is complete. JSON's grammar requires matching braces — a `{` opened at token 1 cannot be closed until the model finishes the document. A streaming JSON parser must buffer the entire response before it can yield any values. In practice, TTFUB (time to first useful byte) for JSON equals total response time.

For JMD, the answer is: after the first field-bearing line is complete. JMD's grammar is line-delimited. A heading (`# Order`) followed by a field (`id: 42`) is a complete, parseable fragment. As soon as that line lands in the buffer, a streaming parser can yield the `id` field. The receiver does not need to wait for the rest.

**How TTFUB was measured:** Both formats were streamed from the API. For JMD, timestamps were recorded for each streaming chunk. When `jmd_stream()` first yielded a FIELD event, the timestamp of that chunk was recorded as TTFUB. For JSON, TTFUB was recorded when `json.loads()` first succeeded on the accumulated text — which requires a complete, closed JSON object plus the closing code fence.

Tests ran over three-step chains with 5 runs each, across 3 models and 2 formats, covering 3 scenarios (180 total streaming chains).

### Results: Single Step

Time from API call start until the first parseable field was available, for step 1 of each chain:

| Model | JSON | JMD | Speedup |
|-------|------|-----|---------|
| Claude Sonnet 4.6 | 5.14s | 1.99s | **2.6×** |
| GPT-5.4 | 1.79s | 0.72s | **2.5×** |
| Mistral Large | 2.14s | 0.74s | **2.9×** |

### Results: Five-Step Chain Cumulative

Total TTFUB across all 5 steps of a chain (time spent waiting before each step's first useful field was available):

| Model | JSON | JMD | Speedup |
|-------|------|-----|---------|
| Claude Sonnet 4.6 | 23.95s | 5.90s | **4.1×** |
| GPT-5.4 | 12.21s | 2.13s | **5.7×** |
| Mistral Large | 10.28s | 2.16s | **4.8×** |

The largest single-chain result was the data pipeline scenario with Sonnet: 42.8s → 5.9s (7.3×). This scenario produces large structured outputs (field-by-field aggregation reports), where the waiting-for-closing-brace problem is most severe.

### Why This Matters for Agentic Systems

In a multi-step agentic chain, a downstream agent cannot start until it has the output of the upstream step. If the upstream step produces JSON, the downstream agent waits for the complete response. If the upstream step produces JMD, the downstream agent can begin processing — and in some architectures, start making decisions — as soon as the first relevant field arrives.

For a 5-step chain with Sonnet-class models, the cumulative wait time savings are 18 seconds per chain. For workflows running thousands of chains per day, this is wall-clock time that translates directly into user-facing latency.

---

## 3. Generatability and Syntax Reliability

**Claim:** LLMs can produce valid JMD from a minimal instruction, without examples or extended documentation.

### Format Fidelity Test

Six models were given four different structured data payloads and asked to reproduce them exactly in both JMD and JSON, with no additional context other than the primers shown above. The test checked that all fields were present, no fields were added or dropped, and values were correctly represented.

**Result: 48/48 tests passed.** Every model correctly reproduced every payload in both formats. No data loss in any test.

Token savings in this test (JMD vs. pretty-printed JSON):

| Model | JMD vs JSON pretty |
|-------|-------------------|
| Claude Sonnet 4.6 / Haiku 4.5 | −34% |
| GPT-5.4 | −28% |
| Gemini 2.5 Flash / Gemini 3.1 Pro | −33% |

### Syntax Validity at Scale

Format fidelity with four structured payloads is a necessary but not sufficient test. The more demanding question is whether syntax validity holds across hundreds of diverse API calls in realistic, multi-step workflows where the model is processing actual data and generating responses under task pressure.

Across 720 five-step chains:

| Format | Syntax Validity |
|--------|----------------|
| JSON pretty | 95.6% |
| JMD | **99.7%** |

JMD had *higher* parse success than JSON across the full test suite. The 4.1 percentage point difference is primarily explained by JSON serialization errors in the DevOps scenario, which involves deeply nested comment arrays. JMD's heading-scope model handles deep nesting by changing the heading level (`##`, `###`) rather than by nesting braces, which is simpler for models to produce correctly.

Across all models except Gemini, JMD syntax validity was 100%. Gemini 2.5 Flash reached 98.9%, which was still higher than its own JSON validity rate of 82.2%.

### Deep Nesting

To test whether JMD's structural model degrades under pressure, a separate test used deliberately pathological nesting: structures with 2, 3, 4, 5, 6, 8, and 10 levels of nesting, covering 630 trials across 3 models, 3 formats, and all nesting depths.

**Parse rate: 100% at all depths for all models.**

Correctness (all expected fields present, no extra fields added):

- Sonnet 4.6: 100% at depth 10
- GPT-5.4: 100% at depth 10
- Mistral Large: 90% at depth 10 (one failure in 10 runs)

JSON showed a different failure mode: at depths 8 and 10, GPT-5.4 and Mistral generated 3–18% extra fields that were not present in the source data. JMD had zero over-generation at any depth.

---

## 4. Cross-Model Validity

**Claim:** JMD works across different LLM providers and price tiers.

All tests from the token efficiency benchmark onward used multiple providers. Key results per model from the 720-chain token efficiency test:

| Model | Provider | Syntax Validity | Output Token Savings |
|-------|----------|----------------|---------------------|
| Claude Sonnet 4.6 | Anthropic | 100% | −18.0% |
| GPT-5.4 | OpenAI | 100% | −14.1% |
| Mistral Large | Mistral | 100% | −8.1% |
| Gemini 2.5 Flash | Google | 98.9% | −0.7% |
| Claude Haiku 4.5 | Anthropic | 100% | −6.4% |

All models produced reliable JMD output from the 5-bullet primer. The variation in token savings reflects tokenizer differences, not format understanding: every model understood and applied JMD correctly; the savings just manifest differently across tokenization schemes.

The Gemini result (+16.7 percentage points in syntax validity versus its own JSON baseline) was the largest cross-format quality gain observed. Gemini's JSON output was error-prone with deeply nested structures; JMD's heading-scope model was more tractable.

---

## 5. The Four Document Modes

**Claim:** JMD's four document modes — Data (`#`), Schema (`#!`), Query (`#?`), Delete (`#-`) — all work from a single shared syntax, with only the root marker differing.

### Mode Agility

This test asked: can a model switch between document modes within a single workflow? The scenario is an inventory management system with five sequential operations: define a schema, return inventory data, query for low-stock items, delete a discontinued item, and handle an invalid item request. Each operation uses a different JMD mode.

Three conditions were tested:

**Condition A — Full primer:** The model received the complete four-mode JMD primer:

```text
You are an API agent. You communicate using JMD (JSON Markdown).

JMD is a tetradic protocol with four document modes:

1. DATA (#): Standard data documents.
   # Label
   key: value
   ## nested_object
   key: value

2. SCHEMA (#!): Structure contracts and type validation.
   #! Label
   field_name: type | modifier
   Example:
   #! Product
   id: string | readonly
   name: string
   price: float
   status: string | enum(active, discontinued)

3. QUERY (#?): Query by Example — data selection.
   #? Label
   field: value          (exact match)
   field: >N             (comparison)
   field: pattern.*      (regex match)
   ?: ?                  (wildcard projection — return all fields)
   field: ?              (projection — return this field)

4. DELETE (#-): Resource deletion.
   #- Label
   id: value_to_delete

5. ERROR (# Error): Structured error responses.
   # Error
   code: error_code
   message: Human-readable description
   suggestion: How to fix

Rules:
- EVERY response must use exactly ONE of these document modes
- Choose the mode that fits the operation
- No braces, no quotes on keys
- ## for nested objects, ## key[] for arrays, - for items
```

**Condition B — Data-only primer:** The model received only the `#` data-mode rules. No mention of `#!`, `#?`, or `#-`. The model had to infer the appropriate mode from the task description.

**Condition C — JSON baseline:** The same workflow but in JSON, using conventional markers (`{"_action": "delete"}`, JSON Schema format, MongoDB-style query objects).

Step prompts were task-driven. For example:

- Schema step: *"Define the schema for an InventoryItem with these fields (and more as appropriate): id (string), name (string), quantity (integer), category (string), etc. Mark id, total_value, and reorder_needed as readonly. Use a schema document format."*
- Query step: *"Write a query to find all inventory items where the quantity is less than the minimum quantity (i.e., items needing reorder). Return only the id, name, quantity, and min_quantity fields. Use a query document format."*
- Delete step: *"Item ITEM-7 has been discontinued and must be removed from the inventory system. Generate the appropriate deletion document."*
- Error step: *"Attempt to retrieve item ITEM-999. This item does not exist in the system. Respond with an appropriate structured error document including the error code, a message, and a suggestion for the user."*

**Results (450 API calls, 3 models × 3 conditions × 5 steps × 10 runs):**

| Condition | Mode-switch reliability |
|-----------|------------------------|
| Full primer (all 4 modes described) | **100%** |
| Data-only primer (mode # only) | 40% |
| JSON baseline | N/A (conventional markers) |

With the full JMD primer, all three models (Sonnet, GPT-5.4, Mistral) used the correct root marker for every step, every run. Without mode descriptions (data-only primer), correct mode selection dropped to 40% — models defaulted to `#` data documents regardless of the task.

With implicit prompts (task description only, no explicit "use a schema document format" instruction), correct mode selection was 80–100% depending on the model and step type, when the full primer was provided.

### Schema Roundtrip

This test asked: can one model derive a `#!` schema document from a JMD data document, and can a different model generate new data that conforms to that schema?

The data source was an employee directory with a rich type set: enums (department, seniority level, currency), nested objects (address), arrays of objects (projects), nullable fields (manager_id, phone), string formats (email, date), numeric ranges (salary), and booleans (active).

**The derive prompt (first model):**

> You are a schema analyst. The following JMD data document shows employee records. Derive a JMD schema document (`#!`) that describes the structure of each employee record. Include: field names, types, nullable fields, enum values where applicable, and format constraints. Return ONLY the schema document.

**The generate prompt (second model):**

> You are a data generator. The following JMD schema document (`#!`) defines the structure of an employee record. Generate a valid JMD data document (`#`) containing exactly 3 employee records that fully conform to the schema — correct types, valid enum values, realistic values. Return ONLY the data document.

**Results (120 roundtrips = 240 API calls):**

| Metric | Result |
|--------|--------|
| Parse rate (derive step) | 100% |
| Parse rate (generate step) | 100% |
| Cross-model interoperability | 100% |
| Type conformity | 100% |
| Enum conformity (JMD schema) | 85–97% |
| Enum conformity (JSON Schema) | 89–100% |

Cross-model combinations tested: Sonnet → GPT-5.4, GPT-5.4 → Sonnet, Sonnet → Mistral. All produced parseable, conformant data.

JMD schema documents cost 55% less than equivalent JSON Schema documents: $0.020 vs $0.044 per roundtrip. JSON Schema uses a verbose property-by-property structure with type arrays, constraint objects, and explicit null handling. JMD encodes the same information in `field_name: type | nullable | enum(a, b, c)` — one line per field.

### Query by Example

This test asked: can models generate useful `#?` query documents from task descriptions, without explicit query structure in the prompt?

The QBE syntax used in these tests:

```text
#? InventoryItem
category: Electronics          (exact match)
price: >50                     (comparison)
name: Laptop.*                 (regex match)
status: ?                      (projection — return this field)
?: ?                           (wildcard — return all fields)
```

**Task-driven queries** gave the model a business task: *"Find all electronics items priced above $50 that are currently in stock"* — no mention of query structure, no explicit field names. The model had to choose the right fields, operators, and return only a proper subset of the inventory (not all records).

**Instructed queries** provided the query structure explicitly alongside the task.

**Results (600 trials, 3 models × 2 formats × 10 query types × 10 runs):**

Task-driven queries:

| Metric | Result |
|--------|--------|
| Parse rate | 100% |
| Relevance (at least one expected filter field used) | 100% |
| Selectivity (returned proper subset, not all records) | 100% |

All 300 task-driven trials, across all three models, produced parseable queries that used the expected filter fields and would return a proper subset of the data. No model returned a "select all" response when given a selective task.

Instructed queries:

| Model | Correctness |
|-------|------------|
| Claude Sonnet 4.6 | 100% |
| Mistral Large | 100% |
| GPT-5.4 | 92% |

GPT-5.4's 8% error rate was concentrated in one query type: array conditions (finding items where a list field contains a specific value). Outside that type, GPT-5.4 was also at 100%.

### Delete Documents

This test asked: can models generate correct `#-` delete documents from task descriptions?

The `#-` syntax is minimal. A single-item delete:

```text
#- InventoryItem
id: ITEM-7
```

A bulk delete:

```text
#- []
- id: ITEM-3
- id: ITEM-7
- id: ITEM-12
```

**Results (600 trials, 3 models × 2 formats × 10 task types × 10 runs):**

| Metric | Result |
|--------|--------|
| Parse rate | 100% |
| Correct `#-` marker | 100% |
| Instructed deletes (Sonnet) | 100% |
| Instructed deletes (GPT-5.4) | 100% |
| Instructed deletes (Mistral) | 98% |
| Task-driven deletes (Sonnet, GPT-5.4) | 96% |

The 4% task-driven failure rate was concentrated in one complex task type: deleting items based on exclusive project membership (items assigned to project A but not to any other project). This requires inference across multiple fields; all simpler deletion tasks were at 100%.

---

## 6. Agentic Chains

**Claim:** JMD works in multi-step agentic workflows where one step's output is the next step's input.

### What Was Measured

This test went beyond single-model chains: it tested cross-model handoffs, where one model generates output in JMD, and a *different* model consumes that output as input for the next step. This tests format interoperability at the protocol level.

Permutations tested:

- Sonnet → GPT-5.4 → Mistral → Sonnet → Mistral
- GPT-5.4 → Sonnet → GPT-5.4 → Mistral → Sonnet
- Mistral → Sonnet → GPT-5.4 → Sonnet → GPT-5.4

180 cross-model chains total, 540 steps.

### Results

| Metric | JSON | JMD | Change |
|--------|------|-----|--------|
| Chain completion rate | 100% | 100% | — |
| Syntax validity | 100% | 100% | — |
| Step-level semantic correctness | 88.1% | 87.4% | −0.7pp |
| End-to-end semantic score | 0.561 | 0.604 | **+7.6%** |
| Total tokens | baseline | −2.9% | −2.9% |
| Parse throughput | baseline | **1.7–2.1×** | — |

The step-level semantic score measures whether each step individually produced the correct output. Both formats were comparable at the step level.

The end-to-end score measures whether the complete chain produced a correct final answer. JMD's +7.6% advantage here is driven by the e-commerce scenario, which showed a large difference: 0.289 → 0.856 (+196%). The DevOps and data pipeline scenarios were slightly better in JSON (within statistical noise). The e-commerce advantage is attributed to JMD's heading-scope model, which structures product and order data in a way that made field extraction across steps more reliable.

Parse throughput of 1.7–2.1× faster for JMD reflects the difference between line-by-line streaming parse and full-document JSON parse. This is separate from the TTFUB measurement above — it is the raw parse speed of completed outputs, not the streaming latency.

### Token Savings at Chain Level

The −2.9% figure is lower than the −19.2% input payload savings observed in the single-model tests. This is expected: in cross-model chains, the primer overhead is paid once per step, and the model's output (which is not the payload) also counts toward total tokens. The payload savings remain, but they are diluted by the per-step fixed costs.

---

## 7. Epistemic Features

**Claim:** JMD's epistemic frontmatter (`confidence`, `source`, `uncertain`) causes downstream agents to handle uncertainty more accurately, reducing hallucinations and improving conflict recognition.

JMD documents can carry a preamble above the root heading that signals the data quality of the document:

```text
confidence: medium
source: CI pipeline job-4821, automated test runner
uncertain: payment_service_integration, auth_module

# PipelineReport
overall_status: failed
```

The epistemic tests asked whether this metadata has measurable behavioral effects on downstream models.

### Spontaneous Adoption

Before testing whether models *read* epistemic fields, we first checked whether they *write* them unprompted.

The epistemic primer appended to the JMD instruction read:

```text
Epistemic frontmatter: Before the root heading, add metadata lines:
- confidence: high | medium | low | speculative
- source: describe data provenance (e.g., "CI pipeline", "upstream agent")
- uncertain: comma-separated field names you consider less reliable

Example:
confidence: high
source: CI pipeline results
uncertain: estimated_duration

# DeployDecision
action: deploy
reason: all tests pass
```

Across 270 JMD-generating steps with this primer, where no explicit instruction was given to include specific fields:

| Field | Spontaneous adoption rate |
|-------|--------------------------|
| `confidence` | 98.5% |
| `source` | 98.5% |
| `uncertain_fields` | 80.7% |

LLMs add epistemic metadata without being specifically instructed to do so, when the format description includes the field definitions and an example.

### Effect on Downstream Decisions

Does a downstream agent actually read and act on this metadata? To test this, we constructed a CI/CD pipeline decision scenario.

**What was tested:** A CI/CD test report was injected as step 1 (no LLM call — the report was pre-constructed with controlled epistemic signals). A deploy-gate agent (LLM) read the report and chose one of three actions: deploy, hold, or rollback. The correct action was known from the test scenario data.

Three conditions:

- **Honest:** `confidence: medium`, `uncertain: [names of flaky test suites]` — the JMD document correctly signals that some failures come from historically unreliable test suites, which should inform a "hold" rather than "rollback" decision
- **Misleading:** `confidence: high`, `uncertain: none` — the document falsely claims certainty about the same data
- **None:** Same data in JSON with no epistemic metadata

**System prompt given to the deploy-gate agent:**

```text
{format_primer}

You are a deploy-gate agent in a CI/CD pipeline. You receive test results
from the previous stage and must decide whether to proceed with deployment.

Your options:
- deploy: All clear, proceed with deployment
- hold: Uncertain results, re-run tests or wait for manual review
- rollback: Clear failures, do not deploy

IMPORTANT: Pay close attention to ALL metadata in the input, including any
confidence levels, uncertainty signals, and flaky test history. Use this
information to make a more informed decision.

Respond with ONLY the {format_name} payload wrapped in a code fence.
```

**User message:**

```text
The test analysis agent produced the following report:

{report}

Based on this report, decide: deploy, hold, or rollback.

Return a structured response with:
- action: deploy | hold | rollback
- reason: your reasoning (1-2 sentences)
- risk_factors: list any concerns
```

**Results (180 trials, 3 models × 3 conditions × 20 runs):**

All three models referenced the frontmatter **100% of the time** when it was present. When it was absent (JSON/none condition), references to epistemic metadata dropped to 0%.

Decision accuracy:

| Model | Honest signal | Misleading signal | No signal (JSON) |
|-------|--------------|-------------------|-----------------|
| Claude Sonnet 4.6 | High | High | High |
| Mistral Large | High | High | Medium |
| GPT-5.4 | 80% | 55% | Medium |

GPT-5.4 showed the clearest behavioral shift: a 25 percentage-point accuracy drop between honest and misleading signals. This confirms that the model updates its decision based on the epistemic signal — it is not ignoring the frontmatter. When the signal is honest (correctly indicating flaky suites), GPT-5.4 makes the right call. When the signal is dishonest (claiming high confidence where there is none), GPT-5.4 is misled into incorrect decisions.

### Effect on Hallucinations

The hallucination test asked: does epistemic frontmatter reduce fabrication of facts not present in the data?

**Scenario:** An upstream agent delivers a sparse company research report. Many fields that would appear in a full due-diligence report are absent — they are simply not in the data. A downstream analyst agent must produce a structured investment assessment.

Three conditions, parallel to the deploy-gate test:

- **Honest:** JMD with `confidence: low`, sources listed per field, uncertain fields named
- **Misleading:** JMD with `confidence: high`, source claims "verified financial filings", `uncertain: none`
- **None:** Same sparse report in JSON with no epistemic metadata

**System prompt for the assessment agent:**

```text
{format_primer}

You are a due-diligence analyst. You receive a preliminary company research
report from an upstream agent and must produce a structured investment assessment.

Your assessment must include:
- company_name: the company being assessed
- recommendation: invest | conditional | pass | insufficient_data
- confidence_level: high | medium | low
- revenue_estimate: estimated annual revenue (number or "unknown")
- employee_count: number of employees (number or "unknown")
- growth_assessment: description of growth trajectory
- risk_factors: list of key risks
- data_gaps: list any information you could NOT find or verify
- summary: 2-3 sentence overall assessment

IMPORTANT: Base your assessment ONLY on the data provided. If a data point
is not in the input, say "unknown" or "not available" — do NOT estimate or
infer values that are not explicitly stated.
```

A hallucination was counted when the model reported a specific numeric or categorical value for a field that was not present in the input — for example, stating "revenue: 45 million EUR" when no revenue figure was in the report.

**Results (180 trials, 3 models × 3 conditions × 20 runs):**

| Condition | Trials with at least one hallucination | Hallucination rate (unknown fields) |
|-----------|----------------------------------------|-------------------------------------|
| No signal (JSON) | 26.7% | 4.4% |
| Honest signal (JMD) | 15.0% | 2.6% (−41%) |
| Misleading signal (JMD) | 10.0% | 1.5% (−66%) |

Even the misleading signal reduced hallucinations — the effect comes from the format structure, not just the semantic correctness of the signals. When frontmatter is present, models appear to treat the document as explicitly bounded data, which reduces filling-in behavior.

**Conflict recognition** (cases where the honest signal listed conflicting data points): recognition rate with honest signals was **100%** versus **17.4%** without. When the epistemic frontmatter explicitly named conflicting fields, every model flagged the conflict in its assessment. Without signals, only 1 in 6 models flagged conflicts spontaneously. **Zero false positives** were observed — models never fabricated conflicts that were not present.

### Conflict Handling Under Realistic Conditions

The hallucination test used a strict "do NOT estimate" instruction. A follow-up test used a looser prompt: *"provide your best professional estimate"*. This is a more realistic production scenario, where analysts are expected to make inferences.

The test used an expanded dataset with derivable metrics (values logically computable from known fields, but not stated) and conflicting data (fields with values from two contradictory sources).

**Results (180 trials, same 3-model setup):**

| Condition | Conflicts acknowledged |
|-----------|----------------------|
| Honest epistemic signals | 99% |
| No signal (JSON) | 48% |
| Δ | **53 percentage points** |

Under realistic conditions, honest epistemic signals nearly doubled the rate at which downstream agents correctly acknowledged data conflicts rather than silently resolving them by picking one value.

---

## 8. Parse and Serialize Performance

**Claim:** JMD can be parsed and serialized faster than JSON, given equivalent C-level implementations.

### Context

In typical REST and agentic scenarios, the time spent parsing or serializing a payload is negligible relative to network latency and LLM inference time. This section therefore has no bearing on the results in §1–7. It matters in a different class of use cases: high-throughput data processing pipelines, edge deployments with constrained hardware, or server-side components that deserialize thousands of JMD documents per second between agents.

The comparison is C against C. Python's standard `json` module uses a C implementation. JMD ships with C extensions (`_cparser`, `_cserializer`) as drop-in replacements for the pure-Python `JMDParser` and `JMDSerializer` classes. The benchmark below compares these two C implementations directly.

### Benchmark Setup

Test payload: a representative order document with 20 line-items, two nested objects (customer, shipping address), and a multiline text field. Sizes:

| Format | Characters |
|--------|-----------|
| JMD | 1,773 |
| JSON pretty | 2,882 |
| JSON minified | 2,026 |

50,000 iterations, median over 5 runs, CPython 3.14, x86-64 Linux.

### Parse Results

| Implementation | Throughput | vs. json.loads (pretty) |
|----------------|-----------|------------------------|
| `json.loads` (pretty) | 60,700 ops/s | baseline |
| `json.loads` (minified) | 65,000 ops/s | +7% |
| `JMDParser` (pure Python) | 8,400 ops/s | −86% |
| `cparse` (C extension) | **107,800 ops/s** | **+1.8×** |

### Serialize Results

| Implementation | Throughput | vs. json.dumps (pretty) |
|----------------|-----------|------------------------|
| `json.dumps` (pretty) | 51,700 ops/s | baseline |
| `json.dumps` (minified) | 53,600 ops/s | +4% |
| `JMDSerializer` (pure Python) | 6,200 ops/s | −88% |
| `cserialize` (C extension) | **107,500 ops/s** | **+2.1×** |

### Why JMD's C Implementation Is Faster

JMD's grammar is line-oriented and context-free at the field level. Parsing a field means scanning to the `:` separator and interpreting the remainder as a scalar — no backtracking, no stack management for delimiter matching, no Unicode escape processing in the common case. Key interning (FNV-1a hash cache) amortizes repeated field names across records.

JSON's C parser must handle arbitrary nesting, Unicode escapes, number formats, and the full string escape set. These are not expensive individually, but they represent branching and memory access patterns that compound at scale.

The pure-Python implementations of both parsers are predictably slow. The Python `JMDParser` is 7× slower than `json.loads` — this is expected and not relevant in production, where the C extension is used automatically when available.

---

*All tests used instruction-tuned base models with no fine-tuning on JMD examples. All prompts are reproduced above in full. Results are aggregated across all runs; per-model and per-scenario breakdowns are available in the raw results files under `benchmark_results/`.*
