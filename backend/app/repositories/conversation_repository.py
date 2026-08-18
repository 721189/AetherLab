from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.project import Project


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        title: Optional[str],
        project_id: int,
    ) -> Conversation:
        conv = Conversation(title=title, project_id=project_id)
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def get_by_id(
        self,
        conv_id: int,
        owner_id: int,
    ) -> Optional[Conversation]:
        """Get a conversation by ID, verifying ownership via its project."""
        return (
            self.db.query(Conversation)
            .join(Project)
            .filter(
                Conversation.id == conv_id,
                Project.owner_id == owner_id,
            )
            .first()
        )

    def get_all_by_project(
        self,
        project_id: int,
        owner_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Conversation]:
        """List conversations in a project (verifying ownership)."""
        return (
            self.db.query(Conversation)
            .join(Project)
            .filter(
                Conversation.project_id == project_id,
                Project.owner_id == owner_id,
            )
            .order_by(Conversation.updated_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(
        self,
        conv_id: int,
        owner_id: int,
        **kwargs,
    ) -> Optional[Conversation]:
        """Update a conversation, verifying ownership."""
        conv = self.get_by_id(conv_id, owner_id)
        if not conv:
            return None

        for key, value in kwargs.items():
            if hasattr(conv, key):
                setattr(conv, key, value)

        self.db.commit()
        self.db.refresh(conv)
        return conv

    def delete(self, conv_id: int, owner_id: int) -> bool:
        conv = self.get_by_id(conv_id, owner_id)
        if not conv:
            return False
        self.db.delete(conv)
        self.db.commit()
        return True