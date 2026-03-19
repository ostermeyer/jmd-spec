"""Simulated Data Pipeline REST API.

30 sales records, aggregation, anomaly detection.
"""

from __future__ import annotations

from typing import Any

from .base import SimulatedAPI

_REGIONS = ["North", "South", "East", "West", "Central"]
_PRODUCTS = ["Widget A", "Widget B", "Gadget X", "Gadget Y", "Tool Z"]


class DataPipelineAPI(SimulatedAPI):

    def __init__(self) -> None:
        super().__init__()
        self._records: list[dict[str, Any]] = []
        self._aggregated: list[dict[str, Any]] = []
        self._anomalies: list[dict[str, Any]] = []

    def _generate_data(self) -> None:
        rng = self._rng
        self._records = []

        for i in range(30):
            month = (i % 12) + 1
            region = rng.choice(_REGIONS)
            product = rng.choice(_PRODUCTS)
            qty = rng.randint(5, 200)
            unit_price = round(rng.uniform(10.0, 150.0), 2)
            revenue = round(qty * unit_price, 2)
            cost = round(revenue * rng.uniform(0.4, 0.85), 2)

            # Inject 2-3 anomalies: negative margin or extreme qty
            is_anomaly = i in (7, 18, 25)
            if is_anomaly:
                cost = round(revenue * rng.uniform(1.05, 1.4), 2)  # negative margin

            self._records.append({
                "id": f"REC-{i:03d}",
                "date": f"2025-{month:02d}-{rng.randint(1, 28):02d}",
                "region": region,
                "product": product,
                "quantity": qty,
                "unit_price": unit_price,
                "revenue": revenue,
                "cost": cost,
                "margin": round(revenue - cost, 2),
            })

        # Pre-compute aggregation (by region)
        region_agg: dict[str, dict[str, float]] = {}
        for r in self._records:
            reg = r["region"]
            if reg not in region_agg:
                region_agg[reg] = {"total_revenue": 0, "total_cost": 0, "total_qty": 0, "count": 0}
            region_agg[reg]["total_revenue"] += r["revenue"]
            region_agg[reg]["total_cost"] += r["cost"]
            region_agg[reg]["total_qty"] += r["quantity"]
            region_agg[reg]["count"] += 1

        self._aggregated = [
            {
                "region": reg,
                "total_revenue": round(agg["total_revenue"], 2),
                "total_cost": round(agg["total_cost"], 2),
                "total_margin": round(agg["total_revenue"] - agg["total_cost"], 2),
                "avg_quantity": round(agg["total_qty"] / agg["count"], 1),
                "record_count": int(agg["count"]),
            }
            for reg, agg in sorted(region_agg.items())
        ]

        # Anomalies: records with negative margin
        # Some anomalies are clear, others are borderline
        self._anomalies = []
        for r in self._records:
            if r["margin"] < 0:
                severity = "clear" if r["margin"] < -100 else "borderline"
                self._anomalies.append({
                    "record_id": r["id"],
                    "type": "negative_margin",
                    "margin": r["margin"],
                    "revenue": r["revenue"],
                    "cost": r["cost"],
                    "detection_confidence": "high" if severity == "clear" else "medium",
                    "detection_method": "rule-based (margin < 0)",
                })
            elif abs(r["quantity"] - 100) > 80:
                # Extreme quantity — statistical outlier, uncertain
                self._anomalies.append({
                    "record_id": r["id"],
                    "type": "quantity_outlier",
                    "quantity": r["quantity"],
                    "detection_confidence": "low",
                    "detection_method": "statistical (>2σ from mean)",
                })

    # --- API endpoints ---

    def get_dataset(self) -> list[dict[str, Any]]:
        return list(self._records)

    def aggregate(self, group_by: str = "region") -> list[dict[str, Any]]:
        return list(self._aggregated)

    def get_anomalies(self) -> list[dict[str, Any]]:
        return list(self._anomalies)

    def store_results(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"status": "stored", "records_written": len(data.get("results", []))}

    def get_pipeline_summary(self) -> dict[str, Any]:
        total_rev = sum(r["revenue"] for r in self._records)
        total_cost = sum(r["cost"] for r in self._records)
        return {
            "total_records": len(self._records),
            "total_revenue": round(total_rev, 2),
            "total_cost": round(total_cost, 2),
            "total_margin": round(total_rev - total_cost, 2),
            "anomaly_count": len(self._anomalies),
            "regions": len(self._aggregated),
        }

    # --- Expected answers ---

    def get_expected_anomaly_ids(self) -> list[str]:
        return [a["record_id"] for a in self._anomalies]

    def get_expected_aggregation(self) -> list[dict[str, Any]]:
        return list(self._aggregated)

    def get_expected_top_region(self) -> str:
        """Region with highest total revenue."""
        return max(self._aggregated, key=lambda a: a["total_revenue"])["region"]
