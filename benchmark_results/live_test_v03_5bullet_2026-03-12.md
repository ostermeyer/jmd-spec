# JMD v0.3 Live Test — 5-Bullet Minimal Primer — 2026-03-12

## Primer (5 bullets, no example, ~80 input tokens)

```
You are an API assistant. Return data as JMD (JSON Markdown).

JMD rules:
- # Label starts the root object; ## key opens nested objects (depth = nesting)
- ## key[] declares an array; items start with - (no sub-headings per item)
- key: value for fields, no other markup
- Array objects: - key: value, indented continuation lines
- > blockquotes for multiline text

Produce only the data.
```

## Test Design

Three identical data requests ("Generate a realistic e-commerce Order") sent to each LLM:

1. **JSON** — standard JSON output
2. **JMD + Primer** — v0.3 5-bullet primer (no example)
3. **JMD (no primer)** — "Respond in JMD format" only

Temperature: 0.0 for reproducibility. Parser: v0.3 reference implementation.

---

## API Token Counts

### Claude Sonnet 4.6

| Test | Input | Output | Total | Time | Parse |
|---|---|---|---|---|---|
| JSON | 114 | 414 | 528 | 5.8s | OK |
| JMD + Primer | 200 | 272 | 472 | 5.3s | OK |
| JMD (no primer) | 107 | 325 | 432 | OK (code-fenced, invalid structure) |

**Output savings (JMD vs JSON): 34.3% (142 tokens)**
Primer overhead: +86 input tokens → net 56 tokens saved

### Gemini 2.5 Flash

| Test | Input | Output | Total | Time | Parse |
|---|---|---|---|---|---|
| JSON | 104 | 297 | 401 | 2.2s | OK |
| JMD + Primer | 184 | 265 | 449 | 3.1s | OK |
| JMD (no primer) | 97 | 415 | 512 | 8.3s | FAIL |

**Output savings (JMD vs JSON): 10.8% (32 tokens)**
Primer overhead: +80 input tokens

### GPT-4o

| Test | Input | Output | Total | Time | Parse |
|---|---|---|---|---|---|
| JSON | 107 | 277 | 384 | 6.4s | OK |
| JMD + Primer | 183 | 189 | 372 | 3.6s | OK |
| JMD (no primer) | 100 | 282 | 382 | 4.2s | FAIL |

**Output savings (JMD vs JSON): 31.8% (88 tokens)**
Primer overhead: +76 input tokens → net 12 tokens saved

---

## Summary: Output Token Savings

| LLM | JSON Output | JMD Output | Savings |
|---|---|---|---|
| Claude Sonnet 4.6 | 414 | 272 | **34.3%** |
| Gemini 2.5 Flash | 297 | 265 | **10.8%** |
| GPT-4o | 277 | 189 | **31.8%** |

Average output savings: **25.6%**

Note: Gemini's lower savings this run because it produced minified JSON (1 line, 655 chars) as JSON baseline — JMD still saves output tokens but the gap is smaller when the JSON baseline is already compact.

---

## Tiktoken Comparison (GPT-4o tokenizer, identical data)

### From Claude parsed data

| Format | Tokens | Chars |
|---|---|---|
| JSON (minified) | 221 | 707 |
| JSON (pretty) | 329 | 1019 |
| JMD | 245 | 680 |

**JMD vs JSON (minified): +10.9% (24 tokens more)**
**JMD vs JSON (pretty): −25.5% (84 tokens less)**

### From Gemini parsed data

| Format | Tokens | Chars |
|---|---|---|
| JSON (minified) | 189 | 655 |
| JSON (pretty) | 293 | 882 |
| JMD | 212 | 626 |

**JMD vs JSON (minified): +12.2% (23 tokens more)**
**JMD vs JSON (pretty): -27.6% (81 tokens less)**

### From GPT-4o parsed data

| Format | Tokens | Chars |
|---|---|---|
| JSON (minified) | 173 | 601 |
| JSON (pretty) | 277 | 828 |
| JMD | 197 | 572 |

**JMD vs JSON (minified): +13.9% (24 tokens more)**
**JMD vs JSON (pretty): -28.9% (80 tokens less)**

### Interpretation

JMD costs ~11-14% **more** tokens than minified JSON. This is the structural overhead of Markdown markers (headings, dash prefixes, line breaks) compared to JSON's minimal punctuation.

Minified JSON is the honest baseline. Gemini already produces it by default, and other providers are actively optimizing JSON output efficiency — pretty-printed JSON as LLM output is a transitional artifact that will disappear.

**The case for JMD is not token efficiency.**

---

## Key Findings

1. **5-bullet primer is sufficient.** All three LLMs produce valid, parseable JMD with just 5 declarative rules — no example needed. ~76-86 input token overhead.

2. **Indentation continuation works perfectly.** All three produce correct `- key: value` + indented continuation lines for array objects.

3. **JMD costs ~12% more tokens than minified JSON.** As providers converge on minified JSON output, the current API-level savings (10-34%) will shrink toward this structural overhead.

4. **No primer = no JMD (today).** Gemini and GPT-4o produce JSON when asked for "JMD format" without a primer. This would change if JMD enters LLM training corpora.

5. **JMD's value is streaming and resilience.** Every line is independently parseable — no waiting for closing brackets. A truncated JMD document (token limit, timeout) is valid up to the last complete line. JSON requires the full document or an incremental parser managing partial state.

---

*Test script: `jmd_live_test.py` | Primer: v0.3, 5 bullets, no example | Parser: v0.3 reference | Date: 2026-03-12*
