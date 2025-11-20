# ============================================================
# CORREÇÃO: Remover a segunda função send_whatsapp_message duplicada
# ============================================================

# INSTRUÇÕES PARA CORREÇÃO:
# 
# 1. Abrir o arquivo main.py no GitHub
# 2. Localizar as linhas 277-302 (segunda definição da função)
# 3. DELETAR todo o bloco abaixo:

"""
# ============================================================
# FUNÇÃO: ENVIAR MENSAGEM WHATSAPP
# ============================================================
async def send_whatsapp_message(phone: str, message: str):
    '''Enviar mensagem via Z-API'''
    try:
        url = f"{ZAPI_URL}/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-text"
        
        payload = {
            "phone": phone,
            "message": message
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                logger.info(f"✅ Mensagem enviada para {phone}")
                return True
            else:
                logger.error(f"❌ Erro ao enviar: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Erro ao enviar mensagem: {str(e)}")
        return False
"""

# 4. Salvar o arquivo
# 5. A primeira função (linha 123-162) será mantida e usada
# 6. Essa função JÁ ESTÁ CORRETA e envia o Client-Token

# ============================================================
# ALTERNATIVA: Se não quiser usar Client-Token
# ============================================================

# Se você NÃO quer usar Client-Token, faça o seguinte:
# 
# 1. Acesse o painel Z-API: https://painel.z-api.io
# 2. Vá em: Segurança → Token de Segurança da Conta
# 3. DESATIVE o recurso "Token de Segurança da Conta"
# 4. Depois, você pode:
#    - Manter a segunda função (linha 280) e deletar a primeira (linha 123)
#    OU
#    - Modificar a primeira função para remover o Client-Token do header

# ============================================================
# RECOMENDAÇÃO
# ============================================================

# OPÇÃO MAIS SIMPLES: Desabilitar o Client-Token na Z-API
# - Não precisa mexer no código
# - Só desativar no painel
# - O bot voltará a funcionar imediatamente

