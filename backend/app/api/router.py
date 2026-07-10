from fastapi import APIRouter

from app.api.v1 import (
    atlas,
    exports,
    health,
    insights,
    meetings,
    metrics,
    processing_runs,
    questions,
    sync,
    transcripts,
    webhooks,
    zoom,
    zoom_accounts,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(zoom.router, prefix="/zoom", tags=["zoom"])
api_router.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
api_router.include_router(transcripts.router, prefix="/transcripts", tags=["transcripts"])
api_router.include_router(insights.router, prefix="/transcripts", tags=["insights"])
api_router.include_router(processing_runs.router, prefix="/processing-runs", tags=["processing-runs"])
api_router.include_router(questions.router, prefix="/questions", tags=["questions"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])
api_router.include_router(zoom_accounts.router, prefix="/zoom-accounts", tags=["zoom-accounts"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(atlas.router, prefix="/atlas", tags=["atlas"])

