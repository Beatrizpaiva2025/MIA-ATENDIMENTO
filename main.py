"""
============================================================
VERSAO COMPLETA MULTIMIDIA + PAINEL ADMIN - main.py
============================================================
Bot WhatsApp com suporte a:
- Mensagens de texto
- Imagens (GPT-4 Vision) - Leitura de documentos
- Audios (Whisper) - Transcricao de voz
- PDFs (GPT-4 Vision) - Analise de documentos multipagina
- Painel Administrativo Completo
- TREINAMENTO DINAMICO DO MONGODB
- AGRUPAMENTO DE MULTIPLAS IMAGENS (4 SEGUNDOS)
============================================================
"""

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import os
import httpx
from openai import OpenAI
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import traceback
import json
import base64
from io import BytesIO
import time
import re
import asyncio
import pytz

# Importar rotas do admin
from admin_routes import router as admin_router
from admin_training_routes import router as training_router
from admin_controle_routes import router as controle_router
from admin_learning_routes import router as learning_router
from admin_atendimento_routes import router as atendimento_router
from admin_conversas_routes import router as conversas_router
from admin_orcamentos_routes import router as orcamentos_router
from webchat_routes import router as webchat_router
from admin_crm_routes import router as crm_router, criar_ou_atualizar_contato

# ============================================================
# CONFIGURACAO DE LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# TIMEZONE E HORARIO COMERCIAL
# ============================================================
EST_TIMEZONE = pytz.timezone('US/Eastern')

def is_business_hours() -> bool:
    """
    Verifica se está dentro do horário comercial.
    ATUALIZADO: Atendimento normal 24/7 - sempre retorna True
    """
    # Atendimento 24/7 - sem restricao de horario
    return True

def get_after_hours_message(idioma: str = "pt") -> str:
    """Retorna mensagem para horário fora do expediente"""
    messages = {
        "en": """Hi! Thank you for contacting Legacy Translations. 😊

Our team is currently offline, but you can place your order directly on our website:
👉 https://portal.legacytranslations.com

We'll respond to your message as soon as we're back online!""",

        "pt": """Olá! Obrigada por entrar em contato com a Legacy Translations. 😊

Nossa equipe está offline no momento, mas você pode fazer seu pedido diretamente pelo nosso site:
👉 https://portal.legacytranslations.com

Responderemos sua mensagem assim que estivermos online!""",

        "es": """¡Hola! Gracias por contactar Legacy Translations. 😊

Nuestro equipo está desconectado en este momento, pero puede hacer su pedido directamente en nuestro sitio web:
👉 https://portal.legacytranslations.com

¡Responderemos su mensaje tan pronto estemos en línea!"""
    }
    return messages.get(idioma, messages["pt"])

# ============================================================
# FILTRO DE MENSAGENS DE SISTEMA
# ============================================================
SYSTEM_MESSAGE_PATTERNS = [
    # MongoDB Atlas Alerts
    r"ALERT:",
    r"Query Targeting",
    r"Scanned Objects",
    r"View Metrics",
    r"Acknowledge Alert",
    r"mongodb\.com",
    r"cluster\d+",
    r"atlas",
    # General system patterns
    r"^\[SYSTEM\]",
    r"^\[ALERTA\]",
    r"^NOTIFICATION:",
    r"^NOTIFICAÇÃO:",
]

def is_system_message(text: str) -> bool:
    """
    Detecta se a mensagem é um alerta de sistema (MongoDB, etc.)
    Essas mensagens NÃO devem ser processadas pelo bot.
    """
    if not text:
        return False

    text_lower = text.lower()

    # Verificar padrões de mensagem de sistema
    for pattern in SYSTEM_MESSAGE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.info(f"[FILTRO] Mensagem de sistema detectada: {text[:50]}...")
            return True

    return False

# ============================================================
# INICIALIZACAO
# ============================================================
app = FastAPI(title="WhatsApp AI Platform - Legacy Translations")

# CORS - Permitir requisicoes do portal
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://portal.legacytranslations.com",
        "http://localhost:3000",
        "http://localhost:5000",
        "http://127.0.0.1:5000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Clientes
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Usar mesma conexao do admin
from admin_training_routes import get_database
db = get_database()


# Limpeza: remover kb_origem do treinamento no MongoDB (pergunta de origem removida)
async def cleanup_kb_origem():
    """Remove o item kb_origem da base de conhecimento do bot Mia"""
    try:
        result = await db.bots.update_one(
            {"name": "Mia"},
            {"$pull": {"knowledge_base": {"_id": "kb_origem"}}}
        )
        if result.modified_count > 0:
            logger.info("[CLEANUP] kb_origem removido do treinamento do bot Mia")
    except Exception as e:
        logger.error(f"[CLEANUP] Erro ao remover kb_origem: {e}")


@app.on_event("startup")
async def startup_cleanup():
    await cleanup_kb_origem()


# ============================================================
# CONTROLE DO BOT - LIGAR/DESLIGAR
# ============================================================
# Estado global do bot (em memoria + MongoDB)
bot_status_cache = {
    "enabled": True,
    "last_update": datetime.now()
}

# ============================================================
# DEBUG LOG - WEBHOOK ACTIVITY
# ============================================================
webhook_debug_log = []  # Lista para armazenar ultimos eventos do webhook
MAX_DEBUG_LOG_SIZE = 50  # Manter apenas os ultimos 50 eventos

def add_webhook_debug(event_type: str, data: dict):
    """Adiciona evento ao log de debug do webhook"""
    global webhook_debug_log
    webhook_debug_log.append({
        "timestamp": datetime.now().isoformat(),
        "event": event_type,
        "data": data
    })
    # Manter apenas os ultimos N eventos
    if len(webhook_debug_log) > MAX_DEBUG_LOG_SIZE:
        webhook_debug_log = webhook_debug_log[-MAX_DEBUG_LOG_SIZE:]


async def get_bot_status():
    """Retorna status atual do bot (ativo/inativo)"""
    try:
        config = await db.bot_config.find_one({"_id": "global_status"})
        if config:
            bot_status_cache["enabled"] = config.get("enabled", True)
            bot_status_cache["last_update"] = config.get("last_update", datetime.now())
        return bot_status_cache
    except Exception as e:
        logger.error(f"Erro ao buscar status do bot: {e}")
        return bot_status_cache


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
        bot_status_cache["enabled"] = enabled
        bot_status_cache["last_update"] = datetime.now()
        logger.info(f"Bot {'ATIVADO' if enabled else 'DESATIVADO'}")
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar status do bot: {e}")
        return False


# ============================================================
# TRANSFERENCIA PARA ATENDENTE HUMANO
# ============================================================
# Numeros do sistema (configuravel por ambiente OU por MongoDB/UI)
# IMPORTANTE: Numeros devem incluir codigo do pais (1 para EUA, 55 para Brasil)
_atendente_raw = os.getenv("ATENDENTE_PHONE", "18573167770")
_notificacao_raw = os.getenv("NOTIFICACAO_PHONE", "18572081139")

# Garantir que numeros tenham o codigo do pais (1 para EUA)
def normalizar_telefone_eua(numero: str) -> str:
    """Garante que numero EUA tenha o codigo de pais 1"""
    numero = numero.strip().replace("+", "").replace("-", "").replace(" ", "")
    # Se comeca com 857 (area de Boston) sem o 1, adiciona
    if numero.startswith("857") and len(numero) == 10:
        return "1" + numero
    return numero

# Cache para configuracao do operador (evita consultar MongoDB a cada mensagem)
_operator_config_cache = {"operator": None, "alerts": None, "last_check": None}

async def get_operator_phones():
    """
    Busca telefones do operador do MongoDB (salvo via UI).
    Usa cache de 60 segundos para performance.
    Fallback para variaveis de ambiente.
    """
    global _operator_config_cache
    from datetime import datetime, timedelta

    # Verificar cache (valido por 60 segundos)
    if _operator_config_cache["last_check"]:
        if datetime.now() - _operator_config_cache["last_check"] < timedelta(seconds=60):
            return _operator_config_cache["operator"], _operator_config_cache["alerts"]

    try:
        config = await db.bot_config.find_one({"_id": "operator_config"})
        if config:
            operator = config.get("operator_number", "")
            alerts = config.get("alerts_number", "")
            if operator:
                _operator_config_cache["operator"] = normalizar_telefone_eua(operator)
            if alerts:
                _operator_config_cache["alerts"] = normalizar_telefone_eua(alerts)
            _operator_config_cache["last_check"] = datetime.now()
            logger.info(f"[CONFIG] Loaded from MongoDB - Operator: {_operator_config_cache['operator']}, Alerts: {_operator_config_cache['alerts']}")
    except Exception as e:
        logger.error(f"[CONFIG] Error loading from MongoDB: {e}")

    # Fallback para variaveis de ambiente se nao tiver no cache
    if not _operator_config_cache["operator"]:
        _operator_config_cache["operator"] = ATENDENTE_PHONE
    if not _operator_config_cache["alerts"]:
        _operator_config_cache["alerts"] = NOTIFICACAO_PHONE

    return _operator_config_cache["operator"], _operator_config_cache["alerts"]

def is_operator_phone(phone: str) -> bool:
    """
    Verifica se o telefone pertence ao operador/atendente.
    Compara os ultimos 10 digitos para evitar problemas com codigo de pais.
    Aceita ATENDENTE_PHONE e NOTIFICACAO_PHONE como operadores.
    NOTA: Esta funcao usa os valores padroes. Para valores dinamicos do MongoDB,
    use is_operator_phone_async() em contexto async.
    """
    digits = ''.join(c for c in phone if c.isdigit())

    # Lista de telefones de operadores (valores padroes + cache se disponivel)
    operator_phones = [ATENDENTE_PHONE, NOTIFICACAO_PHONE]
    if _operator_config_cache["operator"] and _operator_config_cache["operator"] not in operator_phones:
        operator_phones.append(_operator_config_cache["operator"])
    if _operator_config_cache["alerts"] and _operator_config_cache["alerts"] not in operator_phones:
        operator_phones.append(_operator_config_cache["alerts"])

    for op_phone in operator_phones:
        op_digits = ''.join(c for c in op_phone if c.isdigit())
        # Comparar ultimos 10 digitos (numero local EUA sem codigo de pais)
        if len(digits) >= 10 and len(op_digits) >= 10:
            if digits[-10:] == op_digits[-10:]:
                return True
        elif digits == op_digits:
            return True

    return False

async def is_operator_phone_async(phone: str) -> bool:
    """
    Versao async de is_operator_phone que busca config do MongoDB.
    Use esta versao em contextos async para garantir valores atualizados.
    """
    operator, alerts = await get_operator_phones()
    digits = ''.join(c for c in phone if c.isdigit())

    operator_phones = [operator, alerts, ATENDENTE_PHONE, NOTIFICACAO_PHONE]
    operator_phones = list(set(filter(None, operator_phones)))  # Remove duplicatas e vazios

    for op_phone in operator_phones:
        op_digits = ''.join(c for c in op_phone if c.isdigit())
        if len(digits) >= 10 and len(op_digits) >= 10:
            if digits[-10:] == op_digits[-10:]:
                return True
        elif digits == op_digits:
            return True

    return False

ATENDENTE_PHONE = normalizar_telefone_eua(_atendente_raw)
NOTIFICACAO_PHONE = normalizar_telefone_eua(_notificacao_raw)

# Log para debug
logger.info(f"[CONFIG] ATENDENTE_PHONE: {ATENDENTE_PHONE}")
logger.info(f"[CONFIG] NOTIFICACAO_PHONE: {NOTIFICACAO_PHONE}")

# Timeout para modo humano (em minutos) - apos esse tempo, volta automaticamente para IA
HUMAN_MODE_TIMEOUT_MINUTES = int(os.getenv("HUMAN_MODE_TIMEOUT_MINUTES", "30"))

# ============================================================
# SISTEMA DE ETAPAS DO ATENDIMENTO
# ============================================================
# Etapas possiveis:
# - INICIAL: Conversa normal, sem documento analisado
# - AGUARDANDO_NOME: Bot pediu o nome do cliente
# - AGUARDANDO_ORIGEM: Bot pediu como conheceu a Legacy
# - AGUARDANDO_OPCAO_ATENDIMENTO: Fora do horario - opcoes: continuar aqui / website / atendente
# - AGUARDANDO_CONFIRMACAO: Orcamento enviado, aguardando cliente confirmar
# - AGUARDANDO_PAGAMENTO: Cliente confirmou, aguardando comprovante
# - PAGAMENTO_RECEBIDO: Comprovante recebido e confirmado

ETAPAS = {
    "INICIAL": "inicial",
    "AGUARDANDO_NOME": "aguardando_nome",
    "AGUARDANDO_ORIGEM": "aguardando_origem",
    "AGUARDANDO_OPCAO_ATENDIMENTO": "aguardando_opcao_atendimento",
    "AGUARDANDO_CONFIRMACAO": "aguardando_confirmacao",
    "AGUARDANDO_PAGAMENTO": "aguardando_pagamento",
    "PAGAMENTO_RECEBIDO": "pagamento_recebido"
}

# Palavras para detectar confirmacao de prosseguimento
PALAVRAS_CONFIRMACAO = [
    "vou prosseguir", "pode prosseguir", "pode fazer", "pode iniciar",
    "vamos continuar", "pode dar andamento", "confirmo", "ok, pode seguir",
    "quero prosseguir", "pode começar", "pode comecar", "seguimos com a tradução",
    "seguimos com a traducao", "vamos fazer", "pode seguir", "confirmar",
    "quero fazer", "vou fazer", "sim, pode", "sim pode", "fechado", "fechar",
    "vamos fechar", "aceito", "aceitar", "concordo", "let's do it", "let's proceed",
    "yes", "yes please", "go ahead", "proceed", "confirm", "i confirm",
    # Confirmacoes coloquiais em portugues
    "podemo", "podemos", "vamo", "vamos", "bora", "claro", "claro que sim",
    "com certeza", "pode sim", "sim", "isso", "isso mesmo", "certo", "perfeito",
    "beleza", "blz", "ok", "okay", "tudo bem", "ta bom", "tá bom", "pode ser",
    "prosseguir", "continuar", "continuidade", "dar continuidade",
    "fazendo o pagamento", "vou pagar", "vou enviar", "estou fazendo",
    # Confirmacoes em espanhol
    "si", "sí", "dale", "claro que sí", "por supuesto", "de acuerdo",
    "perfecto", "listo", "va", "vamos", "hagámoslo", "adelante",
    # Confirmacoes em ingles
    "sure", "absolutely", "of course", "sounds good", "let's go",
    "i'll pay", "i will pay", "making the payment", "sending payment",
    "paying now", "i agree", "deal", "perfect", "great", "alright"
]

# Palavras para detectar comprovante de pagamento
PALAVRAS_COMPROVANTE = [
    "comprovante", "pagamento", "pago", "paid", "receipt", "transaction",
    "transfer", "venmo", "zelle", "cashapp", "paypal", "bank", "transferência",
    "transferencia", "pix", "deposito", "depósito", "amount", "total",
    "confirmation", "ref", "transaction id"
]


async def get_cliente_estado(phone: str) -> dict:
    """Busca o estado atual do cliente no atendimento"""
    try:
        estado = await db.cliente_estados.find_one({"phone": phone})
        if not estado:
            return {
                "phone": phone,
                "etapa": ETAPAS["INICIAL"],
                "nome": None,
                "origem": None,
                "idioma": "pt",  # Padrao portugues
                "ultimo_orcamento": None,
                "valor_orcamento": None,
                "documento_info": None,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }

        # Sanitizar nome: limpar nomes invalidos que foram salvos por engano
        nome = estado.get("nome", "")
        if nome:
            palavras_invalidas = [
                "humano", "atendente", "falar", "traduzir", "traducao",
                "tradução", "transferir", "operador", "pessoa", "pagina",
                "página", "documento", "comprovante", "pagamento"
            ]
            nome_lower = nome.lower()
            if any(p in nome_lower for p in palavras_invalidas):
                estado["nome"] = ""
                # Limpar no banco tambem
                await db.cliente_estados.update_one(
                    {"phone": phone},
                    {"$set": {"nome": "", "updated_at": datetime.now()}}
                )
                logger.warning(f"[SANITIZE] Nome invalido '{nome}' limpo para {phone}")

        return estado
    except Exception as e:
        logger.error(f"Erro ao buscar estado do cliente: {e}")
        return {"phone": phone, "etapa": ETAPAS["INICIAL"], "idioma": "pt"}


async def set_cliente_estado(phone: str, **kwargs):
    """Atualiza o estado do cliente"""
    try:
        kwargs["updated_at"] = datetime.now()
        await db.cliente_estados.update_one(
            {"phone": phone},
            {"$set": kwargs},
            upsert=True
        )
        logger.info(f"Estado atualizado para {phone}: {kwargs}")
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar estado: {e}")
        return False


def detectar_idioma(texto: str) -> str:
    """Detecta idioma do texto (pt, en, es)"""
    texto_lower = texto.lower()

    # Palavras tipicas de cada idioma
    palavras_pt = ["olá", "ola", "bom dia", "boa tarde", "boa noite", "obrigado", "obrigada",
                   "por favor", "quero", "preciso", "pode", "gostaria", "como", "quanto"]
    palavras_en = ["hello", "hi", "good morning", "good afternoon", "thank you", "thanks",
                   "please", "want", "need", "can", "would", "how", "much", "price"]
    palavras_es = ["hola", "buenos días", "buenas tardes", "gracias", "por favor",
                   "quiero", "necesito", "puede", "cuánto", "precio", "traducción"]

    # Contar matches
    count_pt = sum(1 for p in palavras_pt if p in texto_lower)
    count_en = sum(1 for p in palavras_en if p in texto_lower)
    count_es = sum(1 for p in palavras_es if p in texto_lower)

    if count_en > count_pt and count_en > count_es:
        return "en"
    elif count_es > count_pt and count_es > count_en:
        return "es"
    return "pt"


def detectar_confirmacao_prosseguimento(texto: str) -> bool:
    """Detecta se cliente confirmou que quer prosseguir com o servico"""
    texto_lower = texto.lower()
    return any(palavra in texto_lower for palavra in PALAVRAS_CONFIRMACAO)


def detectar_possivel_comprovante(texto: str) -> bool:
    """Detecta se texto indica possivel comprovante de pagamento"""
    texto_lower = texto.lower()
    return any(palavra in texto_lower for palavra in PALAVRAS_COMPROVANTE)


