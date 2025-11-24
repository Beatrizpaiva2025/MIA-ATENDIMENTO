"""
admin_learning_routes.py - VERSÃO SIMPLES (EM DESENVOLVIMENTO)
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/admin/aprendizado", tags=["Admin Learning"])

@router.get("/", response_class=HTMLResponse)
async def admin_aprendizado(request: Request):
    """Página de aprendizado (em desenvolvimento)"""
    return templates.TemplateResponse("admin_aprendizado.html", {
        "request": request
    })
