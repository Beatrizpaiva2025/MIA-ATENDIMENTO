import os
import logging
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from openai import OpenAI
from datetime import datetime
from routes.admin_routes import router as admin_router
import base64

# ============================================================
# CONFIGURAÇÃO DE LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger("main")

# ============================================================
# INICIALIZAÇÃO DO FASTAPI
# ============================================================
app = FastAPI(title="WhatsApp AI Platform")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# VARIÁVEIS DE AMBIENTE
# ============================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")
ZAPI_INSTANCE = os.getenv("ZAPI_INSTANCE")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")

# ============================================================
# CLIENTES GLOBAIS
# ============================================================
openai_client = OpenAI(api_key=OPENAI_API_KEY)
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["whatsapp_ai"]
conversations_collection = db["conversations"]
messages_collection = db["messages"]

# ============================================================
# MONTAR PAINEL ADMIN
# ============================================================
app.mount("/admin/static", StaticFiles(directory="static"), name="static")
app.include_router(admin_router, prefix="/admin")

# ============================================================
# STARTUP
# ============================================================
@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("🚀 WhatsApp AI Platform - Legacy Translations")
    logger.info("📦 VERSÃO MULTIMÍDIA + ADMIN 2.0")
    logger.info("=" * 60)
    logger.info(f"✅ OpenAI: {'Configurado' if OPENAI_API_KEY else '❌ NÃO CONFIGURADO'}")
    logger.info(f"✅ MongoDB: {'Configurado' if MONGO_URI else '❌ NÃO CONFIGURADO'}")
    logger.info(f"✅ Z-API Instance: {'Configurado' if ZAPI_INSTANCE else '❌ NÃO CONFIGURADO'}")
    logger.info(f"✅ Z-API Token: {'Configurado' if ZAPI_TOKEN else '❌ NÃO CONFIGURADO'}")
    logger.info("=" * 60)
    logger.info("🎯 FUNCIONALIDADES ATIVAS:")
    logger.info("   ✅ Mensagens de texto")
    logger.info("   ✅ Imagens (GPT-4 Vision)")
    logger.info("   ✅ Áudios (Whisper)")
    logger.info("   ✅ Painel Admin Completo")
    logger.info("   ✅ Controle IA vs Humano")
    logger.info("=" * 60)

# ============================================================
# FUNÇÃO: BUSCAR CONVERSA
# ============================================================
async def get_or_create_conversation(phone: str):
    conversation = await conversations_collection.find_one({"phone": phone})
    if not conversation:
        conversation = {
            "phone": phone,
            "mode": "ai",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await conversations_collection.insert_one(conversation)
        conversation["_id"] = result.inserted_id
    return conversation

# ============================================================
# FUNÇÃO: SALVAR MENSAGEM
# ============================================================
async def save_message(phone: str, role: str, content: str, msg_type: str = "text"):
    message = {
        "phone": phone,
        "role": role,
        "content": content,
        "type": msg_type,
        "timestamp": datetime.utcnow()
    }
    await messages_collection.insert_one(message)

# ============================================================
# FUNÇÃO: BUSCAR HISTÓRICO
# ============================================================
async def get_conversation_history(phone: str, limit: int = 10):
    messages = await messages_collection.find(
        {"phone": phone}
    ).sort("timestamp", -1).limit(limit).to_list(length=limit)
    
    messages.reverse()
    
    history = []
    for msg in messages:
        history.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    
    return history

# ============================================================
# FUNÇÃO: PROCESSAR COM IA
# ============================================================
async def process_with_ai(phone: str, user_message: str, message_type: str = "text", media_url: str = None):
    history = await get_conversation_history(phone)
    
    messages = [
        {
            "role": "system",
            "content": """Você é a Mia, assistente virtual da Legacy Translations, uma empresa de tradução juramentada.

INFORMAÇÕES DA EMPRESA:
- Especializada em traduções juramentadas para imigração (EUA, Canadá, Portugal, etc)
- Documentos: certidões, diplomas, históricos escolares, contratos, procurações
- Atendimento humanizado e consultivo
- Preços competitivos e prazos rápidos

SEU PAPEL:
- Seja cordial, empática e prestativa
- Entenda a necessidade do cliente antes de oferecer soluções
- Faça perguntas para qualificar o atendimento
- Explique processos de forma clara
- Quando necessário, informe que um especialista entrará em contato

DIRETRIZES:
- Respostas concisas (máx 3-4 linhas)
- Tom profissional mas acolhedor
- Evite jargões técnicos excessivos
- Sempre pergunte se pode ajudar em algo mais"""
        }
    ]
    
    messages.extend(history)
    
    if message_type == "image" and media_url:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_message},
                {"type": "image_url", "image_url": {"url": media_url}}
            ]
        })
    else:
        messages.append({"role": "user", "content": user_message})
    
    model = "gpt-4o-mini" if message_type == "image" else "gpt-4o-mini"
    
    response = openai_client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=500,
        temperature=0.7
    )
    
    return response.choices[0].message.content

