# 🚀 GUIA DE DEPLOY - MIA ATENDIMENTO

## ✅ PRÉ-REQUISITOS

1. **Conta GitHub** - Beatrizpaiva2025
2. **Conta Render.com** - Conectada ao GitHub
3. **MongoDB Atlas** - Cluster configurado
4. **Credenciais Z-API** - Instance ID, Token, Client Token
5. **OpenAI API Key**

---

## 📦 PASSO 1: CRIAR REPOSITÓRIO NO GITHUB

1. Acesse: https://github.com/new
2. Nome do repositório: **MIA-ATENDIMENTO**
3. Descrição: `Bot WhatsApp com IA - Legacy Translations`
4. **Público** ou **Privado** (sua escolha)
5. **NÃO** marque "Add README" (já temos um)
6. Clique em **Create repository**

---

## 📤 PASSO 2: FAZER UPLOAD DOS ARQUIVOS

### Opção A: Via GitHub Web (Mais Fácil)

1. No repositório criado, clique em **Add file** → **Upload files**
2. Arraste TODOS os arquivos e pastas deste projeto:
   - `main.py`
   - `admin_routes.py`
   - `admin_controle_routes.py`
   - `controle_atendimento.py`
   - `requirements.txt`
   - `runtime.txt`
   - `README.md`
   - `.gitignore`
   - Pasta `templates/` com todos os arquivos HTML

3. Escreva mensagem de commit: `Initial commit - MIA Atendimento v1.0`
4. Clique em **Commit changes**

### Opção B: Via Git Command Line

```bash
cd /caminho/para/MIA-ATENDIMENTO
git init
git add .
git commit -m "Initial commit - MIA Atendimento v1.0"
git branch -M main
git remote add origin https://github.com/Beatrizpaiva2025/MIA-ATENDIMENTO.git
git push -u origin main
```

---

## 🌐 PASSO 3: DEPLOY NO RENDER.COM

### 3.1 Criar Novo Web Service

1. Acesse: https://dashboard.render.com/
2. Clique em **New** → **Web Service**
3. Conecte seu repositório GitHub: **Beatrizpaiva2025/MIA-ATENDIMENTO**
4. Clique em **Connect**

### 3.2 Configurar o Serviço

**Settings:**
- **Name:** `mia-atendimento` (ou outro nome único)
- **Environment:** `Python 3`
- **Region:** `Oregon` (US West) ou mais próximo
- **Branch:** `main`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Plan:** `Free` (para começar)

### 3.3 Configurar Variáveis de Ambiente

Clique em **Environment** → **Add Environment Variable**

Adicione TODAS as variáveis:

```env
# MongoDB Atlas
MONGODB_URI=mongodb+srv://usuario:senha@cluster.mongodb.net/mia_bot?retryWrites=true&w=majority

# OpenAI
OPENAI_API_KEY=sk-proj-...

# Z-API (WhatsApp)
ZAPI_INSTANCE_ID=seu_instance_id_aqui
ZAPI_TOKEN=seu_token_aqui
ZAPI_CLIENT_TOKEN=seu_client_token_aqui
ZAPI_URL=https://api.z-api.io

# Controle do Sistema
IA_ENABLED=true
MANUTENCAO=false
ENVIRONMENT=production

# URL do Render (preencher DEPOIS do deploy)
RENDER_EXTERNAL_URL=https://mia-atendimento.onrender.com
```

**⚠️ IMPORTANTE:** Substitua os valores com suas credenciais reais!

### 3.4 Deploy

1. Clique em **Create Web Service**
2. Aguarde o deploy (3-5 minutos)
3. Quando status ficar **Live** ✅, está pronto!

---

## 🔗 PASSO 4: CONFIGURAR WEBHOOK NA Z-API

1. Acesse: https://api.z-api.io/instances
2. Selecione sua instância
3. Vá em **Webhooks**
4. Configure o webhook:
   ```
   URL: https://seu-app.onrender.com/webhook/whatsapp
   Eventos: Selecione todos (Message, Image, Audio, etc.)
   ```
5. Clique em **Salvar**

---

## ✅ PASSO 5: TESTAR O SISTEMA

### 5.1 Health Check
Acesse: `https://seu-app.onrender.com/health`

Deve retornar:
```json
{
  "status": "healthy",
  "openai": "✅ Configurado",
  "mongodb": "✅ Conectado",
  "zapi_instance": "✅ Configurado"
}
```

### 5.2 Painel Admin
Acesse: `https://seu-app.onrender.com/admin`

Deve abrir o dashboard com:
- Estatísticas gerais
- Gráficos
- Menu lateral roxo

### 5.3 WhatsApp
Envie mensagem para o número configurado:
```
Olá!
```

Mia deve responder automaticamente! 🎉

---

## 🎯 PÁGINAS DO PAINEL ADMIN

- `/admin` - Dashboard principal
- `/admin/pipeline` - Pipeline de vendas
- `/admin/leads` - Gestão de leads
- `/admin/transfers` - Transferências
- `/admin/documents` - Documentos analisados
- `/admin/controle` - Controle IA vs Humano
- `/admin/config` - Configurações

---

## 🆘 SOLUÇÃO DE PROBLEMAS

### Erro: MongoDB connection failed
- Verifique se `MONGODB_URI` está correto
- Teste conexão no MongoDB Atlas
- Whitelist IP do Render: `0.0.0.0/0`

### Erro: OpenAI API error
- Verifique se `OPENAI_API_KEY` é válida
- Conta OpenAI tem créditos?

### Bot não responde no WhatsApp
- Webhook configurado corretamente na Z-API?
- URL está acessível?
- Instância Z-API está conectada?

### Página branca no admin
- MongoDB conectado?
- Logs do Render mostram algum erro?

---

## 📊 MONITORAMENTO

### Logs do Render
```
Dashboard → Logs (tempo real)
```

### Estatísticas
```
https://seu-app.onrender.com/admin/api/stats
```

---

## 🔄 ATUALIZAÇÕES FUTURAS

Para atualizar o código:

1. Faça mudanças nos arquivos locais
2. Commit e push para GitHub:
   ```bash
   git add .
   git commit -m "Descrição da mudança"
   git push
   ```
3. Render fará deploy automático! 🚀

---

## ✅ CHECKLIST FINAL

- [ ] Repositório GitHub criado
- [ ] Arquivos uploaded para GitHub
- [ ] Web Service criado no Render
- [ ] Variáveis de ambiente configuradas
- [ ] Deploy concluído com sucesso
- [ ] Health check retorna "healthy"
- [ ] Painel admin abrindo corretamente
- [ ] Webhook configurado na Z-API
- [ ] Bot respondendo no WhatsApp
- [ ] MongoDB conectando corretamente

---

## 🎉 SUCESSO!

Se todos os checkmarks estão marcados, seu sistema está 100% operacional!

**Próximos passos:**
1. Treinar equipe para usar o painel admin
2. Monitorar conversas e leads
3. Ajustar personalidade da Mia conforme necessário
4. Escalar conforme demanda cresce

---

**Desenvolvido para Legacy Translations**  
Bot: Mia - Assistente Virtual Inteligente 🤖
