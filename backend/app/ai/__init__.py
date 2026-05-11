"""Build the RouterChain from settings."""
from __future__ import annotations

from app.ai.providers.base import LLMRouter
from app.ai.providers.keyword import KeywordRouter
from app.ai.router import RouterChain
from app.settings import Settings, get_settings


def _make_provider(provider: str, model: str, api_key: str, base_url: str) -> LLMRouter | None:
    p = provider.lower().strip()
    if p == "keyword" or not p:
        return None  # KeywordRouter is added by RouterChain itself
    if p == "claude":
        from app.ai.providers.claude import ClaudeRouter

        if not model:
            return None
        return ClaudeRouter(api_key=api_key, model=model, base_url=base_url or "https://api.anthropic.com")
    if p == "gemini":
        from app.ai.providers.gemini import GeminiRouter

        if not model or not api_key:
            return None
        return GeminiRouter(api_key=api_key, model=model, base_url=base_url)
    return None


def build_router_chain(settings: Settings | None = None) -> RouterChain:
    s = settings or get_settings()
    primary = _make_provider(s.llm_provider, s.llm_model, s.llm_api_key, s.llm_base_url)
    fallback = _make_provider(
        s.fallback_provider, s.fallback_model, s.fallback_api_key, s.fallback_base_url
    )
    fallback2 = _make_provider(
        s.fallback2_provider, s.fallback2_model, s.fallback2_api_key, s.fallback2_base_url
    )
    return RouterChain(primary=primary, fallback=fallback, fallback2=fallback2)


__all__ = ["build_router_chain", "RouterChain", "KeywordRouter"]
