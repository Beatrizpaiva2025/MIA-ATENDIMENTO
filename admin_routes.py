"""
MIA Bot - Rotas do Painel Administrativo
Sistema de gestão omnichannel com pipeline de vendas, CRM e análise de documentos
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import os
from pymongo import MongoClient
import logging

# Configurar logging
logger = logging.getLogger(__name__)

# Configurar templates
templates = Jinja2Templates(directory="templates")

# Criar router
router = APIRouter(prefix="/admin", tags=["Admin Panel"])

# Conectar MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
mongo_client = MongoClient(MONGODB_URI) if MONGODB_URI else None
db = mongo_client["mia_bot"] if mongo_client else None

# ============================================
# DASHBOARD PRINCIPAL
# ============================================

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Dashboard principal com estatísticas gerais"""
    try:
        if db is None:  # ✅ CORRIGIDO
            return templates.TemplateResponse("admin_dashboard.html", {
                "request": request,
                "error": "MongoDB não configurado"
            })
        
        # Buscar estatísticas
        total_conversas = db.conversas.count_documents({})
        total_leads = db.leads.count_documents({})
        total_documentos = db.documentos.count_documents({})
        total_transferencias = db.transferencias.count_documents({"status": "PENDENTE"})
        
        # Conversas por canal (últimos 7 dias)
        date_limit = datetime.now() - timedelta(days=7)
        conversas_whatsapp = db.conversas.count_documents({
            "canal": "WhatsApp",
            "timestamp": {"$gte": date_limit}
        })
        conversas_instagram = db.conversas.count_documents({
            "canal": "Instagram",
            "timestamp": {"$gte": date_limit}
        })
        conversas_webchat = db.conversas.count_documents({
            "canal": "WebChat",
            "timestamp": {"$gte": date_limit}
        })
        
        # Últimas conversas
        ultimas_conversas = list(db.conversas.find().sort("timestamp", -1).limit(10))
        
        # Formatar datas
        for conv in ultimas_conversas:
            conv["timestamp_formatted"] = conv["timestamp"].strftime("%d/%m/%Y %H:%M")
        
        stats = {
            "total_conversas": total_conversas,
            "total_leads": total_leads,
            "total_documentos": total_documentos,
            "transferencias_pendentes": total_transferencias,
            "conversas_whatsapp": conversas_whatsapp,
            "conversas_instagram": conversas_instagram,
            "conversas_webchat": conversas_webchat,
            "ultimas_conversas": ultimas_conversas
        }
        
        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request,
            "stats": stats
        })
        
    except Exception as e:
        logger.error(f"Erro no dashboard: {e}")
        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request,
            "error": str(e)
        })

# ============================================
# PIPELINE DE VENDAS
# ============================================

@router.get("/pipeline", response_class=HTMLResponse)
async def admin_pipeline(request: Request):
    """Visualização do pipeline de vendas (funil)"""
    try:
        if db is None:  # ✅ CORRIGIDO
            return templates.TemplateResponse("admin_pipeline.html", {
                "request": request,
                "error": "MongoDB não configurado"
            })
        
        # Leads por estágio do funil
        pipeline_data = {
            "novo": db.leads.count_documents({"estagio": "NOVO"}),
            "contato_inicial": db.leads.count_documents({"estagio": "CONTATO_INICIAL"}),
            "qualificado": db.leads.count_documents({"estagio": "QUALIFICADO"}),
            "proposta": db.leads.count_documents({"estagio": "PROPOSTA"}),
            "negociacao": db.leads.count_documents({"estagio": "NEGOCIACAO"}),
            "fechado": db.leads.count_documents({"estagio": "FECHADO"}),
            "perdido": db.leads.count_documents({"estagio": "PERDIDO"})
        }
        
        # Leads por canal
        leads_por_canal = {
            "WhatsApp": db.leads.count_documents({"canal": "WhatsApp"}),
            "Instagram": db.leads.count_documents({"canal": "Instagram"}),
            "WebChat": db.leads.count_documents({"canal": "WebChat"})
        }
        
        # Leads recentes
        leads_recentes = list(db.leads.find().sort("timestamp", -1).limit(20))
        
        for lead in leads_recentes:
            lead["timestamp_formatted"] = lead["timestamp"].strftime("%d/%m/%Y %H:%M")
        
        return templates.TemplateResponse("admin_pipeline.html", {
            "request": request,
            "pipeline": pipeline_data,
            "leads_por_canal": leads_por_canal,
            "leads_recentes": leads_recentes
        })
        
    except Exception as e:
        logger.error(f"Erro no pipeline: {e}")
        return templates.TemplateResponse("admin_pipeline.html", {
            "request": request,
            "error": str(e)
        })