async def notificar_atendente(phone: str, motivo: str = "Cliente solicitou"):
    """Envia notificacao para atendente com resumo da conversa e dados do cliente"""
    try:
        logger.info(f"[NOTIFICACAO] Iniciando notificacao para {NOTIFICACAO_PHONE} sobre cliente {phone}")

        # Buscar estado completo do cliente (nome, paginas, idioma, orcamento)
        estado = await get_cliente_estado(phone)
        nome_cliente = estado.get("nome", "Nao informado")
        num_paginas = estado.get("num_paginas", "Nao informado")
        idioma = estado.get("idioma", "pt")
        idioma_destino = estado.get("idioma_destino", "Nao informado")
        valor_orcamento = estado.get("valor_orcamento", None)
        documento_info = estado.get("documento_info", None)

        # Traduzir codigo de idioma
        idiomas_map = {"pt": "Portugues", "en": "Ingles", "es": "Espanhol"}
        idioma_texto = idiomas_map.get(idioma, idioma)

        # Buscar ultimas 5 mensagens da conversa
        mensagens = await db.conversas.find(
            {"phone": phone}
        ).sort("timestamp", -1).limit(5).to_list(length=5)

        # Inverter para ordem cronologica
        mensagens.reverse()

        # Montar resumo
        resumo_linhas = []
        for msg in mensagens:
            role = "Cliente" if msg.get("role") == "user" else "Mia"
            texto = msg.get("message", "")[:80]
            resumo_linhas.append(f"{role}: {texto}")

        resumo = "\n".join(resumo_linhas) if resumo_linhas else "Sem historico"

        # Montar mensagem de notificacao com dados completos
        mensagem_atendente = f"""*NOVO ATENDIMENTO HUMANO*

*DADOS DO CLIENTE:*
Telefone: {phone}
Nome: {nome_cliente}
Paginas: {num_paginas}
Idioma cliente: {idioma_texto}
Traducao para: {idioma_destino}"""

        # Adicionar valor do orcamento se existir
        if valor_orcamento:
            mensagem_atendente += f"\n*ORCAMENTO: ${valor_orcamento}*"

        # Adicionar info do documento se existir
        if documento_info:
            mensagem_atendente += f"\nDocumento: {documento_info[:100]}"

        mensagem_atendente += f"""

Motivo: {motivo}

*ULTIMAS MENSAGENS:*
{resumo}

*COMO ATENDER:*
1. Abra a conversa com {phone} no WhatsApp
2. Responda diretamente ao cliente
3. Para PAUSAR a IA: digite *
4. Para RETOMAR a IA: digite +

A IA ja esta PAUSADA para este cliente."""

        # Enviar notificacao para numero pessoal
        logger.info(f"[NOTIFICACAO] Enviando para {NOTIFICACAO_PHONE}...")
        resultado = await send_whatsapp_message(NOTIFICACAO_PHONE, mensagem_atendente)

        if resultado:
            logger.info(f"[NOTIFICACAO] SUCESSO - Notificacao enviada para {NOTIFICACAO_PHONE}")
        else:
            logger.error(f"[NOTIFICACAO] FALHA - Nao foi possivel enviar para {NOTIFICACAO_PHONE}")

        return resultado
    except Exception as e:
        logger.error(f"[NOTIFICACAO] ERRO: {e}")
        logger.error(traceback.format_exc())
        return False


async def detectar_solicitacao_humano(message: str) -> bool:
    """Detecta se cliente esta pedindo atendente humano"""
    palavras_chave = [
        # Palavras principais
        "atendente", "humano", "pessoa", "operador",
        # Nomes dos atendentes
        "beatriz", "eduarda",
        # Frases comuns
        "falar com alguem", "falar com alguém",
        "falar com humano", "falar com atendente",
        "falar com uma pessoa", "falar com pessoa",
        "atendimento humano", "atendente humano",
        "quero falar", "preciso falar",
        "quero um atendente", "quero atendente",
        "preciso de atendente", "preciso atendente",
        "transferir", "transfere",
        # English
        "speak with someone", "talk to someone", "human agent",
        "real person", "speak to a person", "talk to a person",
        # Variações de frustração
        "nao entende", "não entende",
        "nao esta entendendo", "não está entendendo",
        "quero pessoa real", "pessoa de verdade",
        "falar com gente", "alguem real", "alguém real"
    ]

    message_lower = message.lower()
    return any(palavra in message_lower for palavra in palavras_chave)


async def transferir_para_humano(phone: str, motivo: str):
    """Transfere conversa para atendente humano"""
    try:
        # Atualizar estado do cliente para modo humano (fonte unica de verdade)
        await db.cliente_estados.update_one(
            {"phone": phone},
            {
                "$set": {
                    "mode": "human",
                    "transferred_at": datetime.now(),
                    "transfer_reason": motivo,
                    "updated_at": datetime.now()
                }
            },
            upsert=True
        )

        # Tambem atualizar na ultima conversa para compatibilidade
        await db.conversas.update_one(
            {"phone": phone},
            {"$set": {"mode": "human", "transferred_at": datetime.now()}},
            upsert=False
        )

        # Notificar atendente com dados completos do cliente
        await notificar_atendente(phone, motivo)

        logger.info(f"[TRANSFERENCIA] Conversa de {phone} transferida para humano (Motivo: {motivo})")
        return True

    except Exception as e:
        logger.error(f"[TRANSFERENCIA] Erro ao transferir para humano: {e}")
        logger.error(traceback.format_exc())
        return False


async def pausar_ia_para_cliente(phone: str):
    """Pausa a IA para um cliente especifico (comando *)"""
    try:
        await db.cliente_estados.update_one(
            {"phone": phone},
            {
                "$set": {
                    "mode": "human",
                    "paused_at": datetime.now(),
                    "paused_by": "operador",
                    "updated_at": datetime.now()
                }
            },
            upsert=True
        )
        logger.info(f"[OPERADOR] IA PAUSADA para cliente {phone}")
        return True
    except Exception as e:
        logger.error(f"[OPERADOR] Erro ao pausar IA: {e}")
        return False


async def retomar_ia_para_cliente(phone: str):
    """Retoma a IA para um cliente especifico (comando +)"""
    try:
        await db.cliente_estados.update_one(
            {"phone": phone},
            {
                "$set": {
                    "mode": "ia",
                    "resumed_at": datetime.now(),
                    "updated_at": datetime.now()
                },
                "$unset": {
                    "transferred_at": "",
                    "transfer_reason": "",
                    "paused_at": "",
                    "paused_by": ""
                }
            },
            upsert=True
        )
        logger.info(f"[OPERADOR] IA RETOMADA para cliente {phone}")
        return True
    except Exception as e:
        logger.error(f"[OPERADOR] Erro ao retomar IA: {e}")
        return False


async def verificar_modo_cliente(phone: str) -> str:
    """Verifica o modo atual do cliente (ia ou human)"""
    try:
        estado = await db.cliente_estados.find_one({"phone": phone})
        if estado:
            return estado.get("mode", "ia")
        return "ia"  # Padrao: IA ativa
    except Exception as e:
        logger.error(f"Erro ao verificar modo do cliente: {e}")
        return "ia"


async def verificar_timeout_modo_humano(phone: str) -> bool:
    """
    Verifica se o modo humano expirou (timeout).
    Se expirou, retorna a conversa para modo IA automaticamente.
    Retorna True se estava em timeout e foi resetado, False caso contrario.
    """
    from datetime import timedelta

    try:
        # Buscar estado do cliente
        estado = await db.cliente_estados.find_one({"phone": phone})

        if not estado or estado.get("mode") != "human":
            return False

        # Verificar quando foi transferido/pausado
        transferred_at = estado.get("transferred_at") or estado.get("paused_at")
        if not transferred_at:
            # Se nao tem timestamp, usar updated_at
            transferred_at = estado.get("updated_at", datetime.now())

        # Verificar se passou o timeout
        tempo_limite = transferred_at + timedelta(minutes=HUMAN_MODE_TIMEOUT_MINUTES)

        if datetime.now() > tempo_limite:
            # Timeout expirou - resetar para IA
            await retomar_ia_para_cliente(phone)
            logger.info(f"[TIMEOUT] Cliente {phone} retornou para IA apos {HUMAN_MODE_TIMEOUT_MINUTES} min sem interacao")
            return True

        return False

    except Exception as e:
        logger.error(f"Erro ao verificar timeout: {e}")
        return False


# ============================================================
# FUNCAO: DETECTAR CONVERSAO (PAGAMENTO)
# ============================================================
async def detectar_conversao(phone: str, message: str) -> bool:
    """Detecta se mensagem indica conversao (pagamento realizado)"""
    try:
        # Palavras-chave de conversao
        keywords = ["paguei", "transferi", "pix", "pagamento", "transferencia", "depositei", "enviei o pagamento"]

        message_lower = message.lower()

        # Verificar palavras-chave
        for keyword in keywords:
            if keyword in message_lower:
                logger.info(f"CONVERSAO DETECTADA por palavra-chave '{keyword}' - {phone}")

                # Salvar conversao no MongoDB
                await db.conversoes.insert_one({
                    "phone": phone,
                    "message": message,
                    "detection_method": "keyword",
                    "keyword": keyword,
                    "timestamp": datetime.now(),
                    "canal": "WhatsApp"
                })

                return True

        # Verificar se ha valor monetario na mensagem
        # Padroes: R$ 100, R$100, 100 reais, $100
        money_patterns = [
            r'R\$\s*\d+[.,]?\d*',
            r'\d+[.,]?\d*\s*reais',
            r'\$\s*\d+[.,]?\d*'
        ]

        for pattern in money_patterns:
            if re.search(pattern, message_lower):
                # Buscar ultimo orcamento enviado
                last_quote = await db.conversas.find_one(
                    {
                        "phone": phone,
                        "role": "assistant",
                        "message": {"$regex": "R\\$", "$options": "i"}
                    },
                    sort=[("timestamp", -1)]
                )

                if last_quote:
                    logger.info(f"CONVERSAO DETECTADA por valor monetario - {phone}")

                    await db.conversoes.insert_one({
                        "phone": phone,
                        "message": message,
                        "detection_method": "value_match",
                        "last_quote": last_quote.get("message", ""),
                        "timestamp": datetime.now(),
                        "canal": "WhatsApp"
                    })

                    return True

        return False

    except Exception as e:
        logger.error(f"Erro ao detectar conversao: {str(e)}")
        return False


# ============================================================
# FUNCAO: HYBRID LEARNING - SUGERIR CONHECIMENTO
# ============================================================
async def analisar_e_sugerir_conhecimento(phone: str, user_message: str, bot_response: str):
    """Analisa conversa e sugere novo conhecimento se IA nao soube responder bem"""
    try:
        # Detectar sinais de que IA nao soube responder
        sinais_incerteza = [
            "nao tenho certeza", "nao sei", "nao posso", "desculpe",
            "nao consigo", "nao tenho essa informacao", "nao tenho acesso"
        ]

        response_lower = bot_response.lower()

        # Se IA demonstrou incerteza, sugerir novo conhecimento
        if any(sinal in response_lower for sinal in sinais_incerteza):
            logger.info(f"IA demonstrou incerteza - gerando sugestao de conhecimento")

            # Gerar sugestao usando GPT-4
            suggestion_prompt = f"""Analise esta conversa e sugira um novo conhecimento para a base de dados:

PERGUNTA DO CLIENTE: {user_message}
RESPOSTA DA IA: {bot_response}

Gere uma sugestao de conhecimento no formato:
TITULO: [titulo curto e descritivo]
CONTEUDO: [explicacao completa e profissional]

Seja especifico e util. Baseie-se na pergunta do cliente."""

            suggestion_response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Voce e um assistente que ajuda a criar base de conhecimento."},
                    {"role": "user", "content": suggestion_prompt}
                ],
                max_tokens=500
            )

            suggestion_text = suggestion_response.choices[0].message.content

            # Extrair titulo e conteudo
            lines = suggestion_text.split('\n')
            title = ""
            content = ""

            for line in lines:
                if line.startswith("TITULO:"):
                    title = line.replace("TITULO:", "").strip()
                elif line.startswith("CONTEUDO:"):
                    content = line.replace("CONTEUDO:", "").strip()
                elif content:
                    content += "\n" + line

            if not title or not content:
                # Fallback: usar texto completo
                title = f"Duvida sobre: {user_message[:50]}..."
                content = suggestion_text

            # Salvar sugestao no MongoDB
            await db.knowledge_suggestions.insert_one({
                "title": title,
                "content": content.strip(),
                "user_question": user_message,
                "bot_response": bot_response,
                "phone": phone,
                "status": "pending",  # pending, approved, rejected
                "created_at": datetime.now(),
                "approved_at": None,
                "approved_by": None
            })

            logger.info(f"Sugestao de conhecimento salva: {title}")
            return True

        return False

    except Exception as e:
        logger.error(f"Erro ao sugerir conhecimento: {str(e)}")
        logger.error(traceback.format_exc())
        return False


# ============================================================
# ============================================================
# SISTEMA DE DEDUPLICACAO DE MENSAGENS
# ============================================================
# Cache para evitar processar a mesma mensagem mais de uma vez
# (Z-API pode reenviar se o webhook demorar)
mensagens_processadas = {}
imagens_processadas = {}  # Cache para dedup de imagens por URL
pos_pagamento_respondido = {}  # Cache para dedup de respostas pos-pagamento por phone
DEDUP_TIMEOUT_SEGUNDOS = 60  # Manter messageId por 60 segundos


def verificar_mensagem_duplicada(message_id: str) -> bool:
    """
    Verifica se mensagem ja foi processada.
    Retorna True se for duplicada, False se for nova.
    """
    if not message_id:
        return False  # Sem messageId, processar normalmente

    agora = datetime.now()

    # Limpar mensagens antigas do cache (mais de 60 segundos)
    ids_para_remover = []
    for mid, timestamp in mensagens_processadas.items():
        if (agora - timestamp).total_seconds() > DEDUP_TIMEOUT_SEGUNDOS:
            ids_para_remover.append(mid)

    for mid in ids_para_remover:
        del mensagens_processadas[mid]

    # Verificar se mensagem ja foi processada
    if message_id in mensagens_processadas:
        logger.warning(f"[DEDUP] Mensagem duplicada ignorada: {message_id}")
        return True

    # Marcar como processada
    mensagens_processadas[message_id] = agora
    return False


def verificar_imagem_duplicada(image_url: str) -> bool:
    """
    Verifica se uma imagem com essa URL ja foi processada recentemente.
    Previne que Z-API reenvie a mesma imagem em webhooks diferentes.
    """
    if not image_url:
        return False

    agora = datetime.now()

    # Limpar URLs antigas (mais de 30 segundos)
    urls_para_remover = []
    for url, timestamp in imagens_processadas.items():
        if (agora - timestamp).total_seconds() > 30:
            urls_para_remover.append(url)
    for url in urls_para_remover:
        del imagens_processadas[url]

    if image_url in imagens_processadas:
        logger.warning(f"[DEDUP-IMG] Imagem duplicada ignorada (URL): {image_url[:60]}")
        return True

    imagens_processadas[image_url] = agora
    return False


# ============================================================
# SISTEMA DE AGRUPAMENTO DE IMAGENS
# ============================================================
image_sessions = {}  # Cache temporário de sessões de imagem

async def iniciar_sessao_imagem(phone: str):
    """Inicia sessão de agrupamento de imagens"""
    image_sessions[phone] = {
        "count": 0,
        "images": [],
        "image_urls": set(),  # Track URLs to prevent duplicate counting
        "last_received": datetime.now(),
        "waiting_confirmation": False,
        "already_asked": False
    }
    logger.info(f"Sessão de imagem iniciada: {phone}")


async def adicionar_imagem_sessao(phone: str, image_bytes: bytes, image_url: str = ""):
    """Adiciona imagem à sessão e retorna se deve processar"""
    if phone not in image_sessions:
        await iniciar_sessao_imagem(phone)

    session = image_sessions[phone]

    # Deduplicação por URL da imagem - Z-API pode enviar múltiplos webhooks para a mesma imagem
    if image_url and image_url in session["image_urls"]:
        logger.warning(f"[DEDUP-IMG] Imagem duplicada ignorada para {phone}: {image_url[:50]}")
        # Ainda aguardar para manter o timer correto
        await asyncio.sleep(4)
        time_diff = (datetime.now() - session["last_received"]).total_seconds()
        if time_diff >= 3.5:
            session["waiting_confirmation"] = True
            return True
        return False

    if image_url:
        session["image_urls"].add(image_url)

    session["count"] += 1
    session["images"].append(image_bytes)
    session["last_received"] = datetime.now()

    logger.info(f"Imagem {session['count']} adicionada à sessão de {phone}")
    
    # Aguardar 4 segundos para ver se vem mais imagens
    await asyncio.sleep(4)
    
    # Verificar se ainda é a última imagem (nenhuma nova chegou)
    time_diff = (datetime.now() - session["last_received"]).total_seconds()
    
    if time_diff >= 3.5:  # Se passaram 3.5s sem nova imagem
        session["waiting_confirmation"] = True
        return True  # Hora de perguntar
    
    return False  # Ainda aguardando mais imagens


