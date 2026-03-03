"""
============================================================
INTEGRACAO GOOGLE DRIVE - Upload de documentos do WhatsApp
============================================================
Salva documentos/imagens recebidos pelo WhatsApp numa pasta
organizada no Google Drive usando Service Account.

Estrutura: WhatsApp Documents/{phone}/{data}_{filename}

Configuracao:
  - GOOGLE_DRIVE_CREDENTIALS_JSON: JSON da service account (env var)
  - GOOGLE_DRIVE_FOLDER_ID: ID da pasta raiz "WhatsApp Documents"
============================================================
"""

import os
import json
import logging
import threading
from datetime import datetime
from typing import Optional
from io import BytesIO

logger = logging.getLogger(__name__)

# Google Drive config
GOOGLE_DRIVE_CREDENTIALS_JSON = os.getenv("GOOGLE_DRIVE_CREDENTIALS_JSON", "")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

# Cache de folder IDs por cliente para evitar buscas repetidas
_client_folder_cache: dict = {}

# Flag para indicar se o Drive esta configurado
_drive_enabled: bool = False
_drive_service = None

# Lock para serializar operacoes do Google Drive (httplib2 nao e thread-safe)
_drive_lock = threading.Lock()


def _init_drive_service():
    """Inicializa o servico do Google Drive com Service Account"""
    global _drive_enabled, _drive_service

    if _drive_service is not None:
        return _drive_service

    if not GOOGLE_DRIVE_CREDENTIALS_JSON:
        logger.warning("[GDRIVE] GOOGLE_DRIVE_CREDENTIALS_JSON nao configurado - upload desabilitado")
        _drive_enabled = False
        return None

    if not GOOGLE_DRIVE_FOLDER_ID:
        logger.warning("[GDRIVE] GOOGLE_DRIVE_FOLDER_ID nao configurado - upload desabilitado")
        _drive_enabled = False
        return None

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials_info = json.loads(GOOGLE_DRIVE_CREDENTIALS_JSON)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        _drive_service = build("drive", "v3", credentials=credentials)
        _drive_enabled = True
        logger.info("[GDRIVE] Servico Google Drive inicializado com sucesso")
        return _drive_service

    except ImportError:
        logger.error("[GDRIVE] google-api-python-client nao instalado. Rode: pip install google-api-python-client google-auth")
        _drive_enabled = False
        return None
    except Exception as e:
        logger.error(f"[GDRIVE] Erro ao inicializar Drive: {e}")
        _drive_enabled = False
        return None


def is_drive_enabled() -> bool:
    """Verifica se o Google Drive esta configurado e habilitado"""
    if _drive_service is None:
        _init_drive_service()
    return _drive_enabled


def _find_folder(service, folder_name: str, parent_id: str) -> Optional[str]:
    """Busca uma pasta pelo nome dentro de um parent. Retorna o ID ou None."""
    try:
        query = (
            f"name = '{folder_name}' and "
            f"'{parent_id}' in parents and "
            f"mimeType = 'application/vnd.google-apps.folder' and "
            f"trashed = false"
        )
        results = service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name)",
            pageSize=1
        ).execute()

        files = results.get("files", [])
        if files:
            return files[0]["id"]
        return None

    except Exception as e:
        logger.error(f"[GDRIVE] Erro ao buscar pasta '{folder_name}': {e}")
        return None


def _create_folder(service, folder_name: str, parent_id: str) -> Optional[str]:
    """Cria uma pasta no Google Drive. Retorna o ID."""
    try:
        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id]
        }
        folder = service.files().create(
            body=file_metadata,
            fields="id"
        ).execute()

        folder_id = folder.get("id")
        logger.info(f"[GDRIVE] Pasta criada: '{folder_name}' (ID: {folder_id})")
        return folder_id

    except Exception as e:
        logger.error(f"[GDRIVE] Erro ao criar pasta '{folder_name}': {e}")
        return None


def _get_or_create_folder(service, folder_name: str, parent_id: str) -> Optional[str]:
    """Busca ou cria uma pasta. Retorna o ID."""
    folder_id = _find_folder(service, folder_name, parent_id)
    if folder_id:
        return folder_id
    return _create_folder(service, folder_name, parent_id)


def get_client_folder(phone: str, nome: str = "") -> Optional[str]:
    """
    Obtem (ou cria) a pasta do cliente no Google Drive.
    Usa SEMPRE apenas o telefone como nome da pasta para evitar
    race conditions entre chamadas com/sem nome do cliente.
    Estrutura: WhatsApp Documents/{phone}/
    Retorna o ID da pasta ou None se Drive nao estiver configurado.
    """
    service = _init_drive_service()
    if not service:
        return None

    # Verificar cache
    cache_key = phone
    if cache_key in _client_folder_cache:
        return _client_folder_cache[cache_key]

    # Usar APENAS o telefone como nome da pasta (evita pastas duplicadas)
    folder_name = phone

    with _drive_lock:
        # Re-verificar cache depois do lock (outra thread pode ter preenchido)
        if cache_key in _client_folder_cache:
            return _client_folder_cache[cache_key]

        folder_id = _get_or_create_folder(service, folder_name, GOOGLE_DRIVE_FOLDER_ID)
        if folder_id:
            _client_folder_cache[cache_key] = folder_id
            logger.info(f"[GDRIVE] Pasta do cliente obtida: '{folder_name}' (ID: {folder_id})")

    return folder_id


