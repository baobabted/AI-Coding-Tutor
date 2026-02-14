import base64
import json
import logging
import uuid as uuid_mod
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context_builder import build_context_messages, build_system_prompt
from app.ai.embedding_service import EmbeddingService
from app.ai.llm_base import LLMError, LLMProvider
from app.ai.llm_factory import get_llm_provider
from app.ai.pedagogy_engine import PedagogyEngine, StudentState
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.dependencies import get_current_user, get_db
from app.models.chat import UploadedFile
from app.models.user import User
from app.schemas.chat import TokenUsageOut
from app.services import chat_service
from app.services.auth_service import decode_token
from app.services.upload_service import get_upload_slot_limits, get_user_uploads_by_ids

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


def _parse_upload_ids(raw_upload_ids: Any) -> list[uuid_mod.UUID]:
    if not isinstance(raw_upload_ids, list):
        return []

    parsed: list[uuid_mod.UUID] = []
    max_items = settings.upload_max_images_per_message + settings.upload_max_documents_per_message
    for raw_id in raw_upload_ids[:max_items]:
        try:
            parsed.append(uuid_mod.UUID(str(raw_id)))
        except ValueError:
            continue
    return parsed


def _validate_upload_mix(
    image_uploads: list[UploadedFile],
    document_uploads: list[UploadedFile],
) -> None:
    max_images, max_documents = get_upload_slot_limits()
    if len(image_uploads) > max_images or len(document_uploads) > max_documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Too many files. You can upload up to {max_images} photos and "
                f"{max_documents} files per message."
            ),
        )


def _split_uploads(
    uploads: list[UploadedFile],
) -> tuple[list[UploadedFile], list[UploadedFile]]:
    image_uploads: list[UploadedFile] = []
    document_uploads: list[UploadedFile] = []
    for item in uploads:
        if item.file_type == "image":
            image_uploads.append(item)
        else:
            document_uploads.append(item)
    return image_uploads, document_uploads


def _build_enriched_message(
    user_message: str,
    document_uploads: list[UploadedFile],
) -> str:
    clean_user_text = user_message.strip()
    parts: list[str] = []
    if clean_user_text:
        parts.append(clean_user_text)

    for document in document_uploads:
        if not document.extracted_text:
            continue
        parts.append(f"[Attached document: {document.original_filename}]\n{document.extracted_text}")

    if not parts:
        return "Please analyse the attached files."
    return "\n\n".join(parts)


def _build_multimodal_user_parts(
    enriched_user_message: str,
    image_uploads: list[UploadedFile],
) -> list[dict[str, str]]:
    parts: list[dict[str, str]] = [{"type": "text", "text": enriched_user_message}]

    for image in image_uploads:
        image_path = Path(image.storage_path)
        if not image_path.exists():
            continue
        image_bytes = image_path.read_bytes()
        b64_data = base64.b64encode(image_bytes).decode("ascii")
        parts.append(
            {
                "type": "image",
                "media_type": image.content_type,
                "data": b64_data,
            }
        )
    return parts