# ============================================================
# FUNÇÃO: ENVIAR MENSAGEM WHATSAPP
# ============================================================
async def send_whatsapp_message(phone: str, message: str):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE}/token/{ZAPI_TOKEN}/send-text"
    
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    
    payload = {
        "phone": phone,
        "message": message
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"❌ Erro ao enviar: {response.status_code} - {response.text}")
            raise Exception(f"Erro Z-API: {response.text}")
        
        return response.json()

# ============================================================
# FUNÇÃO: BAIXAR MÍDIA DA Z-API
# ============================================================
async def download_media_from_zapi(message_id: str, phone: str):
    """Baixa mídia (imagem/áudio) da Z-API e retorna base64"""
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE}/token/{ZAPI_TOKEN}/download-media/{message_id}"
    
    headers = {
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=headers)
        
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
        else:
            logger.error(f"❌ Erro ao baixar mídia: {response.status_code}")
            return None

# ============================================================
# WEBHOOK PRINCIPAL
# ============================================================
@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    try:
        data = await request.json()
        logger.info(f"📨 Webhook recebido: {data}")
        
        # Ignorar mensagens enviadas por nós
        if data.get("fromMe"):
            return JSONResponse({"status": "ignored", "reason": "fromMe"})
        
        phone = data.get("phone")
        if not phone:
            return JSONResponse({"status": "error", "reason": "no phone"})
        
        # Detectar tipo de mensagem
        message_type = "text"
        user_message = ""
        media_url = None
        
        # TEXTO
        if "text" in data and data["text"]:
            message_type = "text"
            user_message = data["text"].get("message", "")
            logger.info(f"💬 Texto de {phone}: {user_message}")
        
        # IMAGEM
        elif "image" in data and data["image"]:
            message_type = "image"
            user_message = data["image"].get("caption", "Imagem recebida")
            image_url = data["image"].get("imageUrl")
            
            if image_url:
                media_url = image_url
                logger.info(f"🖼️ Imagem de {phone}: {image_url}")
            else:
                message_id = data.get("messageId")
                if message_id:
                    base64_image = await download_media_from_zapi(message_id, phone)
                    if base64_image:
                        media_url = f"data:image/jpeg;base64,{base64_image}"
                        logger.info(f"🖼️ Imagem baixada via Z-API de {phone}")
        
        # ÁUDIO
        elif "audio" in data and data["audio"]:
            message_type = "audio"
            audio_url = data["audio"].get("audioUrl")
            message_id = data.get("messageId")
            
            if audio_url:
                logger.info(f"🎤 Áudio de {phone}: {audio_url}")
                
                async with httpx.AsyncClient(timeout=60.0) as client:
                    audio_response = await client.get(audio_url)
                    audio_data = audio_response.content
                
                transcription = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=("audio.ogg", audio_data, "audio/ogg")
                )
                
                user_message = transcription.text
                logger.info(f"📝 Transcrição: {user_message}")
            
            elif message_id:
                base64_audio = await download_media_from_zapi(message_id, phone)
                if base64_audio:
                    audio_data = base64.b64decode(base64_audio)
                    
                    transcription = openai_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=("audio.ogg", audio_data, "audio/ogg")
                    )
                    
                    user_message = transcription.text
                    logger.info(f"📝 Transcrição (Z-API): {user_message}")
        
        else:
            logger.info(f"🔍 Tipo detectado: {message_type}")
            return JSONResponse({"status": "ignored", "reason": "unsupported type"})
        
        if not user_message:
            return JSONResponse({"status": "ignored", "reason": "empty message"})
        
        # Buscar conversa
        conversation = await get_or_create_conversation(phone)
        mode = conversation.get("mode", "ai")
        
        # Salvar mensagem do usuário
        await save_message(phone, "user", user_message, message_type)
        
        # MODO HUMANO
        if mode == "human":
            logger.info(f"👤 Conversa em modo HUMANO - {phone}")
            return JSONResponse({"status": "human_mode", "phone": phone})
        
        # MODO IA
        logger.info(f"🤖 Processando com IA - {phone}")
        ai_response = await process_with_ai(phone, user_message, message_type, media_url)
        
        # Salvar resposta da IA
        await save_message(phone, "assistant", ai_response, "text")
        
        # Enviar resposta
        await send_whatsapp_message(phone, ai_response)
        
        logger.info(f"✅ Resposta enviada para {phone}")
        
        return JSONResponse({
            "status": "success",
            "phone": phone,
            "response": ai_response
        })
    
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {str(e)}", exc_info=True)
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )

# ============================================================
# HEALTH CHECK
# ============================================================
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "openai": bool(OPENAI_API_KEY),
            "mongodb": bool(MONGO_URI),
            "zapi": bool(ZAPI_INSTANCE and ZAPI_TOKEN)
        }
    }
