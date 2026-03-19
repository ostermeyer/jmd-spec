# Log-Probability Analysis: JMD vs JSON

Methodology: Schall & de Melo (RANLP 2025) — per-token logprob comparison

## gpt-4o

| Metric | JSON | JMD | Delta |
|---|---|---|---|
| Output tokens | 188 | 125 | -63 |
| Structural tokens | 112 (59.7%) | 57 (45.6%) | |
| Content tokens | 75.66666666666667 | 68 | |
| Mean structural logprob | -0.001 | -0.036 | **-0.035** |
| Mean structural prob | 0.999 | 0.972 | |
| Mean content logprob | -0.126 | -0.142 | -0.016 |
| Tokens/sec | 67.1 | 53.8 | -13.3 |
| Wall clock | 2.87s | 2.37s | |

**JSON structural tokens are higher-confidence** (-0.035 logprob). The model finds JSON syntax more natural than Markdown structure.

---

## Interpretation

A **positive structural logprob delta** (JMD > JSON) means the model
generates JMD structural tokens with higher confidence — they are closer
to the model's natural token distribution. Per Schall & de Melo (2025),
lower logprobs indicate the format forces the model away from its preferred
patterns, correlating with performance degradation.

**Content logprob delta** should ideally be ~0: the format should not
affect the model's confidence on the actual data values.
