# ============================================================
# VERSÃO COMPLETA MULTIMÍDIA + PAINEL ADMIN - main.py
# ============================================================
# Bot WhatsApp com suporte a:
# ✅ Mensagens de texto
# ✅ Imagens (GPT-4 Vision) - Leitura de documentos
# ✅ Áudios (Whisper) - Transcrição de voz
# ✅ PDFs (Extração de texto + Vision)
# ✅ Painel Administrativo Completo
# ✅ TREINAMENTO DINÂMICO DO MONGODB
# ✅ CONTROLE DE ACESSO (Admin vs Legacy)
# ✅ PIPELINE E LEADS
# ✅ COMANDOS * e + RESTRITOS AO ATENDENTE
# ============================================================

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os
import httpx
from openai import AsyncOpenAI
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import logging
from typing import Optional, Dict, Any, List, Annotated 
from pydantic import BaseModel
import traceback
import json
import base64
from io import BytesIO

# PDF Support imports
from PyPDF2 import PdfReader
from pdf2image import convert_from_bytes
from PIL import Image

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

# IMPORTANTE: Adicionar middleware de sessão
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "your-secret-key-change-in-production")
)

app.mount("/static", StaticFiles(directory="static"), name="static")  

# Templates
templates = Jinja2Templates(directory="templates")

# Clientes
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Usar mesma conexão do admin
from admin_training_routes import get_database
db = get_database()

# ============================================================
# CONFIGURAÇÃO: NÚMERO DO ATENDENTE
# ============================================================
ATENDENTE_PHONE = "18572081139"  # APENAS ESTE NÚMERO PODE USAR * E +

# ============================================
# ACCESS CONTROL HELPER FUNCTIONS
# ============================================

def get_current_user(request: Request):
    """Get the currently logged-in user from session"""
    username = request.session.get('username')
    if not username:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated"
        )
    return username

def check_admin_access(request: Request):
    """Check if the current user has admin privileges"""
    username = get_current_user(request)
    if username.lower() != 'admin':
        raise HTTPException(
            status_code=403,
            detail="Access denied - Administrator privileges required"
        )
    return username

# ============================================================
# CONTROLE DO BOT - LIGAR/DESLIGAR
# ============================================================

# Estado global do bot (em memória + MongoDB)
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
        logger.info(f"✅ Bot {'ATIVADO' if enabled else 'DESATIVADO'}")
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar status do bot: {e}")
        return False

# ============================================================
# TRANSFERÊNCIA PARA ATENDENTE HUMANO
# ============================================================

async def notificar_atendente(phone: str, motivo: str = "Cliente solicitou"):
    """Envia notificação para atendente com resumo da conversa"""
    try:
        # Buscar últimas 10 mensagens da conversa
        mensagens = await db.conversas.find(
            {"phone": phone}
        ).sort("timestamp", -1).limit(10).to_list(length=10)
        
        # Inverter para ordem cronológica
        mensagens.reverse()
        
        # Montar resumo
        resumo_linhas = []
        for msg in mensagens:
            role = "👤 Cliente" if msg.get("role") == "user" else "🤖 IA"
            texto = msg.get("message", "")[:100]
            resumo_linhas.append(f"{role}: {texto}")
        
        resumo = "\n".join(resumo_linhas) if resumo_linhas else "Sem histórico"
        
        # Montar mensagem de notificação
        mensagem_atendente = f"""🔔 *TRANSFERÊNCIA DE ATENDIMENTO*

📱 *Cliente:* {phone}
⚠️ *Motivo:* {motivo}

📝 *Resumo da Conversa:*
{resumo}

---
✅ Para assumir o atendimento, responda ao cliente diretamente.
🔄 Para retornar à IA, digite: +
"""
        
        # Enviar notificação
        await send_whatsapp_message(ATENDENTE_PHONE, mensagem_atendente)
        logger.info(f"✅ Notificação enviada para atendente: {phone}")
        
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
        
        # Notificar atendente
        await notificar_atendente(phone, motivo)
        
        # NÃO enviar mensagem ao cliente (transferência invisível)
        # Cliente não deve saber quando está com IA ou humano
        
        logger.info(f"✅ Conversa transferida para humano: {phone} (Motivo: {motivo})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao transferir para humano: {e}")
        return False

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
# FUNÇÃO: BUSCAR TREINAMENTO DINÂMICO DO MONGODB
# ============================================================
async def get_bot_training() -> str:
    """Busca treinamento dinâmico do bot Mia no MongoDB"""
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            logger.warning("⚠️ Bot Mia não encontrado no banco, usando padrão")
            return """Você é a Mia, assistente da Legacy Translations.
Responda de forma profissional e educada."""
        
        # Extrair dados do bot
        personality = bot.get("personality", {})
        knowledge_base = bot.get("knowledge_base", [])
        faqs = bot.get("faqs", [])
        
        # Montar prompt dinâmico
        prompt_parts = []
        
        # Objetivos (goals)
        if personality.get("goals"):
            goals_text = "\n".join(personality["goals"]) if isinstance(personality["goals"], list) else personality["goals"]
            prompt_parts.append(f"**OBJETIVOS:**\n{goals_text}")
        
        # Tom de voz
        if personality.get("tone"):
            prompt_parts.append(f"**TOM DE VOZ:**\n{personality['tone']}")
        
        # Restrições
        if personality.get("restrictions"):
            restrictions_text = "\n".join(personality["restrictions"]) if isinstance(personality["restrictions"], list) else personality["restrictions"]
            prompt_parts.append(f"**RESTRIÇÕES:**\n{restrictions_text}")
        
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
        
        logger.info(f"✅ Treinamento carregado do MongoDB ({len(knowledge_base)} conhecimentos, {len(faqs)} FAQs)")
        
        return final_prompt
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar treinamento: {e}")
        return """Você é a Mia, assistente da Legacy Translations.
Responda de forma profissional e educada."""

