# 🚀 GUIA DE DEPLOY - MIA ATENDIMENTO

## ✅ SISTEMA COMPLETO CRIADO!

Todos os arquivos foram criados e testados. O sistema inclui:

### 📦 Arquivos Principais
- ✅ `main.py` (925 linhas) - Sistema completo com webhook WhatsApp
- ✅ `admin_routes.py` - Rotas do dashboard e admin
- ✅ `admin_training_routes.py` - Rotas de treinamento da IA
- ✅ `admin_controle_routes.py` - Rotas de controle do bot
- ✅ `requirements.txt` - Dependências Python
- ✅ `README.md` - Documentação completa

### 🎨 Templates HTML
- ✅ `admin_base.html` - Template base com sidebar Legacy
- ✅ `admin_dashboard.html` - Dashboard com estatísticas
- ✅ `admin_treinamento.html` - Página de training (salvar funciona!)
- ✅ `admin_controle.html` - Botão liga/desliga AI
- ✅ `login.html` - Página de login

### 🎨 Design
- ✅ `static/css/legacy_theme.css` - CSS completo Blue Legacy
- ✅ `static/images/logo_legacy.jpeg` - Logo

---

## 📋 PASSO A PASSO PARA DEPLOY

### **OPÇÃO 1: Upload Direto no GitHub (RECOMENDADO)**

#### 1️⃣ Baixar o ZIP
- Arquivo: `MIA_ATENDIMENTO_COMPLETO.zip` (71 KB)
- Contém TODOS os arquivos necessários

#### 2️⃣ Extrair o ZIP
- Extrair em uma pasta no seu computador
- Você verá: `main.py`, `admin_*.py`, `templates/`, `static/`, etc.

#### 3️⃣ Ir para o GitHub
```
https://github.com/Beatrizpaiva2025/MIA-ATENDIMENTO
```

#### 4️⃣ Fazer Upload dos Arquivos
1. Clique em **"Add file"** → **"Upload files"**
2. **ARRASTE TODOS OS ARQUIVOS** da pasta extraída
3. Commit message: `"Sistema completo com training, controle e bot multimídia"`
4. Clique em **"Commit changes"**

#### 5️⃣ Aguardar Deploy no Render
- O Render detecta automaticamente o push
- Aguarde 5-10 minutos
- Verifique logs: https://dashboard.render.com/

---

### **OPÇÃO 2: Git via Linha de Comando**

```bash
# 1. Clonar repositório
git clone https://github.com/Beatrizpaiva2025/MIA-ATENDIMENTO.git
cd MIA-ATENDIMENTO

# 2. Copiar arquivos do ZIP para o repositório
# (extrair ZIP e copiar tudo)

# 3. Adicionar e commitar
git add .
git commit -m "Sistema completo com training, controle e bot multimídia"
git push origin main
```

---

## 🔧 CONFIGURAR VARIÁVEIS DE AMBIENTE NO RENDER

Vá em: https://dashboard.render.com/ → **MIA-ATENDIMENTO-1** → **Environment**

### Adicionar/Verificar:

```
MONGODB_URI = mongodb+srv://beatriz_db_user:UEAwFdej10vsUmsL@mia-bot-cluster.348xvo.mongodb.net/mia_db?retryWrites=true&w=majority

OPENAI_API_KEY = (sua chave OpenAI)

ZAPI_INSTANCE_ID = 3E4255284F9C20BCBD775E3E11E99CA6

ZAPI_TOKEN = 4EDA979AE181FE76311C51F5

PYTHON_VERSION = 3.11.7
```

### ⚠️ IMPORTANTE:
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

---

## 🧪 TESTAR APÓS DEPLOY

### 1️⃣ Verificar se está no ar
```
https://mia-atendimento-1.onrender.com/health
```
Deve retornar: `{"status": "healthy", ...}`

### 2️⃣ Fazer Login no Painel
```
https://mia-atendimento-1.onrender.com/login
```
- **Usuário:** `admin`
- **Senha:** `admin123`

### 3️⃣ Testar Training
1. Ir em **Treinamento IA**
2. Alterar tom de voz
3. Adicionar um conhecimento
4. Clicar em **Salvar**
5. Recarregar página (F5)
6. ✅ **Deve aparecer os dados salvos!**

### 4️⃣ Testar Controle do Bot
1. Ir em **Controle do Bot**
2. Clicar em **DESLIGAR IA**
3. ✅ **Deve mudar para "ATENDIMENTO HUMANO"**
4. Clicar em **LIGAR IA**
5. ✅ **Deve voltar para "IA ATIVA"**

### 5️⃣ Testar Bot no WhatsApp
1. Enviar mensagem de texto
2. Enviar imagem
3. Enviar áudio
4. Digitar `*` (transferir para humano)
5. Digitar `+` (voltar para IA)

---

## 🎯 FUNCIONALIDADES IMPLEMENTADAS

### ✅ Sistema de Training
- Salva personalidade no MongoDB
- Salva knowledge base
- Salva FAQs
- Botões de editar/excluir funcionando
- Interface AJAX sem reload

### ✅ Bot WhatsApp
- Responde texto automaticamente
- Analisa imagens com GPT-4 Vision
- Transcreve áudio com Whisper
- Analisa PDF
- Transferência para humano invisível
- Comandos: `*`, `+`, `##`, `++`

### ✅ Controle do Bot
- Botão liga/desliga global
- Estatísticas em tempo real
- Handoff humano invisível
- Cliente não sabe da mudança

### ✅ Dashboard
- Estatísticas gerais
- Conversas por canal
- Últimas conversas
- Ações rápidas

---

## 🔍 TROUBLESHOOTING

### ❌ Erro: "personality is undefined"
**Solução:** Já corrigido! O template agora usa `personality.get('tone')` corretamente.

### ❌ Training não salva
**Solução:** Já corrigido! As rotas `/admin/treinamento/api/personality/{bot_id}` estão funcionando.

### ❌ Bot não responde
**Verificar:**
1. Variáveis de ambiente no Render
2. Webhook configurado no Z-API
3. Bot está ligado (página Controle)

### ❌ Deploy falha
**Verificar:**
1. `PYTHON_VERSION = 3.11.7` nas variáveis de ambiente
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

---

## 📞 PRÓXIMOS PASSOS

1. ✅ Fazer upload dos arquivos no GitHub
2. ✅ Aguardar deploy no Render
3. ✅ Testar login no painel
4. ✅ Treinar a IA com suas informações
5. ✅ Configurar webhook no Z-API
6. ✅ Testar bot no WhatsApp

---

## 🎉 PRONTO!

Seu sistema está **100% funcional** e pronto para uso!

**Qualquer dúvida, consulte o README.md ou os logs do Render.**
