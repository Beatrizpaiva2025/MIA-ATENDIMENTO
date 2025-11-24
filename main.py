# ============================================================
# MIA BOT - SISTEMA MULTI-CANAL
# ============================================================
# Canais suportados:
# ✅ WhatsApp (Z-API) - ATIVO
# 🔜 Instagram (Meta API) - PREPARADO
# 🔜 Web Chat (WebSocket) - PREPARADO
# ============================================================
# Funcionalidades:
# ✅ Mensagens de texto com OpenAI
# ✅ Imagens (GPT-4 Vision)
# ✅ Áudios (Whisper)
# ✅ PDFs (Extração + Vision)
# ✅ Atendimento Humano
# ✅ Painel Administrativo Completo
# ✅ Gestão de Leads
# ============================================================

from fastapi import FastAPI, Request, HTTPException, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware
import os
import httpx
from openai import AsyncOpenAI
from datetime import datetime, timedelta
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import traceback
import json
import base64
from io import BytesIO
from PyPDF2 import PdfReader
from pdf2image import convert_from_bytes
from PIL import Image

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Mia Bot - Sistema Multi-Canal")

# Middleware
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY", "mia-secret-key-2024"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files e templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Cliente OpenAI
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("❌ MONGODB_URI não configurado nas variáveis de ambiente")
mongo_client = AsyncIOMotorClient(MONGODB_URI)
db = mongo_client.mia_bot

# ============================================================
# CONFIGURAÇÕES
# ============================================================
ATENDENTE_PHONE = "18572081139"  # Número do atendente humano

# Z-API (WhatsApp)
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")

# Instagram (preparado para futuro)
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_PAGE_ID = os.getenv("INSTAGRAM_PAGE_ID", "")

# Web Chat (preparado para futuro)
WEBCHAT_ENABLED = os.getenv("WEBCHAT_ENABLED", "false").lower() == "true"

# ============================================================
# MODELOS DE DADOS
# ============================================================
class Message(BaseModel):
    phone: str
    message: str
    timestamp: datetime = datetime.now()
    role: str = "user"
    message_type: str = "text"
    canal: str = "whatsapp"

class ChannelConfig(BaseModel):
    canal: str
    enabled: bool
    config: Dict[str, Any] = {}

# ============================================================
# CONTROLE DE ACESSO
# ============================================================
def get_current_user(request: Request):
    username = request.session.get('username')
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return username

def check_admin_access(request: Request):
    username = get_current_user(request)
    if username.lower() != 'admin':
        raise HTTPException(status_code=403, detail="Admin only")
    return username

# ============================================================
# GERENCIAMENTO DE CANAIS
# ============================================================
async def get_channel_status(canal: str) -> bool:
    """Verifica se um canal está ativo"""
    try:
        config = await db.channel_config.find_one({"canal": canal})
        if config:
            return config.get("enabled", False)
        # Padrão: WhatsApp ativo, outros inativos
        return canal == "whatsapp"
    except Exception as e:
        logger.error(f"Erro ao buscar status do canal {canal}: {e}")
        return canal == "whatsapp"

async def set_channel_status(canal: str, enabled: bool):
    """Ativa ou desativa um canal"""
    try:
        await db.channel_config.update_one(
            {"canal": canal},
            {"$set": {"enabled": enabled, "last_update": datetime.now()}},
            upsert=True
        )
        logger.info(f"✅ Canal {canal} {'ATIVADO' if enabled else 'DESATIVADO'}")
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar canal {canal}: {e}")
        return False

# ============================================================
# STATUS DO BOT
# ============================================================
bot_status_cache = {"enabled": True, "last_update": datetime.now()}

async def get_bot_status():
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
    try:
        await db.bot_config.update_one(
            {"_id": "global_status"},
            {"$set": {"enabled": enabled, "last_update": datetime.now()}},
            upsert=True
        )
        bot_status_cache["enabled"] = enabled
        bot_status_cache["last_update"] = datetime.now()
        logger.info(f"✅ Bot {'ATIVADO' if enabled else 'DESATIVADO'}")
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar status: {e}")
        return False

