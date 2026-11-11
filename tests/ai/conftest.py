"""Agent tests never call a real model: any accidental real request fails the test (B3, B15)."""

import pytest
from pydantic_ai import models

models.ALLOW_MODEL_REQUESTS = False

AI_ENV = ("AI_MODEL", "AI_FALLBACK_MODEL", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY")


@pytest.fixture(autouse=True)
def _no_ai_env(monkeypatch):
    """Start every test with no AI configuration, whatever the developer's shell has set."""
    for name in AI_ENV:
        monkeypatch.delenv(name, raising=False)
