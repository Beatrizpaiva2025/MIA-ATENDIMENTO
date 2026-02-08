# CLAUDE.md - MIA Bot (Sistema de Atendimento WhatsApp com IA)

## Project Overview

MIA Bot is a WhatsApp AI chatbot with an admin dashboard, built for **Legacy Translations** (Boston, MA). It automates customer service for document translation services using OpenAI GPT-4, handles multimedia messages (text, images, audio, PDFs), generates quotes, tracks leads, and supports seamless human agent handoff.

**Primary language of code comments and UI:** Portuguese (Brazilian), with English support in customer-facing messages.

## Tech Stack

- **Backend:** Python 3.11.7, FastAPI 0.104.1, Uvicorn 0.24.0
- **Database:** MongoDB Atlas (async via Motor 3.3.2, sync via PyMongo 4.6.0)
- **AI:** OpenAI API 1.3.5 (GPT-4, GPT-4 Vision, Whisper)
- **WhatsApp:** Z-API integration via webhooks
- **Frontend:** Jinja2 templates, vanilla HTML/CSS/JS, Chart.js
- **Deployment:** Render.com

## Project Structure

```
MIA-ATENDIMENTO/
├── main.py                          # Core app: webhook handler, AI processing, conversation state machine (~3800 lines)
├── admin_routes.py                  # Main dashboard, analytics, leads stats
├── admin_training_routes.py         # AI personality, knowledge base, FAQs editor
├── admin_controle_routes.py         # Bot enable/disable, maintenance mode
├── admin_conversas_routes.py        # Conversation analytics, conversion tracking
├── admin_atendimento_routes.py      # Human agent interface for manual responses
├── admin_crm_routes.py              # Contact management, lead tracking
├── admin_orcamentos_routes.py       # Quote management and tracking
├── admin_conversas_leads_routes.py  # Leads page (in development)
├── admin_learning_routes.py         # Learning page (in development)
├── webchat_routes.py                # Web chat widget for portal (~928 lines)
├── ads_integration.py               # Google Ads & Meta Ads API integration
├── setup_leads.py                   # Database seed: sample leads and marketing stats
├── setup_mia_training.py            # Database seed: bot personality, knowledge base, FAQs
├── sample_data.json                 # Sample leads data for seeding
├── requirements.txt                 # Python dependencies
├── templates/                       # 13 Jinja2 HTML templates
│   ├── admin_base.html              # Layout/navbar base template
│   ├── login.html                   # Login form
│   ├── admin_dashboard.html         # Main dashboard
│   ├── admin_treinamento.html       # AI training editor
│   ├── admin_controle.html          # Bot on/off control panel
│   ├── admin_conversas.html         # Conversation analytics
│   ├── admin_crm.html               # CRM/contact management
│   ├── admin_orcamentos.html        # Quote management
│   ├── admin_leads.html             # Lead dashboard
│   ├── admin_atendimento.html       # Human agent queue
│   ├── admin_atendimento_chat.html  # Chat interface
│   ├── admin_aprendizado.html       # Learning (stub)
│   └── admin_support_ENGLISH.html   # Support page
├── static/
│   ├── css/legacy_theme.css         # Design system (Navy #1e3a5f + Light Blue #5eb3e4)
│   ├── js/leads-integration.js      # Dashboard Chart.js integration
│   ├── js/fix-edit-button.js        # UI fix
│   └── images/logo_legacy.jpeg      # Company logo
└── .gitignore
```

## Architecture

### Pattern: Modular Monolith with Router-Based Organization

- `main.py` is the core application containing the FastAPI app instance, webhook handler, all AI processing logic, and the conversation state machine
- Feature modules (`admin_*_routes.py`, `webchat_routes.py`) are FastAPI routers imported and registered in `main.py`
- Fully async with `async/await` throughout (Motor for DB, httpx for HTTP)
- Webhook-driven: WhatsApp messages arrive via `POST /webhook/whatsapp` from Z-API

### Conversation State Machine

Client conversations progress through stages stored in MongoDB (`cliente_estados` collection):

1. `INICIAL` - New conversation
2. `AGUARDANDO_NOME` - Waiting for customer name
3. `AGUARDANDO_ORIGEM` - Waiting for referral source
4. `AGUARDANDO_OPCAO_ATENDIMENTO` - Menu selection
5. `AGUARDANDO_CONFIRMACAO` - Quote confirmation
6. `AGUARDANDO_PAGAMENTO` - Waiting for payment proof
7. `PAGAMENTO_RECEBIDO` - Payment processed

### Operator Commands (via WhatsApp)

Messages from operator phone numbers trigger special behavior:
- `*` - Pause AI, activate human mode for a client
- `+` - Resume AI mode
- `##` - Disable AI for a specific customer
- `++` - Re-enable AI

## Key MongoDB Collections

| Collection | Purpose |
|---|---|
| `bots` | Bot training data (personality, knowledge base, FAQs) |
| `conversas` | All conversation messages |
| `cliente_estados` | Customer conversation state |
| `conversoes` | Conversion tracking with monetary values |
| `orcamentos` | Generated quotes |
| `leads_followup` | Lead follow-up data |
| `crm_contacts` | Contact information |
| `bot_config` | Global bot on/off status |
| `leads` | Lead records |
| `marketing_stats` | Marketing analytics data |
| `webchat_sessions` | Web chat session tracking |

