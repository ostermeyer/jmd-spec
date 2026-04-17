# Contributing to JMD

Thank you for your interest in contributing. JMD is a specification project — contributions are most valuable in the areas listed below.

---

## What We Need Most

### Additional Model Tests

The current benchmark covers seven models from four providers. Contributions that extend coverage are particularly valuable:

- Tests on open-weight models (Llama, Mistral, Qwen, Phi, Gemma, etc.)
- Tests on locally-hosted models via Ollama or similar
- Tests on newer model versions as they are released
- Tests on models not yet covered (Cohere, AI21, etc.)

If you run benchmarks, please use the existing methodology in [BENCHMARKS.md](BENCHMARKS.md) — same scenarios, same chain structure, same validation approach — so results are comparable.

### Implementations in Other Languages

A Python reference implementation with C-accelerated parser and serializer is available at [jmd-impl](https://github.com/ostermeyer/jmd-impl). Implementations in other languages are welcome here as issues or pull requests:

- TypeScript / JavaScript
- Go
- Rust
- Java / Kotlin
- Ruby
- Any other language with significant LLM ecosystem usage

### Framework Adapters

Adapters that make JMD available as a structured output format in popular frameworks:

- LangChain
- LlamaIndex
- Pydantic AI
- DSPy
- Instructor
- Haystack

### Specification Feedback

If you find ambiguities, edge cases, or inconsistencies in [jmd-spec-v0_3.md](jmd-spec-v0_3.md), please open an issue. Be specific: include the relevant section, the problematic case, and your suggested resolution.

---

## How to Contribute

**Issues** — for bug reports, specification questions, and feature proposals. Please check existing issues before opening a new one.

**Pull requests** — for implementations, benchmark results, and documentation improvements. For significant changes, open an issue first to discuss.

**Benchmark results** — if you run the benchmark suite on a new model or configuration, the most useful contribution is a pull request adding your results to `benchmark_results/` with a brief description of the setup.

---

## Benchmark Contribution Format

If you contribute benchmark results, please include:

```
Model: [name and version]
Provider: [API or local]
Primer variant: [minimal / strict / custom — if custom, include the text]
Scenarios: [which of the three standard scenarios]
Runs per scenario: [number]
Date: [YYYY-MM]
```

And the results in the same structure as existing files in `benchmark_results/`.

---

## Code of Conduct

Be precise, be honest about uncertainty, and be kind. Discussions about the specification should focus on evidence and reasoning, not advocacy.

---

## License

By contributing to this repository, you agree that your contributions to the specification will be licensed under [CC BY 4.0](LICENSE), and your contributions to code will be licensed under [Apache 2.0](LICENSE-CODE).
