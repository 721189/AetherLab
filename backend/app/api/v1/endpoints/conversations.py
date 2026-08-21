import json
from typing import Iterator, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
)
from app.schemas.message import MessageCreate
from app.services.conversation_service import ConversationService
from app.services.project_service import ProjectService

router = APIRouter(
    prefix="/projects/{project_id}/conversations",
    tags=["Conversations"],
)


@router.post(
    "/",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    project_id: int,
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify project ownership.
    project_service = ProjectService(db)
    if not project_service.get_project(project_id, current_user.id):
        raise HTTPException(status_code=404, detail="Project not found")

    service = ConversationService(db)
    return service.create_conversation(project_id, current_user.id, data)


@router.get("/", response_model=List[ConversationResponse])
def list_conversations(
    project_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project_service = ProjectService(db)
    if not project_service.get_project(project_id, current_user.id):
        raise HTTPException(status_code=404, detail="Project not found")

    service = ConversationService(db)
    return service.list_conversations(project_id, current_user.id, skip, limit)


@router.get("/{conv_id}", response_model=ConversationResponse)
def get_conversation(
    project_id: int,
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ConversationService(db)
    conv = service.get_conversation(conv_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.patch("/{conv_id}", response_model=ConversationResponse)
def update_conversation(
    project_id: int,
    conv_id: int,
    data: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ConversationService(db)
    conv = service.update_conversation(conv_id, current_user.id, data)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    project_id: int,
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ConversationService(db)
    deleted = service.delete_conversation(conv_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return None


@router.post("/{conv_id}/messages", response_model=dict)
def send_message(
    project_id: int,
    conv_id: int,
    message_data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ConversationService(db)

    # Ensure the conversation exists and is owned by the caller.
    if not service.get_conversation(conv_id, current_user.id):
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = service.send_message(
        conv_id, current_user.id, message_data.content, message_data.agent_id
    )
    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return result


@router.get("/{conv_id}/messages")
def list_messages(
    project_id: int,
    conv_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a paginated slice of a conversation's messages (oldest first).

    Responds with ``{"data": [...], "pagination": {"total", "skip", "limit",
    "next", "prev"}}``. The window is bounded by ``skip``/``limit`` so a
    conversation with thousands of messages never hydrates the entire history
    in one request.
    """
    service = ConversationService(db)
    messages = service.list_messages(conv_id, current_user.id, skip, limit)
    if messages is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return messages


@router.post("/{conv_id}/messages/stream")
def stream_message(
    project_id: int,
    conv_id: int,
    message_data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream the assistant reply as Server-Sent Events.

    The client receives one ``data`` line per token/chunk, plus a final
    ``data: [DONE]`` line. Ownership is asserted up front so non-owners get a
    404 instead of an empty 200 stream.
    """
    service = ConversationService(db)
    # Eager ownership check: fail fast with a 404 for non-owners.
    if not service.get_conversation(conv_id, current_user.id):
        raise HTTPException(status_code=404, detail="Conversation not found")

    exchange_stream = service.stream_chat(
        conv_id, current_user.id, message_data.content, message_data.agent_id
    )

    def event_stream() -> Iterator[str]:
        try:
            for chunk in exchange_stream:
                payload = json.dumps({"delta": chunk})
                yield f"data: {payload}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )