"""Extra demo sites (/demo): property listings, scholarships, jobs. Invented data, our own app.

Checks that each page works, that its values parse into typed fields with the selectors we tell
people to use, and that the demo controls change the same URL a flow watches.
"""

import pytest
from fastapi.testclient import TestClient

from app.engine.extract import extract_list
from app.flow.schema import ExtractListConfig
from app.main import create_app
from app.mockshop.demo_sites import demo_state

BASE = "https://example.com/demo/"


@pytest.fixture
def client(tmp_path):
    demo_state.reset()
    with TestClient(create_app(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'demo.db').as_posix()}"),
                    raise_server_exceptions=False) as c:
        yield c
    demo_state.reset()


def items(html: str, config: dict):
    return extract_list(html, BASE, ExtractListConfig.model_validate(config))


PROPERTY = {"base_selector": "div.listing", "identity_key": "url", "fields": [
    {"name": "title", "selector": "h2.title", "type": "text", "required": True},
    {"name": "price", "selector": ".price", "type": "price", "required": True},
    {"name": "city", "selector": ".city", "type": "text"},
    {"name": "url", "selector": "a.details", "attr": "href", "type": "url", "required": True}]}
SCHOLARSHIP = {"base_selector": "div.scholarship", "identity_key": "url", "fields": [
    {"name": "name", "selector": "h3.name", "type": "text", "required": True},
    {"name": "amount", "selector": ".amount", "type": "price", "required": True},
    {"name": "deadline", "selector": ".deadline", "type": "date"},
    {"name": "url", "selector": "a.apply", "attr": "href", "type": "url", "required": True}]}
JOB = {"base_selector": "div.job", "identity_key": "url", "fields": [
    {"name": "title", "selector": "h2.title", "type": "text", "required": True},
    {"name": "city", "selector": ".city", "type": "text"},
    {"name": "salary", "selector": ".salary", "type": "price"},
    {"name": "url", "selector": "a.details", "attr": "href", "type": "url", "required": True}]}


@pytest.mark.req("FR-36")
def test_index_and_pages_exist(client):
    for path in ["/demo", "/demo/property", "/demo/property?page=2", "/demo/scholarships", "/demo/jobs",
                 "/demo/admin", "/demo/property/dha-house-10-marla", "/demo/jobs/qa-engineer"]:
        assert client.get(path).status_code == 200, path
    for path in ["/demo/nope", "/demo/property?page=9", "/demo/property/nope"]:
        assert client.get(path).status_code == 404, path


@pytest.mark.req("FR-21")
def test_property_listings_parse_and_a_price_drop_shows(client):
    first = items(client.get("/demo/property").text, PROPERTY)
    assert len(first) == 6 and first[0].data["price"] == "25000000.00" and first[0].data["city"] == "Lahore"
    assert first[0].key == "https://example.com/demo/property/dha-house-10-marla"
    client.post("/demo/admin/property-drop", data={"slug": "dha-house-10-marla"})
    after = items(client.get("/demo/property").text, PROPERTY)
    assert after[0].data["price"] == "22500000.00"


@pytest.mark.req("FR-21")
def test_scholarships_parse_and_a_new_one_appears(client):
    before = items(client.get("/demo/scholarships").text, SCHOLARSHIP)
    assert before[0].data["deadline"] == "2026-12-15" and before[0].data["amount"] == "150000.00"
    client.post("/demo/admin/scholarship-add")
    after = items(client.get("/demo/scholarships").text, SCHOLARSHIP)
    assert len(after) == len(before) + 1 and after[0].data["name"] == "AI Innovators Scholarship"


@pytest.mark.req("FR-21")
def test_jobs_parse_and_a_new_islamabad_job_appears(client):
    client.post("/demo/admin/job-add")
    jobs = items(client.get("/demo/jobs").text, JOB)
    assert jobs[0].data["title"] == "Machine Learning Engineer" and jobs[0].data["city"] == "Islamabad"
    assert jobs[0].data["salary"] == "260000.00"


@pytest.mark.req("FR-36")
def test_reset_puts_everything_back(client):
    client.post("/demo/admin/property-drop", data={"slug": "dha-house-10-marla"})
    client.post("/demo/admin/scholarship-add")
    client.post("/demo/admin/job-add")
    client.post("/demo/admin/reset")
    assert items(client.get("/demo/property").text, PROPERTY)[0].data["price"] == "25000000.00"
    assert len(items(client.get("/demo/scholarships").text, SCHOLARSHIP)) == 5
    assert len(items(client.get("/demo/jobs").text, JOB)) == 6
