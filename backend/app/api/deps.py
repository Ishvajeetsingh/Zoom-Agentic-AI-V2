from collections.abc import Generator

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def block_in_public_demo() -> None:
    """
    Block an endpoint when the application is running
    as the public portfolio demonstration.

    Usage:

        @router.post(
            "/something",
            dependencies=[Depends(block_in_public_demo)]
        )

    Normal/local application:
        PUBLIC_DEMO_MODE=false
        -> endpoint works normally

    Public portfolio:
        PUBLIC_DEMO_MODE=true
        -> HTTP 403
    """

    if settings.public_demo_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This feature is disabled in the "
                "public portfolio demo."
            ),
        )