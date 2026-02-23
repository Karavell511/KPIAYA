from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, kpi, users
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine, AsyncSessionLocal
from app.services.bootstrap import bootstrap_security
from app.tasks.scheduler import configure_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await bootstrap_security(session)
    configure_scheduler()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(kpi.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
