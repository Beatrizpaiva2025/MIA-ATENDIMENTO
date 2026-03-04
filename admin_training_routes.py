"""
admin_training_routes.py - CORRIGIDO COM EDICAO COMPLETA
Rotas para gerenciamento de treinamento da IA
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
    tone: str = Form(...),
    goals: str = Form(...),
    restrictions: str = Form(""),
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
                        "tone": tone,
                        "goals": goals,
                        "restrictions": restrictions,
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

@router.get("/conhecimento/{item_id}")
async def obter_conhecimento(item_id: str):
    """Obter dados de um conhecimento específico (para edição)"""
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
        
        # Buscar item específico
        item = None
        for conhecimento in bot.get("knowledge_base", []):
            if conhecimento.get("_id") == item_id:
                item = conhecimento
                break
        
        if not item:
            raise HTTPException(status_code=404, detail="Conhecimento não encontrado")
        
        return JSONResponse({
            "id": item.get("_id"),
            "title": item.get("title") or item.get("titulo", ""),
            "content": item.get("content") or item.get("conteudo", "")
        })
        
    except Exception as e:
        logger.error(f"❌ Erro ao obter conhecimento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/conhecimento/editar/{item_id}")
async def editar_conhecimento(
    item_id: str,
    title: str = Form(...),
    content: str = Form(...)
):
    """Editar item da base de conhecimento"""
    try:
        result = await db.bots.update_one(
            {"name": "Mia", "knowledge_base._id": item_id},
            {
                "$set": {
                    "knowledge_base.$.title": title,
                    "knowledge_base.$.content": content,
                    "knowledge_base.$.titulo": title,
                    "knowledge_base.$.conteudo": content
                }
            }
        )
        
        logger.info(f"✅ Conhecimento editado: {title}")
        
        return RedirectResponse(url="/admin/treinamento", status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Erro ao editar conhecimento: {e}")
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
        
        logger.info(f"✅ FAQ adicionado: {question}")  # CORRIGIDO: era 'pergunta'
        
        return RedirectResponse(url="/admin/treinamento", status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Erro ao adicionar FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/faq/{item_id}")
async def obter_faq(item_id: str):
    """Obter dados de um FAQ específico (para edição)"""
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            raise HTTPException(status_code=404, detail="Bot não encontrado")
        
        # Buscar item específico
        item = None
        for faq in bot.get("faqs", []):
            if faq.get("_id") == item_id:
                item = faq
                break
        
        if not item:
            raise HTTPException(status_code=404, detail="FAQ não encontrado")
        
        return JSONResponse({
            "id": item.get("_id"),
            "question": item.get("question") or item.get("pergunta", ""),
            "answer": item.get("answer") or item.get("resposta", "")
        })
        
    except Exception as e:
        logger.error(f"❌ Erro ao obter FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/faq/editar/{item_id}")
async def editar_faq(
    item_id: str,
    question: str = Form(...),
    answer: str = Form(...)
):
    """Editar FAQ"""
    try:
        result = await db.bots.update_one(
            {"name": "Mia", "faqs._id": item_id},
            {
                "$set": {
                    "faqs.$.question": question,
                    "faqs.$.answer": answer,
                    "faqs.$.pergunta": question,
                    "faqs.$.resposta": answer
                }
            }
        )
        
        logger.info(f"✅ FAQ editado: {question}")
        
        return RedirectResponse(url="/admin/treinamento", status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Erro ao editar FAQ: {e}")
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


# ============================================================
# ROTA DE CORRECAO - ADICIONAR IDs FALTANTES
# ============================================================
@router.get("/corrigir-ids")
async def corrigir_ids_faltantes():
    """
    Corrige itens antigos que nao tem _id
    Acesse: /admin/treinamento/corrigir-ids
    """
    try:
        bot = await db.bots.find_one({"name": "Mia"})

        if not bot:
            return JSONResponse({"error": "Bot Mia nao encontrado"})

        conhecimentos_corrigidos = 0
        faqs_corrigidos = 0

        # Corrigir knowledge_base
        knowledge_base = bot.get("knowledge_base", [])
        nova_knowledge_base = []
        for item in knowledge_base:
            if not item.get("_id"):
                item["_id"] = str(ObjectId())
                conhecimentos_corrigidos += 1
            nova_knowledge_base.append(item)

        # Corrigir FAQs
        faqs = bot.get("faqs", [])
        novos_faqs = []
        for faq in faqs:
            if not faq.get("_id"):
                faq["_id"] = str(ObjectId())
                faqs_corrigidos += 1
            novos_faqs.append(faq)

        # Salvar correcoes
        if conhecimentos_corrigidos > 0 or faqs_corrigidos > 0:
            await db.bots.update_one(
                {"name": "Mia"},
                {
                    "$set": {
                        "knowledge_base": nova_knowledge_base,
                        "faqs": novos_faqs
                    }
                }
            )

        return JSONResponse({
            "success": True,
            "message": "IDs corrigidos com sucesso!",
            "conhecimentos_corrigidos": conhecimentos_corrigidos,
            "faqs_corrigidos": faqs_corrigidos,
            "instrucao": "Agora volte para /admin/treinamento e os botoes Edit/Delete vao funcionar"
        })

    except Exception as e:
        logger.error(f"❌ Erro ao corrigir IDs: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
