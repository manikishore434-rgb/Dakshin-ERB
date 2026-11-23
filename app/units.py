"""Unit conversion. Every item has one base unit; any compatible unit converts into it."""
from decimal import Decimal

from .util import D, ServiceError, to_milli

# unit -> (base unit it belongs to, factor into that base)
FACTORS = {
    "kg": ("kg", Decimal("1")),
    "g": ("kg", Decimal("0.001")),
    "l": ("l", Decimal("1")),
    "ml": ("l", Decimal("0.001")),
    "piece": ("piece", Decimal("1")),
    "packet": ("packet", Decimal("1")),
}


def units_for(item) -> list:
    """Units a user may enter for this item."""
    base = item["base_unit"]
    opts = [u for u, (b, _) in FACTORS.items() if b == base]
    if item["kind"] == "finished" and item["carton_size"]:
        opts.append("carton")
    return opts


def to_base_milli(quantity, unit: str, item) -> int:
    """Convert (quantity, unit) into milli-units of the item's base unit."""
    unit = (unit or item["base_unit"]).lower()
    q = D(quantity)
    if unit == "carton":
        if item["kind"] != "finished" or not item["carton_size"]:
            raise ServiceError(f"{item['name']} is not sold in cartons")
        return to_milli(q * int(item["carton_size"]))
    if unit not in FACTORS:
        raise ServiceError(f"Unknown unit '{unit}'")
    base, factor = FACTORS[unit]
    if base != item["base_unit"]:
        raise ServiceError(f"Cannot convert {unit} to {item['base_unit']} for {item['name']}")
    return to_milli(q * factor)