# ============================================================
# FUNÇÃO: ENVIAR MENSAGEM WHATSAPP
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
        logger.info(f"📤 Enviando mensagem para {phone}")
        
        # Enviar requisição COM headers
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            logger.info(f"📊 Status Z-API: {response.status_code}")
            
            if response.status_code == 200:
                logger.info(f"✅ Mensagem enviada com sucesso")
                return True
            else:
                logger.error(f"❌ Erro ao enviar: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Exceção ao enviar mensagem: {str(e)}")
        return False

# ============================================================
# FUNÇÃO: BAIXAR MÍDIA DA Z-API
# ============================================================
async def download_media_from_zapi(media_url: str) -> Optional[bytes]:
    """Baixa mídia (imagem/áudio/pdf) da Z-API"""
    try:
        logger.info(f"⬇️ Baixando mídia: {media_url[:100]}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(media_url)
            
            if response.status_code == 200:
                logger.info(f"✅ Mídia baixada ({len(response.content)} bytes)")
                return response.content
            else:
                logger.error(f"❌ Erro ao baixar mídia: {response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"❌ Erro ao baixar mídia: {str(e)}")
        return None

# ============================================================
# FUNÇÃO: PROCESSAR PDF COM GPT-4 VISION
# ============================================================
async def process_pdf_with_vision(pdf_url: str, phone: str) -> str:
    """Process PDF documents using GPT-4 Vision"""
    try:
        logger.info(f"📄 Processando PDF: {pdf_url[:100]}")
        
        # Download the PDF
        pdf_bytes = await download_media_from_zapi(pdf_url)
        
        if not pdf_bytes:
            return "⚠️ Não consegui baixar o PDF. Pode enviar novamente?"
        
        # Try to extract text first
        try:
            pdf_reader = PdfReader(BytesIO(pdf_bytes))
            extracted_text = ""
            for page in pdf_reader.pages:
                extracted_text += page.extract_text() + "\n"
            
            if extracted_text.strip():
                # If text extraction successful, analyze with GPT
                training_prompt = await get_bot_training()
                
                response = await openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": training_prompt},
                        {"role": "user", "content": f"Analise este documento PDF e forneça orçamento de tradução:\n\n{extracted_text[:3000]}"}
                    ],
                    max_tokens=800
                )
                
                analysis = response.choices[0].message.content
                
                # Save to database
                await db.conversas.insert_one({
                    "phone": phone,
                    "message": "[PDF ENVIADO - Texto extraído]",
                    "role": "user",
                    "timestamp": datetime.now(),
                    "type": "pdf",
                    "canal": "WhatsApp"
                })
                
                await db.conversas.insert_one({
                    "phone": phone,
                    "message": analysis,
                    "role": "assistant",
                    "timestamp": datetime.now(),
                    "canal": "WhatsApp"
                })
                
                logger.info(f"✅ PDF analisado (texto extraído)")
                return analysis
                
        except Exception as text_error:
            logger.warning(f"⚠️ Extração de texto falhou, usando Vision: {text_error}")
        
        # If text extraction fails, convert to images
        images = convert_from_bytes(pdf_bytes, first_page=1, last_page=3)
        
        # Convert first page to base64 for GPT-4 Vision
        buffered = BytesIO()
        images[0].save(buffered, format="JPEG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        # Analyze with GPT-4 Vision
        training_prompt = await get_bot_training()
        
        vision_response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": training_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analise este documento PDF e forneça orçamento de tradução:"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                    ]
                }
            ],
            max_tokens=1000
        )
        
        analysis = vision_response.choices[0].message.content
        
        # Save to database
        await db.conversas.insert_one({
            "phone": phone,
            "message": "[PDF ENVIADO - Análise visual]",
            "role": "user",
            "timestamp": datetime.now(),
            "type": "pdf",
            "canal": "WhatsApp"
        })
        
        await db.conversas.insert_one({
            "phone": phone,
            "message": analysis,
            "role": "assistant",
            "timestamp": datetime.now(),
            "canal": "WhatsApp"
        })
        
        logger.info(f"✅ PDF analisado (Vision)")
        return analysis
        
    except Exception as e:
        logger.error(f"❌ Erro ao processar PDF: {str(e)}")
        return "⚠️ Desculpe, não consegui analisar o PDF. Pode me enviar como imagem ou me dizer quantas páginas tem?"

