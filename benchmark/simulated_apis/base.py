"""Base class for simulated REST APIs.

Each API produces deterministic data from a seed, and exposes methods
to compute expected answers so validators can check LLM output against
ground truth.
"""

from __future__ import annotations

import random


class SimulatedAPI:
    """Base for deterministic simulated APIs."""

    def __init__(self) -> None:
        self._rng: random.Random = random.Random(42)
        self._seed: int = 42

    def reset(self, seed: int) -> None:
        """Reset to fresh state with a new seed."""
        self._seed = seed
        self._rng = random.Random(seed)
        self._generate_data()

    def _generate_data(self) -> None:
        raise NotImplementedError
