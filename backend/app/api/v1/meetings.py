import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import (
    block_in_public_demo,
    get_db,
)
from app.core.config import settings
from app.db.repositories import meetings as meeting_repo
from app.schemas.meetings import (
    MeetingDetailOut,
    MeetingListItem,
    MeetingListOut,
    PublicMeetingListItem,
    PublicMeetingListOut,
)


router = APIRouter()


# ============================================================
# MEETING LIST
# ============================================================

@router.get("")
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
        pattern="^(created_at|updated_at|start_time)$",
    ),
    order: str = Query(
        "asc",
        pattern="^(asc|desc)$",
    ),
    db: Session = Depends(get_db),
):
    """
    Meeting list.

    Normal application:
        Returns the complete MeetingListItem schema.

    Public portfolio:
        Returns only safe meeting metadata.
    """

    rows, total = meeting_repo.list_meetings(
        db,
        offset=offset,
        limit=limit,
        order_by=order_by,
        order_desc=(order == "desc"),
    )


    # --------------------------------------------------------
    # PUBLIC PORTFOLIO
    # --------------------------------------------------------

    if settings.public_demo_mode:

        items = [
            PublicMeetingListItem(
                id=meeting.id,
                source=meeting.source,
                topic=meeting.topic,
                start_time=meeting.start_time,
                duration_minutes=meeting.duration_minutes,
            )
            for meeting in rows
        ]

        return PublicMeetingListOut(
            items=items,
            total=total,
            offset=offset,
            limit=limit,
        )


    # --------------------------------------------------------
    # NORMAL / PRIVATE APPLICATION
    # --------------------------------------------------------

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


# ============================================================
# MEETING DETAILS
# ============================================================

@router.get(
    "/{meeting_id}",
    response_model=MeetingDetailOut,
    dependencies=[
        Depends(block_in_public_demo)
    ],
)
def get_meeting(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> MeetingDetailOut:
    """
    Full meeting details.

    Disabled completely in public portfolio mode because
    the response may contain Zoom/account/host information.
    """

    detail = meeting_repo.get_meeting_detail(
        db,
        meeting_id,
    )

    if detail is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        )

    return MeetingDetailOut.model_validate(
        detail
    )