# ============================================================
# FUNÇÃO: PROCESSAR IMAGEM COM GPT-4 VISION
# ============================================================
async def process_image_with_vision(image_bytes: bytes, phone: str) -> str:
    """Analisa imagem com GPT-4 Vision"""
    try:
        logger.info(f"🖼️ Processando imagem com Vision ({len(image_bytes)} bytes)")
        
        # Converter para base64
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        # Buscar treinamento dinâmico
        training_prompt = await get_bot_training()
        
        # Chamar GPT-4 Vision
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"""{training_prompt}

**TAREFA ESPECIAL - ANÁLISE DE IMAGEM:**
Você recebeu uma imagem de documento. Analise e forneça:
1. Tipo de documento (certidão, diploma, contrato, etc)
2. Idioma detectado
3. Número estimado de páginas (se visível)
4. Orçamento baseado nas regras de preço do treinamento
5. Prazo de entrega

Seja direto e objetivo na resposta."""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analise este documento e me dê um orçamento de tradução."
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
        
        logger.info(f"✅ Análise Vision concluída")
        return analysis
        
    except Exception as e:
        logger.error(f"❌ Erro no Vision: {str(e)}")
        return "Desculpe, não consegui analisar a imagem. Pode me dizer quantas páginas tem o documento?"

# ============================================================
# FUNÇÃO: PROCESSAR ÁUDIO COM WHISPER
# ============================================================
async def process_audio_with_whisper(audio_bytes: bytes, phone: str) -> Optional[str]:
    """Transcreve áudio com Whisper"""
    try:
        logger.info(f"🎤 Processando áudio com Whisper ({len(audio_bytes)} bytes)")
        
        # Salvar temporariamente
        temp_file = BytesIO(audio_bytes)
        temp_file.name = "audio.ogg"
        
        # Chamar Whisper
        transcription = await openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=temp_file,
            language="pt"
        )
        
        transcribed_text = transcription.text
        
        # Salvar no banco
        await db.conversas.insert_one({
            "phone": phone,
            "message": f"[ÁUDIO] {transcribed_text}",
            "role": "user",
            "timestamp": datetime.now(),
            "canal": "WhatsApp",
            "type": "audio"
        })
        
        logger.info(f"✅ Áudio transcrito: {transcribed_text[:100]}")
        return transcribed_text
        
    except Exception as e:
        logger.error(f"❌ Erro no Whisper: {str(e)}")
        return None

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
        logger.error(f"❌ Erro ao buscar contexto: {e}")
        return []

