from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
client = AsyncIOMotorClient(MONGODB_URI)
db = client.mia_database


@router.get("/admin/conversas", response_class=HTMLResponse)
async def admin_conversas_page(request: Request):
    """Página de histórico de conversas - Dashboard geral"""
    try:
        # Buscar últimas 100 conversas
        conversas = await db.conversas.find().sort("timestamp", -1).limit(100).to_list(length=100)
        
        # Calcular estatísticas
        total = len(conversas)
        stats = {
            "ia": len([c for c in conversas if c.get("role") in ["assistant", "ia"]]),
            "humano": len([c for c in conversas if c.get("mode") == "human"]),
            "whatsapp": len([c for c in conversas if c.get("canal") in ["WhatsApp", None]])
        }
        
        return templates.TemplateResponse("admin_conversas.html", {
            "request": request,
            "conversas": conversas,
            "total": total,
            "stats": stats
        })
        
    except Exception as e:
        logger.error(f"Erro ao carregar conversas: {e}")
        return templates.TemplateResponse("admin_conversas.html", {
            "request": request,
            "conversas": [],
            "total": 0,
            "stats": {"ia": 0, "humano": 0, "whatsapp": 0},
            "error": str(e)
        })
