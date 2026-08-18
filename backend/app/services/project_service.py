from typing import List, Optional

from app.repositories.project_repository import ProjectRepository
from app.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)


class ProjectService:
    def __init__(self, db):
        self.db = db
        self.repo = ProjectRepository(db)

    def create_project(
        self,
        owner_id: int,
        project_data: ProjectCreate,
    ) -> ProjectResponse:
        project = self.repo.create(
            name=project_data.name,
            description=project_data.description,
            owner_id=owner_id,
        )
        return ProjectResponse.model_validate(project)

    def get_project(
        self,
        project_id: int,
        owner_id: int,
    ) -> Optional[ProjectResponse]:
        project = self.repo.get_by_id(project_id, owner_id)
        if project:
            return ProjectResponse.model_validate(project)
        return None

    def get_all_projects(
        self,
        owner_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ProjectResponse]:
        projects = self.repo.get_all_by_owner(owner_id, skip, limit)
        return [ProjectResponse.model_validate(p) for p in projects]

    def update_project(
        self,
        project_id: int,
        owner_id: int,
        update_data: ProjectUpdate,
    ) -> Optional[ProjectResponse]:
        update_kwargs = update_data.model_dump(exclude_unset=True)
        project = self.repo.update(project_id, owner_id, **update_kwargs)
        if project:
            return ProjectResponse.model_validate(project)
        return None

    def delete_project(
        self,
        project_id: int,
        owner_id: int,
    ) -> bool:
        return self.repo.delete(project_id, owner_id)