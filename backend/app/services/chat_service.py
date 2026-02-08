import uuid
from datetime import date

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatSession, ChatMessage, DailyTokenUsage
from app.config import settings


async def get_or_create_session(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID | None = None
) -> ChatSession:
    """Return the given session or create a new general session."""
    if session_id:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id, ChatSession.user_id == user_id
            )
        )
        session = result.scalar_one_or_none()
        if session:
            return session

    session = ChatSession(user_id=user_id, session_type="general")
    db.add(session)
    await db.flush()
    return session


async def save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: str,
    content: str,
    hint_level_used: int | None = None,
    problem_difficulty: int | None = None,
    maths_difficulty: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> ChatMessage:
    """Persist a chat message to the database."""
    msg = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        hint_level_used=hint_level_used,
        problem_difficulty=problem_difficulty,
        maths_difficulty=maths_difficulty,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    db.add(msg)
    await db.flush()
    return msg


async def get_chat_history(
    db: AsyncSession, session_id: uuid.UUID
) -> list[dict]:
    """Load all messages from a session in chronological order."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return [{"role": m.role, "content": m.content} for m in messages]


async def get_session_messages(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> list[dict]:
    """Load all messages for a session (with ownership check)."""
    sess_result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        )
    )
    if not sess_result.scalar_one_or_none():
        return []

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "hint_level_used": m.hint_level_used,
            "problem_difficulty": m.problem_difficulty,
            "maths_difficulty": m.maths_difficulty,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


async def get_user_sessions(
    db: AsyncSession, user_id: uuid.UUID
) -> list[dict]:
    """Return all sessions for a user, newest first, with preview text."""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.created_at.desc())
    )
    sessions = result.scalars().all()

    session_list = []
    for s in sessions:
        msg_result = await db.execute(
            select(ChatMessage.content)
            .where(
                ChatMessage.session_id == s.id,
                ChatMessage.role == "user",
            )
            .order_by(ChatMessage.created_at.asc())
            .limit(1)
        )
        first_msg = msg_result.scalar_one_or_none()
        preview = first_msg[:80] if first_msg else "New conversation"
        session_list.append(
            {
                "id": str(s.id),
                "preview": preview,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
        )
    return session_list


async def delete_session(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> bool:
    """Delete a session and all its messages. Returns True if deleted."""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        return False

    await db.execute(
        delete(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    await db.delete(session)
    await db.flush()
    return True


async def get_daily_usage(db: AsyncSession, user_id: uuid.UUID) -> DailyTokenUsage:
    """Get or create today's token usage record."""
    today = date.today()
    result = await db.execute(
        select(DailyTokenUsage).where(
            DailyTokenUsage.user_id == user_id, DailyTokenUsage.date == today
        )
    )
    usage = result.scalar_one_or_none()
    if not usage:
        usage = DailyTokenUsage(
            user_id=user_id, date=today, input_tokens_used=0, output_tokens_used=0
        )
        db.add(usage)
        await db.flush()
    return usage


async def increment_token_usage(
    db: AsyncSession,
    user_id: uuid.UUID,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Add tokens to today's daily usage counters."""
    usage = await get_daily_usage(db, user_id)
    usage.input_tokens_used += input_tokens
    usage.output_tokens_used += output_tokens
    await db.flush()


async def check_daily_limit(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Return True if the user is within both daily token limits."""
    usage = await get_daily_usage(db, user_id)
    input_ok = usage.input_tokens_used < settings.user_daily_input_token_limit
    output_ok = usage.output_tokens_used < settings.user_daily_output_token_limit
    return input_ok and output_ok
