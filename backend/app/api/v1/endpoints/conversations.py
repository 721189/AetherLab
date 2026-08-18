from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
)
from app.schemas.message import MessageCreate, MessageResponse
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

    result = service.send_message(conv_id, current_user.id, message_data.content)
    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return result