# ============================================
# GESTÃO DE LEADS (CRM)
# ============================================

@router.get("/leads", response_class=HTMLResponse)
async def admin_leads(request: Request, canal: Optional[str] = None, estagio: Optional[str] = None):
    """Gestão completa de leads com filtros"""
    try:
        if db is None:  # ✅ CORRIGIDO
            return templates.TemplateResponse("admin_leads.html", {
                "request": request,
                "error": "MongoDB não configurado"
            })
        
        # Construir filtro
        filtro = {}
        if canal:
            filtro["canal"] = canal
        if estagio:
            filtro["estagio"] = estagio
        
        # Buscar leads
        leads = list(db.leads.find(filtro).sort("timestamp", -1).limit(100))
        
        # Formatar dados
        for lead in leads:
            lead["timestamp_formatted"] = lead["timestamp"].strftime("%d/%m/%Y %H:%M")
            lead["_id"] = str(lead["_id"])
        
        # Estatísticas
        total_leads = len(leads)
        leads_quentes = db.leads.count_documents({**filtro, "temperatura": "QUENTE"})
        leads_mornos = db.leads.count_documents({**filtro, "temperatura": "MORNO"})
        leads_frios = db.leads.count_documents({**filtro, "temperatura": "FRIO"})
        
        return templates.TemplateResponse("admin_leads.html", {
            "request": request,
            "leads": leads,
            "total_leads": total_leads,
            "leads_quentes": leads_quentes,
            "leads_mornos": leads_mornos,
            "leads_frios": leads_frios,
            "filtro_canal": canal,
            "filtro_estagio": estagio
        })
        
    except Exception as e:
        logger.error(f"Erro na gestão de leads: {e}")
        return templates.TemplateResponse("admin_leads.html", {
            "request": request,
            "error": str(e)
        })

# ============================================
# TRANSFERÊNCIAS PARA HUMANO
# ============================================

@router.get("/transfers", response_class=HTMLResponse)
async def admin_transfers(request: Request, status: Optional[str] = "PENDENTE"):
    """Gerenciar transferências para atendimento humano"""
    try:
        if db is None:  # ✅ CORRIGIDO
            return templates.TemplateResponse("admin_transfers.html", {
                "request": request,
                "error": "MongoDB não configurado"
            })
        
        # Buscar transferências
        filtro = {"status": status} if status else {}
        transferencias = list(db.transferencias.find(filtro).sort("timestamp", -1).limit(50))
        
        # Formatar dados
        for trans in transferencias:
            trans["timestamp_formatted"] = trans["timestamp"].strftime("%d/%m/%Y %H:%M")
            trans["_id"] = str(trans["_id"])
        
        # Estatísticas
        total_pendentes = db.transferencias.count_documents({"status": "PENDENTE"})
        total_em_atendimento = db.transferencias.count_documents({"status": "EM_ATENDIMENTO"})
        total_concluidas = db.transferencias.count_documents({"status": "CONCLUIDO"})
        
        return templates.TemplateResponse("admin_transfers.html", {
            "request": request,
            "transferencias": transferencias,
            "total_pendentes": total_pendentes,
            "total_em_atendimento": total_em_atendimento,
            "total_concluidas": total_concluidas,
            "filtro_status": status
        })
        
    except Exception as e:
        logger.error(f"Erro nas transferências: {e}")
        return templates.TemplateResponse("admin_transfers.html", {
            "request": request,
            "error": str(e)
        })