def get_folder_link(folder_id: str) -> str:
    """Retorna o link web da pasta no Google Drive"""
    return f"https://drive.google.com/drive/folders/{folder_id}"


def upload_file_to_drive(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    phone: str,
    nome: str = ""
) -> Optional[dict]:
    """
    Faz upload de um arquivo para o Google Drive na pasta do cliente.

    Args:
        file_bytes: Conteudo do arquivo em bytes
        filename: Nome do arquivo
        mime_type: Tipo MIME (ex: image/jpeg, application/pdf)
        phone: Telefone do cliente
        nome: Nome do cliente (opcional)

    Returns:
        dict com {file_id, file_link, folder_id, folder_link} ou None se falhar
    """
    service = _init_drive_service()
    if not service:
        logger.error(f"[GDRIVE] Servico nao inicializado - upload cancelado para {phone}")
        return None

    try:
        from googleapiclient.http import MediaIoBaseUpload

        # Obter pasta do cliente
        logger.info(f"[GDRIVE] Iniciando upload: '{filename}' ({len(file_bytes)} bytes) para {phone}")
        folder_id = get_client_folder(phone, nome)
        if not folder_id:
            logger.error(f"[GDRIVE] Nao conseguiu criar/obter pasta para {phone}")
            return None

        # Prefixar filename com data/hora
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_filename = f"{timestamp}_{filename}"

        # Upload com lock para thread-safety (httplib2 nao e thread-safe)
        file_metadata = {
            "name": final_filename,
            "parents": [folder_id]
        }

        media = MediaIoBaseUpload(
            BytesIO(file_bytes),
            mimetype=mime_type,
            resumable=True
        )

        with _drive_lock:
            file_result = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink"
            ).execute()

        file_id = file_result.get("id")
        file_link = file_result.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")

        logger.info(f"[GDRIVE] Upload CONCLUIDO: {final_filename} para {phone} (ID: {file_id})")

        return {
            "file_id": file_id,
            "file_link": file_link,
            "folder_id": folder_id,
            "folder_link": get_folder_link(folder_id),
            "filename": final_filename
        }

    except Exception as e:
        logger.error(f"[GDRIVE] ERRO ao fazer upload de '{filename}' para {phone}: {e}", exc_info=True)
        return None


async def upload_file_to_drive_async(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    phone: str,
    nome: str = ""
) -> Optional[dict]:
    """
    Versao async do upload - executa em thread separada para nao bloquear o event loop.
    A Google Drive API e sincrona, entao rodamos em executor.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            upload_file_to_drive,
            file_bytes,
            filename,
            mime_type,
            phone,
            nome
        )
        return result
    except Exception as e:
        logger.error(f"[GDRIVE] Erro async upload '{filename}' para {phone}: {e}", exc_info=True)
        return None


async def save_whatsapp_media_to_drive(
    file_bytes: bytes,
    phone: str,
    media_type: str = "image",
    filename: str = "",
    mime_type: str = "",
    nome: str = ""
) -> Optional[dict]:
    """
    Funcao principal para salvar midia do WhatsApp no Google Drive.
    Determina automaticamente o nome e mime type baseado no tipo de midia.

    Args:
        file_bytes: Conteudo do arquivo
        phone: Telefone do cliente
        media_type: "image", "audio", "document"
        filename: Nome original do arquivo (opcional)
        mime_type: Tipo MIME (opcional, sera inferido)
        nome: Nome do cliente (opcional)

    Returns:
        dict com info do upload ou None
    """
    if not is_drive_enabled():
        logger.warning(f"[GDRIVE] Drive desabilitado - ignorando upload para {phone}")
        return None

    if not file_bytes:
        logger.warning(f"[GDRIVE] file_bytes vazio - ignorando upload para {phone}")
        return None

    # Determinar filename e mime_type se nao fornecidos
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if media_type == "image":
            filename = f"imagem_{timestamp}.jpg"
        elif media_type == "audio":
            filename = f"audio_{timestamp}.ogg"
        elif media_type == "document":
            filename = f"documento_{timestamp}.pdf"
        else:
            filename = f"arquivo_{timestamp}"

    if not mime_type:
        if media_type == "image":
            mime_type = "image/jpeg"
        elif media_type == "audio":
            mime_type = "audio/ogg"
        elif media_type == "document":
            mime_type = "application/pdf"
        else:
            mime_type = "application/octet-stream"

    logger.info(f"[GDRIVE] Salvando midia: {filename} ({media_type}, {len(file_bytes)} bytes) para {phone}")

    result = await upload_file_to_drive_async(
        file_bytes=file_bytes,
        filename=filename,
        mime_type=mime_type,
        phone=phone,
        nome=nome
    )

    if result:
        logger.info(f"[GDRIVE] Midia salva com sucesso para {phone}: {result['filename']}")
    else:
        logger.error(f"[GDRIVE] FALHA ao salvar midia '{filename}' para {phone}")

    return result
