from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.addons import build_addon_registry
from app.analytics.router import router as analytics_router
from app.auth.email import ConsoleOtpSender, ResendOtpSender
from app.auth.router import router as auth_router
from app.config import Settings
from app.db import Database
from app.logging import configure_application_logging, install_token_log_redaction
from app.voice.router import router as voice_router
from app.wallet.router import router as wallet_router
from app.wallet.service import WalletService


def create_app(settings: Settings | None = None) -> FastAPI:
    install_token_log_redaction()
    resolved_settings = settings or Settings()
    configure_application_logging(resolved_settings.log_level)
    database = Database(
        resolved_settings.database_url,
        echo=resolved_settings.database_echo,
    )
    wallet_service = WalletService(database)
    addon_registry = build_addon_registry(resolved_settings, database)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await database.create_all()
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            resend_key = resolved_settings.resend_api_key
            if resend_key is None:
                app.state.email_sender = ConsoleOtpSender()
            else:
                app.state.email_sender = ResendOtpSender(
                    api_key=resend_key.get_secret_value(),
                    sender=resolved_settings.resend_from,
                    client=http_client,
                )
            async with addon_registry.lifespan(app, http_client):
                yield
        await database.dispose()

    app = FastAPI(
        title="NirdeshAI API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = database
    app.state.wallet_service = wallet_service
    addon_registry.install(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(wallet_router)
    app.include_router(voice_router)
    app.include_router(analytics_router)

    @app.get("/capabilities", tags=["system"])
    async def capabilities() -> dict[str, dict[str, bool]]:
        return {"features": addon_registry.capabilities}

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
