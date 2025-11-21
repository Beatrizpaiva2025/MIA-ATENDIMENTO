# ============================================================
# VERSÃO COMPLETA MULTIMÍDIA + PDF + PAINEL ADMIN - main.py
# ============================================================
# Bot WhatsApp com suporte a:
# ✅ Mensagens de texto
# ✅ Imagens (GPT-4 Vision)
# ✅ Áudios (Whisper)
# ✅ PDFs (Extração + Vision)
# ✅ Painel Administrativo Completo
# ✅ CONTROLE DE ACESSO (Admin vs Legacy)
# ============================================================

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os
import httpx
from openai import OpenAI
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import logging
from typing import Optional, Dict, Any, List, Annotated 
from pydantic import BaseModel
import traceback
import json
import base64
from io import BytesIO
import PyPDF2

from admin_routes import router as admin_router
from admin_training_routes import router as training_router
from admin_controle_routes import router as controle_router

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="WhatsApp AI Platform - Legacy Translations")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY", "your-secret-key-change-in-production"))
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from admin_training_routes import get_database
db = get_database()

# ============================================
# ACCESS CONTROL
# ============================================
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

# ============================================
# BOT STATUS
# ============================================
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

# ============================================
# TRANSFERÊNCIA HUMANO
# ============================================
ATENDENTE_PHONE = "5518572081139"

async def notificar_atendente(phone: str, motivo: str = "Cliente solicitou"):
    try:
        mensagens = await db.conversas.find({"phone": phone}).sort("timestamp", -1).limit(10).to_list(length=10)
        mensagens.reverse()
        resumo_linhas = []
        for msg in mensagens:
            role = "👤 Cliente" if msg.get("role") == "user" else "🤖 IA"
            texto = msg.get("message", "")[:100]
            resumo_linhas.append(f"{role}: {texto}")
        resumo = "\n".join(resumo_linhas) if resumo_linhas else "Sem histórico"
        mensagem_atendente = f"""🔔 *TRANSFERÊNCIA DE ATENDIMENTO*

📱 *Cliente:* {phone}
⚠️ *Motivo:* {motivo}

📝 *Resumo:*
{resumo}

---
✅ Para assumir, responda ao cliente.
🤖 Cliente digitando *+* volta para IA."""
        await send_whatsapp_message(ATENDENTE_PHONE, mensagem_atendente)
        logger.info(f"✅ Notificação enviada: {phone}")
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao notificar: {e}")
        return False

async def detectar_solicitacao_humano(message: str) -> bool:
    palavras_chave = ["atendente", "humano", "pessoa", "falar com alguem", "operador", "atendimento humano"]
    return any(palavra in message.lower() for palavra in palavras_chave)

async def transferir_para_humano(phone: str, motivo: str):
    try:
        await db.conversas.update_many({"phone": phone}, {"$set": {"mode": "human", "transferred_at": datetime.now(), "transfer_reason": motivo}})
        await notificar_atendente(phone, motivo)
        await send_whatsapp_message(phone, "✅ Transferido para atendente humano.\n\n💡 Digite + para voltar à IA.")
        logger.info(f"✅ Transferido: {phone}")
        return True
    except Exception as e:
        logger.error(f"❌ Erro ao transferir: {e}")
        return False

app.include_router(admin_router)
app.include_router(training_router)
app.include_router(controle_router)

ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")

class Message(BaseModel):
    phone: str
    message: str
    timestamp: datetime = datetime.now()
    role: str = "user"
    message_type: str = "text"

# ============================================
# TREINAMENTO
# ============================================
async def get_bot_training() -> str:
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        if not bot:
            return "Você é a Mia, assistente da Legacy Translations. Responda profissionalmente."
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
        return "\n\n".join(prompt_parts)
    except Exception as e:
        logger.error(f"❌ Erro treinamento: {e}")
        return "Você é a Mia, assistente da Legacy Translations."

