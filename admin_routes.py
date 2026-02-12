"""
MIA Bot - Rotas do Painel Administrativo
Sistema de gestão omnichannel com pipeline de vendas, CRM e análise de documentos
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import os
from pymongo import MongoClient
from bson import ObjectId
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
db = mongo_client["mia_production"] if mongo_client else None

# ==================== HELPER FUNCTIONS ====================

def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict"""
    if doc and '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc

# ==================== LEADS & MARKETING STATS API ====================

@router.get("/api/leads/stats")
async def get_leads_stats(days: int = 30):
    """Get lead statistics for dashboard"""
    try:
        if db is None:
            return {"success": False, "error": "MongoDB not configured"}
            
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get leads from MongoDB
        leads = list(db['leads'].find({
            'created_at': {'$gte': start_date.isoformat()}
        }))
        
        # Calculate statistics
        total = len(leads)
        converted = sum(1 for l in leads if l.get('status') == 'converted')
        total_revenue = sum(l.get('service_value', 0) for l in leads if l.get('status') == 'converted')
        avg_ticket = total_revenue / converted if converted > 0 else 0
        conversion_rate = (converted / total * 100) if total > 0 else 0
        
        # By origin
        origins = {}
        for lead in leads:
            origin = lead.get('origin', 'Unknown')
            origins[origin] = origins.get(origin, 0) + 1
        
        return {
            "success": True,
            "total_leads": total,
            "total_revenue": round(total_revenue, 2),
            "avg_ticket": round(avg_ticket, 2),
            "conversion_rate": round(conversion_rate, 2),
            "converted_leads": converted,
            "leads_by_origin": origins
        }
    except Exception as e:
        logger.error(f"Error in get_leads_stats: {e}")
        return {"success": False, "error": str(e)}

@router.get("/api/marketing-stats")
async def get_marketing_stats(days: int = 30):
    """Get marketing statistics"""
    try:
        if db is None:
            return {"success": False, "error": "MongoDB not configured"}
            
        start_date = datetime.utcnow() - timedelta(days=days)
        
        stats = list(db['marketing_stats'].find({
            'date': {'$gte': start_date.isoformat()}
        }).sort('date', 1))
        
        # Serialize
        stats = [serialize_doc(stat) for stat in stats]
        
        # Calculate totals
        total_meta_cost = sum(s.get('meta_ads', {}).get('cost', 0) for s in stats)
        total_google_cost = sum(s.get('google_ads', {}).get('cost', 0) for s in stats)
        total_revenue = sum(s.get('conversions', {}).get('revenue', 0) for s in stats)
        
        return {
            "success": True,
            "stats": stats,
            "totals": {
                "marketing_cost": round(total_meta_cost + total_google_cost, 2),
                "revenue": round(total_revenue, 2)
            }
        }
    except Exception as e:
        logger.error(f"Error in get_marketing_stats: {e}")
        return {"success": False, "error": str(e)}

# ==================== ADS INTEGRATION API (Google Ads + Meta Ads) ====================

from ads_integration import get_all_campaigns, check_credentials, google_ads_api

@router.get("/api/ads/campaigns")
async def get_ads_campaigns(days: int = 30):
    """Busca campanhas reais do Google Ads e Meta Ads"""
    try:
        data = await get_all_campaigns(days)
        return {
            "success": True,
            "campaigns": data.get("campaigns", []),
            "totals": data.get("totals", {}),
            "by_platform": data.get("by_platform", {})
        }
    except Exception as e:
        logger.error(f"[ADS API] Error fetching campaigns: {e}")
        return {"success": False, "error": str(e), "campaigns": [], "totals": {}}

@router.get("/api/ads/google/campaigns")
async def get_google_campaigns(days: int = 30):
    """Busca campanhas apenas do Google Ads"""
    try:
        campaigns = await google_ads_api.get_campaigns(days)

        total_impressions = sum(c.get("impressions", 0) for c in campaigns)
        total_clicks = sum(c.get("clicks", 0) for c in campaigns)
        total_cost = sum(c.get("cost", 0) for c in campaigns)
        total_conversions = sum(c.get("conversions", 0) for c in campaigns)

        return {
            "success": True,
            "campaigns": campaigns,
            "totals": {
                "impressions": total_impressions,
                "clicks": total_clicks,
                "cost": round(total_cost, 2),
                "conversions": total_conversions,
                "ctr": round((total_clicks / total_impressions * 100) if total_impressions > 0 else 0, 2),
                "avg_cpc": round((total_cost / total_clicks) if total_clicks > 0 else 0, 2)
            }
        }
    except Exception as e:
        logger.error(f"[GOOGLE ADS API] Error: {e}")
        return {"success": False, "error": str(e), "campaigns": [], "totals": {}}

