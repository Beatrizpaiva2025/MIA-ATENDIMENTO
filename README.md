# 🤖 MIA ATENDIMENTO - WhatsApp AI Platform

Bot WhatsApp inteligente com IA para atendimento automatizado da Legacy Translations.

## 🚀 Funcionalidades

✅ **Mensagens de Texto** - Conversação natural com GPT-4  
✅ **Imagens** - Análise de documentos com GPT-4 Vision  
✅ **Áudios** - Transcrição de voz com Whisper  
✅ **Painel Admin** - Dashboard completo de gestão  
✅ **Pipeline de Vendas** - CRM e funil de conversão  
✅ **Controle IA/Humano** - Alterne entre bot e atendimento manual  

## 📋 Pré-requisitos

- Python 3.11
- MongoDB Atlas
- Conta OpenAI com API Key
- Conta Z-API (WhatsApp Business)

## 🔧 Variáveis de Ambiente

Configure no Render.com:

```env
# MongoDB
MONGODB_URI=mongodb+srv://usuario:senha@cluster.mongodb.net/mia_bot

# OpenAI
OPENAI_API_KEY=sk-...

# Z-API (WhatsApp)
ZAPI_INSTANCE_ID=seu_instance_id
ZAPI_TOKEN=seu_token
ZAPI_CLIENT_TOKEN=seu_client_token
ZAPI_URL=https://api.z-api.io

# Controle
IA_ENABLED=true
MANUTENCAO=false
```

## 🚀 Deploy no Render.com

1. **Conecte o repositório** no Render.com
2. **Configure variáveis de ambiente** (Settings → Environment)
3. **Deploy automático** será iniciado
4. **Acesse o painel:** `https://seu-app.onrender.com/admin`

## 📊 Rotas do Painel Admin

- `/admin` - Dashboard principal
- `/admin/pipeline` - Pipeline de vendas
- `/admin/leads` - Gestão de leads (CRM)
- `/admin/transfers` - Transferências para humano
- `/admin/documents` - Documentos analisados
- `/admin/controle` - Controle IA vs Humano
- `/admin/config` - Configurações do sistema

## 🔗 Webhooks

Configure na Z-API:
```
https://seu-app.onrender.com/webhook/whatsapp
```

## 🎯 Como Usar

1. Cliente envia mensagem no WhatsApp
2. Bot Mia responde automaticamente
3. Se cliente enviar imagem, analisa com Vision
4. Se enviar áudio, transcreve e responde
5. Use painel admin para acompanhar tudo

## 📞 Suporte

Desenvolvido para **Legacy Translations**  
Bot: **Mia** - Assistente Virtual
