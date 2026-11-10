"""Engine functions the sidebar agent may call (specs/contracts.md C4).

This module is the ONLY door from app/ai into the engine. Nothing in app/engine imports
app/ai (tests/engine/test_zero_ai.py checks this).

Status at M0: validate_flow and node_type_schemas are real; the rest are STUBS returning
fixed example data. A20 replaces each stub with the real implementation, same signature.
"""

from __future__ import annotations

from typing import Any

from app.engine import stub_data
from app.flow.schema import node_type_schemas as _node_type_schemas
from app.flow.validate import parse_flow as _parse_flow
from app.flow.validate import validate_flow as _validate_flow


class FetchRefused(Exception):
    """safe_fetch refused the URL (internal address, not HTML, too big, ...)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def validate_flow(flow: dict, for_publish: bool = False, draft: bool = False) -> list[dict]:
    """[] if the flow is valid, else contract C2 issues. REAL.

    The agent checks each edit with draft=True (half-built flows are fine, unsafe ones are not)
    and checks the finished flow with draft=False before saying "ready to publish".
    """
    return _validate_flow(flow, for_publish=for_publish, draft=draft)


def parse_flow(flow: dict, for_publish: bool = False, draft: bool = False) -> tuple[dict | None, list[dict]]:
    """(normalised flow, []) if valid, else (None, issues). REAL.

    Store and apply the normalised flow, never the raw input: it is exactly what was validated
    (trimmed, de-duplicated, defaults filled in).
    """
    return _parse_flow(flow, for_publish=for_publish, draft=draft)


def node_type_schemas() -> list[dict]:
    """Same payload as GET /api/node-types. REAL."""
    return _node_type_schemas()


async def fetch_outline(url: str) -> str:
    """Page HTML through safe_fetch, scripts stripped, about 30 KB. STUB."""
    return (
        "<!-- STUB outline -->\n"
        '<div id="product-grid">\n'
        '  <div class="product"><h2>Blue Kettle</h2><span class="price">Rs 1,099</span>'
        '<span class="stock">In stock</span><a href="/shop/p/blue-kettle">View</a></div>\n'
        '  <div class="product"><h2>Steel Flask</h2><span class="price">Rs 2,400</span>'
        '<span class="stock">In stock</span><a href="/shop/p/steel-flask">View</a></div>\n'
        "</div>\n"
        '<a class="next" href="/shop?page=2">Next</a>'
    )


async def test_selector(url: str, selector: str, attr: str | None = None) -> dict[str, Any]:
    """Match count and up to 5 sample values. STUB."""
    return {"count": 12, "samples": ["Rs 1,099", "Rs 2,400", "Rs 3,999", "Rs 850", "Rs 1,500"]}


async def dry_run(flow: dict, flow_id: str | None, until_node: str | None = None) -> dict[str, Any]:
    """RunReport for the draft; never writes records. STUB."""
    return stub_data.run_report(flow_id=flow_id or "flow_stub1")


async def list_datasets(flow_id: str) -> list[dict[str, Any]]:
    """The flow's datasets. STUB."""
    return stub_data.datasets(flow_id)


async def sample_records(dataset_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Read-only sample of stored records. STUB."""
    return stub_data.records()[: max(0, min(limit, 20))]
