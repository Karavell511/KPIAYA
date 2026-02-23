from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models import KPIInstance, KPIStatus, Role, User
from app.services.audit import audit_log
from app.services.kpi_engine import calculate_instance

bot = Bot(settings.telegram_bot_token)
dp = Dispatcher()

# In-memory wizard state for admin KPI creation via inline buttons.
KPI_WIZARD_STATE: dict[int, str] = {}


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать KPI", callback_data="kpi_create")],
            [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="kpi_help")],
        ]
    )


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer(
        "KPIAYA Bot\nВыберите действие:",
        reply_markup=_main_keyboard(),
    )


@dp.callback_query(F.data == "kpi_help")
async def help_callback(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Формат ввода KPI (каждое значение с новой строки):\n"
        "1) employee_id\n"
        "2) template_id\n"
        "3) month (YYYY-MM)\n"
        "4) period_start (YYYY-MM-DD)\n"
        "5) period_end (YYYY-MM-DD)\n"
        "6) base_salary\n"
        "7) salary_share_percent\n"
        "8) overtime_hours_x1\n"
        "9) overtime_hours_x2\n\n"
        "Пример:\n"
        "15\n1\n2026-02\n2026-02-01\n2026-02-28\n120000\n30\n10\n4"
    )
    await callback.answer()


@dp.callback_query(F.data == "kpi_create")
async def create_kpi_callback(callback: CallbackQuery) -> None:
    telegram_id = callback.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
        if not user:
            await callback.message.answer("Вы не зарегистрированы в системе.")
            await callback.answer()
            return

        roles = (
            await session.execute(select(Role.name).join(Role.users).where(User.id == user.id))
        ).scalars().all()

        is_allowed = user.is_super_admin or any(r in {"Admin", "Manager"} for r in roles)
        if not is_allowed:
            await callback.message.answer("Недостаточно прав. Нужна роль Admin/Manager.")
            await callback.answer()
            return

    KPI_WIZARD_STATE[telegram_id] = "awaiting_payload"
    await callback.message.answer("Введите данные KPI в формате из раздела «Помощь».")
    await callback.answer()


@dp.message()
async def create_kpi_wizard(message: Message) -> None:
    telegram_id = message.from_user.id if message.from_user else 0
    if KPI_WIZARD_STATE.get(telegram_id) != "awaiting_payload":
        return

    lines = [line.strip() for line in (message.text or "").splitlines() if line.strip()]
    if len(lines) != 9:
        await message.answer("Неверный формат. Нужно ровно 9 строк. Нажмите «ℹ️ Помощь» для примера.")
        return

    try:
        employee_id = int(lines[0])
        template_id = int(lines[1])
        month = lines[2]
        period_start = datetime.strptime(lines[3], "%Y-%m-%d").date()
        period_end = datetime.strptime(lines[4], "%Y-%m-%d").date()
        base_salary = float(lines[5])
        salary_share_percent = float(lines[6])
        overtime_hours_x1 = float(lines[7])
        overtime_hours_x2 = float(lines[8])
    except ValueError:
        await message.answer("Ошибка парсинга. Проверьте числа и даты в формате YYYY-MM-DD.")
        return

    async with AsyncSessionLocal() as session:
        actor = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
        if not actor:
            await message.answer("Пользователь не найден в системе.")
            return

        instance = KPIInstance(
            employee_id=employee_id,
            template_id=template_id,
            month=month,
            period_start=period_start,
            period_end=period_end,
            base_salary=base_salary,
            salary_share_percent=salary_share_percent,
            overtime_hours_x1=overtime_hours_x1,
            overtime_hours_x2=overtime_hours_x2,
            status=KPIStatus.submitted,
        )
        session.add(instance)
        await session.flush()
        await session.refresh(instance, attribute_names=["template", "metrics"])
        await calculate_instance(session, instance)
        await audit_log(session, actor.id, "KPIInstance", str(instance.id), "create_from_bot", after_state={"month": month})
        await session.commit()

        await message.answer(
            "✅ KPI создан через бота:\n"
            f"KPI ID: {instance.id}\n"
            f"Сотрудник ID: {instance.employee_id}\n"
            f"Оклад: {float(instance.base_salary):.2f}\n"
            f"Доля от оклада: {float(instance.salary_share_percent):.2f}%\n"
            f"Переработка x1: {float(instance.overtime_hours_x1):.2f} ч\n"
            f"Переработка x2: {float(instance.overtime_hours_x2):.2f} ч\n"
            f"Итог: {float(instance.total_amount):.2f}"
        )

    KPI_WIZARD_STATE.pop(telegram_id, None)
