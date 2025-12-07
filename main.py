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
                "enabled": True,
                "modo_manutencao": False,
                "updated_at": datetime.now()
            }
            await db.bot_config.insert_one(config)
        return config
    except Exception as e:
        logger.error(f"Erro ao buscar status do bot: {e}")
        return {"enabled": True, "modo_manutencao": False}

async def set_bot_status(ia_ativa: bool = None, modo_manutencao: bool = None):
    """Atualiza status do bot"""
    try:
        update_data = {"updated_at": datetime.now()}
        if ia_ativa is not None:
            update_data["enabled"] = ia_ativa
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
            "ia_ativa": config.get("enabled", True),
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
    """Retorna estatísticas do dia com dados reais"""
    try:
        # Buscar conversas de hoje
        hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Contar mensagens de hoje
        mensagens_hoje = await db.conversas.count_documents({
            "timestamp": {"$gte": hoje}
        })

        # Contar clientes únicos de hoje
        clientes_hoje = await db.conversas.distinct("phone", {
            "timestamp": {"$gte": hoje}
        })

        # Contar transferências para humano hoje
        transferencias_hoje = await db.conversas.count_documents({
            "timestamp": {"$gte": hoje},
            "mode": "human"
        })

        # Contar conversões (pagamentos) hoje
        conversoes_hoje = await db.conversoes.count_documents({
            "timestamp": {"$gte": hoje}
        })

        return {
            "mensagens": mensagens_hoje,
            "conversas": len(clientes_hoje),
            "transferencias": transferencias_hoje,
            "conversoes": conversoes_hoje
        }
    except Exception as e:
        logger.error(f"Erro ao buscar estatísticas: {e}")
        return {"mensagens": 0, "conversas": 0, "transferencias": 0, "conversoes": 0}

@router.get("/api/logs")
async def api_get_logs():
    """Retorna logs recentes com números de telefone reais"""
    try:
        # Buscar últimas 30 mensagens
        mensagens = await db.conversas.find().sort("timestamp", -1).limit(30).to_list(30)

        logs = []
        for msg in mensagens:
            phone = msg.get("phone", "Desconhecido")
            timestamp = msg.get("timestamp", datetime.now())
            role = msg.get("role", "user")
            mode = msg.get("mode", "ia")
            message = msg.get("message", "")[:50]  # Primeiros 50 caracteres
            msg_type = msg.get("type", "text")

            # Formatar timestamp
            time_str = timestamp.strftime('%H:%M:%S') if hasattr(timestamp, 'strftime') else str(timestamp)[:8]

            # Ícone baseado no tipo/status
            if mode == "human":
                icon = "🔴"
                status = "HUMANO"
            elif role == "assistant":
                icon = "🤖"
                status = "IA"
            else:
                icon = "👤"
                status = "Cliente"

            # Tipo de mensagem
            type_icon = ""
            if msg_type == "image":
                type_icon = "📷"
            elif msg_type == "audio":
                type_icon = "🎤"
            elif msg_type == "document":
                type_icon = "📄"

            log_entry = f"[{time_str}] {icon} {phone} ({status}) {type_icon}: {message}..."
            logs.append(log_entry)

        return {"logs": logs}
    except Exception as e:
        logger.error(f"Erro ao buscar logs: {e}")
        return {"logs": [f"Erro ao carregar logs: {str(e)}"]}

@router.get("/api/clientes-ativos")
async def api_get_clientes_ativos():
    """Retorna lista de clientes ativos hoje com status"""
    try:
        hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Buscar todos os clientes únicos de hoje
        pipeline = [
            {"$match": {"timestamp": {"$gte": hoje}}},
            {"$group": {
                "_id": "$phone",
                "ultima_msg": {"$max": "$timestamp"},
                "total_msgs": {"$sum": 1},
                "modo": {"$last": "$mode"}
            }},
            {"$sort": {"ultima_msg": -1}},
            {"$limit": 20}
        ]

        clientes = await db.conversas.aggregate(pipeline).to_list(20)

        result = []
        for c in clientes:
            result.append({
                "phone": c["_id"],
                "ultima_msg": c["ultima_msg"].strftime('%H:%M') if hasattr(c["ultima_msg"], 'strftime') else str(c["ultima_msg"]),
                "total_msgs": c["total_msgs"],
                "modo": c.get("modo", "ia")
            })

        return {"clientes": result}
    except Exception as e:
        logger.error(f"Erro ao buscar clientes ativos: {e}")
        return {"clientes": []}

# ==================================================================
# API ENDPOINTS - CONFIGURAÇÕES DO OPERADOR
# ==================================================================

@router.get("/api/config")
async def api_get_config():
    """Retorna configurações atuais do sistema (números do operador)"""
    try:
        config = {}

        # Buscar configuração do operador
        operator_config = await db.bot_config.find_one({"_id": "operator_config"})
        if operator_config:
            # Número que ENVIA comandos (* e +)
            config["operator_number"] = operator_config.get("operator_number", "18573167770")
            # Número que RECEBE alertas/resumos
            config["alerts_number"] = operator_config.get("alerts_number", "18572081139")
        else:
            # Valores padrão
            config["operator_number"] = "18573167770"  # +1(857)316-7770
            config["alerts_number"] = "18572081139"    # +1(857)208-1139

        return {"success": True, "config": config}
    except Exception as e:
        logger.error(f"Erro ao buscar configurações: {e}")
        return {"success": False, "error": str(e)}

@router.post("/api/config/operator")
async def api_set_operator(request: Request):
    """Define os números do operador (comandos) e alertas (resumos)"""
    try:
        data = await request.json()
        # Número que ENVIA comandos (* e +)
        operator_number = data.get("operator_number", "")
        # Número que RECEBE alertas/resumos
        alerts_number = data.get("alerts_number", "")

        update_data = {"updated_at": datetime.now()}

        if operator_number:
            update_data["operator_number"] = operator_number
        if alerts_number:
            update_data["alerts_number"] = alerts_number

        await db.bot_config.update_one(
            {"_id": "operator_config"},
            {"$set": update_data},
            upsert=True
        )

        logger.info(f"Configuração atualizada - Comandos: {operator_number}, Alertas: {alerts_number}")
        return {
            "success": True,
            "operator_number": operator_number,
            "alerts_number": alerts_number
        }

    except Exception as e:
        logger.error(f"Erro ao configurar operador: {e}")
        return {"success": False, "error": str(e)}
