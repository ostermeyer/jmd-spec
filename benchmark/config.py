# SPDX-License-Identifier: Apache-2.0
"""Central benchmark configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BenchmarkConfig:
    # --- Runs ---
    n_runs: int = 30                    # Assessment: N=30 for meaningful stats
    seed_base: int = 1                  # Seeds seed_base..seed_base+n_runs-1

    # --- Model ---
    model: str = "claude-sonnet-4-6"
    temperature: float = 0.0            # Determinism for reproducibility
    max_tokens: int = 4096

    # --- Pricing (USD per 1M tokens, auto-detected from model) ---
    pricing_input: float = 0.0
    pricing_output: float = 0.0

    # --- Formats ---
    formats: list[str] = field(
        default_factory=lambda: ["json_minified", "yaml", "jmd"],
    )

    # --- Primer variants (Assessment: test primer effect) ---
    primer_variants: list[str] = field(
        default_factory=lambda: ["minimal", "standard", "example", "strict"],
    )
    primer_default: str = "strict"      # "strict" validated: 100% syntax on all models incl. Gemini
    primer_test_n: int = 10             # Subset for primer comparison

    # --- Streaming ---
    streaming_runs: int = 5             # TTFUB measurement runs

    # --- Output ---
    output_dir: str = "benchmark_results"

    def __post_init__(self) -> None:
        if self.pricing_input == 0.0 and self.pricing_output == 0.0:
            self._update_pricing()

    def _update_pricing(self) -> None:
        from .llm_client import get_pricing
        self.pricing_input, self.pricing_output = get_pricing(self.model)

    def get_seed(self, run_id: int) -> int:
        """Deterministic seed per run — varied data for correctness measurement."""
        return self.seed_base + run_id

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.pricing_input / 1_000_000
            + output_tokens * self.pricing_output / 1_000_000
        )