# ============================================================
# TREINAMENTO DA MIA
# ============================================================
async def get_bot_training() -> str:
    """Busca treinamento personalizado da Mia no banco"""
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        if not bot:
            return """Você é a Mia, assistente virtual da Legacy Translations.
            
Seja profissional, educada e prestativa. Ajude os clientes com informações sobre tradução de documentos."""
        
        personality = bot.get("personality", {})
        knowledge_base = bot.get("knowledge_base", [])
        faqs = bot.get("faqs", [])
        
        prompt_parts = []
        
        if personality.get("goals"):
            goals_text = "\n".join(personality["goals"]) if isinstance(personality["goals"], list) else personality["goals"]
            prompt_parts.append(f"**OBJETIVOS:**\n{goals_text}")
        
        if personality.get("tone"):
            prompt_parts.append(f"**TOM:**\n{personality['tone']}")
        
        if personality.get("restrictions"):
            restrictions_text = "\n".join(personality["restrictions"]) if isinstance(personality["restrictions"], list) else personality["restrictions"]
            prompt_parts.append(f"**RESTRIÇÕES:**\n{restrictions_text}")
        
        if knowledge_base:
            kb_text = "\n\n".join([f"**{item.get('title')}:**\n{item.get('content')}" for item in knowledge_base])
            prompt_parts.append(f"**CONHECIMENTO:**\n{kb_text}")
        
        if faqs:
            faq_text = "\n\n".join([f"P: {item.get('question')}\nR: {item.get('answer')}" for item in faqs])
            prompt_parts.append(f"**FAQs:**\n{faq_text}")
        
        return "\n\n".join(prompt_parts) if prompt_parts else "Você é a Mia, assistente da Legacy Translations."
    except Exception as e:
        logger.error(f"❌ Erro ao buscar treinamento: {e}")
        return "Você é a Mia, assistente da Legacy Translations."

# ============================================================
# TRANSFERÊNCIA PARA ATENDENTE HUMANO
# ============================================================
async def notificar_atendente(phone: str, canal: str, motivo: str = "Cliente solicitou"):
    """Notifica o atendente sobre transferência de atendimento"""
    try:
        mensagens = await db.conversas.find({"phone": phone, "canal": canal}).sort("timestamp", -1).limit(10).to_list(length=10)
        mensagens.reverse()
        
        resumo_linhas = []
        for msg in mensagens:
            role = "👤 Cliente" if msg.get("role") == "user" else "🤖 IA"
            texto = msg.get("message", "")[:100]
            resumo_linhas.append(f"{role}: {texto}")
        resumo = "\n".join(resumo_linhas) if resumo_linhas else "Sem histórico"
        
        canal_emoji = {"whatsapp": "📱", "instagram": "📸", "web": "💻"}.get(canal, "📱")
        
        mensagem_atendente = f"""🔔 *TRANSFERÊNCIA DE ATENDIMENTO*

{canal_emoji} *Canal:* {canal.upper()}
📱 *Cliente:* {phone}
⚠️ *Motivo:* {motivo}

📝 *Resumo:*
{resumo}

---
✅ Para assumir o atendimento, responda ao cliente diretamente.
🔄 Para retornar à IA, digite: +
"""
        
        # Enviar notificação via WhatsApp
        await send_whatsapp_message(ATENDENTE_PHONE, mensagem_atendente)
        logger.info(f"✅ Notificação enviada ao atendente: {phone} ({canal})")
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao notificar atendente: {e}")
        return False

async def detectar_solicitacao_humano(message: str) -> bool:
    """Detecta se cliente está pedindo atendente humano"""
    palavras_chave = [
        "atendente", "humano", "pessoa", "falar com alguem",
        "falar com alguém", "operador", "atendimento humano",
        "quero falar", "preciso falar", "transferir", "atender"
    ]
    
    message_lower = message.lower()
    return any(palavra in message_lower for palavra in palavras_chave)

async def transferir_para_humano(phone: str, canal: str, motivo: str):
    """Transfere conversa para atendente humano"""
    try:
        await db.conversas.update_many(
            {"phone": phone, "canal": canal}, 
            {"$set": {"mode": "human", "transferred_at": datetime.now(), "transfer_reason": motivo}}
        )
        await notificar_atendente(phone, canal, motivo)
        
        # Transferência invisível - cliente não sabe
        logger.info(f"✅ Conversa transferida para humano: {phone} ({canal}) - Motivo: {motivo}")
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao transferir: {e}")
        return False

