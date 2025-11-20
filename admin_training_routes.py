"""
admin_training_routes.py - VERSÃO CORRIGIDA COM VARIÁVEIS EM PORTUGUÊS
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

# ✅ CORREÇÃO: Usar caminho relativo igual ao main.py
templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/admin/treinamento", tags=["Admin Training"])

# ============================================================
# CONEXÃO MONGODB
# ============================================================

def get_database():
    """Obter database MongoDB com fallback"""
    try:
        # Tentar MONGODB_URI primeiro
        mongo_uri = os.getenv("MONGODB_URI")
        if not mongo_uri:
            # Fallback para MONGODB_URL
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

# Inicializar database
db = get_database()

# ============================================================
# HELPER FUNCTIONS
# ============================================================

async def get_or_create_bot():
    """Buscar ou criar bot Mia"""
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            logger.warning("⚠️ Bot Mia não encontrado, criando...")
            bot_data = {
                "name": "Mia",
                "personality": {
                    "tone": "Profissional e acolhedor",
                    "goals": [
                        "Qualificar leads de tradução",
                        "Agendar reuniões",
                        "Fornecer informações sobre serviços"
                    ],
                    "restrictions": [
                        "Não fornecer orçamentos sem análise",
                        "Sempre transferir casos complexos para humano"
                    ]
                },
                "knowledge_base": [],
                "faqs": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            result = await db.bots.insert_one(bot_data)
            bot = await db.bots.find_one({"_id": result.inserted_id})
            logger.info(f"✅ Bot Mia criado: {result.inserted_id}")
        else:
            logger.info(f"✅ Bot Mia encontrado: {bot['_id']}")
        
        return bot
    except Exception as e:
        logger.error(f"❌ Erro ao buscar/criar bot: {e}")
        raise

# ============================================================
# ROTAS DE VISUALIZAÇÃO
# ============================================================

@router.get("/", response_class=HTMLResponse, name="admin_training")
async def training_page(request: Request):
    """Página principal de treinamento da IA"""
    try:
        bot = await get_or_create_bot()
        bot_id = str(bot["_id"])
        
        logger.info(f"✅ Renderizando template (bot_id: {bot_id})")
        
        # ✅ CORREÇÃO: Passar variáveis em português E inglês (compatibilidade)
        return templates.TemplateResponse(
            "admin_treinamento.html",
            {
                "request": request,
                "bot_id": bot_id,
                "personalidade": bot.get("personality", {}),  # ✅ Português
                "personality": bot.get("personality", {}),     # ✅ Inglês (compatibilidade)
                "knowledge_count": len(bot.get("knowledge_base", [])),
                "faq_count": len(bot.get("faqs", []))
            }
        )
    except Exception as e:
        logger.error(f"❌ ERRO ao carregar página: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# API ENDPOINTS - PERSONALIDADE
# ============================================================

@router.get("/api/personality/{bot_id}")
async def get_personality(bot_id: str):
    """Obter configuração de personalidade"""
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
    """Atualizar personalidade da IA"""
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
            "id": str(ObjectId()),
            "title": data.get("title"),
            "content": data.get("content"),
            "category": data.get("category", "Geral"),
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

@router.delete("/api/knowledge/{bot_id}/{knowledge_id}")
async def delete_knowledge(bot_id: str, knowledge_id: str):
    """Remover item da base de conhecimento"""
    try:
        result = await db.bots.update_one(
            {"_id": ObjectId(bot_id)},
            {
                "$pull": {"knowledge_base": {"id": knowledge_id}},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Item não encontrado")
        
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

@router.get("/api/faqs/{bot_id}")
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

@router.post("/api/faqs/{bot_id}")
async def add_faq(bot_id: str, request: Request):
    """Adicionar FAQ"""
    try:
        data = await request.json()
        
        faq_item = {
            "id": str(ObjectId()),
            "question": data.get("question"),
            "answer": data.get("answer"),
            "category": data.get("category", "Geral"),
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
            "message": "FAQ adicionado",
            "faq": faq_item
        }
    except Exception as e:
        logger.error(f"Erro ao adicionar FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/faqs/{bot_id}/{faq_id}")
async def delete_faq(bot_id: str, faq_id: str):
    """Remover FAQ"""
    try:
        result = await db.bots.update_one(
            {"_id": ObjectId(bot_id)},
            {
                "$pull": {"faqs": {"id": faq_id}},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Item não encontrado")
        
        return {
            "success": True,
            "message": "FAQ removido"
        }
    except Exception as e:
        logger.error(f"Erro ao remover FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))
