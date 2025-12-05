"""
admin_training_routes.py - VERSÃO COMPLETA COM ENDPOINTS JSON
Rotas para gerenciamento de treinamento da IA
Inclui endpoints Form Data (HTML) + JSON (API)
"""

from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
from datetime import datetime
import logging
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional

# Carregar variáveis de ambiente
load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/admin/treinamento", tags=["Admin Training"])

# ============================================================
# MODELS PYDANTIC PARA API JSON
# ============================================================

class KnowledgeUpdate(BaseModel):
    title: str
    content: str

class FAQUpdate(BaseModel):
    question: str
    answer: str

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
# ROTA PRINCIPAL - EXIBIR PÁGINA DE TREINAMENTO
# ============================================================

@router.get("/", response_class=HTMLResponse)
async def pagina_treinamento(request: Request):
    """Renderizar página de treinamento da IA"""
    try:
        # Buscar dados do bot
        bot_data = await db.bots.find_one({"name": "Mia"})
        
        if not bot_data:
            # Criar bot padrão se não existir
            bot_data = {
                "name": "Mia",
                "personality": "Você é Mia, assistente virtual da Legacy Translations...",
                "knowledge_base": [],
                "faqs": []
            }
            await db.bots.insert_one(bot_data)
        
        return templates.TemplateResponse(
            "admin_treinamento.html",
            {
                "request": request,
                "bot": bot_data
            }
        )
    except Exception as e:
        logger.error(f"❌ Erro ao carregar página: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ROTAS FORM DATA (HTML) - PERSONALIDADE
# ============================================================

@router.post("/personalidade")
async def atualizar_personalidade(
    personality: str = Form(...)
):
    """Atualizar personalidade do bot"""
    try:
        result = await db.bots.update_one(
            {"name": "Mia"},
            {"$set": {"personality": personality}}
        )
        
        logger.info("✅ Personalidade atualizada")
        
        return RedirectResponse(url="/admin/treinamento", status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar personalidade: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ROTAS FORM DATA (HTML) - KNOWLEDGE BASE
# ============================================================

@router.post("/conhecimento")
async def adicionar_conhecimento(
    title: str = Form(...),
    content: str = Form(...)
):
    """Adicionar item à base de conhecimento"""
    try:
        novo_item = {
            "_id": str(ObjectId()),
            "title": title,
            "content": content,
            "created_at": datetime.now()
        }
        
        result = await db.bots.update_one(
            {"name": "Mia"},
            {"$push": {"knowledge_base": novo_item}}
        )
        
        logger.info(f"✅ Conhecimento adicionado: {title}")
        
        return RedirectResponse(url="/admin/treinamento", status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Erro ao adicionar conhecimento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/conhecimento/deletar/{item_id}")
async def deletar_conhecimento(item_id: str):
    """Deletar item da base de conhecimento"""
    try:
        result = await db.bots.update_one(
            {"name": "Mia"},
            {"$pull": {"knowledge_base": {"_id": item_id}}}
        )
        
        logger.info(f"✅ Conhecimento deletado: {item_id}")
        
        return RedirectResponse(url="/admin/treinamento", status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Erro ao deletar conhecimento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/conhecimento/editar/{item_id}")
async def editar_conhecimento_form(
    item_id: str,
    title: str = Form(...),
    content: str = Form(...)
):
    """Editar item da base de conhecimento (Form Data)"""
    try:
        result = await db.bots.update_one(
            {"name": "Mia", "knowledge_base._id": item_id},
            {
                "$set": {
                    "knowledge_base.$.title": title,
                    "knowledge_base.$.content": content
                }
            }
        )
        
        logger.info(f"✅ Conhecimento editado: {title}")
        
        return RedirectResponse(url="/admin/treinamento", status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Erro ao editar conhecimento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ROTAS FORM DATA (HTML) - FAQs
# ============================================================

@router.post("/faq")
async def adicionar_faq(
    question: str = Form(...),
    answer: str = Form(...)
):
    """Adicionar FAQ"""
    try:
        novo_faq = {
            "_id": str(ObjectId()),
            "question": question,
            "answer": answer,
            "created_at": datetime.now()
        }
        
        result = await db.bots.update_one(
            {"name": "Mia"},
            {"$push": {"faqs": novo_faq}}
        )
        
        logger.info(f"✅ FAQ adicionado: {question}")
        
        return RedirectResponse(url="/admin/treinamento", status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Erro ao adicionar FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/faq/deletar/{item_id}")
async def deletar_faq(item_id: str):
    """Deletar FAQ"""
    try:
        result = await db.bots.update_one(
            {"name": "Mia"},
            {"$pull": {"faqs": {"_id": item_id}}}
        )
        
        logger.info(f"✅ FAQ deletado: {item_id}")
        
        return RedirectResponse(url="/admin/treinamento", status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Erro ao deletar FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/faq/editar/{item_id}")
async def editar_faq_form(
    item_id: str,
    question: str = Form(...),
    answer: str = Form(...)
):
    """Editar FAQ (Form Data) - NOVO ENDPOINT"""
    try:
        result = await db.bots.update_one(
            {"name": "Mia", "faqs._id": item_id},
            {
                "$set": {
                    "faqs.$.question": question,
                    "faqs.$.answer": answer
                }
            }
        )
        
        logger.info(f"✅ FAQ editado: {question}")
        
        return RedirectResponse(url="/admin/treinamento", status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Erro ao editar FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# API ENDPOINTS JSON - KNOWLEDGE BASE
# ============================================================

@router.get("/api/knowledge/{item_id}")
async def get_knowledge_item(item_id: str):
    """Buscar item específico de conhecimento (JSON)"""
    try:
        bot_data = await db.bots.find_one(
            {"name": "Mia"},
            {"knowledge_base": {"$elemMatch": {"_id": item_id}}}
        )
        
        if not bot_data or "knowledge_base" not in bot_data:
            raise HTTPException(status_code=404, detail="Item não encontrado")
        
        item = bot_data["knowledge_base"][0]
        
        return JSONResponse({
            "id": item["_id"],
            "title": item["title"],
            "content": item["content"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar conhecimento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/api/knowledge/{item_id}")
async def update_knowledge_item(item_id: str, data: KnowledgeUpdate):
    """Editar item da base de conhecimento (JSON API)"""
    try:
        result = await db.bots.update_one(
            {"name": "Mia", "knowledge_base._id": item_id},
            {
                "$set": {
                    "knowledge_base.$.title": data.title,
                    "knowledge_base.$.content": data.content
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Item não encontrado")
        
        logger.info(f"✅ Conhecimento editado via API: {data.title}")
        
        return JSONResponse({
            "success": True,
            "message": "Conhecimento atualizado com sucesso",
            "id": item_id
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao editar conhecimento via API: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# API ENDPOINTS JSON - FAQs
# ============================================================

@router.get("/api/faq/{item_id}")
async def get_faq_item(item_id: str):
    """Buscar FAQ específico (JSON)"""
    try:
        bot_data = await db.bots.find_one(
            {"name": "Mia"},
            {"faqs": {"$elemMatch": {"_id": item_id}}}
        )
        
        if not bot_data or "faqs" not in bot_data:
            raise HTTPException(status_code=404, detail="FAQ não encontrado")
        
        item = bot_data["faqs"][0]
        
        return JSONResponse({
            "id": item["_id"],
            "question": item["question"],
            "answer": item["answer"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao buscar FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/api/faq/{item_id}")
async def update_faq_item(item_id: str, data: FAQUpdate):
    """Editar FAQ (JSON API) - NOVO ENDPOINT"""
    try:
        result = await db.bots.update_one(
            {"name": "Mia", "faqs._id": item_id},
            {
                "$set": {
                    "faqs.$.question": data.question,
                    "faqs.$.answer": data.answer
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="FAQ não encontrado")
        
        logger.info(f"✅ FAQ editado via API: {data.question}")
        
        return JSONResponse({
            "success": True,
            "message": "FAQ atualizado com sucesso",
            "id": item_id
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao editar FAQ via API: {e}")
        raise HTTPException(status_code=500, detail=str(e))
