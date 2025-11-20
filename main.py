# ============================================================
# VERSÃO COMPLETA MULTIMÍDIA + PAINEL ADMIN - main.py
# ============================================================

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import os
import httpx
from openai import OpenAI
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import logging
from typing import Optional, Dict, List
import traceback
import json
import base64
from io import BytesIO

# Importar rotas do admin
from admin_routes import router as admin_router
from admin_controle_routes import router as controle_router

# ============================================================
# CONFIGURAÇÃO DE LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# INICIALIZAÇÃO
# ============================================================
app = FastAPI(title="WhatsApp AI Platform - Legacy Translations")

# Templates
templates = Jinja2Templates(directory="templates")

# Clientes
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
mongo_client = AsyncIOMotorClient(os.getenv("MONGODB_URI"))
db = mongo_client["mia_bot"]

# ============================================================
# INCLUIR ROTAS DO PAINEL ADMIN
# ============================================================
app.include_router(admin_router)
app.include_router(controle_router)

# ============================================================
# CONFIGURAÇÕES Z-API
# ============================================================
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_URL = os.getenv("ZAPI_URL", "https://api.z-api.io")

# ============================================================
# CONTEXTO DA MIA (PERSONALIDADE)
# ============================================================
MIA_SYSTEM_PROMPT = """
Você é a Mia, assistente virtual da Legacy Translations, empresa especializada em traduções juramentadas.

**PERSONALIDADE:**
- Profissional, cordial e prestativa
- Use emojis moderadamente (📄, ✅, 💼, 🌍)
- Tom formal mas acessível

**CAPACIDADES:**
- Análise de documentos via imagem (GPT-4 Vision)
- Identificação de tipo de documento
- Cálculo de preços de tradução
- Orientação sobre processos

**DOCUMENTOS ACEITOS:**
Certidão de Nascimento, Casamento, Óbito, Diploma, Histórico Escolar, CNH, RG, Passaporte, Contrato, Procuração, etc.

**TABELA DE PREÇOS (2024):**
- Certidões simples: R$ 80-100
- Diplomas: R$ 120-150
- Contratos (por página): R$ 60-80
- Documentos complexos: consultar

**QUANDO TRANSFERIR PARA HUMANO:**
- Negociações complexas
- Documentos muito técnicos
- Cliente solicita falar com pessoa
- Situações sensíveis

**INSTRUÇÕES:**
1. Sempre pergunte o nome do cliente
2. Se enviar imagem, analise com GPT-4 Vision
3. Identifique o documento e calcule preço
4. Explique processo e prazo
5. Ofereça finalizar orçamento
"""