# ============================================================
# ENVIAR MENSAGENS (MULTI-CANAL)
# ============================================================
async def send_whatsapp_message(phone: str, message: str):
    """Envia mensagem via Z-API (WhatsApp)"""
    try:
        url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
        
        headers = {
            "Content-Type": "application/json",
            "Client-Token": ZAPI_CLIENT_TOKEN or ""
        }
        
        payload = {
            "phone": phone,
            "message": message
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                logger.info(f"✅ WhatsApp: Mensagem enviada para {phone}")
                return True
            else:
                logger.error(f"❌ WhatsApp: Erro {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"❌ WhatsApp: Erro ao enviar mensagem: {e}")
        return False

async def send_instagram_message(recipient_id: str, message: str):
    """Envia mensagem via Instagram (preparado para futuro)"""
    try:
        if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_PAGE_ID:
            logger.warning("⚠️ Instagram não configurado")
            return False
        
        url = f"https://graph.facebook.com/v18.0/{INSTAGRAM_PAGE_ID}/messages"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message},
            "access_token": INSTAGRAM_ACCESS_TOKEN
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                logger.info(f"✅ Instagram: Mensagem enviada para {recipient_id}")
                return True
            else:
                logger.error(f"❌ Instagram: Erro {response.status_code}")
                return False
    except Exception as e:
        logger.error(f"❌ Instagram: Erro ao enviar mensagem: {e}")
        return False

async def send_message(phone: str, message: str, canal: str = "whatsapp"):
    """Envia mensagem pelo canal apropriado"""
    if canal == "whatsapp":
        return await send_whatsapp_message(phone, message)
    elif canal == "instagram":
        return await send_instagram_message(phone, message)
    elif canal == "web":
        # Web chat usa WebSocket (implementado separadamente)
        return True
    else:
        logger.error(f"❌ Canal desconhecido: {canal}")
        return False

# ============================================================
# PROCESSAR IMAGEM (GPT-4 VISION)
# ============================================================
async def process_image(image_url: str, user_message: str = "") -> str:
    """Processa imagem usando GPT-4 Vision"""
    try:
        training = await get_bot_training()
        
        messages = [
            {
                "role": "system",
                "content": training
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_message or "Analise esta imagem e forneça informações sobre tradução se for um documento."
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url}
                    }
                ]
            }
        ]
        
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1000
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"❌ Erro ao processar imagem: {e}")
        return "Desculpe, não consegui processar esta imagem no momento."

# ============================================================
# PROCESSAR ÁUDIO (WHISPER)
# ============================================================
async def process_audio(audio_url: str) -> str:
    """Transcreve áudio usando Whisper"""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            audio_response = await client.get(audio_url)
            audio_bytes = audio_response.content
        
        audio_file = BytesIO(audio_bytes)
        audio_file.name = "audio.ogg"
        
        transcript = await openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
        
        return transcript.text
    except Exception as e:
        logger.error(f"❌ Erro ao transcrever áudio: {e}")
        return ""

# ============================================================
# PROCESSAR PDF
# ============================================================
async def process_pdf(pdf_url: str) -> str:
    """Extrai texto de PDF"""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            pdf_response = await client.get(pdf_url)
            pdf_bytes = pdf_response.content
        
        pdf_file = BytesIO(pdf_bytes)
        pdf_reader = PdfReader(pdf_file)
        
        text_content = []
        for page in pdf_reader.pages:
            text_content.append(page.extract_text())
        
        full_text = "\n\n".join(text_content)
        
        if len(full_text.strip()) > 100:
            return full_text[:4000]  # Limitar tamanho
        else:
            # Se não conseguiu extrair texto, tenta converter para imagem
            images = convert_from_bytes(pdf_bytes, first_page=1, last_page=1)
            if images:
                # Converter para base64 e processar com Vision
                img_byte_arr = BytesIO()
                images[0].save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)
                img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode()
                
                return await process_image(f"data:image/png;base64,{img_base64}", "Extraia o texto deste documento PDF")
        
        return full_text
    except Exception as e:
        logger.error(f"❌ Erro ao processar PDF: {e}")
        return ""