async def analisar_documento_inteligente(phone: str, image_bytes: bytes, total_pages: int) -> dict:
    """Analisa documento com GPT-4 Vision e retorna informacoes estruturadas"""
    try:
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": """Voce e um analisador de documentos. Analise a imagem e retorne APENAS um JSON com:
{
    "tipo_documento": "historico escolar / diploma / certidao / contrato / etc",
    "idioma_origem": "portugues / ingles / espanhol / etc",
    "idioma_destino_sugerido": "ingles / portugues / etc",
    "descricao_curta": "breve descricao do documento em 10 palavras"
}
Retorne APENAS o JSON, sem texto adicional."""
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analise este documento:"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=200
        )

        resultado = response.choices[0].message.content
        # Tentar extrair JSON
        import json as json_lib
        try:
            # Limpar possíveis caracteres extras
            resultado = resultado.strip()
            if resultado.startswith("```"):
                resultado = resultado.split("```")[1]
                if resultado.startswith("json"):
                    resultado = resultado[4:]
            return json_lib.loads(resultado)
        except:
            return {
                "tipo_documento": "documento",
                "idioma_origem": "a identificar",
                "idioma_destino_sugerido": "ingles",
                "descricao_curta": "documento para traducao"
            }
    except Exception as e:
        logger.error(f"Erro ao analisar documento: {e}")
        return {
            "tipo_documento": "documento",
            "idioma_origem": "a identificar",
            "idioma_destino_sugerido": "ingles",
            "descricao_curta": "documento para traducao"
        }


async def processar_sessao_imagem(phone: str):
    """Processa todas as imagens da sessão - Analise e gerar orcamento direto"""
    if phone not in image_sessions:
        return None

    session = image_sessions[phone]
    total_pages = session["count"]
    first_image = session["images"][0]

    # Buscar estado do cliente
    estado = await get_cliente_estado(phone)
    idioma = estado.get("idioma", "pt")

    # Analisar documento inteligentemente
    analise = await analisar_documento_inteligente(phone, first_image, total_pages)

    # Guardar informacoes do documento no estado (ir direto para orcamento, sem pedir nome)
    await set_cliente_estado(
        phone,
        documento_info={
            "total_pages": total_pages,
            "tipo": analise.get("tipo_documento", "documento"),
            "idioma_origem": analise.get("idioma_origem", "a identificar"),
            "idioma_destino": analise.get("idioma_destino_sugerido", "ingles"),
            "descricao": analise.get("descricao_curta", "documento")
        }
    )

    # Montar mensagem de boas-vindas personalizada baseada no idioma detectado
    tipo_doc = analise.get("tipo_documento", "documento")
    idioma_origem = analise.get("idioma_origem", "")
    idioma_destino = analise.get("idioma_destino_sugerido", "ingles")

    # Saudacao + info do documento (sem pedir nome)
    if total_pages == 1:
        if idioma == "en":
            saudacao = (
                f"Hello! I'm MIA, Legacy Translations' virtual assistant! 🌎\n\n"
                f"I see you sent a {tipo_doc} in {idioma_origem}.\n\n"
            )
        elif idioma == "es":
            saudacao = (
                f"¡Hola! Soy MIA, asistente virtual de Legacy Translations! 🌎\n\n"
                f"Veo que enviaste un {tipo_doc} en {idioma_origem}.\n\n"
            )
        else:
            saudacao = (
                f"Ola! Sou a MIA, assistente virtual da Legacy Translations! 🌎\n\n"
                f"Vi que voce enviou um {tipo_doc} em {idioma_origem}.\n\n"
            )
    else:
        if idioma == "en":
            saudacao = (
                f"Hello! I'm MIA, Legacy Translations' virtual assistant! 🌎\n\n"
                f"I see you sent {total_pages} pages of a {tipo_doc} in {idioma_origem}.\n\n"
            )
        elif idioma == "es":
            saudacao = (
                f"¡Hola! Soy MIA, asistente virtual de Legacy Translations! 🌎\n\n"
                f"Veo que enviaste {total_pages} páginas de un {tipo_doc} en {idioma_origem}.\n\n"
            )
        else:
            saudacao = (
                f"Ola! Sou a MIA, assistente virtual da Legacy Translations! 🌎\n\n"
                f"Vi que voce enviou {total_pages} paginas de um {tipo_doc} em {idioma_origem}.\n\n"
            )

    # Salvar no banco
    await db.conversas.insert_one({
        "phone": phone,
        "message": f"[{total_pages} IMAGENS ENVIADAS - {tipo_doc}]",
        "role": "user",
        "timestamp": datetime.now(),
        "canal": "WhatsApp",
        "type": "image_batch"
    })

    # Limpar sessão de imagens (ja salvamos no estado)
    del image_sessions[phone]

    # Gerar orcamento direto (sem pedir nome)
    orcamento = await gerar_orcamento_final(phone)
    mensagem = saudacao + orcamento

    await db.conversas.insert_one({
        "phone": phone,
        "message": mensagem,
        "role": "assistant",
        "timestamp": datetime.now(),
        "canal": "WhatsApp"
    })

    logger.info(f"Orcamento gerado direto para {phone} ({total_pages} paginas)")
    return mensagem


async def gerar_orcamento_final(phone: str) -> str:
    """Gera o orcamento final apos coletar nome e origem"""
    estado = await get_cliente_estado(phone)
    doc_info = estado.get("documento_info", {})
    idioma = estado.get("idioma", "pt")
    nome = estado.get("nome", "")

    total_pages = doc_info.get("total_pages", 1)
    if not total_pages or total_pages < 1:
        total_pages = 1
    tipo_doc = doc_info.get("tipo", "documento")
    idioma_origem = doc_info.get("idioma_origem", "")
    idioma_destino = doc_info.get("idioma_destino", "ingles")

    # Buscar treinamento para obter valores
    training_prompt = await get_bot_training()

    # Chamar GPT para gerar orcamento
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": f"""{training_prompt}

TAREFA: Gerar orcamento para traducao.
Cliente: {nome}
Documento: {tipo_doc}
Total de paginas: {total_pages}
Idioma origem: {idioma_origem}
Idioma destino: {idioma_destino}