# ============================================
# ENVIAR MENSAGEM
# ============================================
async def send_whatsapp_message(phone: str, message: str):
    try:
        url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
        headers = {"Content-Type": "application/json", "Client-Token": ZAPI_CLIENT_TOKEN or ""}
        payload = {"phone": phone, "message": message}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                logger.info(f"✅ Mensagem enviada: {phone}")
                return True
            else:
                logger.error(f"❌ Erro envio: {response.status_code}")
                return False
    except Exception as e:
        logger.error(f"❌ Exceção: {e}")
        return False

# ============================================
# BAIXAR MÍDIA
# ============================================
async def download_media_from_zapi(media_url: str) -> Optional[bytes]:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(media_url)
            if response.status_code == 200:
                logger.info(f"✅ Mídia baixada ({len(response.content)} bytes)")
                return response.content
            return None
    except Exception as e:
        logger.error(f"❌ Erro download: {e}")
        return None

# ============================================
# PROCESSAR IMAGEM
# ============================================
async def process_image_with_vision(image_bytes: bytes, phone: str) -> str:
    try:
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        training_prompt = await get_bot_training()
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": f"{training_prompt}\n\n**ANÁLISE DE IMAGEM:**\n1. Tipo de documento\n2. Idioma\n3. Páginas\n4. Orçamento\n5. Prazo"},
                {"role": "user", "content": [
                    {"type": "text", "text": "Analise este documento."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]}
            ],
            max_tokens=800
        )
        analysis = response.choices[0].message.content
        await db.conversas.insert_one({"phone": phone, "message": "[IMAGEM]", "role": "user", "timestamp": datetime.now(), "canal": "WhatsApp", "type": "image"})
        await db.conversas.insert_one({"phone": phone, "message": analysis, "role": "assistant", "timestamp": datetime.now(), "canal": "WhatsApp"})
        return analysis
    except Exception as e:
        logger.error(f"❌ Vision: {e}")
        return "Desculpe, erro ao analisar imagem."

# ============================================
# PROCESSAR ÁUDIO
# ============================================
async def process_audio_with_whisper(audio_bytes: bytes, phone: str) -> Optional[str]:
    try:
        temp_file = BytesIO(audio_bytes)
        temp_file.name = "audio.ogg"
        transcription = openai_client.audio.transcriptions.create(model="whisper-1", file=temp_file, language="pt")
        transcribed_text = transcription.text
        await db.conversas.insert_one({"phone": phone, "message": f"[ÁUDIO] {transcribed_text}", "role": "user", "timestamp": datetime.now(), "canal": "WhatsApp", "type": "audio"})
        logger.info(f"✅ Áudio transcrito")
        return transcribed_text
    except Exception as e:
        logger.error(f"❌ Whisper: {e}")
        return None

# ============================================
# PROCESSAR PDF (NOVO!)
# ============================================
async def process_pdf_with_vision(pdf_bytes: bytes, phone: str) -> str:
    try:
        logger.info(f"📄 Processando PDF ({len(pdf_bytes)} bytes)")
        pdf_file = BytesIO(pdf_bytes)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text_content = []
        num_pages = len(pdf_reader.pages)
        
        for page_num in range(min(num_pages, 5)):
            page = pdf_reader.pages[page_num]
            text = page.extract_text()
            if text.strip():
                text_content.append(text)
        
        if text_content:
            full_text = "\n\n".join(text_content)
            training_prompt = await get_bot_training()
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"{training_prompt}\n\n**ANÁLISE PDF:**\n1. Tipo\n2. Idioma\n3. Páginas: {num_pages}\n4. Orçamento\n5. Prazo"},
                    {"role": "user", "content": f"Analise este PDF.\n\nConteúdo:\n{full_text[:3000]}"}
                ],
                max_tokens=800
            )
            analysis = response.choices[0].message.content
            await db.conversas.insert_one({"phone": phone, "message": f"[PDF - {num_pages} pgs]", "role": "user", "timestamp": datetime.now(), "canal": "WhatsApp", "type": "pdf"})
            await db.conversas.insert_one({"phone": phone, "message": analysis, "role": "assistant", "timestamp": datetime.now(), "canal": "WhatsApp"})
            logger.info(f"✅ PDF processado ({num_pages} páginas)")
            return analysis
        
        return "📄 PDF recebido!\n\nPara orçamento:\n1. Quantas páginas?\n2. Idioma de origem?\n3. Idioma de destino?\n\nOu envie fotos! 📸"
    except Exception as e:
        logger.error(f"❌ PDF: {e}")
        return "Desculpe, erro ao processar PDF. Pode enviar fotos das páginas?"

