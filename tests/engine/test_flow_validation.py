"""Flow schema (FR-03, FR-23, FR-24, FR-34) and graph rules (FR-04, FR-22, FR-27).

Edge cases EC-16 – EC-21, EC-24 and EC-56 in docs/testing.md.
"""

import pytest

from app.flow.cases import INVALID_CASES, build_case, load_example
from app.flow.schema import Variable, looks_like_pii
from app.flow.validate import parse_flow, validate_flow


@pytest.mark.req("FR-03")
@pytest.mark.parametrize("name", ["list_tracking", "multi_link"])
def test_example_flows_are_valid(name):
    flow = load_example(name)
    assert validate_flow(flow) == []
    assert validate_flow(flow, for_publish=True) == []


@pytest.mark.req("FR-04")
@pytest.mark.parametrize("name", sorted(INVALID_CASES))
def test_invalid_flow_is_rejected_with_a_clear_message(name):
    flow, expected, for_publish = build_case(name)
    issues = validate_flow(flow, for_publish=for_publish)
    assert issues, f"{name} should be rejected"
    messages = " | ".join(i["message"] for i in issues)
    assert expected in messages
    for issue in issues:
        assert set(issue) == {"node_id", "path", "message"}  # contract C2 shape


@pytest.mark.req("FR-03")
def test_schema_issue_points_at_the_node_and_field():
    flow, _, _ = build_case("bad_selector")
    issues = validate_flow(flow)
    assert issues == [{"node_id": "e1", "path": "config.base_selector", "message": "Selector does not parse"}]


@pytest.mark.req("FR-27")
def test_browser_node_allowed_in_draft_but_not_at_publish():
    flow, _, _ = build_case("browser_node_at_publish")
    assert validate_flow(flow) == []
    assert any("needs a browser" in i["message"] for i in validate_flow(flow, for_publish=True))


@pytest.mark.req("FR-03")
@pytest.mark.parametrize("garbage", [None, 42, "flow", [], {"nodes": "x"}, {"nodes": [{"id": "!"}]}])
def test_garbage_input_returns_issues_not_exceptions(garbage):
    issues = validate_flow(garbage)
    assert issues and all("message" in i for i in issues)


@pytest.mark.req("FR-23")
def test_url_list_is_deduplicated_and_trimmed():
    v = Variable(name="links", type="url_list",
                 value=[" https://a.example/x ", "https://a.example/x", "https://b.example/y"])
    assert v.value == ["https://a.example/x", "https://b.example/y"]


@pytest.mark.req("FR-23")
@pytest.mark.parametrize("vtype,value", [
    ("url_list", []),
    ("url_list", ["ftp://a.example/x"]),
    ("url_list", [f"https://a.example/{i}" for i in range(26)]),
    ("price", 0),
    ("price", "abc"),
    ("number", True),
    ("boolean", "yes"),
    ("text", "x" * 201),
])
def test_bad_variable_values_are_rejected(vtype, value):
    with pytest.raises(ValueError):
        Variable(name="v", type=vtype, value=value)


STARTER = {"version": 0, "nodes": [
    {"id": "t1", "type": "trigger", "config": {}},
    {"id": "k1", "type": "check_page", "config": {}},
], "edges": []}


@pytest.mark.req("FR-03")
def test_half_built_flow_saves_as_draft_but_cannot_run():
    assert validate_flow(STARTER, draft=True) == []
    assert any("must lead to exactly one next step" in i["message"] for i in validate_flow(STARTER))


@pytest.mark.req("FR-03")
@pytest.mark.parametrize("name", [
    "unknown_key", "bad_selector", "code_in_title", "file_url", "pii_field", "cycle",
    "edge_crosses_loop_wall", "nested_loop", "save_inside_loop", "missing_variable",
    "wrong_variable_type", "two_triggers", "condition_without_handle",
])
def test_draft_mode_still_refuses_unsafe_or_broken_structure(name):
    flow, expected, _ = build_case(name)
    messages = " | ".join(i["message"] for i in validate_flow(flow, draft=True))
    assert expected in messages


