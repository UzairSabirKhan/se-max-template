"""Model setup for the sidebar agent: primary model, fallback model, timeouts and per-message deps.

Used only while a user builds a flow (design time). Published runs never call AI, and app/engine
never imports app/ai.

Configuration (names in .env.example, values never committed):
    AI_MODEL           "<provider>:<model>", e.g. "google:<gemini-model>" (tried first)
    AI_FALLBACK_MODEL  one or more "<provider>:<model>", comma-separated, tried in order when the one
                       before fails, e.g. "groq:<llama-model>,anthropic:<claude-model>"
    GEMINI_API_KEY or GOOGLE_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY

Providers: google (Gemini), groq, anthropic (Claude). Any model whose key is missing is skipped, so
setting only the keys you have is enough.
"""

from __future__ import annotations

import copy
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import UsageLimits
from pydantic_ai.exceptions import UserError
from pydantic_ai.models import Model, infer_model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.groq import GroqProvider
from pydantic_ai.settings import ModelSettings

log = logging.getLogger(__name__)

#: At most this many tool calls per user message (FR-07). Enforced by UsageLimits; also counted in AgentDeps.
MAX_TOOL_CALLS = 8

#: Per-request limits. SDK retries are kept low because FallbackModel moves on to the next model instead.
MODEL_SETTINGS = ModelSettings(
    request_timeout=45.0,  # one request to one model, every attempt included
    first_event_timeout=20.0,  # a streamed reply must start within this
    max_retries=1,
)

# "google-gla" is the old PydanticAI prefix (still written in specs/.env.example); "google" is current.
_GOOGLE_PREFIXES = {"google", "google-gla"}


class AIUnavailable(Exception):
    """No model can be used (not configured, or no API key). Maps to C5 error code `ai_unavailable`."""


@dataclass(frozen=True)
class AIConfig:
    model: str = ""
    fallback_model: str = ""
    google_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""

    @property
    def specs(self) -> list[str]:
        """AI_MODEL, then each AI_FALLBACK_MODEL entry, in the order they are tried."""
        fallbacks = [s.strip() for s in self.fallback_model.split(",")]
        return [s for s in (self.model.strip(), *fallbacks) if s]

    @classmethod
    def from_env(cls) -> AIConfig:
        env = os.environ.get
        return cls(
            model=env("AI_MODEL", "").strip(),
            fallback_model=env("AI_FALLBACK_MODEL", "").strip(),
            google_api_key=(env("GOOGLE_API_KEY") or env("GEMINI_API_KEY") or "").strip(),
            anthropic_api_key=env("ANTHROPIC_API_KEY", "").strip(),
            groq_api_key=env("GROQ_API_KEY", "").strip(),
        )


def _build_one(spec: str, config: AIConfig) -> Model:
    """Turn "<provider>:<model>" into a Model. Raises AIUnavailable with a reason the logs can show."""
    provider, sep, name = spec.partition(":")
    if not sep or not name:
        raise AIUnavailable(f"{spec!r} is not in the form '<provider>:<model>'")
    if provider == "test":
        return TestModel()
    if provider in _GOOGLE_PREFIXES:
        if not config.google_api_key:
            raise AIUnavailable(f"{spec}: GEMINI_API_KEY (or GOOGLE_API_KEY) is not set")
        return GoogleModel(name, provider=GoogleProvider(api_key=config.google_api_key))
    if provider == "anthropic":
        if not config.anthropic_api_key:
            raise AIUnavailable(f"{spec}: ANTHROPIC_API_KEY is not set")
        return AnthropicModel(name, provider=AnthropicProvider(api_key=config.anthropic_api_key))
    if provider == "groq":
        if not config.groq_api_key:
            raise AIUnavailable(f"{spec}: GROQ_API_KEY is not set")
        return GroqModel(name, provider=GroqProvider(api_key=config.groq_api_key))
    try:  # any other provider PydanticAI knows, using its own environment variables
        return infer_model(spec)
    except (UserError, ImportError, ValueError) as exc:
        # ImportError: a provider whose package isn't installed (e.g. "openai:...") must mean
        # "assistant offline", never a crash, and must not stop the next model from being tried.
        raise AIUnavailable(f"{spec}: {exc}") from exc


def get_model(config: AIConfig | None = None) -> Model:
    """The model the agent uses: AI_MODEL, then each AI_FALLBACK_MODEL entry in turn when one fails.

    A model that can't be built (missing key, bad name) is skipped with a log line. If neither can be
    built, raises AIUnavailable: the sidebar shows "assistant offline" and published flows keep running.
    """
    config = config or AIConfig.from_env()
    built: list[Model] = []
    reasons: list[str] = []
    for spec in config.specs:
        try:
            built.append(_build_one(spec, config))
        except AIUnavailable as exc:
            reasons.append(str(exc))
            log.warning("AI model skipped: %s", exc)
    if not built:
        raise AIUnavailable("; ".join(reasons) or "AI_MODEL and AI_FALLBACK_MODEL are not set")
    return built[0] if len(built) == 1 else FallbackModel(built[0], *built[1:])


def usage_limits() -> UsageLimits:
    """Caps for one user message: 8 tool calls, and enough model requests to use them and then reply."""
    return UsageLimits(tool_calls_limit=MAX_TOOL_CALLS, request_limit=MAX_TOOL_CALLS + 3)


EmitFn = Callable[[str, dict[str, Any]], Awaitable[None]]


async def _no_emit(event: str, data: dict[str, Any]) -> None:
    return None


@dataclass
class AgentDeps:
    """State for one agent message. Tools read and edit `draft`, a private copy of the user's draft.

    Nothing here is saved: proposed edits collect in `ops` and go to the browser as C5 `flow_ops`,
    where the user accepts or rejects them.
    """

    flow_id: str
    draft: dict[str, Any]
    selected_node_ids: list[str] = field(default_factory=list)
    emit: EmitFn = _no_emit
    tool_calls: int = 0
    ops: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def for_message(
        cls,
        flow_id: str,
        draft: dict[str, Any],
        selected_node_ids: list[str] | None = None,
        emit: EmitFn | None = None,
    ) -> AgentDeps:
        """Build deps around a deep copy, so tool edits never touch the caller's draft."""
        return cls(
            flow_id=flow_id,
            draft=copy.deepcopy(draft),
            selected_node_ids=list(selected_node_ids or []),
            emit=emit or _no_emit,
        )

    def count_tool_call(self) -> int:
        """Record one tool call; returns how many are left in this message's budget."""
        self.tool_calls += 1
        return max(0, MAX_TOOL_CALLS - self.tool_calls)
