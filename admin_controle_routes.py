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

# ============================================================
# FUNÇÕES DE CONTROLE DO BOT
# ============================================================

async def get_bot_status():
    """Retorna status atual do bot (ativo/inativo)"""
    try:
        config = await db.bot_config.find_one({"_id": "global_status"})
        if config:
            return {
                "enabled": config.get("enabled", True),
                "last_update": config.get("last_update", datetime.now())
            }
        return {"enabled": True, "last_update": datetime.now()}
    except Exception as e:
        logger.error(f"Erro ao buscar status do bot: {e}")
        return {"enabled": True, "last_update": datetime.now()}

async def set_bot_status(enabled: bool):
    """Ativa ou desativa o bot globalmente"""
    try:
        await db.bot_config.update_one(
            {"_id": "global_status"},
            {
                "$set": {
                    "enabled": enabled,
                    "last_update": datetime.now()
                }
            },
            upsert=True
        )
        logger.info(f"✅ Bot {'ATIVADO' if enabled else 'DESATIVADO'}")
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar status do bot: {e}")
        return False

# ============================================================
# ROTAS DE VISUALIZAÇÃO
# ============================================================

@router.get("/", response_class=HTMLResponse, name="admin_controle")
async def controle_page(request: Request):
    """Página de controle do bot"""
    try:
        status = await get_bot_status()
        
        # Contar conversas por modo
        try:
            # Conversas em modo IA ativo
            ia_ativa = await db.conversas.count_documents({
                "mode": {"$in": ["ia", None]},
                "timestamp": {"$gte": datetime.now().replace(hour=0, minute=0, second=0)}
            })
            
            # Conversas em atendimento humano
            humano = await db.conversas.count_documents({
                "mode": "human",
                "timestamp": {"$gte": datetime.now().replace(hour=0, minute=0, second=0)}
            })
            
            # Conversas com IA desligada
            ia_desligada = await db.conversas.count_documents({
                "mode": "disabled",
                "timestamp": {"$gte": datetime.now().replace(hour=0, minute=0, second=0)}
            })
        except:
            ia_ativa = 0
            humano = 0
            ia_desligada = 0
        
        return templates.TemplateResponse(
            "admin_controle.html",
            {
                "request": request,
                "bot_enabled": status["enabled"],
                "last_update": status["last_update"],
                "stats": {
                    "ia_ativa": ia_ativa,
                    "atendimento_humano": humano,
                    "ia_desligada": ia_desligada,
                    "total": ia_ativa + humano + ia_desligada
                }
            }
        )
    except Exception as e:
        logger.error(f"❌ Erro ao carregar página de controle: {e}")
        raise

# ============================================================
# API ENDPOINTS
# ============================================================

@router.get("/api/status")
async def api_status():
    """Retorna status atual do bot"""
    status = await get_bot_status()
    
    # Contar conversas por modo
    try:
        ia_ativa = await db.conversas.count_documents({
            "mode": {"$in": ["ia", None]},
            "timestamp": {"$gte": datetime.now().replace(hour=0, minute=0, second=0)}
        })
        
        humano = await db.conversas.count_documents({
            "mode": "human",
            "timestamp": {"$gte": datetime.now().replace(hour=0, minute=0, second=0)}
        })
        
        ia_desligada = await db.conversas.count_documents({
            "mode": "disabled",
            "timestamp": {"$gte": datetime.now().replace(hour=0, minute=0, second=0)}
        })
    except:
        ia_ativa = 0
        humano = 0
        ia_desligada = 0
    
    return {
        "success": True,
        "enabled": status["enabled"],
        "last_update": status["last_update"].isoformat(),
        "stats": {
            "ia_ativa": ia_ativa,
            "atendimento_humano": humano,
            "ia_desligada": ia_desligada,
            "total": ia_ativa + humano + ia_desligada
        }
    }

@router.post("/api/toggle")
async def api_toggle(request: Request):
    """Liga ou desliga o bot globalmente"""
    try:
        data = await request.json()
        enabled = data.get("enabled", True)
        
        success = await set_bot_status(enabled)
        
        if success:
            return {
                "success": True,
                "enabled": enabled,
                "message": f"Bot {'ATIVADO' if enabled else 'DESATIVADO'} com sucesso!"
            }
        else:
            return {
                "success": False,
                "message": "Erro ao atualizar status do bot"
            }
    except Exception as e:
        logger.error(f"Erro ao alternar bot: {e}")
        return {
            "success": False,
            "message": str(e)
        }

@router.post("/api/transfer/{phone}")
async def api_transfer(phone: str):
    """Transfere uma conversa específica para atendimento humano"""
    try:
        await db.conversas.update_many(
            {"phone": phone},
            {"$set": {"mode": "human", "transferred_at": datetime.now()}}
        )
        
        return {
            "success": True,
            "phone": phone,
            "message": f"Conversa {phone} transferida para atendimento humano"
        }
    except Exception as e:
        logger.error(f"Erro ao transferir conversa: {e}")
        return {
            "success": False,
            "message": str(e)
        }

@router.post("/api/return/{phone}")
async def api_return(phone: str):
    """Retorna uma conversa para atendimento IA"""
    try:
        await db.conversas.update_many(
            {"phone": phone},
            {"$set": {"mode": "ia", "returned_at": datetime.now()}}
        )
        
        return {
            "success": True,
            "phone": phone,
            "message": f"Conversa {phone} retornada para IA"
        }
    except Exception as e:
        logger.error(f"Erro ao retornar conversa: {e}")
        return {
            "success": False,
            "message": str(e)
        }
