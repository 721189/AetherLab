from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.project import Project


class AgentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        name: str,
        description: Optional[str],
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
        configuration: Optional[dict],
        project_id: int,
        status: str = "inactive",
    ) -> Agent:
        agent = Agent(
            name=name,
            description=description,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            configuration=configuration or {},
            project_id=project_id,
            status=status,
        )
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def get_by_id(
        self,
        agent_id: int,
        owner_id: int,
    ) -> Optional[Agent]:
        """Get an agent by ID, verifying ownership via its project."""
        return (
            self.db.query(Agent)
            .join(Project)
            .filter(
                Agent.id == agent_id,
                Project.owner_id == owner_id,
                Agent.status != "archived",
            )
            .first()
        )

    def get_all_by_project(
        self,
        project_id: int,
        owner_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Agent]:
        """List agents in a project (verifying ownership)."""
        return (
            self.db.query(Agent)
            .join(Project)
            .filter(
                Project.id == project_id,
                Project.owner_id == owner_id,
                Agent.status != "archived",
            )
            .order_by(Agent.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(
        self,
        agent_id: int,
        owner_id: int,
        **kwargs,
    ) -> Optional[Agent]:
        """Update an agent, verifying ownership."""
        agent = self.get_by_id(agent_id, owner_id)
        if not agent:
            return None

        for key, value in kwargs.items():
            if hasattr(agent, key) and value is not None:
                setattr(agent, key, value)

        self.db.commit()
        self.db.refresh(agent)
        return agent

    def archive(self, agent_id: int, owner_id: int) -> bool:
        """Soft-delete an agent by archiving it."""
        agent = (
            self.db.query(Agent)
            .join(Project)
            .filter(
                Agent.id == agent_id,
                Project.owner_id == owner_id,
            )
            .first()
        )
        if not agent:
            return False

        agent.status = "archived"
        self.db.commit()
        return True