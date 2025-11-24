"""
admin_controle_routes.py - Rotas para controle do bot (Liga/Desliga)
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/admin/controle", tags=["Admin Control"])

# Importar database do admin_training_routes
from admin_training_routes import db

# ==================================================================
# FUNÇÕES DE CONTROLE DO BOT
# ==================================================================

async def get_bot_status():
    """Retorna status atual do bot (ativo/inativo)"""
    try:
        config = await db.bot_config.find_one({"_id": "global_status"})
        if not config:
            # Criar configuração padrão se não existir
            config = {
                "_id": "global_status",
                "ia_ativa": True,
                "modo_manutencao": False,
                "updated_at": datetime.now()
            }
            await db.bot_config.insert_one(config)
        return config
    except Exception as e:
        logger.error(f"Erro ao buscar status do bot: {e}")
        return {"ia_ativa": True, "modo_manutencao": False}

async def set_bot_status(ia_ativa: bool = None, modo_manutencao: bool = None):
    """Atualiza status do bot"""
    try:
        update_data = {"updated_at": datetime.now()}
        if ia_ativa is not None:
            update_data["ia_ativa"] = ia_ativa
        if modo_manutencao is not None:
            update_data["modo_manutencao"] = modo_manutencao
        
        await db.bot_config.update_one(
            {"_id": "global_status"},
            {"$set": update_data},
            upsert=True
        )
        logger.info(f"Status do bot atualizado: {update_data}")
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar status do bot: {e}")
        return False

# ==================================================================
# ROTAS DA PÁGINA
# ==================================================================

@router.get("/", response_class=HTMLResponse)
async def admin_controle_page(request: Request):
    """Página de controle do bot"""
    try:
        return templates.TemplateResponse("admin_controle.html", {
            "request": request
        })
    except Exception as e:
        logger.error(f"Erro ao carregar página de controle: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ==================================================================
# API ENDPOINTS
# ==================================================================

@router.get("/api/status")
async def api_get_status():
    """Retorna status atual do bot"""
    try:
        config = await get_bot_status()
        return {
            "ia_ativa": config.get("ia_ativa", True),
            "modo_manutencao": config.get("modo_manutencao", False)
        }
    except Exception as e:
        logger.error(f"Erro ao buscar status: {e}")
        return {"ia_ativa": True, "modo_manutencao": False}

@router.post("/api/toggle-ia")
async def api_toggle_ia(request: Request):
    """Liga/desliga a IA"""
    try:
        data = await request.json()
        ativo = data.get("ativo", True)
        
        success = await set_bot_status(ia_ativa=ativo)
        
        if success:
            logger.info(f"IA {'ativada' if ativo else 'desativada'}")
            return {"success": True, "ia_ativa": ativo}
        else:
            return {"success": False, "error": "Erro ao atualizar status"}
    except Exception as e:
        logger.error(f"Erro ao toggle IA: {e}")
        return {"success": False, "error": str(e)}

@router.post("/api/toggle-manutencao")
async def api_toggle_manutencao(request: Request):
    """Liga/desliga modo manutenção"""
    try:
        data = await request.json()
        ativo = data.get("ativo", False)
        
        success = await set_bot_status(modo_manutencao=ativo)
        
        if success:
            logger.info(f"Modo manutenção {'ativado' if ativo else 'desativado'}")
            return {"success": True, "modo_manutencao": ativo}
        else:
            return {"success": False, "error": "Erro ao atualizar status"}
    except Exception as e:
        logger.error(f"Erro ao toggle manutenção: {e}")
        return {"success": False, "error": str(e)}

@router.get("/api/stats")
async def api_get_stats():
    """Retorna estatísticas do dia"""
    try:
        # Buscar conversas de hoje
        hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        conversas_hoje = await db.conversations.count_documents({
            "created_at": {"$gte": hoje}
        })
        
        # Contar mensagens de hoje (aproximado pelo número de conversas * 5)
        mensagens_hoje = conversas_hoje * 5
        
        return {
            "mensagens": mensagens_hoje,
            "conversas": conversas_hoje
        }
    except Exception as e:
        logger.error(f"Erro ao buscar estatísticas: {e}")
        return {"mensagens": 0, "conversas": 0}

@router.get("/api/logs")
async def api_get_logs():
    """Retorna logs recentes do sistema"""
    try:
        # Buscar últimas 20 conversas para simular logs
        conversas = await db.conversations.find().sort("created_at", -1).limit(20).to_list(20)
        
        logs = []
        for conv in conversas:
            phone = conv.get("phone", "Unknown")
            created = conv.get("created_at", datetime.now())
            status = conv.get("human_mode", False)
            
            if status:
                logs.append(f"[{created.strftime('%H:%M:%S')}] 🔴 {phone} - Transferred to human")
            else:
                logs.append(f"[{created.strftime('%H:%M:%S')}] 🟢 {phone} - AI responding")
        
        return {"logs": logs}
    except Exception as e:
        logger.error(f"Erro ao buscar logs: {e}")
        return {"logs": ["Error loading logs"]}
