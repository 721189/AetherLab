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
    summary="Create an agent",
    description=(
        "Creates an AI agent within a project. The agent carries the model, "
        "temperature, max tokens and system prompt used when driving chat."
    ),
    response_description="Agent created successfully",
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


@router.get(
    "/",
    response_model=List[AgentResponse],
    summary="List agents in a project",
    description="Returns a paginated list of non-archived agents in a project.",
    response_description="A list of the project's agents",
)
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


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Get an agent",
    description="Returns a single agent owned by the authenticated user's project.",
    response_description="The requested agent",
)
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


@router.patch(
    "/{agent_id}",
    response_model=AgentResponse,
    summary="Update an agent",
    description="Updates editable fields (e.g. model, temperature, status) of an agent.",
    response_description="The updated agent",
)
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


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive an agent",
    description=(
        "Soft-deletes an agent by archiving it. Archived agents are hidden from "
        "list/get queries but retained in the database."
    ),
    response_description="Agent archived successfully",
)
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