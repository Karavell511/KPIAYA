from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.core.config import settings

bot = Bot(settings.telegram_bot_token)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer("KPIAYA bot is online. Use Mini App for login.")
