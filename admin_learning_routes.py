from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from bson import ObjectId
import os

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
client = AsyncIOMotorClient(MONGODB_URI)
db = client.mia_database

@router.get("/admin/aprendizado", response_class=HTMLResponse)
async def admin_learning_page(request: Request):
    """Página de aprendizado híbrido - aprovar/rejeitar sugestões"""
    
    # Buscar sugestões pendentes
    pending_suggestions = await db.knowledge_suggestions.find(
        {"status": "pending"}
    ).sort("created_at", -1).to_list(length=100)
    
    # Buscar sugestões aprovadas (últimas 20)
    approved_suggestions = await db.knowledge_suggestions.find(
        {"status": "approved"}
    ).sort("approved_at", -1).limit(20).to_list(length=20)
    
    # Buscar sugestões rejeitadas (últimas 20)
    rejected_suggestions = await db.knowledge_suggestions.find(
        {"status": "rejected"}
    ).sort("approved_at", -1).limit(20).to_list(length=20)
    
    return templates.TemplateResponse("admin_aprendizado.html", {
        "request": request,
        "pending": pending_suggestions,
        "approved": approved_suggestions,
        "rejected": rejected_suggestions,
        "pending_count": len(pending_suggestions)
    })


@router.post("/admin/aprendizado/approve/{suggestion_id}")
async def approve_suggestion(suggestion_id: str):
    """Aprovar sugestão e adicionar à base de conhecimento"""
    try:
        # Buscar sugestão
        suggestion = await db.knowledge_suggestions.find_one(
            {"_id": ObjectId(suggestion_id)}
        )
        
        if not suggestion:
            return RedirectResponse("/admin/aprendizado", status_code=303)
        
        # Adicionar à base de conhecimento do bot Mia
        await db.bots.update_one(
            {"name": "Mia"},
            {
                "$push": {
                    "knowledge_base": {
                        "title": suggestion["title"],
                        "content": suggestion["content"],
                        "added_at": datetime.now(),
                        "source": "hybrid_learning"
                    }
                }
            }
        )
        
        # Atualizar status da sugestão
        await db.knowledge_suggestions.update_one(
            {"_id": ObjectId(suggestion_id)},
            {
                "$set": {
                    "status": "approved",
                    "approved_at": datetime.now(),
                    "approved_by": "admin"
                }
            }
        )
        
        return RedirectResponse("/admin/aprendizado", status_code=303)
        
    except Exception as e:
        print(f"Erro ao aprovar sugestão: {e}")
        return RedirectResponse("/admin/aprendizado", status_code=303)


@router.post("/admin/aprendizado/reject/{suggestion_id}")
async def reject_suggestion(suggestion_id: str):
    """Rejeitar sugestão"""
    try:
        # Atualizar status da sugestão
        await db.knowledge_suggestions.update_one(
            {"_id": ObjectId(suggestion_id)},
            {
                "$set": {
                    "status": "rejected",
                    "approved_at": datetime.now(),
                    "approved_by": "admin"
                }
            }
        )
        
        return RedirectResponse("/admin/aprendizado", status_code=303)
        
    except Exception as e:
        print(f"Erro ao rejeitar sugestão: {e}")
        return RedirectResponse("/admin/aprendizado", status_code=303)