IMPORTANTE:
- Responda no idioma: {'ingles' if idioma == 'en' else 'espanhol' if idioma == 'es' else 'portugues'}
- Seja cordial e use o nome do cliente
- Inclua: valor total, prazo, forma de pagamento
- Pergunte se deseja prosseguir"""
            },
            {
                "role": "user",
                "content": f"Gere o orcamento para {nome} traduzir {total_pages} paginas de {tipo_doc}"
            }
        ],
        max_tokens=600
    )

    orcamento = response.choices[0].message.content

    # Extrair valor TOTAL do orcamento (buscar padrao $XX.XX ou R$XX,XX)
    # Prioridade: valor perto de "total" > maior valor encontrado > primeiro valor
    import re

    # Tentar encontrar valor perto de palavras "total" / "totalizando"
    valor_total_match = re.search(
        r'(?:total(?:izando)?|total\s*(?:value|price|cost)?)\s*[:\s]*[\$R]\$?\s*(\d+[.,]?\d*)',
        orcamento, re.IGNORECASE
    )
    if not valor_total_match:
        # Tentar formato inverso: $XX.XX ... total
        valor_total_match = re.search(
            r'[\$R]\$?\s*(\d+[.,]?\d*)\s*(?:\(?\s*total\s*\)?)',
            orcamento, re.IGNORECASE
        )

    if valor_total_match:
        valor_str = valor_total_match.group(0).strip()
        # Limpar prefixo de texto antes do $
        clean_match = re.search(r'[\$R]\$?\s*\d+[.,]?\d*', valor_str)
        if clean_match:
            valor_str = clean_match.group(0)
    else:
        # Se nao achou "total", pegar o MAIOR valor (provavelmente o total)
        todos_valores = re.findall(r'[\$R]\$?\s*(\d+[.,]?\d*)', orcamento)
        if todos_valores:
            maior_valor = 0.0
            maior_str = ""
            for v in todos_valores:
                try:
                    num = float(v.replace(',', '.'))
                    if num > maior_valor:
                        maior_valor = num
                        maior_str = v
                except:
                    pass
            valor_str = f"${maior_str}" if maior_str else "0"
        else:
            valor_str = "0"

    # Converter valor para float
    try:
        valor_num = float(re.sub(r'[^\d.,]', '', valor_str).replace(',', '.').strip())
    except:
        valor_num = 0.0

    # Atualizar estado
    await set_cliente_estado(
        phone,
        etapa=ETAPAS["AGUARDANDO_CONFIRMACAO"],
        ultimo_orcamento=orcamento,
        valor_orcamento=valor_str
    )

    # ============================================
    # SALVAR ORCAMENTO NA COLLECTION ORCAMENTOS
    # ============================================
    try:
        await db.orcamentos.insert_one({
            "phone": phone,
            "nome": nome,
            "documento_tipo": tipo_doc,
            "documento_paginas": total_pages,
            "idioma_origem": idioma_origem,
            "idioma_destino": idioma_destino,
            "valor": valor_num,
            "valor_texto": valor_str,
            "orcamento_texto": orcamento,
            "origem_cliente": estado.get("origem", ""),
            "status": "pendente",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        })
        logger.info(f"[ORCAMENTO] Salvo para {phone}: {valor_str}")
    except Exception as e:
        logger.error(f"Erro ao salvar orcamento: {e}")

    return orcamento


async def processar_etapa_nome(phone: str, mensagem: str) -> str:
    """Processa resposta do cliente com o nome e pede a origem"""
    # Buscar idioma ja salvo no estado (detectado na mensagem inicial)
    estado = await get_cliente_estado(phone)
    idioma = estado.get("idioma")

    # Se nao tiver idioma salvo, detectar do nome (fallback)
    if not idioma:
        idioma = detectar_idioma(mensagem)

    # PRIMEIRO: verificar se o cliente esta pedindo atendente humano
    # ao inves de informar o nome
    if await detectar_solicitacao_humano(mensagem):
        await transferir_para_humano(phone, "Cliente solicitou atendente (etapa nome)")
        if idioma == "en":
            return "Of course! I'm forwarding you to our team. A representative will get in touch with you as soon as possible. 😊"
        elif idioma == "es":
            return "¡Por supuesto! Te estoy transfiriendo a nuestro equipo. Un representante se pondrá en contacto contigo lo antes posible. 😊"
        else:
            return "Claro! Estou encaminhando voce para nossa equipe. Um atendente entrara em contato o mais breve possivel. 😊"

    # Extrair nome da mensagem (remover frases como "meu nome e", "my name is", etc)
    nome = mensagem.strip().split('\n')[0].strip()
    # Limpar pontuacao
    nome = nome.rstrip('.,!?')

    # Remover padroes comuns onde o cliente diz o nome com uma frase
    nome_limpo = re.sub(
        r"^(meu nome [eé]|me chamo|eu sou a?|sou a?|my name is|i['\u2019]?m|me llamo|mi nombre es|yo soy)\s+",
        '', nome, flags=re.IGNORECASE
    ).strip()
    if nome_limpo:
        nome = nome_limpo

    # Remover parte de confirmacao de paginas do nome (ex: "Rafaela, 3 paginas" -> "Rafaela")
    nome = re.sub(
        r'[,.]?\s*\d+\s*(?:paginas?|páginas?|pages?|págs?)\b.*$',
        '', nome, flags=re.IGNORECASE
    ).strip()
    nome = re.sub(
        r'[,.]?\s*(?:sao|são|are|son)\s+\d+\s*(?:paginas?|páginas?|pages?|págs?)\b.*$',
        '', nome, flags=re.IGNORECASE
    ).strip()

    # Capitalizar corretamente
    nome = nome.strip().title()

    # Se for muito longo, pegar primeiras palavras
    if len(nome.split()) > 4:
        nome = ' '.join(nome.split()[:3])

    # Validar que o nome nao contem palavras que nao sao nomes
    palavras_invalidas_nome = [
        "humano", "atendente", "falar", "traduzir", "traducao", "tradução",
        "pagina", "página", "documento", "comprovante", "pagamento",
        "transferir", "operador", "pessoa", "ajuda", "help",
        "human", "agent", "translate", "translation", "page", "document",
        "beatriz", "eduarda",
        # Perguntas e frases comuns que nao sao nomes
        "valor", "preco", "preço", "price", "quanto", "custa", "custo",
        "como", "qual", "onde", "quando", "quero", "preciso", "gostaria",
        "vocês", "voces", "fazem", "podem", "conseguem",
        "what", "how", "where", "when", "much", "cost",
        "need", "want", "would", "could", "please",
        "orcamento", "orçamento", "quote", "budget",
        "prazo", "demora", "tempo", "urgente", "urgencia",
        "enviar", "mandar", "email", "site", "website", "portal",
        "bom dia", "boa tarde", "boa noite", "ola", "olá", "hello", "hi",
        "obrigado", "obrigada", "thanks", "thank",
        "sim", "nao", "yes", "no", "si",
        "certified", "sworn", "juramentada", "certificada",
        # Erros e correcoes
        "errado", "errei", "desculpa", "desculpe", "sorry", "wrong", "mistake",
        "mandei", "enviei", "ignore", "ignora", "cancel", "cancela"
    ]
    nome_lower = nome.lower()
    nome_parece_invalido = any(p in nome_lower for p in palavras_invalidas_nome)

    # Rejeitar tambem se contem "?" (e uma pergunta, nao um nome)
    if "?" in mensagem:
        nome_parece_invalido = True

    if nome_parece_invalido or len(nome) < 2:
        # Nome parece invalido - pedir novamente
        if idioma == "en":
            return "Could you tell me your name so we can continue? 😊"
        elif idioma == "es":
            return "¿Podría decirme su nombre para continuar la atención? 😊"
        else:
            return "Poderia dizer seu nome para continuar o atendimento? 😊"

    # Verificar se o cliente informou numero de paginas na mesma mensagem
    # Ex: "Rafaela, sao 3 paginas" ou "5 pages, my name is John"
    paginas_match = re.search(r'(\d+)\s*(?:paginas?|páginas?|pages?|págs?)', mensagem, re.IGNORECASE)
    if paginas_match:
        paginas_confirmadas = int(paginas_match.group(1))
        doc_info = estado.get("documento_info", {})
        if doc_info and paginas_confirmadas > 0:
            doc_info["total_pages"] = paginas_confirmadas
            await set_cliente_estado(phone, documento_info=doc_info)
            logger.info(f"[PAGES] Cliente {phone} confirmou {paginas_confirmadas} paginas")

    # Salvar nome e idioma (pular etapa de origem, ir direto para orcamento)
    await set_cliente_estado(
        phone,
        nome=nome,
        idioma=idioma
    )

    # Salvar no CRM
    try:
        await criar_ou_atualizar_contato(phone, {
            "nome": nome,
            "idioma": idioma
        })
    except Exception as e:
        logger.error(f"[CRM] Erro ao salvar contato: {e}")

    # Saudacao baseada no idioma (sem usar nome para evitar erros)
    if idioma == "en":
        saudacao = f"Nice to meet you! 😊\n\n"
    elif idioma == "es":
        saudacao = f"¡Mucho gusto! 😊\n\n"
    else:
        saudacao = f"Prazer em conhece-lo(a)! 😊\n\n"

    # Se fora do horario e sem documento, mostrar opcoes
    doc_info = estado.get("documento_info")
    if not is_business_hours() and not doc_info:
        await set_cliente_estado(phone, etapa=ETAPAS["AGUARDANDO_OPCAO_ATENDIMENTO"])

        if idioma == "en":
            opcoes = (
                f"{saudacao}"
                f"How would you like to proceed?\n\n"
                f"1️⃣ Continue the service right here\n"
                f"2️⃣ Place my order through the website\n"
                f"3️⃣ I'd like to speak with a representative\n\n"
                f"Just reply with the number!"
            )
        elif idioma == "es":
            opcoes = (
                f"{saudacao}"
                f"¿Cómo prefieres continuar?\n\n"
                f"1️⃣ Continuar la atención aquí\n"
                f"2️⃣ Hacer mi pedido por el sitio web\n"
                f"3️⃣ Quiero hablar con un representante\n\n"
                f"¡Solo responde con el número!"
            )
        else:
            opcoes = (
                f"{saudacao}"
                f"Como voce prefere prosseguir?\n\n"
                f"1️⃣ Continuar o atendimento aqui\n"
                f"2️⃣ Fazer meu pedido pelo website\n"
                f"3️⃣ Quero falar com um atendente\n\n"
                f"Responda com o numero!"
            )
        return opcoes

    # Fluxo normal: gerar orcamento direto
    orcamento = await gerar_orcamento_final(phone)
    return saudacao + orcamento


async def processar_etapa_origem(phone: str, mensagem: str) -> str:
    """Processa resposta da origem e gera orcamento (ou opcoes fora do horario)"""
    estado = await get_cliente_estado(phone)
    idioma = estado.get("idioma", "pt")
    nome = estado.get("nome", "")

    # Detectar origem
    msg_lower = mensagem.lower()
    if "1" in mensagem or "google" in msg_lower:
        origem = "Google"
    elif "2" in mensagem or "instagram" in msg_lower or "insta" in msg_lower:
        origem = "Instagram"
    elif "3" in mensagem or "facebook" in msg_lower or "face" in msg_lower:
        origem = "Facebook"
    elif "4" in mensagem or "amigo" in msg_lower or "friend" in msg_lower or "referencia" in msg_lower:
        origem = "Referencia de amigo"
    else:
        origem = mensagem.strip()[:50]

    # Salvar origem no estado do cliente
    await set_cliente_estado(phone, origem=origem)

    # Salvar origem no CRM (aba MIA)
    try:
        await criar_ou_atualizar_contato(phone, {
            "nome": nome,
            "origem": origem,
            "idioma": idioma
        })
        logger.info(f"[CRM] Origem '{origem}' salva para cliente {phone}")
    except Exception as e:
        logger.error(f"[CRM] Erro ao salvar origem: {e}")

    # Agradecer baseado no idioma
    if idioma == "en":
        agradecimento = f"Thank you! Great to know you found us through {origem}. 🙏\n\n"
    elif idioma == "es":
        agradecimento = f"¡Gracias! Que bueno saber que nos encontraste por {origem}. 🙏\n\n"
    else:
        agradecimento = f"Obrigada! Que bom saber que nos conheceu pelo {origem}. 🙏\n\n"

    # Se fora do horario comercial E cliente nao tem documento ainda, apresentar opcoes
    doc_info = estado.get("documento_info")
    if not is_business_hours() and not doc_info:
        await set_cliente_estado(phone, etapa=ETAPAS["AGUARDANDO_OPCAO_ATENDIMENTO"])

        if idioma == "en":
            opcoes = (
                f"{agradecimento}"
                f"How would you like to proceed?\n\n"
                f"1️⃣ Continue the service right here\n"
                f"2️⃣ Place my order through the website\n"
                f"3️⃣ I'd like to speak with a representative\n\n"
                f"Just reply with the number!"
            )
        elif idioma == "es":
            opcoes = (
                f"{agradecimento}"
                f"¿Cómo prefieres continuar?\n\n"
                f"1️⃣ Continuar la atención aquí\n"
                f"2️⃣ Hacer mi pedido por el sitio web\n"
                f"3️⃣ Quiero hablar con un representante\n\n"
                f"¡Solo responde con el número!"
            )
        else:
            opcoes = (
                f"{agradecimento}"
                f"Como voce prefere prosseguir?\n\n"
                f"1️⃣ Continuar o atendimento aqui\n"
                f"2️⃣ Fazer meu pedido pelo website\n"
                f"3️⃣ Quero falar com um atendente\n\n"
                f"Responda com o numero!"
            )
        return opcoes

    # Fluxo normal (horario comercial ou ja tem documento): gerar orcamento
    orcamento = await gerar_orcamento_final(phone)

    return agradecimento + orcamento


async def processar_etapa_opcao_atendimento(phone: str, mensagem: str) -> str:
    """Processa a escolha do cliente entre as 3 opcoes de atendimento (fora do horario)"""
    estado = await get_cliente_estado(phone)
    idioma = estado.get("idioma", "pt")
    nome = estado.get("nome", "")

    msg_lower = mensagem.lower().strip()

    # Opcao 1: Continuar atendimento aqui
    if "1" in mensagem or "continuar" in msg_lower or "aqui" in msg_lower or "here" in msg_lower or "continue" in msg_lower or "aquí" in msg_lower:
        # Voltar para etapa inicial para receber documentos
        await set_cliente_estado(phone, etapa=ETAPAS["INICIAL"])

        if idioma == "en":
            return (
                f"Great! 😊\n\n"
                f"You can send the document you'd like to have translated right here.\n\n"
                f"Just send a photo or PDF of each page and I'll take care of everything!"
            )
        elif idioma == "es":
            return (
                f"¡Perfecto! 😊\n\n"
                f"Puedes enviar el documento que deseas traducir aquí mismo.\n\n"
                f"¡Solo envía una foto o PDF de cada página y yo me encargo de todo!"
            )
        else:
            return (
                f"Perfeito! 😊\n\n"
                f"Pode enviar o documento que deseja traduzir aqui mesmo.\n\n"
                f"E so mandar uma foto ou PDF de cada pagina que eu cuido de tudo!"
            )

    # Opcao 2: Fazer pelo website
    elif "2" in mensagem or "website" in msg_lower or "site" in msg_lower or "web" in msg_lower or "online" in msg_lower:
        await set_cliente_estado(phone, etapa=ETAPAS["INICIAL"])

        if idioma == "en":
            return (
                f"Sure! You can place your order directly on our website:\n\n"
                f"👉 https://portal.legacytranslations.com\n\n"
                f"If you need any help, just send a message here. 😊"
            )
        elif idioma == "es":
            return (
                f"¡Claro! Puedes hacer tu pedido directamente en nuestro sitio web:\n\n"
                f"👉 https://portal.legacytranslations.com\n\n"
                f"Si necesitas ayuda, solo envía un mensaje aquí. 😊"
            )
        else:
            return (
                f"Claro! Voce pode fazer seu pedido diretamente pelo nosso site:\n\n"
                f"👉 https://portal.legacytranslations.com\n\n"
                f"Se precisar de ajuda, e so mandar uma mensagem aqui. 😊"
            )

    # Opcao 3: Falar com atendente
    elif "3" in mensagem or "atendente" in msg_lower or "humano" in msg_lower or "representante" in msg_lower or "speak" in msg_lower or "hablar" in msg_lower or "agent" in msg_lower or "person" in msg_lower:
        # Transferir para humano
        await transferir_para_humano(phone, f"Cliente solicitou atendente (fora do horario)")

        if idioma == "en":
            return (
                f"Of course! I'm forwarding you to our team right now.\n\n"
                f"A representative will get in touch with you as soon as possible. 😊"
            )
        elif idioma == "es":
            return (
                f"¡Por supuesto! Te estoy transfiriendo a nuestro equipo.\n\n"
                f"Un representante se pondrá en contacto contigo lo antes posible. 😊"
            )
        else:
            return (
                f"Claro! Estou encaminhando voce para nossa equipe.\n\n"
                f"Um atendente entrara em contato o mais breve possivel. 😊"
            )

    # Resposta nao reconhecida - repetir opcoes
    else:
        if idioma == "en":
            return (
                f"Could you please choose one of the options?\n\n"
                f"1️⃣ Continue the service right here\n"
                f"2️⃣ Place my order through the website\n"
                f"3️⃣ I'd like to speak with a representative\n\n"
                f"Just reply with the number!"
            )
        elif idioma == "es":
            return (
                f"¿Podrías elegir una de las opciones?\n\n"
                f"1️⃣ Continuar la atención aquí\n"
                f"2️⃣ Hacer mi pedido por el sitio web\n"
                f"3️⃣ Quiero hablar con un representante\n\n"
                f"¡Solo responde con el número!"
            )
        else:
            return (
                f"Poderia escolher uma das opcoes?\n\n"
                f"1️⃣ Continuar o atendimento aqui\n"
                f"2️⃣ Fazer meu pedido pelo website\n"
                f"3️⃣ Quero falar com um atendente\n\n"
                f"Responda com o numero!"
            )


async def processar_etapa_confirmacao(phone: str, mensagem: str) -> str:
    """Processa confirmacao do cliente e muda para aguardando pagamento"""
    estado = await get_cliente_estado(phone)
    idioma = estado.get("idioma", "pt")
    nome = estado.get("nome", "")
    valor = estado.get("valor_orcamento", "")

    # Verificar se valor eh zero ou invalido de forma robusta
    valor_invalido = False
    if not valor:
        valor_invalido = True
    else:
        # Limpar valor e verificar se eh zero
        try:
            import re
            valor_numerico = float(re.sub(r'[^\d.,]', '', str(valor)).replace(',', '.') or '0')
            if valor_numerico <= 0:
                valor_invalido = True
        except (ValueError, TypeError):
            valor_invalido = True

    # Se o valor estiver vazio ou zero, recalcular baseado no documento
    if valor_invalido:
        doc_info = estado.get("documento_info", {})
        total_pages = doc_info.get("total_pages", 1)
        if not total_pages or total_pages < 1:
            total_pages = 1
        # Preco padrao: $24.99 por pagina
        valor_calculado = total_pages * 24.99
        valor = f"${valor_calculado:.2f}"
        await set_cliente_estado(phone, valor_orcamento=valor)
        logger.warning(f"[ORCAMENTO] Valor era invalido - recalculado para {valor} ({total_pages} paginas)")

    if detectar_confirmacao_prosseguimento(mensagem):
        # Cliente confirmou - mudar para aguardando pagamento
        await set_cliente_estado(phone, etapa=ETAPAS["AGUARDANDO_PAGAMENTO"])

        # Atualizar status do orcamento para CONFIRMADO
        try:
            await db.orcamentos.update_one(
                {"phone": phone, "status": "pendente"},
                {"$set": {"status": "confirmado", "updated_at": datetime.now()}},
            )
            logger.info(f"[ORCAMENTO] Status atualizado para CONFIRMADO: {phone}")
        except Exception as e:
            logger.error(f"Erro ao atualizar status do orcamento: {e}")

        # Montar saudacao (sem nome se nao tiver)
        if idioma == "en":
            saudacao = f"Perfect{', ' + nome if nome else ''}! 🎉"
            resposta = (
                f"{saudacao}\n\n"
                f"To proceed, please send the payment of {valor} via:\n\n"
                f"VENMO: @legacytranslations\n"
                f"ZELLE: Contact@legacytranslations.com (LEGACY TRANSLATIONS INC)\n\n"
                f"After payment, just send the receipt/screenshot here and I'll confirm! ✅"
            )
        elif idioma == "es":
            saudacao = f"¡Perfecto{', ' + nome if nome else ''}! 🎉"
            resposta = (
                f"{saudacao}\n\n"
                f"Para continuar, envía el pago de {valor} por:\n\n"
                f"VENMO: @legacytranslations\n"
                f"ZELLE: Contact@legacytranslations.com (LEGACY TRANSLATIONS INC)\n\n"
                f"Después del pago, solo envía el comprobante aquí y confirmo! ✅"
            )
        else:
            saudacao = f"Perfeito{', ' + nome if nome else ''}! 🎉"
            resposta = (
                f"{saudacao}\n\n"
                f"Para concluir o processo, basta efetuar o pagamento de {valor} atraves de um dos meios abaixo:\n\n"
                f"VENMO: @legacytranslations\n"
                f"ZELLE: Contact@legacytranslations.com (LEGACY TRANSLATIONS INC)\n\n"
                f"Apos o pagamento, e so enviar o comprovante aqui que eu confirmo! ✅"
            )
        return resposta
    else:
        # Nao confirmou ainda - processar normalmente com IA
        return None


async def processar_etapa_pagamento(phone: str, mensagem: str, is_image: bool = False, image_bytes: bytes = None) -> str:
    """Processa na etapa de aguardando pagamento"""
    estado = await get_cliente_estado(phone)
    idioma = estado.get("idioma", "pt")
    nome = estado.get("nome", "")
    valor = estado.get("valor_orcamento", "")

    # Verificar se valor eh zero ou invalido - recalcular se necessario
    import re as re_pag
    try:
        val_check = float(re_pag.sub(r'[^\d.,]', '', str(valor)).replace(',', '.') or '0')
    except:
        val_check = 0.0
    if val_check <= 0:
        doc_info = estado.get("documento_info", {})
        total_pages = doc_info.get("total_pages", 1) if doc_info else 1
        if not total_pages or total_pages < 1:
            total_pages = 1
        valor = f"${total_pages * 24.99:.2f}"
        await set_cliente_estado(phone, valor_orcamento=valor)
        logger.warning(f"[PAGAMENTO] Valor era invalido - recalculado para {valor}")

    # Se recebeu imagem ou PDF, tratar como comprovante
    if is_image and image_bytes:
        # Analisar se parece comprovante
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": """Analise se esta imagem e um comprovante de pagamento.
Procure por: valores, datas, nomes de bancos, apps de pagamento (Zelle, Venmo, PayPal, PIX),
numeros de transacao, confirmacoes.
Responda APENAS: SIM ou NAO"""
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Esta imagem e um comprovante de pagamento?"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=10
        )

        parece_comprovante = "sim" in response.choices[0].message.content.lower()

        if parece_comprovante:
            if idioma == "en":
                return (
                    f"I received the receipt! 📄\n\n"
                    f"Just confirming: is this the payment of {valor} for the translation order above?\n\n"
                    f"Reply YES to confirm or NO if it's something else."
                )
            elif idioma == "es":
                return (
                    f"¡Recibí el comprobante! 📄\n\n"
                    f"Solo confirmando: ¿es el pago de {valor} del pedido de traducción?\n\n"
                    f"Responde SI para confirmar o NO si es otra cosa."
                )
            else:
                return (
                    f"Recebi o comprovante! 📄\n\n"
                    f"So confirmando: e o pagamento de {valor} referente ao pedido de traducao acima?\n\n"
                    f"Responda SIM para confirmar ou NAO se for outra coisa."
                )
        else:
            # Nao parece comprovante - perguntar
            if idioma == "en":
                return (
                    f"I received an image! Is this a payment receipt or a new document for quote?\n\n"
                    f"Reply:\n• RECEIPT - if it's the payment confirmation\n• NEW DOCUMENT - if you want a new quote"
                )
            elif idioma == "es":
                return (
                    f"¡Recibí una imagen! ¿Es un comprobante de pago o un nuevo documento para cotizar?\n\n"
                    f"Responde:\n• COMPROBANTE - si es la confirmación de pago\n• NUEVO DOCUMENTO - si quieres nueva cotización"
                )
            else:
                return (
                    f"Recebi uma imagem! E um comprovante de pagamento ou um novo documento para orcamento?\n\n"
                    f"Responda:\n• COMPROVANTE - se for a confirmacao de pagamento\n• NOVO DOCUMENTO - se quiser novo orcamento"
                )

    # Processar texto
    msg_lower = mensagem.lower()

    # Verificar se confirmou o comprovante
    if any(x in msg_lower for x in ["sim", "yes", "si", "confirmo", "isso", "correto", "that's right"]):
        # Pagamento confirmado!
        await set_cliente_estado(phone, etapa=ETAPAS["PAGAMENTO_RECEBIDO"])
        doc_info = estado.get("documento_info", {})

        # Atualizar status do orcamento para PAGO
        try:
            await db.orcamentos.update_one(
                {"phone": phone, "status": {"$in": ["pendente", "confirmado"]}},
                {"$set": {"status": "pago", "updated_at": datetime.now()}},
            )
            logger.info(f"[ORCAMENTO] Status atualizado para PAGO: {phone}")
        except Exception as e:
            logger.error(f"Erro ao atualizar status do orcamento: {e}")

        # Notificar atendente sobre pagamento
        await notificar_atendente(phone, f"PAGAMENTO RECEBIDO - {nome} - {valor}")

        if idioma == "en":
            return (
                f"Payment confirmed! 🎉✅\n\n"
                f"Thank you! We'll start working on your translation right away.\n\n"
                f"📋 Order details:\n"
                f"• {doc_info.get('total_pages', 1)} page(s) of {doc_info.get('tipo', 'document')}\n"
                f"• From {doc_info.get('idioma_origem', '')} to {doc_info.get('idioma_destino', 'English')}\n\n"
                f"⏰ Estimated delivery: 2-3 business days\n"
                f"📧 We'll send the translation to your email.\n\n"
                f"Any questions, just message here! 😊"
            )
        elif idioma == "es":
            return (
                f"¡Pago confirmado! 🎉✅\n\n"
                f"¡Gracias! Comenzaremos tu traducción de inmediato.\n\n"
                f"📋 Detalles del pedido:\n"
                f"• {doc_info.get('total_pages', 1)} página(s) de {doc_info.get('tipo', 'documento')}\n"
                f"• De {doc_info.get('idioma_origem', '')} a {doc_info.get('idioma_destino', 'inglés')}\n\n"
                f"⏰ Entrega estimada: 2-3 días hábiles\n"
                f"📧 Enviaremos la traducción a tu email.\n\n"
                f"¡Cualquier duda, escribe aquí! 😊"
            )
        else:
            return (
                f"Pagamento confirmado! 🎉✅\n\n"
                f"Obrigada! Ja vamos iniciar sua traducao.\n\n"
                f"📋 Detalhes do pedido:\n"
                f"• {doc_info.get('total_pages', 1)} pagina(s) de {doc_info.get('tipo', 'documento')}\n"
                f"• De {doc_info.get('idioma_origem', '')} para {doc_info.get('idioma_destino', 'ingles')}\n\n"
                f"⏰ Prazo de entrega: 2-3 dias uteis\n"
                f"📧 Enviaremos a traducao para seu email.\n\n"
                f"Qualquer duvida, e so chamar aqui! 😊"
            )

    # Se disse NAO ou novo documento
    if any(x in msg_lower for x in ["nao", "no", "novo", "new", "another", "otro"]):
        # Resetar para inicial
        await set_cliente_estado(phone, etapa=ETAPAS["INICIAL"])
        if idioma == "en":
            return "No problem! Send the new document and I'll give you a quote. 📄"
        elif idioma == "es":
            return "¡Sin problema! Envía el nuevo documento y te doy el presupuesto. 📄"
        else:
            return "Sem problema! Envie o novo documento que eu faco o orcamento. 📄"

    # Outra mensagem - manter conversa
    return None


async def processar_etapa_pos_pagamento(phone: str, mensagem: str, is_image: bool = False, image_bytes: bytes = None) -> str:
    """
    Processa mensagens APÓS o pagamento ser confirmado.
    Evita que imagens/documentos sejam tratados como novos pedidos de tradução.
    """
    estado = await get_cliente_estado(phone)
    idioma = estado.get("idioma", "pt")
    nome = estado.get("nome", "")
    # Se recebeu imagem após pagamento confirmado
    if is_image:
        # Perguntar se é novo documento ou só complemento/dúvida
        if idioma == "en":
            return (
                f"Hi! I received an image. 📷\n\n"
                f"Your translation order is already being processed! ✅\n\n"
                f"Is this:\n"
                f"• A NEW DOCUMENT - for a new quote?\n"
                f"• ADDITIONAL INFO - related to your current order?\n\n"
                f"Just let me know how I can help!"
            )
        elif idioma == "es":
            return (
                f"¡Hola! Recibí una imagen. 📷\n\n"
                f"¡Tu pedido de traducción ya está siendo procesado! ✅\n\n"
                f"¿Es esto:\n"
                f"• NUEVO DOCUMENTO - para nueva cotización?\n"
                f"• INFO ADICIONAL - relacionado con tu pedido actual?\n\n"
                f"¡Dime cómo puedo ayudarte!"
            )
        else:
            return (
                f"Oi! Recebi uma imagem. 📷\n\n"
                f"Seu pedido de traducao ja esta sendo processado! ✅\n\n"
                f"Isso e:\n"
                f"• NOVO DOCUMENTO - para novo orcamento?\n"
                f"• INFO ADICIONAL - relacionado ao seu pedido atual?\n\n"
                f"Me diz como posso te ajudar!"
            )

    # Processar texto - verificar se quer novo orçamento
    msg_lower = mensagem.lower()

    # Cliente quer novo documento/orçamento
    palavras_novo = ["novo", "new", "nuevo", "another", "outro", "otra", "more", "mais", "mas"]
    if any(p in msg_lower for p in palavras_novo):
        await set_cliente_estado(phone, etapa=ETAPAS["INICIAL"])
        if idioma == "en":
            return "Perfect! Send the new document and I'll prepare a quote for you. 📄"
        elif idioma == "es":
            return "¡Perfecto! Envía el nuevo documento y te preparo la cotización. 📄"
        else:
            return "Perfeito! Envie o novo documento que eu preparo o orcamento. 📄"

    # Caso contrário, deixar a IA responder normalmente
    return None


# ============================================================
# INCLUIR ROTAS DO PAINEL ADMIN
# ============================================================
app.include_router(admin_router)
app.include_router(training_router)
app.include_router(controle_router)
app.include_router(learning_router)
app.include_router(atendimento_router)
app.include_router(conversas_router)
app.include_router(orcamentos_router)
app.include_router(webchat_router)
app.include_router(crm_router)

# ============================================================
# CONFIGURACOES Z-API
# ============================================================
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
ZAPI_URL = os.getenv("ZAPI_URL", "https://api.z-api.io")

# ============================================================
# VALIDACAO DE CONFIGURACAO Z-API (log de aviso)
# ============================================================
def validar_config_zapi():
    """Valida e loga status das configuracoes Z-API"""
    problemas = []

    if not ZAPI_INSTANCE_ID:
        problemas.append("ZAPI_INSTANCE_ID nao configurado!")
    if not ZAPI_TOKEN:
        problemas.append("ZAPI_TOKEN nao configurado!")
    if not ZAPI_CLIENT_TOKEN:
        problemas.append("ZAPI_CLIENT_TOKEN nao configurado (pode causar erros)!")

    if problemas:
        logger.error("=" * 60)
        logger.error("PROBLEMAS DE CONFIGURACAO Z-API DETECTADOS:")
        for p in problemas:
            logger.error(f"  - {p}")
        logger.error("O bot NAO conseguira enviar mensagens sem essas configuracoes!")
        logger.error("=" * 60)
        return False
    else:
        logger.info("=" * 60)
        logger.info("CONFIGURACAO Z-API OK:")
        logger.info(f"  - Instance ID: {ZAPI_INSTANCE_ID[:8]}... (configurado)")
        logger.info(f"  - Token: {ZAPI_TOKEN[:8]}... (configurado)")
        logger.info(f"  - Client Token: {'Configurado' if ZAPI_CLIENT_TOKEN else 'Nao configurado'}")
        logger.info("=" * 60)
        return True

# Validar na inicializacao
ZAPI_CONFIG_VALIDA = validar_config_zapi()


# ============================================================
# MODELOS PYDANTIC
# ============================================================
class Message(BaseModel):
    phone: str
    message: str
    timestamp: datetime = datetime.now()
    role: str = "user"
    message_type: str = "text"


# ============================================================
# FUNCAO: BUSCAR TREINAMENTO DINAMICO DO MONGODB
# ============================================================
DEFAULT_BOT_TRAINING = """
Você é Mia, a assistente virtual oficial da Legacy Translations.

**IDENTIDADE:**
A Legacy Translations é especializada em:
- Tradução certificada
- Tradução juramentada
- Serviços em português, inglês e espanhol
- Traduções de diversos idiomas para o inglês

Sede: Boston, MA | Filial: Orlando, FL
Membro da American Translators Association (ATA)

**REGRAS DE IDIOMA:**
- Responda SEMPRE no idioma utilizado pelo cliente
- No início, pergunte: "Olá! Eu sou a Mia, assistente virtual da Legacy Translations. Como posso ajudar?"
- NUNCA use o nome do cliente nas respostas. NÃO pergunte o nome do cliente. NÃO tente chamar o cliente pelo nome

