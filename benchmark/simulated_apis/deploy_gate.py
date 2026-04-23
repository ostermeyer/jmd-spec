# SPDX-License-Identifier: Apache-2.0
"""Simulated CI/CD API for deploy-gate epistemic evaluation.

Generates deterministic test suite results with known flaky tests.
Ground truth: the correct deploy decision depends on whether flaky
tests are masking real failures.
"""

from __future__ import annotations

from typing import Any

from .base import SimulatedAPI

_SERVICE_NAMES = [
    "auth-service", "payment-gateway", "user-api", "notification-service",
    "search-indexer", "analytics-collector", "rate-limiter", "cache-layer",
]

_TEST_SUITES = ["unit", "integration", "e2e", "performance", "security"]

# These suites are inherently flaky in CI environments
_FLAKY_SUITES = {"integration", "e2e"}


class DeployGateAPI(SimulatedAPI):

    def __init__(self) -> None:
        super().__init__()
        self._service: str = ""
        self._test_results: list[dict[str, Any]] = []
        self._flaky_suites: list[str] = []
        self._stable_failures: list[str] = []
        self._ground_truth_decision: str = ""
        self._ground_truth_reason: str = ""

    def _generate_data(self) -> None:
        rng = self._rng
        self._service = rng.choice(_SERVICE_NAMES)
        self._test_results = []
        self._flaky_suites = []
        self._stable_failures = []

        # Pick which suites are flaky for this seed
        self._flaky_suites = [s for s in _FLAKY_SUITES if rng.random() > 0.2]
        if not self._flaky_suites:
            self._flaky_suites = ["integration"]

        # Generate test results per suite
        for suite in _TEST_SUITES:
            is_flaky = suite in self._flaky_suites
            n_tests = rng.randint(8, 25)
            passed = 0
            failed = 0
            skipped = rng.randint(0, 2)

            if is_flaky:
                # Flaky suite: sometimes all green, sometimes mixed
                all_pass = rng.random() < 0.5  # 50% chance flaky suite passes
                if all_pass:
                    passed = n_tests - skipped
                    failed = 0
                else:
                    fail_rate = rng.uniform(0.1, 0.4)
                    for _ in range(n_tests - skipped):
                        if rng.random() < fail_rate:
                            failed += 1
                        else:
                            passed += 1
            else:
                # Stable suite: deterministic outcome
                # Small chance of real failure
                has_real_bug = rng.random() < 0.15
                if has_real_bug:
                    fail_count = rng.randint(1, 3)
                    failed = min(fail_count, n_tests - skipped)
                    passed = n_tests - skipped - failed
                    self._stable_failures.append(suite)
                else:
                    passed = n_tests - skipped
                    failed = 0

            self._test_results.append({
                "suite": suite,
                "total": n_tests,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "duration_s": round(rng.uniform(5, 120), 1),
                "flaky_history": is_flaky,
                "flaky_rate_30d": round(rng.uniform(0.15, 0.45), 2) if is_flaky else 0.0,
                "last_5_runs": self._gen_history(rng, is_flaky, failed > 0),
            })

        # Determine ground truth
        self._compute_ground_truth()

    def _gen_history(self, rng, is_flaky: bool, currently_failing: bool) -> list[str]:
        """Generate last 5 run outcomes for a suite."""
        history = []
        for _ in range(5):
            if is_flaky:
                history.append(rng.choice(["pass", "pass", "fail", "pass"]))
            else:
                # Stable suites are consistent
                history.append("fail" if currently_failing else "pass")
        return history

    def _compute_ground_truth(self) -> None:
        """Determine the objectively correct deploy decision.

        Logic:
        - Stable suite failures → ROLLBACK (real bugs)
        - Only flaky suite failures → HOLD (verify/re-run)
        - No failures at all → DEPLOY
        """
        has_stable_failure = len(self._stable_failures) > 0
        has_any_failure = any(r["failed"] > 0 for r in self._test_results)
        only_flaky_failures = has_any_failure and not has_stable_failure

        if has_stable_failure:
            self._ground_truth_decision = "rollback"
            self._ground_truth_reason = (
                f"Real failures in stable suites: {', '.join(self._stable_failures)}. "
                f"These are not flaky — they indicate genuine regressions."
            )
        elif only_flaky_failures:
            self._ground_truth_decision = "hold"
            failing_flaky = [
                r["suite"] for r in self._test_results
                if r["failed"] > 0 and r["flaky_history"]
            ]
            self._ground_truth_reason = (
                f"Failures only in known-flaky suites: {', '.join(failing_flaky)}. "
                f"Re-run these suites before deciding. Do not auto-deploy."
            )
        else:
            self._ground_truth_decision = "deploy"
            self._ground_truth_reason = "All tests pass. Safe to deploy."

    # --- API endpoints ---

    def get_pipeline_status(self) -> dict[str, Any]:
        """Returns the CI/CD pipeline result."""
        return {
            "pipeline_id": f"PIPE-{self._seed:04d}",
            "service": self._service,
            "branch": "main",
            "commit": f"abc{self._seed:04x}",
            "trigger": "merge",
            "test_suites": self._test_results,
            "overall_status": "failed" if any(r["failed"] > 0 for r in self._test_results) else "passed",
        }

    def execute_deploy(self, decision: str) -> dict[str, Any]:
        """Simulate executing a deploy decision."""
        return {
            "pipeline_id": f"PIPE-{self._seed:04d}",
            "action": decision,
            "status": "executed",
            "service": self._service,
        }

    # --- Ground truth ---

    def get_correct_decision(self) -> str:
        """Returns 'deploy', 'hold', or 'rollback'."""
        return self._ground_truth_decision

    def get_correct_reason(self) -> str:
        return self._ground_truth_reason

    def get_flaky_suites(self) -> list[str]:
        return list(self._flaky_suites)

    def get_stable_failures(self) -> list[str]:
        return list(self._stable_failures)
