"""Anthropic-compatible provider (works with Anthropic API or local self-hosted LLM server).

Uses httpx (no anthropic SDK dep) so it can talk to either:
  - https://api.anthropic.com (real Anthropic key)
  - http://127.0.0.1:8080 (local self-hosted LLM server that speaks Anthropic Messages API)

Calls are wrapped in asyncio.to_thread NOT needed since we use httpx.AsyncClient.
"""
from __future__ import annotations

import json
import logging

import httpx
from pydantic import ValidationError

from app.ai.contracts import RouterResponse
from app.ai.prompts import ROUTER_SYSTEM_PROMPT, SAFETY_GUARD_PROMPT
from app.ai.synonym_map import normalize_router_payload

logger = logging.getLogger(__name__)


class ClaudeRouter:
    name = "claude"

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.anthropic.com") -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    async def _call(self, system: str, messages: list[dict]) -> str:
        body = {
            "model": self._model,
            "max_tokens": 2048,
            "system": system,
            "messages": messages,
        }
        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": self._api_key or "local",
            "authorization": f"Bearer {self._api_key}" if self._api_key else "Bearer local",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(f"{self._base_url}/v1/messages", json=body, headers=headers)
            r.raise_for_status()
            payload = r.json()

        text_parts = []
        for blk in payload.get("content", []):
            if blk.get("type") == "text":
                text_parts.append(blk.get("text", ""))
        raw_text = "".join(text_parts).strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()
        return raw_text

    async def route(self, question: str, schema_hint: dict | None = None) -> RouterResponse:
        system = SAFETY_GUARD_PROMPT + "\n\n" + ROUTER_SYSTEM_PROMPT
        if schema_hint:
            # Anchor "today" to the dataset's max date so the LLM resolves
            # relative phrases (e.g. "last 3 months") against the demo data
            # instead of its training-cutoff guess of now.
            date_range = schema_hint.get("date_range") or [None, None]
            if date_range[0] and date_range[1]:
                system += (
                    f"\n\nDATASET_DATE_RANGE: {date_range[0]} to {date_range[1]}"
                    f"\nTODAY (use this exact date when resolving relative phrases "
                    f"like \"last 3 months\", \"this quarter\", \"yesterday\", \"last "
                    f"week\"): {date_range[1]}"
                )
            system += f"\n\nDataset hint: {json.dumps(schema_hint)[:500]}"

        first_user_msg = {
            "role": "user",
            "content": (
                f"User question: {question}\n\n"
                "Reply with ONE valid JSON object matching the RouterResponse schema. "
                "No prose, no markdown fences."
            ),
        }
        raw_text = await self._call(system, [first_user_msg])
        normalized = normalize_router_payload(raw_text)

        try:
            return RouterResponse.model_validate_json(normalized)
        except ValidationError as e:
            logger.info("ClaudeRouter ValidationError, attempting 1 reflection retry: %s", str(e)[:200])
            # Reflection retry: send the prior text + the validation error and ask for a fix.
            retry_messages = [
                first_user_msg,
                {"role": "assistant", "content": raw_text},
                {
                    "role": "user",
                    "content": (
                        "That JSON failed validation:\n"
                        f"{str(e)[:600]}\n\n"
                        "Return ONE corrected JSON object matching RouterResponse. "
                        "Use ONLY the literal enum values listed in the system prompt. "
                        "No prose, no markdown fences."
                    ),
                },
            ]
            retry_text = await self._call(system, retry_messages)
            retry_normalized = normalize_router_payload(retry_text)
            try:
                return RouterResponse.model_validate_json(retry_normalized)
            except Exception as e2:
                logger.warning("ClaudeRouter reflection retry also failed: %s; raw=%s", e2, retry_text[:300])
                raise
