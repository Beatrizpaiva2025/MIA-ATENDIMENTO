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

# Importar rotas do admin
from admin_routes import router as admin_router
from admin_training_routes import router as training_router
from admin_controle_routes import router as controle_router
from admin_learning_routes import router as learning_router
from admin_atendimento_routes import router as atendimento_router
from admin_conversas_routes import router as conversas_router
from admin_orcamentos_routes import router as orcamentos_router
from webchat_routes import router as webchat_router

# ============================================================
# CONFIGURACAO DE LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

# ============================================================
# CONTROLE DO BOT - LIGAR/DESLIGAR
# ============================================================
# Estado global do bot (em memoria + MongoDB)
bot_status_cache = {
    "enabled": True,
    "last_update": datetime.now()
}


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
# Numeros do sistema (configuravel por ambiente)
ATENDENTE_PHONE = os.getenv("ATENDENTE_PHONE", "18573167770")  # Numero oficial de atendimento EUA
NOTIFICACAO_PHONE = os.getenv("NOTIFICACAO_PHONE", "18572081139")  # Numero pessoal EUA (recebe notificacoes)

# Timeout para modo humano (em minutos) - apos esse tempo, volta automaticamente para IA
HUMAN_MODE_TIMEOUT_MINUTES = int(os.getenv("HUMAN_MODE_TIMEOUT_MINUTES", "30"))

# ============================================================
# SISTEMA DE ETAPAS DO ATENDIMENTO
# ============================================================
# Etapas possiveis:
# - INICIAL: Conversa normal, sem documento analisado
# - AGUARDANDO_NOME: Bot pediu o nome do cliente
# - AGUARDANDO_ORIGEM: Bot pediu como conheceu a Legacy
# - AGUARDANDO_CONFIRMACAO: Orcamento enviado, aguardando cliente confirmar
# - AGUARDANDO_PAGAMENTO: Cliente confirmou, aguardando comprovante
# - PAGAMENTO_RECEBIDO: Comprovante recebido e confirmado

