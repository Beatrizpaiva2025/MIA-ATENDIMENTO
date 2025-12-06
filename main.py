# ============================================================
# NÚMEROS DO OPERADOR (adicione após as outras constantes)
# ============================================================

DEFAULT_OPERATOR_NUMBER = "18573167770"  # +1(857)316-7770 - ENVIA comandos (* e +)
DEFAULT_ALERTS_NUMBER = "18572081139"    # +1(857)208-1139 - RECEBE alertas/resumos


def normalize_phone_number(phone: str) -> str:
    """Normaliza número de telefone removendo caracteres especiais"""
    if not phone:
        return ""
    import re
    normalized = re.sub(r'\D', '', phone)
    if normalized.startswith('0'):
        normalized = normalized[1:]
    return normalized


async def get_operator_number():
    """Retorna número que ENVIA comandos (* e +) para controlar atendimento"""
    try:
        config = await db.bot_config.find_one({"_id": "operator_config"})
        if config and "operator_number" in config:
            return config["operator_number"]
    except Exception as e:
        logger.error(f"Erro ao buscar número do operador: {e}")
    return DEFAULT_OPERATOR_NUMBER


async def get_alerts_number():
    """Retorna número que RECEBE alertas/resumos de transferência"""
    try:
        config = await db.bot_config.find_one({"_id": "operator_config"})
        if config and "alerts_number" in config:
            return config["alerts_number"]
    except Exception as e:
        logger.error(f"Erro ao buscar número de alertas: {e}")
    return DEFAULT_ALERTS_NUMBER


# ============================================================
# ENDPOINT PARA RESETAR MODO HUMANO (adicione com as outras rotas)
# ============================================================

@app.get("/admin/reset-mode/{phone}")
async def reset_human_mode(phone: str):
    """Quick reset human mode for a phone number"""
    normalized = normalize_phone_number(phone)
    
    # Reset in conversas collection (mode from "human" to "ia")
    result = await db.conversas.update_many(
        {"phone": {"$in": [phone, normalized, f"+{normalized}"]}},
        {"$set": {"mode": "ia"}, "$unset": {"transferred_at": "", "transfer_reason": ""}}
    )
    
    logger.info(f"Reset modo humano para {phone} (normalizado: {normalized}) - {result.modified_count} registros")
    
    return {
        "success": True, 
        "phone": normalized, 
        "updated": result.modified_count,
        "message": f"AI mode restored for {normalized}"
    }


# ============================================================
# FUNÇÃO PARA TRANSFERIR PARA HUMANO (atualizada)
# ============================================================

async def transferir_para_humano(phone: str, motivo: str = "Cliente solicitou"):
    """Transfere atendimento para humano e notifica operador"""
    normalized = normalize_phone_number(phone)
    
    # Atualiza conversa para modo humano
    await db.conversas.update_one(
        {"phone": normalized},
        {"$set": {
            "mode": "human",
            "transferred_at": datetime.utcnow().isoformat(),
            "transfer_reason": motivo
        }},
        upsert=True
    )
    
    # Notifica o número de ALERTAS (não o de comandos)
    alerts_number = await get_alerts_number()
    if alerts_number:
        await notificar_atendente(normalized, motivo, alerts_number)
    
    logger.info(f"Transferido para humano: {normalized} - Motivo: {motivo}")


async def retornar_para_ia(phone: str):
    """Retorna atendimento para IA"""
    normalized = normalize_phone_number(phone)
    
    await db.conversas.update_many(
        {"phone": {"$in": [phone, normalized, f"+{normalized}"]}},
        {"$set": {"mode": "ia"}, "$unset": {"transferred_at": "", "transfer_reason": ""}}
    )
    
    logger.info(f"Retornado para IA: {normalized}")


# ============================================================
# NO WEBHOOK - PROCESSAR COMANDOS * E + (substitua a seção de comandos)
# ============================================================

# Dentro da função do webhook, adicione esta lógica:

async def processar_comando_operador(phone: str, message_text: str):
    """Processa comandos * e + do operador"""
    operator_number = await get_operator_number()
    operator_normalized = normalize_phone_number(operator_number)
    phone_normalized = normalize_phone_number(phone)
    
    # Verifica se é do número de comandos
    if phone_normalized != operator_normalized:
        return None
    
    message = message_text.strip()
    
    # Comando: *NUMERO (Pausar IA para cliente)
    if message.startswith("*") and len(message) > 1:
        cliente_phone = message[1:].strip()
        cliente_normalized = normalize_phone_number(cliente_phone)
        if cliente_normalized:
            await transferir_para_humano(cliente_normalized, "Operador pausou IA")
            return f"✅ IA pausada para {cliente_normalized}. Envie +{cliente_normalized} para retomar."
    
    # Comando: +NUMERO (Retomar IA para cliente)
    if message.startswith("+") and len(message) > 1:
        cliente_phone = message[1:].strip()
        cliente_normalized = normalize_phone_number(cliente_phone)
        if cliente_normalized:
            await retornar_para_ia(cliente_normalized)
            return f"✅ IA retomada para {cliente_normalized}. A IA voltará a responder automaticamente."
    
    return None
