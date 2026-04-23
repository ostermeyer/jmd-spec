# SPDX-License-Identifier: Apache-2.0
"""Benchmark scenarios."""

from .ecommerce import ecommerce_scenario
from .devops import devops_scenario
from .datapipeline import datapipeline_scenario

ALL_SCENARIOS = {
    "ecommerce": ecommerce_scenario,
    "devops": devops_scenario,
    "datapipeline": datapipeline_scenario,
}

__all__ = ["ALL_SCENARIOS", "ecommerce_scenario", "devops_scenario", "datapipeline_scenario"]
