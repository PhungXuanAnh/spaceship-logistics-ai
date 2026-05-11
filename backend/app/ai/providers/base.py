"""LLMRouter Protocol + helpers."""
from __future__ import annotations

from typing import Protocol

from app.ai.contracts import RouterResponse


class LLMRouter(Protocol):
    name: str

    async def route(self, question: str, schema_hint: dict | None = None) -> RouterResponse:
        """Map a natural-language question to a typed RouterResponse."""
        ...
