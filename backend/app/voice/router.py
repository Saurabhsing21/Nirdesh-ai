from __future__ import annotations

import time

from fastapi import APIRouter, WebSocket
from sqlalchemy import select

from app.auth.logging import log_auth_rejection
from app.auth.tokens import (
    AccessTokenError,
    access_token_rejection_reason,
    decode_access_token,
)
from app.config import Settings
from app.db import Database
from app.models import User
from app.voice.agent import AgentObservabilityError
from app.voice.protocol import ProbeOptions
from app.voice.session import VoiceSession, VoiceSessionError
from app.voice.stt import SarvamSttError
from app.voice.tts import SarvamTtsError
from app.wallet.service import WalletService

router = APIRouter()

STT_CODECS = {"wav", "pcm_s16le", "pcm_l16", "pcm_raw"}
STT_ENCODINGS = {"audio/wav", "audio/pcm", "pcm_s16le", "pcm_l16", "pcm_raw"}
TTS_CODECS = {"pcm", "linear16", "wav", "mp3"}


@router.websocket("/ws/voice")
async def voice_socket(websocket: WebSocket) -> None:
    settings: Settings = websocket.app.state.settings
    token = websocket.query_params.get("token")
    user, rejection_reason = (
        (None, "missing_token")
        if token is None
        else await _authenticated_user(token, settings, websocket.app.state.database)
    )
    if user is None:
        log_auth_rejection(
            surface="voice_websocket",
            reason=rejection_reason or "invalid_token",
            close_code=4401,
        )
        # Accept before closing so browsers receive the application close code
        # instead of exposing the failed handshake only as an HTTP 403.
        await websocket.accept()
        await websocket.close(code=4401, reason="Invalid or expired access token")
        return

    wallet: WalletService = websocket.app.state.wallet_service
    starting_balance = await wallet.balance(user.id)
    if starting_balance < settings.min_voice_balance_paise:
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "code": "insufficient_balance",
                "message": (
                    f"A balance of at least {settings.min_voice_balance_paise} paise is required."
                ),
                "balance_paise": starting_balance,
            }
        )
        await websocket.close(code=4402, reason="Insufficient balance - recharge required")
        return

    probe_options = _probe_options(websocket, settings)
    await websocket.accept()
    connected_at = time.monotonic()
    try:
        session_factory = getattr(websocket.app.state, "voice_session_factory", VoiceSession)
        extension_factories = getattr(
            websocket.app.state,
            "voice_extension_factories",
            (),
        )
        session = session_factory(
            websocket=websocket,
            settings=settings,
            probe_options=probe_options,
            database=websocket.app.state.database,
            user_id=user.id,
            wallet=wallet,
            starting_balance_paise=starting_balance,
            connected_at=connected_at,
            agent_extensions=[factory(user.id) for factory in extension_factories],
        )
        await session.run()
    except Exception as exc:
        visible_errors = (
            AgentObservabilityError,
            SarvamSttError,
            SarvamTtsError,
            VoiceSessionError,
        )
        message = str(exc) if isinstance(exc, visible_errors) else "Voice session failed"
        try:
            await websocket.send_json(
                {"type": "error", "code": "voice_session_error", "message": message}
            )
            await websocket.close(code=1011)
        except RuntimeError:
            pass


async def _authenticated_user(
    token: str, settings: Settings, database: Database
) -> tuple[User | None, str | None]:
    try:
        claims = decode_access_token(
            token,
            secret=settings.jwt_secret_value,
            algorithm=settings.jwt_algorithm,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except AccessTokenError as exc:
        return None, access_token_rejection_reason(exc)
    async with database.session_factory() as session:
        result = await session.execute(select(User).where(User.id == claims.user_id))
        user = result.scalar_one_or_none()
    if user and user.is_verified and user.email == claims.email:
        return user, None
    return None, "invalid_token"


def _probe_options(websocket: WebSocket, settings: Settings) -> ProbeOptions:
    enabled = (
        settings.app_env == "development"
        and websocket.query_params.get("probe", "false").lower() == "true"
    )
    if not enabled:
        return ProbeOptions()
    return ProbeOptions(
        enabled=True,
        stt_input_audio_codec=_allowed_query(websocket, "stt_codec", STT_CODECS),
        stt_audio_encoding=_allowed_query(websocket, "stt_encoding", STT_ENCODINGS),
        tts_output_audio_codec=_allowed_query(websocket, "tts_codec", TTS_CODECS),
        endpointing_strategy=_allowed_query(
            websocket, "endpointing_strategy", {"local_vad", "sarvam"}
        ),
    )


def _allowed_query(websocket: WebSocket, name: str, allowed: set[str]) -> str | None:
    value = websocket.query_params.get(name)
    return value if value in allowed else None
