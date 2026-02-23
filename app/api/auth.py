from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, verify_telegram_init_data
from app.db.session import get_session
from app.models import User
from app.schemas.auth import TelegramAuthRequest, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram", response_model=TokenPair)
async def telegram_auth(payload: TelegramAuthRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    user_payload = verify_telegram_init_data(payload.init_data)
    telegram_id = int(user_payload["id"])

    if telegram_id != settings.super_admin_telegram_id:
        user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
        if not user or not user.whitelist_enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not whitelisted")
    else:
        user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=telegram_id,
            username=user_payload.get("username", str(telegram_id)),
            full_name=f"{user_payload.get('first_name', '')} {user_payload.get('last_name', '')}".strip(),
            is_super_admin=telegram_id == settings.super_admin_telegram_id,
            whitelist_enabled=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return TokenPair(access_token=create_access_token(str(user.id)), refresh_token=create_refresh_token(str(user.id)))
