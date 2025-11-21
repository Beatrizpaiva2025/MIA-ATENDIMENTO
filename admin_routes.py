"""
MIA Bot - Rotas do Painel Administrativo
Sistema de gestão omnichannel com pipeline de vendas, CRM e análise de documentos
VERSÃO ASYNC - Integrada com dados em tempo real do bot
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import os
import logging

# Configurar logging
logger = logging.getLogger(__name__)

# Configurar templates
templates = Jinja2Templates(directory="templates")

# Criar router
router = APIRouter(prefix="/admin", tags=["Admin Panel"])

# ✅ USAR MESMA CONEXÃO DO BOT (Motor async)
from admin_training_routes import get_database
db = get_database()

# ============================================
# DASHBOARD PRINCIPAL
# ============================================

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Dashboard principal com estatísticas gerais"""
    try:
        # Buscar estatísticas em tempo real
        total_conversas = await db.conversas.count_documents({})
        
        # Conversas de hoje
        hoje_inicio = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        conversas_hoje = await db.conversas.count_documents({
            "timestamp": {"$gte": hoje_inicio},
            "role": "user"
        })
        
        # Leads (conversas únicas por telefone)
        pipeline_leads = [
            {"$group": {"_id": "$phone"}},
            {"$count": "total"}
        ]
        leads_result = await db.conversas.aggregate(pipeline_leads).to_list(length=1)
        total_leads = leads_result[0]["total"] if leads_result else 0
        
        # Documentos analisados (imagens)
        total_documentos = await db.conversas.count_documents({"type": "image"})
        
        # Conversas por canal (últimos 7 dias)
        date_limit = datetime.now() - timedelta(days=7)
        conversas_whatsapp = await db.conversas.count_documents({
            "canal": "WhatsApp",
            "timestamp": {"$gte": date_limit}
        })
        
        # Últimas conversas (agrupadas por telefone)
        ultimas_conversas_raw = await db.conversas.find({
            "role": "user"
        }).sort("timestamp", -1).limit(50).to_list(length=50)
        
        # Agrupar por telefone e pegar última mensagem
        conversas_por_telefone = {}
        for conv in ultimas_conversas_raw:
            phone = conv.get("phone", "")
            if phone and phone not in conversas_por_telefone:
                conversas_por_telefone[phone] = {
                    "phone": phone,
                    "message": conv.get("message", ""),
                    "timestamp": conv.get("timestamp"),
                    "timestamp_formatted": conv.get("timestamp").strftime("%d/%m/%Y %H:%M") if conv.get("timestamp") else "",
                    "canal": conv.get("canal", "WhatsApp"),
                    "type": conv.get("type", "text")
                }
        
        ultimas_conversas = list(conversas_por_telefone.values())[:10]
        
        # Calcular taxa de conversão (simplificado)
        taxa_conversao = 0
        if total_leads > 0:
            # Considerar "conversão" se teve mais de 3 mensagens
            conversas_ativas = 0
            for phone in conversas_por_telefone.keys():
                count = await db.conversas.count_documents({"phone": phone})
                if count >= 3:
                    conversas_ativas += 1
            taxa_conversao = int((conversas_ativas / total_leads) * 100)
        
        stats = {
            "total_conversas": total_conversas,
            "conversas_hoje": conversas_hoje,
            "total_leads": total_leads,
            "total_documentos": total_documentos,
            "taxa_conversao": taxa_conversao,
            "conversas_whatsapp": conversas_whatsapp,
            "ultimas_conversas": ultimas_conversas
        }
        
        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request,
            "stats": stats
        })
        
    except Exception as e:
        logger.error(f"Erro no dashboard: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request,
            "error": str(e),
            "stats": {
                "total_conversas": 0,
                "conversas_hoje": 0,
                "total_leads": 0,
                "total_documentos": 0,
                "taxa_conversao": 0,
                "conversas_whatsapp": 0,
                "ultimas_conversas": []
            }
        })

# ============================================
# API: DADOS DO DASHBOARD (JSON)
# ============================================