@router.get("/api/ads/credentials")
async def check_ads_credentials():
    """Verifica se as credenciais do Google Ads e Meta Ads estao configuradas"""
    return {
        "success": True,
        "credentials": check_credentials()
    }

@router.get("/api/ads/debug")
async def debug_ads_api():
    """Endpoint de diagnostico para verificar problemas com as APIs de ads"""
    import os
    from ads_integration import (
        GOOGLE_ADS_DEV_TOKEN, GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET,
        GOOGLE_ADS_REFRESH_TOKEN, GOOGLE_ADS_CUSTOMER_ID, GOOGLE_ADS_LOGIN_CUSTOMER_ID,
        META_APP_ID, META_ACCESS_TOKEN, META_AD_ACCOUNT_ID, META_APP_SECRET,
        google_ads_api, meta_ads_api
    )

    debug_info = {
        "credentials_loaded": {
            "google_ads": {
                "dev_token": bool(GOOGLE_ADS_DEV_TOKEN) and len(GOOGLE_ADS_DEV_TOKEN) > 5,
                "client_id": bool(GOOGLE_ADS_CLIENT_ID) and "apps.googleusercontent.com" in GOOGLE_ADS_CLIENT_ID,
                "client_secret": bool(GOOGLE_ADS_CLIENT_SECRET) and len(GOOGLE_ADS_CLIENT_SECRET) > 10,
                "refresh_token": bool(GOOGLE_ADS_REFRESH_TOKEN) and len(GOOGLE_ADS_REFRESH_TOKEN) > 20,
                "customer_id": GOOGLE_ADS_CUSTOMER_ID,
                "login_customer_id": GOOGLE_ADS_LOGIN_CUSTOMER_ID
            },
            "meta_ads": {
                "app_id": bool(META_APP_ID) and len(META_APP_ID) > 5,
                "app_secret": bool(META_APP_SECRET) and len(META_APP_SECRET) > 10,
                "access_token": bool(META_ACCESS_TOKEN) and len(META_ACCESS_TOKEN) > 20,
                "ad_account_id": META_AD_ACCOUNT_ID
            }
        },
        "api_tests": {
            "google_ads": None,
            "meta_ads": None
        }
    }

    # Testar Google Ads API
    try:
        google_campaigns = await google_ads_api.get_campaigns(days=7)
        debug_info["api_tests"]["google_ads"] = {
            "success": True,
            "campaigns_found": len(google_campaigns),
            "campaigns": google_campaigns[:3] if google_campaigns else []
        }
    except Exception as e:
        debug_info["api_tests"]["google_ads"] = {
            "success": False,
            "error": str(e)
        }

    # Testar Meta Ads API
    try:
        meta_campaigns = await meta_ads_api.get_campaigns(days=7)
        debug_info["api_tests"]["meta_ads"] = {
            "success": True,
            "campaigns_found": len(meta_campaigns),
            "campaigns": meta_campaigns[:3] if meta_campaigns else []
        }
    except Exception as e:
        debug_info["api_tests"]["meta_ads"] = {
            "success": False,
            "error": str(e)
        }

    return debug_info

