import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.conversation import Conversation
from app.db.models.message import Message


def get_conversation(db: Session, conversation_id: uuid.UUID) -> Conversation | None:
    return db.get(Conversation, conversation_id)


def get_conversation_by_session(db: Session, session_id: str) -> Conversation | None:
    return db.scalar(select(Conversation).where(Conversation.session_id == session_id))


def list_conversations(
    db: Session,
    *,
    meeting_id: uuid.UUID | None = None,
    offset: int = 0,
    limit: int = 50,
    order_desc: bool = True,
) -> tuple[list[Conversation], int]:
    query = select(Conversation)
    count_query = select(func.count()).select_from(Conversation)

    if meeting_id is not None:
        query = query.where(Conversation.meeting_id == meeting_id)
        count_query = count_query.where(Conversation.meeting_id == meeting_id)

    if order_desc:
        query = query.order_by(Conversation.updated_at.desc())
    else:
        query = query.order_by(Conversation.updated_at.asc())

    query = query.offset(offset).limit(limit)

    rows = db.scalars(query).all()
    total = db.scalar(count_query)
    return rows, total


def create_conversation(
    db: Session,
    *,
    meeting_id: uuid.UUID | None = None,
    session_id: str | None = None,
    title: str | None = None,
) -> Conversation:
    conversation = Conversation(meeting_id=meeting_id, session_id=session_id, title=title)
    db.add(conversation)
    db.flush()
    return conversation


def update_conversation(db: Session, conversation_id: uuid.UUID, **updates: object) -> Conversation | None:
    from sqlalchemy import func as sa_func
    conversation = get_conversation(db, conversation_id)
    if conversation is None:
        return None

    for key, value in updates.items():
        if key == "updated_at" or value is None:
            continue
        setattr(conversation, key, value)

    # Always bump updated_at on manual edits so sidebar ordering reflects activity
    conversation.updated_at = sa_func.now()
    db.flush()
    return conversation


def delete_conversation(db: Session, conversation_id: uuid.UUID) -> bool:
    conversation = get_conversation(db, conversation_id)
    if conversation is None:
        return False

    db.delete(conversation)
    db.flush()
    return True


def create_message(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
) -> Message:
    message = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(message)
    db.flush()
    return message


def get_messages_for_conversation(
    db: Session,
    conversation_id: uuid.UUID,
    *,
    offset: int = 0,
    limit: int = 100,
) -> list[Message]:
    query = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(query).all())