@router.get("/api/dashboard-data")
async def get_dashboard_data():
    """Retorna dados do dashboard em JSON para atualização em tempo real"""
    try:
        # Conversas de hoje
        hoje_inicio = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        conversas_hoje = await db.conversas.count_documents({
            "timestamp": {"$gte": hoje_inicio},
            "role": "user"
        })
        
        # Total de conversas
        total_conversas = await db.conversas.count_documents({})
        
        # Leads únicos
        pipeline_leads = [
            {"$group": {"_id": "$phone"}},
            {"$count": "total"}
        ]
        leads_result = await db.conversas.aggregate(pipeline_leads).to_list(length=1)
        total_leads = leads_result[0]["total"] if leads_result else 0
        
        # Documentos
        total_documentos = await db.conversas.count_documents({"type": "image"})
        
        # Conversas por dia (últimos 7 dias)
        conversas_por_dia = []
        for i in range(6, -1, -1):
            dia = datetime.now() - timedelta(days=i)
            dia_inicio = dia.replace(hour=0, minute=0, second=0, microsecond=0)
            dia_fim = dia_inicio + timedelta(days=1)
            
            count = await db.conversas.count_documents({
                "timestamp": {"$gte": dia_inicio, "$lt": dia_fim},
                "role": "user"
            })
            
            conversas_por_dia.append({
                "data": dia.strftime("%d/%m"),
                "count": count
            })
        
        return {
            "conversas_hoje": conversas_hoje,
            "total_conversas": total_conversas,
            "total_leads": total_leads,
            "total_documentos": total_documentos,
            "conversas_por_dia": conversas_por_dia,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao buscar dados: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# PIPELINE DE VENDAS
# ============================================

@router.get("/pipeline", response_class=HTMLResponse)
async def admin_pipeline(request: Request):
    """Visualização do pipeline de vendas (funil)"""
    try:
        # Buscar todas as conversas agrupadas por telefone
        pipeline = [
            {"$group": {
                "_id": "$phone",
                "total_mensagens": {"$sum": 1},
                "ultima_mensagem": {"$max": "$timestamp"}
            }},
            {"$sort": {"ultima_mensagem": -1}}
        ]
        
        leads_data = await db.conversas.aggregate(pipeline).to_list(length=1000)
        
        # Classificar leads por estágio baseado em número de mensagens
        pipeline_data = {
            "novo": 0,  # 1-2 mensagens
            "contato_inicial": 0,  # 3-5 mensagens
            "qualificado": 0,  # 6-10 mensagens
            "proposta": 0,  # 11-15 mensagens
            "negociacao": 0,  # 16+ mensagens
            "fechado": 0,
            "perdido": 0
        }
        
        for lead in leads_data:
            total = lead["total_mensagens"]
            if total <= 2:
                pipeline_data["novo"] += 1
            elif total <= 5:
                pipeline_data["contato_inicial"] += 1
            elif total <= 10:
                pipeline_data["qualificado"] += 1
            elif total <= 15:
                pipeline_data["proposta"] += 1
            else:
                pipeline_data["negociacao"] += 1
        
        # Leads por canal
        leads_por_canal = {
            "WhatsApp": await db.conversas.distinct("phone", {"canal": "WhatsApp"}),
            "Instagram": [],
            "WebChat": []
        }
        
        leads_por_canal_count = {
            "WhatsApp": len(leads_por_canal["WhatsApp"]),
            "Instagram": 0,
            "WebChat": 0
        }
        
        # Leads recentes
        leads_recentes_raw = await db.conversas.find({
            "role": "user"
        }).sort("timestamp", -1).limit(20).to_list(length=20)
        
        # Agrupar por telefone
        leads_por_telefone = {}
        for msg in leads_recentes_raw:
            phone = msg.get("phone", "")
            if phone and phone not in leads_por_telefone:
                # Contar mensagens deste lead
                total_msgs = await db.conversas.count_documents({"phone": phone})
                
                leads_por_telefone[phone] = {
                    "phone": phone,
                    "timestamp": msg.get("timestamp"),
                    "timestamp_formatted": msg.get("timestamp").strftime("%d/%m/%Y %H:%M") if msg.get("timestamp") else "",
                    "canal": msg.get("canal", "WhatsApp"),
                    "total_mensagens": total_msgs,
                    "estagio": "NOVO" if total_msgs <= 2 else "QUALIFICADO" if total_msgs <= 10 else "NEGOCIACAO"
                }
        
        leads_recentes = list(leads_por_telefone.values())
        
        return templates.TemplateResponse("admin_pipeline.html", {
            "request": request,
            "pipeline": pipeline_data,
            "leads_por_canal": leads_por_canal_count,
            "leads_recentes": leads_recentes
        })
        
    except Exception as e:
        logger.error(f"Erro no pipeline: {e}")
        import traceback
        logger.error(traceback.format_exc())
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
        # Buscar todos os leads (telefones únicos)
        filtro_canal = {"canal": canal} if canal else {}
        
        pipeline = [
            {"$match": filtro_canal},
            {"$group": {
                "_id": "$phone",
                "total_mensagens": {"$sum": 1},
                "ultima_mensagem": {"$max": "$timestamp"},
                "canal": {"$first": "$canal"}
            }},
            {"$sort": {"ultima_mensagem": -1}},
            {"$limit": 100}
        ]
        
        leads_data = await db.conversas.aggregate(pipeline).to_list(length=100)
        
        # Formatar leads
        leads = []
        for lead_data in leads_data:
            total = lead_data["total_mensagens"]
            
            # Determinar estágio
            if total <= 2:
                estagio_lead = "NOVO"
                temperatura = "FRIO"
            elif total <= 5:
                estagio_lead = "CONTATO_INICIAL"
                temperatura = "MORNO"
            elif total <= 10:
                estagio_lead = "QUALIFICADO"
                temperatura = "QUENTE"
            else:
                estagio_lead = "NEGOCIACAO"
                temperatura = "QUENTE"
            
            # Filtrar por estágio se especificado
            if estagio and estagio_lead != estagio:
                continue
            
            leads.append({
                "_id": str(lead_data["_id"]),
                "phone": lead_data["_id"],
                "canal": lead_data.get("canal", "WhatsApp"),
                "estagio": estagio_lead,
                "temperatura": temperatura,
                "total_mensagens": total,
                "timestamp": lead_data["ultima_mensagem"],
                "timestamp_formatted": lead_data["ultima_mensagem"].strftime("%d/%m/%Y %H:%M") if lead_data.get("ultima_mensagem") else ""
            })
        
        # Estatísticas
        total_leads = len(leads)
        leads_quentes = len([l for l in leads if l["temperatura"] == "QUENTE"])
        leads_mornos = len([l for l in leads if l["temperatura"] == "MORNO"])
        leads_frios = len([l for l in leads if l["temperatura"] == "FRIO"])
        
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
        import traceback
        logger.error(traceback.format_exc())
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
        # Por enquanto, retornar vazio (funcionalidade futura)
        transferencias = []
        
        return templates.TemplateResponse("admin_transfers.html", {
            "request": request,
            "transferencias": transferencias,
            "total_pendentes": 0,
            "total_em_atendimento": 0,
            "total_concluidas": 0,
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
        # Buscar conversas com imagens
        filtro = {"type": "image"}
        
        documentos_raw = await db.conversas.find(filtro).sort("timestamp", -1).limit(50).to_list(length=50)
        
        # Formatar documentos
        documentos = []
        for doc in documentos_raw:
            documentos.append({
                "_id": str(doc.get("_id", "")),
                "phone": doc.get("phone", ""),
                "timestamp": doc.get("timestamp"),
                "timestamp_formatted": doc.get("timestamp").strftime("%d/%m/%Y %H:%M") if doc.get("timestamp") else "",
                "message": doc.get("message", "[IMAGEM]"),
                "status": "ANALISADO"
            })
        
        # Estatísticas
        total_documentos = len(documentos)
        docs_aprovados = total_documentos  # Todos analisados são considerados aprovados
        docs_pendentes = 0
        docs_rejeitados = 0
        
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
        import traceback
        logger.error(traceback.format_exc())
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
            "mongodb_status": "✅ Conectado",
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
       @router.get("/controle", response_class=HTMLResponse)
async def admin_controle(request: Request):
    """Controle de atendimento IA/Humano"""
    return templates.TemplateResponse("admin_controle.html", {
        "request": request
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
        total_conversas = await db.conversas.count_documents({})
        
        # Leads únicos
        pipeline_leads = [
            {"$group": {"_id": "$phone"}},
            {"$count": "total"}
        ]
        leads_result = await db.conversas.aggregate(pipeline_leads).to_list(length=1)
        total_leads = leads_result[0]["total"] if leads_result else 0
        
        total_documentos = await db.conversas.count_documents({"type": "image"})
        
        stats = {
            "total_conversas": total_conversas,
            "total_leads": total_leads,
            "total_documentos": total_documentos,
            "transferencias_pendentes": 0,
            "timestamp": datetime.now().isoformat()
        }
        
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
