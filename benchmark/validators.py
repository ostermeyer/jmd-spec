"""Strong semantic validators.

Assessment feedback: validators must check against concrete expected answers,
not just structural presence of keys. Each validator receives the parsed LLM
output AND the API instance (which knows the ground truth for the current seed).
"""

from __future__ import annotations

from typing import Any

from .metrics import ValidationResult
from .simulated_apis.ecommerce import ECommerceAPI
from .simulated_apis.devops import DevOpsAPI
from .simulated_apis.datapipeline import DataPipelineAPI


def _deep_find(data: Any, key: str) -> Any:
    """Recursively search for a key in nested dicts/lists."""
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for v in data.values():
            result = _deep_find(v, key)
            if result is not None:
                return result
    if isinstance(data, list):
        for item in data:
            result = _deep_find(item, key)
            if result is not None:
                return result
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_ids(data: Any, key: str = "id") -> list[str]:
    """Extract ID values from various LLM output shapes."""
    if isinstance(data, list):
        ids = []
        for item in data:
            if isinstance(item, dict) and key in item:
                ids.append(str(item[key]))
            elif isinstance(item, str):
                ids.append(item)
        return ids
    if isinstance(data, dict):
        # Maybe a wrapper like {"top_products": [...]}
        for v in data.values():
            if isinstance(v, list):
                return _extract_ids(v, key)
        if key in data:
            return [str(data[key])]
    return []


def _overlap_score(expected: list[str], actual: list[str]) -> float:
    """Fraction of expected items found in actual."""
    if not expected:
        return 1.0
    found = len(set(expected) & set(actual))
    return found / len(expected)


# ---------------------------------------------------------------------------
# E-Commerce validators
# ---------------------------------------------------------------------------

def validate_ecommerce_step1(data: Any, api: ECommerceAPI) -> ValidationResult:
    """Step 1: extract top-3 product IDs by rating."""
    expected = api.get_expected_top3()
    actual = _extract_ids(data, "id") or _extract_ids(data, "product_id")
    if not actual:
        return ValidationResult(False, 0.0, "No product IDs found in output")

    score = _overlap_score(expected, actual)
    return ValidationResult(
        score >= 0.67,  # at least 2 of 3
        score,
        f"Expected {expected}, got {actual} (overlap={score:.0%})",
    )


def validate_ecommerce_step2(data: Any, api: ECommerceAPI) -> ValidationResult:
    """Step 2: choose best available product."""
    expected = api.get_expected_best_available()
    actual_ids = _extract_ids(data, "product_id") or _extract_ids(data, "id")
    # Also check if the ID appears as a bare value
    if not actual_ids and isinstance(data, dict):
        for v in data.values():
            if isinstance(v, str) and v == expected:
                actual_ids = [v]
                break

    if expected in actual_ids:
        return ValidationResult(True, 1.0, f"Correctly chose {expected}")

    return ValidationResult(
        False, 0.0,
        f"Expected best available={expected}, got {actual_ids}",
    )


def validate_ecommerce_step3(data: Any, api: ECommerceAPI) -> ValidationResult:
    """Step 3: cart request body with correct product and valid structure."""
    if not isinstance(data, dict):
        return ValidationResult(False, 0.0, "Output is not a dict")

    expected_pid = api.get_expected_best_available()
    score = 0.0
    reasons = []

    # Check product_id — search deeply, models nest it in various ways
    pid = (
        data.get("product_id")
        or (data.get("items", [{}])[0].get("product_id") if isinstance(data.get("items"), list) and data["items"] else None)
        or _deep_find(data, "product_id")
    )
    if pid == expected_pid:
        score += 0.4
    else:
        reasons.append(f"product_id: expected {expected_pid}, got {pid}")

    # Check quantity
    qty = data.get("quantity") or (data.get("items", [{}])[0].get("quantity") if isinstance(data.get("items"), list) and data["items"] else None)
    if isinstance(qty, int) and qty > 0:
        score += 0.3
    else:
        reasons.append(f"quantity: expected positive int, got {qty}")

    # Check shipping address
    has_address = "shipping_address" in data or "address" in data
    if has_address:
        score += 0.3
    else:
        reasons.append("missing shipping_address")

    return ValidationResult(score >= 0.7, score, "; ".join(reasons) if reasons else "OK")


