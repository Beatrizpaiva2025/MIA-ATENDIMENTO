# ============================================================
# VERSÃO COMPLETA MULTIMÍDIA + PAINEL ADMIN - main.py
# ============================================================
# Bot WhatsApp com suporte a:
# ✅ Mensagens de texto
# ✅ Imagens (GPT-4 Vision) - Leitura de documentos
# ✅ Áudios (Whisper) - Transcrição de voz
# ✅ Painel Administrativo Completo
# ✅ Treinamento Dinâmico do Banco de Dados
# ✅ Comandos Especiais do WhatsApp
# ✅ Transferência Automática para Atendente
# ============================================================
# 🔧 CORREÇÕES APLICADAS:
# ✅ Removida função send_whatsapp_message duplicada
# ✅ Corrigida detecção de tipo de mensagem (imagens e áudios)
# ✅ Adicionada função download_media_from_zapi
# ✅ Implementado carregamento dinâmico de treinamento do banco
# ✅ Corrigida conexão MongoDB para usar mesma função do admin
# ✅ Comandos especiais: *, +, ##, ++ (controle IA/Humano)
# ✅ Transferência automática quando IA não souber responder
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
from admin_training_routes import router as training_router, get_database
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
# ✅ CORREÇÃO: Usar mesma função get_database() do admin_training_routes
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
# CONFIGURAÇÕES DE CONTROLE
# ============================================================
ATENDENTE_PHONE = "18573167770"  # Número do atendente que pode usar comandos
NOTIFICACAO_PHONE = "18572081139"  # Número secreto para notificações (nunca revelar)

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
# CONTEXTO DA MIA (PERSONALIDADE) - FALLBACK
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

