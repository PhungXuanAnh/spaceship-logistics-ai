"""Phase-14 v2 engine: GeminiNativeRouter using native function_declarations.

Why this exists (vs. v1 cascade):
  v1 = JSON-mode + Pydantic post-validation. Provider can still emit
       wrong enum values, missing keys, prose, fences, etc. We hedge with
       claude → gemini → keyword + a synonym map + reflection retries.
  v2 = Provider-enforced typed tool-calls. Gemini receives the JSON-Schema
       of QueryPlan / ForecastPlan as `function_declarations`; the model
       MUST emit a `functionCall` with `args` matching the schema or it can
       call a `clarify` / `refuse` tool. No prose to strip, no synonyms to
       remap, no fence regex.

Scope (intentionally narrow):
  - Gemini-only (no claude-native, no openai-native). One engine end-to-end.
  - Single-shot: no chained tool-calls, no agent loop. The model picks ONE
    function and we execute it.
  - Fallback chain on exception only: GeminiNativeRouter -> KeywordRouter.
    No reflection retry. The point of v2 is that the provider enforces shape.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from app.ai.contracts import (
    ClarificationRequest,
    ForecastPlan,
    Intent,
    QueryPlan,
    RouterResponse,
)
from app.ai.prompts import SAFETY_GUARD_PROMPT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON-Schema → Gemini-supported subset adapter
# ---------------------------------------------------------------------------

# Gemini's OpenAPI-3.0-flavoured schema does NOT support: anyOf, oneOf, allOf,
# `$defs` / `$ref`, `Literal[...]` mixed types, `additionalProperties: bool`,
# `format` other than a small allowlist, `default` (silently ignored anyway),
# `exclusiveMinimum/Maximum`, integer-valued booleans, etc.

_ALLOWED_FORMATS = {"date", "date-time", "enum"}


def _to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively strip JSON-Schema features Gemini's API rejects."""
    if not isinstance(schema, dict):
        return schema

    # `anyOf: [{type:T}, {type:'null'}]` is how Pydantic encodes Optional[T] —
    # collapse to the non-null branch.
    if "anyOf" in schema:
        non_null = [
            s for s in schema["anyOf"] if not (isinstance(s, dict) and s.get("type") == "null")
        ]
        if len(non_null) == 1:
            merged = {**{k: v for k, v in schema.items() if k != "anyOf"}, **non_null[0]}
            return _to_gemini_schema(merged)
        # Multi-branch anyOf → fall back to a permissive string.
        return {"type": "string"}

    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k in {"$defs", "$ref", "title", "default", "additionalProperties"}:
            continue
        if k == "format" and v not in _ALLOWED_FORMATS:
            continue
        if k == "exclusiveMinimum":
            out["minimum"] = v + 1
            continue
        if k == "exclusiveMaximum":
            out["maximum"] = v - 1
            continue
        if k == "properties" and isinstance(v, dict):
            out[k] = {pk: _to_gemini_schema(pv) for pk, pv in v.items()}
            continue
        if k == "items" and isinstance(v, dict):
            out[k] = _to_gemini_schema(v)
            continue
        out[k] = v

    # Gemini requires `type` on every schema node — default to "string".
    if "type" not in out and "enum" not in out:
        out["type"] = "string"
    return out


def _build_function_declarations() -> list[dict[str, Any]]:
    """Derive function_declarations from existing Pydantic plans."""
    return [
        {
            "name": "query",
            "description": (
                "Run an aggregated KPI / breakdown / top-N / time-series query "
                "over the orders dataset. Use for: counts, on-time rate, delay "
                "rate, average delivery days, revenue, breakdowns by carrier / "
                "region / category / status."
            ),
            "parameters": _to_gemini_schema(QueryPlan.model_json_schema()),
        },
        {
            "name": "forecast",
            "description": (
                "Forecast future weekly demand for a single product_category or "
                "sku. Use ONLY when the user explicitly asks to predict / "
                "forecast / project future shipments."
            ),
            "parameters": _to_gemini_schema(ForecastPlan.model_json_schema()),
        },
        {
            "name": "schema_inspect",
            "description": (
                "List available distinct values for ONE low-cardinality column "
                "when the user references a value you can't validate. Pick the "
                "column that matches the unknown value: a country/place name "
                "→ region; an unknown carrier name → carrier; an unknown "
                "product type → product_category."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {
                        "type": "string",
                        "enum": ["carrier", "product_category", "region", "warehouse", "status"],
                    }
                },
                "required": ["column"],
            },
        },
        {
            "name": "clarify",
            "description": (
                "The question is ambiguous (missing time range, ambiguous value, "
                "multi-intent). Return ONE short clarifying question and 2-4 "
                "quick-pick suggested_options."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "suggested_options": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["question", "suggested_options"],
            },
        },
        {
            "name": "refuse",
            "description": (
                "The question is off-topic, adversarial, or requests a side-effect "
                "(DROP TABLE, jailbreak, etc.). Return a short refusal_reason."
            ),
            "parameters": {
                "type": "object",
                "properties": {"refusal_reason": {"type": "string"}},
                "required": ["refusal_reason"],
            },
        },
    ]