# ============================================
# CONTEXTO
# ============================================
async def get_conversation_context(phone: str, limit: int = 10) -> List[Dict]:
    try:
        messages = await db.conversas.find({"phone": phone}).sort("timestamp", -1).limit(limit).to_list(length=limit)
        messages.reverse()
        return [{"role": msg["role"], "content": msg["message"]} for msg in messages]
    except Exception as e:
        return []

# ============================================
# PROCESSAR COM IA
# ============================================
async def process_message_with_ai(phone: str, message: str) -> str:
    try:
        if await detectar_solicitacao_humano(message):
            await transferir_para_humano(phone, "Cliente solicitou")
            return None
        system_prompt = await get_bot_training()
        context = await get_conversation_context(phone)
        messages = [{"role": "system", "content": system_prompt}] + context + [{"role": "user", "content": message}]
        response = openai_client.chat.completions.create(model="gpt-4o", messages=messages, max_tokens=500, temperature=0.7)
        reply = response.choices[0].message.content
        await db.conversas.insert_one({"phone": phone, "message": message, "role": "user", "timestamp": datetime.now(), "canal": "WhatsApp"})
        await db.conversas.insert_one({"phone": phone, "message": reply, "role": "assistant", "timestamp": datetime.now(), "canal": "WhatsApp"})
        return reply
    except Exception as e:
        logger.error(f"❌ IA: {e}")
        return "Desculpe, erro. Pode repetir?"

# ============================================
# API ROUTES
# ============================================
@app.get("/admin/api/bot/status")
async def api_bot_status():
    status = await get_bot_status()
    ia_ativa = await db.conversas.distinct("phone", {"mode": {"$ne": "human"}})
    humano = await db.conversas.distinct("phone", {"mode": "human"})
    return {"enabled": status["enabled"], "last_update": status["last_update"].isoformat(), "stats": {"ia_ativa": len(ia_ativa), "atendimento_humano": len(humano), "ia_desligada": 0 if status["enabled"] else len(ia_ativa), "total": len(ia_ativa) + len(humano)}}

@app.post("/admin/api/bot/toggle")
async def api_bot_toggle(enabled: bool):
    success = await set_bot_status(enabled)
    if success:
        return {"success": True, "enabled": enabled, "message": f"Bot {'ATIVADO' if enabled else 'DESATIVADO'}"}
    raise HTTPException(status_code=500, detail="Erro")

@app.get("/admin/api/stats")
async def get_dashboard_stats(request: Request):
    username = check_admin_access(request)
    return {"receita_total": 150000.00, "novos_leads": 42, "taxa_conversao": 35, "atividades": [{"tipo": "NEW LEAD", "descricao": "Tech Solutions entered", "data": "11/21/2025 2:30 PM", "status": "new"}]}

@app.get("/admin/api/control-stats")
async def get_control_stats(request: Request):
    username = get_current_user(request)
    return {"ai_active_minutes": 1250, "human_service_minutes": 180, "ai_disabled_minutes": 45, "total_minutes": 1475, "conversations": []}

@app.post("/admin/bot/start")
async def start_bot(request: Request):
    username = check_admin_access(request)
    success = await set_bot_status(True)
    return {"success": success, "message": "Bot started"}

@app.post("/admin/bot/stop")
async def stop_bot(request: Request):
    username = check_admin_access(request)
    success = await set_bot_status(False)
    return {"success": success, "message": "Bot stopped"}

