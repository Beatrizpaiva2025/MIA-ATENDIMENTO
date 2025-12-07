"""
admin_conversas_routes.py - Dashboard de Conversas e Conversões
Relatórios de vendas, follow-up e análise de conversão
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
client = AsyncIOMotorClient(MONGODB_URI)
db = client.mia_database


@router.get("/admin/conversas", response_class=HTMLResponse)
async def admin_conversas_page(request: Request):
    """Página de histórico de conversas - Dashboard de Conversões"""
    try:
        return templates.TemplateResponse("admin_conversas.html", {
            "request": request
        })
    except Exception as e:
        logger.error(f"Erro ao carregar conversas: {e}")
        return templates.TemplateResponse("admin_conversas.html", {
            "request": request,
            "error": str(e)
        })


# ==================================================================
# API: ESTATÍSTICAS GERAIS
# ==================================================================
@router.get("/admin/conversas/api/stats")
async def api_get_stats(periodo: str = "7"):
    """Retorna estatísticas gerais do período"""
    try:
        dias = int(periodo)
        data_inicio = datetime.now() - timedelta(days=dias)

        # Total de conversas no período
        total_conversas = await db.conversas.count_documents({
            "timestamp": {"$gte": data_inicio}
        })

        # Clientes únicos
        clientes_unicos = await db.conversas.distinct("phone", {
            "timestamp": {"$gte": data_inicio}
        })

        # Conversões (pagamentos)
        conversoes = await db.conversoes.count_documents({
            "timestamp": {"$gte": data_inicio}
        })

        # Valor total das conversões
        pipeline_valor = [
            {"$match": {"timestamp": {"$gte": data_inicio}}},
            {"$group": {"_id": None, "total": {"$sum": "$valor"}}}
        ]
        valor_result = await db.conversoes.aggregate(pipeline_valor).to_list(1)
        valor_total = valor_result[0]["total"] if valor_result else 0

        # Atendimentos por IA vs Humano
        atendimentos_ia = await db.conversas.count_documents({
            "timestamp": {"$gte": data_inicio},
            "role": "assistant"
        })

        atendimentos_humano = await db.conversas.count_documents({
            "timestamp": {"$gte": data_inicio},
            "mode": "human"
        })

        # Taxa de conversão
        taxa_conversao = (conversoes / len(clientes_unicos) * 100) if clientes_unicos else 0

        return {
            "total_conversas": total_conversas,
            "clientes_unicos": len(clientes_unicos),
            "conversoes": conversoes,
            "valor_total": valor_total,
            "atendimentos_ia": atendimentos_ia,
            "atendimentos_humano": atendimentos_humano,
            "taxa_conversao": round(taxa_conversao, 1)
        }
    except Exception as e:
        logger.error(f"Erro ao buscar stats: {e}")
        return {"error": str(e)}


# ==================================================================
# API: DADOS PARA GRÁFICOS
# ==================================================================
@router.get("/admin/conversas/api/chart-data")
async def api_get_chart_data(periodo: str = "7"):
    """Retorna dados para gráficos de conversão por dia"""
    try:
        dias = int(periodo)
        data_inicio = datetime.now() - timedelta(days=dias)

        # Conversões por dia
        pipeline_conversoes = [
            {"$match": {"timestamp": {"$gte": data_inicio}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "total": {"$sum": 1},
                "valor": {"$sum": "$valor"}
            }},
            {"$sort": {"_id": 1}}
        ]
        conversoes_dia = await db.conversoes.aggregate(pipeline_conversoes).to_list(100)

        # Atendimentos por dia (IA vs Humano)
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

        # Gerar labels para todos os dias do período
        labels = []
        conversoes_data = []
        valores_data = []
        ia_data = []
        humano_data = []

        for i in range(dias):
            data = (datetime.now() - timedelta(days=dias-1-i)).strftime("%Y-%m-%d")
            labels.append(data)

            # Conversões
            conv = next((c for c in conversoes_dia if c["_id"] == data), None)
            conversoes_data.append(conv["total"] if conv else 0)
            valores_data.append(conv["valor"] if conv else 0)

            # IA
            ia = next((a for a in atendimentos_ia if a["_id"] == data), None)
            ia_data.append(ia["total"] if ia else 0)

            # Humano
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
        logger.error(f"Erro ao buscar chart data: {e}")
        return {"error": str(e)}


# ==================================================================
# API: CONVERSÕES (PAGAMENTOS)
# ==================================================================
@router.get("/admin/conversas/api/conversoes")
async def api_get_conversoes(periodo: str = "30"):
    """Retorna lista de conversões/pagamentos"""
    try:
        dias = int(periodo)
        data_inicio = datetime.now() - timedelta(days=dias)

        conversoes = await db.conversoes.find({
            "timestamp": {"$gte": data_inicio}
        }).sort("timestamp", -1).limit(50).to_list(50)

        result = []
        for c in conversoes:
            # Buscar tempo de atendimento
            primeira_msg = await db.conversas.find_one(
                {"phone": c.get("phone")},
                sort=[("timestamp", 1)]
            )

            tempo_atendimento = None
            if primeira_msg and c.get("timestamp"):
                delta = c["timestamp"] - primeira_msg.get("timestamp", c["timestamp"])
                tempo_atendimento = str(delta).split(".")[0]

            # Verificar se teve interação humana
            teve_humano = await db.conversas.find_one({
                "phone": c.get("phone"),
                "mode": "human"
            })

            result.append({
                "phone": c.get("phone", "N/A"),
                "valor": c.get("valor", 0),
                "timestamp": c.get("timestamp").strftime("%d/%m/%Y %H:%M") if c.get("timestamp") else "N/A",
                "tempo_atendimento": tempo_atendimento or "N/A",
                "tipo_atendimento": "Humano + IA" if teve_humano else "IA",
                "metodo": c.get("detection_method", "manual"),
                "mensagem": c.get("message", "")[:50]
            })

        return {"conversoes": result}
    except Exception as e:
        logger.error(f"Erro ao buscar conversões: {e}")
        return {"conversoes": [], "error": str(e)}


# ==================================================================
# API: LEADS PARA FOLLOW-UP (não fecharam)
# ==================================================================
@router.get("/admin/conversas/api/leads-followup")
async def api_get_leads_followup(periodo: str = "7"):
    """Retorna leads que não converteram para follow-up"""
    try:
        dias = int(periodo)
        data_inicio = datetime.now() - timedelta(days=dias)

        # Buscar todos os clientes que conversaram no período
        clientes_periodo = await db.conversas.distinct("phone", {
            "timestamp": {"$gte": data_inicio}
        })

        # Buscar clientes que converteram
        clientes_convertidos = await db.conversoes.distinct("phone", {
            "timestamp": {"$gte": data_inicio}
        })

        # Leads que NÃO converteram
        leads_nao_convertidos = [c for c in clientes_periodo if c not in clientes_convertidos]

        result = []
        for phone in leads_nao_convertidos[:30]:
            # Buscar última mensagem
            ultima_msg = await db.conversas.find_one(
                {"phone": phone},
                sort=[("timestamp", -1)]
            )

            # Contar total de mensagens
            total_msgs = await db.conversas.count_documents({"phone": phone})

            # Verificar se pediu orçamento (palavras-chave)
            pediu_orcamento = await db.conversas.find_one({
                "phone": phone,
                "message": {"$regex": "orcamento|preco|valor|quanto custa|price|quote", "$options": "i"}
            })

            # Calcular dias sem contato
            if ultima_msg and ultima_msg.get("timestamp"):
                dias_sem_contato = (datetime.now() - ultima_msg["timestamp"]).days
            else:
                dias_sem_contato = 0

            result.append({
                "phone": phone,
                "ultima_msg": ultima_msg.get("timestamp").strftime("%d/%m/%Y %H:%M") if ultima_msg and ultima_msg.get("timestamp") else "N/A",
                "total_msgs": total_msgs,
                "dias_sem_contato": dias_sem_contato,
                "pediu_orcamento": "Sim" if pediu_orcamento else "Nao",
                "prioridade": "Alta" if pediu_orcamento and dias_sem_contato <= 3 else ("Media" if pediu_orcamento else "Baixa"),
                "preview": ultima_msg.get("message", "")[:40] if ultima_msg else ""
            })

        # Ordenar por prioridade
        prioridade_ordem = {"Alta": 0, "Media": 1, "Baixa": 2}
        result.sort(key=lambda x: prioridade_ordem.get(x["prioridade"], 3))

        return {"leads": result, "total": len(leads_nao_convertidos)}
    except Exception as e:
        logger.error(f"Erro ao buscar leads: {e}")
        return {"leads": [], "error": str(e)}


# ==================================================================
# API: REGISTRAR CONVERSÃO MANUAL
# ==================================================================
@router.post("/admin/conversas/api/registrar-conversao")
async def api_registrar_conversao(request: Request):
    """Registra uma conversão/pagamento manualmente"""
    try:
        data = await request.json()

        conversao = {
            "phone": data.get("phone"),
            "valor": float(data.get("valor", 0)),
            "timestamp": datetime.now(),
            "detection_method": "manual",
            "message": data.get("observacao", "Registrado manualmente"),
            "canal": "WhatsApp"
        }

        await db.conversoes.insert_one(conversao)
        logger.info(f"Conversao registrada: {data.get('phone')} - $ {data.get('valor')}")

        return {"success": True, "message": "Conversao registrada com sucesso"}
    except Exception as e:
        logger.error(f"Erro ao registrar conversao: {e}")
        return {"success": False, "error": str(e)}


# ==================================================================
# API: RESUMO EXECUTIVO
# ==================================================================
@router.get("/admin/conversas/api/resumo")
async def api_get_resumo():
    """Retorna resumo executivo para dashboard"""
    try:
        hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        semana = datetime.now() - timedelta(days=7)
        mes = datetime.now() - timedelta(days=30)

        # Hoje
        conversoes_hoje = await db.conversoes.count_documents({"timestamp": {"$gte": hoje}})
        valor_hoje = await db.conversoes.aggregate([
            {"$match": {"timestamp": {"$gte": hoje}}},
            {"$group": {"_id": None, "total": {"$sum": "$valor"}}}
        ]).to_list(1)

        # Semana
        conversoes_semana = await db.conversoes.count_documents({"timestamp": {"$gte": semana}})
        valor_semana = await db.conversoes.aggregate([
            {"$match": {"timestamp": {"$gte": semana}}},
            {"$group": {"_id": None, "total": {"$sum": "$valor"}}}
        ]).to_list(1)

        # Mes
        conversoes_mes = await db.conversoes.count_documents({"timestamp": {"$gte": mes}})
        valor_mes = await db.conversoes.aggregate([
            {"$match": {"timestamp": {"$gte": mes}}},
            {"$group": {"_id": None, "total": {"$sum": "$valor"}}}
        ]).to_list(1)

        return {
            "hoje": {
                "conversoes": conversoes_hoje,
                "valor": valor_hoje[0]["total"] if valor_hoje else 0
            },
            "semana": {
                "conversoes": conversoes_semana,
                "valor": valor_semana[0]["total"] if valor_semana else 0
            },
            "mes": {
                "conversoes": conversoes_mes,
                "valor": valor_mes[0]["total"] if valor_mes else 0
            }
        }
    except Exception as e:
        logger.error(f"Erro ao buscar resumo: {e}")
        return {"error": str(e)}
