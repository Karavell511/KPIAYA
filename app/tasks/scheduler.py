from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models import KPIInstance, KPIStatus, Role, User, UserStatus
from app.services.telegram import TelegramNotifier

scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)


async def monthly_reminder() -> None:
    target_month = datetime.now().strftime("%Y-%m")
    async with AsyncSessionLocal() as session:
        admins = (
            await session.execute(
                select(User)
                .join(User.roles)
                .where(Role.name.in_(["Super Admin", "Admin"]))
                .where(User.status == UserStatus.active)
            )
        ).scalars().all()
        all_users = (await session.execute(select(User).where(User.status == UserStatus.active))).scalars().all()
        submitted_ids = set(
            (await session.execute(select(KPIInstance.employee_id).where(KPIInstance.month == target_month, KPIInstance.status != KPIStatus.draft)))
            .scalars()
            .all()
        )
        filled = [u.username for u in all_users if u.id in submitted_ids]
        unfilled = [u.username for u in all_users if u.id not in submitted_ids]

        notifier = TelegramNotifier()
        text = notifier.format_kpi_table(target_month, filled, unfilled)
        for admin in admins:
            if admin.roles and any(r.name == "Admin" for r in admin.roles) and not settings.scheduler_admin_include_optional:
                continue
            await notifier.send(session, admin.telegram_id, text, "monthly_reminder", {"month": target_month})
        await session.commit()


def configure_scheduler() -> None:
    for day in [20, 22, 23]:
        scheduler.add_job(monthly_reminder, "cron", day=day, hour=9, minute=0, id=f"monthly_reminder_{day}", replace_existing=True)
    scheduler.start()