**TABELA DE PREÇOS:**
- Português → Inglês (Certificada): $24.99/página | 3 dias úteis
- Espanhol → Inglês (Certificada): $24.99/página | 3 dias úteis
- Tradução Juramentada (Sworn): $35.00/página | 5 dias úteis
- Urgência Priority (24h): +25%
- Urgência Urgente (12h): +50%
- Envio físico Priority Mail: $18.99
- Desconto: Acima de 7 páginas = 10% de desconto automático

**IMPORTANTE - DESCONTOS DE PARCEIROS (George Law, Geovanna, Gdreams, etc.):**
NÃO oferecemos mais descontos para parceiros ou indicações.
Se o cliente perguntar sobre desconto de George Law, Geovanna, Gdreams, ou qualquer outro parceiro/escritório, responda:
"Nosso preço por página era $35.00 e agora trabalhamos com o valor mínimo de $24.99 por página. Por isso, não temos mais descontos de parceiros, pois o preço já está reduzido."

**OPÇÃO DE ENVIO POR EMAIL:**
Se o cliente preferir enviar o documento por e-mail:
"Você pode enviar o documento para: contact@legacytranslations.com"

**FORMA DE PAGAMENTO (SEMPRE ENVIAR):**
Para concluir o processo, basta efetuar o pagamento:
VENMO: @legacytranslations
ZELLE: Contact@legacytranslations.com — LEGACY TRANSLATIONS INC

**APÓS PAGAMENTO CONFIRMADO:**
Enviar: "Aproveite para nos seguir no Instagram: https://www.instagram.com/legacytranslations/"

**CLIENTE CONFUSO OU PEDE MAIS DESCONTO:**
Transferir educadamente para um atendente humano.

**FLUXO OBRIGATÓRIO DE ATENDIMENTO:**
1. Cumprimentar o cliente (NÃO perguntar o nome)
2. Perguntar qual idioma de tradução (de qual para qual)
3. Perguntar quantas páginas tem o documento
4. PEDIR PARA O CLIENTE ENVIAR O DOCUMENTO (foto ou arquivo) - OBRIGATÓRIO antes de dar orçamento
5. SOMENTE APÓS RECEBER O DOCUMENTO, apresentar o orçamento com base no número de páginas e idioma
6. Informar formas de pagamento (VENMO/ZELLE)

**REGRAS:**
- NUNCA dê orçamento ou valor ANTES de receber o documento do cliente
- Sempre peça para o cliente enviar o documento primeiro, depois confirme o orçamento
- Todas as traduções são certificadas e aceitas por USCIS, universidades, escolas, bancos
- Seja educada, profissional e use um toque humano nas respostas
- NUNCA pergunte "tem mais paginas?", "pode mandar mais?" ou "so isso?" - apenas confirme o total recebido
- NUNCA diga "estou a disposicao se tiver alguma duvida" ou frases genéricas de encerramento
- NUNCA repita o link do portal mais de uma vez na mesma conversa
- Apos o cliente confirmar o total de paginas, peça para enviar o documento
- NUNCA diga o preço antes de receber o documento. Primeiro peça o documento, depois dê o orçamento
- NUNCA pergunte como o cliente conheceu ou ficou sabendo da Legacy Translations. NÃO faça pesquisa de origem (Google, Instagram, Facebook, indicação). Essa pergunta foi REMOVIDA do fluxo
- SEMPRE responda no mesmo idioma que o cliente usar. Se o cliente escreveu em inglês, responda em inglês. Se escreveu em português, responda em português. Se escreveu em espanhol, responda em espanhol. Na dúvida, pergunte em que idioma o cliente prefere continuar
"""

async def get_bot_training() -> str:
    """Busca treinamento dinamico do bot Mia no MongoDB"""
    try:
        bot = await db.bots.find_one({"name": "Mia"})

        if not bot:
            logger.warning("Bot Mia nao encontrado no banco, usando padrao completo")
            return DEFAULT_BOT_TRAINING

        # Extrair dados do bot
        personality = bot.get("personality", {})
        knowledge_base = bot.get("knowledge_base", [])
        faqs = bot.get("faqs", [])

        # Montar prompt dinamico
        prompt_parts = []

        # Objetivos (goals)
        if personality.get("goals"):
            goals_text = "\n".join(personality["goals"]) if isinstance(personality["goals"], list) else personality["goals"]
            prompt_parts.append(f"**OBJETIVOS:**\n{goals_text}")

        # Tom de voz
        if personality.get("tone"):
            prompt_parts.append(f"**TOM DE VOZ:**\n{personality['tone']}")

        # Restricoes
        if personality.get("restrictions"):
            restrictions_text = "\n".join(personality["restrictions"]) if isinstance(personality["restrictions"], list) else personality["restrictions"]
            prompt_parts.append(f"**RESTRICOES:**\n{restrictions_text}")

        # Base de conhecimento (filtrar kb_origem - pergunta de origem removida)
        if knowledge_base:
            knowledge_base = [
                item for item in knowledge_base
                if item.get("_id") != "kb_origem" and "como conheceu" not in item.get("content", "").lower()
                and "como ficou sabendo" not in item.get("content", "").lower()
                and "how you heard" not in item.get("content", "").lower()
            ]
            kb_text = "\n\n".join([
                f"**{item.get('title', 'Info')}:**\n{item.get('content', '')}"
                for item in knowledge_base
            ])
            prompt_parts.append(f"**BASE DE CONHECIMENTO:**\n{kb_text}")

        # FAQs
        if faqs:
            faq_text = "\n\n".join([
                f"P: {item.get('question', '')}\nR: {item.get('answer', '')}"
                for item in faqs
            ])
            prompt_parts.append(f"**PERGUNTAS FREQUENTES:**\n{faq_text}")

        final_prompt = "\n\n".join(prompt_parts)

        logger.info(f"Treinamento carregado do MongoDB ({len(knowledge_base)} conhecimentos, {len(faqs)} FAQs)")

        return final_prompt

    except Exception as e:
        logger.error(f"Erro ao buscar treinamento: {e}")
        return DEFAULT_BOT_TRAINING


# ============================================================
# FUNCAO: ENVIAR MENSAGEM WHATSAPP
# ============================================================
async def send_whatsapp_message(phone: str, message: str):
    """Envia mensagem via Z-API com Client-Token"""
    try:
        # VALIDACAO: Verificar se configuracao Z-API esta ok
        if not ZAPI_CONFIG_VALIDA:
            logger.error("=" * 60)
            logger.error("FALHA NO ENVIO: Configuracao Z-API invalida!")
            logger.error(f"  ZAPI_INSTANCE_ID: {'OK' if ZAPI_INSTANCE_ID else 'FALTANDO!'}")
            logger.error(f"  ZAPI_TOKEN: {'OK' if ZAPI_TOKEN else 'FALTANDO!'}")
            logger.error(f"  ZAPI_CLIENT_TOKEN: {'OK' if ZAPI_CLIENT_TOKEN else 'FALTANDO!'}")
            logger.error("Mensagem NAO foi enviada para: " + phone)
            logger.error("=" * 60)
            return False

        # Construir URL completa
        url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"

        # Headers COM Client-Token
        headers = {
            "Content-Type": "application/json",
            "Client-Token": ZAPI_CLIENT_TOKEN or ""
        }

        # Payload
        payload = {
            "phone": phone,
            "message": message
        }

        # Logs de debug detalhados
        logger.info("=" * 40)
        logger.info(f"[ENVIO Z-API] Destinatario: {phone}")
        logger.info(f"[ENVIO Z-API] Mensagem ({len(message)} chars): {message[:100]}...")
        logger.info(f"[ENVIO Z-API] URL: {url[:60]}...")
        logger.info(f"[ENVIO Z-API] Client-Token: {'Sim' if headers['Client-Token'] else 'NAO - PODE CAUSAR ERRO!'}")

        # Enviar requisicao COM headers
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)

            logger.info(f"[ENVIO Z-API] Status HTTP: {response.status_code}")
            logger.info(f"[ENVIO Z-API] Resposta: {response.text[:200]}")

            if response.status_code == 200:
                logger.info(f"[ENVIO Z-API] SUCESSO - Mensagem enviada para {phone}")
                logger.info("=" * 40)
                return True
            else:
                logger.error("=" * 60)
                logger.error(f"[ENVIO Z-API] FALHA! Status: {response.status_code}")
                logger.error(f"[ENVIO Z-API] Resposta erro: {response.text}")
                logger.error(f"[ENVIO Z-API] Telefone: {phone}")
                logger.error("=" * 60)
                return False

    except httpx.TimeoutException:
        logger.error(f"[ENVIO Z-API] TIMEOUT ao enviar para {phone} (30s)")
        return False
    except httpx.ConnectError as e:
        logger.error(f"[ENVIO Z-API] ERRO DE CONEXAO com Z-API: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"[ENVIO Z-API] EXCECAO: {str(e)}")
        logger.error(traceback.format_exc())
        return False


# ============================================================
# FUNCAO: BAIXAR MIDIA DA Z-API
# ============================================================
async def download_media_from_zapi(media_url: str) -> Optional[bytes]:
    """Baixa midia (imagem/audio) da Z-API"""
    try:
        logger.info(f"Baixando midia: {media_url[:100]}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(media_url)

            if response.status_code == 200:
                logger.info(f"Midia baixada ({len(response.content)} bytes)")
                return response.content
            else:
                logger.error(f"Erro ao baixar midia: {response.status_code}")
                return None

    except Exception as e:
        logger.error(f"Erro ao baixar midia: {str(e)}")
        return None


# ============================================================
# FUNCAO: PROCESSAR IMAGEM COM GPT-4 VISION
# ============================================================
async def process_image_with_vision(image_bytes: bytes, phone: str) -> str:
    """Analisa imagem com GPT-4 Vision"""
    try:
        logger.info(f"Processando imagem com Vision ({len(image_bytes)} bytes)")

        # Converter para base64
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        # Buscar treinamento dinamico
        training_prompt = await get_bot_training()

        # Chamar GPT-4 Vision
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"""{training_prompt}

TAREFA ESPECIAL - ANALISE DE IMAGEM:
Voce recebeu uma imagem de documento. Analise e forneca:
- Tipo de documento (certidao, diploma, contrato, etc)
- Idioma detectado
- Numero estimado de paginas (se visivel)
- Orcamento baseado nas regras de preco do treinamento
- Prazo de entrega
Seja direto e objetivo na resposta."""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analise este documento e me de um orcamento de traducao."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=800
        )

        analysis = response.choices[0].message.content

        # Salvar no banco
        await db.conversas.insert_one({
            "phone": phone,
            "message": "[IMAGEM ENVIADA]",
            "role": "user",
            "timestamp": datetime.now(),
            "canal": "WhatsApp",
            "type": "image"
        })

        await db.conversas.insert_one({
            "phone": phone,
            "message": analysis,
            "role": "assistant",
            "timestamp": datetime.now(),
            "canal": "WhatsApp"
        })

        logger.info(f"Analise Vision concluida")
        return analysis

    except Exception as e:
        logger.error(f"Erro no Vision: {str(e)}")
        logger.error(traceback.format_exc())
        return "Desculpe, nao consegui analisar a imagem. Pode me dizer quantas paginas tem o documento?"


# ============================================================
# FUNCAO: PROCESSAR PDF COM VISION
# ============================================================
async def process_pdf_with_vision(pdf_bytes: bytes, phone: str) -> str:
    """Analisa PDF convertendo paginas em imagens e usando GPT-4 Vision"""
    try:
        logger.info(f"Processando PDF ({len(pdf_bytes)} bytes)")

        # Salvar PDF temporariamente
        temp_pdf_path = f"/tmp/pdf_{phone}_{int(time.time())}.pdf"
        with open(temp_pdf_path, "wb") as f:
            f.write(pdf_bytes)

        # Converter PDF para imagens
        from pdf2image import convert_from_path
        images = convert_from_path(temp_pdf_path, dpi=150)

        logger.info(f"PDF convertido em {len(images)} paginas")

        # Processar primeira pagina com Vision (para analise inicial)
        first_page = images[0]

        # Converter para bytes
        img_byte_arr = BytesIO()
        first_page.save(img_byte_arr, format='PNG')
        img_bytes = img_byte_arr.getvalue()

        # Converter para base64
        base64_image = base64.b64encode(img_bytes).decode('utf-8')

        # Buscar treinamento dinamico
        training_prompt = await get_bot_training()

        # Chamar GPT-4 Vision
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"""{training_prompt}

