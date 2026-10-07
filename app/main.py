from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .auth import ensure_bootstrap_admin, current_user, require_user, require_admin
from .scheduler import start_scheduler
from .routes import auth, inventory, admin, reports, analytics, techcards


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_bootstrap_admin()
    scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan, title="PF Tracker")

app.add_middleware(GZipMiddleware, minimum_size=500)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

app.include_router(
    inventory.router, prefix="/api/inventory",
    dependencies=[Depends(require_user)],
)
app.include_router(
    reports.router, prefix="/api/reports",
    dependencies=[Depends(require_admin)],
)
app.include_router(
    analytics.router, prefix="/api/analytics",
    dependencies=[Depends(require_admin)],
)
app.include_router(
    techcards.router, prefix="/api/techcards",
    dependencies=[Depends(require_user)],
)
app.include_router(
    admin.router, prefix="/api/admin",
    dependencies=[Depends(require_admin)],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/login")
def login_page():
    return FileResponse("app/static/login.html")


@app.get("/")
def index(request: Request):
    if not current_user(request):
        return RedirectResponse("/login", status_code=302)
    return FileResponse("app/static/index.html")


@app.get("/sw.js")
def sw():
    return FileResponse("app/static/sw.js", media_type="application/javascript")


@app.get("/manifest.json")
def manifest():
    return FileResponse(
        "app/static/manifest.json",
        media_type="application/manifest+json",
    )


@app.get("/health")
def health():
    return {"ok": True}