from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import engine
from app.db.init_db import init_db
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.routers.upload import router as upload_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Keep schema aligned with migration history.
    await init_db()

    yield
    # Close DB connections on shutdown.
    await engine.dispose()


app = FastAPI(title="AI Coding Tutor", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(health_router)
app.include_router(upload_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
