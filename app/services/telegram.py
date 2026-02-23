from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import NotificationLog


class TelegramNotifier:
    def __init__(self) -> None:
        self.bot = Bot(token=settings.telegram_bot_token)

    @staticmethod
    def format_kpi_table(month: str, filled: list[str], unfilled: list[str]) -> str:
        filled_rows = "\n".join(f"• {name}" for name in filled) if filled else "• —"
        unfilled_rows = "\n".join(f"• {name}" for name in unfilled) if unfilled else "• —"
        return (
            f"📊 KPI Напоминание\n"
            f"Период: {month}\n"
            f"\n✅ Заполнено:\n{filled_rows}\n"
            f"\n❗ Не заполнено:\n{unfilled_rows}"
        )

    async def send(self, session: AsyncSession, telegram_id: int, text: str, event_type: str, payload: dict | None = None) -> None:
        status = "sent"
        try:
            await self.bot.send_message(chat_id=telegram_id, text=text)
        except Exception:
            status = "failed"
        session.add(
            NotificationLog(
                user_id=None,
                channel="telegram",
                event_type=event_type,
                payload=payload or {"text": text, "telegram_id": telegram_id},
                status=status,
            )
        )
