from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.project import Project


class MessageRepository:
    """Message persistence with conversation-level ownership enforcement.

    Every method threads ``owner_id`` through a ``Message -> Conversation ->
    Project`` join so a caller can never touch a message that lives in another
    user's conversation, even if they guess a foreign conversation/message id.
    """

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        conversation_id: int,
        role: str,
        content: str,
        owner_id: int,
    ) -> Optional[Message]:
        """Create a message inside a conversation the owner actually owns.

        Returns ``None`` when the conversation does not exist, is archived, or
        belongs to a different user — the repository refuses to fabricate a
        message in a conversation the caller has no right to write to.
        """
        owned = (
            self.db.query(Conversation)
            .join(Project)
            .filter(
                Conversation.id == conversation_id,
                Project.owner_id == owner_id,
                Conversation.is_archived.is_(False),
            )
            .first()
        )
        if not owned:
            return None

        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def get_all_by_conversation(
        self,
        conversation_id: int,
        owner_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Message]:
        """Return non-archived messages for a conversation the owner owns."""
        return (
            self.db.query(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .join(Project, Conversation.project_id == Project.id)
            .filter(
                Message.conversation_id == conversation_id,
                Project.owner_id == owner_id,
                Message.is_archived.is_(False),
                Conversation.is_archived.is_(False),
            )
            .order_by(Message.created_at.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_conversation(self, conversation_id: int, owner_id: int) -> int:
        """Total number of non-archived messages the owner can see in a conversation."""
        return (
            self.db.query(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .join(Project, Conversation.project_id == Project.id)
            .filter(
                Message.conversation_id == conversation_id,
                Project.owner_id == owner_id,
                Message.is_archived.is_(False),
                Conversation.is_archived.is_(False),
            )
            .count()
        )

    def archive(
        self,
        message_id: int,
        conversation_id: int,
        owner_id: int,
    ) -> bool:
        """Soft-delete a message, verifying it belongs to an owned conversation.

        Returns True when the message exists, lives in the given conversation,
        and that conversation belongs to ``owner_id``. A message in another
        user's conversation (or another conversation of the same owner) is
        never touched.
        """
        msg = (
            self.db.query(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .join(Project, Conversation.project_id == Project.id)
            .filter(
                Message.id == message_id,
                Message.conversation_id == conversation_id,
                Project.owner_id == owner_id,
            )
            .first()
        )
        if not msg:
            return False
        msg.is_archived = True
        self.db.commit()
        return True