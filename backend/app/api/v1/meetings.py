import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.db.repositories import (
    meetings as meeting_repo,
)
from app.schemas.meetings import (
    MeetingDetailOut,
    MeetingListItem,
    MeetingListOut,
)


router = APIRouter()


@router.get(
    "",
    response_model=MeetingListOut,
)
def list_meetings(
    offset: int = Query(
        0,
        ge=0,
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
    ),
    order_by: str = Query(
        "created_at",
        pattern=(
            "^(created_at|"
            "updated_at|"
            "start_time)$"
        ),
    ),
    order: str = Query(
        "asc",
        pattern="^(asc|desc)$",
    ),
    db: Session = Depends(get_db),
) -> MeetingListOut:

    # Public portfolio mode exposes only the
    # sanitized Zoom meeting showcase.
    #
    # Historical source="upload" placeholders
    # are intentionally excluded.
    #
    # Normal/full mode remains unchanged and
    # returns meetings from all sources.
    source_filter = (
        "zoom"
        if settings.public_demo_mode
        else None
    )

    rows, total = (
        meeting_repo.list_meetings(
            db,
            offset=offset,
            limit=limit,
            order_by=order_by,
            order_desc=(
                order == "desc"
            ),
            source=source_filter,
        )
    )

    items = [
        MeetingListItem.model_validate(
            meeting
        )
        for meeting in rows
    ]

    return MeetingListOut(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{meeting_id}",
    response_model=MeetingDetailOut,
)
def get_meeting(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> MeetingDetailOut:

    # Meeting details can contain fields such
    # as host/account identifiers and are not
    # exposed by the public portfolio.
    if settings.public_demo_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Meeting details are protected "
                "in the public portfolio demo."
            ),
        )

    detail = (
        meeting_repo.get_meeting_detail(
            db,
            meeting_id,
        )
    )

    if detail is None:
        raise HTTPException(
            status_code=
                status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        )

    return MeetingDetailOut.model_validate(
        detail
    )