# ============================================================
# FUNÇÃO: BAIXAR MÍDIA DA Z-API
# ============================================================
async def download_media_from_zapi(media_url: str) -> Optional[bytes]:
    """Baixa arquivo de mídia (imagem/áudio) da Z-API"""
    try:
        logger.info(f"📥 Baixando mídia: {media_url[:50]}...")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(media_url)
            
            if response.status_code == 200:
                logger.info(f"✅ Mídia baixada: {len(response.content)} bytes")
                return response.content
            else:
                logger.error(f"❌ Erro ao baixar mídia: {response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"❌ Erro ao baixar mídia: {str(e)}")
        return None

# ============================================================
# FUNÇÃO: PROCESSAR IMAGEM COM GPT-4 VISION
# ============================================================
async def process_image_with_vision(image_bytes: bytes, phone: str) -> str:
    """Analisa imagem usando GPT-4 Vision"""
    try:
        logger.info(f"🔍 Analisando imagem com GPT-4 Vision para {phone}")
        
        # Converter para base64
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        # Chamar GPT-4 Vision
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": """Você é um especialista em análise de documentos para tradução juramentada.
                    
                    Analise a imagem e forneça:
                    1. Tipo de documento identificado
                    2. Idioma do documento
                    3. Qualidade da imagem (boa/média/ruim)
                    4. Se é adequado para tradução juramentada
                    5. Estimativa de preço baseado na tabela da Legacy Translations
                    
                    Seja objetivo e profissional."""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analise este documento e me diga que tipo é, se está legível e qual seria o preço aproximado da tradução juramentada."
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
            max_tokens=500
        )
        
        analysis = response.choices[0].message.content
        logger.info(f"✅ Análise concluída: {analysis[:100]}...")
        
        # Salvar no banco
        await db.documentos.insert_one({
            "phone": phone,
            "timestamp": datetime.now(),
            "analysis": analysis,
            "status": "ANALISADO"
        })
        
        return analysis
        
    except Exception as e:
        logger.error(f"❌ Erro ao processar imagem: {str(e)}")
        logger.error(traceback.format_exc())
        return "Desculpe, tive um problema ao analisar a imagem. Pode tentar enviar novamente?"

# ============================================================
# FUNÇÃO: PROCESSAR ÁUDIO COM WHISPER
# ============================================================
async def process_audio_with_whisper(audio_bytes: bytes, phone: str) -> str:
    """Transcreve áudio usando Whisper"""
    try:
        logger.info(f"🎤 Transcrevendo áudio com Whisper para {phone}")
        
        # Criar arquivo temporário em memória
        audio_file = BytesIO(audio_bytes)
        audio_file.name = "audio.ogg"
        
        # Transcrever com Whisper
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="pt"
        )
        
        transcription = transcript.text
        logger.info(f"✅ Transcrição: {transcription[:100]}...")
        
        return transcription
        
    except Exception as e:
        logger.error(f"❌ Erro ao transcrever áudio: {str(e)}")
        logger.error(traceback.format_exc())
        return None

# ============================================================
# ✅ FUNÇÃO: ENVIAR MENSAGEM WHATSAPP (CORRIGIDA)
# ============================================================
async def send_whatsapp_message(phone: str, message: str) -> bool:
    """Enviar mensagem via Z-API - SEM CLIENT-TOKEN"""
    try:
        url = f"{ZAPI_URL}/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
        
        payload = {
            "phone": phone,
            "message": message
        }
        
        # ✅ SEM HEADERS - A autenticação está na URL
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                logger.info(f"✅ Mensagem enviada para {phone}")
                return True
            else:
                logger.error(f"❌ Erro ao enviar: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Erro ao enviar mensagem: {str(e)}")
        return False

# ============================================================
# FUNÇÃO: BUSCAR CONTEXTO DA CONVERSA
# ============================================================
async def get_conversation_context(phone: str, limit: int = 10) -> List[Dict]:
    """Busca últimas mensagens da conversa"""
    try:
        messages = await db.conversas.find(
            {"phone": phone}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        
        # Inverter para ordem cronológica
        messages.reverse()
        
        return [
            {"role": msg["role"], "content": msg["message"]}
            for msg in messages
        ]
    except Exception as e:
        logger.error(f"❌ Erro ao buscar contexto: {str(e)}")
        return []

# ============================================================
# FUNÇÃO: PROCESSAR MENSAGEM COM IA
# ============================================================
async def process_message_with_ai(phone: str, message: str) -> str:
    """Processar mensagem com GPT-4"""
    try:
        # Buscar contexto
        context = await get_conversation_context(phone)
        
        # Montar mensagens
        messages = [
            {"role": "system", "content": MIA_SYSTEM_PROMPT}
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
        logger.error(f"❌ Erro ao processar com IA: {str(e)}")
        logger.error(traceback.format_exc())
        return "Desculpe, tive um problema. Pode repetir?"

# ============================================================
# WEBHOOK: WHATSAPP (Z-API)
# ============================================================
@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    """Webhook principal para receber mensagens do WhatsApp via Z-API"""
    try:
        data = await request.json()
        logger.info(f"📨 Webhook recebido: {json.dumps(data, indent=2)}")
        
        # Controle de ativação
        ia_enabled = os.getenv("IA_ENABLED", "true").lower() == "true"
        em_manutencao = os.getenv("MANUTENCAO", "false").lower() == "true"
        
        phone = data.get("phone", "")
        message_type = data.get("messageType", "text")
        
        if not phone:
            return JSONResponse({"status": "ignored", "reason": "no phone"})
        
        if em_manutencao:
            logger.info(f"🔧 Modo manutenção ativo - mensagem de {phone}")
            if message_type == "text":
                await send_whatsapp_message(phone, "🔧 Sistema em manutenção. Voltaremos em breve!")
            return JSONResponse({"status": "maintenance"})
        
        if not ia_enabled:
            logger.info(f"⏸️ IA desabilitada - mensagem de {phone} ignorada")
            return JSONResponse({"status": "ia_disabled"})
        
        # Processar TEXTO
        if message_type == "text":
            text = data.get("text", {}).get("message", "")
            
            if not text:
                return JSONResponse({"status": "ignored", "reason": "empty text"})
            
            logger.info(f"💬 Texto de {phone}: {text}")
            
            reply = await process_message_with_ai(phone, text)
            await send_whatsapp_message(phone, reply)
            
            return JSONResponse({"status": "processed", "type": "text"})
        
        # Processar IMAGEM
        elif message_type == "image":
            image_url = data.get("image", {}).get("imageUrl", "")
            
            if not image_url:
                return JSONResponse({"status": "ignored", "reason": "no image url"})
            
            logger.info(f"🖼️ Imagem de {phone}")
            
            image_bytes = await download_media_from_zapi(image_url)
            
            if not image_bytes:
                await send_whatsapp_message(phone, "Desculpe, não consegui baixar a imagem.")
                return JSONResponse({"status": "error", "reason": "download failed"})
            
            analysis = await process_image_with_vision(image_bytes, phone)
            reply = f"📄 *Análise do Documento*\n\n{analysis}\n\n_Posso ajudar com mais alguma coisa?_"
            
            await send_whatsapp_message(phone, reply)
            
            return JSONResponse({"status": "processed", "type": "image"})
        
        # Processar ÁUDIO
        elif message_type == "audio":
            audio_url = data.get("audio", {}).get("audioUrl", "")
            
            if not audio_url:
                return JSONResponse({"status": "ignored", "reason": "no audio url"})
            
            logger.info(f"🎤 Áudio de {phone}")
            
            audio_bytes = await download_media_from_zapi(audio_url)
            
            if not audio_bytes:
                await send_whatsapp_message(phone, "Desculpe, não consegui baixar o áudio.")
                return JSONResponse({"status": "error", "reason": "download failed"})
            
            transcription = await process_audio_with_whisper(audio_bytes, phone)
            
            if not transcription:
                await send_whatsapp_message(phone, "Desculpe, não consegui entender o áudio.")
                return JSONResponse({"status": "error", "reason": "transcription failed"})
            
            logger.info(f"📝 Transcrição: {transcription}")
            
            reply = await process_message_with_ai(phone, transcription)
            await send_whatsapp_message(phone, reply)
            
            return JSONResponse({"status": "processed", "type": "audio"})
        
        else:
            logger.info(f"⚠️ Tipo não suportado: {message_type}")
            return JSONResponse({"status": "ignored", "reason": f"unsupported type: {message_type}"})
            
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

# ============================================================
# ROTA: HEALTH CHECK
# ============================================================
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        await db.command("ping")
        
        return {
            "status": "healthy",
            "openai": "✅ Configurado" if os.getenv("OPENAI_API_KEY") else "❌ Não configurado",
            "mongodb": "✅ Configurado" if os.getenv("MONGODB_URI") else "❌ Não configurado",
            "zapi_instance": "✅ Configurado" if ZAPI_INSTANCE_ID else "❌ Não configurado",
            "zapi_token": "✅ Configurado" if ZAPI_TOKEN else "❌ Não configurado"
        }
    except Exception as e:
        return JSONResponse(
            {"status": "unhealthy", "error": str(e)},
            status_code=503
        )

# ============================================================
# ROTA RAIZ
# ============================================================
@app.get("/")
async def root():
    """Redirecionar para painel admin"""
    return RedirectResponse(url="/admin")

# ============================================================
# STARTUP
# ============================================================
@app.on_event("startup")
async def startup_event():
    """Evento de inicialização"""
    logger.info("=" * 60)
    logger.info("🚀 WhatsApp AI Platform - Legacy Translations")
    logger.info("📦 VERSÃO CORRIGIDA - SEM CLIENT-TOKEN")
    logger.info("=" * 60)
    logger.info(f"✅ OpenAI: {'Configurado' if os.getenv('OPENAI_API_KEY') else '❌ FALTANDO'}")
    logger.info(f"✅ MongoDB: {'Configurado' if os.getenv('MONGODB_URI') else '❌ FALTANDO'}")
    logger.info(f"✅ Z-API Instance: {'Configurado' if ZAPI_INSTANCE_ID else '❌ FALTANDO'}")
    logger.info(f"✅ Z-API Token: {'Configurado' if ZAPI_TOKEN else '❌ FALTANDO'}")
    logger.info("=" * 60)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