# ============================================================
# GERAR RESPOSTA IA
# ============================================================
async def generate_ai_response(phone: str, user_message: str, canal: str = "whatsapp") -> str:
    """Gera resposta usando OpenAI"""
    try:
        training = await get_bot_training()
        logger.info(f"📚 Treinamento: {training[:200]}...")
        
        # Buscar histórico
        historico = await db.conversas.find({"phone": phone, "canal": canal}).sort("timestamp", -1).limit(10).to_list(length=10)
        historico.reverse()
        
        messages = [{"role": "system", "content": training}]
        
        for msg in historico:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("message", "")
            })
        
        messages.append({"role": "user", "content": user_message})
        
        # Buscar delay configurado
        bot = await db.bots.find_one({"name": "Mia"})
        response_delay = 3
        if bot and bot.get("personality", {}).get("response_delay"):
            response_delay = int(bot["personality"]["response_delay"])
        
        logger.info(f"⏱️ Aguardando {response_delay} segundos...")
        await asyncio.sleep(response_delay)
        
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        
        reply = response.choices[0].message.content
        logger.info(f"🤖 Resposta: {reply[:100]}...")
        return reply
    except Exception as e:
        logger.error(f"❌ Erro ao gerar resposta: {e}")
        return "Desculpe, estou com dificuldades técnicas no momento. Tente novamente em instantes."

# ============================================================
# SALVAR MENSAGEM
# ============================================================
async def save_message(phone: str, message: str, role: str, canal: str = "whatsapp", message_type: str = "text"):
    """Salva mensagem no banco de dados"""
    try:
        await db.conversas.insert_one({
            "phone": phone,
            "message": message,
            "role": role,
            "message_type": message_type,
            "canal": canal,
            "timestamp": datetime.now(),
            "mode": "ai"
        })
    except Exception as e:
        logger.error(f"❌ Erro ao salvar mensagem: {e}")

