import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.logging import get_logger
from app.db.repositories import zoom_accounts as zoom_account_repo

router = APIRouter()
logger = get_logger(__name__)


class ZoomAccountCreate(BaseModel):
    account_name: str = Field(..., min_length=1, max_length=255)
    zoom_account_id: str = Field(..., min_length=1, max_length=255)
    client_id: str = Field(..., min_length=1, max_length=255)
    client_secret: str = Field(..., min_length=1, max_length=255)
    enabled: bool = True
    is_default: bool = False
    token_url: str | None = None
    api_base_url: str | None = None
    notes: str | None = None


class ZoomAccountUpdate(BaseModel):
    account_name: str | None = None
    zoom_account_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    token_url: str | None = None
    api_base_url: str | None = None
    notes: str | None = None


class ZoomAccountOut(BaseModel):
    id: uuid.UUID
    account_name: str
    zoom_account_id: str
    client_id: str
    enabled: bool
    is_default: bool
    token_url: str
    api_base_url: str
    notes: str | None
    last_sync_at: str | None
    created_at: str
    updated_at: str


class ZoomAccountListOut(BaseModel):
    items: list[ZoomAccountOut]
    total: int


class ZoomAccountDetailOut(BaseModel):
    id: uuid.UUID
    account_name: str
    zoom_account_id: str
    client_id: str
    enabled: bool
    is_default: bool
    token_url: str
    api_base_url: str
    notes: str | None
    last_sync_at: str | None
    created_at: str
    updated_at: str


def _account_to_out(account) -> ZoomAccountOut:
    return ZoomAccountOut(
        id=account.id,
        account_name=account.account_name,
        zoom_account_id=account.zoom_account_id,
        client_id=account.client_id,
        enabled=account.enabled,
        is_default=account.is_default,
        token_url=account.token_url,
        api_base_url=account.api_base_url,
        notes=account.notes,
        last_sync_at=str(account.last_sync_at) if account.last_sync_at else None,
        created_at=str(account.created_at),
        updated_at=str(account.updated_at),
    )


@router.get("", response_model=ZoomAccountListOut)
def list_zoom_accounts(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ZoomAccountListOut:
    rows, total = zoom_account_repo.list_all(db, offset=offset, limit=limit)
    return ZoomAccountListOut(
        items=[_account_to_out(a) for a in rows],
        total=total,
    )


@router.get("/enabled", response_model=ZoomAccountListOut)
def list_enabled_accounts(
    db: Session = Depends(get_db),
) -> ZoomAccountListOut:
    rows = zoom_account_repo.list_enabled(db)
    return ZoomAccountListOut(
        items=[_account_to_out(a) for a in rows],
        total=len(rows),
    )


@router.get("/{account_id}", response_model=ZoomAccountDetailOut)
def get_zoom_account(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ZoomAccountDetailOut:
    account = zoom_account_repo.get_by_id(db, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zoom account not found")
    return ZoomAccountDetailOut(
        id=account.id,
        account_name=account.account_name,
        zoom_account_id=account.zoom_account_id,
        client_id=account.client_id,
        enabled=account.enabled,
        is_default=account.is_default,
        token_url=account.token_url,
        api_base_url=account.api_base_url,
        notes=account.notes,
        last_sync_at=str(account.last_sync_at) if account.last_sync_at else None,
        created_at=str(account.created_at),
        updated_at=str(account.updated_at),
    )


@router.post("", response_model=ZoomAccountDetailOut, status_code=status.HTTP_201_CREATED)
def create_zoom_account(
    request: ZoomAccountCreate,
    db: Session = Depends(get_db),
) -> ZoomAccountDetailOut:
    existing = zoom_account_repo.get_by_zoom_account_id(db, request.zoom_account_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Zoom account with ID '{request.zoom_account_id}' already exists",
        )
    try:
        account = zoom_account_repo.create(
            db,
            account_name=request.account_name,
            zoom_account_id=request.zoom_account_id,
            client_id=request.client_id,
            client_secret=request.client_secret,
            enabled=request.enabled,
            is_default=request.is_default,
            token_url=request.token_url,
            api_base_url=request.api_base_url,
            notes=request.notes,
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("zoom_accounts.create_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create Zoom account",
        ) from exc

    return ZoomAccountDetailOut(
        id=account.id,
        account_name=account.account_name,
        zoom_account_id=account.zoom_account_id,
        client_id=account.client_id,
        enabled=account.enabled,
        is_default=account.is_default,
        token_url=account.token_url,
        api_base_url=account.api_base_url,
        notes=account.notes,
        last_sync_at=None,
        created_at=str(account.created_at),
        updated_at=str(account.updated_at),
    )


@router.put("/{account_id}", response_model=ZoomAccountDetailOut)
def update_zoom_account(
    account_id: uuid.UUID,
    request: ZoomAccountUpdate,
    db: Session = Depends(get_db),
) -> ZoomAccountDetailOut:
    account = zoom_account_repo.get_by_id(db, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zoom account not found")
    try:
        account = zoom_account_repo.update_account(
            db,
            account,
            account_name=request.account_name,
            zoom_account_id=request.zoom_account_id,
            client_id=request.client_id,
            client_secret=request.client_secret,
            enabled=request.enabled,
            is_default=request.is_default,
            token_url=request.token_url,
            api_base_url=request.api_base_url,
            notes=request.notes,
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("zoom_accounts.update_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update Zoom account",
        ) from exc

    return ZoomAccountDetailOut(
        id=account.id,
        account_name=account.account_name,
        zoom_account_id=account.zoom_account_id,
        client_id=account.client_id,
        enabled=account.enabled,
        is_default=account.is_default,
        token_url=account.token_url,
        api_base_url=account.api_base_url,
        notes=account.notes,
        last_sync_at=str(account.last_sync_at) if account.last_sync_at else None,
        created_at=str(account.created_at),
        updated_at=str(account.updated_at),
    )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_zoom_account(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    account = zoom_account_repo.get_by_id(db, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zoom account not found")
    try:
        zoom_account_repo.delete_account(db, account)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("zoom_accounts.delete_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete Zoom account",
        ) from exc


@router.post("/{account_id}/set-default", response_model=ZoomAccountDetailOut)
def set_default_account(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ZoomAccountDetailOut:
    account = zoom_account_repo.get_by_id(db, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zoom account not found")
    try:
        account = zoom_account_repo.update_account(db, account, is_default=True)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("zoom_accounts.set_default_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set default Zoom account",
        ) from exc

    return ZoomAccountDetailOut(
        id=account.id,
        account_name=account.account_name,
        zoom_account_id=account.zoom_account_id,
        client_id=account.client_id,
        enabled=account.enabled,
        is_default=account.is_default,
        token_url=account.token_url,
        api_base_url=account.api_base_url,
        notes=account.notes,
        last_sync_at=str(account.last_sync_at) if account.last_sync_at else None,
        created_at=str(account.created_at),
        updated_at=str(account.updated_at),
    )
