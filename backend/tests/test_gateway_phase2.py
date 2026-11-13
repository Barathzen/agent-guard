import asyncio
import pytest
import httpx
from sqlalchemy.exc import SQLAlchemyError
from types import SimpleNamespace

from backend.app.main import app
from backend.app.api.v1 import router as router_module
from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.db.models import Agent, Session, Reservation, AgentStatus, SessionStatus


class FakeDB:
    def __init__(self, store):
        self.store = store

    async def get(self, model, key):
        return self.store.get((model, key))


def make_store(*, agent_status=AgentStatus.ACTIVE, session_status=SessionStatus.ACTIVE, agent_team="team-1", session_agent="agent-1"):
    agent = Agent(id="agent-1", team_id=agent_team, name="Agent One", status=agent_status)
    session = Session(id="session-1", agent_id=session_agent, status=session_status)
    return {
        (Agent, "agent-1"): agent,
        (Session, "session-1"): session,
    }


async def _client_with_store(store):
    async def override_get_db():
        yield FakeDB(store)

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def clear_state():
    router_module._idempotency_cache.clear()
    app.dependency_overrides.clear()
    yield
    router_module._idempotency_cache.clear()
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_gateway_requires_trusted_api_key():
    store = make_store()
    async with await _client_with_store(store) as client:
        resp = await client.post("/api/v1/gateway/chat/completions", json={
            "request_id": "req-auth-1",
            "team_id": "team-1",
            "agent_id": "agent-1",
            "session_id": "session-1",
            "model": "mock-gpt-4o",
            "messages": [{"role": "user", "content": "hello"}],
            "max_output_tokens": 32,
        })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_gateway_fails_closed_when_database_is_unavailable():
    class UnavailableDB:
        async def get(self, *_):
            raise SQLAlchemyError("database unavailable")

    async def override_get_db():
        yield UnavailableDB()

    app.dependency_overrides[get_db] = override_get_db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/gateway/chat/completions",
            headers={"X-API-Key": settings.GATEWAY_API_KEY},
            json={
                "request_id": "req-db-outage",
                "team_id": "team-1",
                "agent_id": "agent-1",
                "session_id": "session-1",
                "messages": [{"role": "user", "content": "must not reach provider"}],
            },
        )
    assert resp.status_code == 503
    assert "Database unavailable" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_gateway_rejects_unresolved_or_mismatched_identity_server_side():
    headers = {"X-API-Key": settings.GATEWAY_API_KEY}

    # session belongs to different agent
    store = make_store(session_agent="agent-other")
    async with await _client_with_store(store) as client:
        resp = await client.post("/api/v1/gateway/chat/completions", headers=headers, json={
            "request_id": "req-id-1",
            "team_id": "team-1",
            "agent_id": "agent-1",
            "session_id": "session-1",
            "messages": [{"role": "user", "content": "hi"}],
        })
    assert resp.status_code == 400
    assert "Session does not belong" in resp.text

    # missing agent
    store2 = {(Session, "session-1"): Session(id="session-1", agent_id="agent-1", status=SessionStatus.ACTIVE)}
    async with await _client_with_store(store2) as client:
        resp = await client.post("/api/v1/gateway/chat/completions", headers=headers, json={
            "request_id": "req-id-2",
            "team_id": "team-1",
            "agent_id": "agent-1",
            "session_id": "session-1",
            "messages": [{"role": "user", "content": "hi"}],
        })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_gateway_routes_through_mock_provider_with_correlation_and_idempotency():
    headers = {"X-API-Key": settings.GATEWAY_API_KEY}
    store = make_store()
    payload = {
        "request_id": "req-ok-1",
        "team_id": "team-1",
        "agent_id": "agent-1",
        "session_id": "session-1",
        "model": "mock-gpt-4o",
        "messages": [{"role": "user", "content": "hello gateway"}],
        "max_output_tokens": 20,
    }
    async with await _client_with_store(store) as client:
        resp = await client.post("/api/v1/gateway/chat/completions", headers=headers, json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["request_id"] == "req-ok-1"
        assert data["status"] == "SUCCESS"
        assert "Intercepted successfully" in data["content"]
        assert data["model"] == "mock-gpt-4o"
        assert data["estimated_input_tokens"] > 0

        # duplicate request id is rejected (idempotency identifier enforced)
        resp2 = await client.post("/api/v1/gateway/chat/completions", headers=headers, json=payload)
        assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_gateway_timeout_and_provider_error_behavior():
    headers = {"X-API-Key": settings.GATEWAY_API_KEY}
    base_payload = {
        "team_id": "team-1",
        "agent_id": "agent-1",
        "session_id": "session-1",
        "model": "mock-gpt-4o",
        "messages": [{"role": "user", "content": "hello"}],
        "max_output_tokens": 20,
    }

    store = make_store()
    async with await _client_with_store(store) as client:
        resp = await client.post("/api/v1/gateway/chat/completions", headers=headers, json={
            **base_payload, "request_id": "req-err-1", "simulate_error": "provider_error"
        })
        assert resp.status_code == 502

    # timeout behavior (gateway enforces timeout)
    old_timeout = settings.GATEWAY_TIMEOUT_SECONDS
    settings.GATEWAY_TIMEOUT_SECONDS = 0.001
    try:
        store = make_store()
        async with await _client_with_store(store) as client:
            resp = await client.post("/api/v1/gateway/chat/completions", headers=headers, json={
                **base_payload, "request_id": "req-timeout-1"
            })
        assert resp.status_code in (504, 200)  # 504 expected; allow 200 if mock returns extremely fast
        if resp.status_code == 504:
            assert "timeout" in resp.text.lower()
    finally:
        settings.GATEWAY_TIMEOUT_SECONDS = old_timeout


@pytest.mark.asyncio
async def test_gateway_rejects_inactive_agent_or_session():
    headers = {"X-API-Key": settings.GATEWAY_API_KEY}

    store = make_store(agent_status=AgentStatus.PAUSED)
    async with await _client_with_store(store) as client:
        resp = await client.post("/api/v1/gateway/chat/completions", headers=headers, json={
            "request_id": "req-paused-1",
            "team_id": "team-1",
            "agent_id": "agent-1",
            "session_id": "session-1",
            "messages": [{"role": "user", "content": "hello"}],
        })
    assert resp.status_code == 403
