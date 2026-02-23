from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    AuthError,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_telegram_init_data,
)
from app.db.session import get_session
from app.models import User, UserStatus
from app.schemas.auth import RefreshTokenRequest, TelegramAuthRequest, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram", response_model=TokenPair)
async def telegram_auth(payload: TelegramAuthRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    user_payload = verify_telegram_init_data(payload.init_data)
    telegram_id = int(user_payload["id"])

    user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if telegram_id != settings.super_admin_telegram_id:
        if not user or not user.whitelist_enabled or user.status == UserStatus.banned:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not whitelisted or banned")

    if not user:
        user = User(
            telegram_id=telegram_id,
            username=user_payload.get("username", str(telegram_id)),
            full_name=f"{user_payload.get('first_name', '')} {user_payload.get('last_name', '')}".strip() or str(telegram_id),
            is_super_admin=telegram_id == settings.super_admin_telegram_id,
            whitelist_enabled=True,
            status=UserStatus.active,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return TokenPair(access_token=create_access_token(str(user.id)), refresh_token=create_refresh_token(str(user.id)))


@router.post("/refresh", response_model=TokenPair)
async def refresh_tokens(payload: RefreshTokenRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    try:
        decoded = decode_token(payload.refresh_token, expected_type="refresh")
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = await session.get(User, int(decoded["sub"]))
    if not user or user.status != UserStatus.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")

    return TokenPair(access_token=create_access_token(str(user.id)), refresh_token=create_refresh_token(str(user.id)))
