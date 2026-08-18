from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate
from app.services.agent_service import AgentService
from app.services.project_service import ProjectService

router = APIRouter(
    prefix="/projects/{project_id}/agents",
    tags=["Agents"],
)


@router.post(
    "/",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agent(
    project_id: int,
    agent_data: AgentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify project ownership before creating the agent.
    project_service = ProjectService(db)
    project = project_service.get_project(project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    service = AgentService(db)
    return service.create_agent(agent_data, project_id)


@router.get("/", response_model=List[AgentResponse])
def list_agents(
    project_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify project ownership.
    project_service = ProjectService(db)
    project = project_service.get_project(project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    service = AgentService(db)
    return service.get_agents_by_project(project_id, current_user.id, skip, limit)


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(
    project_id: int,
    agent_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AgentService(db)
    agent = service.get_agent(agent_id, current_user.id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse)
def update_agent(
    project_id: int,
    agent_id: int,
    update_data: AgentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AgentService(db)
    agent = service.update_agent(agent_id, current_user.id, update_data)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_agent(
    project_id: int,
    agent_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = AgentService(db)
    archived = service.archive_agent(agent_id, current_user.id)
    if not archived:
        raise HTTPException(status_code=404, detail="Agent not found")
    return None