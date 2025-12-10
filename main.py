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
# Numeros do sistema
ATENDENTE_PHONE = "18573167770"  # Numero oficial de atendimento EUA (responde clientes)
NOTIFICACAO_PHONE = "18572081139"  # Numero pessoal EUA (recebe notificacoes)

async def notificar_atendente(phone: str, motivo: str = "Cliente solicitou"):
    """Envia notificacao para atendente com resumo da conversa"""
    try:
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

Para assumir o atendimento, responda ao cliente diretamente.
Cliente digitando + volta para IA automaticamente."""

        # Enviar notificacao para numero pessoal
        await send_whatsapp_message(NOTIFICACAO_PHONE, mensagem_atendente)
        logger.info(f"Notificacao enviada para atendente: {phone}")

        return True
    except Exception as e:
        logger.error(f"Erro ao notificar atendente: {e}")
        return False


async def detectar_solicitacao_humano(message: str) -> bool:
    """Detecta se cliente esta pedindo atendente humano"""
    palavras_chave = [
        "atendente", "humano", "pessoa", "falar com alguem", "falar com alguem",
        "operador", "atendimento humano", "quero falar", "preciso falar", "transferir"
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
        "waiting_confirmation": False
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


async def processar_sessao_imagem(phone: str):
    """Processa todas as imagens da sessão e gera orçamento"""
    if phone not in image_sessions:
        return None
    
    session = image_sessions[phone]
    total_pages = session["count"]
    
    # Pegar apenas a primeira imagem para análise (Vision)
    first_image = session["images"][0]
    
    # Buscar treinamento
    training_prompt = await get_bot_training()
    
    # Converter primeira imagem para base64
    base64_image = base64.b64encode(first_image).decode('utf-8')
    
    # Chamar GPT-4 Vision com contexto de múltiplas páginas
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": f"""{training_prompt}

TAREFA ESPECIAL - ORÇAMENTO DE MÚLTIPLAS PÁGINAS:
O cliente enviou {total_pages} página(s) para tradução.
Analise a primeira página e forneça:
- Idioma detectado
- Cálculo: {total_pages} páginas × valor unitário
- Prazo de entrega
- Instruções de pagamento

