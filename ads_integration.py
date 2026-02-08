# ============================================
# INTEGRACAO COM GOOGLE ADS E META ADS APIs
# Busca dados reais das campanhas
# ============================================

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURACOES - Variaveis de Ambiente
# ============================================

# Google Ads
GOOGLE_ADS_DEV_TOKEN = os.getenv("GOOGLE_ADS_DEV_TOKEN", "")
GOOGLE_ADS_CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID", "")
GOOGLE_ADS_CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET", "")
GOOGLE_ADS_REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN", "")
GOOGLE_ADS_LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "")
GOOGLE_ADS_CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "")

# Meta Ads
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID", "")

# ============================================
# GOOGLE ADS API
# ============================================

class GoogleAdsAPI:
    """Cliente para Google Ads API v18"""

    BASE_URL = "https://googleads.googleapis.com/v18"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(self):
        self.access_token = None
        self.token_expiry = None

    async def _refresh_access_token(self) -> str:
        """Obtem novo access token usando refresh token"""
        if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.access_token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": GOOGLE_ADS_CLIENT_ID,
                    "client_secret": GOOGLE_ADS_CLIENT_SECRET,
                    "refresh_token": GOOGLE_ADS_REFRESH_TOKEN,
                    "grant_type": "refresh_token"
                }
            )

            if response.status_code == 200:
                data = response.json()
                self.access_token = data["access_token"]
                self.token_expiry = datetime.now() + timedelta(seconds=data.get("expires_in", 3600) - 60)
                logger.info("[GOOGLE ADS] Access token refreshed successfully")
                return self.access_token
            else:
                logger.error(f"[GOOGLE ADS] Failed to refresh token: {response.text}")
                raise Exception(f"Failed to refresh Google Ads token: {response.text}")

    async def get_campaigns(self, days: int = 30) -> List[Dict]:
        """Busca campanhas e metricas do Google Ads"""
        try:
            access_token = await self._refresh_access_token()

            customer_id = GOOGLE_ADS_CUSTOMER_ID.replace("-", "")

            # Query GAQL para buscar campanhas com metricas
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            query = f"""
                SELECT
                    campaign.id,
                    campaign.name,
                    campaign.status,
                    campaign.advertising_channel_type,
                    metrics.impressions,
                    metrics.clicks,
                    metrics.cost_micros,
                    metrics.conversions,
                    metrics.ctr,
                    metrics.average_cpc
                FROM campaign
                WHERE segments.date BETWEEN '{start_date.strftime('%Y-%m-%d')}' AND '{end_date.strftime('%Y-%m-%d')}'
                ORDER BY metrics.impressions DESC
            """

            url = f"{self.BASE_URL}/customers/{customer_id}/googleAds:searchStream"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "developer-token": GOOGLE_ADS_DEV_TOKEN,
                "login-customer-id": GOOGLE_ADS_LOGIN_CUSTOMER_ID.replace("-", ""),
                "Content-Type": "application/json"
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json={"query": query}
                )

                if response.status_code == 200:
                    data = response.json()
                    campaigns = []

                    for result in data:
                        if "results" in result:
                            for row in result["results"]:
                                campaign = row.get("campaign", {})
                                metrics = row.get("metrics", {})

                                # Converter cost de micros para dolares
                                cost_micros = metrics.get("costMicros", 0)
                                cost = int(cost_micros) / 1_000_000 if cost_micros else 0

                                # Converter CPC de micros para dolares
                                avg_cpc_micros = metrics.get("averageCpc", 0)
                                avg_cpc = int(avg_cpc_micros) / 1_000_000 if avg_cpc_micros else 0

                                campaigns.append({
                                    "id": campaign.get("id", ""),
                                    "name": campaign.get("name", ""),
                                    "status": campaign.get("status", "UNKNOWN"),
                                    "type": campaign.get("advertisingChannelType", ""),
                                    "impressions": int(metrics.get("impressions", 0)),
                                    "clicks": int(metrics.get("clicks", 0)),
                                    "cost": round(cost, 2),
                                    "conversions": float(metrics.get("conversions", 0)),
                                    "ctr": round(float(metrics.get("ctr", 0)) * 100, 2),
                                    "avg_cpc": round(avg_cpc, 2),
                                    "platform": "Google Ads"
                                })

                    logger.info(f"[GOOGLE ADS] Fetched {len(campaigns)} campaigns")
                    return campaigns
                else:
                    logger.error(f"[GOOGLE ADS] API Error: {response.status_code} - {response.text}")
                    return []

        except Exception as e:
            logger.error(f"[GOOGLE ADS] Exception: {str(e)}")
            return []

    async def get_campaign_by_id(self, campaign_id: str, days: int = 30) -> Optional[Dict]:
        """Busca uma campanha especifica por ID"""
        campaigns = await self.get_campaigns(days)
        for campaign in campaigns:
            if str(campaign.get("id")) == str(campaign_id):
                return campaign
        return None


# ============================================
# META ADS API
# ============================================

