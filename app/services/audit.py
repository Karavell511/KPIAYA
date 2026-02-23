from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KPIHistory


async def audit_log(
    session: AsyncSession,
    actor_id: int | None,
    entity_type: str,
    entity_id: str,
    action: str,
    before_state: dict | None = None,
    after_state: dict | None = None,
) -> None:
    session.add(
        KPIHistory(
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            before_state=before_state,
            after_state=after_state,
        )
    )
