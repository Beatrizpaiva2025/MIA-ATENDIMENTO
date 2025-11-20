from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
import os
import logging

logger = logging.getLogger("admin_routes")

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# MongoDB
MONGO_URI = os.getenv("MONGO_URI")
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["whatsapp_ai"]
conversations_collection = db["conversations"]
messages_collection = db["messages"]

# ============================================================
# PÁGINA PRINCIPAL DO ADMIN
# ============================================================
@router.get("/", response_class=HTMLResponse)
@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

# ============================================================
# API: DADOS DO DASHBOARD
# ============================================================
@router.get("/api/dashboard-data")
async def get_dashboard_data():
    try:
        # Total de conversas
        total_conversations = conversations_collection.count_documents({})
        
        # Conversas ativas (últimas 24h)
        yesterday = datetime.utcnow() - timedelta(days=1)
        active_conversations = conversations_collection.count_documents({
            "updated_at": {"$gte": yesterday}
        })
        
        # Total de mensagens
        total_messages = messages_collection.count_documents({})
        
        # Mensagens hoje
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        messages_today = messages_collection.count_documents({
            "timestamp": {"$gte": today_start}
        })
        
        # Conversas em modo IA vs Humano
        ai_mode = conversations_collection.count_documents({"mode": "ai"})
        human_mode = conversations_collection.count_documents({"mode": "human"})
        
        return JSONResponse({
            "total_conversations": total_conversations,
            "active_conversations": active_conversations,
            "total_messages": total_messages,
            "messages_today": messages_today,
            "ai_mode": ai_mode,
            "human_mode": human_mode
        })
    
    except Exception as e:
        logger.error(f"Erro ao buscar dados do dashboard: {e}")
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )

# ============================================================
# API: LISTAR CONVERSAS
# ============================================================
@router.get("/api/conversations")
async def get_conversations(skip: int = 0, limit: int = 50):
    try:
        conversations = await conversations_collection.find().sort(
            "updated_at", -1
        ).skip(skip).limit(limit).to_list(length=limit)
        
        # Converter ObjectId para string
        for conv in conversations:
            conv["_id"] = str(conv["_id"])
            if "created_at" in conv:
                conv["created_at"] = conv["created_at"].isoformat()
            if "updated_at" in conv:
                conv["updated_at"] = conv["updated_at"].isoformat()
        
        return JSONResponse(conversations)
    
    except Exception as e:
        logger.error(f"Erro ao listar conversas: {e}")
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )

# ============================================================
# API: DETALHES DE UMA CONVERSA
# ============================================================
@router.get("/api/conversations/{phone}")
async def get_conversation_details(phone: str):
    try:
        # Buscar conversa
        conversation = await conversations_collection.find_one({"phone": phone})
        
        if not conversation:
            return JSONResponse(
                {"error": "Conversa não encontrada"},
                status_code=404
            )
        
        # Buscar mensagens
        messages = await messages_collection.find(
            {"phone": phone}
        ).sort("timestamp", 1).to_list(length=1000)
        
        # Converter para JSON
        conversation["_id"] = str(conversation["_id"])
        if "created_at" in conversation:
            conversation["created_at"] = conversation["created_at"].isoformat()
        if "updated_at" in conversation:
            conversation["updated_at"] = conversation["updated_at"].isoformat()
        
        for msg in messages:
            msg["_id"] = str(msg["_id"])
            if "timestamp" in msg:
                msg["timestamp"] = msg["timestamp"].isoformat()
        
        return JSONResponse({
            "conversation": conversation,
            "messages": messages
        })
    
    except Exception as e:
        logger.error(f"Erro ao buscar detalhes da conversa: {e}")
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )

# ============================================================
# API: ALTERNAR MODO (IA <-> HUMANO)
# ============================================================
@router.post("/api/conversations/{phone}/toggle-mode")
async def toggle_conversation_mode(phone: str):
    try:
        conversation = await conversations_collection.find_one({"phone": phone})
        
        if not conversation:
            return JSONResponse(
                {"error": "Conversa não encontrada"},
                status_code=404
            )
        
        current_mode = conversation.get("mode", "ai")
        new_mode = "human" if current_mode == "ai" else "ai"
        
        await conversations_collection.update_one(
            {"phone": phone},
            {
                "$set": {
                    "mode": new_mode,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return JSONResponse({
            "phone": phone,
            "old_mode": current_mode,
            "new_mode": new_mode
        })
    
    except Exception as e:
        logger.error(f"Erro ao alternar modo: {e}")
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )

# ============================================================
# API: ENVIAR MENSAGEM MANUAL
# ============================================================
@router.post("/api/conversations/{phone}/send-message")
async def send_manual_message(phone: str, request: Request):
    try:
        data = await request.json()
        message_content = data.get("message")
        
        if not message_content:
            return JSONResponse(
                {"error": "Mensagem vazia"},
                status_code=400
            )
        
        # Salvar mensagem no banco
        message = {
            "phone": phone,
            "role": "assistant",
            "content": message_content,
            "type": "text",
            "timestamp": datetime.utcnow(),
            "manual": True
        }
        await messages_collection.insert_one(message)
        
        # Enviar via Z-API
        import httpx
        ZAPI_INSTANCE = os.getenv("ZAPI_INSTANCE")
        ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
        ZAPI_CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN")
        
        url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE}/token/{ZAPI_TOKEN}/send-text"
        
        headers = {
            "Content-Type": "application/json",
            "Client-Token": ZAPI_CLIENT_TOKEN
        }
        
        payload = {
            "phone": phone,
            "message": message_content
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Erro ao enviar mensagem manual: {response.text}")
                return JSONResponse(
                    {"error": f"Erro Z-API: {response.text}"},
                    status_code=500
                )
        
        return JSONResponse({
            "status": "success",
            "phone": phone,
            "message": message_content
        })
    
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem manual: {e}")
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )
