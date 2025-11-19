"""
Rotas do Painel Admin - Controle de Atendimento IA vs Humano
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from typing import Optional
import logging
from controle_atendimento import (
    verificar_estado_conversa,
    forcar_estado,
    obter_info_controle,
    listar_atendimentos_ativos,
    estatisticas_atendimento,
    ESTADO_IA,
    ESTADO_HUMANO,
    ESTADO_DESLIGADA
)

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/admin/controle", tags=["Controle Atendimento"])

# ============================================================
# PÁGINA: CONTROLE DE ATENDIMENTO
# ============================================================

@router.get("/", response_class=HTMLResponse)
async def pagina_controle(request: Request):
    """Página de controle de atendimento IA vs Humano"""
    try:
        # Buscar atendimentos ativos
        atendimentos = await listar_atendimentos_ativos()
        
        # Formatar timestamps
        for atendimento in atendimentos:
            if atendimento.get("timestamp"):
                atendimento["timestamp_formatted"] = atendimento["timestamp"].strftime("%d/%m/%Y %H:%M")
            atendimento["_id"] = str(atendimento["_id"])
        
        # Estatísticas
        stats = await estatisticas_atendimento()
        
        return templates.TemplateResponse("admin_controle.html", {
            "request": request,
            "atendimentos": atendimentos,
            "stats": stats
        })
        
    except Exception as e:
        logger.error(f"Erro na página de controle: {e}")
        return templates.TemplateResponse("admin_controle.html", {
            "request": request,
            "error": str(e),
            "atendimentos": [],
            "stats": {}
        })

# ============================================================
# API: VERIFICAR ESTADO
# ============================================================

@router.get("/api/estado/{phone}")
async def api_verificar_estado(phone: str):
    """Verifica estado atual de um contato"""
    try:
        info = await obter_info_controle(phone)
        return JSONResponse(info)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# API: ALTERNAR PARA IA
# ============================================================

@router.post("/api/ativar-ia/{phone}")
async def api_ativar_ia(phone: str):
    """Ativa IA para um contato"""
    try:
        await forcar_estado(phone, ESTADO_IA)
        
        return JSONResponse({
            "status": "success",
            "phone": phone,
            "novo_estado": ESTADO_IA,
            "mensagem": "IA ativada com sucesso"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# API: ALTERNAR PARA HUMANO
# ============================================================

@router.post("/api/ativar-humano/{phone}")
async def api_ativar_humano(phone: str, atendente: Optional[str] = "Admin"):
    """Ativa atendimento humano para um contato"""
    try:
        await forcar_estado(phone, ESTADO_HUMANO, atendente)
        
        return JSONResponse({
            "status": "success",
            "phone": phone,
            "novo_estado": ESTADO_HUMANO,
            "atendente": atendente,
            "mensagem": "Atendimento humano ativado"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# API: DESLIGAR IA
# ============================================================

@router.post("/api/desligar-ia/{phone}")
async def api_desligar_ia(phone: str, atendente: Optional[str] = "Admin"):
    """Desliga IA completamente para um contato"""
    try:
        await forcar_estado(phone, ESTADO_DESLIGADA, atendente)
        
        return JSONResponse({
            "status": "success",
            "phone": phone,
            "novo_estado": ESTADO_DESLIGADA,
            "atendente": atendente,
            "mensagem": "IA desligada"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# API: ESTATÍSTICAS
# ============================================================

@router.get("/api/stats")
async def api_estatisticas():
    """Retorna estatísticas de atendimento"""
    try:
        stats = await estatisticas_atendimento()
        return JSONResponse(stats)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# API: LISTAR ATIVOS
# ============================================================

@router.get("/api/ativos")
async def api_listar_ativos():
    """Lista todos os atendimentos não-IA ativos"""
    try:
        atendimentos = await listar_atendimentos_ativos()
        
        # Formatar para JSON
        for atendimento in atendimentos:
            atendimento["_id"] = str(atendimento["_id"])
            if atendimento.get("timestamp"):
                atendimento["timestamp"] = atendimento["timestamp"].isoformat()
        
        return JSONResponse({
            "total": len(atendimentos),
            "atendimentos": atendimentos
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
