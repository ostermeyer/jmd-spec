# SPDX-License-Identifier: Apache-2.0
"""Simulated Inventory Management API for Phase 6a: Mode Agility.

Tests whether LLMs can correctly switch between all four JMD document
modes (#, #!, #?, #-) plus Error documents within a single workflow.

The API provides a product inventory with schema, CRUD operations,
search queries, and intentional error triggers.
"""

from __future__ import annotations

from typing import Any

from .base import SimulatedAPI


_DEPARTMENTS = ["Electronics", "Furniture", "Office Supplies", "Warehouse", "Cafeteria"]
_LOCATIONS = ["Rack-A1", "Rack-B2", "Shelf-C3", "Pallet-D4", "Bin-E5", "Cage-F6"]
_STATUSES = ["active", "discontinued", "on_order", "reserved"]
_UNITS = ["pcs", "kg", "m", "liters", "boxes"]


class InventoryAPI(SimulatedAPI):
    """Deterministic inventory with schema, products, and error scenarios."""

    def __init__(self) -> None:
        super().__init__()
        self._items: dict[str, dict[str, Any]] = {}
        self._schema: dict[str, Any] = {}
        self._deleted: list[str] = []

    def _generate_data(self) -> None:
        rng = self._rng
        self._items = {}
        self._deleted = []

        # Generate 8 inventory items
        for i in range(8):
            item_id = f"INV-{2000 + i}"
            dept = rng.choice(_DEPARTMENTS)
            loc = rng.choice(_LOCATIONS)
            status = rng.choice(_STATUSES)
            unit = rng.choice(_UNITS)
            qty = rng.randint(0, 500)
            min_qty = rng.randint(5, 50)
            unit_cost = round(rng.uniform(0.50, 250.00), 2)
            last_audit = f"2026-0{rng.randint(1, 3)}-{rng.randint(10, 28):02d}"

            self._items[item_id] = {
                "id": item_id,
                "name": f"{dept} Item #{i + 1}",
                "department": dept,
                "location": loc,
                "status": status,
                "quantity": qty,
                "unit": unit,
                "min_quantity": min_qty,
                "unit_cost": unit_cost,
                "total_value": round(qty * unit_cost, 2),
                "last_audit": last_audit,
                "reorder_needed": qty < min_qty,
            }

        self._schema = self._build_schema()

    @staticmethod
    def _build_schema() -> dict[str, Any]:
        """The canonical JMD schema for an inventory item."""
        return {
            "label": "InventoryItem",
            "fields": {
                "id": {"type": "string", "modifier": "readonly", "description": "Unique inventory ID"},
                "name": {"type": "string", "description": "Human-readable item name"},
                "department": {"type": "string", "description": "Department owning this item"},
                "location": {"type": "string", "description": "Physical storage location"},
                "status": {"type": "string", "enum": ["active", "discontinued", "on_order", "reserved"]},
                "quantity": {"type": "int", "description": "Current stock count"},
                "unit": {"type": "string", "description": "Unit of measurement"},
                "min_quantity": {"type": "int", "description": "Reorder threshold"},
                "unit_cost": {"type": "float", "description": "Cost per unit in EUR"},
                "total_value": {"type": "float", "modifier": "readonly", "description": "quantity * unit_cost"},
                "last_audit": {"type": "date", "description": "Date of last physical count"},
                "reorder_needed": {"type": "bool", "modifier": "readonly", "description": "quantity < min_quantity"},
            },
        }

    # ── API endpoints ────────────────────────────────────────────────────

    def get_schema(self) -> dict[str, Any]:
        """Return the inventory item schema."""
        return self._schema

    def list_items(self) -> list[dict[str, Any]]:
        """Return all active inventory items."""
        return list(self._items.values())

    def get_item(self, item_id: str) -> dict[str, Any]:
        """Return a single item, or error if not found."""
        if item_id in self._items:
            return self._items[item_id]
        return {"error": "not_found", "message": f"Item {item_id} does not exist"}

    def delete_item(self, item_id: str) -> dict[str, Any]:
        """Delete an item. Returns confirmation or error."""
        if item_id in self._items:
            item = self._items.pop(item_id)
            self._deleted.append(item_id)
            return {"deleted": item_id, "name": item["name"], "status": "removed"}
        return {"error": "not_found", "message": f"Item {item_id} does not exist"}

    def update_item(self, item_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update an item. Rejects writes to readonly fields."""
        if item_id not in self._items:
            return {"error": "not_found", "message": f"Item {item_id} does not exist"}

        readonly = {"id", "total_value", "reorder_needed"}
        violations = set(updates.keys()) & readonly
        if violations:
            return {
                "error": "readonly_violation",
                "message": f"Cannot modify readonly fields: {', '.join(sorted(violations))}",
                "fields": sorted(violations),
            }

        self._items[item_id].update(updates)
        # Recompute derived fields
        item = self._items[item_id]
        item["total_value"] = round(item["quantity"] * item["unit_cost"], 2)
        item["reorder_needed"] = item["quantity"] < item["min_quantity"]
        return item

    # ── Ground truth for validation ──────────────────────────────────────

    def get_item_to_delete(self) -> str:
        """Return the ID of a 'discontinued' item (candidate for deletion)."""
        for item in self._items.values():
            if item["status"] == "discontinued":
                return item["id"]
        # Fallback: last item
        return list(self._items.keys())[-1]

    def get_items_needing_reorder(self) -> list[str]:
        """Return IDs of items where reorder_needed is True."""
        return [
            item["id"] for item in self._items.values()
            if item["reorder_needed"]
        ]

    def get_low_stock_query_expected(self) -> list[dict[str, Any]]:
        """Items matching a 'quantity < min_quantity' query."""
        return [
            item for item in self._items.values()
            if item["quantity"] < item["min_quantity"]
        ]

    def get_readonly_fields(self) -> list[str]:
        """Return names of readonly fields from the schema."""
        return [
            name for name, props in self._schema["fields"].items()
            if props.get("modifier") == "readonly"
        ]

    def get_nonexistent_id(self) -> str:
        """Return an ID that does not exist (for error trigger)."""
        return "INV-9999"

    def get_jmd_schema_text(self) -> str:
        """Return the schema as a JMD #! document string."""
        lines = ["#! InventoryItem"]
        for name, props in self._schema["fields"].items():
            parts = [f"{name}: {props['type']}"]
            if props.get("modifier"):
                parts.append(props["modifier"])
            if props.get("enum"):
                parts.append(f"enum({', '.join(props['enum'])})")
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    def get_jmd_data_text(self, item_id: str) -> str:
        """Return a single item as a JMD # data document."""
        item = self._items.get(item_id)
        if not item:
            return f"# Error\ncode: not_found\nmessage: Item {item_id} does not exist"
        lines = [f"# InventoryItem"]
        for key, val in item.items():
            lines.append(f"{key}: {val}")
        return "\n".join(lines)
