import json
import logging
import uuid as uuid_mod
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.services.auth_service import decode_token
from app.services import chat_service
from app.ai.embedding_service import EmbeddingService
from app.ai.pedagogy_engine import PedagogyEngine, StudentState
from app.ai.context_builder import build_system_prompt, build_context_messages
from app.ai.llm_factory import get_llm_provider
from app.ai.llm_base import LLMProvider, LLMError
from app.schemas.chat import TokenUsageOut, ChatSessionListItem, ChatMessageOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Shared services (initialised on first connection)
_embedding_service: EmbeddingService | None = None
_pedagogy_engine: PedagogyEngine | None = None


async def _get_services(llm: LLMProvider) -> tuple[EmbeddingService, PedagogyEngine]:
    """Lazy-initialise the embedding service and pedagogy engine."""
    global _embedding_service, _pedagogy_engine
    if _embedding_service is None:
        _embedding_service = EmbeddingService(
            provider=settings.embedding_provider,
            cohere_api_key=settings.cohere_api_key,
            voyage_api_key=settings.voyageai_api_key,
        )
        await _embedding_service.initialize()
    if _pedagogy_engine is None or _pedagogy_engine.llm is not llm:
        _pedagogy_engine = PedagogyEngine(_embedding_service, llm)
    return _embedding_service, _pedagogy_engine


async def _authenticate_ws(token: str) -> User | None:
    """Validate a JWT token and return the user, or None."""
    try:
        payload = decode_token(token)
        if payload.get("token_type") != "access":
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
    except ValueError:
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


# ── REST endpoints ──────────────────────────────────────────────────