@router.get("/api/ads/raw-test")
async def test_google_ads_raw():
    """Testa Google Ads API e retorna resposta bruta para diagnostico"""
    import httpx
    from datetime import datetime, timedelta
    from ads_integration import (
        GOOGLE_ADS_DEV_TOKEN, GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET,
        GOOGLE_ADS_REFRESH_TOKEN, GOOGLE_ADS_CUSTOMER_ID, GOOGLE_ADS_LOGIN_CUSTOMER_ID
    )

    result = {
        "step": "init",
        "credentials_present": {
            "dev_token": bool(GOOGLE_ADS_DEV_TOKEN),
            "client_id": bool(GOOGLE_ADS_CLIENT_ID),
            "client_secret": bool(GOOGLE_ADS_CLIENT_SECRET),
            "refresh_token": bool(GOOGLE_ADS_REFRESH_TOKEN),
            "customer_id": GOOGLE_ADS_CUSTOMER_ID,
            "login_customer_id": GOOGLE_ADS_LOGIN_CUSTOMER_ID
        }
    }

    try:
        # Step 1: Get access token
        result["step"] = "getting_access_token"
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_ADS_CLIENT_ID,
                    "client_secret": GOOGLE_ADS_CLIENT_SECRET,
                    "refresh_token": GOOGLE_ADS_REFRESH_TOKEN,
                    "grant_type": "refresh_token"
                }
            )
            result["token_status"] = token_response.status_code
            result["token_response"] = token_response.json() if token_response.status_code == 200 else token_response.text

            if token_response.status_code != 200:
                result["error"] = "Failed to get access token"
                return result

            access_token = token_response.json()["access_token"]
            result["step"] = "got_access_token"

            # Step 2: Query campaigns
            customer_id = GOOGLE_ADS_CUSTOMER_ID.replace("-", "")
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)

            # Query simples primeiro
            query = """
                SELECT
                    campaign.id,
                    campaign.name,
                    campaign.status
                FROM campaign
                LIMIT 10
            """

            url = f"https://googleads.googleapis.com/v18/customers/{customer_id}/googleAds:searchStream"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "developer-token": GOOGLE_ADS_DEV_TOKEN,
                "login-customer-id": GOOGLE_ADS_LOGIN_CUSTOMER_ID.replace("-", ""),
                "Content-Type": "application/json"
            }

            result["step"] = "querying_campaigns_simple"
            campaign_response = await client.post(url, headers=headers, json={"query": query})
            result["campaign_status"] = campaign_response.status_code
            result["campaign_raw_response"] = campaign_response.text[:2000]  # Primeiros 2000 chars

            if campaign_response.status_code == 200:
                result["campaign_json"] = campaign_response.json()
                result["step"] = "success_simple_query"

                # Agora tentar com metricas
                query_with_metrics = f"""
                    SELECT
                        campaign.id,
                        campaign.name,
                        campaign.status,
                        metrics.impressions,
                        metrics.clicks,
                        metrics.cost_micros
                    FROM campaign
                    WHERE segments.date BETWEEN '{start_date.strftime('%Y-%m-%d')}' AND '{end_date.strftime('%Y-%m-%d')}'
                """

                result["step"] = "querying_with_metrics"
                metrics_response = await client.post(url, headers=headers, json={"query": query_with_metrics})
                result["metrics_status"] = metrics_response.status_code
                result["metrics_raw_response"] = metrics_response.text[:2000]

                if metrics_response.status_code == 200:
                    result["metrics_json"] = metrics_response.json()
                    result["step"] = "success_with_metrics"
                else:
                    result["metrics_error"] = metrics_response.text
            else:
                result["error"] = campaign_response.text

    except Exception as e:
        result["exception"] = str(e)
        import traceback
        result["traceback"] = traceback.format_exc()

    return result

@router.get("/api/dashboard-data")
async def get_dashboard_data(days: int = 30):
    """Get complete dashboard data"""
    try:
        if db is None:
            return {"success": False, "error": "MongoDB not configured"}
            
        # Get lead stats
        lead_stats_response = await get_leads_stats(days)
        
        # Get marketing stats
        marketing_stats_response = await get_marketing_stats(days)
        
        # Calculate KPIs
        total_cost = marketing_stats_response.get('totals', {}).get('marketing_cost', 0)
        total_revenue = lead_stats_response.get('total_revenue', 0)
        total_leads = lead_stats_response.get('total_leads', 0)
        converted = lead_stats_response.get('converted_leads', 0)
        
        cpl = total_cost / total_leads if total_leads > 0 else 0
        cac = total_cost / converted if converted > 0 else 0
        ltv = 385  # Average LTV
        
        return {
            "success": True,
            "lead_stats": lead_stats_response,
            "marketing_stats": marketing_stats_response.get('stats', []),
            "kpis": {
                "cpl": round(cpl, 2),
                "cac": round(cac, 2),
                "ltv": ltv,
                "ltv_cac_ratio": round(ltv / cac, 2) if cac > 0 else 0,
                "marketing_roi": round(((total_revenue - total_cost) / total_cost) * 100, 2) if total_cost > 0 else 0
            }
        }
    except Exception as e:
        logger.error(f"Error in get_dashboard_data: {e}")
        return {"success": False, "error": str(e)}

# ============================================
# DASHBOARD PRINCIPAL
# ============================================

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Dashboard principal com estatísticas gerais"""
    try:
        if db is None:
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
        if db is None:
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
        if db is None:
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
        if db is None:
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
        if db is None:
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
            "mongodb_status": "✅ Conectado" if db is not None else "❌ Não conectado",
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
        if db is None:
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