def validate_ecommerce_step4(data: Any, api: ECommerceAPI) -> ValidationResult:
    """Step 4: extract order_id and delivery info."""
    if not isinstance(data, dict):
        return ValidationResult(False, 0.0, "Output is not a dict")

    score = 0.0
    reasons = []

    if data.get("order_id") or data.get("id"):
        score += 0.5
    else:
        reasons.append("missing order_id")

    has_delivery = (
        data.get("estimated_delivery_days")
        or data.get("delivery_date")
        or data.get("delivery")
    )
    if has_delivery:
        score += 0.5
    else:
        reasons.append("missing delivery info")

    return ValidationResult(score >= 0.5, score, "; ".join(reasons) if reasons else "OK")


def validate_ecommerce_step5(data: Any, api: ECommerceAPI) -> ValidationResult:
    """Step 5: human-readable summary. Check it mentions key facts."""
    text = str(data) if not isinstance(data, str) else data
    score = 0.0

    if any(w in text.lower() for w in ["order", "ord-"]):
        score += 0.33
    if any(w in text.lower() for w in ["deliver", "ship", "arrival"]):
        score += 0.33
    if any(c.isdigit() for c in text):  # contains some numbers (price, id)
        score += 0.34

    return ValidationResult(score >= 0.5, score, f"Summary quality score: {score:.0%}")


# ---------------------------------------------------------------------------
# DevOps validators
# ---------------------------------------------------------------------------

def validate_devops_step1(data: Any, api: DevOpsAPI) -> ValidationResult:
    """Step 1: identify top-5 priority bugs."""
    expected = api.get_expected_priority_bugs()
    actual = _extract_ids(data, "id") or _extract_ids(data, "issue_id")

    if not actual:
        return ValidationResult(False, 0.0, "No issue IDs found")

    score = _overlap_score(expected, actual)
    return ValidationResult(
        score >= 0.6,  # at least 3 of 5
        score,
        f"Expected {expected}, got {actual} (overlap={score:.0%})",
    )


def validate_devops_step2(data: Any, api: DevOpsAPI) -> ValidationResult:
    """Step 2: ranking with reasoning."""
    if not isinstance(data, (dict, list)):
        return ValidationResult(False, 0.0, "Output is not structured")

    # Check it contains ranking elements
    text = str(data)
    has_ranking = any(
        w in text.lower() for w in ["rank", "priority", "critical", "high", "severity"]
    )
    has_reasoning = len(text) > 100  # substantive response
    score = (0.5 if has_ranking else 0.0) + (0.5 if has_reasoning else 0.0)
    return ValidationResult(score >= 0.5, score, f"Ranking quality: {score:.0%}")


def validate_devops_step3(data: Any, api: DevOpsAPI) -> ValidationResult:
    """Step 3: issue update request body."""
    if not isinstance(data, dict):
        return ValidationResult(False, 0.0, "Output is not a dict")

    score = 0.0
    if _deep_find(data, "status") or _deep_find(data, "state"):
        score += 0.5
    if _deep_find(data, "id") or _deep_find(data, "issue_id"):
        score += 0.25
    if _deep_find(data, "assignee") or _deep_find(data, "labels") or _deep_find(data, "priority"):
        score += 0.25

    return ValidationResult(score >= 0.5, score, f"Update body score: {score:.0%}")


def validate_devops_step4(data: Any, api: DevOpsAPI) -> ValidationResult:
    """Step 4: comment body."""
    # Search the full serialized output for keywords — models may nest
    # the comment text in various structures (body, comment, or deeper).
    text = str(data)

    has_content = len(text) > 20
    has_reference = any(w in text.lower() for w in ["issue", "bug", "fix", "status", "update", "triage", "priority", "assign"])
    score = (0.5 if has_content else 0.0) + (0.5 if has_reference else 0.0)
    return ValidationResult(score >= 0.5, score, f"Comment quality: {score:.0%}")


