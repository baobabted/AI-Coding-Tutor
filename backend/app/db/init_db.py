from sqlalchemy.ext.asyncio import AsyncEngine

from app.models.user import Base


async def init_db(engine: AsyncEngine) -> None:
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
