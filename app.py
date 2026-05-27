from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from auth import SESSION_COOKIE, get_current_user, read_session_token
from database import RESOURCE_DIR, init_db
from routers import admin, api, dashboard, sales


class AuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_PATHS = {"/login", "/static"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in self.PUBLIC_PATHS):
            return await call_next(request)
        if path.startswith("/api/"):
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE)
        if not token or not read_session_token(token):
            if path.startswith("/api"):
                from fastapi.responses import JSONResponse

                return JSONResponse({"error": "Not authenticated"}, status_code=401)
            return RedirectResponse("/login", status_code=302)

        return await call_next(request)


def create_app() -> FastAPI:
    init_db()
    from database import SessionLocal
    from seed import print_default_credentials, seed_database

    db = SessionLocal()
    try:
        admin_created = seed_database(db)
        if admin_created:
            print_default_credentials()
    finally:
        db.close()

    app = FastAPI(title="Pickleball Management")
    app.add_middleware(AuthMiddleware)
    app.mount("/static", StaticFiles(directory=str(RESOURCE_DIR / "static")), name="static")

    app.include_router(dashboard.router)
    app.include_router(admin.router)
    app.include_router(sales.router)
    app.include_router(api.router)

    return app