TAREFA ESPECIAL - ANALISE DE PDF:
Voce recebeu a primeira pagina de um documento PDF com {len(images)} paginas. Analise e forneca:
- Tipo de documento (certidao, diploma, contrato, etc)
- Idioma detectado
- Numero de paginas: {len(images)}
- Orcamento baseado nas regras de preco do treinamento
- Prazo de entrega
Seja direto e objetivo na resposta."""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Analise este documento PDF de {len(images)} paginas e me de um orcamento de traducao."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=800
        )

        analysis = response.choices[0].message.content

        # Limpar arquivo temporario
        os.remove(temp_pdf_path)

        # Salvar no banco
        await db.conversas.insert_one({
            "phone": phone,
            "message": f"[PDF ENVIADO - {len(images)} paginas]",
            "role": "user",
            "timestamp": datetime.now(),
            "canal": "WhatsApp",
            "type": "document"
        })

        await db.conversas.insert_one({
            "phone": phone,
            "message": analysis,
            "role": "assistant",
            "timestamp": datetime.now(),
            "canal": "WhatsApp"
        })

        logger.info(f"Analise PDF concluida")
        return analysis

    except Exception as e:
        logger.error(f"Erro ao processar PDF: {str(e)}")
        logger.error(traceback.format_exc())
        return "Desculpe, nao consegui analisar o PDF. Pode me dizer quantas paginas tem o documento?"


# ============================================================
# FUNCAO: PROCESSAR AUDIO COM WHISPER
# ============================================================
async def process_audio_with_whisper(audio_bytes: bytes, phone: str) -> Optional[str]:
    """Transcreve audio com Whisper"""
    try:
        logger.info(f"Processando audio com Whisper ({len(audio_bytes)} bytes)")

        # Salvar temporariamente
        temp_file = BytesIO(audio_bytes)
        temp_file.name = "audio.ogg"

        # Chamar Whisper
        transcription = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=temp_file,
            language="pt"  # Pode ser pt, en, es
        )

        transcribed_text = transcription.text

        # Salvar no banco
        await db.conversas.insert_one({
            "phone": phone,
            "message": f"[AUDIO] {transcribed_text}",
            "role": "user",
            "timestamp": datetime.now(),
            "canal": "WhatsApp",
            "type": "audio"
        })

        logger.info(f"Audio transcrito: {transcribed_text[:100]}")
        return transcribed_text

    except Exception as e:
        logger.error(f"Erro no Whisper: {str(e)}")
        logger.error(traceback.format_exc())
        return None


# ============================================================
# FUNCAO: BUSCAR CONTEXTO DA CONVERSA
# ============================================================
async def get_conversation_context(phone: str, limit: int = 10) -> List[Dict]:
    """Busca ultimas mensagens da conversa"""
    try:
        messages = await db.conversas.find(
            {"phone": phone}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)

        # Inverter para ordem cronologica
        messages.reverse()

        return [
            {"role": msg["role"], "content": msg["message"]}
            for msg in messages
        ]
    except Exception as e:
        logger.error(f"Erro ao buscar contexto: {e}")
        return []


# ============================================================
# FUNCAO: PROCESSAR MENSAGEM COM IA
# ============================================================
def get_transfer_message(idioma: str = "pt") -> str:
    """Retorna mensagem de transferência para atendente no idioma correto"""
    messages = {
        "en": "I'll transfer you to one of our specialists. Please wait a moment! 😊",
        "pt": "Vou transferir você para um de nossos especialistas. Aguarde um momento! 😊",
        "es": "Te transfiero a uno de nuestros especialistas. ¡Espera un momento! 😊"
    }
    return messages.get(idioma, messages["pt"])

async def process_message_with_ai(phone: str, message: str) -> str:
    """Processar mensagem com GPT-4 usando treinamento dinamico"""
    try:
        # Detectar se cliente quer falar com humano
        if await detectar_solicitacao_humano(message):
            await transferir_para_humano(phone, "Cliente solicitou atendente")
            # Retornar mensagem simples de transferência no idioma do cliente
            estado = await get_cliente_estado(phone)
            idioma = estado.get("idioma", "pt")
            return get_transfer_message(idioma)

        # Buscar treinamento dinamico do MongoDB
        system_prompt = await get_bot_training()

        # Detectar idioma do cliente e injetar instrucao explicita
        estado = await get_cliente_estado(phone)
        idioma_cliente = estado.get("idioma", detectar_idioma(message))
        idioma_map = {"en": "English", "es": "Spanish", "pt": "Portuguese"}
        idioma_nome = idioma_map.get(idioma_cliente, "Portuguese")
        system_prompt += f"\n\n**IDIOMA OBRIGATÓRIO:** O cliente está se comunicando em {idioma_nome}. Você DEVE responder EXCLUSIVAMENTE em {idioma_nome}. NÃO responda em outro idioma."

        # Buscar contexto
        context = await get_conversation_context(phone)

        # Montar mensagens
        messages = [
            {"role": "system", "content": system_prompt}
        ] + context + [
            {"role": "user", "content": message}
        ]

        # Chamar GPT-4
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )

        reply = response.choices[0].message.content

        # NOTA: Nao salvar no banco aqui - os callers (webhook handler) ja salvam
        # para evitar duplicacao de mensagens no contexto da conversa

        return reply

    except Exception as e:
        logger.error(f"Erro ao processar com IA: {str(e)}")
        logger.error(traceback.format_exc())
        return "Desculpe, tive um problema. Pode repetir?"


# ============================================================
# FUNCAO AUXILIAR: NORMALIZAR TELEFONE
# ============================================================
def normalize_phone(phone: str) -> str:
    """Normaliza numero de telefone para comparacao"""
    return ''.join(filter(str.isdigit, phone))[-10:]


# ============================================================
# API: CONTROLE DO BOT
# ============================================================
@app.get("/admin/api/bot/status")
async def api_bot_status():
    """Retorna status atual do bot"""
    status = await get_bot_status()

    # Contar conversas por modo
    ia_ativa = await db.conversas.distinct("phone", {"mode": {"$ne": "human"}})
    humano = await db.conversas.distinct("phone", {"mode": "human"})

    return {
        "enabled": status["enabled"],
        "last_update": status["last_update"].isoformat(),
        "stats": {
            "ia_ativa": len(ia_ativa),
            "atendimento_humano": len(humano),
            "ia_desligada": 0 if status["enabled"] else len(ia_ativa),
            "total": len(ia_ativa) + len(humano)
        }
    }


@app.get("/admin/api/debug/config")
async def api_debug_config():
    """
    Endpoint de DEBUG - Verifica configuracoes do bot
    Acesse: /admin/api/debug/config
    """
    # Verificar OpenAI
    openai_ok = bool(os.getenv("OPENAI_API_KEY"))

    # Verificar MongoDB
    try:
        await db.command("ping")
        mongodb_ok = True
        mongodb_error = None
    except Exception as e:
        mongodb_ok = False
        mongodb_error = str(e)

    # Status do bot
    bot_status = await get_bot_status()

    return {
        "timestamp": datetime.now().isoformat(),
        "configuracao": {
            "zapi": {
                "instance_id": "OK" if ZAPI_INSTANCE_ID else "FALTANDO!",
                "token": "OK" if ZAPI_TOKEN else "FALTANDO!",
                "client_token": "OK" if ZAPI_CLIENT_TOKEN else "FALTANDO!",
                "config_valida": ZAPI_CONFIG_VALIDA
            },
            "openai": {
                "api_key": "OK" if openai_ok else "FALTANDO!"
            },
            "mongodb": {
                "conectado": mongodb_ok,
                "erro": mongodb_error
            }
        },
        "bot_status": {
            "enabled": bot_status["enabled"],
            "last_update": bot_status["last_update"].isoformat()
        },
        "diagnostico": {
            "pode_receber_mensagens": mongodb_ok,
            "pode_processar_ia": openai_ok and mongodb_ok,
            "pode_enviar_respostas": ZAPI_CONFIG_VALIDA,
            "bot_funcionando": all([mongodb_ok, openai_ok, ZAPI_CONFIG_VALIDA, bot_status["enabled"]])
        },
        "instrucoes": {
            "se_zapi_faltando": "Configure ZAPI_INSTANCE_ID, ZAPI_TOKEN e ZAPI_CLIENT_TOKEN nas variaveis de ambiente",
            "se_openai_faltando": "Configure OPENAI_API_KEY nas variaveis de ambiente",
            "se_mongodb_erro": "Verifique MONGODB_URI nas variaveis de ambiente"
        }
    }


@app.get("/admin/api/debug/webhook")
async def api_debug_webhook():
    """
    DEBUG: Mostra ultimos eventos do webhook para verificar se * e + estao chegando
    Acesse: /admin/api/debug/webhook
    """
    return {
        "total_eventos": len(webhook_debug_log),
        "ultimos_eventos": webhook_debug_log[-20:][::-1],  # Ultimos 20, mais recentes primeiro
        "comandos_detectados": [
            e for e in webhook_debug_log
            if e["event"] in ["COMMAND_DETECTED", "COMMAND_EXECUTED"]
        ][-10:][::-1],  # Ultimos 10 comandos
        "instrucoes": {
            "como_testar": "Envie * ou + no WhatsApp e atualize esta pagina",
            "o_que_verificar": "Procure por eventos COMMAND_DETECTED com fromMe=true",
            "se_fromMe_false": "O Z-API nao esta enviando suas mensagens ao webhook. Verifique as configuracoes do Z-API."
        }
    }


@app.post("/admin/api/bot/toggle")
async def api_bot_toggle(enabled: bool):
    """Liga ou desliga o bot globalmente"""
    success = await set_bot_status(enabled)

    if success:
        return {
            "success": True,
            "enabled": enabled,
            "message": f"Bot {'ATIVADO' if enabled else 'DESATIVADO'} com sucesso!"
        }
    else:
        raise HTTPException(status_code=500, detail="Erro ao atualizar status do bot")


# ============================================================
# API: VERIFICAR E CONTROLAR MODO DO CLIENTE
# ============================================================
@app.get("/admin/api/cliente/{phone}/modo")
async def api_get_modo_cliente(phone: str):
    """Verifica o modo atual de um cliente (ia ou human)"""
    estado = await db.cliente_estados.find_one({"phone": phone})

    if not estado:
        return {
            "phone": phone,
            "modo": "ia",
            "existe_estado": False,
            "mensagem": "Cliente sem estado salvo - modo padrao IA"
        }

    return {
        "phone": phone,
        "modo": estado.get("mode", "ia"),
        "existe_estado": True,
        "transferred_at": estado.get("transferred_at"),
        "paused_at": estado.get("paused_at"),
        "paused_by": estado.get("paused_by"),
        "updated_at": estado.get("updated_at"),
        "nome": estado.get("nome"),
        "etapa": estado.get("etapa")
    }


@app.post("/admin/api/cliente/{phone}/pausar")
async def api_pausar_cliente(phone: str):
    """Pausa a IA para um cliente especifico"""
    sucesso = await pausar_ia_para_cliente(phone)

    if sucesso:
        return {
            "success": True,
            "phone": phone,
            "modo": "human",
            "mensagem": f"IA pausada para cliente {phone}"
        }
    else:
        raise HTTPException(status_code=500, detail="Erro ao pausar IA")


@app.post("/admin/api/cliente/{phone}/retomar")
async def api_retomar_cliente(phone: str):
    """Retoma a IA para um cliente especifico"""
    sucesso = await retomar_ia_para_cliente(phone)

    if sucesso:
        return {
            "success": True,
            "phone": phone,
            "modo": "ia",
            "mensagem": f"IA retomada para cliente {phone}"
        }
    else:
        raise HTTPException(status_code=500, detail="Erro ao retomar IA")


@app.get("/admin/api/clientes/modo-humano")
async def api_listar_clientes_modo_humano():
    """Lista todos os clientes em modo humano (atendimento pausado)"""
    clientes = await db.cliente_estados.find({"mode": "human"}).to_list(length=100)

    return {
        "total": len(clientes),
        "clientes": [
            {
                "phone": c.get("phone"),
                "nome": c.get("nome", "Nao informado"),
                "paused_at": c.get("paused_at") or c.get("transferred_at"),
                "motivo": c.get("transfer_reason", "Nao especificado")
            }
            for c in clientes
        ]
    }


# ============================================================
# WEBHOOK: WHATSAPP (Z-API) - INTEGRADO
# ============================================================
@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    """
    Webhook principal para receber mensagens do WhatsApp via Z-API
    Suporta: texto, imagens e audios
    """
    try:
        data = await request.json()
        logger.info(f"Webhook recebido: {json.dumps(data, indent=2)}")

        # ============================================
        # EXTRAIR DADOS BASICOS
        # ============================================
        phone = data.get("phone", "")
        from_me_raw = data.get("fromMe", False)
        message_id = data.get("messageId", "")

        # Converter fromMe para boolean robusto (Z-API pode enviar string "true"/"false")
        if isinstance(from_me_raw, str):
            from_me = from_me_raw.lower() == "true"
        else:
            from_me = bool(from_me_raw)

        # LOG DETALHADO PARA DEBUG DE COMANDOS
        logger.info(f"[DEBUG] fromMe={from_me} (raw={from_me_raw}, type={type(from_me_raw).__name__})")

        # ============================================
        # VERIFICAR MENSAGEM DUPLICADA
        # ============================================
        if verificar_mensagem_duplicada(message_id):
            return JSONResponse({
                "status": "ignored",
                "reason": "duplicate_message",
                "messageId": message_id
            })

        # Extrair texto de forma mais robusta
        # Z-API pode enviar o texto em diferentes formatos
        message_text = ""

        # Log dos campos disponiveis para debug
        campos_disponiveis = [k for k in data.keys() if k not in ['_traceContext', 'photo', 'senderPhoto']]
        logger.info(f"[DEBUG-CAMPOS] Campos no webhook: {campos_disponiveis}")

        # Tentar extrair texto de varios campos possiveis
        if "text" in data:
            if isinstance(data["text"], dict):
                message_text = data["text"].get("message", "") or data["text"].get("body", "")
            elif isinstance(data["text"], str):
                message_text = data["text"]

        # Fallback: tentar outros campos comuns do Z-API
        if not message_text:
            message_text = (
                data.get("body", "") or
                data.get("message", "") or
                data.get("content", "") or
                data.get("caption", "") or
                ""
            )

        # Para mensagens de texto simples, Z-API as vezes usa "text.message"
        if not message_text and "text" in data and isinstance(data.get("text"), dict):
            message_text = data["text"].get("message", "")

        message_text = message_text.strip() if message_text else ""

        # Log detalhado
        logger.info(f"[WEBHOOK] phone={phone}, fromMe={from_me}, text='{message_text}'")
        if from_me:
            logger.info(f"[DEBUG-FROMME] Mensagem do operador - text='{message_text}', campos={campos_disponiveis}")

        # Registrar no debug log
        add_webhook_debug("WEBHOOK_RECEIVED", {
            "phone": phone,
            "fromMe": from_me,
            "text": message_text[:50] if message_text else "",
            "message_id": message_id
        })

        # ============================================
        # PROCESSAR COMANDOS DO OPERADOR (* e +)
        # Metodo 1: fromMe=true (operador no WhatsApp conectado ao Z-API)
        # Metodo 2: mensagem do numero do operador (18573167770)
        # Usa is_operator_phone() para comparacao robusta de telefone
        # ============================================

        comando = message_text.strip()
        # Comandos aceitos: * ou + (e alternativas 8/* e 9/+ para teclados problematicos)
        COMANDOS_PAUSA = ["*", "8", "**", "88"]  # Pausa IA
        COMANDOS_RETOMA = ["+", "9", "++", "99"]  # Retoma IA
        e_comando_pausa = comando in COMANDOS_PAUSA
        e_comando_retoma = comando in COMANDOS_RETOMA
        e_comando_operador = e_comando_pausa or e_comando_retoma

        # Usar versao async para pegar config atualizada do MongoDB
        e_telefone_operador = await is_operator_phone_async(phone)

        # Pegar config atual para logs
        operator_phone, alerts_phone = await get_operator_phones()

        # Log detalhado SEMPRE para debug de comandos - incluir bytes para ver caracteres invisiveis
        comando_bytes = comando.encode('utf-8').hex() if comando else "vazio"
        logger.info(f"[DEBUG-CMD] fromMe={from_me}, phone={phone}, comando='{comando}' (bytes={comando_bytes})")
        logger.info(f"[DEBUG-CMD] e_comando_pausa={e_comando_pausa}, e_comando_retoma={e_comando_retoma}, e_telefone_operador={e_telefone_operador}")
        logger.info(f"[DEBUG-CMD] OPERATOR_PHONE (MongoDB): {operator_phone}, ALERTS_PHONE: {alerts_phone}")

        if e_comando_operador:
            add_webhook_debug("COMMAND_DETECTED", {
                "phone": phone,
                "fromMe": from_me,
                "comando": comando,
                "e_telefone_operador": e_telefone_operador
            })

        # Detectar se eh operador: fromMe OU telefone do operador
        e_operador = from_me or e_telefone_operador

        # Log CRITICO para debug de operador - sempre mostra
        logger.info(f"[DEBUG-OPERADOR] ====== VERIFICACAO DE OPERADOR ======")
        logger.info(f"[DEBUG-OPERADOR] phone recebido: '{phone}'")
        logger.info(f"[DEBUG-OPERADOR] OPERATOR_PHONE (MongoDB/config): '{operator_phone}'")
        logger.info(f"[DEBUG-OPERADOR] ALERTS_PHONE (MongoDB/config): '{alerts_phone}'")
        logger.info(f"[DEBUG-OPERADOR] fromMe: {from_me}")
        logger.info(f"[DEBUG-OPERADOR] e_telefone_operador: {e_telefone_operador}")
        logger.info(f"[DEBUG-OPERADOR] e_operador (final): {e_operador}")
        logger.info(f"[DEBUG-OPERADOR] e_comando_pausa: {e_comando_pausa}, e_comando_retoma: {e_comando_retoma}")
        if not e_operador:
            logger.info(f"[DEBUG-OPERADOR] NAO eh operador - sera processado como CLIENTE")
        logger.info(f"[DEBUG-OPERADOR] =====================================")

        if e_operador:
            logger.info(f"[OPERADOR] ========================================")
            logger.info(f"[OPERADOR] Mensagem de OPERADOR detectada!")
            logger.info(f"[OPERADOR] fromMe={from_me}, phone={phone}, e_telefone_operador={e_telefone_operador}")
            logger.info(f"[OPERADOR] Texto/Comando: '{comando}'")
            logger.info(f"[OPERADOR] e_comando_pausa={e_comando_pausa}, e_comando_retoma={e_comando_retoma}")
            logger.info(f"[OPERADOR] ========================================")

            if e_comando_operador:
                # METODO 1: fromMe=true E phone NAO eh o operador → phone eh do CLIENTE
                if from_me and not e_telefone_operador:
                    cliente_phone = phone
                    if e_comando_pausa:
                        resultado = await pausar_ia_para_cliente(cliente_phone)
                        logger.info(f"[OPERADOR] IA PAUSADA para cliente {cliente_phone} (via fromMe, comando='{comando}')")
                    else:
                        resultado = await retomar_ia_para_cliente(cliente_phone)
                        logger.info(f"[OPERADOR] IA RETOMADA para cliente {cliente_phone} (via fromMe, comando='{comando}')")
                    add_webhook_debug("COMMAND_EXECUTED", {
                        "comando": comando,
                        "metodo": "fromMe",
                        "cliente": cliente_phone,
                        "resultado": resultado
                    })
                    # Registrar ultimo cliente que o operador interagiu
                    await db.sistema.update_one(
                        {"key": "ultimo_cliente_operador"},
                        {"$set": {"phone": cliente_phone, "updated_at": datetime.now()}},
                        upsert=True
                    )
                    # Notificar operador
                    try:
                        acao = "pausada" if e_comando_pausa else "retomada"
                        await send_whatsapp_message(ATENDENTE_PHONE, f"✅ IA {acao} para {cliente_phone}")
                    except Exception:
                        pass
                    return {"status": "command_processed", "client": cliente_phone}

                # METODO 2: Operador enviou do seu numero pessoal (ou fromMe com phone=operador)
                # Buscar o cliente correto usando estrategia em camadas
                else:
                    logger.info(f"[OPERADOR] Buscando cliente para comando '{comando}' (via telefone operador)...")
                    cliente_phone = None

                    # Para comandos de retomar (+/9): primeiro buscar cliente em modo humano
                    if e_comando_retoma:
                        ultimo_humano = await db.cliente_estados.find_one(
                            {
                                "mode": "human",
                                "phone": {"$ne": phone}
                            },
                            sort=[("updated_at", -1)]
                        )
                        if ultimo_humano:
                            cliente_phone = ultimo_humano["phone"]
                            logger.info(f"[OPERADOR] Comando retomar encontrou cliente em modo humano: {cliente_phone}")

                    # Para comandos de pausa (*/8): buscar cliente mais recente em modo IA (nao pausado)
                    if e_comando_pausa and not cliente_phone:
                        # Buscar o cliente que enviou mensagem mais recentemente e esta em modo IA
                        clientes_ativos = await db.conversas.find(
                            {"role": "user", "phone": {"$ne": phone}}
                        ).sort("timestamp", -1).limit(10).to_list(length=10)

                        phones_vistos = set()
                        for msg in clientes_ativos:
                            msg_phone = msg.get("phone", "")
                            if msg_phone and msg_phone not in phones_vistos and not is_operator_phone(msg_phone):
                                phones_vistos.add(msg_phone)
                                # Verificar se este cliente esta em modo IA (nao esta pausado)
                                estado_cli = await db.cliente_estados.find_one({"phone": msg_phone})
                                modo_cli = estado_cli.get("mode", "ia") if estado_cli else "ia"
                                if modo_cli == "ia":
                                    cliente_phone = msg_phone
                                    logger.info(f"[OPERADOR] * encontrou cliente ativo em modo IA: {cliente_phone}")
                                    break

                    # Tentar ultimo cliente registrado via interacao do operador
                    if not cliente_phone:
                        ultimo_operador = await db.sistema.find_one({"key": "ultimo_cliente_operador"})
                        if ultimo_operador:
                            cliente_phone = ultimo_operador.get("phone")
                            logger.info(f"[OPERADOR] Usando ultimo cliente da interacao: {cliente_phone}")

                    # Fallback: ultimo cliente que enviou mensagem
                    if not cliente_phone:
                        ultimo_cliente = await db.conversas.find_one(
                            {"role": "user", "phone": {"$ne": phone}},
                            sort=[("timestamp", -1)]
                        )
                        if ultimo_cliente:
                            cliente_phone = ultimo_cliente["phone"]
                            logger.info(f"[OPERADOR] Fallback: ultimo cliente por mensagem: {cliente_phone}")

                    if cliente_phone:
                        if e_comando_pausa:
                            resultado = await pausar_ia_para_cliente(cliente_phone)
                            logger.info(f"[OPERADOR] IA PAUSADA para cliente {cliente_phone} (via telefone operador, comando='{comando}')")
                            await send_whatsapp_message(phone, f"✅ IA pausada para {cliente_phone}")
                        else:
                            resultado = await retomar_ia_para_cliente(cliente_phone)
                            logger.info(f"[OPERADOR] IA RETOMADA para cliente {cliente_phone} (via telefone operador, comando='{comando}')")
                            await send_whatsapp_message(phone, f"✅ IA retomada para {cliente_phone}")
                        # Atualizar ultimo_cliente_operador para manter tracking correto
                        await db.sistema.update_one(
                            {"key": "ultimo_cliente_operador"},
                            {"$set": {"phone": cliente_phone, "updated_at": datetime.now()}},
                            upsert=True
                        )
                        add_webhook_debug("COMMAND_EXECUTED", {
                            "comando": comando,
                            "metodo": "telefone_operador",
                            "cliente": cliente_phone,
                            "resultado": resultado
                        })
                        return {"status": "command_processed", "client": cliente_phone}
                    else:
                        logger.warning(f"[OPERADOR] Nenhum cliente encontrado no banco!")
                        await send_whatsapp_message(phone, "⚠️ Nenhum cliente recente encontrado.")
                        return {"status": "no_recent_client"}

            # Mensagem normal do operador (nao eh comando)
            # Registrar ultimo cliente para referencia se fromMe
            if from_me and not e_telefone_operador:
                await db.sistema.update_one(
                    {"key": "ultimo_cliente_operador"},
                    {"$set": {"phone": phone, "updated_at": datetime.now()}},
                    upsert=True
                )
                logger.info(f"[OPERADOR] Mensagem normal para {phone} - registrando como ultimo cliente")
            else:
                logger.info(f"[OPERADOR] Mensagem normal do operador - ignorando")
            return {"status": "ignored", "reason": "operator_message"}

        # ============================================
        # CAPTURA AUTOMATICA PARA CRM
        # ============================================
        try:
            # Capturar contato no CRM automaticamente
            sender_name = data.get("senderName", "") or data.get("pushName", "") or data.get("notifyName", "")
            await criar_ou_atualizar_contato(phone, {
                "name": sender_name,
                "source": "WhatsApp - Auto",
                "last_message": message_text[:200] if message_text else ""
            })
            logger.info(f"[CRM] Contato capturado/atualizado: {phone}")
        except Exception as crm_error:
            logger.error(f"[CRM] Erro ao capturar contato: {crm_error}")

        # ============================================
        # VERIFICAR STATUS DO BOT E MODO DO CLIENTE
        # ============================================
        bot_status = await get_bot_status()

        # Verificar modo do cliente usando cliente_estados (fonte unica de verdade)
        modo_cliente = await verificar_modo_cliente(phone)
        modo_humano = (modo_cliente == "human")

        logger.info(f"[WEBHOOK] Cliente {phone} - Modo atual: {modo_cliente}")

        # Se em modo humano, verificar se expirou o timeout
        timeout_expirou = False
        if modo_humano:
            timeout_expirou = await verificar_timeout_modo_humano(phone)
            if timeout_expirou:
                # Timeout expirou - nao esta mais em modo humano
                modo_humano = False
                logger.info(f"[TIMEOUT] Cliente {phone} voltou para modo IA automaticamente")

                # Enviar mensagem de fallback ao cliente
                mensagem_fallback = (
                    "Desculpe a demora! No momento nossos atendentes estao ocupados. "
                    "Enquanto isso, posso continuar te ajudando. Como posso auxiliar?"
                )
                await send_whatsapp_message(phone, mensagem_fallback)

        # Se bot desligado OU conversa em modo humano (e NAO expirou timeout), nao processar
        if not bot_status["enabled"] or modo_humano:
            logger.info(f"[WEBHOOK] Bot {'DESLIGADO' if not bot_status['enabled'] else 'em MODO HUMANO para ' + phone} - Mensagem nao sera processada pela IA")

            await db.conversas.insert_one({
                "phone": phone,
                "message": message_text or "[MENSAGEM]",
                "timestamp": datetime.now(),
                "role": "user",
                "type": "text",
                "mode": "human" if modo_humano else "disabled",
                "canal": "WhatsApp"
            })

            return {"status": "received", "processed": False, "reason": "bot_disabled_or_human_mode"}

        # ============================================
        # PROCESSAR COMANDOS ESPECIAIS DO CLIENTE
        # ============================================
        # Nota: Comandos * e + sao EXCLUSIVOS do operador (ATENDENTE_PHONE)
        # Clientes NAO usam esses sinais

        # Comando: ## (Desligar IA para este usuario)
        if message_text == "##":
            await db.conversas.update_many(
                {"phone": phone},
                {"$set": {"mode": "disabled", "disabled_at": datetime.now()}}
            )
            await send_whatsapp_message(
                phone,
                "Atendimento automatico desligado. Digite ++ para religar."
            )
            return {"status": "ia_disabled"}

        # Comando: ++ (Religar IA para este usuario)
        if message_text == "++":
            await db.conversas.update_many(
                {"phone": phone},
                {"$set": {"mode": "ia", "enabled_at": datetime.now()}}
            )
            await send_whatsapp_message(
                phone,
                "Atendimento automatico religado. Como posso ajudar?"
            )
            return {"status": "ia_enabled"}


        # ============================================
        # CONTROLE DE ATIVACAO DA IA
        # ============================================
        ia_enabled = os.getenv("IA_ENABLED", "true").lower() == "true"
        em_manutencao = os.getenv("MANUTENCAO", "false").lower() == "true"

        # Extrair dados basicos
        phone = data.get("phone", "")
        message_id = data.get("messageId", "")
        connected_phone = data.get("connectedPhone", "")
        is_group = data.get("isGroup", False)

        # FILTRO: Ignorar mensagens de grupos
        if is_group:
            logger.info(f"Mensagem de grupo ignorada")
            return JSONResponse({"status": "ignored", "reason": "group message"})

        # FILTRO: Ignorar mensagens de sistema (MongoDB alerts, etc.)
        if message_text and is_system_message(message_text):
            logger.info(f"[FILTRO] Mensagem de sistema ignorada de {phone}: {message_text[:50]}...")
            return JSONResponse({"status": "ignored", "reason": "system_message"})

        # DETECCAO CORRETA DE TIPO DE MENSAGEM
        # Z-API nao envia "messageType", detectar pela presenca dos campos
        message_type = "text"  # padrao

        if "image" in data and data.get("image"):
            message_type = "image"
        elif "audio" in data and data.get("audio"):
            message_type = "audio"
        elif "document" in data and data.get("document"):
            message_type = "document"
        elif "text" in data and data.get("text"):
            message_type = "text"

        logger.info(f"Tipo detectado: {message_type}")

        if not phone:
            return JSONResponse({"status": "ignored", "reason": "no phone"})

        # Se em manutencao, responder e sair
        if em_manutencao:
            logger.info(f"Modo manutencao ativo - mensagem de {phone}")
            if message_type == "text":
                mensagem_manutencao = """*Sistema em Manutencao*

