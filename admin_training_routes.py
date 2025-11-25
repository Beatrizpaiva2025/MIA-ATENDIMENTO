"""
admin_training_routes.py - COM ROTAS DE EDIÇÃO
Rotas para gerenciamento de treinamento da IA
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
from datetime import datetime
import logging
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/admin/treinamento", tags=["Admin Training"])

# ============================================================
# CONEXÃO MONGODB
# ============================================================

def get_database():
    """Obter database MongoDB com fallback"""
    try:
        mongo_uri = os.getenv("MONGODB_URI")
        if not mongo_uri:
            mongo_uri = os.getenv("MONGODB_URL")
        
        if not mongo_uri:
            logger.error("❌ Nenhuma URI MongoDB configurada!")
            raise ValueError("MongoDB URI não configurada")
        
        logger.info("🔗 Conectando MongoDB Atlas")
        client = AsyncIOMotorClient(mongo_uri)
        db = client.get_database()
        logger.info("✅ Database fallback criado")
        return db
    except Exception as e:
        logger.error(f"❌ Erro ao conectar MongoDB: {e}")
        raise

db = get_database()

# ============================================================
# PÁGINA DE TREINAMENTO
# ============================================================

@router.get("/", response_class=HTMLResponse)
async def admin_treinamento(request: Request):
    """Página de treinamento da IA"""
    try:
        bot_id = "default"
        bot = await db.bots.find_one({"_id": ObjectId(bot_id)}) if ObjectId.is_valid(bot_id) else await db.bots.find_one({"bot_id": bot_id})
        
        if not bot:
            bot = {
                "bot_id": "default",
                "personality": {},
                "knowledge_base": [],
                "faqs": []
            }
            result = await db.bots.insert_one(bot)
            bot["_id"] = result.inserted_id
        
        return templates.TemplateResponse("admin_treinamento.html", {
            "request": request,
            "bot_id": str(bot.get("_id")),
            "personality": bot.get("personality", {}),
            "knowledge_count": len(bot.get("knowledge_base", [])),
            "faq_count": len(bot.get("faqs", []))
        })
    except Exception as e:
        logger.error(f"Erro ao carregar página de treinamento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# API ENDPOINTS - PERSONALIDADE
# ============================================================

@router.get("/api/personality/{bot_id}")
async def get_personality(bot_id: str):
    """Obter personalidade do bot"""
    try:
        bot = await db.bots.find_one({"_id": ObjectId(bot_id)})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
        
        return {
            "success": True,
            "personality": bot.get("personality", {})
        }
    except Exception as e:
        logger.error(f"Erro ao buscar personalidade: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/personality/{bot_id}")
async def update_personality(bot_id: str, request: Request):
    """Atualizar personalidade do bot"""
    try:
        data = await request.json()
        
        result = await db.bots.update_one(
            {"_id": ObjectId(bot_id)},
            {
                "$set": {
                    "personality": data.get("personality"),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
        
        return {
            "success": True,
            "message": "Personalidade atualizada com sucesso"
        }
    except Exception as e:
        logger.error(f"Erro ao atualizar personalidade: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# API ENDPOINTS - BASE DE CONHECIMENTO
# ============================================================

@router.get("/api/knowledge/{bot_id}")
async def get_knowledge(bot_id: str):
    """Listar base de conhecimento"""
    try:
        bot = await db.bots.find_one({"_id": ObjectId(bot_id)})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
        
        return {
            "success": True,
            "knowledge": bot.get("knowledge_base", [])
        }
    except Exception as e:
        logger.error(f"Erro ao buscar conhecimento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/knowledge/{bot_id}")
async def add_knowledge(bot_id: str, request: Request):
    """Adicionar item à base de conhecimento"""
    try:
        data = await request.json()
        
        knowledge_item = {
            "title": data.get("title"),
            "content": data.get("content"),
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = await db.bots.update_one(
            {"_id": ObjectId(bot_id)},
            {
                "$push": {"knowledge_base": knowledge_item},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
        
        return {
            "success": True,
            "message": "Conhecimento adicionado",
            "knowledge": knowledge_item
        }
    except Exception as e:
        logger.error(f"Erro ao adicionar conhecimento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/api/knowledge/{bot_id}/{index}")
async def update_knowledge(bot_id: str, index: int, request: Request):
    """Atualizar item da base de conhecimento por índice"""
    try:
        data = await request.json()
        
        # Buscar bot
        bot = await db.bots.find_one({"_id": ObjectId(bot_id)})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
        
        knowledge_base = bot.get("knowledge_base", [])
        
        if index < 0 or index >= len(knowledge_base):
            raise HTTPException(status_code=404, detail="Conhecimento não encontrado")
        
        # Atualizar item
        knowledge_base[index] = {
            "title": data.get("title"),
            "content": data.get("content"),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Salvar no banco
        result = await db.bots.update_one(
            {"_id": ObjectId(bot_id)},
            {
                "$set": {
                    "knowledge_base": knowledge_base,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erro ao atualizar")
        
        return {
            "success": True,
            "message": "Conhecimento atualizado"
        }
    except Exception as e:
        logger.error(f"Erro ao atualizar conhecimento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/knowledge/{bot_id}/{index}")
async def delete_knowledge(bot_id: str, index: int):
    """Remover item da base de conhecimento por índice"""
    try:
        # Buscar bot
        bot = await db.bots.find_one({"_id": ObjectId(bot_id)})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
        
        knowledge_base = bot.get("knowledge_base", [])
        
        if index < 0 or index >= len(knowledge_base):
            raise HTTPException(status_code=404, detail="Conhecimento não encontrado")
        
        # Remover item
        knowledge_base.pop(index)
        
        # Salvar no banco
        result = await db.bots.update_one(
            {"_id": ObjectId(bot_id)},
            {
                "$set": {
                    "knowledge_base": knowledge_base,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erro ao deletar")
        
        return {
            "success": True,
            "message": "Conhecimento removido"
        }
    except Exception as e:
        logger.error(f"Erro ao remover conhecimento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# API ENDPOINTS - FAQs
# ============================================================

@router.get("/api/faq/{bot_id}")
async def get_faqs(bot_id: str):
    """Listar FAQs"""
    try:
        bot = await db.bots.find_one({"_id": ObjectId(bot_id)})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
        
        return {
            "success": True,
            "faqs": bot.get("faqs", [])
        }
    except Exception as e:
        logger.error(f"Erro ao buscar FAQs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/faq/{bot_id}")
async def add_faq(bot_id: str, request: Request):
    """Adicionar FAQ"""
    try:
        data = await request.json()
        
        faq_item = {
            "question": data.get("question"),
            "answer": data.get("answer"),
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = await db.bots.update_one(
            {"_id": ObjectId(bot_id)},
            {
                "$push": {"faqs": faq_item},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
        
        return {
            "success": True,
            "message": "FAQ adicionada",
            "faq": faq_item
        }
    except Exception as e:
        logger.error(f"Erro ao adicionar FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/api/faq/{bot_id}/{index}")
async def update_faq(bot_id: str, index: int, request: Request):
    """Atualizar FAQ por índice"""
    try:
        data = await request.json()
        
        # Buscar bot
        bot = await db.bots.find_one({"_id": ObjectId(bot_id)})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
        
        faqs = bot.get("faqs", [])
        
        if index < 0 or index >= len(faqs):
            raise HTTPException(status_code=404, detail="FAQ não encontrada")
        
        # Atualizar item
        faqs[index] = {
            "question": data.get("question"),
            "answer": data.get("answer"),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Salvar no banco
        result = await db.bots.update_one(
            {"_id": ObjectId(bot_id)},
            {
                "$set": {
                    "faqs": faqs,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erro ao atualizar")
        
        return {
            "success": True,
            "message": "FAQ atualizada"
        }
    except Exception as e:
        logger.error(f"Erro ao atualizar FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/faq/{bot_id}/{index}")
async def delete_faq(bot_id: str, index: int):
    """Remover FAQ por índice"""
    try:
        # Buscar bot
        bot = await db.bots.find_one({"_id": ObjectId(bot_id)})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
        
        faqs = bot.get("faqs", [])
        
        if index < 0 or index >= len(faqs):
            raise HTTPException(status_code=404, detail="FAQ não encontrada")
        
        # Remover item
        faqs.pop(index)
        
        # Salvar no banco
        result = await db.bots.update_one(
            {"_id": ObjectId(bot_id)},
            {
                "$set": {
                    "faqs": faqs,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Erro ao deletar")
        
        return {
            "success": True,
            "message": "FAQ removida"
        }
    except Exception as e:
        logger.error(f"Erro ao remover FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))
