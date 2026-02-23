from datetime import datetime, timezone
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import permission_required
from app.db.session import get_session
from app.models import KPIDispute, KPIInstance, KPIInstanceMetric, KPIShareLink, KPIStatus, User
from app.schemas.kpi import DisputeCreate, KPIInstanceCreate, KPIShareLinkCreate
from app.services.audit import audit_log
from app.services.export import render_kpi_pdf, render_kpi_xlsx, render_zip
from app.services.kpi_engine import calculate_instance
from app.services.telegram import TelegramNotifier

router = APIRouter(prefix="/kpi", tags=["kpi"])


@router.post("/instances")
async def create_kpi_instance(
    data: KPIInstanceCreate,
    user: User = Depends(permission_required("kpi:edit")),
    session: AsyncSession = Depends(get_session),
):
    instance = KPIInstance(
        employee_id=data.employee_id,
        template_id=data.template_id,
        month=data.month,
        period_start=data.period_start,
        period_end=data.period_end,
        overtime_amount=data.overtime_amount,
        status=KPIStatus.submitted,
    )
    session.add(instance)
    await session.flush()
    for m in data.metrics:
        session.add(
            KPIInstanceMetric(
                instance_id=instance.id,
                template_metric_id=m.template_metric_id,
                fact_value=m.fact_value,
                overtime_result=m.overtime_result,
            )
        )
    await session.flush()
    await session.refresh(instance, attribute_names=["metrics", "template"])
    await calculate_instance(session, instance)
    await audit_log(session, user.id, "KPIInstance", str(instance.id), "create", after_state={"status": instance.status.value})
    await session.commit()

    return {"id": instance.id, "total_amount": float(instance.total_amount), "status": instance.status.value}


@router.post("/disputes")
async def create_dispute(
    data: DisputeCreate,
    user: User = Depends(permission_required("kpi:dispute")),
    session: AsyncSession = Depends(get_session),
):
    dispute = KPIDispute(instance_id=data.instance_id, metric_id=data.metric_id, created_by=user.id, comment=data.comment)
    session.add(dispute)
    await audit_log(session, user.id, "KPIDispute", "new", "create", after_state={"instance_id": data.instance_id})

    admins = (await session.execute(select(User).where(User.is_super_admin.is_(True)))).scalars().all()
    notifier = TelegramNotifier()
    for admin in admins:
        await notifier.send(session, admin.telegram_id, f"KPI dispute created for instance {data.instance_id}", "kpi_disputed")
    await session.commit()
    return {"status": "ok"}


@router.post("/share-links")
async def create_share_link(
    data: KPIShareLinkCreate,
    user: User = Depends(permission_required("kpi:share")),
    session: AsyncSession = Depends(get_session),
):
    link = KPIShareLink(**data.model_dump(), created_by=user.id)
    session.add(link)
    await audit_log(session, user.id, "KPIShareLink", "new", "create", after_state=data.model_dump())
    await session.commit()
    await session.refresh(link)
    return {"uuid": str(link.uuid), "scope": link.scope.value, "permission": link.permission.value}


async def _instances_by_link(session: AsyncSession, link: KPIShareLink) -> list[KPIInstance]:
    q = select(KPIInstance).options(selectinload(KPIInstance.metrics))
    if link.scope.value == "single_kpi":
        q = q.where(KPIInstance.id == link.kpi_instance_id)
    elif link.scope.value == "employee_all":
        q = q.where(KPIInstance.employee_id == link.employee_id)
    elif link.scope.value == "month_all":
        q = q.where(KPIInstance.month == link.month)
    return (await session.execute(q)).scalars().all()


@router.get("/share/{uuid_value}")
async def shared_view(uuid_value: UUID, session: AsyncSession = Depends(get_session)):
    link = (await session.execute(select(KPIShareLink).where(KPIShareLink.uuid == uuid_value))).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    if link.expires_at and datetime.now(timezone.utc).replace(tzinfo=None) > link.expires_at:
        raise HTTPException(status_code=410, detail="Link expired")
    await audit_log(session, None, "KPIShareLink", str(link.uuid), "open", after_state={"opened_at": datetime.utcnow().isoformat()})
    instances = await _instances_by_link(session, link)
    await session.commit()
    return [{"id": i.id, "month": i.month, "status": i.status.value, "total": float(i.total_amount)} for i in instances]


@router.get("/export/{instance_id}")
async def export_kpi(
    instance_id: int,
    fmt: str = Query("pdf", pattern="^(pdf|xlsx)$"),
    batch: bool = False,
    month: str | None = None,
    user: User = Depends(permission_required("kpi:export")),
    session: AsyncSession = Depends(get_session),
):
    if batch:
        if not month:
            raise HTTPException(status_code=400, detail="month required for batch")
        instances = (
            await session.execute(select(KPIInstance).where(and_(KPIInstance.month == month)).options(selectinload(KPIInstance.metrics)))
        ).scalars().all()
        content = render_zip(instances, fmt)
        return StreamingResponse(BytesIO(content), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=kpi_{month}.zip"})

    instance = (
        await session.execute(select(KPIInstance).where(KPIInstance.id == instance_id).options(selectinload(KPIInstance.metrics)))
    ).scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="KPI not found")
    content = render_kpi_pdf(instance) if fmt == "pdf" else render_kpi_xlsx(instance)
    media_type = "application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ext = "pdf" if fmt == "pdf" else "xlsx"
    return StreamingResponse(BytesIO(content), media_type=media_type, headers={"Content-Disposition": f"attachment; filename=kpi_{instance_id}.{ext}"})
