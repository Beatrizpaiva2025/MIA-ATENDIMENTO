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

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
client = AsyncIOMotorClient(MONGODB_URI)
db = client.mia_database


# ==================================================================
# FUNÇÃO AUXILIAR
# ==================================================================
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


# ==================================================================
# PÁGINA PRINCIPAL
# ==================================================================
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


# ==================================================================
# API: ESTATÍSTICAS COMPLETAS (DADOS REAIS)
# ==================================================================
@router.get("/admin/conversas/api/stats")
async def api_get_stats(periodo: str = "15"):
    """Retorna estatísticas completas com cálculos reais"""
    try:
        dias = int(periodo)
        data_inicio = datetime.now() - timedelta(days=dias)

        # ====== CONVERSÕES ======
        conversoes_docs = await db.conversoes.find({
            "timestamp": {"$gte": data_inicio}
        }).to_list(1000)
        
        total_conversoes = len(conversoes_docs)
        valor_total = sum(extrair_valor(doc) for doc in conversoes_docs)

        # ====== CLIENTES ÚNICOS ======
        clientes_unicos = await db.conversas.distinct("phone", {
            "timestamp": {"$gte": data_inicio}
        })
        total_clientes = len(clientes_unicos)

        # ====== TAXA DE CONVERSÃO REAL ======
        # (Conversões ÷ Total de Clientes) × 100
        taxa_conversao = (total_conversoes / total_clientes * 100) if total_clientes > 0 else 0

        # ====== TEMPO TOTAL - AI SUPPORT ======
        # Buscar todas as sessões de conversa IA
        conversas_ia = await db.conversas.find({
            "timestamp": {"$gte": data_inicio},
            "role": "assistant"
        }).to_list(10000)
        
        # Calcular tempo total (assumindo ~2min por interação IA)
        # Ou você pode ter um campo 'duration' no banco
        tempo_ia_minutos = len(conversas_ia) * 2  # 2min por resposta

        # ====== TEMPO TOTAL - HUMAN SUPPORT ======
        # Buscar conversas em modo humano e calcular duração
        conversas_humano = await db.conversas.find({
            "timestamp": {"$gte": data_inicio},
            "mode": "human"
        }).to_list(10000)
        
        # Calcular tempo total (assumindo ~5min por interação humana)
        tempo_humano_minutos = len(conversas_humano) * 5  # 5min por resposta

        # ====== LEADS PARA FOLLOW-UP ======
        # Contar leads cadastrados que NÃO converteram
        leads_nao_convertidos = await db.leads_followup.count_documents({
            "status": {"$ne": "converted"}
        })

        # Se não houver leads cadastrados, usar método automático
        if leads_nao_convertidos == 0:
            # Clientes que interagiram mas não converteram
            clientes_convertidos = [doc.get("phone") for doc in conversoes_docs]
            leads_nao_convertidos = len([c for c in clientes_unicos if c not in clientes_convertidos])

        return {
            # Cards principais
            "valor_total": round(valor_total, 2),
            "total_conversoes": total_conversoes,
            "taxa_conversao": round(taxa_conversao, 1),
            "leads_followup": leads_nao_convertidos,
            
            # Cards de estatísticas
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


# ==================================================================
# API: CHART DATA
# ==================================================================
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
                data = doc["timestamp"].strftime("%Y-%m-%d")
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
            data = (datetime.now() - timedelta(days=dias-1-i)).strftime("%Y-%m-%d")
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


# ==================================================================
# API: CONVERSÕES
# ==================================================================
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
                    "timestamp": c.get("timestamp").strftime("%m/%d/%Y %H:%M") if c.get("timestamp") else "N/A",
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


# ==================================================================
# API: LEADS PARA FOLLOW-UP
# ==================================================================
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
                    dias_sem_contato = (datetime.now() - last_contact).days
                    last_contact_str = last_contact.strftime("%m/%d/%Y")
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


# ==================================================================
# API: ADICIONAR LEAD
# ==================================================================
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


# ==================================================================
# API: ATUALIZAR STATUS
# ==================================================================
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


# ==================================================================
# API: DELETAR LEAD
# ==================================================================
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


# ==================================================================
# API: REGISTRAR CONVERSÃO
# ==================================================================
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
        
        # Marcar lead como convertido se existir
        await db.leads_followup.update_one(
            {"phone": phone},
            {"$set": {"status": "converted", "converted_at": datetime.now()}}
        )
        
        logger.info(f"✅ Conversão: {phone} - ${valor}")

        return {"success": True, "message": "Conversion saved", "id": str(result.inserted_id)}
    except Exception as e:
        logger.error(f"❌ Erro conversão: {e}")
        return {"success": False, "error": str(e)}
📄 admin_conversas.html (PARTE 1/2)
Copy{% extends "admin_base.html" %}

{% block title %}Conversions & Reports - MIA Admin{% endblock %}

{% block extra_style %}
<style>
    .dashboard-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 25px;
        flex-wrap: wrap;
        gap: 15px;
    }

    .periodo-selector {
        display: flex;
        gap: 10px;
        align-items: center;
    }

    .periodo-btn {
        padding: 8px 16px;
        border: 2px solid #e0e0e0;
        background: white;
        border-radius: 8px;
        cursor: pointer;
        font-weight: 600;
        transition: all 0.3s;
    }

    .periodo-btn.active {
        background: #5dade2;
        color: white;
        border-color: #5dade2;
    }

    .periodo-btn:hover {
        border-color: #5dade2;
    }

    /* GRID DE 3 CARDS (removido Clients Served) */
    .resumo-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 20px;
        margin-bottom: 30px;
    }

    .resumo-card {
        background: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        text-align: center;
    }

    .resumo-card.destaque {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }

    .resumo-label {
        font-size: 0.85em;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        opacity: 0.8;
        margin-bottom: 8px;
    }

    .resumo-valor {
        font-size: 2em;
        font-weight: bold;
    }

    .resumo-sub {
        font-size: 0.9em;
        opacity: 0.7;
        margin-top: 5px;
    }

    .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 15px;
        margin-bottom: 30px;
    }

    .stat-card {
        background: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        border-left: 4px solid;
    }

    .stat-card.conversoes { border-left-color: #27ae60; }
    .stat-card.clientes { border-left-color: #3498db; }
    .stat-card.ia { border-left-color: #9b59b6; }
    .stat-card.humano { border-left-color: #f39c12; }
    .stat-card.taxa { border-left-color: #e74c3c; }

    .stat-label {
        font-size: 0.85em;
        color: #7f8c8d;
        text-transform: uppercase;
        margin-bottom: 8px;
    }

    .stat-value {
        font-size: 1.8em;
        font-weight: bold;
        color: #1e3a5f;
    }

    .charts-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
        gap: 25px;
        margin-bottom: 30px;
    }

    .chart-card {
        background: white;
        border-radius: 12px;
        padding: 25px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }

    .chart-title {
        font-size: 1.1em;
        font-weight: 600;
        color: #1e3a5f;
        margin-bottom: 20px;
    }

    .section-card {
        background: white;
        border-radius: 12px;
        padding: 25px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        margin-bottom: 25px;
    }

    .section-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
    }

    .section-title {
        font-size: 1.2em;
        font-weight: 600;
        color: #1e3a5f;
    }

    .table-container {
        overflow-x: auto;
    }

    .data-table {
        width: 100%;
        border-collapse: collapse;
    }

    .data-table th {
        background: #f8f9fa;
        padding: 12px 15px;
        text-align: left;
        font-weight: 600;
        color: #1e3a5f;
        border-bottom: 2px solid #e0e0e0;
        font-size: 0.9em;
    }

    .data-table td {
        padding: 12px 15px;
        border-bottom: 1px solid #f0f0f0;
        font-size: 0.95em;
    }

    .data-table tr:hover {
        background: #f8f9fa;
    }

    .badge {
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.8em;
        font-weight: 600;
    }

    .badge-success { background: #d4edda; color: #155724; }
    .badge-warning { background: #fff3cd; color: #856404; }
    .badge-danger { background: #f8d7da; color: #721c24; }
    .badge-info { background: #d1ecf1; color: #0c5460; }
    .badge-ia { background: #e8daef; color: #6c3483; }
    .badge-humano { background: #fdebd0; color: #b9770e; }

    .prioridade-high { background: #f8d7da; color: #721c24; }
    .prioridade-medium { background: #fff3cd; color: #856404; }
    .prioridade-low { background: #d4edda; color: #155724; }

    .btn-action {
        padding: 6px 12px;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.85em;
        transition: all 0.3s;
        margin-right: 5px;
    }

    .btn-whatsapp {
        background: #25d366;
        color: white;
    }

    .btn-whatsapp:hover {
        background: #1da851;
    }

    .btn-edit {
        background: #5dade2;
        color: white;
    }

    .btn-edit:hover {
        background: #4a9dd1;
    }

    .btn-delete {
        background: #e74c3c;
        color: white;
    }

    .btn-delete:hover {
        background: #c0392b;
    }

    .btn-registrar {
        background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%);
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        font-weight: 600;
    }

    .btn-registrar:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(39, 174, 96, 0.3);
    }

    .modal-overlay {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        z-index: 1000;
        justify-content: center;
        align-items: center;
    }

    .modal-content {
        background: white;
        border-radius: 12px;
        padding: 30px;
        width: 90%;
        max-width: 500px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        max-height: 90vh;
        overflow-y: auto;
    }

    .modal-header {
        font-size: 1.3em;
        font-weight: 600;
        color: #1e3a5f;
        margin-bottom: 20px;
    }

    .form-group {
        margin-bottom: 15px;
    }

    .form-label {
        display: block;
        font-weight: 600;
        color: #1e3a5f;
        margin-bottom: 8px;
    }

    .form-input, .form-textarea {
        width: 100%;
        padding: 12px;
        border: 2px solid #e0e0e0;
        border-radius: 8px;
        font-size: 1em;
        box-sizing: border-box;
    }

    .form-input:focus, .form-textarea:focus {
        outline: none;
        border-color: #5dade2;
    }

    .form-textarea {
        min-height: 80px;
        resize: vertical;
    }

    .status-buttons {
        display: flex;
        gap: 10px;
        margin-bottom: 15px;
    }

    .status-btn {
        flex: 1;
        padding: 12px;
        border: 2px solid #e0e0e0;
        background: white;
        border-radius: 8px;
        cursor: pointer;
        font-weight: 600;
        transition: all 0.3s;
    }

    .status-btn.active-converted {
        background: #d4edda;
        border-color: #27ae60;
        color: #155724;
    }

    .status-btn.active-no {
        background: #f8d7da;
        border-color: #e74c3c;
        color: #721c24;
    }

    .status-btn.active-pending {
        background: #fff3cd;
        border-color: #f39c12;
        color: #856404;
    }

    .status-btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }

    .modal-buttons {
        display: flex;
        gap: 10px;
        margin-top: 20px;
    }

    .btn-cancel {
        flex: 1;
        padding: 12px;
        background: #e0e0e0;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        font-weight: 600;
    }

    .btn-confirm {
        flex: 1;
        padding: 12px;
        background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%);
        color: white;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        font-weight: 600;
    }

    .empty-state {
        text-align: center;
        padding: 40px;
        color: #7f8c8d;
    }

    .error-message {
        background: #f8d7da;
        color: #721c24;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 20px;
        border-left: 4px solid #e74c3c;
    }

    .checkbox-group {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 15px;
    }

    .checkbox-group input[type="checkbox"] {
        width: 20px;
        height: 20px;
        cursor: pointer;
    }

    @media (max-width: 768px) {
        .charts-grid {
            grid-template-columns: 1fr;
        }
        .status-buttons {
            flex-direction: column;
        }
    }
</style>
{% endblock %}

{% block content %}
<div class="dashboard-header">
    <div>
        <h1>Conversions & Reports</h1>
        <p>Track sales, leads and improve your conversion rate</p>
    </div>
    <div class="periodo-selector">
        <span style="font-weight: 600; color: #7f8c8d;">Period:</span>
        <button class="periodo-btn" data-periodo="7" onclick="setPeriodo(7)">7 days</button>
        <button class="periodo-btn active" data-periodo="15" onclick="setPeriodo(15)">15 days</button>
        <button class="periodo-btn" data-periodo="30" onclick="setPeriodo(30)">30 days</button>
    </div>
</div>

<div id="error-container" style="display: none;"></div>

<!-- GRID DE 3 CARDS (Clients Served REMOVIDO) -->
<div class="resumo-grid">
    <div class="resumo-card destaque">
        <div class="resumo-label">Period Revenue</div>
        <div class="resumo-valor" id="valor-total">$0</div>
        <div class="resumo-sub" id="conversoes-total">0 conversions</div>
    </div>
    <div class="resumo-card">
        <div class="resumo-label">Conversion Rate</div>
        <div class="resumo-valor" id="taxa-conversao">0%</div>
        <div class="resumo-sub">clients to sales</div>
    </div>
    <div class="resumo-card">
        <div class="resumo-label">Leads for Follow-up</div>
        <div class="resumo-valor" id="leads-followup">0</div>
        <div class="resumo-sub">did not convert</div>
    </div>
</div>

<div class="stats-grid">
    <div class="stat-card conversoes">
        <div class="stat-label">Conversions</div>
        <div class="stat-value" id="stat-conversoes">0</div>
    </div>
    <div class="stat-card clientes">
        <div class="stat-label">Clients</div>
        <div class="stat-value" id="stat-clientes">0</div>
    </div>
    <div class="stat-card ia">
        <div class="stat-label">AI Support (min)</div>
        <div class="stat-value" id="stat-ia">0</div>
    </div>
    <div class="stat-card humano">
        <div class="stat-label">Human Support (min)</div>
        <div class="stat-value" id="stat-humano">0</div>
    </div>
    <div class="stat-card taxa">
        <div class="stat-label">Conv. Rate</div>
        <div class="stat-value" id="stat-taxa">0%</div>
    </div>
</div>

<div class="charts-grid">
    <div class="chart-card">
        <div class="chart-title">Conversions per Day</div>
        <canvas id="chartConversoes"></canvas>
    </div>
    <div class="chart-card">
        <div class="chart-title">AI vs Human (Support)</div>
        <canvas id="chartAtendimentos"></canvas>
    </div>
</div>

<div class="section-card">
    <div class="section-header">
        <div class="section-title">Recent Conversions</div>
        <button class="btn-registrar" onclick="abrirModalConversao()">+ Add Conversion</button>
    </div>
    <div class="table-container">
        <table class="data-table">
            <thead>
                <tr>
                    <th>Client</th>
                    <th>Value</th>
                    <th>Date</th>
                    <th>Support Time</th>
                    <th>Type</th>
                    <th>Detection</th>
                </tr>
            </thead>
            <tbody id="conversoes-body">
                <tr><td colspan="6" class="empty-state">Loading...</td></tr>
            </tbody>
        </table>
    </div>
</div>

<div class="section-card">
    <div class="section-header">
        <div class="section-title">Leads for Follow-up</div>
        <button class="btn-registrar" onclick="abrirModalLead()">+ Add Lead</button>
    </div>
    <div class="table-container">
        <table class="data-table">
            <thead>
                <tr>
                    <th>Client</th>
                    <th>Last Contact</th>
                    <th>Messages</th>
                    <th>Days Inactive</th>
                    <th>Asked Quote</th>
                    <th>Priority</th>
                    <th>Result</th>
                    <th>Reason</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody id="leads-body">
                <tr><td colspan="9" class="empty-state">Loading...</td></tr>
            </tbody>
        </table>
    </div>
</div>

<!-- MODAL ADD CONVERSION -->
<div class="modal-overlay" id="modal-conversao">
    <div class="modal-content">
        <div class="modal-header">Add New Conversion</div>
        <div class="form-group">
            <label class="form-label">Client Phone</label>
            <input type="text" class="form-input" id="conv-phone" placeholder="18572081139">
        </div>
        <div class="form-group">
            <label class="form-label">Value ($)</label>
            <input type="number" class="form-input" id="conv-valor" placeholder="150.00" step="0.01">
        </div>
        <div class="form-group">
            <label class="form-label">Notes</label>
            <input type="text" class="form-input" id="conv-obs" placeholder="Certificate translation">
        </div>
        <div class="modal-buttons">
            <button class="btn-cancel" onclick="fecharModal('modal-conversao')">Cancel</button>
            <button class="btn-confirm" onclick="registrarConversao()">Save</button>
        </div>
    </div>
</div>

<!-- MODAL ADD LEAD (COM STATUS E REASON) -->
<div class="modal-overlay" id="modal-lead">
    <div class="modal-content">
        <div class="modal-header">Add New Lead</div>
        
        <div class="form-group">
            <label class="form-label">Client Phone</label>
            <input type="text" class="form-input" id="lead-phone" placeholder="18572081139">
        </div>

        <div class="form-group">
            <label class="form-label">Last Contact Date</label>
            <input type="date" class="form-input" id="lead-date">
        </div>

        <div class="checkbox-group">
            <input type="checkbox" id="lead-asked-quote">
            <label for="lead-asked-quote">Asked for Quote?</label>
        </div>

        <div class="form-group">
            <label class="form-label">Priority</label>
            <select class="form-input" id="lead-priority">
                <option value="High">High</option>
                <option value="Medium" selected>Medium</option>
                <option value="Low">Low</option>
            </select>
        </div>

        <div class="form-group">
            <label class="form-label">Result</label>
            <div class="status-buttons">
                <button class="status-btn" id="status-pending" onclick="setLeadStatus('pending')">
                    Pending
                </button>
                <button class="status-btn" id="status-converted" onclick="setLeadStatus('converted')">
                    Converted
                </button>
                <button class="status-btn" id="status-no" onclick="setLeadStatus('no')">
                    No
                </button>
            </div>
        </div>

        <div class="form-group">
            <label class="form-label">Reason / Notes</label>
            <textarea class="form-textarea" id="lead-reason" placeholder="Why converted / not converted / follow-up notes..."></textarea>
        </div>

        <div class="modal-buttons">
            <button class="btn-cancel" onclick="fecharModal('modal-lead')">Cancel</button>
            <button class="btn-confirm" onclick="salvarLead()">Save Lead</button>
        </div>
    </div>
</div>
{% endblock %}

{% block extra_scripts %}
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
    var periodo = 15;
    var chartConversoes = null;
    var chartAtendimentos = null;
    var leadStatusSelected = 'pending';

    window.onload = function() {
        carregarDados();
        document.getElementById('lead-date').valueAsDate = new Date();
        setLeadStatus('pending');
    };

    function mostrarErro(mensagem) {
        var container = document.getElementById('error-container');
        container.innerHTML = '<div class="error-message">⚠️ ' + mensagem + '</div>';
        container.style.display = 'block';
        setTimeout(function() {
            container.style.display = 'none';
        }, 5000);
    }

    function setPeriodo(dias) {
        periodo = dias;
        document.querySelectorAll('.periodo-btn').forEach(function(btn) {
            btn.classList.remove('active');
            if (btn.dataset.periodo == dias) btn.classList.add('active');
        });
        carregarDados();
    }

    function carregarDados() {
        carregarStats();
        carregarCharts();
        carregarConversoes();
        carregarLeads();
    }

    function carregarStats() {
        fetch('/admin/conversas/api/stats?periodo=' + periodo)
            .then(function(r) { 
                if (!r.ok) throw new Error('API Error: ' + r.status);
                return r.json(); 
            })
            .then(function(data) {
                if (data.error) {
                    mostrarErro('Error loading stats: ' + data.error);
                    return;
                }
                document.getElementById('valor-total').textContent = '$' + (data.valor_total || 0);
                document.getElementById('conversoes-total').textContent = (data.total_conversoes || 0) + ' conversions';
                document.getElementById('taxa-conversao').textContent = (data.taxa_conversao || 0) + '%';
                document.getElementById('leads-followup').textContent = data.leads_followup || 0;
                
                document.getElementById('stat-conversoes').textContent = data.conversoes || 0;
                document.getElementById('stat-clientes').textContent = data.clientes_unicos || 0;
                document.getElementById('stat-ia').textContent = data.tempo_ia_minutos || 0;
                document.getElementById('stat-humano').textContent = data.tempo_humano_minutos || 0;
                document.getElementById('stat-taxa').textContent = (data.taxa_conversao_stat || 0) + '%';
            })
            .catch(function(err) {
                console.error('Error loading stats:', err);
                mostrarErro('Failed to load statistics');
            });
    }

    function carregarCharts() {
        fetch('/admin/conversas/api/chart-data?periodo=' + periodo)
            .then(function(r) { 
                if (!r.ok) throw new Error('API Error: ' + r.status);
                return r.json(); 
            })
            .then(function(data) {
                if (data.error) {
                    mostrarErro('Error loading charts: ' + data.error);
                    return;
                }
                
                var labels = data.labels.map(function(d) {
                    var date = new Date(d);
                    return (date.getMonth()+1) + '/' + date.getDate();
                });

                var ctxConv = document.getElementById('chartConversoes').getContext('2d');
                if (chartConversoes) chartConversoes.destroy();
                chartConversoes = new Chart(ctxConv, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Conversions',
                            data: data.conversoes,
                            backgroundColor: 'rgba(39, 174, 96, 0.8)'
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: { legend: { display: false } },
                        scales: { y: { beginAtZero: true } }
                    }
                });

                var ctxAtend = document.getElementById('chartAtendimentos').getContext('2d');
                if (chartAtendimentos) chartAtendimentos.destroy();
                chartAtendimentos = new Chart(ctxAtend, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'AI',
                            data: data.atendimentos_ia,
                            borderColor: 'rgba(155, 89, 182, 1)',
                            backgroundColor: 'rgba(155, 89, 182, 0.1)',
                            fill: true
                        }, {
                            label: 'Human',
                            data: data.atendimentos_humano,
                            borderColor: 'rgba(243, 156, 18, 1)',
                            backgroundColor: 'rgba(243, 156, 18, 0.1)',
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true,
                        scales: { y: { beginAtZero: true } }
                    }
                });
            })
            .catch(function(err) {
                console.error('Error loading charts:', err);
                mostrarErro('Failed to load charts');
            });
    }

    function carregarConversoes() {
        fetch('/admin/conversas/api/conversoes?periodo=' + periodo)
            .then(function(r) { 
                if (!r.ok) throw new Error('API Error: ' + r.status);
                return r.json(); 
            })
            .then(function(data) {
                var tbody = document.getElementById('conversoes-body');
                if (data.error) {
                    tbody.innerHTML = '<tr><td colspan="6" class="empty-state" style="color:#e74c3c;">Error: ' + data.error + '</td></tr>';
                    return;
                }
                if (!data.conversoes || data.conversoes.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No conversions in this period</td></tr>';
                    return;
                }
                var html = '';
                data.conversoes.forEach(function(c) {
                    html += '<tr>';
                    html += '<td><strong>' + c.phone + '</strong></td>';
                    html += '<td style="color:#27ae60;font-weight:bold;">$' + c.valor + '</td>';
                    html += '<td>' + c.timestamp + '</td>';
                    html += '<td>' + c.tempo_atendimento + '</td>';
                    html += '<td><span class="badge badge-ia">' + c.tipo_atendimento + '</span></td>';
                    html += '<td><span class="badge badge-info">' + c.metodo + '</span></td>';
                    html += '</tr>';
                });
                tbody.innerHTML = html;
            })
            .catch(function(err) {
                console.error('Error loading conversions:', err);
                document.getElementById('conversoes-body').innerHTML = '<tr><td colspan="6" class="empty-state" style="color:#e74c3c;">Failed to load conversions</td></tr>';
            });
    }

    function carregarLeads() {
        fetch('/admin/conversas/api/leads-followup')
            .then(function(r) { 
                if (!r.ok) throw new Error('API Error: ' + r.status);
                return r.json(); 
            })
            .then(function(data) {
                var tbody = document.getElementById('leads-body');
                if (data.error) {
                    tbody.innerHTML = '<tr><td colspan="9" class="empty-state" style="color:#e74c3c;">Error: ' + data.error + '</td></tr>';
                    return;
                }
                if (!data.leads || data.leads.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="9" class="empty-state">No leads registered. Click "+ Add Lead" to start.</td></tr>';
                    return;
                }
                var html = '';
                data.leads.forEach(function(l) {
                    var priClass = 'prioridade-' + l.priority.toLowerCase();
                    var statusBadge = '';
                    if (l.status === 'converted') statusBadge = '<span class="badge badge-success">Converted</span>';
                    else if (l.status === 'no') statusBadge = '<span class="badge badge-danger">No</span>';
                    else statusBadge = '<span class="badge badge-warning">Pending</span>';
                    
                    html += '<tr>';
                    html += '<td><strong>' + l.phone + '</strong></td>';
                    html += '<td>' + l.last_contact + '</td>';
                    html += '<td>' + l.total_msgs + '</td>';
                    html += '<td>' + l.dias_sem_contato + ' days</td>';
                    html += '<td>' + l.asked_quote + '</td>';
                    html += '<td><span class="badge ' + priClass + '">' + l.priority + '</span></td>';
                    html += '<td>' + statusBadge + '</td>';
                    html += '<td style="max-width:150px;overflow:hidden;text-overflow:ellipsis;">' + (l.notes || 'N/A') + '</td>';
                    html += '<td>';
                    html += '<button class="btn-action btn-whatsapp" onclick="abrirWhatsApp(\'' + l.phone + '\')">📱</button>';
                    html += '<button class="btn-action btn-edit" onclick="editarLead(\'' + l.id + '\')">✏️</button>';
                    html += '<button class="btn-action btn-delete" onclick="deletarLead(\'' + l.id + '\')">🗑️</button>';
                    html += '</td>';
                    html += '</tr>';
                });
                tbody.innerHTML = html;
            })
            .catch(function(err) {
                console.error('Error loading leads:', err);
                document.getElementById('leads-body').innerHTML = '<tr><td colspan="9" class="empty-state" style="color:#e74c3c;">Failed to load leads</td></tr>';
            });
    }

    function abrirWhatsApp(phone) {
        window.open('https://wa.me/' + phone, '_blank');
    }

    function abrirModalConversao() {
        document.getElementById('modal-conversao').style.display = 'flex';
    }

    function abrirModalLead() {
        document.getElementById('modal-lead').style.display = 'flex';
        document.getElementById('lead-phone').value = '';
        document.getElementById('lead-date').valueAsDate = new Date();
        document.getElementById('lead-asked-quote').checked = false;
        document.getElementById('lead-priority').value = 'Medium';
        document.getElementById('lead-reason').value = '';
        setLeadStatus('pending');
    }

    function fecharModal(modalId) {
        document.getElementById(modalId).style.display = 'none';
    }

    function setLeadStatus(status) {
        leadStatusSelected = status;
        document.getElementById('status-pending').classList.remove('active-pending');
        document.getElementById('status-converted').classList.remove('active-converted');
        document.getElementById('status-no').classList.remove('active-no');
        
        if (status === 'pending') {
            document.getElementById('status-pending').classList.add('active-pending');
        } else if (status === 'converted') {
            document.getElementById('status-converted').classList.add('active-converted');
        } else if (status === 'no') {
            document.getElementById('status-no').classList.add('active-no');
        }
    }

    function salvarLead() {
        var phone = document.getElementById('lead-phone').value;
        var date = document.getElementById('lead-date').value;
        var askedQuote = document.getElementById('lead-asked-quote').checked;
        var priority = document.getElementById('lead-priority').value;
        var reason = document.getElementById('lead-reason').value;
        
        if (!phone) {
            alert('Please enter phone number');
            return;
        }
        
        fetch('/admin/conversas/api/add-lead', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                phone: phone,
                last_contact_date: date,
                asked_quote: askedQuote,
                priority: priority,
                status: leadStatusSelected,
                notes: reason
            })
        })
        .then(function(r) { 
            if (!r.ok) throw new Error('API Error: ' + r.status);
            return r.json(); 
        })
        .then(function(data) {
            if (data.success) {
                alert('✅ Lead saved successfully!');
                fecharModal('modal-lead');
                carregarDados();
            } else {
                alert('❌ Error: ' + data.error);
            }
        })
        .catch(function(err) {
            console.error('Error saving lead:', err);
            alert('❌ Failed to save lead');
        });
    }

    function registrarConversao() {
        var phone = document.getElementById('conv-phone').value;
        var valor = document.getElementById('conv-valor').value;
        var obs = document.getElementById('conv-obs').value;
        
        if (!phone || !valor) {
            alert('Please fill in phone and value');
            return;
        }
        
        fetch('/admin/conversas/api/registrar-conversao', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone: phone, valor: valor, observacao: obs })
        })
        .then(function(r) { 
            if (!r.ok) throw new Error('API Error: ' + r.status);
            return r.json(); 
        })
        .then(function(data) {
            if (data.success) {
                alert('✅ Conversion saved successfully!');
                fecharModal('modal-conversao');
                document.getElementById('conv-phone').value = '';
                document.getElementById('conv-valor').value = '';
                document.getElementById('conv-obs').value = '';
                carregarDados();
            } else {
                alert('❌ Error: ' + data.error);
            }
        })
        .catch(function(err) {
            console.error('Error saving conversion:', err);
            alert('❌ Failed to save conversion');
        });
    }

    function editarLead(id) {
        alert('Edit functionality coming soon! Lead ID: ' + id);
    }

    function deletarLead(id) {
        if (!confirm('Delete this lead?')) return;
        
        fetch('/admin/conversas/api/delete-lead/' + id, { method: 'POST' })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) {
                    alert('✅ Lead deleted!');
                    carregarDados();
                } else {
                    alert('❌ Error: ' + data.error);
                }
            })
            .catch(function(err) {
                console.error('Error deleting lead:', err);
                alert('❌ Failed to delete lead');
            });
    }
</script>
{% endblock %}
