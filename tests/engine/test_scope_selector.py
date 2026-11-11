"""A field selector ":scope" reads the item element itself (cards that are themselves links)."""

import pytest
from pydantic import ValidationError

from app.engine.extract import extract_list
from app.flow.schema import ClickConfig, ExtractListConfig

HTML = """<div><a class="group" href="/p/1"><h3>One</h3></a>
<a class="group" href="/p/2"><h3>Two</h3></a></div>"""


def config(url_selector: str) -> ExtractListConfig:
    return ExtractListConfig.model_validate({"base_selector": "a.group", "identity_key": "url", "fields": [
        {"name": "title", "selector": "h3", "type": "text", "required": True},
        {"name": "url", "selector": url_selector, "attr": "href", "type": "url", "required": True}]})


def test_scope_reads_the_item_itself():
    items = extract_list(HTML, "https://example.com/", config(":scope"))
    assert [i.data["url"] for i in items] == ["https://example.com/p/1", "https://example.com/p/2"]
    assert all(i.data["title"] for i in items)


def test_a_descendant_link_selector_finds_nothing_in_a_link_card():
    items = extract_list(HTML, "https://example.com/", config("h3 a"))
    assert all(i.data["url"] is None for i in items)


def test_scope_is_only_accepted_for_fields():
    with pytest.raises(ValidationError):
        ClickConfig.model_validate({"selector": ":scope"})
    with pytest.raises(ValidationError):
        config("&")
