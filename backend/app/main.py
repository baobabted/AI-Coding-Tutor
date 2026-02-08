from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import engine
from app.db.init_db import init_db
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup: initialize database tables
    await init_db(engine)

    # Pre-initialise embedding service if an embedding key is configured
    if settings.cohere_api_key or settings.voyage_ai_key:
        from app.ai.embedding_service import EmbeddingService
        embedding_svc = EmbeddingService(
            provider=settings.embedding_provider,
            cohere_api_key=settings.cohere_api_key,
            voyage_api_key=settings.voyage_ai_key,
        )
        await embedding_svc.initialize()

    yield
    # Shutdown: dispose of engine
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
