# SPDX-License-Identifier: Apache-2.0
"""Metrics collection and aggregation."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ValidationResult:
    valid: bool
    score: float = 1.0      # 0.0-1.0 partial credit
    reason: str = ""


@dataclass
class StepMetrics:
    run_id: int
    scenario: str
    format_name: str
    primer_variant: str
    step_index: int
    step_name: str
    input_tokens: int
    output_tokens: int
    payload_bytes: int
    payload_tokens: int
    wall_clock_s: float
    syn_valid: bool
    sem_correct: bool
    sem_score: float
    cost_usd: float
    server_processing_ms: float = 0.0
    skipped: bool = False
    raw_output: str = ""
    extracted_text: str = ""
    fence_method: str = ""       # "exact", "any_fence", "none", "freetext"
    parse_error: str = ""
    sem_reason: str = ""
    model: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ChainResult:
    scenario: str
    format_name: str
    primer_variant: str
    run_id: int
    steps: list[StepMetrics]

    @property
    def complete(self) -> bool:
        return all(s.syn_valid for s in self.steps)

    @property
    def total_tokens(self) -> int:
        return sum(s.total_tokens for s in self.steps)

    @property
    def total_cost(self) -> float:
        return sum(s.cost_usd for s in self.steps)

    @property
    def total_wall_clock(self) -> float:
        return sum(s.wall_clock_s for s in self.steps)


@dataclass
class StreamingMetrics:
    scenario: str
    format_name: str
    run_id: int
    step_name: str
    total_time_s: float
    ttfub_s: float           # time to first useful byte


class MetricsCollector:
    """Accumulates all benchmark metrics."""

    def __init__(self) -> None:
        self.chains: list[ChainResult] = []
        self.streaming: list[StreamingMetrics] = []

    def record_chain(self, result: ChainResult) -> None:
        self.chains.append(result)

    def record_streaming(self, result: StreamingMetrics) -> None:
        self.streaming.append(result)

    def get_chains(
        self,
        scenario: str | None = None,
        format_name: str | None = None,
        primer_variant: str | None = None,
    ) -> list[ChainResult]:
        results = self.chains
        if scenario:
            results = [c for c in results if c.scenario == scenario]
        if format_name:
            results = [c for c in results if c.format_name == format_name]
        if primer_variant:
            results = [c for c in results if c.primer_variant == primer_variant]
        return results

    def get_all_steps(
        self,
        scenario: str | None = None,
        format_name: str | None = None,
    ) -> list[StepMetrics]:
        steps = []
        for chain in self.get_chains(scenario, format_name):
            steps.extend(chain.steps)
        return steps


def mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    n = len(values)
    m = sum(values) / n
    if n < 2:
        return m, 0.0
    variance = sum((x - m) ** 2 for x in values) / (n - 1)
    return m, math.sqrt(variance)


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% confidence interval for a proportion."""
    if total == 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    return max(0.0, centre - spread), min(1.0, centre + spread)
