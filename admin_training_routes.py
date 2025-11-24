"""
admin_training_routes.py - CORRIGIDO COM FORM DATA + DELAY
Rotas para gerenciamento de treinamento da IA
"""

from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
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
        # Buscar bot "Mia"
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            # Criar bot padrão
            bot = {
                "name": "Mia",
                "personality": {
                    "tone": "Professional",
                    "goals": "",
                    "restrictions": "",
                    "response_delay": 3
                },
                "knowledge_base": [],
                "faqs": [],
                "created_at": datetime.now()
            }
            result = await db.bots.insert_one(bot)
            bot["_id"] = result.inserted_id
            logger.info("✅ Bot Mia criado no MongoDB")
        
        return templates.TemplateResponse("admin_treinamento.html", {
            "request": request,
            "personalidade": bot.get("personality", {}),
            "conhecimentos": bot.get("knowledge_base", []),
            "faqs": bot.get("faqs", [])
        })
    except Exception as e:
        logger.error(f"❌ Erro ao carregar página de treinamento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ROTAS DE EDIÇÃO - PERSONALIDADE
# ============================================================

@router.post("/personalidade")
async def salvar_personalidade(
    tom_voz: str = Form(...),
    descricao: str = Form(...),
    objetivos: str = Form(...),
    restricoes: str = Form(""),
    response_delay: int = Form(3)
):
    """Salvar personalidade do bot"""
    try:
        # Buscar bot Mia
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            raise HTTPException(status_code=404, detail="Bot Mia não encontrado")
        
        # Atualizar personalidade
        result = await db.bots.update_one(
            {"name": "Mia"},
            {
                "$set": {
                    "personality": {
                        "tone": tom_voz,
                        "goals": objetivos,
                        "restrictions": restricoes,
                        "response_delay": response_delay
                    },
                    "updated_at": datetime.now()
                }
            }
        )
        
        logger.info(f"✅ Personalidade atualizada! Delay: {response_delay}s")
        
        return RedirectResponse(url="/admin/treinamento", status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Erro ao salvar personalidade: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ROTAS DE EDIÇÃO - BASE DE CONHECIMENTO
# ============================================================

@router.post("/conhecimento")
async def adicionar_conhecimento(
    titulo: str = Form(...),
    conteudo: str = Form(...)
):
    """Adicionar item à base de conhecimento"""
    try:
        novo_item = {
            "_id": str(ObjectId()),
            "titulo": titulo,
            "conteudo": conteudo,
            "created_at": datetime.now()
        }
        
        result = await db.bots.update_one(
            {"name": "Mia"},
            {"$push": {"knowledge_base": novo_item}}
        )
        
        logger.info(f"✅ Conhecimento adicionado: {titulo}")
        
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

# ============================================================
# ROTAS DE EDIÇÃO - FAQs
# ============================================================

@router.post("/faq")
async def adicionar_faq(
    pergunta: str = Form(...),
    resposta: str = Form(...)
):
    """Adicionar FAQ"""
    try:
        novo_faq = {
            "_id": str(ObjectId()),
            "question": pergunta,
            "answer": resposta,
            "created_at": datetime.now()
        }
        
        result = await db.bots.update_one(
            {"name": "Mia"},
            {"$push": {"faqs": novo_faq}}
        )
        
        logger.info(f"✅ FAQ adicionado: {pergunta}")
        
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
