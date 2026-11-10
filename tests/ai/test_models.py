"""B3: model setup. No test here makes a network call (ALLOW_MODEL_REQUESTS is False)."""

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.test import TestModel

from app.ai.models import (
    MAX_TOOL_CALLS,
    MODEL_SETTINGS,
    AgentDeps,
    AIConfig,
    AIUnavailable,
    get_model,
    usage_limits,
)

pytestmark = pytest.mark.contract

DRAFT = {
    "version": 1,
    "variables": [],
    "nodes": [{"id": "n_trig01", "type": "trigger", "position": {"x": 0, "y": 0}, "config": {"mode": "manual"}}],
    "edges": [],
}


def _hello_agent() -> Agent[AgentDeps, str]:
    agent = Agent(deps_type=AgentDeps, output_type=str, instructions="Say hello.", model_settings=MODEL_SETTINGS)

    @agent.tool
    def count_nodes(ctx: RunContext[AgentDeps]) -> int:
        """How many steps the draft has."""
        ctx.deps.count_tool_call()
        return len(ctx.deps.draft["nodes"])

    return agent


@pytest.mark.req("FR-09")
async def test_hello_world_agent_answers_through_test_model():
    deps = AgentDeps.for_message("fl_1", DRAFT)
    result = await _hello_agent().run("hi", deps=deps, model=TestModel(), usage_limits=usage_limits())
    assert isinstance(result.output, str) and result.output
    assert deps.tool_calls == 1  # TestModel calls every tool once


def test_tools_edit_a_copy_never_the_callers_draft():
    deps = AgentDeps.for_message("fl_1", DRAFT, selected_node_ids=["n_trig01"])
    deps.draft["nodes"].append({"id": "n_x", "type": "wait"})
    assert len(DRAFT["nodes"]) == 1
    assert deps.selected_node_ids == ["n_trig01"]


@pytest.mark.req("FR-10")
def test_no_model_configured_means_ai_unavailable():
    with pytest.raises(AIUnavailable, match="not set"):
        get_model(AIConfig())


@pytest.mark.req("FR-10")
def test_missing_api_keys_mean_ai_unavailable_with_reasons():
    cfg = AIConfig(model="google:gemini-x", fallback_model="anthropic:claude-x")
    with pytest.raises(AIUnavailable) as exc:
        get_model(cfg)
    assert "GEMINI_API_KEY" in str(exc.value) and "ANTHROPIC_API_KEY" in str(exc.value)


@pytest.mark.req("FR-09")
def test_primary_then_fallback_builds_a_fallback_model():
    cfg = AIConfig(
        model="google:gemini-x", fallback_model="anthropic:claude-x", google_api_key="k1", anthropic_api_key="k2"
    )
    model = get_model(cfg)
    assert isinstance(model, FallbackModel)
    assert [type(m) for m in model.models] == [GoogleModel, AnthropicModel]


def test_old_google_gla_prefix_still_works():
    assert isinstance(get_model(AIConfig(model="google-gla:gemini-x", google_api_key="k1")), GoogleModel)


def test_a_model_without_its_key_is_skipped_and_the_other_used():
    cfg = AIConfig(model="google:gemini-x", fallback_model="anthropic:claude-x", anthropic_api_key="k2")
    assert isinstance(get_model(cfg), AnthropicModel)


def test_bad_spec_is_reported():
    with pytest.raises(AIUnavailable, match="provider"):
        get_model(AIConfig(model="no-colon-here"))


def test_config_reads_environment(monkeypatch):
    monkeypatch.setenv("AI_MODEL", "google:gemini-x")
    monkeypatch.setenv("AI_FALLBACK_MODEL", "anthropic:claude-x")
    monkeypatch.setenv("GEMINI_API_KEY", "k1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k2")
    assert isinstance(get_model(), FallbackModel)


@pytest.mark.req("FR-07")
async def test_usage_limits_stop_more_than_eight_tool_calls():
    agent = Agent(deps_type=AgentDeps, output_type=str)
    for i in range(MAX_TOOL_CALLS + 1):
        agent.tool_plain(name=f"tool_{i}")(lambda: "ok")

    with pytest.raises(UsageLimitExceeded):
        await agent.run("go", deps=AgentDeps.for_message("fl_1", DRAFT), model=TestModel(), usage_limits=usage_limits())


async def test_real_model_requests_are_blocked_in_tests():
    cfg = AIConfig(model="anthropic:claude-x", anthropic_api_key="k2")
    with pytest.raises(RuntimeError, match="ALLOW_MODEL_REQUESTS"):
        await Agent(get_model(cfg)).run("hi")