@router.get("/api/chat/sessions")
async def list_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return all chat sessions for the current user, newest first."""
    return await chat_service.get_user_sessions(db, current_user.id)


@router.delete("/api/chat/sessions/{session_id}")
async def delete_session(
    session_id: uuid_mod.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a chat session and all its messages."""
    deleted = await chat_service.delete_session(db, current_user.id, session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    await db.commit()
    return {"message": "Session deleted"}


@router.get("/api/chat/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: uuid_mod.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return all messages for a session in chronological order."""
    messages = await chat_service.get_session_messages(
        db, current_user.id, session_id
    )
    if not messages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    return messages


@router.get("/api/chat/usage", response_model=TokenUsageOut)
async def get_usage(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return today's token usage for the current user."""
    usage = await chat_service.get_daily_usage(db, current_user.id)
    input_limit = settings.user_daily_input_token_limit
    output_limit = settings.user_daily_output_token_limit
    input_pct = (usage.input_tokens_used / input_limit * 100) if input_limit > 0 else 0
    output_pct = (usage.output_tokens_used / output_limit * 100) if output_limit > 0 else 0
    display_pct = round(max(input_pct, output_pct), 1)
    return TokenUsageOut(
        date=usage.date,
        input_tokens_used=usage.input_tokens_used,
        output_tokens_used=usage.output_tokens_used,
        daily_input_limit=input_limit,
        daily_output_limit=output_limit,
        usage_percentage=min(100.0, display_pct),
    )


# ── WebSocket endpoint ──────────────────────────────────────────────


@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(...),
):
    """WebSocket endpoint for the chat pipeline.

    Client sends JSON: {"content": "...", "session_id": "..." | null}
    Server sends JSON events:
      {"type": "session", "session_id": "..."}
      {"type": "token", "content": "..."}
      {"type": "done", "hint_level": N, "programming_difficulty": N, "maths_difficulty": N}
      {"type": "error", "message": "..."}
      {"type": "canned", "content": "...", "filter": "..."}
    """
    user = await _authenticate_ws(token)
    if not user:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    await websocket.accept()

    try:
        llm = get_llm_provider(settings)
        embedding_service, pedagogy_engine = await _get_services(llm)
    except Exception as e:
        logger.error("Failed to initialise AI services: %s", e)
        await websocket.send_json({"type": "error", "message": "Service unavailable"})
        await websocket.close()
        return

    # Build student state from user record
    student_state = StudentState(
        user_id=str(user.id),
        effective_programming_level=(
            user.effective_programming_level
            if user.effective_programming_level is not None
            else float(user.programming_level)
        ),
        effective_maths_level=(
            user.effective_maths_level
            if user.effective_maths_level is not None
            else float(user.maths_level)
        ),
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                user_message = data.get("content", "").strip()
                session_id_str = data.get("session_id")
            except (json.JSONDecodeError, AttributeError):
                await websocket.send_json(
                    {"type": "error", "message": "Invalid message format"}
                )
                continue

            if not user_message:
                continue

            async with AsyncSessionLocal() as db:
                # Check daily limit (both input and output)
                if not await chat_service.check_daily_limit(db, user.id):
                    await websocket.send_json(
                        {"type": "error", "message": "Daily token limit reached. Try again tomorrow."}
                    )
                    continue

                # Get or create session
                session_id = None
                if session_id_str:
                    try:
                        session_id = uuid_mod.UUID(session_id_str)
                    except ValueError:
                        pass

                session = await chat_service.get_or_create_session(db, user.id, session_id)

                # Save user message and commit early so the REST API
                # can see the session (with preview) when the frontend
                # refreshes the sidebar.
                input_tokens = llm.count_tokens(user_message)
                await chat_service.save_message(
                    db, session.id, "user", user_message, input_tokens=input_tokens
                )
                await db.commit()

                # Now notify the client — the session + message are
                # visible to the GET /api/chat/sessions endpoint.
                await websocket.send_json(
                    {"type": "session", "session_id": str(session.id)}
                )

                # Run pedagogy pipeline
                result = await pedagogy_engine.process_message(
                    user_message, student_state, username=user.username
                )

                # Handle canned responses (greeting / off-topic)
                if result.filter_result:
                    await websocket.send_json({
                        "type": "canned",
                        "content": result.canned_response,
                        "filter": result.filter_result,
                    })
                    await chat_service.save_message(
                        db, session.id, "assistant", result.canned_response
                    )
                    await db.commit()
                    continue

                # Build LLM context
                chat_history = await chat_service.get_chat_history(db, session.id)
                # Remove the message we just saved (it's the current message)
                if chat_history and chat_history[-1]["content"] == user_message:
                    chat_history = chat_history[:-1]

                system_prompt = build_system_prompt(
                    hint_level=result.hint_level,
                    programming_level=round(student_state.effective_programming_level),
                    maths_level=round(student_state.effective_maths_level),
                )

                messages = await build_context_messages(
                    chat_history=chat_history,
                    user_message=user_message,
                    llm=llm,
                    max_context_tokens=settings.llm_max_context_tokens,
                    compression_threshold=settings.context_compression_threshold,
                )

                # Stream LLM response
                full_response = []
                try:
                    async for chunk in llm.generate_stream(
                        system_prompt=system_prompt,
                        messages=messages,
                    ):
                        full_response.append(chunk)
                        await websocket.send_json(
                            {"type": "token", "content": chunk}
                        )
                except LLMError as e:
                    logger.error("LLM error: %s", e)
                    await websocket.send_json(
                        {"type": "error", "message": "AI service temporarily unavailable. Please try again."}
                    )
                    await db.commit()
                    continue

                assistant_text = "".join(full_response)
                output_tokens = llm.count_tokens(assistant_text)

                # Update context embedding with Q+A for same-problem detection
                await pedagogy_engine.update_context_embedding(
                    student_state, user_message, assistant_text
                )

                # Save assistant message
                await chat_service.save_message(
                    db,
                    session.id,
                    "assistant",
                    assistant_text,
                    hint_level_used=result.hint_level,
                    problem_difficulty=result.programming_difficulty,
                    maths_difficulty=result.maths_difficulty,
                    output_tokens=output_tokens,
                )

                # Track both input and output token usage
                await chat_service.increment_token_usage(
                    db, user.id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

                # Update effective levels on user record
                db_user_result = await db.execute(
                    select(User).where(User.id == user.id)
                )
                db_user = db_user_result.scalar_one_or_none()
                if db_user:
                    db_user.effective_programming_level = student_state.effective_programming_level
                    db_user.effective_maths_level = student_state.effective_maths_level

                await db.commit()

                # Send done event
                await websocket.send_json({
                    "type": "done",
                    "hint_level": result.hint_level,
                    "programming_difficulty": result.programming_difficulty,
                    "maths_difficulty": result.maths_difficulty,
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for user %s", user.id)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        try:
            await websocket.send_json({"type": "error", "message": "Internal error"})
            await websocket.close()
        except Exception:
            pass
