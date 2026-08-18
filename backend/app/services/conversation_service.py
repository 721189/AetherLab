from datetime import datetime, timezone
from typing import List, Optional

from app.ai.factory import get_llm_provider
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
)
from app.schemas.message import MessageResponse

DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant."


class ConversationService:
    def __init__(self, db):
        self.db = db
        self.conv_repo = ConversationRepository(db)
        self.msg_repo = MessageRepository(db)

    def create_conversation(
        self,
        project_id: int,
        owner_id: int,
        data: ConversationCreate,
    ) -> ConversationResponse:
        conv = self.conv_repo.create(data.title, project_id)
        return ConversationResponse.model_validate(conv)

    def get_conversation(
        self,
        conv_id: int,
        owner_id: int,
    ) -> Optional[ConversationResponse]:
        conv = self.conv_repo.get_by_id(conv_id, owner_id)
        if conv:
            return ConversationResponse.model_validate(conv)
        return None

    def list_conversations(
        self,
        project_id: int,
        owner_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ConversationResponse]:
        convs = self.conv_repo.get_all_by_project(project_id, owner_id, skip, limit)
        return [ConversationResponse.model_validate(c) for c in convs]

    def update_conversation(
        self,
        conv_id: int,
        owner_id: int,
        data: ConversationUpdate,
    ) -> Optional[ConversationResponse]:
        update_kwargs = data.model_dump(exclude_unset=True)
        conv = self.conv_repo.update(conv_id, owner_id, **update_kwargs)
        if conv:
            return ConversationResponse.model_validate(conv)
        return None

    def delete_conversation(
        self,
        conv_id: int,
        owner_id: int,
    ) -> bool:
        return self.conv_repo.delete(conv_id, owner_id)

    def send_message(
        self,
        conv_id: int,
        owner_id: int,
        content: str,
        agent_model: str = "gpt-4o",
    ) -> Optional[dict]:
        """Persist the user message, query the LLM, persist the assistant reply,
        and return the exchange. Returns None if the conversation is not owned
        by the caller.
        """
        conv = self.conv_repo.get_by_id(conv_id, owner_id)
        if not conv:
            return None

        # Save the user message.
        user_msg = self.msg_repo.create(conv_id, "user", content)

        # Build the history to send to the LLM.
        history = self.msg_repo.get_all_by_conversation(conv_id, limit=50)
        messages = [{"role": m.role, "content": m.content} for m in history]

        # Call the configured LLM provider.
        provider = get_llm_provider(agent_model)
        response_text = provider.generate_response(
            messages=messages,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            temperature=0.7,
        )

        # Persist the assistant reply.
        assistant_msg = self.msg_repo.create(conv_id, "assistant", response_text)

        # Bump the conversation timestamp.
        conv.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        return {
            "user_message": MessageResponse.model_validate(user_msg),
            "assistant_message": MessageResponse.model_validate(assistant_msg),
        }