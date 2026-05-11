"""RouterChain: primary → fallback 1 → KeywordRouter terminal fallback."""
from __future__ import annotations

import logging
import time
from typing import Any

from app.ai.contracts import RouterResponse
from app.ai.providers.base import LLMRouter
from app.ai.providers.keyword import KeywordRouter

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS_PER_QUESTION = 2


class RouterChain:
    """Try each router in order until one succeeds. KeywordRouter never fails."""

    def __init__(
        self,
        primary: LLMRouter | None,
        fallback: LLMRouter | None = None,
        fallback2: LLMRouter | None = None,
    ) -> None:
        self._chain: list[LLMRouter] = []
        for r in (primary, fallback, fallback2):
            if r is None:
                continue
            # de-dupe by provider name to avoid running the same router twice
            if any(getattr(x, "name", None) == r.name for x in self._chain):
                continue
            self._chain.append(r)
        # Terminal fallback — always present
        kw = KeywordRouter()
        if not any(getattr(r, "name", None) == kw.name for r in self._chain):
            self._chain.append(kw)

    async def route(
        self, question: str, schema_hint: dict | None = None
    ) -> tuple[RouterResponse, str, dict[str, Any]]:
        last_error: Exception | None = None
        attempts: list[dict[str, Any]] = []
        for router in self._chain:
            t0 = time.perf_counter()
            try:
                resp = await router.route(question, schema_hint=schema_hint)
                dur_ms = int((time.perf_counter() - t0) * 1000)
                attempts.append({"provider": router.name, "ok": True, "ms": dur_ms})
                return resp, router.name, {"attempts": attempts}
            except Exception as e:
                dur_ms = int((time.perf_counter() - t0) * 1000)
                attempts.append({"provider": router.name, "ok": False, "ms": dur_ms, "err": str(e)[:200]})
                logger.warning("Router %s failed: %s", router.name, e)
                last_error = e
                continue
        # Should be unreachable since KeywordRouter never raises, but for safety:
        raise RuntimeError(f"All routers failed: {last_error}")