# ============================================
# ANÁLISE DE DOCUMENTOS
# ============================================

@router.get("/documents", response_class=HTMLResponse)
async def admin_documents(request: Request, status: Optional[str] = None):
    """Visualizar documentos analisados pelo GPT-4 Vision"""
    try:
        if db is None:  # ✅ CORRIGIDO
            return templates.TemplateResponse("admin_documents.html", {
                "request": request,
                "error": "MongoDB não configurado"
            })
        
        # Buscar documentos
        filtro = {"status": status} if status else {}
        documentos = list(db.documentos.find(filtro).sort("timestamp", -1).limit(50))
        
        # Formatar dados
        for doc in documentos:
            doc["timestamp_formatted"] = doc["timestamp"].strftime("%d/%m/%Y %H:%M")
            doc["_id"] = str(doc["_id"])
        
        # Estatísticas
        total_documentos = len(documentos)
        docs_aprovados = db.documentos.count_documents({"status": "APROVADO"})
        docs_pendentes = db.documentos.count_documents({"status": "PENDENTE"})
        docs_rejeitados = db.documentos.count_documents({"status": "REJEITADO"})
        
        return templates.TemplateResponse("admin_documents.html", {
            "request": request,
            "documentos": documentos,
            "total_documentos": total_documentos,
            "docs_aprovados": docs_aprovados,
            "docs_pendentes": docs_pendentes,
            "docs_rejeitados": docs_rejeitados,
            "filtro_status": status
        })
        
    except Exception as e:
        logger.error(f"Erro na análise de documentos: {e}")
        return templates.TemplateResponse("admin_documents.html", {
            "request": request,
            "error": str(e)
        })

# ============================================
# CONFIGURAÇÕES DO SISTEMA
# ============================================

@router.get("/config", response_class=HTMLResponse)
async def admin_config(request: Request):
    """Configurações do sistema e integrações"""
    try:
        # Verificar status das integrações
        config = {
            "openai_status": "✅ Configurado" if os.getenv("OPENAI_API_KEY") else "❌ Não configurado",
            "mongodb_status": "✅ Conectado" if db is not None else "❌ Não conectado",  # ✅ CORRIGIDO
            "zapi_status": "✅ Configurado" if os.getenv("ZAPI_TOKEN") else "❌ Não configurado",
            "instagram_status": "⚠️ Opcional",
            "render_url": os.getenv("RENDER_EXTERNAL_URL", "https://mia-atendimento.onrender.com"),
            "ambiente": os.getenv("ENVIRONMENT", "production")
        }
        
        # Webhooks URLs
        webhooks = {
            "whatsapp": f"{config['render_url']}/webhook/whatsapp",
            "instagram": f"{config['render_url']}/webhook/instagram"
        }
        
        return templates.TemplateResponse("admin_config.html", {
            "request": request,
            "config": config,
            "webhooks": webhooks
        })
        
    except Exception as e:
        logger.error(f"Erro nas configurações: {e}")
        return templates.TemplateResponse("admin_config.html", {
            "request": request,
            "error": str(e)
        })

# ============================================
# API ENDPOINTS (JSON)
# ============================================

@router.get("/api/stats")
async def api_stats():
    """Retornar estatísticas em JSON"""
    try:
        if db is None:  # ✅ CORRIGIDO
            raise HTTPException(status_code=503, detail="MongoDB não disponível")
        
        stats = {
            "total_conversas": db.conversas.count_documents({}),
            "total_leads": db.leads.count_documents({}),
            "total_documentos": db.documentos.count_documents({}),
            "transferencias_pendentes": db.transferencias.count_documents({"status": "PENDENTE"}),
            "timestamp": datetime.now().isoformat()
        }
        
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
