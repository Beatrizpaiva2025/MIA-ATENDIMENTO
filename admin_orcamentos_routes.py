"""
admin_orcamentos_routes.py - Gestão de Orçamentos
Lista e gerencia todos os orçamentos gerados pelo bot
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
from bson import ObjectId
import os
import logging
import re
from timezone_utils import format_datetime_est, utc_to_est

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
client = AsyncIOMotorClient(MONGODB_URI)
db = client.mia_database


def extrair_valor_orcamento(texto: str) -> float:
    """Extrai valor monetário do texto do orçamento"""
    if not texto:
        return 0.0

    # Padrões: $100.00, $100, R$100,00, R$ 100
    padroes = [
        r'\$\s*(\d+(?:[.,]\d{2})?)',
        r'R\$\s*(\d+(?:[.,]\d{2})?)',
        r'(\d+(?:[.,]\d{2})?)\s*(?:dollars?|dólares?|reais)'
    ]

    for padrao in padroes:
        match = re.search(padrao, texto, re.IGNORECASE)
        if match:
            valor = match.group(1).replace(',', '.')
            try:
                return float(valor)
            except:
                pass
    return 0.0


@router.get("/admin/orcamentos", response_class=HTMLResponse)
async def admin_orcamentos_page(request: Request):
    """Página principal de orçamentos"""
    try:
        return templates.TemplateResponse("admin_orcamentos.html", {
            "request": request
        })
    except Exception as e:
        logger.error(f"Erro ao carregar página de orçamentos: {e}")
        return HTMLResponse(content=f"Erro: {e}", status_code=500)


@router.get("/admin/orcamentos/api/list")
async def api_list_orcamentos(dias: int = 30, status: str = "todos"):
    """Lista orçamentos com filtros"""
    try:
        data_inicio = datetime.now() - timedelta(days=dias)

        # Filtro base
        filtro = {"created_at": {"$gte": data_inicio}}

        # Filtro de status
        if status != "todos":
            filtro["status"] = status

        # Buscar orçamentos
        orcamentos = await db.orcamentos.find(filtro).sort("created_at", -1).to_list(length=500)

        # Formatar para JSON
        resultado = []
        for orc in orcamentos:
            resultado.append({
                "id": str(orc.get("_id")),
                "phone": orc.get("phone", ""),
                "nome": orc.get("nome", "Não informado"),
                "documento_tipo": orc.get("documento_tipo", ""),
                "documento_paginas": orc.get("documento_paginas", 1),
                "idioma_origem": orc.get("idioma_origem", ""),
                "idioma_destino": orc.get("idioma_destino", ""),
                "valor": orc.get("valor", 0),
                "valor_formatado": f"${orc.get('valor', 0):.2f}",
                "status": orc.get("status", "pendente"),
                "origem_cliente": orc.get("origem_cliente", ""),
                "created_at": format_datetime_est(orc.get("created_at"), "%m/%d/%Y %H:%M"),
                "orcamento_texto": orc.get("orcamento_texto", "")[:200] + "..."
            })

        # Estatísticas
        total = len(resultado)
        total_valor = sum(o["valor"] for o in resultado)
        pendentes = len([o for o in resultado if o["status"] == "pendente"])
        confirmados = len([o for o in resultado if o["status"] == "confirmado"])
        pagos = len([o for o in resultado if o["status"] == "pago"])

        return {
            "success": True,
            "orcamentos": resultado,
            "stats": {
                "total": total,
                "total_valor": total_valor,
                "total_valor_formatado": f"${total_valor:.2f}",
                "pendentes": pendentes,
                "confirmados": confirmados,
                "pagos": pagos
            }
        }

    except Exception as e:
        logger.error(f"Erro ao listar orçamentos: {e}")
        return {"success": False, "error": str(e)}


@router.post("/admin/orcamentos/api/update-status")
async def api_update_status(request: Request):
    """Atualiza status de um orçamento"""
    try:
        data = await request.json()
        orcamento_id = data.get("id")
        novo_status = data.get("status")

        if not orcamento_id or not novo_status:
            return {"success": False, "error": "ID e status são obrigatórios"}

        result = await db.orcamentos.update_one(
            {"_id": ObjectId(orcamento_id)},
            {"$set": {"status": novo_status, "updated_at": datetime.now()}}
        )

        if result.modified_count > 0:
            return {"success": True, "message": f"Status atualizado para {novo_status}"}
        else:
            return {"success": False, "error": "Orçamento não encontrado"}

    except Exception as e:
        logger.error(f"Erro ao atualizar status: {e}")
        return {"success": False, "error": str(e)}


@router.get("/admin/orcamentos/api/stats")
async def api_orcamentos_stats():
    """Estatísticas gerais de orçamentos"""
    try:
        # Últimos 30 dias
        data_30d = datetime.now() - timedelta(days=30)

        # Total de orçamentos
        total = await db.orcamentos.count_documents({})
        total_30d = await db.orcamentos.count_documents({"created_at": {"$gte": data_30d}})

        # Por status
        pendentes = await db.orcamentos.count_documents({"status": "pendente"})
        confirmados = await db.orcamentos.count_documents({"status": "confirmado"})
        pagos = await db.orcamentos.count_documents({"status": "pago"})

        # Valor total
        pipeline = [
            {"$group": {"_id": None, "total": {"$sum": "$valor"}}}
        ]
        valor_result = await db.orcamentos.aggregate(pipeline).to_list(length=1)
        valor_total = valor_result[0]["total"] if valor_result else 0

        # Valor últimos 30 dias
        pipeline_30d = [
            {"$match": {"created_at": {"$gte": data_30d}}},
            {"$group": {"_id": None, "total": {"$sum": "$valor"}}}
        ]
        valor_30d_result = await db.orcamentos.aggregate(pipeline_30d).to_list(length=1)
        valor_30d = valor_30d_result[0]["total"] if valor_30d_result else 0

        return {
            "success": True,
            "stats": {
                "total": total,
                "total_30d": total_30d,
                "pendentes": pendentes,
                "confirmados": confirmados,
                "pagos": pagos,
                "valor_total": valor_total,
                "valor_total_formatado": f"${valor_total:.2f}",
                "valor_30d": valor_30d,
                "valor_30d_formatado": f"${valor_30d:.2f}",
                "taxa_conversao": f"{(pagos/total*100):.1f}%" if total > 0 else "0%"
            }
        }

    except Exception as e:
        logger.error(f"Erro ao buscar estatísticas: {e}")
        return {"success": False, "error": str(e)}
