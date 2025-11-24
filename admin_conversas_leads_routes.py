"""
Routes para páginas em desenvolvimento: Conversas e Leads
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

# ============================================================
# CONVERSAS
# ============================================================
router_conversas = APIRouter(prefix="/admin/conversas", tags=["Admin Conversas"])

@router_conversas.get("/", response_class=HTMLResponse)
async def admin_conversas(request: Request):
    """Página de conversas (em desenvolvimento)"""
    return templates.TemplateResponse("admin_conversas.html", {
        "request": request
    })

# ============================================================
# LEADS
# ============================================================
router_leads = APIRouter(prefix="/admin/leads", tags=["Admin Leads"])

@router_leads.get("/", response_class=HTMLResponse)
async def admin_leads(request: Request):
    """Página de leads (em desenvolvimento)"""
    return templates.TemplateResponse("admin_leads.html", {
        "request": request
    })
