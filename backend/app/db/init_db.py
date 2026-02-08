from sqlalchemy.ext.asyncio import AsyncEngine

from app.models.user import Base
import app.models.chat  # noqa: F401 - register chat tables with Base.metadata


async def init_db(engine: AsyncEngine) -> None:
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