@app.post("/admin/knowledge/add")
async def add_knowledge(request: Request, category: str = Form(...), title: str = Form(...), content: str = Form(...)):
    username = get_current_user(request)
    await db.knowledge.insert_one({"category": category, "title": title, "content": content, "created_by": username, "created_at": datetime.now()})
    return RedirectResponse(url="/admin/training", status_code=303)

@app.delete("/admin/knowledge/delete/{knowledge_id}")
async def delete_knowledge(knowledge_id: str, request: Request):
    username = check_admin_access(request)
    from bson import ObjectId
    result = await db.knowledge.delete_one({"_id": ObjectId(knowledge_id)})
    if result.deleted_count == 1:
        return {"success": True}
    raise HTTPException(status_code=404, detail="Not found")

@app.post("/admin/faq/add")
async def add_faq(request: Request, question: str = Form(...), answer: str = Form(...)):
    username = get_current_user(request)
    await db.faqs.insert_one({"question": question, "answer": answer, "created_by": username, "created_at": datetime.now()})
    return RedirectResponse(url="/admin/training", status_code=303)

@app.delete("/admin/faq/delete/{faq_id}")
async def delete_faq(faq_id: str, request: Request):
    username = check_admin_access(request)
    from bson import ObjectId
    result = await db.faqs.delete_one({"_id": ObjectId(faq_id)})
    if result.deleted_count == 1:
        return {"success": True}
    raise HTTPException(status_code=404, detail="Not found")