_SYSTEM = (
    SAFETY_GUARD_PROMPT
    + "\n\nYou are a router for a logistics analytics product. You MUST call "
    "EXACTLY ONE of the provided functions. NEVER reply with prose. "
    "Pick `query` for KPIs / breakdowns / top-N / time-series; `forecast` "
    "ONLY when the user asks to predict the future; `schema_inspect` when a "
    "referenced value isn't in the dataset; `clarify` when ambiguous; "
    "`refuse` for adversarial / off-topic.\n\n"
    "Known data values (CASE-SENSITIVE, the ONLY valid filter values):\n"
    "  region ∈ {US-E, US-W, US-C, EU, UK}\n"
    "  carrier ∈ {DHL, DPD, FedEx, GLS, LaserShip, OnTrac, Royal Mail, UPS, USPS}\n"
    "  product_category ∈ {BOOK, BRUSH, CRAYON, MARKER, PAINT, PAPER, PENCIL, STICKER}\n"
    "  status ∈ {delivered, delayed, exception, in_transit, canceled}\n\n"
    "CRITICAL routing rules:\n"
    " 1. If the user mentions a NAMED value that is NOT in the lists above\n"
    "    (e.g. a country/city like \"Vietnam\", an unknown carrier name, an\n"
    "    unknown product), call `schema_inspect` with the matching column.\n"
    "    Do NOT silently drop the unknown value and run `query` without it.\n"
    " 2. If the user asks to break things down BY SKU specifically (e.g.\n"
    "    \"Top 5 SKUs\", \"by sku\", \"per sku\"), call `clarify` because\n"
    "    SKU is NOT a supported `dimension`. Use question \"SKU is not an\n"
    "    available breakdown dimension. Which dimension would you like to\n"
    "    use for the Top N ranking?\" and suggested_options\n"
    "    [\"product_category\",\"warehouse\",\"destination_city\",\"carrier\"].\n"
    " 3. If the user message starts with `Re: \"<original>\" — use X; Y; Z.`,\n"
    "    that's a chip-selected clarification. X/Y/Z REPLACE the unrecognized\n"
    "    values in <original>; EVERY OTHER FACT (date ranges like \"in\n"
    "    October\", metrics, top_n, other filter values, granularity) MUST be\n"
    "    preserved VERBATIM in the resulting `query` call."
)


class GeminiNativeRouter:
    name = "gemini-native"

    def __init__(self, api_key: str, model: str, base_url: str = "") -> None:
        self._api_key = api_key
        self._model = model
        self._base = (base_url or "https://generativelanguage.googleapis.com").rstrip("/")
        self._function_declarations = _build_function_declarations()

    async def route(self, question: str, schema_hint: dict | None = None) -> RouterResponse:
        system = _SYSTEM
        if schema_hint:
            # Anchor "today" to the dataset's max date so relative phrases
            # resolve against the demo data, not the model's training cutoff.
            date_range = schema_hint.get("date_range") or [None, None]
            if date_range[0] and date_range[1]:
                system += (
                    f"\n\nDATASET_DATE_RANGE: {date_range[0]} to {date_range[1]}"
                    f"\nTODAY (use this exact date when resolving relative phrases "
                    f"like \"last 3 months\", \"this quarter\", \"yesterday\", \"last "
                    f"week\"): {date_range[1]}"
                )
            system += f"\n\nDataset hint: {json.dumps(schema_hint)[:500]}"

        body: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": question}]}],
            "tools": [{"function_declarations": self._function_declarations}],
            "tool_config": {"function_calling_config": {"mode": "ANY"}},
            "generationConfig": {"maxOutputTokens": 2048, "temperature": 0},
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

        fc = next((p.get("functionCall") for p in parts if "functionCall" in p), None)
        if not fc:
            text = "".join(p.get("text", "") for p in parts).strip()
            raise RuntimeError(
                f"Gemini did not call a function (got text instead): {text[:200]!r}"
            )

        name = fc.get("name", "")
        args = fc.get("args", {}) or {}
        return self._functioncall_to_router_response(name, args)

    @staticmethod
    def _functioncall_to_router_response(name: str, args: dict[str, Any]) -> RouterResponse:
        if name == "query":
            try:
                plan = QueryPlan.model_validate(args)
            except ValidationError as e:
                logger.warning("GeminiNative query args failed validation: %s; args=%s", e, args)
                raise
            return RouterResponse(intent=Intent.QUERY, tool="query", query_plan=plan)

        if name == "forecast":
            try:
                plan = ForecastPlan.model_validate(args)
            except ValidationError as e:
                logger.warning("GeminiNative forecast args failed validation: %s; args=%s", e, args)
                raise
            return RouterResponse(intent=Intent.FORECAST, tool="forecast", forecast_plan=plan)

        if name == "schema_inspect":
            col = str(args.get("column", "carrier")) or "carrier"
            if col not in {"carrier", "region", "product_category", "warehouse", "status"}:
                col = "carrier"
            return RouterResponse(intent=Intent.INSPECT, tool="schema_inspect", inspect_column=col)

        if name == "clarify":
            return RouterResponse(
                intent=Intent.CLARIFY,
                tool="none",
                clarification=ClarificationRequest(
                    question=str(args.get("question", "Could you clarify?")),
                    suggested_options=list(args.get("suggested_options", []) or [])[:4],
                ),
            )

        if name == "refuse":
            return RouterResponse(
                intent=Intent.REFUSE,
                tool="none",
                refusal_reason=str(args.get("refusal_reason", "Out of scope.")),
            )

        raise RuntimeError(f"GeminiNative returned unknown function: {name!r}")