NÃO mencione "histórico escolar" ou "estimando como uma única página".
Seja direto e objetivo."""
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Preciso traduzir estas {total_pages} páginas. Quanto fica?"
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
    
    orcamento = response.choices[0].message.content
    
    # Salvar no banco
    await db.conversas.insert_one({
        "phone": phone,
        "message": f"[{total_pages} IMAGENS ENVIADAS]",
        "role": "user",
        "timestamp": datetime.now(),
        "canal": "WhatsApp",
        "type": "image_batch"
    })
    
    await db.conversas.insert_one({
        "phone": phone,
        "message": orcamento,
        "role": "assistant",
        "timestamp": datetime.now(),
        "canal": "WhatsApp"
    })
    
    # Limpar sessão
    del image_sessions[phone]
    
    logger.info(f"Orçamento gerado para {total_pages} páginas")
    return orcamento


# ============================================================
# INCLUIR ROTAS DO PAINEL ADMIN
# ============================================================
app.include_router(admin_router)
app.include_router(training_router)
app.include_router(controle_router)
app.include_router(learning_router)
app.include_router(atendimento_router)
app.include_router(conversas_router)

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
        await send_whatsapp_message(phone, "Desculpe, nao consegui baixar a imagem. Pode tentar enviar novamente?")
        return JSONResponse({"status": "error", "reason": "download failed"})

    # Sistema de agrupamento (4 segundos)
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
        pergunta = f"Recebi {total_atual} página{'s' if total_atual > 1 else ''}. Tem mais alguma página para traduzir?"
        
        await send_whatsapp_message(phone, pergunta)
        
        logger.info(f"Pergunta enviada para {phone} ({total_atual} páginas)")
        return JSONResponse({"status": "waiting_confirmation", "pages": total_atual})
    
    # Se não deve perguntar, apenas aguardar mais imagens
    return JSONResponse({"status": "receiving", "pages": image_sessions[phone]["count"]})

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
            # Retornar mensagem normal (invisivel - cliente nao sabe que foi transferido)
            # Mensagem natural sem mencionar "humano" ou "robo"
            return "Perfeito! Vou transferir voce agora para um de nossos especialistas que podera te ajudar melhor com isso. Um momento, por favor."

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
        message_text = ""
        if "text" in data and "message" in data["text"]:
            message_text = data["text"]["message"].strip()

        # ============================================
        # PROCESSAR COMANDOS DO OPERADOR (fromMe=true)
        # Quando operador envia * ou + na conversa com cliente
        # ============================================
        if from_me and message_text in ["*", "+"]:
            if message_text == "*":
                await db.conversas.update_many(
                    {"phone": phone},
                    {"$set": {"mode": "human", "transferred_at": datetime.now()}}
                )
                logger.info(f"[OPERADOR] IA PAUSADA para cliente {phone}")
                return {"status": "ia_paused", "client": phone}

            elif message_text == "+":
                await db.conversas.update_many(
                    {"phone": phone},
                    {"$set": {"mode": "ia"}, "$unset": {"transferred_at": "", "transfer_reason": ""}}
                )
                logger.info(f"[OPERADOR] IA RETOMADA para cliente {phone}")
                return {"status": "ia_resumed", "client": phone}

        # ============================================
        # IGNORAR OUTRAS MENSAGENS ENVIADAS (fromMe=true)
        # ============================================
        if from_me:
            logger.info(f"Mensagem enviada (fromMe=true) ignorada")
            return {"status": "ignored", "reason": "from_me"}

        # ============================================
        # VERIFICAR STATUS DO BOT
        # ============================================
        bot_status = await get_bot_status()

        # Verificar se conversa esta em modo humano
        conversa = await db.conversas.find_one({"phone": phone}, sort=[("timestamp", -1)])
        modo_humano = conversa and conversa.get("mode") == "human"

        # Se bot desligado OU conversa em modo humano, nao processar
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

            # Verificar se está aguardando confirmação de páginas
            if phone in image_sessions and image_sessions[phone].get("waiting_confirmation"):
                respostas_negativas = ["não", "nao", "só isso", "so isso", "não tenho", "nao tenho", "é só", "e so"]
                
                if any(neg in text.lower() for neg in respostas_negativas):
                    # Cliente confirmou que não tem mais páginas
                    logger.info(f"Cliente confirmou - processando {image_sessions[phone]['count']} páginas")
                    
                    orcamento = await processar_sessao_imagem(phone)
                    
                    if orcamento:
                        await send_whatsapp_message(phone, orcamento)
                        return JSONResponse({"status": "processed", "type": "image_batch"})
                else:
                    # Cliente disse que tem mais páginas
                    image_sessions[phone]["waiting_confirmation"] = False
                    await send_whatsapp_message(phone, "Ok! Pode enviar as demais páginas.")
                    return JSONResponse({"status": "waiting_more_images"})

            # Detectar conversao (pagamento)
            conversao_detectada = await detectar_conversao(phone, text)

            if conversao_detectada:
                logger.info(f"CONVERSAO REGISTRADA: {phone}")

            # Processar com IA
            reply = await process_message_with_ai(phone, text)

            # Analisar e sugerir conhecimento (Hybrid Learning)
            await analisar_e_sugerir_conhecimento(phone, text, reply)

            # Enviar resposta
            await send_whatsapp_message(phone, reply)

            return JSONResponse({"status": "processed", "type": "text", "conversion": conversao_detectada})

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
                await send_whatsapp_message(phone, "Desculpe, nao consegui baixar a imagem. Pode tentar enviar novamente?")
                return JSONResponse({"status": "error", "reason": "download failed"})

            # Sistema de agrupamento (4 segundos)
            deve_perguntar = await adicionar_imagem_sessao(phone, image_bytes)
            
            if deve_perguntar:
                # Perguntar se tem mais páginas
                session = image_sessions[phone]
                total_atual = session["count"]
                
                pergunta = f"Recebi {total_atual} página{'s' if total_atual > 1 else ''}. Tem mais alguma página para traduzir?"
                await send_whatsapp_message(phone, pergunta)
                
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
        "version": "3.5 - Image Grouping Only"
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
# INICIAR SERVIDOR
# ============================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