@pytest.mark.req("FR-03")
@pytest.mark.parametrize("name", ["orphan_node", "bad_spine", "history_op_without_save",
                                  "track_unknown_field", "browser_node_at_publish"])
def test_draft_mode_allows_incomplete_wiring(name):
    flow, _, _ = build_case(name)
    assert validate_flow(flow, draft=True) == []


@pytest.mark.req("FR-24")
def test_field_from_a_loop_is_usable_after_done():
    # Same shape as the field_not_upstream case, but the condition sits AFTER the loop: valid.
    flow, _, _ = build_case("field_not_upstream")
    flow["nodes"] = [n for n in flow["nodes"] if n["id"] != "r1"]
    flow["edges"] = [e for e in flow["edges"] if e["id"] not in ("e_l2_r1", "e_s1_c2")]
    flow["edges"].append({"id": "e_l2_c2", "source": "l2", "sourceHandle": "done", "target": "c2"})
    assert validate_flow(flow) == []


@pytest.mark.req("FR-21")
def test_identity_field_is_normalised_to_required():
    flow = load_example("list_tracking")
    next(f for f in flow["nodes"][3]["config"]["fields"] if f["name"] == "url")["required"] = False
    normalised, issues = parse_flow(flow)
    assert issues == []
    url_field = next(f for f in normalised["nodes"][3]["config"]["fields"] if f["name"] == "url")
    assert url_field["required"] is True


@pytest.mark.req("FR-23")
def test_parse_flow_returns_what_was_validated():
    flow = load_example("multi_link")
    flow["variables"][0]["value"] = [" https://a.example/x ", "https://a.example/x"]
    normalised, issues = parse_flow(flow)
    assert issues == []
    assert normalised["variables"][0]["value"] == ["https://a.example/x"]
    assert validate_flow(normalised) == []  # normalising is stable


@pytest.mark.req("FR-34")
@pytest.mark.parametrize("name,is_pii", [
    ("seller_phone", True), ("email", True), ("e_mail", True), ("cnic", True), ("home_address", True),
    ("date_of_birth", True), ("phone_number", True),
    ("iphone_price", False), ("automobile_price", False), ("adobe_price", False), ("telescope", False),
    ("title", False), ("price", False),
])
def test_personal_data_names_match_whole_words(name, is_pii):
    assert looks_like_pii(name) is is_pii


@pytest.mark.req("FR-03")
def test_exported_contract_files_are_up_to_date():
    """contracts/ is what Kaleem builds against. Regenerate: uv run python scripts/export_schema.py"""
    import json

    from app.flow.cases import EXAMPLES_DIR
    from app.flow.schema import Flow

    schema = json.loads((EXAMPLES_DIR.parent / "flow.schema.json").read_text(encoding="utf-8"))
    expected = Flow.model_json_schema()
    expected["title"] = "Flow"
    assert schema == expected, "flow.schema.json is stale"
    for name in INVALID_CASES:
        exported = json.loads((EXAMPLES_DIR / f"invalid_{name}.json").read_text(encoding="utf-8"))
        flow, message, for_publish = build_case(name)
        assert exported["flow"] == flow, f"invalid_{name}.json is stale"
        assert exported["_issues"] == validate_flow(flow, for_publish=for_publish)
    on_disk = {p.stem.removeprefix("invalid_") for p in EXAMPLES_DIR.glob("invalid_*.json")}
    assert on_disk == set(INVALID_CASES), "remove invalid_*.json files whose case no longer exists"


@pytest.mark.req("FR-22")
def test_loop_back_edge_is_not_a_cycle():
    # b2 -> l1 ("next") closes the loop; it must not be reported as a cycle.
    flow = load_example("multi_link")
    assert not any("cycle" in i["message"] for i in validate_flow(flow))
