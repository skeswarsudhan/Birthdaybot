"""
web/app.py — FastAPI application factory for Birthday Bot.

Mounts:
  - /submit/{token}  — manager form (form.py router)
  - /               — dashboard (dashboard.py router)
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.routes.form import router as form_router
from web.routes.dashboard import router as dashboard_router

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app instance ready for Uvicorn.
    """
    app = FastAPI(
        title="Birthday Bot",
        description="Automated employee birthday email system",
        version="1.0.0",
        docs_url=None,   # Hide Swagger in production-style POC
        redoc_url=None,
    )

    # Include routers
    app.include_router(form_router)
    app.include_router(dashboard_router)

    # Mount uploads directory for serving submitted photos (if needed)
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

    return app


# Module-level app instance — imported by run.py and Uvicorn
app = create_app()
