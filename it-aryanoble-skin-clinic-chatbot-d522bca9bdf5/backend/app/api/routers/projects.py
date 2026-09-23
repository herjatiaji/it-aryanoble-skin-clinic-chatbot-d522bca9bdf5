from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional
import uuid
from datetime import datetime, timezone

from app.core.database import get_db
from app.api.dependencies import RequireAccess
from app.models.user import User
from app.models.project import Project
from app.models.knowledge import Knowledge
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectStatsResponse, ProjectDetailResponse
from app.schemas.knowledge import KnowledgeResponse

router = APIRouter(tags=["Projects"])

@router.get("/stats", response_model=ProjectStatsResponse)
async def get_project_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireAccess("knowledge:read"))
):
    """Return overview counts of active projects and knowledge records."""
    total_projects_stmt = select(func.count(Project.id)).where(Project.deleted_at.is_(None))
    total_projects = (await db.execute(total_projects_stmt)).scalar() or 0

    total_knowledge_stmt = select(func.count(Knowledge.id)).where(Knowledge.deleted_at.is_(None))
    total_knowledge = (await db.execute(total_knowledge_stmt)).scalar() or 0

    return ProjectStatsResponse(
        total_projects=total_projects,
        total_knowledge=total_knowledge
    )

from app.schemas.pagination import PaginatedResponse
from typing import List, Optional, Union
import math

@router.get("/", response_model=Union[PaginatedResponse[ProjectResponse], List[ProjectResponse]])
async def list_projects(
    search: Optional[str] = Query(None, description="Search query for project name"),
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireAccess("knowledge:read"))
):
    """List all active projects with knowledge item counts."""
    query = (
        select(
            Project,
            func.count(Knowledge.id).label("total_knowledges")
        )
        .outerjoin(Knowledge, and_(Knowledge.project_id == Project.id, Knowledge.deleted_at.is_(None)))
        .where(Project.deleted_at.is_(None))
        .group_by(Project.id)
        .order_by(Project.created_at.desc())
    )

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        query = query.where(Project.name.ilike(search_term))

    if page is not None:
        p_size = page_size or 10
        count_stmt = select(func.count()).select_from(query.subquery())
        count_res = await db.execute(count_stmt)
        total = count_res.scalar() or 0
        total_pages = max(1, math.ceil(total / p_size))

        paginated_query = query.offset((page - 1) * p_size).limit(p_size)
        result = await db.execute(paginated_query)
        rows = result.all()

        responses: List[ProjectResponse] = []
        for project, count in rows:
            responses.append(ProjectResponse(
                id=project.id,
                name=project.name,
                description=project.description,
                created_by=project.created_by,
                total_knowledges=count,
                created_at=project.created_at,
                updated_at=project.updated_at
            ))

        return PaginatedResponse[ProjectResponse](
            items=responses,
            total=total,
            page=page,
            page_size=p_size,
            total_pages=total_pages
        )

    result = await db.execute(query)
    rows = result.all()

    responses: List[ProjectResponse] = []
    for project, count in rows:
        responses.append(ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            created_by=project.created_by,
            total_knowledges=count,
            created_at=project.created_at,
            updated_at=project.updated_at
        ))

    return responses

@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_in: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireAccess("knowledge:write"))
):
    """Create a new project workspace."""
    # Check if active project with same name already exists
    existing_stmt = select(Project).where(
        Project.name == project_in.name.strip(),
        Project.deleted_at.is_(None)
    )
    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="A project with this name already exists")

    project = Project(
        name=project_in.name.strip(),
        description=project_in.description.strip() if project_in.description else None,
        created_by=current_user.id
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_by=project.created_by,
        total_knowledges=0,
        created_at=project.created_at,
        updated_at=project.updated_at
    )

@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project_detail(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireAccess("knowledge:read"))
):
    """Get project details and its associated knowledge records."""
    stmt = select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    knowledge_stmt = select(Knowledge).where(
        Knowledge.project_id == project_id,
        Knowledge.deleted_at.is_(None)
    ).order_by(Knowledge.created_at.desc())
    knowledges_res = await db.execute(knowledge_stmt)
    knowledges = list(knowledges_res.scalars().all())

    return ProjectDetailResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_by=project.created_by,
        total_knowledges=len(knowledges),
        created_at=project.created_at,
        updated_at=project.updated_at,
        knowledges=[KnowledgeResponse.model_validate(k) for k in knowledges]
    )

@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    project_in: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireAccess("knowledge:write"))
):
    """Update a project's name or description."""
    stmt = select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = project_in.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"]:
        new_name = update_data["name"].strip()
        if new_name != project.name:
            check_stmt = select(Project).where(
                Project.name == new_name,
                Project.id != project_id,
                Project.deleted_at.is_(None)
            )
            if (await db.execute(check_stmt)).scalar_one_or_none():
                raise HTTPException(status_code=400, detail="A project with this name already exists")
            project.name = new_name

    if "description" in update_data:
        project.description = update_data["description"].strip() if update_data["description"] else None

    await db.commit()
    await db.refresh(project)

    # Get count
    count_stmt = select(func.count(Knowledge.id)).where(Knowledge.project_id == project_id, Knowledge.deleted_at.is_(None))
    count = (await db.execute(count_stmt)).scalar() or 0

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_by=project.created_by,
        total_knowledges=count,
        created_at=project.created_at,
        updated_at=project.updated_at
    )

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireAccess("knowledge:write"))
):
    """Soft delete a project."""
    stmt = select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from sqlalchemy import update
    project.deleted_at = datetime.now(timezone.utc)
    await db.execute(
        update(Knowledge).where(Knowledge.project_id == project_id).values(project_id=None)
    )
    await db.commit()
