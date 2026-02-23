from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import NotificationLog


class TelegramNotifier:
    def __init__(self) -> None:
        self.bot = Bot(token=settings.telegram_bot_token)

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
