"""
admin_conversas_routes.py - VERSÃO FINAL CORRIGIDA
Dados reais, cálculos precisos, gestão de leads
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
from bson import ObjectId
import os
import logging
import traceback
from timezone_utils import format_datetime_est, format_time_est, format_date_est, utc_to_est

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
client = AsyncIOMotorClient(MONGODB_URI)
db = client.mia_database


def extrair_valor(conversao_doc):
    """Extrai valor de forma flexível"""
    valor = conversao_doc.get("valor") or conversao_doc.get("value") or 0
    if isinstance(valor, str):
        try:
            valor = valor.replace("$", "").replace("R$", "").replace(",", "").strip()
            valor = float(valor)
        except:
            valor = 0
    return float(valor) if valor else 0.0


@router.get("/admin/conversas", response_class=HTMLResponse)
async def admin_conversas_page(request: Request):
    """Página principal"""
    try:
        return templates.TemplateResponse("admin_conversas.html", {
            "request": request
        })
    except Exception as e:
        logger.error(f"Erro ao carregar página: {e}")
        return templates.TemplateResponse("admin_conversas.html", {
            "request": request,
            "error": str(e)
        })


@router.get("/admin/conversas/api/stats")
async def api_get_stats(periodo: str = "15"):
    """Retorna estatísticas completas com cálculos reais"""
    try:
        dias = int(periodo)
        data_inicio = datetime.now() - timedelta(days=dias)

        conversoes_docs = await db.conversoes.find({
            "timestamp": {"$gte": data_inicio}
        }).to_list(1000)
        
        total_conversoes = len(conversoes_docs)
        valor_total = sum(extrair_valor(doc) for doc in conversoes_docs)

        clientes_unicos = await db.conversas.distinct("phone", {
            "timestamp": {"$gte": data_inicio}
        })
        total_clientes = len(clientes_unicos)

        taxa_conversao = (total_conversoes / total_clientes * 100) if total_clientes > 0 else 0

        conversas_ia = await db.conversas.find({
            "timestamp": {"$gte": data_inicio},
            "role": "assistant"
        }).to_list(10000)
        
        tempo_ia_minutos = len(conversas_ia) * 2

        conversas_humano = await db.conversas.find({
            "timestamp": {"$gte": data_inicio},
            "mode": "human"
        }).to_list(10000)
        
        tempo_humano_minutos = len(conversas_humano) * 5

        leads_nao_convertidos = await db.leads_followup.count_documents({
            "status": {"$ne": "converted"}
        })

        if leads_nao_convertidos == 0:
            clientes_convertidos = [doc.get("phone") for doc in conversoes_docs]
            leads_nao_convertidos = len([c for c in clientes_unicos if c not in clientes_convertidos])

        return {
            "valor_total": round(valor_total, 2),
            "total_conversoes": total_conversoes,
            "taxa_conversao": round(taxa_conversao, 1),
            "leads_followup": leads_nao_convertidos,
            "conversoes": total_conversoes,
            "clientes_unicos": total_clientes,
            "tempo_ia_minutos": tempo_ia_minutos,
            "tempo_humano_minutos": tempo_humano_minutos,
            "taxa_conversao_stat": round(taxa_conversao, 1)
        }
    except Exception as e:
        logger.error(f"Erro ao buscar stats: {e}")
        logger.error(traceback.format_exc())
        return {
            "error": str(e),
            "valor_total": 0,
            "total_conversoes": 0,
            "taxa_conversao": 0,
            "leads_followup": 0,
            "conversoes": 0,
            "clientes_unicos": 0,
            "tempo_ia_minutos": 0,
            "tempo_humano_minutos": 0,
            "taxa_conversao_stat": 0
        }


@router.get("/admin/conversas/api/chart-data")
async def api_get_chart_data(periodo: str = "15"):
    """Dados para gráficos"""
    try:
        dias = int(periodo)
        data_inicio = datetime.now() - timedelta(days=dias)

        conversoes_docs = await db.conversoes.find({
            "timestamp": {"$gte": data_inicio}
        }).to_list(1000)
        
        conversoes_por_dia = {}
        for doc in conversoes_docs:
            if doc.get("timestamp"):
                data = format_date_est(doc["timestamp"], "%Y-%m-%d")
                if data not in conversoes_por_dia:
                    conversoes_por_dia[data] = {"total": 0, "valor": 0}
                conversoes_por_dia[data]["total"] += 1
                conversoes_por_dia[data]["valor"] += extrair_valor(doc)

        pipeline_ia = [
            {"$match": {"timestamp": {"$gte": data_inicio}, "role": "assistant"}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "total": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        atendimentos_ia = await db.conversas.aggregate(pipeline_ia).to_list(100)

        pipeline_humano = [
            {"$match": {"timestamp": {"$gte": data_inicio}, "mode": "human"}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "total": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        atendimentos_humano = await db.conversas.aggregate(pipeline_humano).to_list(100)

        labels = []
        conversoes_data = []
        valores_data = []
        ia_data = []
        humano_data = []

        for i in range(dias):
            data = format_date_est(datetime.utcnow() - timedelta(days=dias-1-i), "%Y-%m-%d")
            labels.append(data)

            conv = conversoes_por_dia.get(data, {"total": 0, "valor": 0})
            conversoes_data.append(conv["total"])
            valores_data.append(round(conv["valor"], 2))

            ia = next((a for a in atendimentos_ia if a["_id"] == data), None)
            ia_data.append(ia["total"] if ia else 0)

            hum = next((h for h in atendimentos_humano if h["_id"] == data), None)
            humano_data.append(hum["total"] if hum else 0)

        return {
            "labels": labels,
            "conversoes": conversoes_data,
            "valores": valores_data,
            "atendimentos_ia": ia_data,
            "atendimentos_humano": humano_data
        }
    except Exception as e:
        logger.error(f"Erro chart data: {e}")
        return {
            "error": str(e),
            "labels": [],
            "conversoes": [],
            "valores": [],
            "atendimentos_ia": [],
            "atendimentos_humano": []
        }


@router.get("/admin/conversas/api/conversoes")
async def api_get_conversoes(periodo: str = "30"):
    """Lista de conversões"""
    try:
        dias = int(periodo)
        data_inicio = datetime.now() - timedelta(days=dias)

        conversoes = await db.conversoes.find({
            "timestamp": {"$gte": data_inicio}
        }).sort("timestamp", -1).limit(50).to_list(50)

        result = []
        for c in conversoes:
            try:
                phone = c.get("phone", "N/A")
                
                primeira_msg = await db.conversas.find_one(
                    {"phone": phone},
                    sort=[("timestamp", 1)]
                )

                tempo_atendimento = "N/A"
                if primeira_msg and primeira_msg.get("timestamp") and c.get("timestamp"):
                    delta = c["timestamp"] - primeira_msg["timestamp"]
                    horas = delta.total_seconds() / 3600
                    if horas < 1:
                        tempo_atendimento = f"{int(delta.total_seconds() / 60)}min"
                    elif horas < 24:
                        tempo_atendimento = f"{int(horas)}h"
                    else:
                        tempo_atendimento = f"{int(horas/24)}d"

                teve_humano = await db.conversas.find_one({
                    "phone": phone,
                    "mode": "human"
                })

                result.append({
                    "phone": phone,
                    "valor": extrair_valor(c),
                    "timestamp": format_datetime_est(c.get("timestamp"), "%m/%d/%Y %H:%M"),
                    "tempo_atendimento": tempo_atendimento,
                    "tipo_atendimento": "Human + AI" if teve_humano else "AI Only",
                    "metodo": c.get("detection_method", "manual"),
                    "mensagem": c.get("message", "")[:50]
                })
            except Exception as item_error:
                logger.error(f"Erro conversão: {item_error}")
                continue

        return {"conversoes": result}
    except Exception as e:
        logger.error(f"Erro conversões: {e}")
        return {"conversoes": [], "error": str(e)}


@router.get("/admin/conversas/api/leads-followup")
async def api_get_leads_followup():
    """Leads cadastrados para follow-up"""
    try:
        leads = await db.leads_followup.find({}).sort("created_at", -1).to_list(100)

        result = []
        for lead in leads:
            try:
                phone = lead.get("phone", "N/A")
                
                last_contact = lead.get("last_contact_date")
                if last_contact and isinstance(last_contact, datetime):
                    dias_sem_contato = (datetime.utcnow() - last_contact).days
                    last_contact_str = format_date_est(last_contact, "%m/%d/%Y")
                else:
                    dias_sem_contato = 0
                    last_contact_str = "N/A"

                total_msgs = await db.conversas.count_documents({"phone": phone})

                result.append({
                    "id": str(lead.get("_id")),
                    "phone": phone,
                    "last_contact": last_contact_str,
                    "dias_sem_contato": dias_sem_contato,
                    "total_msgs": total_msgs,
                    "asked_quote": "Yes" if lead.get("asked_quote") else "No",
                    "priority": lead.get("priority", "Low"),
                    "status": lead.get("status", "pending"),
                    "notes": lead.get("notes", "")
                })
            except Exception as item_error:
                logger.error(f"Erro lead: {item_error}")
                continue

        return {"leads": result, "total": len(result)}
    except Exception as e:
        logger.error(f"Erro leads: {e}")
        return {"leads": [], "total": 0, "error": str(e)}


@router.post("/admin/conversas/api/add-lead")
async def api_add_lead(request: Request):
    """Adiciona lead para follow-up"""
    try:
        data = await request.json()

        phone = data.get("phone", "").strip()
        if not phone:
            return {"success": False, "error": "Phone required"}

        existe = await db.leads_followup.find_one({"phone": phone})
        if existe:
            return {"success": False, "error": "Lead already exists"}

        lead = {
            "phone": phone,
            "last_contact_date": datetime.now(),
            "asked_quote": data.get("asked_quote", False),
            "priority": data.get("priority", "Medium"),
            "status": data.get("status", "pending"),
            "notes": data.get("notes", ""),
            "created_at": datetime.now(),
            "created_by": "admin"
        }

        result = await db.leads_followup.insert_one(lead)
        logger.info(f"✅ Lead adicionado: {phone}")

        return {"success": True, "message": "Lead added", "id": str(result.inserted_id)}
    except Exception as e:
        logger.error(f"❌ Erro add lead: {e}")
        return {"success": False, "error": str(e)}


@router.post("/admin/conversas/api/update-lead-status")
async def api_update_lead_status(request: Request):
    """Atualiza status (converted/no/pending)"""
    try:
        data = await request.json()

        lead_id = data.get("lead_id")
        status = data.get("status")

        if not lead_id or not status:
            return {"success": False, "error": "lead_id and status required"}

        if status not in ["converted", "no", "pending"]:
            return {"success": False, "error": "Invalid status"}

        result = await db.leads_followup.update_one(
            {"_id": ObjectId(lead_id)},
            {"$set": {"status": status, "updated_at": datetime.now()}}
        )

        if result.modified_count == 0:
            return {"success": False, "error": "Lead not found"}

        logger.info(f"✅ Status atualizado: {lead_id} -> {status}")

        return {"success": True, "message": "Status updated"}
    except Exception as e:
        logger.error(f"❌ Erro update status: {e}")
        return {"success": False, "error": str(e)}


@router.post("/admin/conversas/api/delete-lead/{lead_id}")
async def api_delete_lead(lead_id: str):
    """Deleta lead"""
    try:
        result = await db.leads_followup.delete_one({"_id": ObjectId(lead_id)})

        if result.deleted_count == 0:
            return {"success": False, "error": "Lead not found"}

        logger.info(f"✅ Lead deletado: {lead_id}")

        return {"success": True, "message": "Lead deleted"}
    except Exception as e:
        logger.error(f"❌ Erro delete lead: {e}")
        return {"success": False, "error": str(e)}


@router.post("/admin/conversas/api/registrar-conversao")
async def api_registrar_conversao(request: Request):
    """Registra conversão manual"""
    try:
        data = await request.json()

        phone = data.get("phone", "").strip()
        if not phone:
            return {"success": False, "error": "Phone required"}

        try:
            valor = float(data.get("valor", 0))
        except:
            return {"success": False, "error": "Invalid value"}

        if valor <= 0:
            return {"success": False, "error": "Value must be > 0"}

        conversao = {
            "phone": phone,
            "valor": valor,
            "value": valor,
            "timestamp": datetime.now(),
            "detection_method": "manual",
            "message": data.get("observacao", "Manual entry"),
            "canal": "WhatsApp",
            "registered_by": "admin"
        }

        result = await db.conversoes.insert_one(conversao)
        
        await db.leads_followup.update_one(
            {"phone": phone},
            {"$set": {"status": "converted", "converted_at": datetime.now()}}
        )
        
        logger.info(f"✅ Conversão: {phone} - ${valor}")

        return {"success": True, "message": "Conversion saved", "id": str(result.inserted_id)}
    except Exception as e:
        logger.error(f"❌ Erro conversão: {e}")
        return {"success": False, "error": str(e)}
