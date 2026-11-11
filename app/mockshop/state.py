"""The mock shop's data: invented products only (no real store, no personal data; committee change 7).

The state lives in memory on purpose: the admin page changes it during the demo (a price, a removed
product, layout v2, a blocked page), and a restart puts the shop back to normal.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from decimal import Decimal

PER_PAGE = 6


@dataclass
class Product:
    slug: str
    sku: str
    title: str
    price: Decimal
    stock: str          # "In stock" | "Only 2 left" | "Sold out"
    description: str


CATALOGUE: list[Product] = [
    Product("blue-kettle", "KT-100", "Blue Kettle", Decimal("1250"), "In stock", "1.7 litre steel kettle."),
    Product("steel-flask", "FL-200", "Steel Flask", Decimal("2400"), "In stock", "Keeps tea hot for 12 hours."),
    Product("tea-set", "TS-300", "Tea Set", Decimal("3999"), "Only 2 left", "Six cups and a teapot."),
    Product("spice-jar", "SJ-400", "Spice Jar Set", Decimal("850"), "In stock", "Twelve glass jars."),
    Product("rice-cooker", "RC-500", "Rice Cooker", Decimal("6499"), "In stock", "1.8 litre, keeps warm."),
    Product("cutting-board", "CB-600", "Cutting Board", Decimal("1500"), "Sold out", "Bamboo, 40 cm."),
    Product("chai-mug", "CM-700", "Chai Mug", Decimal("450"), "In stock", "Hand-painted clay mug."),
    Product("lunch-box", "LB-800", "Lunch Box", Decimal("1250"), "In stock", "Three steel tiers."),
    Product("table-lamp", "TL-900", "Table Lamp", Decimal("3200"), "In stock", "Warm white LED."),
    Product("cushion-cover", "CC-110", "Cushion Cover", Decimal("999"), "Only 5 left", "Hand-embroidered."),
    Product("wall-clock", "WC-120", "Wall Clock", Decimal("2750"), "In stock", "Silent sweep, 30 cm."),
    Product("prayer-mat", "PM-130", "Prayer Mat", Decimal("1800"), "In stock", "Soft velvet, foldable."),
]

LAYOUTS = ("v1", "v2")
MODES = ("normal", "blocked", "js", "dupes")


@dataclass
class ShopState:
    products: list[Product] = field(default_factory=lambda: copy.deepcopy(CATALOGUE))
    removed: set[str] = field(default_factory=set)
    layout: str = "v1"
    mode: str = "normal"

    def visible(self) -> list[Product]:
        return [p for p in self.products if p.slug not in self.removed]

    def find(self, slug: str) -> Product | None:
        return next((p for p in self.products if p.slug == slug), None)

    def reset(self) -> None:
        fresh = ShopState()
        self.products, self.removed, self.layout, self.mode = fresh.products, fresh.removed, "v1", "normal"


state = ShopState()


def format_price(price: Decimal) -> str:
    """Rs 1,250 (Pakistani shops rarely show paisa)."""
    whole = int(price) if price == int(price) else None
    return f"Rs {whole:,}" if whole is not None else f"Rs {price:,.2f}"
