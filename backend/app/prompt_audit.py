"""Append-only JSONL log of every /ask prompt for review/debugging.

Writes one JSON object per line to PROMPT_LOG_PATH (default /data/prompts.log,
which is on the persistent docker volume on EC2). Rotates at 5 MB, keeps 5
backups. Failures here never affect the request.

Tail with:  ssh ec2 -- 'docker compose exec backend tail -f /data/prompts.log'
or:         ssh ec2 -- 'sudo tail -f /var/spaceship/data/prompts.log'
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

_LOG_PATH = os.environ.get("PROMPT_LOG_PATH", "/data/prompts.log")
_logger = logging.getLogger("prompt_audit")
_logger.setLevel(logging.INFO)
_logger.propagate = False

_initialized = False


def _ensure_handler() -> None:
    global _initialized
    if _initialized:
        return
    try:
        os.makedirs(os.path.dirname(_LOG_PATH) or ".", exist_ok=True)
        handler = RotatingFileHandler(
            _LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(handler)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("prompt_audit disabled: %s", exc)
    _initialized = True


def log_prompt(
    *,
    request_id: str,
    engine: str,
    user_email: str | None,
    client_ip: str | None,
    user_agent: str | None,
    question: str,
    intent: str,
    tool: str | None,
    provider: str | None,
    duration_ms: int | None,
    row_count: int | None,
    out_of_scope: bool,
    answer: str | None = None,
    data: object | None = None,
    plan: object | None = None,
) -> None:
    _ensure_handler()
    if not _logger.handlers:
        return
    # Truncate data preview so the log stays tail-friendly.
    data_preview = data
    if isinstance(data, list):
        data_preview = data[:10]
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "engine": engine,
        "user": user_email,
        "ip": client_ip,
        "ua": user_agent,
        "question": question[:2000],
        "intent": intent,
        "tool": tool,
        "provider": provider,
        "duration_ms": duration_ms,
        "row_count": row_count,
        "out_of_scope": out_of_scope,
        "answer": (answer or "")[:1000] or None,
        "plan": plan,
        "data": data_preview,
    }
    try:
        _logger.info(json.dumps(record, ensure_ascii=False, default=str))
    except Exception:  # noqa: BLE001
        pass
