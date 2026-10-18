"""Application factory: wires routers and runs idempotent startup seeding."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import Base, SessionLocal, engine
from app.routers import payments, tariffs, webhooks
from app.seed import seed


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            seed(db)
        yield

    app = FastAPI(title="Kvitto Payments", version="1.0.0", lifespan=lifespan)
    app.include_router(tariffs.router)
    app.include_router(payments.router)
    app.include_router(webhooks.router)
    return app


app = create_app()
