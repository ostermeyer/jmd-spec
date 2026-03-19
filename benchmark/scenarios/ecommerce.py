"""E-Commerce scenario: 5-step agent chain."""

from __future__ import annotations

from typing import Any

from .base import Scenario, Step
from ..simulated_apis.ecommerce import ECommerceAPI
from ..validators import (
    validate_ecommerce_step1,
    validate_ecommerce_step2,
    validate_ecommerce_step3,
    validate_ecommerce_step4,
    validate_ecommerce_step5,
)

_API = ECommerceAPI()

# --- Step functions ---


def _step1_response(api: ECommerceAPI, carry: dict) -> Any:
    return api.search_products()


def _step1_extract(parsed: Any) -> dict:
    """Extract top-3 product IDs for next step."""
    from ..validators import _extract_ids
    ids = _extract_ids(parsed, "id") or _extract_ids(parsed, "product_id")
    return {"top3_ids": ids[:3]}


def _step2_response(api: ECommerceAPI, carry: dict) -> Any:
    ids = carry.get("top3_ids", [p["id"] for p in api.search_products()[:3]])
    return api.check_availability(ids)


def _step2_extract(parsed: Any) -> dict:
    from ..validators import _extract_ids
    ids = _extract_ids(parsed, "product_id") or _extract_ids(parsed, "id")
    best = ids[0] if ids else None
    # Also try to get it from a "selected" or "best" field
    if isinstance(parsed, dict):
        best = parsed.get("product_id") or parsed.get("selected_product") or best
    return {"best_product_id": best}


def _step3_response(api: ECommerceAPI, carry: dict) -> Any:
    pid = carry.get("best_product_id", api.get_expected_best_available())
    product = next(
        (p for p in api.search_products() if p["id"] == pid),
        api.get_expected_best_available_product(),
    )
    return {
        "selected_product": product,
        "instruction": "Create a cart with this product (quantity: 1) and a shipping address.",
    }


def _step3_extract(parsed: Any) -> dict:
    if isinstance(parsed, dict):
        cart_items = parsed.get("items", [])
        if not cart_items and parsed.get("product_id"):
            cart_items = [{"product_id": parsed["product_id"], "quantity": parsed.get("quantity", 1)}]
        return {"cart_request": parsed}
    return {"cart_request": {}}


def _step4_response(api: ECommerceAPI, carry: dict) -> Any:
    cart_req = carry.get("cart_request", {})
    items = cart_req.get("items", [{"product_id": api.get_expected_best_available(), "quantity": 1}])
    cart = api.create_cart(items)
    address = cart_req.get("shipping_address", {"street": "123 Main St", "city": "Anytown", "zip": "12345"})
    return api.place_order(cart["cart_id"], address)


def _step4_extract(parsed: Any) -> dict:
    if isinstance(parsed, dict):
        return {
            "order_id": parsed.get("order_id") or parsed.get("id"),
            "delivery_days": parsed.get("estimated_delivery_days"),
        }
    return {}


def _step5_response(api: ECommerceAPI, carry: dict) -> Any:
    oid = carry.get("order_id")
    if oid:
        return api.get_order(oid)
    # Fallback: return last placed order data
    return {"order_id": oid, "status": "confirmed"}


def _step5_extract(parsed: Any) -> dict:
    return {}  # final step


# --- Scenario definition ---

ecommerce_scenario = Scenario(
    name="ecommerce",
    api=_API,
    steps=[
        Step(
            name="search_products",
            system_prompt_extra=(
                "You are helping a customer find the best products. "
                "Analyze the product catalog and identify the top 3 products "
                "by rating (highest first). Return their IDs, names, ratings, and prices."
            ),
            user_message_template=(
                "Here is the product catalog. Identify the top 3 products by rating. "
                "Return a structured response with the selected products."
            ),
            get_api_response=_step1_response,
            label="Products",
            validator=validate_ecommerce_step1,
            extract_for_next=_step1_extract,
        ),
        Step(
            name="check_availability",
            system_prompt_extra=(
                "Check product availability and select the best available product "
                "(highest rated among in-stock items). Return the selected product ID "
                "and availability details."
            ),
            user_message_template=(
                "Here is the availability data for the top products. "
                "Select the best available product (highest rated, in stock). "
                "Return the selected product with its availability info."
            ),
            get_api_response=_step2_response,
            label="Availability",
            validator=validate_ecommerce_step2,
            extract_for_next=_step2_extract,
        ),
        Step(
            name="build_cart",
            system_prompt_extra=(
                "Build a cart request body for the selected product. "
                "Include: product_id, quantity (1), and a shipping_address "
                "with street, city, and zip fields."
            ),
            user_message_template=(
                "Based on the selected product, create a cart request body. "
                "Include product_id, quantity: 1, and a shipping_address."
            ),
            get_api_response=_step3_response,
            label="SelectedProduct",
            validator=validate_ecommerce_step3,
            extract_for_next=_step3_extract,
        ),
        Step(
            name="place_order",
            system_prompt_extra=(
                "The order has been placed. Extract the order_id and "
                "estimated_delivery_days from the confirmation."
            ),
            user_message_template=(
                "The order was placed successfully. Extract the order_id and "
                "delivery information from this confirmation."
            ),
            get_api_response=_step4_response,
            label="OrderConfirmation",
            validator=validate_ecommerce_step4,
            extract_for_next=_step4_extract,
        ),
        Step(
            name="summarize",
            system_prompt_extra=(
                "Summarize the completed order for the customer. "
                "Include the order ID, product details, total cost, and delivery estimate."
            ),
            user_message_template=(
                "Here are the full order details. Write a concise, human-readable "
                "summary for the customer."
            ),
            get_api_response=_step5_response,
            label="OrderDetails",
            validator=validate_ecommerce_step5,
            extract_for_next=_step5_extract,
            expects_structured=False,
        ),
    ],
)
