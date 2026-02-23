from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthError, decode_token
from app.db.session import get_session
from app.models import Permission, Role, User


async def get_current_user(
    authorization: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = await session.get(User, int(payload["sub"]))
    if not user or user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")
    return user


def permission_required(code: str):
    async def dependency(
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> User:
        if user.is_super_admin:
            return user
        query = (
            select(Permission.code)
            .join(Permission.roles)
            .join(Role.users)
            .where(User.id == user.id)
        )
        result = await session.execute(query)
        if code not in set(result.scalars().all()):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {code}")
        return user

    return dependency