class MetaAdsAPI:
    """Cliente para Meta Marketing API v21.0"""

    BASE_URL = "https://graph.facebook.com/v21.0"

    async def get_campaigns(self, days: int = 30) -> List[Dict]:
        """Busca campanhas e metricas do Meta Ads"""
        try:
            if not META_ACCESS_TOKEN or not META_AD_ACCOUNT_ID:
                logger.warning("[META ADS] Credentials not configured")
                return []

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # Buscar campanhas
            url = f"{self.BASE_URL}/{META_AD_ACCOUNT_ID}/campaigns"
            params = {
                "access_token": META_ACCESS_TOKEN,
                "fields": "id,name,status,objective",
                "limit": 100
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)

                if response.status_code != 200:
                    logger.error(f"[META ADS] Failed to fetch campaigns: {response.text}")
                    return []

                campaigns_data = response.json().get("data", [])
                campaigns = []

                for camp in campaigns_data:
                    # Buscar insights (metricas) para cada campanha
                    insights_url = f"{self.BASE_URL}/{camp['id']}/insights"
                    insights_params = {
                        "access_token": META_ACCESS_TOKEN,
                        "fields": "impressions,clicks,spend,actions,ctr,cpc",
                        "time_range": f'{{"since":"{start_date.strftime("%Y-%m-%d")}","until":"{end_date.strftime("%Y-%m-%d")}"}}'
                    }

                    insights_response = await client.get(insights_url, params=insights_params)

                    metrics = {}
                    if insights_response.status_code == 200:
                        insights_data = insights_response.json().get("data", [])
                        if insights_data:
                            metrics = insights_data[0]

                    # Extrair conversoes das actions
                    conversions = 0
                    actions = metrics.get("actions", [])
                    for action in actions:
                        if action.get("action_type") in ["lead", "purchase", "complete_registration"]:
                            conversions += int(action.get("value", 0))

                    campaigns.append({
                        "id": camp.get("id", ""),
                        "name": camp.get("name", ""),
                        "status": camp.get("status", "UNKNOWN"),
                        "type": camp.get("objective", ""),
                        "impressions": int(metrics.get("impressions", 0)),
                        "clicks": int(metrics.get("clicks", 0)),
                        "cost": round(float(metrics.get("spend", 0)), 2),
                        "conversions": conversions,
                        "ctr": round(float(metrics.get("ctr", 0)), 2),
                        "avg_cpc": round(float(metrics.get("cpc", 0)), 2),
                        "platform": "Meta Ads"
                    })

                logger.info(f"[META ADS] Fetched {len(campaigns)} campaigns")
                return campaigns

        except Exception as e:
            logger.error(f"[META ADS] Exception: {str(e)}")
            return []


# ============================================
# FUNCOES AUXILIARES
# ============================================

# Instancias globais
google_ads_api = GoogleAdsAPI()
meta_ads_api = MetaAdsAPI()

async def get_all_campaigns(days: int = 30) -> Dict:
    """Busca campanhas de todas as plataformas"""
    google_campaigns = await google_ads_api.get_campaigns(days)
    meta_campaigns = await meta_ads_api.get_campaigns(days)

    all_campaigns = google_campaigns + meta_campaigns

    # Calcular totais
    total_impressions = sum(c.get("impressions", 0) for c in all_campaigns)
    total_clicks = sum(c.get("clicks", 0) for c in all_campaigns)
    total_cost = sum(c.get("cost", 0) for c in all_campaigns)
    total_conversions = sum(c.get("conversions", 0) for c in all_campaigns)

    # Calcular CTR geral
    overall_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0

    # Calcular CPC medio
    avg_cpc = (total_cost / total_clicks) if total_clicks > 0 else 0

    return {
        "campaigns": all_campaigns,
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "cost": round(total_cost, 2),
            "conversions": total_conversions,
            "ctr": round(overall_ctr, 2),
            "avg_cpc": round(avg_cpc, 2),
            "active_campaigns": len([c for c in all_campaigns if c.get("status") in ["ENABLED", "ACTIVE"]])
        },
        "by_platform": {
            "google_ads": {
                "campaigns": len(google_campaigns),
                "cost": round(sum(c.get("cost", 0) for c in google_campaigns), 2),
                "impressions": sum(c.get("impressions", 0) for c in google_campaigns),
                "clicks": sum(c.get("clicks", 0) for c in google_campaigns)
            },
            "meta_ads": {
                "campaigns": len(meta_campaigns),
                "cost": round(sum(c.get("cost", 0) for c in meta_campaigns), 2),
                "impressions": sum(c.get("impressions", 0) for c in meta_campaigns),
                "clicks": sum(c.get("clicks", 0) for c in meta_campaigns)
            }
        }
    }


def check_credentials() -> Dict:
    """Verifica se as credenciais estao configuradas"""
    return {
        "google_ads": {
            "configured": all([
                GOOGLE_ADS_DEV_TOKEN,
                GOOGLE_ADS_CLIENT_ID,
                GOOGLE_ADS_CLIENT_SECRET,
                GOOGLE_ADS_REFRESH_TOKEN,
                GOOGLE_ADS_CUSTOMER_ID
            ]),
            "dev_token": bool(GOOGLE_ADS_DEV_TOKEN),
            "client_id": bool(GOOGLE_ADS_CLIENT_ID),
            "client_secret": bool(GOOGLE_ADS_CLIENT_SECRET),
            "refresh_token": bool(GOOGLE_ADS_REFRESH_TOKEN),
            "customer_id": bool(GOOGLE_ADS_CUSTOMER_ID)
        },
        "meta_ads": {
            "configured": all([
                META_APP_ID,
                META_ACCESS_TOKEN,
                META_AD_ACCOUNT_ID
            ]),
            "app_id": bool(META_APP_ID),
            "access_token": bool(META_ACCESS_TOKEN),
            "ad_account_id": bool(META_AD_ACCOUNT_ID)
        }
    }
