from typing import List

from sqlalchemy.orm import Session

from app.models.message import Message


class MessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        conversation_id: int,
        role: str,
        content: str,
    ) -> Message:
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
        skip: int = 0,
        limit: int = 100,
    ) -> List[Message]:
        """Return non-archived messages for a conversation, oldest->newest."""
        return (
            self.db.query(Message)
            .filter(
                Message.conversation_id == conversation_id,
                Message.is_archived.is_(False),
            )
            .order_by(Message.created_at.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_conversation(self, conversation_id: int) -> int:
        """Total number of non-archived messages in a conversation."""
        return (
            self.db.query(Message)
            .filter(
                Message.conversation_id == conversation_id,
                Message.is_archived.is_(False),
            )
            .count()
        )

    def archive(self, message_id: int) -> bool:
        """Soft-delete a message by setting ``is_archived``.

        Returns True when a message with the given ID was found and archived.
        """
        msg = (
            self.db.query(Message)
            .filter(Message.id == message_id)
            .first()
        )
        if not msg:
            return False
        msg.is_archived = True
        self.db.commit()
        return True