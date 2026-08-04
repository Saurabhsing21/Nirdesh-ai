from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth.tokens import encode_access_token
from app.config import Settings
from app.main import create_app
from app.voice.protocol import validate_client_message

USER_ID = "00000000-0000-0000-0000-000000000001"
EMAIL = "person@example.com"


def build_app(tmp_path: Path, *, balance_paise: int, session_factory=None):
    database_path = tmp_path / "ws.db"
    settings = Settings(
        jwt_secret="test-secret-that-is-at-least-thirty-two-characters",
        database_url=f"sqlite+aiosqlite:///{database_path}",
        sarvam_api_key=None,
        exa_api_key=None,
        resend_api_key=None,
        min_voice_balance_paise=1,
    )
    app = create_app(settings)
    asyncio.run(app.state.database.create_all())
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO users (id, email, created_at, is_verified) VALUES (?, ?, ?, 1)",
            (USER_ID, EMAIL, "2026-01-01 00:00:00"),
        )
        if balance_paise:
            connection.execute(
                """
                INSERT INTO wallet_transactions
                    (id, user_id, amount_paise, kind, usage_session_id, created_at)
                VALUES (?, ?, ?, 'topup', NULL, ?)
                """,
                (
                    "00000000-0000-0000-0000-000000000002",
                    USER_ID,
                    balance_paise,
                    "2026-01-01 00:00:00",
                ),
            )
    if session_factory is not None:
        app.state.voice_session_factory = session_factory
    token = encode_access_token(
        user_id=USER_ID,
        email=EMAIL,
        secret=settings.jwt_secret_value,
        algorithm=settings.jwt_algorithm,
        ttl_seconds=60,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
    return app, token


class InterruptScriptedSession:
    def __init__(self, *, websocket: WebSocket, **kwargs) -> None:
        del kwargs
        self.websocket = websocket

    async def run(self) -> None:
        await self.websocket.send_json(
            {
                "type": "ready",
                "session_id": "session-1",
                "balance_paise": 500,
                "price_per_minute_paise": 200,
                "tts_sample_rate_hz": 24000,
            }
        )
        await self.websocket.send_json({"type": "interrupt", "turn_id": "turn-1"})
        acknowledgement = validate_client_message(await self.websocket.receive_json())
        assert acknowledgement["type"] == "interrupt_ack"
        await self.websocket.send_json(
            {
                "type": "interrupt_resolved",
                "turn_id": "turn-1",
                "barge_in_stop_ack_ms": 20.0,
            }
        )
        await self.websocket.close(code=1000)


class ExhaustionScriptedSession:
    def __init__(self, *, websocket: WebSocket, **kwargs) -> None:
        del kwargs
        self.websocket = websocket

    async def run(self) -> None:
        await self.websocket.send_json(
            {
                "type": "billing",
                "seconds": 2,
                "cost_paise": 5,
                "balance_paise": 0,
                "low_balance": True,
                "final": True,
                "terminated_reason": "balance_exhausted",
            }
        )
        await self.websocket.send_json({"type": "call_ended", "reason": "balance_exhausted"})
        await self.websocket.close(code=4403, reason="Balance exhausted")


def test_ws_rejects_below_minimum_balance_with_4402(tmp_path: Path) -> None:
    app, token = build_app(tmp_path, balance_paise=0)

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/ws/voice?token={token}") as websocket,
    ):
        error = websocket.receive_json()
        assert error["code"] == "insufficient_balance"
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()

    assert closed.value.code == 4402


def test_ws_expired_token_closes_with_4401_and_logs_reason(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = build_app(tmp_path, balance_paise=500)
    settings = app.state.settings
    expired = encode_access_token(
        user_id=USER_ID,
        email=EMAIL,
        secret=settings.jwt_secret_value,
        algorithm=settings.jwt_algorithm,
        ttl_seconds=1,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        now=datetime.now(UTC) - timedelta(minutes=1),
    )

    monkeypatch.setattr(logging.getLogger("voxloom"), "propagate", True)
    with (
        caplog.at_level(logging.WARNING, logger="voxloom.auth"),
        TestClient(app) as client,
        client.websocket_connect(f"/ws/voice?token={expired}") as websocket,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        websocket.receive_text()

    assert closed.value.code == 4401
    payloads = [json.loads(record.message) for record in caplog.records]
    assert {
        "event": "auth_rejected",
        "surface": "voice_websocket",
        "reason": "expired_token",
        "close_code": 4401,
    } in payloads
    assert expired not in caplog.text


def test_interrupt_and_interrupt_ack_sequence(tmp_path: Path) -> None:
    app, token = build_app(
        tmp_path,
        balance_paise=500,
        session_factory=InterruptScriptedSession,
    )

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/ws/voice?token={token}") as websocket,
    ):
        assert websocket.receive_json()["type"] == "ready"
        interrupt = websocket.receive_json()
        assert interrupt == {"type": "interrupt", "turn_id": "turn-1"}
        websocket.send_json(
            {
                "type": "interrupt_ack",
                "turn_id": "turn-1",
                "interrupt_received_perf_ms": 10.0,
                "queue_cleared_perf_ms": 11.0,
                "audio_queue_cleared": True,
            }
        )
        assert websocket.receive_json()["type"] == "interrupt_resolved"
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()

    assert closed.value.code == 1000


def test_mid_call_exhaustion_closes_with_4403(tmp_path: Path) -> None:
    app, token = build_app(
        tmp_path,
        balance_paise=5,
        session_factory=ExhaustionScriptedSession,
    )

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/ws/voice?token={token}") as websocket,
    ):
        billing = websocket.receive_json()
        assert billing["terminated_reason"] == "balance_exhausted"
        assert billing["balance_paise"] == 0
        assert websocket.receive_json() == {
            "type": "call_ended",
            "reason": "balance_exhausted",
        }
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()

    assert closed.value.code == 4403