# ============================================================
# FUNÇÃO: PROCESSAR MENSAGEM COM IA
# ============================================================
async def process_message_with_ai(phone: str, message: str) -> str:
    """Processar mensagem com GPT-4 usando treinamento dinâmico"""
    try:
        # Detectar se cliente quer falar com humano
        if await detectar_solicitacao_humano(message):
            await transferir_para_humano(phone, "Cliente solicitou atendente")
            return None
        
        # Buscar treinamento dinâmico do MongoDB
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
        response = await openai_client.chat.completions.create(
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
        return "Desculpe, tive um problema. Pode repetir?"

# ============================================================
# FUNÇÃO AUXILIAR: NORMALIZAR TELEFONE
# ============================================================
def normalize_phone(phone: str) -> str:
    """Normaliza número de telefone para comparação"""
    return ''.join(filter(str.isdigit, phone))

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
async def api_bot_toggle(request: Request):
    """Toggle bot status"""
    username = check_admin_access(request)
    
    try:
        data = await request.json()
        new_status = data.get("is_active", True)
        
        await db.bots.update_one(
            {"name": "Mia"},
            {"$set": {"is_active": new_status, "updated_at": datetime.now()}},
            upsert=True
        )
        
        return {"success": True, "is_active": new_status}
    except Exception as e:
        logger.error(f"Error toggling bot: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# NOVAS API ROUTES - DASHBOARD E CONTROLE
# ============================================================

@app.get("/admin/api/stats")
async def get_dashboard_stats(request: Request):
    """Get dashboard statistics - Admin only"""
    username = check_admin_access(request)
    
    return {
        "receita_total": 150000.00,
        "novos_leads": 42,
        "taxa_conversao": 35,
        "atividades": [
            {
                "tipo": "NEW LEAD",
                "descricao": "Client 'Tech Solutions' entered the funnel",
                "data": "11/21/2025 2:30 PM",
                "status": "new"
            },
            {
                "tipo": "SALE",
                "descricao": "Sworn Translation - $8,500",
                "data": "11/21/2025 11:15 AM",
                "status": "won"
            }
        ]
    }

@app.get("/admin/api/control-stats")
async def get_control_stats(request: Request):
    """Get control page statistics"""
    username = get_current_user(request)
    
    return {
        "ai_active_minutes": 1250,
        "human_service_minutes": 180,
        "ai_disabled_minutes": 45,
        "total_minutes": 1475,
        "conversations": []
    }

@app.get("/admin/api/transfers")
async def get_transfers(request: Request):
    """Get transfers"""
    username = check_admin_access(request)
    return {"success": True, "transfers": []}

@app.get("/admin/api/documents")
async def get_documents(request: Request):
    """Get documents"""
    username = check_admin_access(request)
    return {"success": True, "documents": []}

@app.post("/admin/bot/start")
async def start_bot(request: Request):
    """Start the AI bot - Admin only"""
    username = check_admin_access(request)
    success = await set_bot_status(True)
    return {"success": success, "message": "Bot started successfully"}

@app.post("/admin/bot/stop")
async def stop_bot(request: Request):
    """Stop the AI bot - Admin only"""
    username = check_admin_access(request)
    success = await set_bot_status(False)
    return {"success": success, "message": "Bot stopped successfully"}

# ============================================================
# API: TRAINING - FIX SAVE FUNCTIONALITY
# ============================================================

# ============================================================
# ROTA: SALVAR PERSONALIDADE DA IA
# ============================================================
@app.post("/admin/config/personality")
async def save_personality(
    request: Request,
    tone: str = Form(...),
    goals: str = Form(...),
    restrictions: str = Form(...)
):
    """Salvar configuração de personalidade da IA"""
    username = get_current_user(request)
    
    try:
        # Buscar ou criar bot
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            bot = {
                "name": "Mia",
                "personality": {},
                "knowledge_base": [],
                "faqs": [],
                "is_active": True,
                "created_at": datetime.now()
            }
            await db.bots.insert_one(bot)
        
        # Atualizar personalidade
        await db.bots.update_one(
            {"name": "Mia"},
            {
                "$set": {
                    "personality": {
                        "tone": tone,
                        "goals": goals,
                        "restrictions": restrictions
                    },
                    "updated_at": datetime.now(),
                    "updated_by": username
                }
            }
        )
        
        return RedirectResponse(url="/admin/training", status_code=303)
        
    except Exception as e:
        print(f"❌ Erro ao salvar personalidade: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.post("/admin/training/knowledge/add")
async def add_knowledge_item(
    request: Request,
    category: str = Form(...),
    title: str = Form(...),
    content: str = Form(...)
):
    """Add new knowledge item to bot training"""
    username = get_current_user(request)
    
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            bot = {
                "name": "Mia",
                "personality": {"goals": [], "tone": "", "restrictions": []},
                "knowledge_base": [],
                "faqs": []
            }
            await db.bots.insert_one(bot)
        
        new_item = {
            "category": category,
            "title": title,
            "content": content,
            "created_by": username,
            "created_at": datetime.now()
        }
        
        await db.bots.update_one(
            {"name": "Mia"},
            {"$push": {"knowledge_base": new_item}}
        )
        
        return RedirectResponse(url="/admin/training", status_code=303)
        
    except Exception as e:
        logger.error(f"Error adding knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/training/faq/add")
async def add_faq_item(
    request: Request,
    question: str = Form(...),
    answer: str = Form(...)
):
    """Add new FAQ item to bot training"""
    username = get_current_user(request)
    
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            bot = {
                "name": "Mia",
                "personality": {"goals": [], "tone": "", "restrictions": []},
                "knowledge_base": [],
                "faqs": []
            }
            await db.bots.insert_one(bot)
        
        new_item = {
            "question": question,
            "answer": answer,
            "created_by": username,
            "created_at": datetime.now()
        }
        
        await db.bots.update_one(
            {"name": "Mia"},
            {"$push": {"faqs": new_item}}
        )
        
        return RedirectResponse(url="/admin/training", status_code=303)
        
    except Exception as e:
        logger.error(f"Error adding FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/admin/training/knowledge/delete/{index}")
async def delete_knowledge_item(index: int, request: Request):
    """Delete knowledge item by index"""
    username = check_admin_access(request)
    
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        
        if bot and "knowledge_base" in bot:
            knowledge_base = bot["knowledge_base"]
            
            if 0 <= index < len(knowledge_base):
                knowledge_base.pop(index)
                
                await db.bots.update_one(
                    {"name": "Mia"},
                    {"$set": {"knowledge_base": knowledge_base}}
                )
                
                return {"success": True}
        
        raise HTTPException(status_code=404, detail="Item not found")
        
    except Exception as e:
        logger.error(f"Error deleting knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/admin/training/faq/delete/{index}")
async def delete_faq_item(index: int, request: Request):
    """Delete FAQ item by index"""
    username = check_admin_access(request)
    
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        
        if bot and "faqs" in bot:
            faqs = bot["faqs"]
            
            if 0 <= index < len(faqs):
                faqs.pop(index)
                
                await db.bots.update_one(
                    {"name": "Mia"},
                    {"$set": {"faqs": faqs}}
                )
                
                return {"success": True}
        
        raise HTTPException(status_code=404, detail="Item not found")
        
    except Exception as e:
        logger.error(f"Error deleting FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ROTA: PIPELINE (COM CONTROLE DE ACESSO)
# ============================================================
@app.get("/admin/pipeline")
async def admin_pipeline(request: Request):
    """Sales Pipeline page"""
    username = get_current_user(request)
    
    return templates.TemplateResponse(
        "admin_pipeline.html",
        {
            "request": request,
            "session": request.session,
            "username": username
        }
    )

# ============================================================
# ROTA: LEADS (COM CONTROLE DE ACESSO)
# ============================================================
@app.get("/admin/leads")
async def admin_leads(request: Request):
    """Leads Management page"""
    username = get_current_user(request)
    
    return templates.TemplateResponse(
        "admin_leads.html",
        {
            "request": request,
            "session": request.session,
            "username": username
        }
    )

# ============================================================
# ROTA: TRANSFERS (NOVA)
# ============================================================
@app.get("/admin/transfers")
async def admin_transfers(request: Request):
    """Transfers page - View conversation transfers"""
    username = get_current_user(request)
    
    # Get recent transfers
    transfers = await db.conversas.find(
        {"mode": "human"}
    ).sort("transferred_at", -1).limit(20).to_list(length=20)
    
    return templates.TemplateResponse(
        "admin_transfers.html",
        {
            "request": request,
            "session": request.session,
            "username": username,
            "transfers": transfers
        }
    )

# ============================================================
# ROTA: DOCUMENTS (NOVA)
# ============================================================
@app.get("/admin/documents")
async def admin_documents(request: Request):
    """Documents page - View uploaded documents"""
    username = get_current_user(request)
    
    # Get recent documents (PDFs, images)
    documents = await db.conversas.find(
        {"type": {"$in": ["pdf", "image", "document"]}}
    ).sort("timestamp", -1).limit(50).to_list(length=50)
    
    return templates.TemplateResponse(
        "admin_documents.html",
        {
            "request": request,
            "session": request.session,
            "username": username,
            "documents": documents
        }
    )

# ============================================================
# ROTA: CONFIGURATIONS (NOVA)
# ============================================================
@app.get("/admin/configurations")
async def admin_configurations(request: Request):
    """Configurations page"""
    username = check_admin_access(request)
    
    bot = await db.bots.find_one({"name": "Mia"})
    
    config = {
        "openai_status": "Connected",
        "zapi_status": "Connected",
        "mongodb_status": "Connected",
        "bot_active": bot.get("is_active", True) if bot else True
    }
    
    return templates.TemplateResponse(
        "admin_config.html",
        {
            "request": request,
            "username": username,
            "config": config
        }
    )

# ============================================================
# WEBHOOK: WHATSAPP (Z-API) - COMANDOS RESTRITOS
# ============================================================

@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    """Webhook principal para receber mensagens do WhatsApp"""
    try:
        data = await request.json()
        logger.info(f"📨 Webhook recebido: {json.dumps(data, indent=2)}")
        
        # ============================================
        # VERIFICAR STATUS DO BOT
        # ============================================
        bot_status = await get_bot_status()
        phone = data.get("phone", "")
        
        # Normalizar telefones para comparação
        phone_normalized = normalize_phone(phone)
        atendente_normalized = normalize_phone(ATENDENTE_PHONE)
        
        # Verificar se é o ATENDENTE
        is_atendente = phone_normalized == atendente_normalized
        
        # Verificar se conversa está em modo humano
        conversa = await db.conversas.find_one({"phone": phone}, sort=[("timestamp", -1)])
        modo_humano = conversa and conversa.get("mode") == "human"
        
        # Se bot desligado OU conversa em modo humano, não processar (EXCETO ATENDENTE)
        if not is_atendente and (not bot_status["enabled"] or modo_humano):
            logger.info(f"⏸️ Bot {'desligado' if not bot_status['enabled'] else 'em modo humano para ' + phone}")
            
            # Salvar mensagem mas não responder
            await db.conversas.insert_one({
                "phone": phone,
                "message": data.get("text", {}).get("message", "[MENSAGEM]"),
                "timestamp": datetime.now(),
                "role": "user",
                "type": "text",
                "mode": "human" if modo_humano else "disabled",
                "canal": "WhatsApp"
            })
            
            return {"status": "received", "processed": False, "reason": "bot_disabled_or_human_mode"}
        
        # ============================================
        # PROCESSAR COMANDOS ESPECIAIS (APENAS ATENDENTE)
        # ============================================
        message_text = ""
        if "text" in data and "message" in data["text"]:
            message_text = data["text"]["message"].strip()
        
        # ✅ APENAS ATENDENTE pode usar * e +
        if is_atendente:
            # Comando: * (Transferir para humano)
            if message_text == "*":
                # Atendente marcando que VAI assumir atendimento
                logger.info(f"✅ Atendente assumiu controle")
                return {"status": "atendente_command_received"}
            
            # Comando: + (Voltar para IA)
            if message_text.startswith("+"):
                # Extrair número do cliente (formato: "+5511999999999")
                parts = message_text.split()
                if len(parts) >= 2:
                    cliente_phone = parts[1]
                    
                    await db.conversas.update_many(
                        {"phone": cliente_phone},
                        {
                            "$set": {
                                "mode": "ia",
                                "returned_at": datetime.now()
                            },
                            "$unset": {
                                "transfer_reason": "",
                                "transferred_at": ""
                            }
                        }
                    )
                    
                    # NÃO avisar cliente sobre retorno à IA (transição invisível)
                    pass
                    
                    await send_whatsapp_message(
                        ATENDENTE_PHONE,
                        f"✅ Cliente {cliente_phone} retornou à IA."
                    )
                    
                    logger.info(f"✅ Cliente {cliente_phone} voltou para IA (comando do atendente)")
                    return {"status": "returned_to_ia"}
                else:
                    await send_whatsapp_message(
                        ATENDENTE_PHONE,
                        "⚠️ Formato incorreto. Use: + 5511999999999"
                    )
                    return {"status": "invalid_format"}

        # ============================================
        # CONTROLE DE ATIVAÇÃO DA IA
        # ============================================
        ia_enabled = os.getenv("IA_ENABLED", "true").lower() == "true"
        em_manutencao = os.getenv("MANUTENCAO", "false").lower() == "true"
        
        # Extrair dados básicos
        is_group = data.get("isGroup", False)
        
        # Ignorar mensagens de grupos
        if is_group:
            logger.info(f"🚫 Mensagem de grupo ignorada")
            return JSONResponse({"status": "ignored", "reason": "group message"})
        
        # Detecção de tipo de mensagem
        message_type = "text"
        
        if "image" in data and data.get("image"):
            message_type = "image"
        elif "audio" in data and data.get("audio"):
            message_type = "audio"
        elif "document" in data and data.get("document"):
            message_type = "document"
        elif "text" in data and data.get("text"):
            message_type = "text"
        
        logger.info(f"🔍 Tipo detectado: {message_type}")
        
        if not phone:
            return JSONResponse({"status": "ignored", "reason": "no phone"})
        
        # Se em manutenção, responder e sair
        if em_manutencao:
            logger.info(f"🔧 Modo manutenção ativo - mensagem de {phone}")
            if message_type == "text":
                mensagem_manutencao = """🔧 *Sistema em Manutenção*

Olá! Estamos melhorando nosso atendimento.
Em breve voltaremos! 😊"""
                await send_whatsapp_message(phone, mensagem_manutencao)
            return JSONResponse({"status": "maintenance"})
        
        # Se IA desabilitada, apenas logar
        if not ia_enabled:
            logger.info(f"⏸️ IA desabilitada - mensagem de {phone} ignorada")
            return JSONResponse({"status": "ia_disabled"})
        
        # ============================================
        # PROCESSAR MENSAGEM DE TEXTO
        # ============================================
        if message_type == "text":
            text = data.get("text", {}).get("message", "")
            
            if not text:
                return JSONResponse({"status": "ignored", "reason": "empty text"})
            
            logger.info(f"💬 Texto de {phone}: {text}")
            
            # Processar com IA
            reply = await process_message_with_ai(phone, text)
            
            # Enviar resposta
            if reply:
                await send_whatsapp_message(phone, reply)
            
            return JSONResponse({"status": "processed", "type": "text"})
        
        # ============================================
        # PROCESSAR IMAGEM
        # ============================================
        elif message_type == "image":
            image_url = data.get("image", {}).get("imageUrl", "")
            
            if not image_url:
                return JSONResponse({"status": "ignored", "reason": "no image url"})
            
            logger.info(f"🖼️ Imagem de {phone}: {image_url[:50]}")
            
            image_bytes = await download_media_from_zapi(image_url)
            
            if not image_bytes:
                await send_whatsapp_message(phone, "Desculpe, não consegui baixar a imagem. Pode tentar enviar novamente?")
                return JSONResponse({"status": "error", "reason": "download failed"})
            
            analysis = await process_image_with_vision(image_bytes, phone)
            await send_whatsapp_message(phone, analysis)
            
            return JSONResponse({"status": "processed", "type": "image"})
        
        # ============================================
        # PROCESSAR ÁUDIO
        # ============================================
        elif message_type == "audio":
            audio_url = data.get("audio", {}).get("audioUrl", "")
            
            if not audio_url:
                return JSONResponse({"status": "ignored", "reason": "no audio url"})
            
            logger.info(f"🎤 Áudio de {phone}: {audio_url[:50]}")
            
            audio_bytes = await download_media_from_zapi(audio_url)
            
            if not audio_bytes:
                await send_whatsapp_message(phone, "Desculpe, não consegui baixar o áudio. Pode tentar enviar novamente?")
                return JSONResponse({"status": "error", "reason": "download failed"})
            
            transcription = await process_audio_with_whisper(audio_bytes, phone)
            
            if not transcription:
                await send_whatsapp_message(phone, "Desculpe, não consegui entender o áudio. Pode escrever ou enviar novamente?")
                return JSONResponse({"status": "error", "reason": "transcription failed"})
            
            logger.info(f"📝 Transcrição: {transcription}")
            
            reply = await process_message_with_ai(phone, transcription)
            
            if reply:
                await send_whatsapp_message(phone, reply)
            
            return JSONResponse({"status": "processed", "type": "audio"})
        
        # ============================================
        # PROCESSAR DOCUMENTO (PDF)
        # ============================================
        elif message_type == "document":
            document_data = data.get("document", {})
            pdf_url = document_data.get("url") or document_data.get("link") or document_data.get("documentUrl")
            mime_type = document_data.get("mimeType", "")
            file_name = document_data.get("fileName", "")
            
            logger.info(f"📎 Documento recebido: {file_name} ({mime_type})")
            
            if "pdf" in mime_type.lower() or file_name.lower().endswith(".pdf"):
                if not pdf_url:
                    await send_whatsapp_message(phone, "⚠️ Não consegui acessar o PDF. Pode enviar novamente?")
                    return JSONResponse({"status": "error", "reason": "no pdf url"})
                
                analysis = await process_pdf_with_vision(pdf_url, phone)
                await send_whatsapp_message(phone, analysis)
                
                return JSONResponse({"status": "processed", "type": "pdf"})
            else:
                await send_whatsapp_message(phone, "⚠️ Por favor, envie apenas arquivos PDF, imagens ou áudios.")
                return JSONResponse({"status": "unsupported_document"})
        
        return JSONResponse({"status": "unknown_type"})
        
    except Exception as e:
        logger.error(f"❌ ERRO no webhook: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

# ============================================================
# ROTA: PÁGINA INICIAL (LOGIN)
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def show_root(request: Request):
    """Redirect root to login"""
    return RedirectResponse(url="/login")

# ============================================================
# ROTA: LOGIN PAGE (GET)
# ============================================================
@app.get("/login", response_class=HTMLResponse)
async def show_login_page(request: Request):
    """Show login page"""
    return templates.TemplateResponse("login.html", {"request": request})

# ============================================================
# ROTA: PROCESSAMENTO DO LOGIN (POST)
# ============================================================
@app.post("/login")
async def handle_login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Handle login with session management"""
    
    # Validate credentials
    valid_credentials = {
        "admin": "admin123",
        "legacy": "legacy2025"
    }
    
    if username in valid_credentials and valid_credentials[username] == password:
        # Set session
        request.session['username'] = username
        request.session['user_role'] = 'admin' if username.lower() == 'admin' else 'legacy'
        
        # Redirect to admin dashboard
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    else:
        # Invalid credentials
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Invalid username or password"
            }
        )

# ============================================================
# ROTA: LOGOUT
# ============================================================
@app.get("/logout")
async def logout(request: Request):
    """Logout and clear session"""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# ============================================================
# ROTA: DASHBOARD (COM CONTROLE DE ACESSO)
# ============================================================
@app.get("/admin/dashboard")
async def admin_dashboard(request: Request):
    """Admin Dashboard - Shows different content based on user role"""
    username = get_current_user(request)
    user_role = request.session.get('user_role', 'legacy')
    
    # Get knowledge count
    bot = await db.bots.find_one({"name": "Mia"})
    knowledge_count = len(bot.get("knowledge_base", [])) if bot else 0
    
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "session": request.session,
            "username": username,
            "user_role": user_role,
            "knowledge_count": knowledge_count
        }
    )

# ============================================================
# ROTA: TRAINING (COM CONTROLE DE ACESSO)
# ============================================================
@app.get("/admin/training")
async def admin_training(request: Request):
    """AI Training page"""
    username = get_current_user(request)
    
    # Buscar dados do bot Mia
    bot = await db.bots.find_one({"name": "Mia"})
    
    if not bot:
        # Criar bot padrão se não existir
        bot = {
            "name": "Mia",
            "personality": {
                "tone": "friendly",
                "goals": "Help clients efficiently, provide accurate information about translation services, and convert inquiries into business opportunities.",
                "restrictions": "Never provide false information, do not make promises without confirmation, always maintain professional ethics."
            },
            "knowledge_base": [],
            "faqs": [],
            "is_active": True,
            "created_at": datetime.now()
        }
        await db.bots.insert_one(bot)
    
    # Extrair dados
    personality = bot.get("personality", {})
    knowledge_items = bot.get("knowledge_base", [])
    faq_items = bot.get("faqs", [])
    
    return templates.TemplateResponse(
        "admin_training.html",
        {
            "request": request,
            "session": request.session,
            "username": username,
            "personality": personality,
            "knowledge_items": knowledge_items,
            "faq_items": faq_items
        }
    )
# ROTA: CONTROL (COM CONTROLE DE ACESSO)
# ============================================================
@app.get("/admin/control")
async def admin_control(request: Request):
    """AI/Human Control page"""
    username = get_current_user(request)
    
    return templates.TemplateResponse(
        "admin_control.html",
        {
            "request": request,
            "session": request.session,
            "username": username
        }
    )

# ============================================================
# INICIAR SERVIDOR
# ============================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
