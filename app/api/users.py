import csv
from io import StringIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import permission_required
from app.db.session import get_session
from app.models import KPIInstance, Role, User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(
    role: str | None = None,
    status: str | None = None,
    month: str | None = None,
    kpi_status: str | None = None,
    search: str | None = None,
    sort: str = "id",
    order: str = "asc",
    page: int = 1,
    size: int = 20,
    _: User = Depends(permission_required("users:view")),
    session: AsyncSession = Depends(get_session),
):
    q = select(User).distinct()
    if role:
        q = q.join(User.roles).where(Role.name == role)
    if status:
        q = q.where(User.status == status)
    if search:
        like = f"%{search}%"
        q = q.where(or_(User.username.ilike(like), User.full_name.ilike(like), User.telegram_id.cast(User.username.type).ilike(like)))
    if month or kpi_status:
        q = q.join(KPIInstance, KPIInstance.employee_id == User.id)
        if month:
            q = q.where(KPIInstance.month == month)
        if kpi_status:
            q = q.where(KPIInstance.status == kpi_status)

    order_column = getattr(User, sort, User.id)
    q = q.order_by(order_column.asc() if order == "asc" else order_column.desc())
    q = q.offset((page - 1) * size).limit(size)

    users = (await session.execute(q)).scalars().all()
    return [
        {"id": u.id, "username": u.username, "full_name": u.full_name, "telegram_id": u.telegram_id, "status": u.status.value}
        for u in users
    ]


@router.get("/export/csv")
async def export_users_csv(
    status: str | None = None,
    _: User = Depends(permission_required("users:export")),
    session: AsyncSession = Depends(get_session),
):
    q = select(User)
    if status:
        q = q.where(User.status == status)
    users = (await session.execute(q)).scalars().all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "username", "full_name", "telegram_id", "status"])
    for u in users:
        writer.writerow([u.id, u.username, u.full_name, u.telegram_id, u.status.value])

    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=users.csv"})
