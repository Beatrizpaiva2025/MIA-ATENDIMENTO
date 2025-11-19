"""
VERSÃO FINAL - USA MONGODB ATLAS CORRETO
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/treinamento", tags=["admin-treinamento"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def get_database():
    """PEGA DATABASE DO MONGODB ATLAS - SEM LOCALHOST"""
    try:
        # TENTA IMPORTAR DE SERVER.PY (PREFERENCIAL)
        from server import get_database as server_get_db
        db = server_get_db()
        logger.info("✅ Database obtido de server.py")
        return db
    except Exception as e:
        logger.warning(f"⚠️ Não conseguiu importar de server.py: {e}")
        
        # FALLBACK: CONECTA DIRETO NO ATLAS
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            
            # PEGA MONGODB_URL DAS VARIÁVEIS DE AMBIENTE
            MONGODB_URL = os.getenv("MONGODB_URL")
            
            if not MONGODB_URL:
                logger.error("❌ MONGODB_URL não configurado!")
                return None
            
            # VERIFICA SE NÃO É LOCALHOST
            if "localhost" in MONGODB_URL or "127.0.0.1" in MONGODB_URL:
                logger.error("❌ MONGODB_URL está apontando para localhost!")
                return None
            
            logger.info(f"🔗 Conectando MongoDB Atlas: {MONGODB_URL[:30]}...")
            client = AsyncIOMotorClient(MONGODB_URL)
            db = client.whatsapp_ai
            logger.info("✅ Database fallback criado com MongoDB Atlas")
            return db
            
        except Exception as fallback_error:
            logger.error(f"❌ Erro ao criar fallback: {fallback_error}")
            return None


@router.get("/", response_class=HTMLResponse)
async def pagina_treinamento(request: Request):
    """Carregar página de treinamento"""
    try:
        logger.info("🔍 Carregando página de treinamento...")
        
        db = get_database()
        
        if db is None:
            logger.error("❌ Database não disponível")
            return HTMLResponse(
                content="<h1>Erro de Conexão</h1><p>Não foi possível conectar ao banco de dados. Verifique a variável MONGODB_URL.</p>",
                status_code=500
            )
        
        logger.info("✅ Database OK, buscando bot Mia...")
        
        # Buscar ou criar bot Mia
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            logger.warning("⚠️ Bot Mia não encontrado, criando...")
            bot = {
                "name": "Mia",
                "system_prompt": "Você é Mia, assistente virtual da Legacy Translations.",
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            result = await db.bots.insert_one(bot)
            bot["_id"] = result.inserted_id
            logger.info(f"✅ Bot Mia criado: {bot['_id']}")
        else:
            logger.info(f"✅ Bot Mia encontrado: {bot.get('_id')}")
        
        # Contar mensagens
        try:
            total_mensagens = await db.conversations.count_documents({})
        except:
            total_mensagens = 0
            logger.warning("⚠️ Não conseguiu contar mensagens")
        
        context = {
            "request": request,
            "bot_name": "Mia",
            "bot_id": str(bot["_id"]),
            "system_prompt": bot.get("system_prompt", ""),
            "is_active": bot.get("is_active", True),
            "description": bot.get("description", "Assistente da Legacy Translations"),
            "ultima_atualizacao": bot.get("updated_at", datetime.utcnow()),
            "total_mensagens": total_mensagens
        }
        
        logger.info(f"✅ Renderizando template (bot_id: {context['bot_id']})")
        
        return templates.TemplateResponse("admin_treinamento.html", context)
        
    except Exception as e:
        logger.error(f"❌ ERRO ao carregar página: {e}", exc_info=True)
        return HTMLResponse(
            content=f"<h1>Erro</h1><p>{str(e)}</p>",
            status_code=500
        )


@router.post("/salvar")
async def salvar_treinamento(
    bot_id: str = Form(...),
    system_prompt: str = Form(...),
    is_active: bool = Form(False)
):
    """SALVAR TREINAMENTO - VERSÃO SIMPLIFICADA"""
    try:
        logger.info(f"💾 Salvando treinamento (bot_id: {bot_id}, prompt: {len(system_prompt)} chars)")
        
        db = get_database()
        
        if db is None:
            logger.error("❌ Database não disponível")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Database não disponível"}
            )
        
        # Validação básica
        if not system_prompt or len(system_prompt.strip()) < 10:
            logger.error("❌ Prompt muito curto")
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Treinamento muito curto (mínimo 10 caracteres)"}
            )
        
        # Atualizar bot
        from bson import ObjectId
        
        result = await db.bots.update_one(
            {"_id": ObjectId(bot_id)},
            {"$set": {
                "system_prompt": system_prompt.strip(),
                "is_active": is_active,
                "updated_at": datetime.utcnow()
            }}
        )
        
        if result.matched_count == 0:
            logger.error(f"❌ Bot não encontrado: {bot_id}")
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Bot não encontrado"}
            )
        
        logger.info(f"✅ Bot atualizado com sucesso! (modified: {result.modified_count})")
        
        # Redirecionar com sucesso
        return RedirectResponse(
            url="/admin/treinamento/?success=true",
            status_code=303
        )
        
    except Exception as e:
        logger.error(f"❌ ERRO ao salvar: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@router.get("/health")
async def health_check():
    """Health check"""
    try:
        db = get_database()
        
        if db is None:
            return {"status": "unhealthy", "database": "disconnected"}
        
        # Tentar buscar bot
        bot = await db.bots.find_one({"name": "Mia"})
        
        return {
            "status": "healthy",
            "database": "connected",
            "bot_mia": "found" if bot else "not_found",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
