# Benchmark Results

This directory contains the raw output of the benchmark runs that underlie [BENCHMARKS.md](../BENCHMARKS.md) and [jmd-efficiency-analysis.md](../jmd-efficiency-analysis.md). The data is provided as-is for reference and reproducibility.

## Structure

```
benchmark_results/
├── benchmark_results_steps.csv       # Per-step token and timing data (main run)
├── benchmark_results_streaming.csv   # TTFUB streaming measurements (main run)
├── compute_raw.json                  # Raw server processing time data
├── phase2_results.json               # Cross-model validity results
├── phase3_results.json               # Agentic chain results (720 chains)
├── phase4_epistemic_results.json     # Deploy-gate epistemic scenario
├── phase5_hallucination_results.json # Due-diligence, restrictive prompt
├── phase5b_inference_results.json    # Due-diligence, permissive prompt
├── phase6a_mode_agility_results.json # Four document modes agility
├── phase6b_nesting_results.json      # Deep nesting
├── phase6c_schema_roundtrip_results.json  # Schema roundtrip
├── phase7_qbe_results.json           # Query by Example
├── phase8_delete_results.json        # Delete mode
├── streaming_chain_results.json      # Full streaming chain measurements
├── single_run_*/                     # Per-model result directories
│   ├── benchmark_results_steps.csv
│   └── benchmark_results_streaming.csv
└── live_test_*.md                    # Manual validation records
```

## Notes

- `single_run_*/` directories contain results from individual model runs used to cross-validate the aggregated data.
- `live_test_*.md` files are manual records of live model interactions used to validate the minimal 5-bullet JMD primer.
- All JSON result files follow the structure documented in the corresponding benchmark scripts in `../benchmark/`.