# ============================================
# WEBHOOK
# ============================================
@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    try:
        data = await request.json()
        bot_status = await get_bot_status()
        phone = data.get("phone", "")
        conversa = await db.conversas.find_one({"phone": phone}, sort=[("timestamp", -1)])
        modo_humano = conversa and conversa.get("mode") == "human"
        
        if not bot_status["enabled"] or modo_humano:
            await db.conversas.insert_one({"phone": phone, "message": data.get("text", {}).get("message", "[MSG]"), "timestamp": datetime.now(), "role": "user", "type": "text", "mode": "human" if modo_humano else "disabled", "canal": "WhatsApp"})
            return {"status": "received", "processed": False}
        
        message_text = ""
        if "text" in data and "message" in data["text"]:
            message_text = data["text"]["message"].strip()
        
        if message_text == "*":
            await transferir_para_humano(phone, "Cliente digitou *")
            return {"status": "transferred"}
        if message_text == "+":
            await db.conversas.update_many({"phone": phone}, {"$set": {"mode": "ia", "returned_at": datetime.now()}, "$unset": {"transfer_reason": "", "transferred_at": ""}})
            await send_whatsapp_message(phone, "✅ Voltou para IA. Como posso ajudar?")
            return {"status": "returned_to_ia"}
        if message_text == "##":
            await db.conversas.update_many({"phone": phone}, {"$set": {"mode": "disabled", "disabled_at": datetime.now()}})
            await send_whatsapp_message(phone, "⏸️ IA desligada. Digite ++ para religar.")
            return {"status": "ia_disabled"}
        if message_text == "++":
            await db.conversas.update_many({"phone": phone}, {"$set": {"mode": "ia", "enabled_at": datetime.now()}})
            await send_whatsapp_message(phone, "✅ IA religada!")
            return {"status": "ia_enabled"}
        
        is_group = data.get("isGroup", False)
        if is_group:
            return JSONResponse({"status": "ignored", "reason": "group"})
        
        message_type = "text"
        if "image" in data and data.get("image"):
            message_type = "image"
        elif "audio" in data and data.get("audio"):
            message_type = "audio"
        elif "document" in data and data.get("document"):
            message_type = "document"
        elif "text" in data and data.get("text"):
            message_type = "text"
        
        if not phone:
            return JSONResponse({"status": "ignored", "reason": "no phone"})
        
        if message_type == "text":
            text = data.get("text", {}).get("message", "")
            if not text:
                return JSONResponse({"status": "ignored"})
            reply = await process_message_with_ai(phone, text)
            if reply:
                await send_whatsapp_message(phone, reply)
            return JSONResponse({"status": "processed", "type": "text"})
        
        elif message_type == "image":
            image_url = data.get("image", {}).get("imageUrl", "")
            if not image_url:
                return JSONResponse({"status": "ignored"})
            image_bytes = await download_media_from_zapi(image_url)
            if not image_bytes:
                await send_whatsapp_message(phone, "Erro ao baixar imagem. Tente novamente.")
                return JSONResponse({"status": "error"})
            analysis = await process_image_with_vision(image_bytes, phone)
            await send_whatsapp_message(phone, analysis)
            return JSONResponse({"status": "processed", "type": "image"})
        
        elif message_type == "audio":
            audio_url = data.get("audio", {}).get("audioUrl", "")
            if not audio_url:
                return JSONResponse({"status": "ignored"})
            audio_bytes = await download_media_from_zapi(audio_url)
            if not audio_bytes:
                await send_whatsapp_message(phone, "Erro ao baixar áudio.")
                return JSONResponse({"status": "error"})
            transcription = await process_audio_with_whisper(audio_bytes, phone)
            if not transcription:
                await send_whatsapp_message(phone, "Não entendi o áudio.")
                return JSONResponse({"status": "error"})
            reply = await process_message_with_ai(phone, transcription)
            if reply:
                await send_whatsapp_message(phone, reply)
            return JSONResponse({"status": "processed", "type": "audio"})
        
        elif message_type == "document":
            document_url = data.get("document", {}).get("documentUrl", "")
            mime_type = data.get("document", {}).get("mimeType", "")
            filename = data.get("document", {}).get("fileName", "")
            if not document_url:
                return JSONResponse({"status": "ignored"})
            if "pdf" not in mime_type.lower() and not filename.lower().endswith('.pdf'):
                await send_whatsapp_message(phone, "Só aceito PDF. Envie em PDF ou fotos.")
                return JSONResponse({"status": "ignored"})
            pdf_bytes = await download_media_from_zapi(document_url)
            if not pdf_bytes:
                await send_whatsapp_message(phone, "Erro ao baixar PDF.")
                return JSONResponse({"status": "error"})
            analysis = await process_pdf_with_vision(pdf_bytes, phone)
            await send_whatsapp_message(phone, analysis)
            return JSONResponse({"status": "processed", "type": "pdf"})
        
        return JSONResponse({"status": "ignored"})
    except Exception as e:
        logger.error(f"❌ Webhook: {e}")
        return JSONResponse({"status": "error"}, status_code=500)

# ============================================
# ROTAS
# ============================================
@app.get("/", response_class=HTMLResponse)
async def show_login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def handle_login(request: Request, username: str = Form(...), password: str = Form(...)):
    valid_credentials = {"admin": "admin123", "legacy": "legacy2025"}
    if username in valid_credentials and valid_credentials[username] == password:
        request.session['username'] = username
        request.session['user_role'] = 'admin' if username.lower() == 'admin' else 'legacy'
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/admin/dashboard")
async def admin_dashboard(request: Request):
    username = get_current_user(request)
    knowledge_count = await db.knowledge.count_documents({})
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "session": request.session, "username": username, "knowledge_count": knowledge_count})

@app.get("/admin/training")
async def admin_training(request: Request):
    username = get_current_user(request)
    knowledge_items = await db.knowledge.find().to_list(length=100)
    faq_items = await db.faqs.find().to_list(length=100)
    return templates.TemplateResponse("admin_training.html", {"request": request, "session": request.session, "username": username, "knowledge_items": knowledge_items, "faq_items": faq_items})

@app.get("/admin/control")
async def admin_control(request: Request):
    username = get_current_user(request)
    return templates.TemplateResponse("admin_control.html", {"request": request, "session": request.session, "username": username})

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
