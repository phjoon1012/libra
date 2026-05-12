"""FastAPI entrypoint for the LIBRA backend.

Routes are intentionally thin. All business logic lives in
``app.services``. Provider-specific code stays behind the voice service
abstraction.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, memory, tools, voice
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Place for future startup/shutdown (db pool, redis, provider clients).
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="LIBRA API",
        version="0.1.0",
        description="Orchestrator backend for the LIBRA personal AI companion.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(tools.router, prefix="/api/tools", tags=["tools"])

    return app


app = create_app()
