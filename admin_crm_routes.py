"""
admin_crm_routes.py - Sistema CRM para gerenciar contatos
Captura automatica de telefones do WhatsApp e emails
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
from bson import ObjectId
import os
import re
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/crm", tags=["Admin CRM"])
templates = Jinja2Templates(directory="templates")

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
client = AsyncIOMotorClient(MONGODB_URI)
db = client.mia_database


# ============================================================
# FUNCOES AUXILIARES
# ============================================================

def extrair_email_do_texto(texto: str) -> str:
    """Extrai email de um texto"""
    if not texto:
        return None
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    match = re.search(email_pattern, texto)
    return match.group(0) if match else None


async def criar_ou_atualizar_contato(phone: str, dados: dict = None):
    """Cria ou atualiza um contato no CRM"""
    if not phone:
        return None

    # Limpar phone
    phone_limpo = re.sub(r'[^\d]', '', phone.replace('@lid', '').replace('@c.us', ''))

    # Buscar contato existente
    contato = await db.crm_contacts.find_one({"phone": phone_limpo})

    agora = datetime.now()

    if contato:
        # Atualizar contato existente
        update_data = {
            "last_contact": agora,
            "total_interactions": contato.get("total_interactions", 0) + 1
        }

        if dados:
            if dados.get("nome") and not contato.get("nome"):
                update_data["nome"] = dados["nome"]
            if dados.get("email") and not contato.get("email"):
                update_data["email"] = dados["email"]
            if dados.get("idioma"):
                update_data["idioma"] = dados["idioma"]
            if dados.get("origem"):
                update_data["origem"] = dados["origem"]

        await db.crm_contacts.update_one(
            {"_id": contato["_id"]},
            {"$set": update_data}
        )
        return contato["_id"]
    else:
        # Criar novo contato
        novo_contato = {
            "phone": phone_limpo,
            "nome": dados.get("nome") if dados else None,
            "email": dados.get("email") if dados else None,
            "idioma": dados.get("idioma", "pt") if dados else "pt",
            "origem": dados.get("origem") if dados else "WhatsApp",
            "status": "novo",
            "etapa": "inicial",
            "tags": [],
            "notas": "",
            "valor_orcamento": None,
            "total_interactions": 1,
            "first_contact": agora,
            "last_contact": agora,
            "created_at": agora,
            "updated_at": agora
        }

        result = await db.crm_contacts.insert_one(novo_contato)
        return result.inserted_id


async def extrair_info_conversa(phone: str):
    """Extrai informacoes de um contato a partir das conversas"""
    conversas = await db.conversas.find({"phone": phone}).sort("timestamp", -1).limit(50).to_list(50)

    nome = None
    email = None
    idioma = "pt"

    # Buscar no cliente_estados
    estado = await db.cliente_estados.find_one({"phone": phone})
    if estado:
        nome = estado.get("nome")
        idioma = estado.get("idioma", "pt")

    # Procurar email nas conversas
    for conv in conversas:
        msg = conv.get("message", "")
        found_email = extrair_email_do_texto(msg)
        if found_email:
            email = found_email
            break

    return {
        "nome": nome,
        "email": email,
        "idioma": idioma
    }


# ============================================================
# PAGINA PRINCIPAL
# ============================================================

@router.get("/", response_class=HTMLResponse)
async def crm_page(request: Request):
    """Pagina principal do CRM"""
    return templates.TemplateResponse("admin_crm.html", {"request": request})


# ============================================================
# API - LISTAR CONTATOS
# ============================================================

@router.get("/api/contacts")
async def api_list_contacts(
    status: str = None,
    search: str = None,
    limit: int = 50,
    skip: int = 0
):
    """Lista contatos do CRM com filtros"""
    try:
        query = {}

        if status and status != "all":
            query["status"] = status

        if search:
            query["$or"] = [
                {"phone": {"$regex": search, "$options": "i"}},
                {"nome": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}}
            ]

        total = await db.crm_contacts.count_documents(query)

        contatos = await db.crm_contacts.find(query).sort("last_contact", -1).skip(skip).limit(limit).to_list(limit)

        # Formatar para JSON
        contatos_formatados = []
        for c in contatos:
            contatos_formatados.append({
                "id": str(c["_id"]),
                "phone": c.get("phone", ""),
                "nome": c.get("nome", ""),
                "email": c.get("email", ""),
                "idioma": c.get("idioma", "pt"),
                "origem": c.get("origem", "WhatsApp"),
                "status": c.get("status", "novo"),
                "etapa": c.get("etapa", "inicial"),
                "tags": c.get("tags", []),
                "notas": c.get("notas", ""),
                "valor_orcamento": c.get("valor_orcamento"),
                "total_interactions": c.get("total_interactions", 0),
                "first_contact": c.get("first_contact", c.get("created_at")).strftime("%Y-%m-%d %H:%M") if c.get("first_contact") or c.get("created_at") else "",
                "last_contact": c.get("last_contact", c.get("updated_at")).strftime("%Y-%m-%d %H:%M") if c.get("last_contact") or c.get("updated_at") else ""
            })

        return {
            "success": True,
            "total": total,
            "contacts": contatos_formatados
        }

    except Exception as e:
        logger.error(f"Erro ao listar contatos: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# API - OBTER CONTATO
# ============================================================

@router.get("/api/contact/{contact_id}")
async def api_get_contact(contact_id: str):
    """Obtem detalhes de um contato"""
    try:
        contato = await db.crm_contacts.find_one({"_id": ObjectId(contact_id)})

        if not contato:
            return {"success": False, "error": "Contato nao encontrado"}

        # Buscar conversas recentes
        conversas = await db.conversas.find(
            {"phone": {"$regex": contato["phone"]}}
        ).sort("timestamp", -1).limit(20).to_list(20)

        conversas_formatadas = []
        for conv in conversas:
            conversas_formatadas.append({
                "role": conv.get("role", "user"),
                "message": conv.get("message", "")[:200],
                "timestamp": conv.get("timestamp").strftime("%Y-%m-%d %H:%M") if conv.get("timestamp") else ""
            })

        return {
            "success": True,
            "contact": {
                "id": str(contato["_id"]),
                "phone": contato.get("phone", ""),
                "nome": contato.get("nome", ""),
                "email": contato.get("email", ""),
                "idioma": contato.get("idioma", "pt"),
                "origem": contato.get("origem", "WhatsApp"),
                "status": contato.get("status", "novo"),
                "etapa": contato.get("etapa", "inicial"),
                "tags": contato.get("tags", []),
                "notas": contato.get("notas", ""),
                "valor_orcamento": contato.get("valor_orcamento"),
                "total_interactions": contato.get("total_interactions", 0)
            },
            "conversas": conversas_formatadas
        }

    except Exception as e:
        logger.error(f"Erro ao obter contato: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# API - CRIAR CONTATO
# ============================================================

@router.post("/api/contact")
async def api_create_contact(request: Request):
    """Cria um novo contato manualmente"""
    try:
        data = await request.json()

        phone = data.get("phone", "").strip()
        if not phone:
            return {"success": False, "error": "Telefone obrigatorio"}

        # Verificar se ja existe
        phone_limpo = re.sub(r'[^\d]', '', phone)
        existente = await db.crm_contacts.find_one({"phone": phone_limpo})
        if existente:
            return {"success": False, "error": "Contato ja existe"}

        agora = datetime.now()

        novo_contato = {
            "phone": phone_limpo,
            "nome": data.get("nome", "").strip() or None,
            "email": data.get("email", "").strip() or None,
            "idioma": data.get("idioma", "pt"),
            "origem": data.get("origem", "Manual"),
            "status": data.get("status", "novo"),
            "etapa": "inicial",
            "tags": data.get("tags", []),
            "notas": data.get("notas", ""),
            "valor_orcamento": None,
            "total_interactions": 0,
            "first_contact": agora,
            "last_contact": agora,
            "created_at": agora,
            "updated_at": agora
        }

        result = await db.crm_contacts.insert_one(novo_contato)

        return {
            "success": True,
            "id": str(result.inserted_id),
            "message": "Contato criado com sucesso"
        }

    except Exception as e:
        logger.error(f"Erro ao criar contato: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# API - ATUALIZAR CONTATO
# ============================================================

@router.put("/api/contact/{contact_id}")
async def api_update_contact(contact_id: str, request: Request):
    """Atualiza um contato"""
    try:
        data = await request.json()

        update_data = {"updated_at": datetime.now()}

        campos_permitidos = ["nome", "email", "idioma", "origem", "status", "etapa", "tags", "notas", "valor_orcamento"]

        for campo in campos_permitidos:
            if campo in data:
                update_data[campo] = data[campo]

        result = await db.crm_contacts.update_one(
            {"_id": ObjectId(contact_id)},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            return {"success": False, "error": "Contato nao encontrado"}

        return {"success": True, "message": "Contato atualizado"}

    except Exception as e:
        logger.error(f"Erro ao atualizar contato: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# API - DELETAR CONTATO
# ============================================================

@router.delete("/api/contact/{contact_id}")
async def api_delete_contact(contact_id: str):
    """Deleta um contato"""
    try:
        result = await db.crm_contacts.delete_one({"_id": ObjectId(contact_id)})

        if result.deleted_count == 0:
            return {"success": False, "error": "Contato nao encontrado"}

        return {"success": True, "message": "Contato deletado"}

    except Exception as e:
        logger.error(f"Erro ao deletar contato: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# API - IMPORTAR CONTATOS DO WHATSAPP
# ============================================================

@router.post("/api/import-whatsapp")
async def api_import_whatsapp_contacts():
    """Importa contatos das conversas do WhatsApp"""
    try:
        # Buscar todos os phones unicos das conversas
        phones = await db.conversas.distinct("phone")

        importados = 0
        atualizados = 0

        for phone in phones:
            if not phone or "@" not in str(phone):
                # Nao eh um phone valido do WhatsApp
                continue

            phone_limpo = re.sub(r'[^\d]', '', phone.replace('@lid', '').replace('@c.us', ''))

            if len(phone_limpo) < 10:
                continue

            # Verificar se ja existe
            existente = await db.crm_contacts.find_one({"phone": phone_limpo})

            # Extrair info das conversas
            info = await extrair_info_conversa(phone)

            if existente:
                # Atualizar se tiver nova info
                update_data = {"updated_at": datetime.now()}
                if info.get("nome") and not existente.get("nome"):
                    update_data["nome"] = info["nome"]
                if info.get("email") and not existente.get("email"):
                    update_data["email"] = info["email"]

                if len(update_data) > 1:
                    await db.crm_contacts.update_one(
                        {"_id": existente["_id"]},
                        {"$set": update_data}
                    )
                    atualizados += 1
            else:
                # Criar novo contato
                # Contar interacoes
                total_msgs = await db.conversas.count_documents({"phone": phone})

                # Primeira e ultima mensagem
                primeira = await db.conversas.find_one({"phone": phone}, sort=[("timestamp", 1)])
                ultima = await db.conversas.find_one({"phone": phone}, sort=[("timestamp", -1)])

                agora = datetime.now()

                novo_contato = {
                    "phone": phone_limpo,
                    "nome": info.get("nome"),
                    "email": info.get("email"),
                    "idioma": info.get("idioma", "pt"),
                    "origem": "WhatsApp",
                    "status": "novo",
                    "etapa": "inicial",
                    "tags": [],
                    "notas": "",
                    "valor_orcamento": None,
                    "total_interactions": total_msgs,
                    "first_contact": primeira.get("timestamp") if primeira else agora,
                    "last_contact": ultima.get("timestamp") if ultima else agora,
                    "created_at": agora,
                    "updated_at": agora
                }

                await db.crm_contacts.insert_one(novo_contato)
                importados += 1

        return {
            "success": True,
            "importados": importados,
            "atualizados": atualizados,
            "message": f"Importados: {importados}, Atualizados: {atualizados}"
        }

    except Exception as e:
        logger.error(f"Erro ao importar contatos: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# API - ESTATISTICAS DO CRM
# ============================================================

@router.get("/api/stats")
async def api_crm_stats():
    """Retorna estatisticas do CRM"""
    try:
        total = await db.crm_contacts.count_documents({})
        novos = await db.crm_contacts.count_documents({"status": "novo"})
        em_contato = await db.crm_contacts.count_documents({"status": "em_contato"})
        qualificados = await db.crm_contacts.count_documents({"status": "qualificado"})
        convertidos = await db.crm_contacts.count_documents({"status": "convertido"})
        perdidos = await db.crm_contacts.count_documents({"status": "perdido"})

        # Contatos com email
        com_email = await db.crm_contacts.count_documents({"email": {"$ne": None, "$ne": ""}})

        # Ultimos 7 dias
        data_7_dias = datetime.now() - timedelta(days=7)
        novos_7_dias = await db.crm_contacts.count_documents({
            "created_at": {"$gte": data_7_dias}
        })

        return {
            "success": True,
            "stats": {
                "total": total,
                "novos": novos,
                "em_contato": em_contato,
                "qualificados": qualificados,
                "convertidos": convertidos,
                "perdidos": perdidos,
                "com_email": com_email,
                "novos_7_dias": novos_7_dias
            }
        }

    except Exception as e:
        logger.error(f"Erro ao obter stats: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# API - ADICIONAR TAG
# ============================================================

@router.post("/api/contact/{contact_id}/tag")
async def api_add_tag(contact_id: str, request: Request):
    """Adiciona uma tag a um contato"""
    try:
        data = await request.json()
        tag = data.get("tag", "").strip()

        if not tag:
            return {"success": False, "error": "Tag obrigatoria"}

        result = await db.crm_contacts.update_one(
            {"_id": ObjectId(contact_id)},
            {"$addToSet": {"tags": tag}}
        )

        return {"success": True, "message": "Tag adicionada"}

    except Exception as e:
        logger.error(f"Erro ao adicionar tag: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# API - REMOVER TAG
# ============================================================

@router.delete("/api/contact/{contact_id}/tag/{tag}")
async def api_remove_tag(contact_id: str, tag: str):
    """Remove uma tag de um contato"""
    try:
        result = await db.crm_contacts.update_one(
            {"_id": ObjectId(contact_id)},
            {"$pull": {"tags": tag}}
        )

        return {"success": True, "message": "Tag removida"}

    except Exception as e:
        logger.error(f"Erro ao remover tag: {e}")
        return {"success": False, "error": str(e)}
