from datetime import datetime, timezone
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import permission_required
from app.db.session import get_session
from app.models import (
    KPIDispute,
    KPITemplate,
    KPITemplateMetric,
    KPIInstance,
    KPIInstanceMetric,
    KPIShareLink,
    KPIStatus,
    SharePermission,
    User,
    UserStatus,
)
from app.schemas.kpi import DisputeCreate, KPIInstanceCreate, KPIShareLinkCreate, KPITemplateCreate
from app.services.audit import audit_log
from app.services.export import render_kpi_pdf, render_kpi_xlsx, render_zip
from app.services.kpi_engine import FormulaValidationError, calculate_instance, validate_formula
from app.services.telegram import TelegramNotifier

router = APIRouter(prefix="/kpi", tags=["kpi"])




@router.post("/templates")
async def create_template(
    data: KPITemplateCreate,
    user: User = Depends(permission_required("kpi:edit")),
    session: AsyncSession = Depends(get_session),
):
    total_weight = sum(m.weight_percent for m in data.metrics)
    if round(total_weight, 2) > 100:
        raise HTTPException(status_code=400, detail="Total weight_percent cannot exceed 100")

    for metric in data.metrics:
        try:
            validate_formula(metric.formula)
        except FormulaValidationError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid formula for metric '{metric.title}': {exc}") from exc

    template = KPITemplate(
        title=data.title,
        max_total_amount=data.max_total_amount,
        formula_config=data.formula_config,
        is_active=True,
    )
    session.add(template)
    await session.flush()

    for metric in data.metrics:
        session.add(
            KPITemplateMetric(
                template_id=template.id,
                title=metric.title,
                description=metric.description,
                weight_percent=metric.weight_percent,
                plan_value=metric.plan_value,
                allow_overtime=metric.allow_overtime,
                formula=metric.formula,
            )
        )

    await audit_log(session, user.id, "KPITemplate", str(template.id), "create", after_state=data.model_dump())
    await session.commit()
    return {"id": template.id, "title": template.title}
@router.post("/instances")
async def create_kpi_instance(
    data: KPIInstanceCreate,
    user: User = Depends(permission_required("kpi:edit")),
    session: AsyncSession = Depends(get_session),
):
    existing = (
        await session.execute(
            select(KPIInstance).where(
                KPIInstance.employee_id == data.employee_id,
                KPIInstance.month == data.month,
                KPIInstance.template_id == data.template_id,
            )
        )
    ).scalar_one_or_none()
    if existing and existing.status in {KPIStatus.approved, KPIStatus.archived}:
        raise HTTPException(status_code=409, detail="Approved or archived KPI cannot be modified")

    instance = existing or KPIInstance(
        employee_id=data.employee_id,
        template_id=data.template_id,
        month=data.month,
        period_start=data.period_start,
        period_end=data.period_end,
        overtime_amount=data.overtime_amount,
        status=KPIStatus.submitted,
    )
    if not existing:
        session.add(instance)
        await session.flush()
    else:
        instance.period_start = data.period_start
        instance.period_end = data.period_end
        instance.overtime_amount = data.overtime_amount
        instance.status = KPIStatus.submitted
        for old_metric in list(instance.metrics):
            await session.delete(old_metric)
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

    try:
        await calculate_instance(session, instance)
    except FormulaValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await audit_log(session, user.id, "KPIInstance", str(instance.id), "upsert", after_state={"status": instance.status.value})
    await session.commit()

    return {"id": instance.id, "total_amount": float(instance.total_amount), "status": instance.status.value}


