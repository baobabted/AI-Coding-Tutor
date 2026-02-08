from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router

__all__ = ["auth_router", "chat_router", "health_router"]
