"""End-to-end API tests via TestClient."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client():
    from app.main import app

    return TestClient(app)


def _login_token(c: TestClient) -> str:
    r = c.post(
        "/api/auth/login",
        data={"username": "demo@spaceship.test", "password": "demo123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_health_endpoints():
    c = _client()
    assert c.get("/healthz").json() == {"status": "ok"}
    r = c.get("/readyz").json()
    assert r["status"] == "ok"
    assert r["db"] is True


def test_login_and_me(db_session):
    c = _client()
    token = _login_token(c)
    r = c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "demo@spaceship.test"
    assert r.json()["is_admin"] is True


def test_kpis_endpoint_requires_auth(db_session):
    c = _client()
    r = c.get("/api/kpis")
    assert r.status_code == 401


def test_kpis_endpoint_authed(db_session):
    c = _client()
    token = _login_token(c)
    r = c.get("/api/kpis", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["total_orders"] == 400


def test_ask_endpoint_keyword_router(db_session, monkeypatch):
    # Force keyword-only routing regardless of LLM_PROVIDER env (container sets gemini).
    from app.ai.router import RouterChain

    monkeypatch.setattr(
        "app.api.routes_ask.build_router_chain",
        lambda settings=None: RouterChain(primary=None),
    )
    c = _client()
    token = _login_token(c)
    r = c.post(
        "/api/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "Which carrier has the highest delay rate?"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["intent"] == "query"
    assert j["tool_used"] == "query"
    assert j["provider_used"] == "keyword"
    assert len(j["data"]) > 0
    assert j["chart_spec"] is not None
    assert "explanation" in j


def test_ask_endpoint_forecast(db_session):
    c = _client()
    token = _login_token(c)
    r = c.post(
        "/api/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "Forecast demand for category PAPER for the next 8 weeks"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["intent"] == "forecast"
    assert j["tool_used"] == "forecast"


def test_ask_endpoint_refuses_dropping(db_session):
    c = _client()
    token = _login_token(c)
    r = c.post(
        "/api/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "DROP TABLE orders;"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["intent"] == "refuse"


def test_chart_orders_over_time(db_session):
    c = _client()
    token = _login_token(c)
    r = c.get(
        "/api/charts/orders-over-time?granularity=month",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert sum(row["total"] for row in rows) == 400