## Environment Variables

**Required:**
- `OPENAI_API_KEY` - OpenAI API access (GPT-4, Vision, Whisper)
- `MONGODB_URI` - MongoDB Atlas connection string
- `ZAPI_INSTANCE_ID` - WhatsApp Z-API instance ID
- `ZAPI_TOKEN` - WhatsApp Z-API authentication token

**Optional:**
- `ATENDENTE_PHONE` - Main attendant phone number
- `NOTIFICACAO_PHONE` - Notification phone number
- `HUMAN_MODE_TIMEOUT_MINUTES` - Auto-resume AI timeout (default: 30)
- `GOOGLE_ADS_*` (6 vars) - Google Ads API credentials
- `META_*` (4 vars) - Meta/Facebook Ads API credentials
- `PORT` - Server port (default: 8000)

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (starts Uvicorn dev server)
python main.py

# Seed database with sample data
python setup_leads.py
python setup_mia_training.py
```

## Deployment (Render.com)

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Python version:** 3.11.7

## API Structure

### Webhook
- `POST /webhook/whatsapp` - Receives all WhatsApp messages from Z-API

### Admin HTML Pages (Jinja2)
- `GET /admin` - Dashboard
- `GET /admin/treinamento` - AI Training
- `GET /admin/controle` - Bot Control
- `GET /admin/conversas` - Conversations
- `GET /admin/atendimento` - Human Agent Interface
- `GET /admin/crm` - CRM
- `GET /admin/leads` - Lead Management
- `GET /admin/orcamentos` - Quote Management

### Admin JSON APIs
- `GET/POST /admin/api/bot/status|toggle` - Bot control
- `GET/POST /admin/api/cliente/{phone}/*` - Per-client AI mode control
- `GET /admin/api/leads/stats` - Lead statistics
- `GET /admin/api/marketing-stats` - Marketing analytics
- `GET /admin/api/ads/campaigns` - Ad campaign data
- `GET /admin/conversas/api/stats` - Conversation analytics
- `GET /admin/orcamentos/api/list` - Quote listing

### Utility
- `GET /health` - Health check
- `GET /login` - Login page
- `POST /login` - Authentication (simple hardcoded credentials)

## Conventions and Patterns

### Code Style
- Python with type hints (`Optional`, `Dict`, `Any`, `List` from `typing`)
- Async functions for all route handlers and database operations
- Logging via Python `logging` module (INFO level default)
- Comments and docstrings predominantly in Portuguese

### API Response Pattern
- HTML responses for page routes (Jinja2 `TemplateResponse`)
- JSON responses for API endpoints: `{"success": bool, "data": {}, "error": "string"}`
- `RedirectResponse` for form submissions

### Database Access Pattern
- Async Motor client for route handlers: `motor_client = AsyncIOMotorClient(MONGODB_URI)`
- Sync PyMongo client for setup/seed scripts
- No ORM - direct collection operations (`find`, `insert_one`, `update_one`, etc.)
- No schema validation at DB level; validation at application level

### Frontend
- Jinja2 templates extending `admin_base.html`
- Inline `<script>` blocks in templates for page-specific logic
- Chart.js loaded via CDN for analytics charts
- Custom CSS design system in `static/css/legacy_theme.css`

## Testing

There is no formal test suite (no pytest, unittest, or test framework). Testing is done manually via:
- `/health` endpoint for health checks
- `/admin/api/debug/webhook` for webhook activity logging
- `/admin/api/debug/config` for configuration diagnostics
- `/admin/test-notification` for testing operator notifications

## Important Notes for AI Assistants

1. **`main.py` is large (~3800 lines)** - It contains the core webhook handler, all AI processing (text, image, audio, PDF), the conversation state machine, quote generation, and message sending logic. Read specific sections rather than the whole file when possible.

2. **Database names differ:** Async code uses `mia_database`, sync setup scripts use `mia_production`. Be aware of this when working with database operations.

3. **No `.env` file in repo** - Environment variables must be set externally (Render dashboard or local `.env` file). Never commit secrets.

4. **Authentication is basic** - Login uses hardcoded credentials (`admin`/`admin123`). Do not expose or weaken this further.

5. **Z-API webhook format** - Incoming WhatsApp messages have a specific JSON structure from Z-API. Refer to the webhook handler in `main.py` for the expected payload format.

6. **Image grouping buffer** - The system waits 4 seconds after receiving an image to batch multiple photos together before processing. This is a deliberate design decision for document scanning workflows.

7. **Business hours are disabled** - `is_business_hours()` always returns `True` (24/7 operation). The after-hours flow still exists in code but is not triggered.

8. **Multi-language support** - The bot detects and responds in Portuguese, English, or Spanish based on the customer's language preference stored in `cliente_estados`.

9. **Pricing is configured in MongoDB** - Standard: $24.99/page, Sworn: $35/page. Automatic 10% discount for 7+ pages. Pricing data lives in the `bots` collection knowledge base.

10. **No automated tests exist** - When making changes, test manually via the admin dashboard and webhook endpoints. Consider adding tests for critical paths like webhook processing and quote generation.
