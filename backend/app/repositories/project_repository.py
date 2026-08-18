from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.project import Project


class ProjectRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        name: str,
        description: Optional[str],
        owner_id: int,
    ) -> Project:
        project = Project(
            name=name,
            description=description,
            owner_id=owner_id,
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def get_by_id(
        self,
        project_id: int,
        owner_id: int,
    ) -> Optional[Project]:
        return (
            self.db.query(Project)
            .filter(
                Project.id == project_id,
                Project.owner_id == owner_id,
                Project.is_archived.is_(False),
            )
            .first()
        )

    def get_all_by_owner(
        self,
        owner_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Project]:
        return (
            self.db.query(Project)
            .filter(
                Project.owner_id == owner_id,
                Project.is_archived.is_(False),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(
        self,
        project_id: int,
        owner_id: int,
        **kwargs,
    ) -> Optional[Project]:
        project = self.get_by_id(project_id, owner_id)
        if not project:
            return None

        for key, value in kwargs.items():
            if hasattr(project, key) and value is not None:
                setattr(project, key, value)

        self.db.commit()
        self.db.refresh(project)
        return project

    def delete(self, project_id: int, owner_id: int) -> bool:
        project = (
            self.db.query(Project)
            .filter(
                Project.id == project_id,
                Project.owner_id == owner_id,
            )
            .first()
        )
        if not project:
            return False

        # Soft delete by archiving.
        project.is_archived = True
        self.db.commit()
        return True