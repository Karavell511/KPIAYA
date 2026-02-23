from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Permission, Role, RolePermission, User, UserRole, UserStatus

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "Super Admin": ["*"],
    "Admin": ["kpi:edit", "kpi:approve", "kpi:share", "kpi:export", "users:view", "users:export", "kpi:dispute"],
    "Manager": ["kpi:edit", "kpi:share", "kpi:export", "users:view"],
    "Accountant": ["kpi:view", "kpi:approve", "kpi:export"],
    "Employee": ["kpi:view:own", "kpi:dispute"],
    "Leadership": ["kpi:view", "kpi:export"],
}


async def bootstrap_security(session: AsyncSession) -> None:
    permissions: dict[str, Permission] = {}
    for code in sorted({p for perms in ROLE_PERMISSIONS.values() for p in perms if p != "*"}):
        existing = (await session.execute(select(Permission).where(Permission.code == code))).scalar_one_or_none()
        if not existing:
            existing = Permission(code=code, description=code)
            session.add(existing)
            await session.flush()
        permissions[code] = existing

    for role_name, perms in ROLE_PERMISSIONS.items():
        role = (await session.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
        if not role:
            role = Role(name=role_name, description=role_name, immutable=(role_name == "Super Admin"))
            session.add(role)
            await session.flush()
        if role_name != "Super Admin":
            for code in perms:
                rp = (
                    await session.execute(
                        select(RolePermission).where(RolePermission.role_id == role.id, RolePermission.permission_id == permissions[code].id)
                    )
                ).scalar_one_or_none()
                if not rp:
                    session.add(RolePermission(role_id=role.id, permission_id=permissions[code].id))

    super_admin = (
        await session.execute(select(User).where(User.telegram_id == settings.super_admin_telegram_id))
    ).scalar_one_or_none()
    if not super_admin:
        super_admin = User(
            telegram_id=settings.super_admin_telegram_id,
            username=settings.super_admin_username,
            full_name=settings.super_admin_username,
            is_super_admin=True,
            whitelist_enabled=True,
            status=UserStatus.active,
        )
        session.add(super_admin)
        await session.flush()
    else:
        super_admin.is_super_admin = True
        super_admin.username = settings.super_admin_username
        super_admin.status = UserStatus.active

    super_role = (await session.execute(select(Role).where(Role.name == "Super Admin"))).scalar_one()
    ur = (
        await session.execute(select(UserRole).where(UserRole.user_id == super_admin.id, UserRole.role_id == super_role.id))
    ).scalar_one_or_none()
    if not ur:
        session.add(UserRole(user_id=super_admin.id, role_id=super_role.id))

    await session.commit()
