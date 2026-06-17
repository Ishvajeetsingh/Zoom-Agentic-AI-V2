import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models.zoom_account import ZoomAccount


def get_by_id(db: Session, account_id: uuid.UUID) -> ZoomAccount | None:
    return db.get(ZoomAccount, account_id)


def get_by_zoom_account_id(db: Session, zoom_account_id: str) -> ZoomAccount | None:
    return db.scalar(select(ZoomAccount).where(ZoomAccount.zoom_account_id == zoom_account_id))


def get_default(db: Session) -> ZoomAccount | None:
    return db.scalar(select(ZoomAccount).where(ZoomAccount.is_default.is_(True)).limit(1))


def list_enabled(db: Session) -> list[ZoomAccount]:
    return list(db.scalars(select(ZoomAccount).where(ZoomAccount.enabled.is_(True)).order_by(ZoomAccount.account_name)).all())


def list_all(db: Session, *, offset: int = 0, limit: int = 100) -> tuple[list[ZoomAccount], int]:
    from sqlalchemy import func
    count = db.scalar(select(func.count()).select_from(ZoomAccount))
    rows = db.scalars(
        select(ZoomAccount).order_by(ZoomAccount.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return list(rows), count or 0


def create(db: Session, *, account_name: str, zoom_account_id: str, client_id: str, client_secret: str, enabled: bool = True, is_default: bool = False, token_url: str | None = None, api_base_url: str | None = None, notes: str | None = None) -> ZoomAccount:
    if is_default:
        _clear_other_defaults(db)
    account = ZoomAccount(
        account_name=account_name,
        zoom_account_id=zoom_account_id,
        client_id=client_id,
        client_secret=client_secret,
        enabled=enabled,
        is_default=is_default,
        token_url=token_url or "https://zoom.us/oauth/token",
        api_base_url=api_base_url or "https://api.zoom.us/v2",
        notes=notes,
    )
    db.add(account)
    db.flush()
    return account


def update_account(db: Session, account: ZoomAccount, *, account_name: str | None = None, zoom_account_id: str | None = None, client_id: str | None = None, client_secret: str | None = None, enabled: bool | None = None, is_default: bool | None = None, token_url: str | None = None, api_base_url: str | None = None, notes: str | None = None) -> ZoomAccount:
    if account_name is not None:
        account.account_name = account_name
    if zoom_account_id is not None:
        account.zoom_account_id = zoom_account_id
    if client_id is not None:
        account.client_id = client_id
    if client_secret is not None:
        account.client_secret = client_secret
    if enabled is not None:
        account.enabled = enabled
    if is_default is not None:
        if is_default:
            _clear_other_defaults(db)
        account.is_default = is_default
    if token_url is not None:
        account.token_url = token_url
    if api_base_url is not None:
        account.api_base_url = api_base_url
    if notes is not None:
        account.notes = notes
    db.flush()
    return account


def delete_account(db: Session, account: ZoomAccount) -> None:
    db.delete(account)
    db.flush()


def update_last_sync(db: Session, account_id: uuid.UUID) -> None:
    db.execute(
        update(ZoomAccount).where(ZoomAccount.id == account_id).values(last_sync_at=datetime.now(UTC))
    )
    db.flush()


def _clear_other_defaults(db: Session) -> None:
    db.execute(
        update(ZoomAccount).where(ZoomAccount.is_default.is_(True)).values(is_default=False)
    )
