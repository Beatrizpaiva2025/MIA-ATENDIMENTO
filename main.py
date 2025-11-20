# ============================================================
# VERSÃO COMPLETA MULTIMÍDIA + PAINEL ADMIN - main.py
# ============================================================
# Bot WhatsApp com suporte a:
# ✅ Mensagens de texto
# ✅ Imagens (GPT-4 Vision) - Leitura de documentos
# ✅ Áudios (Whisper) - Transcrição de voz
# ✅ Painel Administrativo Completo
# ============================================================

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

# Importar rotas do admin
from admin_routes import router as admin_router
from admin_training_routes import router as training_router
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
# Usar mesma conexão do admin
from admin_training_routes import get_database
db = get_database()

# ============================================================
# INCLUIR ROTAS DO PAINEL ADMIN
# ============================================================
app.include_router(admin_router)
app.include_router(training_router)
app.include_router(controle_router)

# ============================================================
# CONFIGURAÇÕES Z-API
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
async def send_whatsapp_message(phone: str, message: str):
    """Envia mensagem via Z-API com Client-Token"""
    try:
        # Construir URL completa
        url = f"https://api.z-api.io/instances/3E4255284F9C20BCBD775E3E11E99CA6/token/4EDA979AE181FE76311C51F5/send-text"
        
        # Headers COM Client-Token
        headers = {
            "Content-Type": "application/json",
            "Client-Token": os.getenv("ZAPI_CLIENT_TOKEN", "")
        }
        
        # Payload
        payload = {
            "phone": phone,
            "message": message
        }
        
        # Logs de debug
        logger.info(f"🔍 Enviando para Z-API: {url}")
        logger.info(f"🔍 Telefone: {phone}")
        logger.info(f"🔍 Client-Token configurado: {'Sim' if headers['Client-Token'] else 'Não'}")
        
        # Enviar requisição COM headers
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            logger.info(f"🔍 Status Z-API: {response.status_code}")
            logger.info(f"🔍 Resposta Z-API: {response.text}")
            
            if response.status_code == 200:
                logger.info(f"✅ Mensagem enviada com sucesso para {phone}")
                return True
            else:
                logger.error(f"❌ Erro ao enviar: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Exceção ao enviar para Z-API: {e}")
        return False


# ============================================================
# FUNÇÃO: PROCESSAR IMAGEM COM GPT-4 VISION
# ============================================================
async def process_image_with_vision(image_bytes: bytes, phone: str) -> str:
    """
    Analisa imagem usando GPT-4 Vision para identificar documento
    
    Args:
        image_bytes: Bytes da imagem
        phone: Telefone do usuário (para contexto)
    
    Returns:
        str: Análise do documento
    """
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
    """
    Transcreve áudio usando Whisper
    
    Args:
        audio_bytes: Bytes do áudio
        phone: Telefone do usuário
    
    Returns:
        str: Texto transcrito
    """
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
# FUNÇÃO: ENVIAR MENSAGEM WHATSAPP
# ============================================================
async def send_whatsapp_message(phone: str, message: str):
    """Enviar mensagem via Z-API"""
    try:
        url = f"{ZAPI_URL}/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
        
        payload = {
            "phone": phone,
            "message": message
        }
        
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
# ============================================================
# FUNÇÃO AUXILIAR: NORMALIZAR TELEFONE
# ============================================================
def normalize_phone(phone: str) -> str:
    """Normaliza número de telefone para comparação"""
    return ''.join(filter(str.isdigit, phone))[-10:]

# ============================================================
# WEBHOOK: WHATSAPP (Z-API) - INTEGRADO
# ============================================================
@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    """
    Webhook principal para receber mensagens do WhatsApp via Z-API
    Suporta: texto, imagens e áudios
    """
    try:
        data = await request.json()
        logger.info(f"📨 Webhook recebido: {json.dumps(data, indent=2)}")
        
        # ============================================
        # 🛑 CONTROLE DE ATIVAÇÃO DA IA
        # ============================================
        ia_enabled = os.getenv("IA_ENABLED", "true").lower() == "true"
        em_manutencao = os.getenv("MANUTENCAO", "false").lower() == "true"
        
        # Extrair informações
        phone = data.get("phone", "")
        message_id = data.get("messageId", "")
        connected_phone = data.get("connectedPhone", "")
        is_group = data.get("isGroup", False)
        
        # 🚫 FILTRO: Ignorar mensagens de grupos
        if is_group:
            logger.info(f"🚫 Mensagem de grupo ignorada")
            return JSONResponse({"status": "ignored", "reason": "group message"})
        
        message_type = data.get("messageType", "text")
        
        if not phone:
            return JSONResponse({"status": "ignored", "reason": "no phone"})
        
        # Se em manutenção, responder e sair
        if em_manutencao:
            logger.info(f"🔧 Modo manutenção ativo - mensagem de {phone}")
            if message_type == "text":
                mensagem_manutencao = """🔧 *Sistema em Manutenção*\n\nOlá! Estamos melhorando nosso atendimento.\nEm breve voltaremos! 😊\n\n📞 Para urgências: (contato)"""
                await send_whatsapp_message(phone, mensagem_manutencao)
            return JSONResponse({"status": "maintenance"})
        
        # Se IA desabilitada, apenas logar e sair
        if not ia_enabled:
            logger.info(f"⏸️ IA desabilitada - mensagem de {phone} ignorada")
            return JSONResponse({"status": "ia_disabled"})
        # ============================================
        
        # ========== PROCESSAR TEXTO ==========
        if message_type == "text":
            text = data.get("text", {}).get("message", "")
            
            if not text:
                return JSONResponse({"status": "ignored", "reason": "empty text"})
            
            logger.info(f"💬 Texto de {phone}: {text}")
            
            # ============================================
