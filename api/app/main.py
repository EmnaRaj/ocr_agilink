from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import analytics, chat, fiches, fiches_read, stats

app = FastAPI(title="Agilink Fiches Suiveuses API")

# The SPA is served from a different origin (Vite dev server / nginx container),
# so allow it to call the API. Tighten allow_origins for a real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Order matters: the write router owns POST /fiches/scan; the read router owns
# GET /fiches, /fiches/{id}, /fiches/{id}/scan.
app.include_router(fiches.router)
app.include_router(fiches_read.router)
app.include_router(stats.router)
app.include_router(chat.router)
app.include_router(analytics.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.environment}
