"""
============================================================
API REST v1 - Integracao Make.com / WhatsApp
============================================================
Endpoints para criar e gerenciar projetos (orcamentos) via API.
Autenticacao via API key no header X-API-Key.

Endpoints:
  POST /api/v1/projects          - Criar projeto
  POST /api/v1/projects/upload   - Upload de arquivo ao projeto
  GET  /api/v1/projects/{phone}  - Buscar projetos por telefone
  GET  /api/v1/projects          - Listar projetos (com filtros)
============================================================
"""

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from bson import ObjectId
from typing import Optional
import os
import logging

from google_drive import (
    save_whatsapp_media_to_drive,
    is_drive_enabled,
    get_client_folder,
    get_folder_link
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["API v1"])

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
client = AsyncIOMotorClient(MONGODB_URI)
db = client.mia_database

# API Key para autenticacao
API_KEY = os.getenv("MIA_API_KEY", "")


async def verify_api_key(request: Request):
    """Middleware de autenticacao por API key"""
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="API key not configured. Set MIA_API_KEY environment variable."
        )

    api_key = request.headers.get("X-API-Key", "")
    if not api_key or api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@router.post("/projects", dependencies=[Depends(verify_api_key)])
async def create_project(request: Request):
    """
    Cria um novo projeto/orcamento.

    Body JSON:
    {
        "phone": "5511999999999",          (obrigatorio)
        "nome": "Joao Silva",              (opcional)
        "documento_tipo": "Certidao",      (opcional)
        "documento_paginas": 3,            (opcional, default 1)
        "idioma_origem": "pt",             (opcional)
        "idioma_destino": "en",            (opcional)
        "valor": 74.97,                    (opcional)
        "status": "pendente",              (opcional, default "pendente")
        "origem": "Make.com/WhatsApp",     (opcional)
        "notas": "Cliente via Make.com"    (opcional)
    }
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    phone = data.get("phone", "").strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Field 'phone' is required")

    nome = data.get("nome", "").strip()
    status = data.get("status", "pendente")
    if status not in ("pendente", "confirmado", "pago"):
        raise HTTPException(status_code=400, detail="Status must be: pendente, confirmado, or pago")

    valor = data.get("valor", 0)
    try:
        valor = float(valor)
    except (ValueError, TypeError):
        valor = 0.0

    paginas = data.get("documento_paginas", 1)
    try:
        paginas = int(paginas)
    except (ValueError, TypeError):
        paginas = 1

    # Montar documento do orcamento
    orcamento = {
        "phone": phone,
        "nome": nome,
        "documento_tipo": data.get("documento_tipo", ""),
        "documento_paginas": paginas,
        "idioma_origem": data.get("idioma_origem", ""),
        "idioma_destino": data.get("idioma_destino", ""),
        "valor": valor,
        "valor_texto": f"${valor:.2f}" if valor else "",
        "orcamento_texto": data.get("notas", ""),
        "origem_cliente": data.get("origem", "API/Make.com"),
        "status": status,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "created_via": "api_v1"
    }

    # Vincular pasta do Google Drive se existir
    if is_drive_enabled() and phone:
        try:
            folder_id = get_client_folder(phone, nome)
            if folder_id:
                orcamento["google_drive_folder"] = get_folder_link(folder_id)
                orcamento["google_drive_folder_id"] = folder_id
        except Exception as e:
            logger.error(f"[API] Erro ao vincular Google Drive: {e}")

    result = await db.orcamentos.insert_one(orcamento)
    orcamento_id = str(result.inserted_id)

    logger.info(f"[API] Projeto criado: {orcamento_id} para {phone} ({nome})")

    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "project": {
                "id": orcamento_id,
                "phone": phone,
                "nome": nome,
                "status": status,
                "valor": valor,
                "google_drive_folder": orcamento.get("google_drive_folder", None),
                "created_at": orcamento["created_at"].isoformat()
            }
        }
    )


@router.post("/projects/upload", dependencies=[Depends(verify_api_key)])
async def upload_file_to_project(
    phone: str = Form(...),
    file: UploadFile = File(...),
    nome: str = Form(""),
    project_id: str = Form("")
):
    """
    Faz upload de um arquivo para o projeto de um cliente.
    O arquivo e salvo no Google Drive na pasta do cliente.

    Form Data:
        phone: Telefone do cliente (obrigatorio)
        file: Arquivo para upload (obrigatorio)
        nome: Nome do cliente (opcional)
        project_id: ID do projeto/orcamento (opcional, para vincular)
    """
    if not phone:
        raise HTTPException(status_code=400, detail="Field 'phone' is required")

    if not is_drive_enabled():
        raise HTTPException(
            status_code=503,
            detail="Google Drive not configured. Set GOOGLE_DRIVE_CREDENTIALS_JSON and GOOGLE_DRIVE_FOLDER_ID."
        )

    # Ler arquivo
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    filename = file.filename or f"upload_{int(datetime.now().timestamp())}"
    content_type = file.content_type or "application/octet-stream"

    # Determinar tipo de midia
    if "image" in content_type:
        media_type = "image"
    elif "audio" in content_type:
        media_type = "audio"
    else:
        media_type = "document"

    # Upload ao Google Drive
    result = await save_whatsapp_media_to_drive(
        file_bytes=file_bytes,
        phone=phone,
        media_type=media_type,
        filename=filename,
        mime_type=content_type,
        nome=nome
    )

    if not result:
        raise HTTPException(status_code=500, detail="Failed to upload file to Google Drive")

    # Se project_id fornecido, vincular Google Drive ao orcamento
    if project_id:
        try:
            await db.orcamentos.update_one(
                {"_id": ObjectId(project_id)},
                {"$set": {
                    "google_drive_folder": result["folder_link"],
                    "google_drive_folder_id": result["folder_id"],
                    "updated_at": datetime.now()
                }}
            )
        except Exception as e:
            logger.error(f"[API] Erro ao vincular arquivo ao projeto {project_id}: {e}")

    logger.info(f"[API] Arquivo uploaded: {filename} para {phone}")

    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "upload": {
                "filename": result["filename"],
                "file_link": result["file_link"],
                "folder_link": result["folder_link"],
                "phone": phone
            }
        }
    )


@router.get("/projects/{phone}", dependencies=[Depends(verify_api_key)])
async def get_projects_by_phone(phone: str, status: Optional[str] = None, limit: int = 50):
    """
    Busca projetos/orcamentos por telefone.

    Query params:
        status: Filtrar por status (pendente, confirmado, pago)
        limit: Limite de resultados (default 50)
    """
    if not phone:
        raise HTTPException(status_code=400, detail="Phone is required")

    filtro = {"phone": phone}
    if status:
        if status not in ("pendente", "confirmado", "pago"):
            raise HTTPException(status_code=400, detail="Status must be: pendente, confirmado, or pago")
        filtro["status"] = status

    if limit > 200:
        limit = 200

    orcamentos = await db.orcamentos.find(filtro).sort("created_at", -1).to_list(length=limit)

    resultado = []
    for orc in orcamentos:
        resultado.append({
            "id": str(orc.get("_id")),
            "phone": orc.get("phone", ""),
            "nome": orc.get("nome", ""),
            "documento_tipo": orc.get("documento_tipo", ""),
            "documento_paginas": orc.get("documento_paginas", 1),
            "idioma_origem": orc.get("idioma_origem", ""),
            "idioma_destino": orc.get("idioma_destino", ""),
            "valor": orc.get("valor", 0),
            "valor_formatado": f"${orc.get('valor', 0):.2f}",
            "status": orc.get("status", "pendente"),
            "origem_cliente": orc.get("origem_cliente", ""),
            "google_drive_folder": orc.get("google_drive_folder", None),
            "created_at": orc.get("created_at", datetime.now()).isoformat(),
            "updated_at": orc.get("updated_at", datetime.now()).isoformat()
        })

    return {
        "success": True,
        "phone": phone,
        "total": len(resultado),
        "projects": resultado
    }


@router.get("/projects", dependencies=[Depends(verify_api_key)])
async def list_projects(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """
    Lista todos os projetos com filtros opcionais.

    Query params:
        status: Filtrar por status (pendente, confirmado, pago)
        limit: Limite de resultados (default 50, max 200)
        offset: Pular N resultados (paginacao)
    """
    filtro = {}
    if status:
        if status not in ("pendente", "confirmado", "pago"):
            raise HTTPException(status_code=400, detail="Status must be: pendente, confirmado, or pago")
        filtro["status"] = status

    if limit > 200:
        limit = 200

    total = await db.orcamentos.count_documents(filtro)
    orcamentos = await db.orcamentos.find(filtro).sort("created_at", -1).skip(offset).limit(limit).to_list(length=limit)

    resultado = []
    for orc in orcamentos:
        resultado.append({
            "id": str(orc.get("_id")),
            "phone": orc.get("phone", ""),
            "nome": orc.get("nome", ""),
            "documento_tipo": orc.get("documento_tipo", ""),
            "documento_paginas": orc.get("documento_paginas", 1),
            "valor": orc.get("valor", 0),
            "status": orc.get("status", "pendente"),
            "google_drive_folder": orc.get("google_drive_folder", None),
            "created_at": orc.get("created_at", datetime.now()).isoformat()
        })

    return {
        "success": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "projects": resultado
    }