Ola! Estamos melhorando nosso atendimento. Em breve voltaremos!

Para urgencias: (contato)"""
                await send_whatsapp_message(phone, mensagem_manutencao)
            return JSONResponse({"status": "maintenance"})

        # Se IA desabilitada, apenas logar e sair
        if not ia_enabled:
            logger.info(f"IA desabilitada - mensagem de {phone} ignorada")
            return JSONResponse({"status": "ia_disabled"})

        # ============================================
        # VERIFICAR HORÁRIO COMERCIAL (5pm-8:30am EST)
        # Fora do horario: iniciar fluxo de apresentacao + opcoes
        # ao inves de bloquear com mensagem offline
        # ============================================
        if not is_business_hours():
            logger.info(f"[HORÁRIO] Fora do expediente - cliente {phone}")

            estado = await get_cliente_estado(phone)
            etapa_atual = estado.get("etapa", ETAPAS["INICIAL"])
            idioma = estado.get("idioma", "pt")

            # Se o cliente ja esta em uma etapa ativa (nome, origem, opcoes, etc.),
            # deixar o fluxo normal processar (nao bloquear)
            if etapa_atual not in [ETAPAS["INICIAL"]]:
                logger.info(f"[HORÁRIO] Cliente {phone} ja em etapa {etapa_atual} - continuando fluxo normal")
                # Nao bloquear - cai no processamento normal abaixo
            else:
                # Cliente em etapa INICIAL fora do horario:
                # Iniciar fluxo de apresentacao -> pedir nome
                if message_type == "text":
                    text_msg = data.get("text", {}).get("message", "")
                    idioma_detectado = detectar_idioma(text_msg) if text_msg else "pt"
                else:
                    idioma_detectado = idioma

                await set_cliente_estado(
                    phone,
                    etapa=ETAPAS["AGUARDANDO_OPCAO_ATENDIMENTO"],
                    idioma=idioma_detectado
                )

                if idioma_detectado == "en":
                    intro_msg = (
                        f"Hello! 👋 I'm Mia, the virtual assistant at Legacy Translations.\n\n"
                        f"Welcome! We specialize in certified and sworn translations.\n\n"
                        f"How would you like to proceed?\n\n"
                        f"1️⃣ Continue the service right here\n"
                        f"2️⃣ Place my order through the website\n"
                        f"3️⃣ I'd like to speak with a representative\n\n"
                        f"Just reply with the number!"
                    )
                elif idioma_detectado == "es":
                    intro_msg = (
                        f"¡Hola! 👋 Soy Mia, la asistente virtual de Legacy Translations.\n\n"
                        f"¡Bienvenido(a)! Somos especialistas en traducciones certificadas y juramentadas.\n\n"
                        f"¿Cómo prefieres continuar?\n\n"
                        f"1️⃣ Continuar la atención aquí\n"
                        f"2️⃣ Hacer mi pedido por el sitio web\n"
                        f"3️⃣ Quiero hablar con un representante\n\n"
                        f"¡Solo responde con el número!"
                    )
                else:
                    intro_msg = (
                        f"Ola! 👋 Eu sou a Mia, assistente virtual da Legacy Translations.\n\n"
                        f"Bem-vindo(a)! Somos especialistas em traducoes certificadas e juramentadas.\n\n"
                        f"Como voce prefere prosseguir?\n\n"
                        f"1️⃣ Continuar o atendimento aqui\n"
                        f"2️⃣ Fazer meu pedido pelo website\n"
                        f"3️⃣ Quero falar com um atendente\n\n"
                        f"Responda com o numero!"
                    )

                # Salvar mensagem do usuario
                await db.conversas.insert_one({
                    "phone": phone,
                    "message": message_text or "[MENSAGEM FORA DO HORÁRIO]",
                    "role": "user",
                    "timestamp": datetime.now(),
                    "canal": "WhatsApp",
                    "type": message_type,
                    "after_hours": True
                })

                await send_whatsapp_message(phone, intro_msg)

                await db.conversas.insert_one({
                    "phone": phone,
                    "message": intro_msg,
                    "role": "assistant",
                    "timestamp": datetime.now(),
                    "canal": "WhatsApp",
                    "after_hours": True
                })

                return JSONResponse({
                    "status": "after_hours_intro",
                    "message": "Fora do horario - iniciando fluxo de apresentacao"
                })

        # ============================================
        # PROCESSAR MENSAGEM DE TEXTO
        # ============================================
        if message_type == "text":
            text = data.get("text", {}).get("message", "")

            if not text:
                return JSONResponse({"status": "ignored", "reason": "empty text"})

            logger.info(f"Texto de {phone}: {text}")

            # Verificar se está aguardando confirmação de páginas (imagens)
            if phone in image_sessions and image_sessions[phone].get("waiting_confirmation"):
                # Respostas que confirmam que o total de paginas esta correto (sim, e isso, etc.)
                # NOTA: Como a pergunta agora e "Pode confirmar se sao todas as paginas?",
                # "sim" = confirmado, "nao" = tem mais paginas (NAO incluir nao/no aqui)
                respostas_confirmacao_paginas = [
                    "sim", "yes", "si", "isso", "e isso", "é isso", "isso mesmo",
                    "correto", "certo", "exato", "confirmado", "confirmo",
                    "só isso", "so isso", "só esse", "so esse", "só essa", "so essa",
                    "somente", "apenas", "only", "that's it", "that's all", "thats it", "thats all",
                    "é só", "e so", "so 1", "só 1", "somente 1", "apenas 1",
                    "1 pagina", "1 página", "one page", "just one", "just that",
                    "é esse", "e esse", "é essa", "e essa", "só esse documento", "so esse documento",
                    "apenas esse", "apenas essa", "just this", "just this one",
                    "pode traduzir", "pode seguir", "pode continuar",
                    "todas", "são todas", "sao todas", "is all", "all of them", "that is all"
                ]

                text_lower = text.lower().strip()
                confirmou_paginas = any(conf in text_lower for conf in respostas_confirmacao_paginas)

                # Tambem confirmar se o cliente respondeu com um numero igual ao total recebido
                total_session = image_sessions[phone]["count"]
                try:
                    if text.strip().isdigit() and int(text.strip()) == total_session:
                        confirmou_paginas = True
                except:
                    pass

                # Detectar se o cliente informou um numero DIFERENTE de paginas
                # Ex: bot recebeu 2, cliente diz "sao 3 paginas"
                import re
                numero_match = re.search(r'(\d+)\s*(pagina|página|pages?|pg)', text_lower)
                if numero_match:
                    numero_informado = int(numero_match.group(1))
                    if numero_informado > total_session:
                        # Cliente diz que tem mais paginas do que o bot recebeu
                        confirmou_paginas = False
                        image_sessions[phone]["waiting_confirmation"] = False
                        image_sessions[phone]["already_asked"] = False
                        estado = await get_cliente_estado(phone)
                        idioma = estado.get("idioma", "pt")
                        faltam = numero_informado - total_session
                        if idioma == "en":
                            msg = f"Got it! I received {total_session} so far. You can send the remaining {faltam} page{'s' if faltam > 1 else ''}."
                        elif idioma == "es":
                            msg = f"¡Entendido! Recibí {total_session} hasta ahora. Puedes enviar {'las' if faltam > 1 else 'la'} {faltam} página{'s' if faltam > 1 else ''} restante{'s' if faltam > 1 else ''}."
                        else:
                            msg = f"Entendido! Recebi {total_session} ate agora. Pode enviar {'as' if faltam > 1 else 'a'} {faltam} pagina{'s' if faltam > 1 else ''} que falta{'m' if faltam > 1 else ''}."
                        await send_whatsapp_message(phone, msg)
                        return JSONResponse({"status": "waiting_more_images"})
                    elif numero_informado == total_session:
                        confirmou_paginas = True

                if confirmou_paginas:
                    # Cliente confirmou o total de paginas
                    logger.info(f"Cliente confirmou - processando {image_sessions[phone]['count']} páginas")

                    resposta = await processar_sessao_imagem(phone)

                    if resposta:
                        await send_whatsapp_message(phone, resposta)
                        return JSONResponse({"status": "processed", "type": "image_batch"})
                else:
                    # Cliente indicou que tem mais paginas para enviar
                    image_sessions[phone]["waiting_confirmation"] = False
                    image_sessions[phone]["already_asked"] = False
                    estado = await get_cliente_estado(phone)
                    idioma = estado.get("idioma", "pt")
                    if idioma == "en":
                        msg = "Got it! You can send the remaining pages."
                    elif idioma == "es":
                        msg = "¡Entendido! Puedes enviar las demás páginas."
                    else:
                        msg = "Entendido! Pode enviar as demais páginas."
                    await send_whatsapp_message(phone, msg)
                    return JSONResponse({"status": "waiting_more_images"})

            # ============================================
            # VERIFICAR ETAPA DO ATENDIMENTO
            # ============================================
            estado = await get_cliente_estado(phone)
            etapa_atual = estado.get("etapa", ETAPAS["INICIAL"])

            # Atualizar idioma baseado na resposta do cliente
            idioma_detectado = detectar_idioma(text)
            if idioma_detectado != estado.get("idioma", "pt"):
                await set_cliente_estado(phone, idioma=idioma_detectado)

            # Salvar mensagem do usuario
            await db.conversas.insert_one({
                "phone": phone,
                "message": text,
                "role": "user",
                "timestamp": datetime.now(),
                "canal": "WhatsApp",
                "type": "text"
            })

            reply = None

            # VERIFICAR SE CLIENTE QUER FALAR COM HUMANO (em qualquer etapa)
            if await detectar_solicitacao_humano(text):
                logger.info(f"[HUMANO] Cliente {phone} solicitou atendente na etapa {etapa_atual}")
                await transferir_para_humano(phone, f"Cliente solicitou atendente (etapa: {etapa_atual})")
                idioma_cliente = estado.get("idioma", "pt")
                if idioma_cliente == "en":
                    reply = (
                        f"Of course! I'm forwarding you to our team right now.\n\n"
                        f"A representative will get in touch with you as soon as possible. 😊"
                    )
                elif idioma_cliente == "es":
                    reply = (
                        f"¡Por supuesto! Te estoy transfiriendo a nuestro equipo.\n\n"
                        f"Un representante se pondrá en contacto contigo lo antes posible. 😊"
                    )
                else:
                    reply = (
                        f"Claro! Estou encaminhando voce para nossa equipe.\n\n"
                        f"Um atendente entrara em contato o mais breve possivel. 😊"
                    )

                await send_whatsapp_message(phone, reply)
                await db.conversas.insert_one({
                    "phone": phone,
                    "message": reply,
                    "role": "assistant",
                    "timestamp": datetime.now(),
                    "canal": "WhatsApp"
                })
                return JSONResponse({"status": "transferred_to_human", "etapa": etapa_atual})

            # Processar baseado na etapa atual
            if etapa_atual == ETAPAS["AGUARDANDO_NOME"]:
                reply = await processar_etapa_nome(phone, text)
                estado_atualizado = await get_cliente_estado(phone)
                nova_etapa = estado_atualizado.get("etapa", "")
                logger.info(f"[ETAPA] {phone}: AGUARDANDO_NOME -> {nova_etapa}")

            elif etapa_atual == ETAPAS["AGUARDANDO_ORIGEM"]:
                # Etapa legada - tratar como se fosse nome (caso cliente esteja preso nessa etapa)
                reply = await processar_etapa_origem(phone, text)
                estado_atualizado = await get_cliente_estado(phone)
                nova_etapa = estado_atualizado.get("etapa", "")
                logger.info(f"[ETAPA] {phone}: AGUARDANDO_ORIGEM -> {nova_etapa}")

            elif etapa_atual == ETAPAS["AGUARDANDO_OPCAO_ATENDIMENTO"]:
                reply = await processar_etapa_opcao_atendimento(phone, text)
                logger.info(f"[ETAPA] {phone}: AGUARDANDO_OPCAO_ATENDIMENTO -> opcao processada")

            elif etapa_atual == ETAPAS["AGUARDANDO_CONFIRMACAO"]:
                reply = await processar_etapa_confirmacao(phone, text)
                if reply:
                    logger.info(f"[ETAPA] {phone}: AGUARDANDO_CONFIRMACAO -> AGUARDANDO_PAGAMENTO")
                # Se reply for None, continua para processamento normal com IA

            elif etapa_atual == ETAPAS["AGUARDANDO_PAGAMENTO"]:
                reply = await processar_etapa_pagamento(phone, text)
                if reply:
                    logger.info(f"[ETAPA] {phone}: Processando resposta na etapa AGUARDANDO_PAGAMENTO")
                # Se reply for None, continua para processamento normal com IA

            elif etapa_atual == ETAPAS["PAGAMENTO_RECEBIDO"]:
                # NOVO: Handler para após pagamento confirmado
                reply = await processar_etapa_pos_pagamento(phone, text)
                if reply:
                    logger.info(f"[ETAPA] {phone}: Processando resposta na etapa PAGAMENTO_RECEBIDO")
                # Se reply for None, continua para processamento normal com IA

            # Se nenhuma etapa especifica tratou, processar normalmente com IA
            if reply is None:
                # Detectar conversao (pagamento) - sistema antigo
                conversao_detectada = await detectar_conversao(phone, text)
                if conversao_detectada:
                    logger.info(f"CONVERSAO REGISTRADA: {phone}")

                # Injetar contexto do orcamento quando estiver em etapas de pagamento
                # para evitar que a IA gere mensagens com valor "0"
                extra_context = ""
                if etapa_atual in [ETAPAS["AGUARDANDO_CONFIRMACAO"], ETAPAS["AGUARDANDO_PAGAMENTO"]]:
                    valor_ctx = estado.get("valor_orcamento", "")
                    nome_ctx = estado.get("nome", "")
                    doc_ctx = estado.get("documento_info", {})
                    pages_ctx = doc_ctx.get("total_pages", 1) if doc_ctx else 1

                    # Se valor esta zerado, recalcular
                    import re as re_ctx
                    try:
                        val_num = float(re_ctx.sub(r'[^\d.,]', '', str(valor_ctx)).replace(',', '.') or '0')
                    except:
                        val_num = 0.0
                    if val_num <= 0:
                        val_num = pages_ctx * 24.99
                        valor_ctx = f"${val_num:.2f}"
                        await set_cliente_estado(phone, valor_orcamento=valor_ctx)

                    extra_context = (
                        f"\n\n[CONTEXTO INTERNO - NAO MOSTRAR AO CLIENTE: "
                        f"Cliente {nome_ctx}, orcamento de {valor_ctx} para {pages_ctx} pagina(s). "
                        f"Etapa atual: {etapa_atual}. "
                        f"Use o valor {valor_ctx} nas respostas sobre pagamento. "
                        f"NUNCA use valor 0 ou vazio. "
                        f"Formas de pagamento: VENMO @legacytranslations / ZELLE Contact@legacytranslations.com (LEGACY TRANSLATIONS INC)]"
                    )

                # Processar com IA
                reply = await process_message_with_ai(phone, text + extra_context if extra_context else text)

                # Analisar e sugerir conhecimento (Hybrid Learning)
                await analisar_e_sugerir_conhecimento(phone, text, reply)

            # Enviar resposta PRIMEIRO, depois salvar no banco
            envio_sucesso = await send_whatsapp_message(phone, reply)

            if not envio_sucesso:
                logger.error(f"[WEBHOOK] FALHA ao enviar resposta para {phone}!")
                logger.error(f"[WEBHOOK] Resposta que DEVERIA ter sido enviada: {reply[:200]}...")
                return JSONResponse({
                    "status": "error",
                    "reason": "send_failed",
                    "phone": phone,
                    "message": "Falha ao enviar resposta via Z-API"
                }, status_code=500)

            # Salvar resposta do bot (somente se envio foi bem sucedido)
            await db.conversas.insert_one({
                "phone": phone,
                "message": reply,
                "role": "assistant",
                "timestamp": datetime.now(),
                "canal": "WhatsApp",
                "envio_confirmado": True
            })

            logger.info(f"[WEBHOOK] Resposta enviada e salva com sucesso para {phone}")
            return JSONResponse({"status": "processed", "type": "text", "etapa": etapa_atual})

        # ============================================
        # PROCESSAR IMAGEM (COM AGRUPAMENTO - 4 SEGUNDOS)
        # ============================================
        elif message_type == "image":
            image_url = data.get("image", {}).get("imageUrl", "")
            caption = data.get("image", {}).get("caption", "")

            if not image_url:
                return JSONResponse({"status": "ignored", "reason": "no image url"})

            # DEDUP: Verificar se essa mesma URL de imagem ja foi processada
            if verificar_imagem_duplicada(image_url):
                logger.warning(f"[DEDUP-IMG] Webhook duplicado para imagem de {phone}: {image_url[:50]}")
                return JSONResponse({"status": "ignored", "reason": "duplicate_image_url"})

            logger.info(f"Imagem de {phone}: {image_url[:50]}")

            # Baixar imagem
            image_bytes = await download_media_from_zapi(image_url)

            if not image_bytes:
                estado = await get_cliente_estado(phone)
                idioma = estado.get("idioma", "pt")
                if idioma == "en":
                    msg = "Sorry, I couldn't download the image. Can you try sending it again?"
                elif idioma == "es":
                    msg = "Lo siento, no pude descargar la imagen. ¿Puedes intentar enviarla de nuevo?"
                else:
                    msg = "Desculpe, nao consegui baixar a imagem. Pode tentar enviar novamente?"
                await send_whatsapp_message(phone, msg)
                return JSONResponse({"status": "error", "reason": "download failed"})

            # ============================================
            # VERIFICAR SE ESTA NA ETAPA DE PAGAMENTO
            # ============================================
            estado = await get_cliente_estado(phone)
            etapa_atual = estado.get("etapa", ETAPAS["INICIAL"])

            if etapa_atual == ETAPAS["AGUARDANDO_PAGAMENTO"]:
                # Tratar imagem como possivel comprovante
                logger.info(f"[ETAPA] {phone}: Recebeu imagem na etapa AGUARDANDO_PAGAMENTO - tratando como comprovante")

                reply = await processar_etapa_pagamento(phone, "", is_image=True, image_bytes=image_bytes)

                if reply:
                    # Salvar no banco
                    await db.conversas.insert_one({
                        "phone": phone,
                        "message": "[IMAGEM RECEBIDA - POSSIVEL COMPROVANTE]",
                        "role": "user",
                        "timestamp": datetime.now(),
                        "canal": "WhatsApp",
                        "type": "image"
                    })

                    await db.conversas.insert_one({
                        "phone": phone,
                        "message": reply,
                        "role": "assistant",
                        "timestamp": datetime.now(),
                        "canal": "WhatsApp"
                    })

                    await send_whatsapp_message(phone, reply)
                    return JSONResponse({"status": "processed", "type": "receipt_check"})

            # ============================================
            # NOVO: VERIFICAR SE ESTA NA ETAPA POS-PAGAMENTO
            # Evita tratar imagens como novos documentos após pagamento
            # ============================================
            elif etapa_atual == ETAPAS["PAGAMENTO_RECEBIDO"]:
                logger.info(f"[ETAPA] {phone}: Recebeu imagem na etapa PAGAMENTO_RECEBIDO - perguntando se e novo documento")

                # DEDUP: Evitar responder multiplas vezes se cliente enviar varias imagens seguidas
                agora = datetime.now()
                ultima_resposta = pos_pagamento_respondido.get(phone)
                if ultima_resposta and (agora - ultima_resposta).total_seconds() < 30:
                    logger.info(f"[DEDUP-POS-PAG] {phone}: Ja respondeu a imagem pos-pagamento recentemente, ignorando")
                    return JSONResponse({"status": "ignored", "reason": "post_payment_dedup"})

                pos_pagamento_respondido[phone] = agora

                reply = await processar_etapa_pos_pagamento(phone, "", is_image=True, image_bytes=image_bytes)

                if reply:
                    # Salvar no banco
                    await db.conversas.insert_one({
                        "phone": phone,
                        "message": "[IMAGEM RECEBIDA - POS PAGAMENTO]",
                        "role": "user",
                        "timestamp": datetime.now(),
                        "canal": "WhatsApp",
                        "type": "image"
                    })

                    await db.conversas.insert_one({
                        "phone": phone,
                        "message": reply,
                        "role": "assistant",
                        "timestamp": datetime.now(),
                        "canal": "WhatsApp"
                    })

                    await send_whatsapp_message(phone, reply)
                    return JSONResponse({"status": "processed", "type": "post_payment_image"})

            # ============================================
            # FLUXO NORMAL: Sistema de agrupamento (4 segundos)
            # ============================================
            deve_perguntar = await adicionar_imagem_sessao(phone, image_bytes, image_url)

            if deve_perguntar:
                # VERIFICAR SE JÁ PERGUNTOU (EVITAR DUPLICATA)
                session = image_sessions[phone]

                # Se já está aguardando confirmação, não perguntar de novo
                if session.get("already_asked"):
                    logger.info(f"Já perguntou para {phone}, aguardando resposta...")
                    return JSONResponse({"status": "waiting_response", "pages": session["count"]})

                # Marcar como "já perguntou"
                session["already_asked"] = True

                total_atual = session["count"]
                idioma = estado.get("idioma", "pt")

                # ============================================
                # VERIFICAR SE É PRIMEIRA INTERAÇÃO (NOVO CLIENTE)
                # Se for, dar boas-vindas contextualizadas
                # ============================================
                conversas_anteriores = await db.conversas.count_documents({"phone": phone})
                e_primeiro_contato = conversas_anteriores <= 1  # Primeira ou segunda mensagem

                if e_primeiro_contato:
                    # NOVO CLIENTE - Mensagem de boas-vindas contextualizada
                    logger.info(f"[NOVO-CLIENTE] {phone}: Primeiro contato com documento - enviando boas-vindas")
                    if idioma == "en":
                        pergunta = (
                            f"Hi there! 👋 Welcome to Legacy Translations!\n\n"
                            f"I'm Mia, your virtual assistant. I received {total_atual} page{'s' if total_atual > 1 else ''} of your document! 📄\n\n"
                            f"Can you confirm that {'these are all the pages' if total_atual > 1 else 'this is the only page'} for translation?\n\n"
                            f"Once you confirm, I'll analyze the document and provide a quick quote! ⚡"
                        )
                    elif idioma == "es":
                        pergunta = (
                            f"¡Hola! 👋 ¡Bienvenido(a) a Legacy Translations!\n\n"
                            f"Soy Mia, tu asistente virtual. ¡Recibí {total_atual} página{'s' if total_atual > 1 else ''} de tu documento! 📄\n\n"
                            f"¿Puedes confirmar que {'son todas las páginas' if total_atual > 1 else 'es solo esta página'} para la traducción?\n\n"
                            f"¡Cuando confirmes, analizaré el documento y te daré una cotización rápida! ⚡"
                        )
                    else:
                        pergunta = (
                            f"Oi! 👋 Bem-vindo(a) a Legacy Translations!\n\n"
                            f"Sou a Mia, sua assistente virtual. Recebi {total_atual} pagina{'s' if total_atual > 1 else ''} do seu documento! 📄\n\n"
                            f"Pode confirmar se {'sao todas as paginas' if total_atual > 1 else 'e somente essa pagina'} para a traducao?\n\n"
                            f"Assim que confirmar, vou analisar o documento e te passar um orcamento rapidinho! ⚡"
                        )
                else:
                    # CLIENTE JÁ CONHECIDO - Mensagem mais direta
                    if idioma == "en":
                        pergunta = f"I received {total_atual} page{'s' if total_atual > 1 else ''}. Can you confirm {'these are all the pages' if total_atual > 1 else 'this is the only page'} for translation?"
                    elif idioma == "es":
                        pergunta = f"Recibí {total_atual} página{'s' if total_atual > 1 else ''}. ¿Puedes confirmar que {'son todas las páginas' if total_atual > 1 else 'es solo esta página'} para la traducción?"
                    else:
                        pergunta = f"Recebi {total_atual} pagina{'s' if total_atual > 1 else ''}. Pode confirmar se {'sao todas as paginas' if total_atual > 1 else 'e somente essa pagina'} para a traducao?"

                await send_whatsapp_message(phone, pergunta)

                logger.info(f"Pergunta enviada para {phone} ({total_atual} páginas)")
                return JSONResponse({"status": "waiting_confirmation", "pages": total_atual})

            # Se não deve perguntar, apenas aguardar mais imagens
            return JSONResponse({"status": "receiving", "pages": image_sessions[phone]["count"]})

        # ============================================
        # PROCESSAR AUDIO
        # ============================================
        elif message_type == "audio":
            audio_url = data.get("audio", {}).get("audioUrl", "")

            if not audio_url:
                return JSONResponse({"status": "ignored", "reason": "no audio url"})

            logger.info(f"Audio de {phone}: {audio_url[:50]}")

            # Baixar audio
            audio_bytes = await download_media_from_zapi(audio_url)

            if not audio_bytes:
                await send_whatsapp_message(phone, "Desculpe, nao consegui baixar o audio. Pode tentar enviar novamente?")
                return JSONResponse({"status": "error", "reason": "download failed"})

            # Transcrever com Whisper
            transcription = await process_audio_with_whisper(audio_bytes, phone)

            if not transcription:
                await send_whatsapp_message(phone, "Desculpe, nao consegui entender o audio. Pode escrever ou enviar novamente?")
                return JSONResponse({"status": "error", "reason": "transcription failed"})

            logger.info(f"Transcricao: {transcription}")

            # Salvar mensagem do usuario (transcricao do audio)
            await db.conversas.insert_one({
                "phone": phone,
                "message": f"[AUDIO] {transcription}",
                "role": "user",
                "timestamp": datetime.now(),
                "canal": "WhatsApp",
                "type": "audio"
            })

            # Processar transcricao com IA
            reply = await process_message_with_ai(phone, transcription)

            # Enviar resposta
            await send_whatsapp_message(phone, reply)

            # Salvar resposta do bot
            await db.conversas.insert_one({
                "phone": phone,
                "message": reply,
                "role": "assistant",
                "timestamp": datetime.now(),
                "canal": "WhatsApp"
            })

            return JSONResponse({"status": "processed", "type": "audio"})

        # ============================================
        # PROCESSAR PDF/DOCUMENT
        # ============================================
        elif message_type == "document":
            document_url = data.get("document", {}).get("documentUrl", "")
            mime_type = data.get("document", {}).get("mimeType", "")

            if not document_url:
                return JSONResponse({"status": "ignored", "reason": "no document url"})

            # Verificar se e PDF
            if "pdf" not in mime_type.lower():
                await send_whatsapp_message(phone, "Desculpe, so consigo analisar arquivos PDF no momento. Pode converter e enviar novamente?")
                return JSONResponse({"status": "ignored", "reason": "not pdf"})

            logger.info(f"PDF de {phone}: {document_url[:50]}")

            # Baixar PDF
            pdf_bytes = await download_media_from_zapi(document_url)

            if not pdf_bytes:
                await send_whatsapp_message(phone, "Desculpe, nao consegui baixar o PDF. Pode tentar enviar novamente?")
                return JSONResponse({"status": "error", "reason": "download failed"})

            # Analisar com Vision
            analysis = await process_pdf_with_vision(pdf_bytes, phone)

            # Enviar resposta
            await send_whatsapp_message(phone, analysis)

            return JSONResponse({"status": "processed", "type": "document"})

        else:
            logger.warning(f"Tipo de mensagem nao suportado: {message_type}")
            return JSONResponse({"status": "ignored", "reason": "unsupported type"})

    except Exception as e:
        logger.error(f"ERRO no webhook: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


# ============================================================
# ROTA: LOGIN
# ============================================================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Pagina de login"""
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    """Processar login"""
    if username == "admin" and password == "admin123":
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Usuário ou senha inválidos"})