async def _build_combined_embedding(
    embedding_service: EmbeddingService,
    enriched_user_message: str,
    image_uploads: list[UploadedFile],
) -> list[float] | None:
    vectors: list[list[float]] = []

    text_embedding = await embedding_service.embed_text(enriched_user_message)
    if text_embedding:
        vectors.append(text_embedding)

    for image in image_uploads:
        image_path = Path(image.storage_path)
        if not image_path.exists():
            continue
        image_bytes = image_path.read_bytes()
        image_embedding = await embedding_service.embed_image(
            image_bytes, image.content_type
        )
        if image_embedding:
            vectors.append(image_embedding)

    return embedding_service.combine_embeddings(vectors)


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
    if messages is None:
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
    output_pct = (
        (usage.output_tokens_used / output_limit * 100) if output_limit > 0 else 0
    )
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
    """WebSocket endpoint for the chat pipeline."""
    user = await _authenticate_ws(token)
    if not user:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    await websocket.accept()

    try:
        llm = get_llm_provider(settings)
        embedding_service, pedagogy_engine = await _get_services(llm)
    except Exception as exc:
        logger.error("Failed to initialise AI services: %s", exc)
        await websocket.send_json({"type": "error", "message": "Service unavailable"})
        await websocket.close()
        return

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
                user_message = str(data.get("content", "")).strip()
                session_id_str = data.get("session_id")
                raw_upload_ids = data.get("upload_ids", [])
                max_items = (
                    settings.upload_max_images_per_message
                    + settings.upload_max_documents_per_message
                )
                if (
                    isinstance(raw_upload_ids, list)
                    and len(raw_upload_ids) > max_items
                ):
                    max_images, max_documents = get_upload_slot_limits()
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": (
                                f"Too many files. You can upload up to {max_images} photos "
                                f"and {max_documents} files per message."
                            ),
                        }
                    )
                    continue
                upload_ids = _parse_upload_ids(raw_upload_ids)
                if isinstance(raw_upload_ids, list) and len(upload_ids) != len(raw_upload_ids):
                    await websocket.send_json(
                        {"type": "error", "message": "Invalid attachment reference format."}
                    )
                    continue
            except (json.JSONDecodeError, AttributeError, TypeError):
                await websocket.send_json(
                    {"type": "error", "message": "Invalid message format"}
                )
                continue

            if not user_message and not upload_ids:
                continue

            async with AsyncSessionLocal() as db:
                if not await chat_service.check_daily_limit(db, user.id):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Daily token limit reached. Try again tomorrow.",
                        }
                    )
                    continue

                session_id = None
                if session_id_str:
                    try:
                        session_id = uuid_mod.UUID(str(session_id_str))
                    except ValueError:
                        session_id = None

                uploads = await get_user_uploads_by_ids(db, user.id, upload_ids)
                if len(uploads) != len(upload_ids):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "One or more attachments are invalid, expired, or inaccessible.",
                        }
                    )
                    continue

                image_uploads, document_uploads = _split_uploads(uploads)
                try:
                    _validate_upload_mix(image_uploads, document_uploads)
                except HTTPException as exc:
                    await websocket.send_json(
                        {"type": "error", "message": str(exc.detail)}
                    )
                    continue
                enriched_user_message = _build_enriched_message(
                    user_message, document_uploads
                )
                input_tokens = llm.count_tokens(enriched_user_message) + (
                    len(image_uploads) * 512
                )
                if input_tokens > settings.llm_max_user_input_tokens:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": (
                                "Files are too large for one message. "
                                "Please split them and try again."
                            ),
                        }
                    )
                    continue

                combined_embedding = await _build_combined_embedding(
                    embedding_service, enriched_user_message, image_uploads
                )

                session = await chat_service.get_or_create_session(db, user.id, session_id)

                stored_user_content = user_message if user_message else "Sent attachments."
                await chat_service.save_message(
                    db,
                    session.id,
                    "user",
                    stored_user_content,
                    input_tokens=input_tokens,
                    attachment_ids=[str(item.id) for item in uploads],
                )
                await db.commit()

                await websocket.send_json(
                    {"type": "session", "session_id": str(session.id)}
                )

                result = await pedagogy_engine.process_message(
                    enriched_user_message,
                    student_state,
                    username=user.username,
                    embedding_override=combined_embedding,
                    # Attachments are always task context, so skip greeting/off-topic filters.
                    enable_topic_filters=not bool(uploads),
                )

                if result.filter_result:
                    await websocket.send_json(
                        {
                            "type": "canned",
                            "content": result.canned_response,
                            "filter": result.filter_result,
                        }
                    )
                    await chat_service.save_message(
                        db, session.id, "assistant", result.canned_response or ""
                    )
                    await db.commit()
                    continue

                chat_history = await chat_service.get_chat_history(db, session.id)
                if chat_history:
                    chat_history = chat_history[:-1]

                system_prompt = build_system_prompt(
                    hint_level=result.hint_level or 1,
                    programming_level=round(student_state.effective_programming_level),
                    maths_level=round(student_state.effective_maths_level),
                )

                messages = await build_context_messages(
                    chat_history=chat_history,
                    user_message=enriched_user_message,
                    llm=llm,
                    max_context_tokens=settings.llm_max_context_tokens,
                    compression_threshold=settings.context_compression_threshold,
                )
                if image_uploads and messages:
                    messages[-1] = {
                        "role": "user",
                        "content": _build_multimodal_user_parts(
                            enriched_user_message, image_uploads
                        ),
                    }

                full_response: list[str] = []
                try:
                    async for chunk in llm.generate_stream(
                        system_prompt=system_prompt,
                        messages=messages,
                    ):
                        full_response.append(chunk)
                        await websocket.send_json({"type": "token", "content": chunk})
                except LLMError as exc:
                    logger.error("LLM error: %s", exc)
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "AI service temporarily unavailable. Please try again.",
                        }
                    )
                    await db.commit()
                    continue

                assistant_text = "".join(full_response)
                output_tokens = llm.count_tokens(assistant_text)

                await pedagogy_engine.update_context_embedding(
                    student_state,
                    enriched_user_message,
                    assistant_text,
                    question_embedding=combined_embedding,
                )

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

                await chat_service.increment_token_usage(
                    db, user.id, input_tokens=input_tokens, output_tokens=output_tokens
                )

                db_user_result = await db.execute(select(User).where(User.id == user.id))
                db_user = db_user_result.scalar_one_or_none()
                if db_user:
                    db_user.effective_programming_level = (
                        student_state.effective_programming_level
                    )
                    db_user.effective_maths_level = student_state.effective_maths_level

                await db.commit()

                await websocket.send_json(
                    {
                        "type": "done",
                        "hint_level": result.hint_level,
                        "programming_difficulty": result.programming_difficulty,
                        "maths_difficulty": result.maths_difficulty,
                    }
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for user %s", user.id)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": "Internal error"})
            await websocket.close()
        except Exception:
            pass