@router.post("/instances/{instance_id}/finalize")
async def finalize_kpi_instance(
    instance_id: int,
    user: User = Depends(permission_required("kpi:approve")),
    session: AsyncSession = Depends(get_session),
):
    instance = await session.get(KPIInstance, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="KPI not found")
    if instance.status == KPIStatus.approved:
        return {"id": instance.id, "status": instance.status.value}

    before = {"status": instance.status.value}
    instance.status = KPIStatus.approved
    await audit_log(session, user.id, "KPIInstance", str(instance.id), "finalize", before_state=before, after_state={"status": "approved"})

    employee = await session.get(User, instance.employee_id)
    if employee:
        notifier = TelegramNotifier()
        await notifier.send(session, employee.telegram_id, f"Ваш KPI #{instance.id} утверждён", "kpi_approved")

    await session.commit()
    return {"id": instance.id, "status": instance.status.value}


@router.post("/disputes")
async def create_dispute(
    data: DisputeCreate,
    user: User = Depends(permission_required("kpi:dispute")),
    session: AsyncSession = Depends(get_session),
):
    dispute = KPIDispute(instance_id=data.instance_id, metric_id=data.metric_id, created_by=user.id, comment=data.comment)
    session.add(dispute)
    await audit_log(session, user.id, "KPIDispute", "new", "create", after_state={"instance_id": data.instance_id})

    admins = (
        await session.execute(
            select(User).where(
                and_(User.status == UserStatus.active, User.is_super_admin.is_(True))
            )
        )
    ).scalars().all()
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


@router.get("/share/{uuid_value}/export")
async def export_by_share_link(
    uuid_value: UUID,
    fmt: str = Query("pdf", pattern="^(pdf|xlsx)$"),
    session: AsyncSession = Depends(get_session),
):
    link = (await session.execute(select(KPIShareLink).where(KPIShareLink.uuid == uuid_value))).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    if link.permission != SharePermission.view_download:
        raise HTTPException(status_code=403, detail="Download is not allowed for this share link")
    if link.expires_at and datetime.now(timezone.utc).replace(tzinfo=None) > link.expires_at:
        raise HTTPException(status_code=410, detail="Link expired")

    instances = await _instances_by_link(session, link)
    await audit_log(session, None, "KPIShareLink", str(link.uuid), "download", after_state={"format": fmt})
    await session.commit()

    if len(instances) > 1:
        payload = render_zip(instances, fmt)
        return StreamingResponse(BytesIO(payload), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=shared_kpi_{link.uuid}.zip"})

    if not instances:
        raise HTTPException(status_code=404, detail="No KPI found for link")
    instance = instances[0]
    payload = render_kpi_pdf(instance) if fmt == "pdf" else render_kpi_xlsx(instance)
    media_type = "application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ext = "pdf" if fmt == "pdf" else "xlsx"
    return StreamingResponse(BytesIO(payload), media_type=media_type, headers={"Content-Disposition": f"attachment; filename=shared_kpi_{instance.id}.{ext}"})


@router.get("/export/{instance_id}")
async def export_kpi(
    instance_id: int,
    fmt: str = Query("pdf", pattern="^(pdf|xlsx)$"),
    batch: bool = False,
    month: str | None = None,
    _: User = Depends(permission_required("kpi:export")),
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


@router.get("/instances")
async def list_kpis(
    month: str | None = None,
    period_start_from: str | None = None,
    period_end_to: str | None = None,
    status: KPIStatus | None = None,
    employee_id: int | None = None,
    _: User = Depends(permission_required("kpi:view")),
    session: AsyncSession = Depends(get_session),
):
    q = select(KPIInstance)
    if month:
        q = q.where(KPIInstance.month == month)
    if period_start_from:
        q = q.where(KPIInstance.period_start >= period_start_from)
    if period_end_to:
        q = q.where(KPIInstance.period_end <= period_end_to)
    if status:
        q = q.where(KPIInstance.status == status)
    if employee_id:
        q = q.where(KPIInstance.employee_id == employee_id)
    rows = (await session.execute(q.order_by(KPIInstance.period_start.desc()))).scalars().all()
    return [{"id": i.id, "employee_id": i.employee_id, "month": i.month, "status": i.status.value, "total": float(i.total_amount)} for i in rows]
