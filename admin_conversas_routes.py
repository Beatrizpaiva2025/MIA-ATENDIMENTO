"""
admin_conversas_routes.py - CORRIGIDO E OTIMIZADO
Dashboard de Conversas e Conversões com tratamento de erros
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
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
# FUNÇÃO AUXILIAR: Extrair valor monetário de forma flexível
# ==================================================================
def extrair_valor(conversao_doc):
    """Extrai valor de forma flexível (suporta 'valor', 'value', etc)"""
    # Tentar diferentes campos possíveis
    valor = conversao_doc.get("valor") or conversao_doc.get("value") or 0
    
    # Se for string, tentar converter
    if isinstance(valor, str):
        try:
            # Remover símbolos comuns
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
# API: DEBUG - Verificar dados no banco
# ==================================================================
@router.get("/admin/conversas/api/debug")
async def api_debug_data():
    """Debug: mostra quantidade de dados no banco"""
    try:
        total_conversas = await db.conversas.count_documents({})
        total_conversoes = await db.conversoes.count_documents({})
        
        ultima_conversa = await db.conversas.find_one({}, sort=[("timestamp", -1)])
        ultima_conversao = await db.conversoes.find_one({}, sort=[("timestamp", -1)])
        
        clientes = await db.conversas.distinct("phone")
        amostra_conversa = await db.conversas.find_one({})
        amostra_conversao = await db.conversoes.find_one({})

        return {
            "total_conversas": total_conversas,
            "total_conversoes": total_conversoes,
            "clientes_unicos": len(clientes),
            "ultima_conversa": str(ultima_conversa.get("timestamp")) if ultima_conversa else None,
            "ultima_conversao": str(ultima_conversao.get("timestamp")) if ultima_conversao else None,
            "campos_conversa": list(amostra_conversa.keys()) if amostra_conversa else [],
            "campos_conversao": list(amostra_conversao.keys()) if amostra_conversao else [],
            "amostra_phone": amostra_conversa.get("phone") if amostra_conversa else None,
            "amostra_conversao": {k: str(v)[:50] for k, v in amostra_conversao.items()} if amostra_conversao else {}
        }
    except Exception as e:
        logger.error(f"Erro debug: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e), "traceback": traceback.format_exc()}


# ==================================================================
# API: ESTATÍSTICAS GERAIS
# ==================================================================
@router.get("/admin/conversas/api/stats")
async def api_get_stats(periodo: str = "7"):
    """Retorna estatísticas gerais do período"""
    try:
        dias = int(periodo)
        data_inicio = datetime.now() - timedelta(days=dias)

        # Total de conversas
        total_conversas = await db.conversas.count_documents({
            "timestamp": {"$gte": data_inicio}
        })

        # Clientes únicos
        clientes_unicos = await db.conversas.distinct("phone", {
            "timestamp": {"$gte": data_inicio}
        })

        # Conversões no período
        conversoes = await db.conversoes.count_documents({
            "timestamp": {"$gte": data_inicio}
        })

        # Valor total (agregação flexível)
        conversoes_docs = await db.conversoes.find({
            "timestamp": {"$gte": data_inicio}
        }).to_list(1000)
        
        valor_total = sum(extrair_valor(doc) for doc in conversoes_docs)

        # Atendimentos IA
        atendimentos_ia = await db.conversas.count_documents({
            "timestamp": {"$gte": data_inicio},
            "role": "assistant"
        })

        # Atendimentos Humano
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
            "valor_total": round(valor_total, 2),
            "atendimentos_ia": atendimentos_ia,
            "atendimentos_humano": atendimentos_humano,
            "taxa_conversao": round(taxa_conversao, 1)
        }
    except Exception as e:
        logger.error(f"Erro ao buscar stats: {e}")
        logger.error(traceback.format_exc())
        return {
            "error": str(e),
            "total_conversas": 0,
            "clientes_unicos": 0,
            "conversoes": 0,
            "valor_total": 0,
            "atendimentos_ia": 0,
            "atendimentos_humano": 0,
            "taxa_conversao": 0
        }


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
        conversoes_docs = await db.conversoes.find({
            "timestamp": {"$gte": data_inicio}
        }).to_list(1000)
        
        # Organizar por data
        conversoes_por_dia = {}
        for doc in conversoes_docs:
            if doc.get("timestamp"):
                data = doc["timestamp"].strftime("%Y-%m-%d")
                if data not in conversoes_por_dia:
                    conversoes_por_dia[data] = {"total": 0, "valor": 0}
                conversoes_por_dia[data]["total"] += 1
                conversoes_por_dia[data]["valor"] += extrair_valor(doc)

        # IA por dia
        pipeline_ia = [
            {"$match": {"timestamp": {"$gte": data_inicio}, "role": "assistant"}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "total": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        atendimentos_ia = await db.conversas.aggregate(pipeline_ia).to_list(100)

        # Humano por dia
        pipeline_humano = [
            {"$match": {"timestamp": {"$gte": data_inicio}, "mode": "human"}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "total": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        atendimentos_humano = await db.conversas.aggregate(pipeline_humano).to_list(100)

        # Montar arrays para Chart.js
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
        logger.error(f"Erro ao buscar chart data: {e}")
        logger.error(traceback.format_exc())
        return {
            "error": str(e),
            "labels": [],
            "conversoes": [],
            "valores": [],
            "atendimentos_ia": [],
            "atendimentos_humano": []
        }


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
            try:
                phone = c.get("phone", "N/A")
                
                # Primeira mensagem do cliente
                primeira_msg = await db.conversas.find_one(
                    {"phone": phone},
                    sort=[("timestamp", 1)]
                )

                # Calcular tempo de atendimento
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

                # Verificar se teve atendimento humano
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
                logger.error(f"Erro ao processar conversão: {item_error}")
                continue

        return {"conversoes": result}
    except Exception as e:
        logger.error(f"Erro ao buscar conversões: {e}")
        logger.error(traceback.format_exc())
        return {"conversoes": [], "error": str(e)}


# ==================================================================
# API: LEADS PARA FOLLOW-UP
# ==================================================================
@router.get("/admin/conversas/api/leads-followup")
async def api_get_leads_followup(periodo: str = "7"):
    """Retorna leads que não converteram para follow-up"""
    try:
        dias = int(periodo)
        data_inicio = datetime.now() - timedelta(days=dias)

        # Clientes do período
        clientes_periodo = await db.conversas.distinct("phone", {
            "timestamp": {"$gte": data_inicio}
        })

        # Clientes que converteram
        clientes_convertidos = await db.conversoes.distinct("phone", {
            "timestamp": {"$gte": data_inicio}
        })

        # Leads não convertidos
        leads_nao_convertidos = [c for c in clientes_periodo if c not in clientes_convertidos]

        result = []
        for phone in leads_nao_convertidos[:30]:
            try:
                # Última mensagem
                ultima_msg = await db.conversas.find_one(
                    {"phone": phone},
                    sort=[("timestamp", -1)]
                )

                if not ultima_msg or not ultima_msg.get("timestamp"):
                    continue

                # Total de mensagens
                total_msgs = await db.conversas.count_documents({"phone": phone})

                # Pediu orçamento?
                pediu_orcamento = await db.conversas.find_one({
                    "phone": phone,
                    "$or": [
                        {"message": {"$regex": "quote|price|cost|how much|quanto", "$options": "i"}},
                        {"message": {"$regex": "orcamento|preco|valor|custo", "$options": "i"}}
                    ]
                })

                # Dias sem contato
                dias_sem_contato = (datetime.now() - ultima_msg["timestamp"]).days

                # Prioridade
                if pediu_orcamento and dias_sem_contato <= 3:
                    prioridade = "High"
                elif pediu_orcamento:
                    prioridade = "Medium"
                else:
                    prioridade = "Low"

                result.append({
                    "phone": phone,
                    "ultima_msg": ultima_msg["timestamp"].strftime("%m/%d/%Y %H:%M"),
                    "total_msgs": total_msgs,
                    "dias_sem_contato": dias_sem_contato,
                    "pediu_orcamento": "Yes" if pediu_orcamento else "No",
                    "prioridade": prioridade,
                    "preview": ultima_msg.get("message", "")[:40]
                })
            except Exception as item_error:
                logger.error(f"Erro ao processar lead {phone}: {item_error}")
                continue

        # Ordenar por prioridade
        prioridade_ordem = {"High": 0, "Medium": 1, "Low": 2}
        result.sort(key=lambda x: prioridade_ordem.get(x["prioridade"], 3))

        return {"leads": result, "total": len(leads_nao_convertidos)}
    except Exception as e:
        logger.error(f"Erro ao buscar leads: {e}")
        logger.error(traceback.format_exc())
        return {"leads": [], "total": 0, "error": str(e)}


# ==================================================================
# API: REGISTRAR CONVERSÃO MANUAL
# ==================================================================
@router.post("/admin/conversas/api/registrar-conversao")
async def api_registrar_conversao(request: Request):
    """Registra uma conversão/pagamento manualmente"""
    try:
        data = await request.json()

        # Validar dados
        phone = data.get("phone", "").strip()
        if not phone:
            return {"success": False, "error": "Phone number required"}

        try:
            valor = float(data.get("valor", 0))
        except:
            return {"success": False, "error": "Invalid value"}

        if valor <= 0:
            return {"success": False, "error": "Value must be greater than 0"}

        # Criar documento de conversão
        conversao = {
            "phone": phone,
            "valor": valor,  # Salvar com 'valor' para compatibilidade
            "value": valor,  # Também salvar com 'value' para flexibilidade
            "timestamp": datetime.now(),
            "detection_method": "manual",
            "message": data.get("observacao", "Manual entry"),
            "canal": "WhatsApp",
            "registered_by": "admin"
        }

        result = await db.conversoes.insert_one(conversao)
        logger.info(f"✅ Conversão registrada: {phone} - ${valor}")

        return {"success": True, "message": "Conversion saved successfully", "id": str(result.inserted_id)}
    except Exception as e:
        logger.error(f"❌ Erro ao salvar conversão: {e}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}