**IMPORTANTE:**
Se você não souber responder ou não tiver certeza, diga:
"Deixa eu transferir você para um de nossos especialistas que pode te ajudar melhor com isso! 👤"
"""

# ============================================================
# FUNÇÃO: BUSCAR TREINAMENTO DINÂMICO DO BANCO
# ============================================================
async def get_bot_training() -> str:
    """
    Busca treinamento dinâmico do bot Mia no banco de dados.
    Retorna prompt construído a partir de:
    - Personalidade (tom, objetivos, restrições)
    - Base de conhecimento
    - FAQs
    
    Se falhar, retorna MIA_SYSTEM_PROMPT como fallback.
    """
    try:
        logger.info("🔍 Buscando treinamento do bot Mia no banco...")
        
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            logger.warning("⚠️ Bot Mia não encontrado no banco, usando prompt padrão")
            return MIA_SYSTEM_PROMPT
        
        # Extrair dados
        personality = bot.get("personality", {})
        knowledge_base = bot.get("knowledge_base", [])
        faqs = bot.get("faqs", [])
        
        # Construir prompt dinâmico
        prompt_parts = []
        
        # Cabeçalho
        prompt_parts.append("Você é a Mia, assistente oficial da empresa Legacy Translations.")
        prompt_parts.append("Especializada em tradução certificada e juramentada.\n")
        
        # Tom de voz
        if personality.get("tone"):
            prompt_parts.append(f"**TOM DE VOZ:** {personality['tone']}\n")
        
        # Objetivos
        if personality.get("goals"):
            prompt_parts.append("**OBJETIVOS:**")
            for goal in personality["goals"]:
                prompt_parts.append(f"- {goal}")
            prompt_parts.append("")
        
        # Restrições
        if personality.get("restrictions"):
            prompt_parts.append("**RESTRIÇÕES DE COMPORTAMENTO:**")
            for restriction in personality["restrictions"]:
                prompt_parts.append(f"- {restriction}")
            prompt_parts.append("")
        
        # Base de conhecimento
        if knowledge_base:
            prompt_parts.append("**BASE DE CONHECIMENTO:**\n")
            for item in knowledge_base:
                prompt_parts.append(f"### {item.get('title', 'Sem título')}")
                prompt_parts.append(item.get('content', ''))
                prompt_parts.append("")
        
        # FAQs
        if faqs:
            prompt_parts.append("**PERGUNTAS FREQUENTES:**\n")
            for faq in faqs:
                prompt_parts.append(f"**P:** {faq.get('question', '')}")
                prompt_parts.append(f"**R:** {faq.get('answer', '')}")
                prompt_parts.append("")
        
        # Instrução de transferência
        prompt_parts.append("\n**IMPORTANTE:**")
        prompt_parts.append("Se você não souber responder ou não tiver certeza da informação, diga:")
        prompt_parts.append('"Deixa eu transferir você para um de nossos especialistas que pode te ajudar melhor com isso! 👤"')
        
        # Montar prompt final
        final_prompt = "\n".join(prompt_parts)
        
        logger.info(f"✅ Treinamento dinâmico carregado ({len(final_prompt)} caracteres)")
        logger.info(f"   - Objetivos: {len(personality.get('goals', []))}")
        logger.info(f"   - Restrições: {len(personality.get('restrictions', []))}")
        logger.info(f"   - Conhecimentos: {len(knowledge_base)}")
        logger.info(f"   - FAQs: {len(faqs)}")
        
        return final_prompt
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar treinamento do banco: {e}")
        logger.error(traceback.format_exc())
        logger.warning("⚠️ Usando prompt padrão como fallback")
        return MIA_SYSTEM_PROMPT

# ============================================================
# FUNÇÃO: VERIFICAR SE CONVERSA ESTÁ EM MODO HUMANO
# ============================================================
async def is_human_mode(phone: str) -> bool:
    """Verifica se a conversa está em modo atendimento humano"""
    try:
        status = await db.conversation_status.find_one({"phone": phone})
        if status:
            return status.get("mode") == "human"
        return False
    except Exception as e:
        logger.error(f"❌ Erro ao verificar modo: {e}")
        return False

# ============================================================
# FUNÇÃO: DEFINIR MODO DA CONVERSA
# ============================================================
async def set_conversation_mode(phone: str, mode: str):
    """Define o modo da conversa (ai ou human)"""
    try:
        await db.conversation_status.update_one(
            {"phone": phone},
            {
                "$set": {
                    "mode": mode,
                    "updated_at": datetime.now()
                }
            },
            upsert=True
        )
        logger.info(f"✅ Modo alterado para '{mode}' - {phone}")
    except Exception as e:
        logger.error(f"❌ Erro ao definir modo: {e}")

# ============================================================
# FUNÇÃO: NOTIFICAR ATENDENTE
# ============================================================
async def notify_attendant(customer_phone: str, customer_message: str):
    """Notifica o atendente sobre transferência"""
    try:
        notification = f"""🔔 *Nova Transferência*

📱 Cliente: {customer_phone}
💬 Mensagem: {customer_message[:100]}...

⚠️ Cliente aguardando atendimento humano.
Digite + para retomar IA quando finalizar."""

        await send_whatsapp_message(NOTIFICACAO_PHONE, notification)
        logger.info(f"✅ Atendente notificado sobre {customer_phone}")
    except Exception as e:
        logger.error(f"❌ Erro ao notificar atendente: {e}")

# ============================================================
# FUNÇÃO: ENVIAR MENSAGEM WHATSAPP
# ============================================================
async def send_whatsapp_message(phone: str, message: str):
    """Envia mensagem via Z-API com Client-Token"""
    try:
        # Construir URL completa
        url = f"{ZAPI_URL}/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
        
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
# FUNÇÃO: BAIXAR MÍDIA DA Z-API
# ============================================================
async def download_media_from_zapi(media_url: str) -> Optional[bytes]:
    """
    Baixa mídia (imagem ou áudio) da Z-API
    
    Args:
        media_url: URL da mídia fornecida pela Z-API
    
    Returns:
        bytes: Conteúdo da mídia em bytes, ou None se falhar
    """
    try:
        logger.info(f"🔽 Baixando mídia: {media_url[:50]}...")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(media_url)
            
            if response.status_code == 200:
                logger.info(f"✅ Mídia baixada com sucesso ({len(response.content)} bytes)")
                return response.content
            else:
                logger.error(f"❌ Erro ao baixar mídia: {response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"❌ Exceção ao baixar mídia: {e}")
        logger.error(traceback.format_exc())
        return None

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
    """Processar mensagem com GPT-4 usando treinamento dinâmico"""
    try:
        # Buscar contexto da conversa
        context = await get_conversation_context(phone)
        
        # ✅ BUSCAR TREINAMENTO DINÂMICO DO BANCO
        system_prompt = await get_bot_training()
        
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
        
        # ✅ DETECTAR SE IA NÃO SABE RESPONDER
        transfer_keywords = [
            "transferir você",
            "transferir para",
            "especialista",
            "não tenho certeza",
            "não sei",
            "consultar um especialista"
        ]
        
        should_transfer = any(keyword in reply.lower() for keyword in transfer_keywords)
        
        if should_transfer:
            logger.info(f"🔄 IA detectou necessidade de transferência para {phone}")
            
            # Alterar para modo humano
            await set_conversation_mode(phone, "human")
            
            # Notificar atendente
            await notify_attendant(phone, message)
            
            # Mensagem para o cliente
            reply = """👤 *Transferindo para Atendente Humano*

