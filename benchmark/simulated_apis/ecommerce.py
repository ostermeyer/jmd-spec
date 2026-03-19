"""Simulated E-Commerce REST API.

15 products, availability checks, cart, orders.
Data varies by seed for meaningful correctness measurement across runs.
"""

from __future__ import annotations

from typing import Any

from .base import SimulatedAPI

_CATEGORIES = ["Electronics", "Clothing", "Home & Garden", "Sports", "Books"]
_BRANDS = [
    "TechPro", "StyleMax", "HomeEase", "SportFit", "ReadWell",
    "GadgetX", "FashionOne", "CozyLiving", "ActiveGear", "PageTurn",
]
_COLORS = ["Black", "White", "Blue", "Red", "Green", "Silver", "Gray"]
_ADJECTIVES = [
    "Premium", "Ultra", "Pro", "Essential", "Classic",
    "Advanced", "Compact", "Deluxe", "Smart", "Elite",
]
_NOUNS = [
    "Widget", "Gadget", "Device", "Tool", "Kit",
    "System", "Module", "Unit", "Set", "Pack",
    "Speaker", "Headphones", "Keyboard", "Monitor", "Camera",
]


class ECommerceAPI(SimulatedAPI):

    def __init__(self) -> None:
        super().__init__()
        self._products: list[dict[str, Any]] = []
        self._availability: dict[str, dict[str, Any]] = {}
        self._carts: dict[str, dict[str, Any]] = {}
        self._orders: dict[str, dict[str, Any]] = {}
        self._next_cart_id = 1
        self._next_order_id = 1

    def _generate_data(self) -> None:
        rng = self._rng
        self._products = []
        self._availability = {}
        self._carts = {}
        self._orders = {}
        self._next_cart_id = 1
        self._next_order_id = 1

        for i in range(15):
            pid = f"PROD-{1000 + i}"
            category = rng.choice(_CATEGORIES)
            brand = rng.choice(_BRANDS)
            adj = rng.choice(_ADJECTIVES)
            noun = rng.choice(_NOUNS)
            price = round(rng.uniform(9.99, 299.99), 2)
            rating = round(rng.uniform(2.5, 5.0), 1)
            stock = rng.randint(0, 50)
            weight_kg = round(rng.uniform(0.1, 15.0), 2)
            color = rng.choice(_COLORS)

            product = {
                "id": pid,
                "name": f"{adj} {noun}",
                "brand": brand,
                "category": category,
                "price": price,
                "rating": rating,
                "stock": stock,
                "description": (
                    f"The {adj} {noun} by {brand}. "
                    f"A top-rated {category.lower()} product."
                ),
                "weight_kg": weight_kg,
                "color": color,
                "sku": f"SKU-{rng.randint(10000, 99999)}",
                "warranty_months": rng.choice([6, 12, 24, 36]),
            }
            self._products.append(product)

            # Availability with explicit uncertainty markers
            ship_days_min = rng.randint(1, 4)
            ship_days_max = ship_days_min + rng.randint(1, 5)
            # Some products have conflicting ratings from different sources
            alt_rating = round(rng.uniform(2.5, 5.0), 1)
            has_rating_conflict = abs(alt_rating - rating) > 1.0

            self._availability[pid] = {
                "product_id": pid,
                "name": f"{adj} {noun}",
                "rating": rating,
                "rating_source": "vendor",
                **({"community_rating": alt_rating, "community_rating_source": "user reviews (47 reviews)"} if has_rating_conflict else {}),
                "in_stock": stock > 0,
                "quantity_available": stock,
                "stock_last_checked": "2026-03-15T08:00:00Z",
                "warehouse": rng.choice(["East", "West", "Central"]),
                "estimated_ship_days": f"{ship_days_min}-{ship_days_max}",
                "ship_estimate_confidence": rng.choice(["high", "medium", "low"]),
            }

    # --- API endpoints ---

    def search_products(self) -> list[dict[str, Any]]:
        return list(self._products)

    def check_availability(self, product_ids: list[str]) -> list[dict[str, Any]]:
        return [
            self._availability[pid]
            for pid in product_ids
            if pid in self._availability
        ]

    def create_cart(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        cart_id = f"CART-{self._next_cart_id:04d}"
        self._next_cart_id += 1
        total = sum(
            item.get("quantity", 1) * self._get_price(item.get("product_id", ""))
            for item in items
        )
        cart = {
            "cart_id": cart_id,
            "items": items,
            "total": round(total, 2),
            "currency": "USD",
            "status": "active",
        }
        self._carts[cart_id] = cart
        return cart

    def place_order(
        self, cart_id: str, shipping_address: dict[str, Any]
    ) -> dict[str, Any]:
        order_id = f"ORD-{self._next_order_id:06d}"
        self._next_order_id += 1
        cart = self._carts.get(cart_id, {"items": [], "total": 0})
        ship_min = self._rng.randint(2, 5)
        ship_max = ship_min + self._rng.randint(2, 7)
        order = {
            "order_id": order_id,
            "cart_id": cart_id,
            "items": cart["items"],
            "total": cart.get("total", 0),
            "shipping_address": shipping_address,
            "status": "confirmed",
            "estimated_delivery_days": f"{ship_min}-{ship_max}",
            "delivery_estimate_source": "carrier API (real-time)",
            "payment_status": "charged",
        }
        self._orders[order_id] = order
        return order

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._orders.get(order_id, {"error": "not found"})

    # --- Expected answers for validators ---

    def get_expected_top3(self) -> list[str]:
        """Top 3 products by rating (descending), price (ascending) as tiebreaker."""
        ranked = sorted(
            self._products,
            key=lambda p: (-p["rating"], p["price"]),
        )
        return [p["id"] for p in ranked[:3]]

    def get_expected_best_available(self) -> str:
        """Best available product: highest-rated among in-stock items."""
        in_stock = [
            p for p in self._products
            if self._availability[p["id"]]["in_stock"]
        ]
        if not in_stock:
            return self._products[0]["id"]
        best = max(in_stock, key=lambda p: (p["rating"], -p["price"]))
        return best["id"]

    def get_expected_best_available_product(self) -> dict[str, Any]:
        pid = self.get_expected_best_available()
        return next(p for p in self._products if p["id"] == pid)

    def _get_price(self, product_id: str) -> float:
        for p in self._products:
            if p["id"] == product_id:
                return p["price"]
        return 0.0
