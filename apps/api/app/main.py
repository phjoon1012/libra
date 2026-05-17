"""FastAPI entrypoint for the LIBRA backend.

Routes are intentionally thin. All business logic lives in
``app.services``. Provider-specific code stays behind the voice service
abstraction.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, integrations, memory, tools, voice
from app.core.config import get_settings
from app.services.events import start_vision_bridge, stop_vision_bridge
from app.services.tools import register_builtin_tools


def _configure_logging(level_name: str) -> None:
    """Make `app.*` loggers visible on stdout.

    Uvicorn's default config keeps the root logger at WARNING, which
    silences our INFO lines (vision bridge, distiller, etc.). We turn on
    our own namespace explicitly and leave uvicorn's own loggers alone.
    """
    level = getattr(logging, level_name.upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-5s %(name)s :: %(message)s")
    )
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        app_logger.addHandler(handler)
    app_logger.setLevel(level)
    app_logger.propagate = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    register_builtin_tools()
    settings = get_settings()
    start_vision_bridge(settings)
    try:
        yield
    finally:
        stop_vision_bridge()


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(settings.log_level)

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
    app.include_router(
        integrations.router, prefix="/api/integrations", tags=["integrations"]
    )

    return app


app = create_app()
