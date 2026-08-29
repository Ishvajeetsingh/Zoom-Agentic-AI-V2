from fastapi import APIRouter, Depends

from app.api.deps import block_in_public_demo

from app.api.v1 import (
    public_demo,
    atlas,
    atlas_proxy,
    exports,
    health,
    insights,
    meetings,
    metrics,
    ollama,
    processing_runs,
    questions,
    sync,
    transcripts,
    webhooks,
    zoom,
    zoom_accounts,
)


api_router = APIRouter()


# ============================================================
# SAFE / PUBLIC ROUTES
# ============================================================

# Basic application health
api_router.include_router(
    health.router,
    tags=["health"],
)

# Safe meeting list/details will be restricted separately.
# We keep this router available because the public portfolio
# needs meeting metadata for the populated Meetings page.
api_router.include_router(
    meetings.router,
    prefix="/meetings",
    tags=["meetings"],
)
# Public portfolio interactive transcript demo.
#
# This router exposes only the explicitly approved
# upload -> processing -> generated questions workflow.
# The normal transcript API remains protected below.
api_router.include_router(
    public_demo.router,
    prefix="/public-demo",
    tags=["public-demo"],
)

# Aggregate dashboard metrics.
api_router.include_router(
    metrics.router,
    prefix="/metrics",
    tags=["metrics"],
)

# Processing runs contain useful portfolio/dashboard information.
# Individual sensitive fields/actions will be restricted separately.
api_router.include_router(
    processing_runs.router,
    prefix="/processing-runs",
    tags=["processing-runs"],
)

# Ollama/cloud-model status.
api_router.include_router(
    ollama.router,
)


# ============================================================
# PRIVATE ROUTES
#
# These continue to work normally when:
#
#     PUBLIC_DEMO_MODE=false
#
# But every endpoint below returns HTTP 403 when:
#
#     PUBLIC_DEMO_MODE=true
# ============================================================


# ------------------------------------------------------------
# Transcripts
# ------------------------------------------------------------

api_router.include_router(
    transcripts.router,
    prefix="/transcripts",
    tags=["transcripts"],
    dependencies=[Depends(block_in_public_demo)],
)


# ------------------------------------------------------------
# Transcript-derived insights
# ------------------------------------------------------------

api_router.include_router(
    insights.router,
    prefix="/transcripts",
    tags=["insights"],
    dependencies=[Depends(block_in_public_demo)],
)


# ------------------------------------------------------------
# Generated questions
# ------------------------------------------------------------

api_router.include_router(
    questions.router,
    prefix="/questions",
    tags=["questions"],
    dependencies=[Depends(block_in_public_demo)],
)


# ------------------------------------------------------------
# Exports
# ------------------------------------------------------------

api_router.include_router(
    exports.router,
    prefix="/exports",
    tags=["exports"],
    dependencies=[Depends(block_in_public_demo)],
)


# ------------------------------------------------------------
# Zoom ingestion / discovery / orchestration
# ------------------------------------------------------------

api_router.include_router(
    zoom.router,
    prefix="/zoom",
    tags=["zoom"],
    dependencies=[Depends(block_in_public_demo)],
)


# ------------------------------------------------------------
# Zoom accounts
#
# We do NOT expose real Zoom account records in portfolio mode.
# The frontend will later display a harmless demo representation.
# ------------------------------------------------------------

api_router.include_router(
    zoom_accounts.router,
    prefix="/zoom-accounts",
    tags=["zoom-accounts"],
    dependencies=[Depends(block_in_public_demo)],
)


# ------------------------------------------------------------
# Zoom synchronization
# ------------------------------------------------------------

api_router.include_router(
    sync.router,
    prefix="/sync",
    tags=["sync"],
    dependencies=[Depends(block_in_public_demo)],
)


# ------------------------------------------------------------
# Zoom webhooks
# ------------------------------------------------------------

api_router.include_router(
    webhooks.router,
    prefix="/webhooks",
    tags=["webhooks"],
    dependencies=[Depends(block_in_public_demo)],
)


# ------------------------------------------------------------
# Atlas
#
# Atlas can indirectly reveal transcript content through
# retrieval/chat, so it is disabled in public portfolio mode.
# ------------------------------------------------------------

api_router.include_router(
    atlas.router,
    prefix="/atlas",
    tags=["atlas"],
    dependencies=[Depends(block_in_public_demo)],
)


# ------------------------------------------------------------
# Atlas REST proxy / retrieval
# ------------------------------------------------------------

api_router.include_router(
    atlas_proxy.router,
    tags=["atlas-proxy"],
    dependencies=[Depends(block_in_public_demo)],
)