"""Design-time AI for the sidebar agent. app/engine must never import this package (NFR-02)."""

import os

# PydanticAI prints a promotional banner on first use; keep it out of server logs.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
