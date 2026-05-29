from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from auth import require_role, require_user
from database import RESOURCE_DIR, get_db

router = APIRouter(tags=["merchandise"])
templates = Jinja2Templates(directory=str(RESOURCE_DIR / "templates"))


def _ctx(request: Request, user, **extra):
    return {
        "request": request,
        "user": user,
        "currency": "₱",
        "is_admin": user.role == "admin",
        **extra,
    }


@router.get("/merchandise", response_class=HTMLResponse)
def merchandise_page(request: Request, db=Depends(get_db)):
    user = require_user(request, db)
    return templates.TemplateResponse(request, "merchandise.html", _ctx(request, user))


@router.get("/inventory", response_class=HTMLResponse)
def inventory_page(request: Request, db=Depends(get_db)):
    user = require_role(request, db, "admin")
    return templates.TemplateResponse(request, "inventory.html", _ctx(request, user))
