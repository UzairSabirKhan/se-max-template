"""B3: model setup. No test here makes a network call (ALLOW_MODEL_REQUESTS is False)."""

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.models.test import TestModel

from app.ai.models import (
    MAX_MODEL_REQUESTS,
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


@pytest.mark.req("FR-06")
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


@pytest.mark.req("FR-09")
def test_old_google_gla_prefix_still_works():
    assert isinstance(get_model(AIConfig(model="google-gla:gemini-x", google_api_key="k1")), GoogleModel)


@pytest.mark.req("FR-09")
def test_a_model_without_its_key_is_skipped_and_the_other_used():
    cfg = AIConfig(model="google:gemini-x", fallback_model="anthropic:claude-x", anthropic_api_key="k2")
    assert isinstance(get_model(cfg), AnthropicModel)


@pytest.mark.req("FR-10")
def test_bad_spec_is_reported():
    with pytest.raises(AIUnavailable, match="provider"):
        get_model(AIConfig(model="no-colon-here"))


@pytest.mark.req("FR-09")
def test_config_reads_environment(monkeypatch):
    monkeypatch.setenv("AI_MODEL", "google:gemini-x")
    monkeypatch.setenv("AI_FALLBACK_MODEL", "anthropic:claude-x")
    monkeypatch.setenv("GEMINI_API_KEY", "k1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k2")
    assert isinstance(get_model(), FallbackModel)


@pytest.mark.req("FR-07")
async def test_many_tool_calls_in_one_message_are_allowed():
    agent = Agent(deps_type=AgentDeps, output_type=str)
    for i in range(30):
        agent.tool_plain(name=f"tool_{i}")(lambda: "ok")
    result = await agent.run("go", deps=AgentDeps.for_message("fl_1", DRAFT), model=TestModel(),
                             usage_limits=usage_limits())
    assert result.output


@pytest.mark.req("FR-07")
async def test_an_endless_loop_is_still_stopped():
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    agent = Agent(deps_type=AgentDeps, output_type=str)
    agent.tool_plain(name="again")(lambda: "ok")
    loop = FunctionModel(lambda messages, info: ModelResponse(parts=[ToolCallPart("again", {})]))
    with pytest.raises(UsageLimitExceeded):
        await agent.run("go", deps=AgentDeps.for_message("fl_1", DRAFT), model=loop, usage_limits=usage_limits())
    assert usage_limits().request_limit == MAX_MODEL_REQUESTS


@pytest.mark.req("FR-10")
async def test_real_model_requests_are_blocked_in_tests():
    cfg = AIConfig(model="anthropic:claude-x", anthropic_api_key="k2")
    with pytest.raises(RuntimeError, match="ALLOW_MODEL_REQUESTS"):
        await Agent(get_model(cfg)).run("hi")


@pytest.mark.req("FR-09")
def test_groq_is_supported_with_its_own_key():
    assert isinstance(get_model(AIConfig(model="groq:llama-x", groq_api_key="k3")), GroqModel)
    with pytest.raises(AIUnavailable, match="GROQ_API_KEY"):
        get_model(AIConfig(model="groq:llama-x"))


@pytest.mark.req("FR-09")
def test_fallback_chain_tries_each_model_in_order():
    cfg = AIConfig(model="google:gemini-x", fallback_model="groq:llama-x, anthropic:claude-x",
                   google_api_key="k1", groq_api_key="k3", anthropic_api_key="k2")
    model = get_model(cfg)
    assert [type(m) for m in model.models] == [GoogleModel, GroqModel, AnthropicModel]


@pytest.mark.req("FR-09")
def test_only_the_models_with_keys_are_used():
    cfg = AIConfig(model="google:gemini-x", fallback_model="groq:llama-x,anthropic:claude-x", groq_api_key="k3")
    assert isinstance(get_model(cfg), GroqModel)


@pytest.mark.req("FR-10")
@pytest.mark.parametrize("spec", ["openai:gpt-x", "groq-typo:llama-x", "nonsense:model"])
def test_uninstalled_or_unknown_provider_is_offline_not_a_crash(spec):
    with pytest.raises(AIUnavailable):
        get_model(AIConfig(model=spec))


@pytest.mark.req("FR-10")
def test_a_broken_first_model_does_not_stop_the_fallback():
    cfg = AIConfig(model="openai:gpt-x", fallback_model="groq:llama-x", groq_api_key="k3")
    assert isinstance(get_model(cfg), GroqModel)


@pytest.mark.req("FR-09")
def test_groq_key_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("AI_MODEL", "groq:llama-x")
    monkeypatch.setenv("GROQ_API_KEY", "k3")
    assert isinstance(get_model(), GroqModel)


@pytest.mark.req("FR-09")
def test_a_second_key_is_tried_before_the_next_model():
    cfg = AIConfig(model="google:gemini-x", fallback_model="groq:llama-x",
                   google_api_key="k1", google_api_key_2="k1b", groq_api_key="k3")
    model = get_model(cfg)
    assert [type(m) for m in model.models] == [GoogleModel, GoogleModel, GroqModel]
    assert [m._provider.client._api_client.api_key for m in model.models[:2]] == ["k1", "k1b"]


@pytest.mark.req("FR-09")
def test_second_keys_are_read_from_the_environment(monkeypatch):
    for name in ("GOOGLE_API_KEY", "GOOGLE_API_KEY_2", "AI_FALLBACK_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AI_MODEL", "google:gemini-x")
    monkeypatch.setenv("GEMINI_API_KEY", "k1")
    monkeypatch.setenv("GEMINI_API_KEY_2", "k1b")
    model = get_model()
    assert isinstance(model, FallbackModel) and len(model.models) == 2


@pytest.mark.req("FR-09")
def test_a_second_key_equal_to_the_first_is_ignored():
    cfg = AIConfig(model="groq:llama-x", groq_api_key="k3", groq_api_key_2="k3")
    assert isinstance(get_model(cfg), GroqModel)


@pytest.mark.req("FR-09")
async def test_a_key_out_of_quota_hands_over_to_the_next_key():
    from pydantic_ai.exceptions import ModelHTTPError
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    def out_of_quota(messages, info: AgentInfo):
        raise ModelHTTPError(status_code=429, model_name="gemini-x", body={"error": "RESOURCE_EXHAUSTED"})

    async def out_of_quota_stream(messages, info: AgentInfo):
        raise ModelHTTPError(status_code=429, model_name="gemini-x", body={"error": "RESOURCE_EXHAUSTED"})
        yield ""  # pragma: no cover

    model = FallbackModel(FunctionModel(out_of_quota, stream_function=out_of_quota_stream), TestModel())
    deps = AgentDeps.for_message("fl_1", DRAFT)
    result = await _hello_agent().run("hi", deps=deps, model=model, usage_limits=usage_limits())
    assert result.output
    async with _hello_agent().run_stream("hi", deps=AgentDeps.for_message("fl_1", DRAFT), model=model,
                                         usage_limits=usage_limits()) as stream:
        assert await stream.get_output()
