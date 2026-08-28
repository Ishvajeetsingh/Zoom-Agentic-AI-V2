from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = None
    job_queue = None
    if settings.sync_scheduler_enabled:
        from app.services.sync_scheduler import SyncScheduler
        scheduler = SyncScheduler.get_instance()
        scheduler.start(poll_interval=settings.sync_scheduler_poll_interval_seconds)
    if settings.job_queue_num_workers > 0:
        from app.services.job_queue_service import JobQueueService
        job_queue = JobQueueService()
        job_queue.start_workers(
            num_workers=settings.job_queue_num_workers,
            poll_interval=settings.job_queue_poll_interval_seconds,
        )
    yield
    if job_queue is not None:
        job_queue.stop_workers()
    if scheduler is not None:
        scheduler.stop()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.0.163:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()

