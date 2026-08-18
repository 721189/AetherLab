from typing import List, Optional

from app.repositories.agent_repository import AgentRepository
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate


class AgentService:
    def __init__(self, db):
        self.db = db
        self.repo = AgentRepository(db)

    def create_agent(
        self,
        data: AgentCreate,
        project_id: int,
    ) -> AgentResponse:
        agent = self.repo.create(
            name=data.name,
            description=data.description,
            model=data.model,
            system_prompt=data.system_prompt,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            configuration=data.configuration,
            project_id=project_id,
            status=data.status or "inactive",
        )
        return AgentResponse.model_validate(agent)

    def get_agent(
        self,
        agent_id: int,
        owner_id: int,
    ) -> Optional[AgentResponse]:
        agent = self.repo.get_by_id(agent_id, owner_id)
        if agent:
            return AgentResponse.model_validate(agent)
        return None

    def get_agents_by_project(
        self,
        project_id: int,
        owner_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[AgentResponse]:
        agents = self.repo.get_all_by_project(project_id, owner_id, skip, limit)
        return [AgentResponse.model_validate(a) for a in agents]

    def update_agent(
        self,
        agent_id: int,
        owner_id: int,
        update_data: AgentUpdate,
    ) -> Optional[AgentResponse]:
        update_kwargs = update_data.model_dump(exclude_unset=True)
        agent = self.repo.update(agent_id, owner_id, **update_kwargs)
        if agent:
            return AgentResponse.model_validate(agent)
        return None

    def archive_agent(
        self,
        agent_id: int,
        owner_id: int,
    ) -> bool:
        return self.repo.archive(agent_id, owner_id)