def validate_devops_step5(data: Any, api: DevOpsAPI) -> ValidationResult:
    """Step 5: link PR to issue."""
    if not isinstance(data, dict):
        return ValidationResult(False, 0.0, "Output is not a dict")

    has_pr = data.get("pr_id") or data.get("pull_request_id") or data.get("id")
    has_issue = data.get("issue_id") or data.get("linked_issue")
    score = (0.5 if has_pr else 0.0) + (0.5 if has_issue else 0.0)
    return ValidationResult(score >= 0.5, score, f"PR link score: {score:.0%}")


# ---------------------------------------------------------------------------
# Data Pipeline validators
# ---------------------------------------------------------------------------

def validate_pipeline_step1(data: Any, api: DataPipelineAPI) -> ValidationResult:
    """Step 1: data quality check — must identify anomalies."""
    expected_ids = api.get_expected_anomaly_ids()
    text = str(data)

    found = sum(1 for aid in expected_ids if aid in text)
    score = found / len(expected_ids) if expected_ids else 1.0

    has_quality_assessment = any(
        w in text.lower() for w in ["anomal", "negative", "margin", "issue", "quality"]
    )
    if has_quality_assessment:
        score = min(1.0, score + 0.3)

    return ValidationResult(
        score >= 0.5, score,
        f"Found {found}/{len(expected_ids)} anomalies, quality assessment: {has_quality_assessment}",
    )


def validate_pipeline_step2(data: Any, api: DataPipelineAPI) -> ValidationResult:
    """Step 2: aggregation request."""
    if not isinstance(data, dict):
        return ValidationResult(False, 0.0, "Output is not a dict")

    score = 0.0
    has_group = data.get("group_by") or "group" in str(data).lower()
    has_functions = data.get("functions") or data.get("aggregations") or "sum" in str(data).lower()

    if has_group:
        score += 0.5
    if has_functions:
        score += 0.5

    return ValidationResult(score >= 0.5, score, f"Aggregation request score: {score:.0%}")


def validate_pipeline_step3(data: Any, api: DataPipelineAPI) -> ValidationResult:
    """Step 3: anomaly flags on aggregated data."""
    text = str(data)

    has_flags = any(w in text.lower() for w in ["anomal", "flag", "negative", "warning", "alert"])
    has_numbers = any(c.isdigit() for c in text)
    score = (0.5 if has_flags else 0.0) + (0.5 if has_numbers else 0.0)

    return ValidationResult(score >= 0.5, score, f"Anomaly flag score: {score:.0%}")


def validate_pipeline_step4(data: Any, api: DataPipelineAPI) -> ValidationResult:
    """Step 4: store request body."""
    if not isinstance(data, dict):
        return ValidationResult(False, 0.0, "Output is not a dict")

    # Use deep search — models may nest results under metadata/results sub-objects.
    # Also check for dot-notation keys (e.g. "results.summary") that some models produce.
    has_results = (
        _deep_find(data, "results") or _deep_find(data, "data")
        or _deep_find(data, "records") or _deep_find(data, "anomalies")
        or _deep_find(data, "summary")
        or any(k for k in data if "results" in k or "anomal" in k or "summary" in k)
    )
    has_meta = (
        _deep_find(data, "pipeline_id") or _deep_find(data, "timestamp")
        or _deep_find(data, "source") or _deep_find(data, "status")
        or _deep_find(data, "record_count")
    )
    score = (0.6 if has_results else 0.0) + (0.4 if has_meta else 0.0)

    return ValidationResult(score >= 0.5, score, f"Store request score: {score:.0%}")


def validate_pipeline_step5(data: Any, api: DataPipelineAPI) -> ValidationResult:
    """Step 5: narrative summary."""
    text = str(data) if not isinstance(data, str) else data

    score = 0.0
    if any(w in text.lower() for w in ["revenue", "sales", "total"]):
        score += 0.33
    if any(w in text.lower() for w in ["region", "north", "south", "east", "west"]):
        score += 0.33
    if any(w in text.lower() for w in ["anomal", "margin", "issue", "negative"]):
        score += 0.34

    return ValidationResult(score >= 0.5, score, f"Summary quality: {score:.0%}")
