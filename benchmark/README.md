# Benchmark Code

This directory contains the scripts used to produce the results documented in [BENCHMARKS.md](../BENCHMARKS.md). The code is provided as-is for reference and reproducibility. It is not a supported library.

## Dependency

The benchmark suite requires the `jmd` reference implementation. Without it, all scripts will fail on import. Install it before running anything:

```bash
pip install jmd
```

API keys for Anthropic, OpenAI, and Google are required for benchmarks that call live models. Set them as environment variables:

```bash
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
export GOOGLE_API_KEY=...
```

## Structure

```
benchmark/
├── run_benchmark.py          # Main entry point for token efficiency benchmarks
├── run_streaming_chain.py    # Streaming TTFUB measurements
├── run_phase2.py             # Cross-model validity (6 models, 3 providers)
├── run_phase3.py             # Agentic chain benchmark (720 chains)
├── run_phase4_epistemic.py   # Epistemic frontmatter — deploy-gate scenario
├── run_phase5_hallucination.py  # Epistemic — due-diligence, restrictive prompt
├── run_phase5b_inference.py  # Epistemic — due-diligence, permissive prompt
├── run_phase6a_mode_agility.py  # Four document modes agility test
├── run_phase6b_nesting.py    # Deep nesting benchmark
├── run_phase6c_schema_roundtrip.py  # Schema roundtrip validation
├── run_phase7_qbe.py         # Query by Example benchmark
├── run_phase8_delete.py      # Delete mode benchmark
├── scenarios/                # Multi-step API scenario definitions
│   ├── ecommerce.py          # 5-step e-commerce flow
│   ├── devops.py             # Issue triage flow
│   └── datapipeline.py       # Data pipeline scenarios
├── simulated_apis/           # Mock API backends for agentic chain tests
├── primers.py                # JMD format instruction variants
├── metrics.py                # Token counting and timing utilities
├── validators.py             # Output validation helpers
└── config.py                 # Model definitions and API configuration
```

## Results

Raw results are written to `../benchmark_results/`. See the [benchmark_results README](../benchmark_results/README.md) for the data structure.
