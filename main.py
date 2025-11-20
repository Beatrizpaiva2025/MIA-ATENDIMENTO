# ============================================================
# WEBHOOK CORRIGIDO: WHATSAPP (Z-API)
# ============================================================
@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    """
    Webhook principal para receber mensagens do WhatsApp via Z-API
    Suporta: texto, imagens e áudios
    """
    try:
        data = await request.json()
        logger.info(f"📨 Webhook recebido: {json.dumps(data, indent=2)}")
        
        # ============================================
        # 🛑 CONTROLE DE ATIVAÇÃO DA IA
        # ============================================
        ia_enabled = os.getenv("IA_ENABLED", "true").lower() == "true"
        em_manutencao = os.getenv("MANUTENCAO", "false").lower() == "true"
        
        # Extrair informações
        phone = data.get("phone", "")
        
        if not phone:
            return JSONResponse({"status": "ignored", "reason": "no phone"})
        
        # ============================================
        # 🔍 DETECTAR TIPO DE MENSAGEM (CORREÇÃO)
        # ============================================
        # A Z-API não envia campo "messageType"
        # Detectar tipo pela presença de campos específicos
        
        if "text" in data and data["text"].get("message"):
            message_type = "text"
        elif "image" in data and data["image"].get("imageUrl"):
            message_type = "image"
        elif "audio" in data and data["audio"].get("audioUrl"):
            message_type = "audio"
        else:
            message_type = "unknown"
            logger.warning(f"⚠️ Tipo de mensagem desconhecido: {list(data.keys())}")
            return JSONResponse({"status": "ignored", "reason": "unknown message type"})
        
        logger.info(f"🔍 Tipo detectado: {message_type}")
        # ============================================
        
        # Se em manutenção, responder e sair
        if em_manutencao:
            logger.info(f"🔧 Modo manutenção ativo - mensagem de {phone}")
            if message_type == "text":
                mensagem_manutencao = """🔧 *Sistema em Manutenção*\n\nOlá! Estamos melhorando nosso atendimento.\nEm breve voltaremos! 😊\n\n📞 Para urgências: (contato)"""
                await send_whatsapp_message(phone, mensagem_manutencao)
            return JSONResponse({"status": "maintenance"})
        
        # Se IA desabilitada, apenas logar e sair
        if not ia_enabled:
            logger.info(f"⏸️ IA desabilitada - mensagem de {phone} ignorada")
            return JSONResponse({"status": "ia_disabled"})
        # ============================================
        
        # ========== PROCESSAR TEXTO ==========
        if message_type == "text":
            text = data.get("text", {}).get("message", "")
            
            if not text:
                return JSONResponse({"status": "ignored", "reason": "empty text"})
            
            logger.info(f"💬 Texto de {phone}: {text}")
            
            # Processar com IA
            reply = await process_message_with_ai(phone, text)
            
            # Enviar resposta
            await send_whatsapp_message(phone, reply)
            
            return JSONResponse({"status": "processed", "type": "text"})
        
        # ========== PROCESSAR IMAGEM ==========
        elif message_type == "image":
            image_url = data.get("image", {}).get("imageUrl", "")
            caption = data.get("image", {}).get("caption", "")
            
            if not image_url:
                return JSONResponse({"status": "ignored", "reason": "no image url"})
            
            logger.info(f"🖼️ Imagem de {phone}: {image_url[:50]}")
            
            # Baixar imagem
            image_bytes = await download_media_from_zapi(image_url)
            
            if not image_bytes:
                await send_whatsapp_message(phone, "Desculpe, não consegui baixar a imagem. Pode tentar enviar novamente?")
                return JSONResponse({"status": "error", "reason": "download failed"})
            
            # Analisar com Vision
            analysis = await process_image_with_vision(image_bytes, phone)
            
            # Montar resposta
            reply = f"📄 *Análise do Documento*\n\n{analysis}\n\n_Posso ajudar com mais alguma coisa?_"
            
            # Enviar resposta
            await send_whatsapp_message(phone, reply)
            
            return JSONResponse({"status": "processed", "type": "image"})
        
        # ========== PROCESSAR ÁUDIO ==========
        elif message_type == "audio":
            audio_url = data.get("audio", {}).get("audioUrl", "")
            
            if not audio_url:
                return JSONResponse({"status": "ignored", "reason": "no audio url"})
            
            logger.info(f"🎤 Áudio de {phone}: {audio_url[:50]}")
            
            # Baixar áudio
            audio_bytes = await download_media_from_zapi(audio_url)
            
            if not audio_bytes:
                await send_whatsapp_message(phone, "Desculpe, não consegui baixar o áudio. Pode tentar enviar novamente?")
                return JSONResponse({"status": "error", "reason": "download failed"})
            
            # Transcrever com Whisper
            transcription = await process_audio_with_whisper(audio_bytes, phone)
            
            if not transcription:
                await send_whatsapp_message(phone, "Desculpe, não consegui transcrever o áudio. Pode tentar novamente?")
                return JSONResponse({"status": "error", "reason": "transcription failed"})
            
            logger.info(f"📝 Transcrição: {transcription[:100]}...")
            
            # Processar transcrição com IA
            reply = await process_message_with_ai(phone, transcription)
            
            # Enviar resposta
            await send_whatsapp_message(phone, reply)
            
            return JSONResponse({"status": "processed", "type": "audio"})
        
        # ========== TIPO DESCONHECIDO ==========
        else:
            logger.warning(f"⚠️ Tipo de mensagem não suportado: {message_type}")
            return JSONResponse({"status": "ignored", "reason": "unsupported type"})
            
    except Exception as e:
        logger.error(f"❌ Erro no webhook: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ============================================================
# RESUMO DAS MUDANÇAS
# ============================================================

# ANTES (LINHA 397):
# message_type = data.get("messageType", "text")

# DEPOIS (LINHAS 395-410):
# if "text" in data and data["text"].get("message"):
#     message_type = "text"
# elif "image" in data and data["image"].get("imageUrl"):
#     message_type = "image"
# elif "audio" in data and data["audio"].get("audioUrl"):
#     message_type = "audio"
# else:
#     message_type = "unknown"

# ============================================================
# POR QUE ESSA MUDANÇA É NECESSÁRIA?
# ============================================================

# A Z-API NÃO envia um campo "messageType" nos webhooks.
# Todos os webhooks têm "type": "ReceivedCallback".
# 
# O tipo de mensagem é identificado pela PRESENÇA de campos:
# - "text": {...} → Mensagem de texto
# - "image": {...} → Mensagem de imagem
# - "audio": {...} → Mensagem de áudio
#
# Com o código antigo, o bot SEMPRE assumia "text" como padrão,
# então imagens e áudios NUNCA eram processados corretamente.

# ============================================================
# LOGS ESPERADOS APÓS A CORREÇÃO
# ============================================================

# TEXTO:
# 📨 Webhook recebido: {...}
# 🔍 Tipo detectado: text
# 💬 Texto de 16893094980: Oi

# IMAGEM:
# 📨 Webhook recebido: {...}
# 🔍 Tipo detectado: image
# 🖼️ Imagem de 16893094980: https://...
# 🔍 Analisando imagem com GPT-4 Vision...
# ✅ Análise concluída: ...

# ÁUDIO:
# 📨 Webhook recebido: {...}
# 🔍 Tipo detectado: audio
# 🎤 Áudio de 16893094980: https://...
# 🔍 Transcrevendo áudio com Whisper...
# ✅ Transcrição: ...
