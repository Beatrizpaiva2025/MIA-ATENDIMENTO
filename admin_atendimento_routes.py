from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
import httpx
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
client = AsyncIOMotorClient(MONGODB_URI)
db = client.mia_database

# Z-API
ZAPI_INSTANCE = os.getenv("ZAPI_INSTANCE_ID")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN")
ZAPI_URL = f"https://api.z-api.io/instances/{ZAPI_INSTANCE}/token/{ZAPI_TOKEN}"


@router.get("/admin/atendimento", response_class=HTMLResponse)
async def admin_atendimento_page(request: Request):
    """Página de atendimento humano - conversas aguardando resposta"""
    try:
        # Buscar conversas em modo human
        pipeline = [
            {
                "$match": {
                    "$or": [
                        {"mode": "human"},
                        {"transferred_at": {"$exists": True}}
                    ]
                }
            },
            {
                "$sort": {"timestamp": -1}
            },
            {
                "$group": {
                    "_id": "$phone",
                    "last_message": {"$first": "$message"},
                    "last_timestamp": {"$first": "$timestamp"},
                    "message_count": {"$sum": 1},
                    "transferred_at": {"$first": "$transferred_at"},
                    "transfer_reason": {"$first": "$transfer_reason"}
                }
            },
            {
                "$sort": {"transferred_at": -1}
            }
        ]
        
        conversas_human = await db.conversas.aggregate(pipeline).to_list(length=100)
        
        return templates.TemplateResponse("admin_atendimento.html", {
            "request": request,
            "conversas": conversas_human,
            "total": len(conversas_human)
        })
        
    except Exception as e:
        print(f"Erro ao carregar atendimento: {e}")
        return templates.TemplateResponse("admin_atendimento.html", {
            "request": request,
            "conversas": [],
            "total": 0,
            "error": str(e)
        })


@router.get("/admin/atendimento/{phone}", response_class=HTMLResponse)
async def admin_atendimento_chat(request: Request, phone: str):
    """Chat de atendimento - ver histórico e responder"""
    try:
        # Buscar todas as mensagens
        messages = await db.conversas.find(
            {"phone": phone}
        ).sort("timestamp", 1).to_list(length=1000)
        
        return templates.TemplateResponse("admin_atendimento_chat.html", {
            "request": request,
            "phone": phone,
            "messages": messages,
            "total": len(messages)
        })
        
    except Exception as e:
        print(f"Erro ao carregar chat: {e}")
        return templates.TemplateResponse("admin_atendimento_chat.html", {
            "request": request,
            "phone": phone,
            "messages": [],
            "total": 0,
            "error": str(e)
        })


@router.post("/admin/atendimento/send")
async def send_message_to_client(phone: str = Form(...), message: str = Form(...)):
    """Enviar mensagem para cliente via admin"""
    try:
        # Enviar via Z-API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ZAPI_URL}/send-text",
                json={
                    "phone": phone,
                    "message": message
                },
                timeout=30.0
            )
        
        # Salvar no MongoDB
        await db.conversas.insert_one({
            "phone": phone,
            "message": message,
            "role": "assistant",
            "mode": "human",
            "timestamp": datetime.now(),
            "sent_by": "admin_panel"
        })
        
        return JSONResponse({"status": "success", "message": "Mensagem enviada"})
        
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@router.post("/admin/atendimento/return-to-ia/{phone}")
async def return_to_ia(phone: str):
    """Devolver conversa para IA"""
    try:
        # Atualizar modo para IA
        await db.conversas.update_many(
            {"phone": phone},
            {
                "$set": {
                    "mode": "ia",
                    "returned_at": datetime.now(),
                    "returned_by": "admin_panel"
                },
                "$unset": {
                    "transfer_reason": "",
                    "transferred_at": ""
                }
            }
        )
        
        # Enviar mensagem automática para o cliente
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{ZAPI_URL}/send-text",
                json={
                    "phone": phone,
                    "message": "✅ Você está de volta ao atendimento automático! Como posso ajudar?"
                },
                timeout=30.0
            )
        
        return JSONResponse({"status": "success", "message": "Conversa devolvida para IA"})
        
    except Exception as e:
        print(f"Erro ao devolver para IA: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@router.get("/admin/atendimento/messages/{phone}")
async def get_messages(phone: str):
    """API para buscar mensagens (atualização em tempo real)"""
    try:
        messages = await db.conversas.find(
            {"phone": phone}
        ).sort("timestamp", 1).to_list(length=1000)
        
        # Converter ObjectId para string
        for msg in messages:
            msg["_id"] = str(msg["_id"])
            if "timestamp" in msg:
                msg["timestamp"] = msg["timestamp"].isoformat()
        
        return JSONResponse({"status": "success", "messages": messages})
        
    except Exception as e:
        print(f"Erro ao buscar mensagens: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
