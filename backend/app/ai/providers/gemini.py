"""Gemini provider via REST (no SDK dep, native async via httpx)."""
from __future__ import annotations

import json
import logging
import re

import httpx
from pydantic import ValidationError

from app.ai.contracts import RouterResponse
from app.ai.prompts import ROUTER_SYSTEM_PROMPT, SAFETY_GUARD_PROMPT
from app.ai.synonym_map import normalize_router_payload

logger = logging.getLogger(__name__)


class GeminiRouter:
    name = "gemini"

    def __init__(self, api_key: str, model: str, base_url: str = "") -> None:
        self._api_key = api_key
        self._model = model
        self._base = (base_url or "https://generativelanguage.googleapis.com").rstrip("/")

    async def _call(self, system: str, contents: list[dict]) -> str:
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": 2048,
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        url = f"{self._base}/v1beta/models/{self._model}:generateContent?key={self._api_key}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            payload = r.json()

        cands = payload.get("candidates", [])
        if not cands:
            raise RuntimeError("Gemini returned no candidates")
        parts = cands[0].get("content", {}).get("parts", []) or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            finish = cands[0].get("finishReason")
            raise RuntimeError(f"Gemini returned empty text (finishReason={finish})")
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        return text

    async def route(self, question: str, schema_hint: dict | None = None) -> RouterResponse:
        system = SAFETY_GUARD_PROMPT + "\n\n" + ROUTER_SYSTEM_PROMPT
        if schema_hint:
            system += f"\n\nDataset hint: {json.dumps(schema_hint)[:500]}"

        first_user_part = {
            "role": "user",
            "parts": [
                {
                    "text": (
                        f"User question: {question}\n\n"
                        "Reply with ONE valid JSON object matching the RouterResponse "
                        "schema. No prose, no markdown fences."
                    )
                }
            ],
        }
        raw = await self._call(system, [first_user_part])
        normalized = normalize_router_payload(raw)

        try:
            return RouterResponse.model_validate_json(normalized)
        except ValidationError as e:
            logger.info("GeminiRouter ValidationError, attempting 1 reflection retry: %s", str(e)[:200])
            retry_contents = [
                first_user_part,
                {"role": "model", "parts": [{"text": raw}]},
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "That JSON failed validation:\n"
                                f"{str(e)[:600]}\n\n"
                                "Return ONE corrected JSON object matching RouterResponse. "
                                "Use ONLY the literal enum values listed in the system prompt. "
                                "No prose, no markdown fences."
                            )
                        }
                    ],
                },
            ]
            retry_text = await self._call(system, retry_contents)
            retry_normalized = normalize_router_payload(retry_text)
            try:
                return RouterResponse.model_validate_json(retry_normalized)
            except Exception as e2:
                logger.warning("GeminiRouter reflection retry also failed: %s; raw=%s", e2, retry_text[:300])
                raise
