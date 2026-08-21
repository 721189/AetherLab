from datetime import datetime, timezone
from typing import Iterator, List, Optional

from app.ai.factory import get_llm_provider
from app.exceptions import NotFoundError
from app.repositories.agent_repository import AgentRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
)
from app.schemas.message import MessageResponse

DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant."
DEFAULT_MODEL = "gpt-4o"
DEFAULT_TEMPERATURE = 0.7


class ConversationService:
    def __init__(self, db):
        self.db = db
        self.conv_repo = ConversationRepository(db)
        self.msg_repo = MessageRepository(db)
        self.agent_repo = AgentRepository(db)

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

    def _resolve_llm_config(
        self,
        agent_id: Optional[int],
        owner_id: int,
        project_id: int,
    ) -> tuple:
        """Resolve the LLM call parameters used for a message.

        When ``agent_id`` is provided the agent's stored configuration (model,
        system prompt, temperature, max tokens) is used. Otherwise the provider
        factory defaults are left untouched (``model=None``) so behaviour is
        unchanged for conversations without an agent. A missing, unowned or
        cross-project agent raises :class:`NotFoundError`.
        """
        if agent_id is None:
            return None, DEFAULT_SYSTEM_PROMPT, DEFAULT_TEMPERATURE, None

        agent = self.agent_repo.get_by_id(agent_id, owner_id)
        if agent is None or agent.project_id != project_id:
            raise NotFoundError(detail="Agent not found")

        model = agent.model or DEFAULT_MODEL
        temperature = (
            agent.temperature
            if agent.temperature is not None
            else DEFAULT_TEMPERATURE
        )
        max_tokens = agent.max_tokens
        system_prompt = agent.system_prompt or DEFAULT_SYSTEM_PROMPT
        return model, system_prompt, temperature, max_tokens

    def send_message(
        self,
        conv_id: int,
        owner_id: int,
        content: str,
        agent_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Persist the user message, query the LLM, persist the assistant reply,
        and return the exchange. Returns None if the conversation is not owned
        by the caller.

        ``agent_id`` optionally selects an agent whose stored configuration
        (model, system prompt, temperature, max tokens) drives the LLM call.
        When omitted the provider factory resolves the configured default (free
        Nemotron via OpenRouter when available).
        """
        conv = self.conv_repo.get_by_id(conv_id, owner_id)
        if not conv:
            return None

        model, system_prompt, temperature, max_tokens = self._resolve_llm_config(
            agent_id, owner_id, conv.project_id
        )

        # Save the user message.
        user_msg = self.msg_repo.create(conv_id, "user", content)

        # Build the history to send to the LLM.
        history = self.msg_repo.get_all_by_conversation(conv_id, limit=50)
        messages = [{"role": m.role, "content": m.content} for m in history]

        # Call the configured LLM provider with the resolved agent config.
        provider = get_llm_provider(model)
        response_text = provider.generate_response(
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
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

    def list_messages(
        self,
        conv_id: int,
        owner_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> Optional[List[MessageResponse]]:
        """Return a paginated slice of messages for a conversation owned by
        ``owner_id``. The newest messages are at the end of the list.

        Returns ``None`` when the conversation is missing or not owned by the
        caller, allowing the endpoint to return a 404 without leaking
        existence.
        """
        conv = self.conv_repo.get_by_id(conv_id, owner_id)
        if not conv:
            return None
        msgs = self.msg_repo.get_all_by_conversation(conv_id, skip, limit)
        return [MessageResponse.model_validate(m) for m in msgs]

    def stream_chat(
        self,
        conv_id: int,
        owner_id: int,
        content: str,
        agent_id: Optional[int] = None,
    ) -> Iterator[str]:
        """Stream an assistant reply token-by-token.

        Ownership and (when ``agent_id`` is supplied) the agent config are
        resolved eagerly — before the returned generator is iterated — so a
        non-owner or missing agent produces a 404 rather than a broken 200
        stream. The generator itself persists the user message, builds the
        message history, delegates to the provider's ``stream_response`` and,
        once the stream completes (or the client disconnects), persists the
        assistant reply and bumps the conversation timestamp.
        """
        conv = self.conv_repo.get_by_id(conv_id, owner_id)
        if not conv:
            return

        model, system_prompt, temperature, max_tokens = self._resolve_llm_config(
            agent_id, owner_id, conv.project_id
        )

        # Persist the user message immediately so it is part of the history
        # the provider receives.
        self.msg_repo.create(conv_id, "user", content)

        # Build the history (now includes the user message) bounded to a sane
        # window so large conversations don't blow past token limits.
        history = self.msg_repo.get_all_by_conversation(conv_id, limit=50)
        messages = [{"role": m.role, "content": m.content} for m in history]

        def _inner() -> Iterator[str]:
            provider = get_llm_provider(model)
            collected: List[str] = []
            try:
                for chunk in provider.stream_response(
                    messages=messages,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    collected.append(chunk)
                    yield chunk
            finally:
                # Persist the assistant reply (even on early client disconnect,
                # best-effort) so the conversation history stays consistent.
                text = "".join(collected)
                if text:
                    self.msg_repo.create(conv_id, "assistant", text)
                    conv = self.conv_repo.get_by_id(conv_id, owner_id)
                    if conv:
                        conv.updated_at = datetime.now(timezone.utc)
                        self.db.commit()

        return _inner()