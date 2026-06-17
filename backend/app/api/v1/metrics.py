from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.repositories import metrics as metrics_repo

router = APIRouter()


@router.get("")
def list_metrics(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> dict:
    return metrics_repo.get_queue_metrics(db, hours=hours)


@router.get("/queue")
def get_queue_metrics(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> dict:
    return metrics_repo.get_queue_metrics(db, hours=hours)
