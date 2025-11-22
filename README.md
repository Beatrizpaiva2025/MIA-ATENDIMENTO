# MIA Bot - Sistema de Atendimento WhatsApp com IA

Bot de atendimento inteligente para WhatsApp com painel administrativo completo.

## 🚀 Funcionalidades

### Bot de Atendimento
- ✅ Responde automaticamente com IA (GPT-4)
- ✅ Reconhece **texto**, **imagem** (GPT-4 Vision), **áudio** (Whisper) e **PDF**
- ✅ Transferência para atendente humano **invisível**
- ✅ Comandos especiais: `*` (transferir), `+` (voltar IA), `##` (desligar), `++` (religar)

### Painel Administrativo
- ✅ **Dashboard** com estatísticas em tempo real
- ✅ **Treinamento da IA** (personalidade, knowledge base, FAQs)
- ✅ **Controle do Bot** (botão liga/desliga global)
- ✅ **Conversas** em tempo real
- ✅ **Leads** capturados automaticamente

## 📋 Requisitos

- Python 3.11+
- MongoDB Atlas
- OpenAI API Key
- Z-API (WhatsApp)

## 🔧 Instalação Local

```bash
# Clonar repositório
git clone https://github.com/Beatrizpaiva2025/MIA-ATENDIMENTO.git
cd MIA-ATENDIMENTO

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com suas credenciais

# Executar
python main.py
```

## 🌐 Deploy no Render.com

1. Conectar repositório GitHub
2. Configurar variáveis de ambiente:
   - `MONGODB_URI`
   - `OPENAI_API_KEY`
   - `ZAPI_INSTANCE_ID`
   - `ZAPI_TOKEN`
   - `PYTHON_VERSION=3.11.7`
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## 🎯 Como Usar

### Acessar Painel Admin
1. Acesse: `https://seu-dominio.onrender.com/login`
2. Login: `admin` / Senha: `admin123`

### Treinar a IA
1. Vá em **Treinamento IA**
2. Configure personalidade, knowledge base e FAQs
3. Salve as alterações

### Controlar o Bot
1. Vá em **Controle do Bot**
2. Use o botão **LIGAR/DESLIGAR IA**
3. Quando desligado, você atende manualmente (cliente não sabe)

### Comandos do Cliente
- `*` → Transferir para atendente humano
- `+` → Voltar para IA
- `##` → Desligar IA (individual)
- `++` → Religar IA (individual)

## 📱 Integração WhatsApp

Configure o webhook no Z-API:
```
https://seu-dominio.onrender.com/webhook/whatsapp
```

## 🎨 Design

- **Cores**: Blue Legacy (Navy + Light Blue)
- **Fonte**: Inter, Segoe UI
- **Framework**: FastAPI + Jinja2

## 📞 Suporte

Para dúvidas ou problemas, abra uma issue no GitHub.

## 📄 Licença

MIT License
