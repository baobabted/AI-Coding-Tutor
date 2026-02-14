import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

def _build_alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    return cfg


async def init_db() -> None:
    """Run Alembic migrations to keep the schema up to date."""
    cfg = _build_alembic_config()
    await asyncio.to_thread(command.upgrade, cfg, "head")