# ============================================================
# WEBHOOK WHATSAPP
# ============================================================
@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    """Recebe mensagens do WhatsApp via Z-API"""
    try:
        data = await request.json()
        logger.info(f"📩 WhatsApp webhook: {json.dumps(data, indent=2)}")
        
        # Verificar se canal WhatsApp está ativo
        if not await get_channel_status("whatsapp"):
            logger.info("⏸️ WhatsApp desativado - mensagem ignorada")
            return JSONResponse({"status": "channel_disabled"})
        
        # Verificar se bot está ativo
        status = await get_bot_status()
        if not status["enabled"]:
            logger.info("⏸️ Bot desativado - mensagem ignorada")
            return JSONResponse({"status": "bot_disabled"})
        
        phone = data.get("phone")
        message_text = data.get("text", {}).get("message", "")
        message_type = data.get("type", "text")
        
        if not phone:
            return JSONResponse({"status": "no_phone"})
        
        # Verificar se é comando do atendente
        if phone == ATENDENTE_PHONE:
            if message_text == "+":
                await set_bot_status(True)
                await send_whatsapp_message(phone, "✅ Bot reativado! IA assumiu novamente.")
                return JSONResponse({"status": "bot_enabled"})
        
        # Verificar modo de atendimento
        ultima_msg = await db.conversas.find_one({"phone": phone, "canal": "whatsapp"}, sort=[("timestamp", -1)])
        modo_atual = ultima_msg.get("mode", "ai") if ultima_msg else "ai"
        
        if modo_atual == "human":
            logger.info(f"👤 Atendimento humano ativo para {phone}")
            await save_message(phone, message_text, "user", "whatsapp", message_type)
            return JSONResponse({"status": "human_mode"})
        
        # Processar mensagem
        response_text = ""
        
        if message_type == "image":
            image_url = data.get("image", {}).get("imageUrl", "")
            if image_url:
                await save_message(phone, "[Imagem recebida]", "user", "whatsapp", "image")
                response_text = await process_image(image_url, message_text)
        
        elif message_type == "audio" or message_type == "ptt":
            audio_url = data.get("audio", {}).get("audioUrl", "")
            if audio_url:
                transcription = await process_audio(audio_url)
                await save_message(phone, f"[Áudio]: {transcription}", "user", "whatsapp", "audio")
                response_text = await generate_ai_response(phone, transcription, "whatsapp")
        
        elif message_type == "document":
            doc_url = data.get("document", {}).get("documentUrl", "")
            doc_name = data.get("document", {}).get("fileName", "")
            if doc_url and doc_name.lower().endswith('.pdf'):
                pdf_text = await process_pdf(doc_url)
                await save_message(phone, f"[PDF]: {pdf_text[:200]}...", "user", "whatsapp", "document")
                response_text = await generate_ai_response(phone, f"Cliente enviou PDF com conteúdo: {pdf_text}", "whatsapp")
        
        else:  # text
            await save_message(phone, message_text, "user", "whatsapp", "text")
            
            # Detectar pedido de atendente
            if await detectar_solicitacao_humano(message_text):
                await transferir_para_humano(phone, "whatsapp", "Cliente solicitou atendente")
                return JSONResponse({"status": "transferred_to_human"})
            
            response_text = await generate_ai_response(phone, message_text, "whatsapp")
        
        # Enviar resposta
        if response_text:
            await send_whatsapp_message(phone, response_text)
            await save_message(phone, response_text, "assistant", "whatsapp", "text")
        
        return JSONResponse({"status": "success"})
    
    except Exception as e:
        logger.error(f"❌ Erro no webhook WhatsApp: {e}\n{traceback.format_exc()}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

# ============================================================
# WEBHOOK INSTAGRAM (PREPARADO PARA FUTURO)
# ============================================================
@app.post("/webhook/instagram")
async def webhook_instagram(request: Request):
    """Recebe mensagens do Instagram via Meta API"""
    try:
        data = await request.json()
        logger.info(f"📸 Instagram webhook: {json.dumps(data, indent=2)}")
        
        # Verificar se canal Instagram está ativo
        if not await get_channel_status("instagram"):
            logger.info("⏸️ Instagram desativado - mensagem ignorada")
            return JSONResponse({"status": "channel_disabled"})
        
        # TODO: Implementar processamento de mensagens do Instagram
        # Similar ao WhatsApp, mas usando Meta Graph API
        
        return JSONResponse({"status": "instagram_not_implemented"})
    
    except Exception as e:
        logger.error(f"❌ Erro no webhook Instagram: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

# ============================================================
# WEBHOOK VERIFICATION (Meta)
# ============================================================
@app.get("/webhook/instagram")
async def webhook_instagram_verify(request: Request):
    """Verificação do webhook do Instagram/Facebook"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    if mode == "subscribe" and token == os.getenv("WEBHOOK_VERIFY_TOKEN", "mia-verify-token"):
        logger.info("✅ Instagram webhook verificado")
        return int(challenge)
    
    return JSONResponse({"status": "error"}, status_code=403)

# ============================================================
# WEB CHAT (PREPARADO PARA FUTURO)
# ============================================================
@app.websocket("/ws/chat/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str):
    """WebSocket para chat web (preparado para futuro)"""
    await websocket.accept()
    logger.info(f"💻 Web chat conectado: {client_id}")
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            user_message = message_data.get("message", "")
            
            if not user_message:
                continue
            
            # Salvar mensagem do usuário
            await save_message(client_id, user_message, "user", "web", "text")
            
            # Gerar resposta
            response_text = await generate_ai_response(client_id, user_message, "web")
            
            # Salvar resposta
            await save_message(client_id, response_text, "assistant", "web", "text")
            
            # Enviar resposta via WebSocket
            await websocket.send_json({
                "type": "message",
                "content": response_text,
                "timestamp": datetime.now().isoformat()
            })
    
    except WebSocketDisconnect:
        logger.info(f"💻 Web chat desconectado: {client_id}")
    except Exception as e:
        logger.error(f"❌ Erro no WebSocket: {e}")

# ============================================================
# ROTAS ADMINISTRATIVAS
# ============================================================
from admin_routes import router as admin_router
from admin_training_routes import router as training_router
from admin_controle_routes import router as controle_router
from admin_learning_routes_SIMPLES import router as learning_router
from admin_atendimento_routes import router as atendimento_router
from admin_conversas_leads_routes import router_conversas, router_leads

app.include_router(admin_router)
app.include_router(training_router)
app.include_router(controle_router)
app.include_router(learning_router)
app.include_router(atendimento_router)
app.include_router(router_conversas)
app.include_router(router_leads)

# ============================================================
# ROTAS BÁSICAS
# ============================================================
@app.get("/")
def root():
    return RedirectResponse(url="/login")

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    if username == "admin" and password == "admin123":
        request.session["user"] = username
        return RedirectResponse(url="/admin/", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Credenciais inválidas"
    })

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "channels": {
            "whatsapp": await get_channel_status("whatsapp"),
            "instagram": await get_channel_status("instagram"),
            "web": await get_channel_status("web")
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
