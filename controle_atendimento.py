"""
Sistema de Controle de Atendimento - IA vs Humano
Permite alternar entre bot IA e atendimento humano manualmente
"""

from datetime import datetime
from typing import Optional, Dict
from motor.motor_asyncio import AsyncIOMotorClient
import os

# Conectar MongoDB
mongo_client = AsyncIOMotorClient(os.getenv("MONGODB_URI"))
db = mongo_client["mia_bot"]

# ============================================================
# COMANDOS ESPECIAIS
# ============================================================
COMANDO_HUMANO = "*"      # Transferir para humano
COMANDO_IA = "+"          # Voltar para IA
COMANDO_DESLIGAR = "##"   # Desligar IA (somente humano)
COMANDO_LIGAR = "++"      # Ligar IA novamente

# ============================================================
# ESTADOS DE ATENDIMENTO
# ============================================================
ESTADO_IA = "IA_ATIVA"
ESTADO_HUMANO = "HUMANO_ATIVO"
ESTADO_DESLIGADA = "IA_DESLIGADA"

# ============================================================
# FUNÇÕES DE CONTROLE
# ============================================================

async def verificar_estado_conversa(phone: str) -> str:
    """
    Verifica o estado atual da conversa
    
    Returns:
        'IA_ATIVA', 'HUMANO_ATIVO' ou 'IA_DESLIGADA'
    """
    try:
        controle = await db.controle_atendimento.find_one({"phone": phone})
        
        if not controle:
            # Primeira conversa, criar registro
            await db.controle_atendimento.insert_one({
                "phone": phone,
                "estado": ESTADO_IA,
                "timestamp": datetime.now(),
                "atendente": None
            })
            return ESTADO_IA
        
        return controle.get("estado", ESTADO_IA)
        
    except Exception as e:
        print(f"Erro ao verificar estado: {e}")
        return ESTADO_IA


async def processar_comando_especial(phone: str, message: str, atendente: Optional[str] = None) -> Optional[Dict]:
    """
    Processa comandos especiais (* + ## ++)
    
    Returns:
        Dict com ação realizada ou None se não for comando
    """
    message_stripped = message.strip()
    
    # COMANDO: * (Transferir para humano)
    if message_stripped == COMANDO_HUMANO:
        await db.controle_atendimento.update_one(
            {"phone": phone},
            {
                "$set": {
                    "estado": ESTADO_HUMANO,
                    "timestamp": datetime.now(),
                    "atendente": atendente,
                    "motivo": "Comando manual (*)"
                }
            },
            upsert=True
        )
        
        # Criar registro de transferência
        await db.transferencias.insert_one({
            "phone": phone,
            "timestamp": datetime.now(),
            "status": "EM_ATENDIMENTO",
            "atendente": atendente,
            "motivo": "Comando manual (*)",
            "canal": "WhatsApp"
        })
        
        return {
            "acao": "transferir_humano",
            "resposta": "🔄 *Transferindo para atendimento humano...*\n\nUm de nossos atendentes já está ciente e responderá em instantes!",
            "estado_novo": ESTADO_HUMANO
        }
    
    # COMANDO: + (Voltar para IA)
    elif message_stripped == COMANDO_IA:
        await db.controle_atendimento.update_one(
            {"phone": phone},
            {
                "$set": {
                    "estado": ESTADO_IA,
                    "timestamp": datetime.now(),
                    "atendente": None
                }
            },
            upsert=True
        )
        
        # Atualizar transferência
        await db.transferencias.update_many(
            {"phone": phone, "status": "EM_ATENDIMENTO"},
            {
                "$set": {
                    "status": "CONCLUIDO",
                    "fim_atendimento": datetime.now()
                }
            }
        )
        
        return {
            "acao": "voltar_ia",
            "resposta": "🤖 *IA Mia ativada!*\n\nOlá! Voltei a atendê-lo. Como posso ajudar? 😊",
            "estado_novo": ESTADO_IA
        }
    
    # COMANDO: ## (Desligar IA - somente humano)
    elif message_stripped == COMANDO_DESLIGAR:
        await db.controle_atendimento.update_one(
            {"phone": phone},
            {
                "$set": {
                    "estado": ESTADO_DESLIGADA,
                    "timestamp": datetime.now(),
                    "atendente": atendente,
                    "desligada_por": atendente
                }
            },
            upsert=True
        )
        
        return {
            "acao": "desligar_ia",
            "resposta": "⏸️ *IA desligada*\n\nA IA Mia está temporariamente desativada para este contato. Use ++ para reativar.",
            "estado_novo": ESTADO_DESLIGADA
        }
    
    # COMANDO: ++ (Ligar IA novamente)
    elif message_stripped == COMANDO_LIGAR:
        await db.controle_atendimento.update_one(
            {"phone": phone},
            {
                "$set": {
                    "estado": ESTADO_IA,
                    "timestamp": datetime.now(),
                    "atendente": None
                }
            },
            upsert=True
        )
        
        return {
            "acao": "ligar_ia",
            "resposta": "✅ *IA Mia religada!*\n\nOlá! Estou de volta para atendê-lo. Em que posso ajudar? 😊",
            "estado_novo": ESTADO_IA
        }
    
    return None


async def deve_processar_com_ia(phone: str, message: str) -> bool:
    """
    Verifica se a mensagem deve ser processada pela IA
    
    Returns:
        True se deve processar com IA, False se é atendimento humano
    """
    # Verificar se é comando especial
    if message.strip() in [COMANDO_HUMANO, COMANDO_IA, COMANDO_DESLIGAR, COMANDO_LIGAR]:
        return False  # Comandos são processados separadamente
    
    # Verificar estado da conversa
    estado = await verificar_estado_conversa(phone)
    
    return estado == ESTADO_IA


async def forcar_estado(phone: str, estado: str, atendente: Optional[str] = None):
    """
    Força um estado específico (usado pelo painel admin)
    """
    await db.controle_atendimento.update_one(
        {"phone": phone},
        {
            "$set": {
                "estado": estado,
                "timestamp": datetime.now(),
                "atendente": atendente,
                "forcado": True
            }
        },
        upsert=True
    )


async def obter_info_controle(phone: str) -> Dict:
    """
    Obtém informações completas de controle do atendimento
    """
    controle = await db.controle_atendimento.find_one({"phone": phone})
    
    if not controle:
        return {
            "phone": phone,
            "estado": ESTADO_IA,
            "atendente": None,
            "timestamp": None
        }
    
    return {
        "phone": phone,
        "estado": controle.get("estado", ESTADO_IA),
        "atendente": controle.get("atendente"),
        "timestamp": controle.get("timestamp"),
        "desligada_por": controle.get("desligada_por")
    }


async def listar_atendimentos_ativos() -> list:
    """
    Lista todos os atendimentos que não estão em modo IA
    """
    atendimentos = await db.controle_atendimento.find({
        "estado": {"$ne": ESTADO_IA}
    }).sort("timestamp", -1).to_list(length=100)
    
    return atendimentos


async def estatisticas_atendimento() -> Dict:
    """
    Retorna estatísticas de atendimento
    """
    total_ia = await db.controle_atendimento.count_documents({"estado": ESTADO_IA})
    total_humano = await db.controle_atendimento.count_documents({"estado": ESTADO_HUMANO})
    total_desligada = await db.controle_atendimento.count_documents({"estado": ESTADO_DESLIGADA})
    
    return {
        "ia_ativa": total_ia,
        "humano_ativo": total_humano,
        "ia_desligada": total_desligada,
        "total": total_ia + total_humano + total_desligada
    }