ETAPAS = {
    "INICIAL": "inicial",
    "AGUARDANDO_NOME": "aguardando_nome",
    "AGUARDANDO_ORIGEM": "aguardando_origem",
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
    "yes", "yes please", "go ahead", "proceed", "confirm", "i confirm"
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
    """Envia notificacao para atendente com resumo da conversa"""
    try:
        logger.info(f"[NOTIFICACAO] Iniciando notificacao para {NOTIFICACAO_PHONE} sobre cliente {phone}")

        # Buscar ultimas 10 mensagens da conversa
        mensagens = await db.conversas.find(
            {"phone": phone}
        ).sort("timestamp", -1).limit(10).to_list(length=10)

        # Inverter para ordem cronologica
        mensagens.reverse()

        # Montar resumo
        resumo_linhas = []
        for msg in mensagens:
            role = "Cliente" if msg.get("role") == "user" else "IA"
            texto = msg.get("message", "")[:100]
            resumo_linhas.append(f"{role}: {texto}")

        resumo = "\n".join(resumo_linhas) if resumo_linhas else "Sem historico"

        # Montar mensagem de notificacao
        mensagem_atendente = f"""*TRANSFERENCIA DE ATENDIMENTO*

Cliente: {phone}
Motivo: {motivo}

Resumo da Conversa:
{resumo}

*COMANDOS (envie NA CONVERSA DO CLIENTE):*
* = Pausar IA (ja esta pausada)
+ = Retomar IA"""

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
        # Frases comuns
        "falar com alguem", "falar com alguém",
        "falar com humano", "falar com atendente",
        "falar com uma pessoa", "falar com pessoa",
        "atendimento humano", "atendente humano",
        "quero falar", "preciso falar",
        "quero um atendente", "quero atendente",
        "preciso de atendente", "preciso atendente",
        "transferir", "transfere",
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
        # Atualizar status no banco
        await db.conversas.update_many(
            {"phone": phone},
            {
                "$set": {
                    "mode": "human",
                    "transferred_at": datetime.now(),
                    "transfer_reason": motivo
                }
            }
        )

        # Notificar atendente (INVISIVEL - cliente nao sabe)
        await notificar_atendente(phone, motivo)

        # NAO enviar mensagem ao cliente (transferencia invisivel)
        # Cliente continua conversando normalmente, mas atendente humano assume

        logger.info(f"Conversa transferida para humano: {phone} (Motivo: {motivo})")
        return True

    except Exception as e:
        logger.error(f"Erro ao transferir para humano: {e}")
        return False


async def verificar_timeout_modo_humano(phone: str) -> bool:
    """
    Verifica se o modo humano expirou (timeout).
    Se expirou, retorna a conversa para modo IA automaticamente.
    Retorna True se estava em timeout e foi resetado, False caso contrario.
    """
    from datetime import timedelta

    try:
        # Buscar ultima conversa com modo human
        conversa = await db.conversas.find_one(
            {"phone": phone, "mode": "human"},
            sort=[("timestamp", -1)]
        )

        if not conversa:
            return False

        transferred_at = conversa.get("transferred_at")
        if not transferred_at:
            # Se nao tem timestamp de transferencia, usar timestamp da mensagem
            transferred_at = conversa.get("timestamp", datetime.now())

        # Verificar se passou o timeout
        tempo_limite = transferred_at + timedelta(minutes=HUMAN_MODE_TIMEOUT_MINUTES)

        if datetime.now() > tempo_limite:
            # Timeout expirou - verificar se houve resposta do atendente
            # Buscar mensagens do atendente (role=assistant) apos a transferencia
            resposta_atendente = await db.conversas.find_one({
                "phone": phone,
                "role": "assistant",
                "timestamp": {"$gt": transferred_at}
            })

            if not resposta_atendente:
                # Nenhuma resposta do atendente - resetar para IA
                await db.conversas.update_many(
                    {"phone": phone},
                    {
                        "$set": {"mode": "ia"},
                        "$unset": {"transferred_at": "", "transfer_reason": ""}
                    }
                )
                logger.info(f"[TIMEOUT] Conversa {phone} retornou para IA apos {HUMAN_MODE_TIMEOUT_MINUTES} min sem resposta do atendente")
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
# SISTEMA DE AGRUPAMENTO DE IMAGENS
# ============================================================
image_sessions = {}  # Cache temporário de sessões de imagem

async def iniciar_sessao_imagem(phone: str):
    """Inicia sessão de agrupamento de imagens"""
    image_sessions[phone] = {
        "count": 0,
        "images": [],
        "last_received": datetime.now(),
        "waiting_confirmation": False,
        "already_asked": False
    }
    logger.info(f"Sessão de imagem iniciada: {phone}")


async def adicionar_imagem_sessao(phone: str, image_bytes: bytes):
    """Adiciona imagem à sessão e retorna se deve processar"""
    if phone not in image_sessions:
        await iniciar_sessao_imagem(phone)
    
    session = image_sessions[phone]
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
    """Processa todas as imagens da sessão - FASE 1: Analise e pedir nome"""
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

    # Guardar informacoes do documento no estado
    await set_cliente_estado(
        phone,
        etapa=ETAPAS["AGUARDANDO_NOME"],
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

    # Mensagens em diferentes idiomas
    if idioma == "en":
        mensagem = (
            f"Hello! I'm MIA, Legacy Translations' virtual assistant! 🌎\n\n"
            f"I see you sent {total_pages} page{'s' if total_pages > 1 else ''} of a {tipo_doc} "
            f"in {idioma_origem}.\n\n"
            f"Can you confirm if you'd like to translate {'them' if total_pages > 1 else 'it'} to {idioma_destino}?\n\n"
            f"Also, may I have your name please?"
        )
    elif idioma == "es":
        mensagem = (
            f"¡Hola! Soy MIA, asistente virtual de Legacy Translations! 🌎\n\n"
            f"Veo que enviaste {total_pages} página{'s' if total_pages > 1 else ''} de un {tipo_doc} "
            f"en {idioma_origem}.\n\n"
            f"¿Puedes confirmar si deseas traducir{'las' if total_pages > 1 else 'lo'} al {idioma_destino}?\n\n"
            f"Además, ¿me puedes decir tu nombre por favor?"
        )
    else:  # Portugues (padrao)
        mensagem = (
            f"Ola! Sou a MIA, assistente virtual da Legacy Translations! 🌎\n\n"
            f"Vi que voce enviou {total_pages} pagina{'s' if total_pages > 1 else ''} de um {tipo_doc} "
            f"em {idioma_origem}.\n\n"
            f"Pode confirmar se deseja traduzi-lo{'s' if total_pages > 1 else ''} para o {idioma_destino}?\n\n"
            f"E tambem, qual e o seu nome?"
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

    await db.conversas.insert_one({
        "phone": phone,
        "message": mensagem,
        "role": "assistant",
        "timestamp": datetime.now(),
        "canal": "WhatsApp"
    })

    # Limpar sessão de imagens (ja salvamos no estado)
    del image_sessions[phone]

    logger.info(f"Analise de documento enviada para {phone} ({total_pages} paginas)")
    return mensagem


async def gerar_orcamento_final(phone: str) -> str:
    """Gera o orcamento final apos coletar nome e origem"""
    estado = await get_cliente_estado(phone)
    doc_info = estado.get("documento_info", {})
    idioma = estado.get("idioma", "pt")
    nome = estado.get("nome", "")

    total_pages = doc_info.get("total_pages", 1)
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

    # Extrair valor do orcamento (buscar padrao $XX.XX ou R$XX,XX)
    import re
    valor_match = re.search(r'[\$R]\$?\s*(\d+[.,]?\d*)', orcamento)
    valor_str = valor_match.group(0) if valor_match else "0"

    # Converter valor para float
    try:
        valor_num = float(valor_str.replace('$', '').replace('R$', '').replace(',', '.').strip())
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
    # Detectar e atualizar idioma
    idioma = detectar_idioma(mensagem)

    # Extrair nome (geralmente e a primeira palavra ou frase curta)
    nome = mensagem.strip().split('\n')[0].strip()
    # Limpar pontuacao
    nome = nome.rstrip('.,!?')
    # Se for muito longo, pegar primeiras palavras
    if len(nome.split()) > 4:
        nome = ' '.join(nome.split()[:3])

    # Salvar nome e idioma
    await set_cliente_estado(
        phone,
        nome=nome,
        idioma=idioma,
        etapa=ETAPAS["AGUARDANDO_ORIGEM"]
    )

    # Perguntar origem baseado no idioma
    if idioma == "en":
        resposta = (
            f"Nice to meet you, {nome}! 😊\n\n"
            f"Before I give you the quote, could you tell me how you heard about Legacy Translations?\n\n"
            f"1️⃣ Google Search\n"
            f"2️⃣ Instagram\n"
            f"3️⃣ Facebook\n"
            f"4️⃣ Friend's referral\n\n"
            f"Just reply with the number or the option!"
        )
    elif idioma == "es":
        resposta = (
            f"¡Mucho gusto, {nome}! 😊\n\n"
            f"Antes de darte el presupuesto, ¿podrías decirme cómo conociste Legacy Translations?\n\n"
            f"1️⃣ Búsqueda en Google\n"
            f"2️⃣ Instagram\n"
            f"3️⃣ Facebook\n"
            f"4️⃣ Referencia de amigo\n\n"
            f"¡Solo responde con el número o la opción!"
        )
    else:
        resposta = (
            f"Prazer em conhece-lo(a), {nome}! 😊\n\n"
            f"Antes de passar o orcamento, poderia me dizer como conheceu a Legacy Translations?\n\n"
            f"1️⃣ Pesquisa no Google\n"
            f"2️⃣ Instagram\n"
            f"3️⃣ Facebook\n"
            f"4️⃣ Referencia de amigo\n\n"
            f"Responda com o numero ou a opcao!"
        )

    return resposta


async def processar_etapa_origem(phone: str, mensagem: str) -> str:
    """Processa resposta da origem e gera orcamento"""
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

    # Salvar origem
    await set_cliente_estado(phone, origem=origem)

    # Agradecer baseado no idioma
    if idioma == "en":
        agradecimento = f"Thank you, {nome}! Great to know you found us through {origem}. 🙏\n\n"
    elif idioma == "es":
        agradecimento = f"¡Gracias, {nome}! Que bueno saber que nos encontraste por {origem}. 🙏\n\n"
    else:
        agradecimento = f"Obrigada, {nome}! Que bom saber que nos conheceu pelo {origem}. 🙏\n\n"

    # Gerar orcamento
    orcamento = await gerar_orcamento_final(phone)

    return agradecimento + orcamento


async def processar_etapa_confirmacao(phone: str, mensagem: str) -> str:
    """Processa confirmacao do cliente e muda para aguardando pagamento"""
    estado = await get_cliente_estado(phone)
    idioma = estado.get("idioma", "pt")
    nome = estado.get("nome", "")
    valor = estado.get("valor_orcamento", "")

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

        if idioma == "en":
            resposta = (
                f"Perfect, {nome}! 🎉\n\n"
                f"To proceed, please send the payment of {valor} via:\n"
                f"• Zelle\n• Venmo\n• PayPal\n• Bank Transfer\n\n"
                f"After payment, just send the receipt/screenshot here and I'll confirm! ✅"
            )
        elif idioma == "es":
            resposta = (
                f"¡Perfecto, {nome}! 🎉\n\n"
                f"Para continuar, envía el pago de {valor} por:\n"
                f"• Zelle\n• Venmo\n• PayPal\n• Transferencia bancaria\n\n"
                f"Después del pago, solo envía el comprobante aquí y confirmo! ✅"
            )
        else:
            resposta = (
                f"Perfeito, {nome}! 🎉\n\n"
                f"Para prosseguir, envie o pagamento de {valor} via:\n"
                f"• Zelle\n• Venmo\n• PayPal\n• Transferencia bancaria\n\n"
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
                f"Thank you, {nome}! We'll start working on your translation right away.\n\n"
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
                f"¡Gracias, {nome}! Comenzaremos tu traducción de inmediato.\n\n"
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
                f"Obrigada, {nome}! Ja vamos iniciar sua traducao.\n\n"
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

# ============================================================
# CONFIGURACOES Z-API
# ============================================================
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
ZAPI_URL = os.getenv("ZAPI_URL", "https://api.z-api.io")


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
async def get_bot_training() -> str:
    """Busca treinamento dinamico do bot Mia no MongoDB"""
    try:
        bot = await db.bots.find_one({"name": "Mia"})

        if not bot:
            logger.warning("Bot Mia nao encontrado no banco, usando padrao")
            return """Voce e a Mia, assistente da Legacy Translations.

Responda de forma profissional e educada."""

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

        # Base de conhecimento
        if knowledge_base:
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
        return """Voce e a Mia, assistente da Legacy Translations.

Responda de forma profissional e educada."""


# ============================================================
# FUNCAO: ENVIAR MENSAGEM WHATSAPP
# ============================================================
async def send_whatsapp_message(phone: str, message: str):
    """Envia mensagem via Z-API com Client-Token"""
    try:
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

        # Logs de debug
        logger.info(f"Enviando mensagem para {phone}")
        logger.info(f"Client-Token: {'Configurado' if headers['Client-Token'] else 'VAZIO'}")

        # Enviar requisicao COM headers
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)

            logger.info(f"Status Z-API: {response.status_code}")
            logger.info(f"Resposta: {response.text}")

            if response.status_code == 200:
                logger.info(f"Mensagem enviada com sucesso")
                return True
            else:
                logger.error(f"Erro ao enviar: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f"Excecao ao enviar mensagem: {str(e)}")
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
async def process_message_with_ai(phone: str, message: str) -> str:
    """Processar mensagem com GPT-4 usando treinamento dinamico"""
    try:
        # Detectar se cliente quer falar com humano
        if await detectar_solicitacao_humano(message):
            await transferir_para_humano(phone, "Cliente solicitou atendente")
            # Retornar mensagem informativa sobre a transferencia
            return (
                "Perfeito! Estou encaminhando voce para um de nossos especialistas. "
                "Por favor aguarde, em breve alguem ira te atender. "
                "Se preferir, pode continuar enviando suas duvidas enquanto aguarda."
            )

        # Buscar treinamento dinamico do MongoDB
        system_prompt = await get_bot_training()

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

        # Salvar no banco
        await db.conversas.insert_one({
            "phone": phone,
            "message": message,
            "role": "user",
            "timestamp": datetime.now(),
            "canal": "WhatsApp"
        })

        await db.conversas.insert_one({
            "phone": phone,
            "message": reply,
            "role": "assistant",
            "timestamp": datetime.now(),
            "canal": "WhatsApp"
        })

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
        from_me = data.get("fromMe", False)

        # Extrair texto de forma mais robusta
        message_text = ""
        if "text" in data:
            if isinstance(data["text"], dict):
                message_text = data["text"].get("message", "")
            elif isinstance(data["text"], str):
                message_text = data["text"]
        message_text = message_text.strip() if message_text else ""

        logger.info(f"[WEBHOOK] phone={phone}, fromMe={from_me}, text='{message_text}'")

        # ============================================
        # PROCESSAR COMANDOS DO OPERADOR (fromMe=true)
        # Quando operador envia * ou + na conversa com cliente
        # ============================================
        if from_me:
            # Verificar comandos de controle
            comando = message_text.strip().lower()
            logger.info(f"[OPERADOR] Mensagem fromMe detectada: '{comando}' para cliente {phone}")

            # Comando para pausar IA: * ou pause ou pausar
            if comando in ["*", "pause", "pausar", "pausa"]:
                await db.conversas.update_many(
                    {"phone": phone},
                    {"$set": {"mode": "human", "transferred_at": datetime.now()}}
                )
                logger.info(f"[OPERADOR] IA PAUSADA para cliente {phone}")
                return {"status": "ia_paused", "client": phone}

            # Comando para retomar IA: + ou resume ou retomar
            elif comando in ["+", "resume", "retomar", "retoma", "volta", "voltar"]:
                # Resetar modo na collection conversas
                await db.conversas.update_many(
                    {"phone": phone},
                    {"$set": {"mode": "ia"}, "$unset": {"transferred_at": "", "transfer_reason": ""}}
                )
                # Resetar etapa do cliente para INICIAL
                await set_cliente_estado(phone, etapa=ETAPAS["INICIAL"])
                logger.info(f"[OPERADOR] IA RETOMADA para cliente {phone}")
                return {"status": "ia_resumed", "client": phone}

            # Ignorar outras mensagens enviadas pelo operador (nao interferir)
            logger.info(f"[OPERADOR] Mensagem normal ignorada (operador respondendo cliente)")
            return {"status": "ignored", "reason": "operator_message"}

        # ============================================
        # VERIFICAR STATUS DO BOT
        # ============================================
        bot_status = await get_bot_status()

        # Verificar se conversa esta em modo humano
        conversa = await db.conversas.find_one({"phone": phone}, sort=[("timestamp", -1)])
        modo_humano = conversa and conversa.get("mode") == "human"

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
            logger.info(f"Bot {'desligado' if not bot_status['enabled'] else 'em modo humano para ' + phone}")

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
        # Comando: * (Transferir para humano)
        if message_text == "*":
            await transferir_para_humano(phone, "Cliente digitou *")
            return {"status": "transferred_to_human"}

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
        # PROCESSAR MENSAGEM DE TEXTO
        # ============================================
        if message_type == "text":
            text = data.get("text", {}).get("message", "")

            if not text:
                return JSONResponse({"status": "ignored", "reason": "empty text"})

            logger.info(f"Texto de {phone}: {text}")

            # Verificar se está aguardando confirmação de páginas (imagens)
            if phone in image_sessions and image_sessions[phone].get("waiting_confirmation"):
                respostas_negativas = ["não", "nao", "só isso", "so isso", "não tenho", "nao tenho", "é só", "e so"]

                if any(neg in text.lower() for neg in respostas_negativas):
                    # Cliente confirmou que não tem mais páginas
                    logger.info(f"Cliente confirmou - processando {image_sessions[phone]['count']} páginas")

                    resposta = await processar_sessao_imagem(phone)

                    if resposta:
                        await send_whatsapp_message(phone, resposta)
                        return JSONResponse({"status": "processed", "type": "image_batch"})
                else:
                    # Cliente disse que tem mais páginas
                    image_sessions[phone]["waiting_confirmation"] = False
                    image_sessions[phone]["already_asked"] = False
                    estado = await get_cliente_estado(phone)
                    idioma = estado.get("idioma", "pt")
                    if idioma == "en":
                        msg = "Ok! You can send the remaining pages."
                    elif idioma == "es":
                        msg = "¡Ok! Puedes enviar las demás páginas."
                    else:
                        msg = "Ok! Pode enviar as demais páginas."
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

            # Processar baseado na etapa atual
            if etapa_atual == ETAPAS["AGUARDANDO_NOME"]:
                reply = await processar_etapa_nome(phone, text)
                logger.info(f"[ETAPA] {phone}: AGUARDANDO_NOME -> AGUARDANDO_ORIGEM")

            elif etapa_atual == ETAPAS["AGUARDANDO_ORIGEM"]:
                reply = await processar_etapa_origem(phone, text)
                logger.info(f"[ETAPA] {phone}: AGUARDANDO_ORIGEM -> AGUARDANDO_CONFIRMACAO")

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

            # Se nenhuma etapa especifica tratou, processar normalmente com IA
            if reply is None:
                # Detectar conversao (pagamento) - sistema antigo
                conversao_detectada = await detectar_conversao(phone, text)
                if conversao_detectada:
                    logger.info(f"CONVERSAO REGISTRADA: {phone}")

                # Processar com IA
                reply = await process_message_with_ai(phone, text)

                # Analisar e sugerir conhecimento (Hybrid Learning)
                await analisar_e_sugerir_conhecimento(phone, text, reply)

            # Salvar resposta do bot
            await db.conversas.insert_one({
                "phone": phone,
                "message": reply,
                "role": "assistant",
                "timestamp": datetime.now(),
                "canal": "WhatsApp"
            })

            # Enviar resposta
            await send_whatsapp_message(phone, reply)

            return JSONResponse({"status": "processed", "type": "text", "etapa": etapa_atual})

        # ============================================
        # PROCESSAR IMAGEM (COM AGRUPAMENTO - 4 SEGUNDOS)
        # ============================================
        elif message_type == "image":
            image_url = data.get("image", {}).get("imageUrl", "")
            caption = data.get("image", {}).get("caption", "")

            if not image_url:
                return JSONResponse({"status": "ignored", "reason": "no image url"})

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
            # FLUXO NORMAL: Sistema de agrupamento (4 segundos)
            # ============================================
            deve_perguntar = await adicionar_imagem_sessao(phone, image_bytes)

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

                if idioma == "en":
                    pergunta = f"I received {total_atual} page{'s' if total_atual > 1 else ''}. Do you have any more pages to translate?"
                elif idioma == "es":
                    pergunta = f"Recibí {total_atual} página{'s' if total_atual > 1 else ''}. ¿Tienes más páginas para traducir?"
                else:
                    pergunta = f"Recebi {total_atual} pagina{'s' if total_atual > 1 else ''}. Tem mais alguma pagina para traduzir?"

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

            # Processar transcricao com IA
            reply = await process_message_with_ai(phone, transcription)

            # Enviar resposta
            await send_whatsapp_message(phone, reply)

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