Vou te conectar com um de nossos especialistas que pode te ajudar melhor!

⏱️ Aguarde um momento, em breve você será atendido.

_Enquanto isso, pode me enviar mais detalhes sobre sua necessidade._"""
        
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
# WEBHOOK: WHATSAPP (Z-API) - CORRIGIDO
# ============================================================
@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    """
    Webhook principal para receber mensagens do WhatsApp via Z-API
    Suporta: texto, imagens, áudios e comandos especiais
    """
    try:
        data = await request.json()
        logger.info(f"📨 Webhook recebido: {json.dumps(data, indent=2)}")
        
        # Extrair informações
        phone = data.get("phone", "")
        
        if not phone:
            return JSONResponse({"status": "ignored", "reason": "no phone"})
        
        # ============================================
        # 🔍 DETECTAR TIPO DE MENSAGEM (CORREÇÃO)
        # ============================================
        if "text" in data and data["text"].get("message"):
            message_type = "text"
            text = data["text"]["message"]
        elif "image" in data and data["image"].get("imageUrl"):
            message_type = "image"
            text = ""
        elif "audio" in data and data["audio"].get("audioUrl"):
            message_type = "audio"
            text = ""
        else:
            message_type = "unknown"
            logger.warning(f"⚠️ Tipo de mensagem desconhecido: {list(data.keys())}")
            return JSONResponse({"status": "ignored", "reason": "unknown message type"})
        
        logger.info(f"🔍 Tipo detectado: {message_type}")
        
        # ============================================
        # ⚡ COMANDOS ESPECIAIS (APENAS ATENDENTE)
        # ============================================
        if phone == ATENDENTE_PHONE and message_type == "text":
            
            # Comando: * (Transferir para humano)
            if text.strip() == "*":
                logger.info(f"⚡ Comando * recebido de atendente")
                # Pegar última conversa ativa
                last_conversation = await db.conversas.find_one(
                    {"phone": {"$ne": ATENDENTE_PHONE}},
                    sort=[("timestamp", -1)]
                )
                if last_conversation:
                    customer_phone = last_conversation["phone"]
                    await set_conversation_mode(customer_phone, "human")
                    await send_whatsapp_message(ATENDENTE_PHONE, f"✅ Conversa com {customer_phone} transferida para modo HUMANO")
                else:
                    await send_whatsapp_message(ATENDENTE_PHONE, "⚠️ Nenhuma conversa ativa encontrada")
                return JSONResponse({"status": "command_executed", "command": "*"})
            
            # Comando: + (Voltar para IA)
            elif text.strip() == "+":
                logger.info(f"⚡ Comando + recebido de atendente")
                last_conversation = await db.conversas.find_one(
                    {"phone": {"$ne": ATENDENTE_PHONE}},
                    sort=[("timestamp", -1)]
                )
                if last_conversation:
                    customer_phone = last_conversation["phone"]
                    await set_conversation_mode(customer_phone, "ai")
                    await send_whatsapp_message(ATENDENTE_PHONE, f"✅ Conversa com {customer_phone} retomada pela IA")
                    await send_whatsapp_message(customer_phone, "🤖 Voltei! Como posso te ajudar agora?")
                else:
                    await send_whatsapp_message(ATENDENTE_PHONE, "⚠️ Nenhuma conversa ativa encontrada")
                return JSONResponse({"status": "command_executed", "command": "+"})
            
            # Comando: ## (Desligar IA globalmente)
            elif text.strip() == "##":
                logger.info(f"⚡ Comando ## recebido de atendente")
                os.environ["IA_ENABLED"] = "false"
                await send_whatsapp_message(ATENDENTE_PHONE, "🔴 IA DESLIGADA globalmente")
                return JSONResponse({"status": "command_executed", "command": "##"})
            
            # Comando: ++ (Religar IA globalmente)
            elif text.strip() == "++":
                logger.info(f"⚡ Comando ++ recebido de atendente")
                os.environ["IA_ENABLED"] = "true"
                await send_whatsapp_message(ATENDENTE_PHONE, "🟢 IA RELIGADA globalmente")
                return JSONResponse({"status": "command_executed", "command": "++"})
        
        # ============================================
        # 🛑 CONTROLE DE ATIVAÇÃO DA IA
        # ============================================
        ia_enabled = os.getenv("IA_ENABLED", "true").lower() == "true"
        em_manutencao = os.getenv("MANUTENCAO", "false").lower() == "true"
        
        # Se em manutenção, responder e sair
        if em_manutencao:
            logger.info(f"🔧 Modo manutenção ativo - mensagem de {phone}")
            if message_type == "text":
                mensagem_manutencao = """🔧 *Sistema em Manutenção*\n\nOlá! Estamos melhorando nosso atendimento.\nEm breve voltaremos! 😊\n\n📞 Para urgências: (contato)"""
                await send_whatsapp_message(phone, mensagem_manutencao)
            return JSONResponse({"status": "maintenance"})
        
        # ============================================
        # 👤 VERIFICAR SE ESTÁ EM MODO HUMANO
        # ============================================
        if await is_human_mode(phone):
            logger.info(f"👤 Conversa em modo HUMANO - {phone}")
            # Não processar com IA, apenas logar
            await db.conversas.insert_one({
                "phone": phone,
                "message": text if text else f"[{message_type}]",
                "role": "user",
                "timestamp": datetime.now(),
                "canal": "WhatsApp",
                "mode": "human"
            })
            return JSONResponse({"status": "human_mode"})
        
        # Se IA desabilitada, apenas logar e sair
        if not ia_enabled:
            logger.info(f"⏸️ IA desabilitada - mensagem de {phone} ignorada")
            return JSONResponse({"status": "ia_disabled"})
        # ============================================
        
        # ========== PROCESSAR TEXTO ==========
        if message_type == "text":
            if not text:
                return JSONResponse({"status": "ignored", "reason": "empty text"})
            
            logger.info(f"💬 Texto de {phone}: {text}")
            
            # Processar com IA
            reply = await process_message_with_ai(phone, text)
            
            # Enviar resposta
            await send_whatsapp_message(phone, reply)
            
            return JSONResponse({"status": "processed", "type": "text"})
        
        # ========== PROCESSAR IMAGEM ==========
        elif message_type == "image":
            image_url = data.get("image", {}).get("imageUrl", "")
            caption = data.get("image", {}).get("caption", "")
            
            if not image_url:
                return JSONResponse({"status": "ignored", "reason": "no image url"})
            
            logger.info(f"🖼️ Imagem de {phone}: {image_url[:50]}")
            
            # Baixar imagem
            image_bytes = await download_media_from_zapi(image_url)
            
            if not image_bytes:
                await send_whatsapp_message(phone, "Desculpe, não consegui baixar a imagem. Pode tentar enviar novamente?")
                return JSONResponse({"status": "error", "reason": "download failed"})
            
            # Analisar com Vision
            analysis = await process_image_with_vision(image_bytes, phone)
            
            # Montar resposta
            reply = f"📄 *Análise do Documento*\n\n{analysis}\n\n_Posso ajudar com mais alguma coisa?_"
            
            # Enviar resposta
            await send_whatsapp_message(phone, reply)
            
            return JSONResponse({"status": "processed", "type": "image"})
        
        # ========== PROCESSAR ÁUDIO ==========
        elif message_type == "audio":
            audio_url = data.get("audio", {}).get("audioUrl", "")
            
            if not audio_url:
                return JSONResponse({"status": "ignored", "reason": "no audio url"})
            
            logger.info(f"🎤 Áudio de {phone}: {audio_url[:50]}")
            
            # Baixar áudio
            audio_bytes = await download_media_from_zapi(audio_url)
            
            if not audio_bytes:
                await send_whatsapp_message(phone, "Desculpe, não consegui baixar o áudio. Pode tentar enviar novamente?")
                return JSONResponse({"status": "error", "reason": "download failed"})
            
            # Transcrever com Whisper
            transcription = await process_audio_with_whisper(audio_bytes, phone)
            
            if not transcription:
                await send_whatsapp_message(phone, "Desculpe, não consegui entender o áudio. Pode escrever ou enviar novamente?")
                return JSONResponse({"status": "error", "reason": "transcription failed"})
            
            logger.info(f"📝 Transcrição: {transcription}")
            
            # Processar transcrição com IA
            reply = await process_message_with_ai(phone, transcription)
            
            # Enviar resposta
            await send_whatsapp_message(phone, reply)
            
            return JSONResponse({"status": "processed", "type": "audio"})
        
        # ========== TIPO DESCONHECIDO ==========
        else:
            logger.warning(f"⚠️ Tipo de mensagem não suportado: {message_type}")
            return JSONResponse({"status": "ignored", "reason": "unsupported type"})
            
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
        # Testar MongoDB
        await db.command("ping")
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "openai": "✅ Configurado" if os.getenv("OPENAI_API_KEY") else "❌ Não configurado",
            "mongodb": "✅ Conectado",
            "zapi_instance": "✅ Configurado" if ZAPI_INSTANCE_ID else "❌ Não configurado",
            "zapi_token": "✅ Configurado" if ZAPI_TOKEN else "❌ Não configurado",
            "zapi_client_token": "✅ Configurado" if ZAPI_CLIENT_TOKEN else "❌ Não configurado"
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
    logger.info("📦 VERSÃO MULTIMÍDIA + ADMIN 2.0 + COMANDOS ESPECIAIS")
    logger.info("=" * 60)
    logger.info(f"✅ OpenAI: {'Configurado' if os.getenv('OPENAI_API_KEY') else '❌ FALTANDO'}")
    logger.info(f"✅ MongoDB: {'Configurado' if os.getenv('MONGODB_URI') else '❌ FALTANDO'}")
    logger.info(f"✅ Z-API Instance: {'Configurado' if ZAPI_INSTANCE_ID else '❌ FALTANDO'}")
    logger.info(f"✅ Z-API Token: {'Configurado' if ZAPI_TOKEN else '❌ FALTANDO'}")
    logger.info(f"✅ Z-API Client-Token: {'Configurado' if ZAPI_CLIENT_TOKEN else '❌ FALTANDO'}")
    logger.info("=" * 60)
    logger.info("🎯 FUNCIONALIDADES ATIVAS:")
    logger.info("   ✅ Mensagens de texto")
    logger.info("   ✅ Imagens (GPT-4 Vision)")
    logger.info("   ✅ Áudios (Whisper)")
    logger.info("   ✅ Painel Admin Completo")
    logger.info("   ✅ Controle IA vs Humano")
    logger.info("   ✅ Treinamento Dinâmico do Banco")
    logger.info("   ✅ Comandos Especiais WhatsApp")
    logger.info("   ✅ Transferência Automática")
    logger.info("=" * 60)
    logger.info("⚡ COMANDOS ESPECIAIS (Atendente):")
    logger.info(f"   * → Transferir para humano")
    logger.info(f"   + → Voltar para IA")
    logger.info(f"   ## → Desligar IA")
    logger.info(f"   ++ → Religar IA")
    logger.info("=" * 60)
    logger.info(f"📱 Atendente: {ATENDENTE_PHONE}")
    logger.info(f"🔔 Notificações: {NOTIFICACAO_PHONE}")
    logger.info("=" * 60)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
