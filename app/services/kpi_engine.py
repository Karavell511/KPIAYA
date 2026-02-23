from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KPIInstance, KPIInstanceMetric, KPITemplateMetric


def _safe_eval(formula: str, context: dict) -> Decimal:
    allowed = {"__builtins__": {}, "min": min, "max": max, "round": round}
    return Decimal(str(eval(formula, allowed, context)))


async def calculate_instance(session: AsyncSession, instance: KPIInstance) -> KPIInstance:
    total = Decimal("0")
    for metric in instance.metrics:
        template_metric = await session.get(KPITemplateMetric, metric.template_metric_id)
        max_metric_amount = Decimal(str(instance.template.max_total_amount)) * (Decimal(str(template_metric.weight_percent)) / Decimal("100"))
        context = {
            "max_total_amount": Decimal(str(instance.template.max_total_amount)),
            "weight_percent": Decimal(str(template_metric.weight_percent)),
            "plan_value": Decimal(str(template_metric.plan_value)),
            "fact_value": Decimal(str(metric.fact_value)),
            "max_metric_amount": max_metric_amount,
        }
        metric.metric_result = _safe_eval(template_metric.formula, context)
        total += Decimal(str(metric.metric_result)) + Decimal(str(metric.overtime_result or 0))
    instance.total_amount = total + Decimal(str(instance.overtime_amount or 0))
    return instance


async def archive_old_kpis(session: AsyncSession, month: str) -> int:
    query = select(KPIInstance).where(KPIInstance.month < month, KPIInstance.is_archived.is_(False))
    result = await session.execute(query)
    rows = result.scalars().all()
    for item in rows:
        item.is_archived = True
    return len(rows)
