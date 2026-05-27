from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from auth import require_user
from database import RESOURCE_DIR, get_db

router = APIRouter(tags=["sales"])
templates = Jinja2Templates(directory=str(RESOURCE_DIR / "templates"))


@router.get("/sales", response_class=HTMLResponse)
def sales_page(request: Request, db=Depends(get_db)):
    user = require_user(request, db)
    return templates.TemplateResponse(
        request,
        "sales.html",
        {
            "user": user,
            "currency": "₱",
        },
    )