# ============================================================
# ROTA: PAGINA INICIAL
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def root():
    """Pagina inicial"""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>MIA Bot - Legacy Translations</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .container {
            background: rgba(255,255,255,0.1);
            padding: 40px;
            border-radius: 20px;
            backdrop-filter: blur(10px);
        }
        h1 { font-size: 2.5em; margin-bottom: 10px; }
        .status { color: #4ade80; font-weight: bold; }
        a {
            display: inline-block;
            margin: 10px 10px 10px 0;
            padding: 15px 30px;
            background: white;
            color: #667eea;
            text-decoration: none;
            border-radius: 10px;
            font-weight: bold;
            transition: transform 0.2s;
        }
        a:hover { transform: scale(1.05); }
        .feature {
            background: rgba(255,255,255,0.1);
            padding: 10px;
            margin: 5px 0;
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 MIA Bot</h1>
        <p class="status">✅ Sistema Ativo</p>
        <p>Assistente virtual inteligente da Legacy Translations</p>

        <h3>📊 Painel Administrativo:</h3>
        <a href="/admin">Dashboard</a>
        <a href="/admin/treinamento">Treinamento IA</a>
        <a href="/admin/pipeline">Pipeline</a>
        <a href="/admin/leads">Leads</a>

        <h3>🚀 Recursos Implementados:</h3>
        <div class="feature">✅ Mensagens de texto (GPT-4)</div>
        <div class="feature">✅ Análise de imagens (GPT-4 Vision)</div>
        <div class="feature">✅ Agrupamento de múltiplas imagens (4 segundos)</div>
        <div class="feature">✅ Transcrição de áudio (Whisper)</div>
        <div class="feature">✅ Treinamento dinâmico (MongoDB)</div>
    </div>
</body>
</html>
"""


# ============================================================
# ROTA: HEALTH CHECK
# ============================================================
@app.get("/health")
async def health_check():
    """Health check para Render.com"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "MIA Bot",
        "version": "3.5 - Image Grouping Fixed"
    }


# ============================================================
# ENDPOINT DE RESET (TEMPORARIO)
# ============================================================
@app.get("/admin/reset-mode/{phone}")
async def reset_mode(phone: str):
    """Reset modo de conversa para IA (desbloquear)"""
    try:
        result = await db.conversas.update_many(
            {"phone": phone},
            {
                "$set": {"mode": "ia"},
                "$unset": {"transferred_at": "", "transfer_reason": ""}
            }
        )

        return {
            "status": "success",
            "phone": phone,
            "updated": result.modified_count,
            "message": f"Numero {phone} desbloqueado! Bot vai responder agora."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================
# ENDPOINT DE TESTE DE NOTIFICACAO
# ============================================================
@app.get("/admin/test-notification")
async def test_notification():
    """Testa envio de notificacao para numero do atendente"""
    try:
        mensagem_teste = f"""*TESTE DE NOTIFICACAO*

Este e um teste para verificar se as notificacoes estao chegando.

Hora do teste: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

Configuracao atual:
- Numero de notificacao: {NOTIFICACAO_PHONE}
- Numero do bot: {ATENDENTE_PHONE}

Se voce recebeu esta mensagem, as notificacoes estao funcionando!"""

        logger.info(f"[TESTE] Enviando notificacao de teste para {NOTIFICACAO_PHONE}")
        resultado = await send_whatsapp_message(NOTIFICACAO_PHONE, mensagem_teste)

        if resultado:
            return {
                "status": "success",
                "message": f"Notificacao enviada para {NOTIFICACAO_PHONE}",
                "notificacao_phone": NOTIFICACAO_PHONE,
                "atendente_phone": ATENDENTE_PHONE
            }
        else:
            return {
                "status": "error",
                "message": f"Falha ao enviar para {NOTIFICACAO_PHONE}. Verifique os logs.",
                "notificacao_phone": NOTIFICACAO_PHONE,
                "dica": "O numero precisa ter conversado com o bot antes (janela 24h do WhatsApp)"
            }
    except Exception as e:
        logger.error(f"[TESTE] Erro: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/admin/config-numbers")
async def get_config_numbers():
    """Mostra numeros configurados no sistema"""
    return {
        "atendente_phone": ATENDENTE_PHONE,
        "notificacao_phone": NOTIFICACAO_PHONE,
        "zapi_instance": ZAPI_INSTANCE_ID,
        "nota": "Para alterar, configure as variaveis ATENDENTE_PHONE e NOTIFICACAO_PHONE no Render"
    }


@app.get("/admin/reset-all-human")
async def reset_all_human_mode():
    """Reseta clientes em modo humano da ultima hora para modo IA"""
    from datetime import timedelta

    try:
        # Apenas conversas da ultima hora (evita mexer em conversas antigas)
        limite_tempo = datetime.now() - timedelta(hours=1)

        # Encontrar numeros em modo human COM atividade recente
        phones_human = await db.conversas.distinct("phone", {
            "mode": "human",
            "timestamp": {"$gte": limite_tempo}
        })

        if not phones_human:
            return {
                "status": "success",
                "message": "Nenhum cliente em modo humano na ultima hora",
                "phones_resetados": []
            }

        # Resetar apenas esses numeros
        result = await db.conversas.update_many(
            {
                "phone": {"$in": phones_human},
                "mode": "human"
            },
            {
                "$set": {"mode": "ia"},
                "$unset": {"transferred_at": "", "transfer_reason": ""}
            }
        )

        return {
            "status": "success",
            "message": f"{len(phones_human)} clientes recentes resetados para modo IA",
            "phones_resetados": phones_human,
            "documentos_atualizados": result.modified_count,
            "nota": "Apenas conversas da ultima hora foram afetadas"
        }
    except Exception as e:
        logger.error(f"Erro ao resetar: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================
# INICIAR SERVIDOR
# ============================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
