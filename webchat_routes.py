"""
============================================================
WEBCHAT ROUTES - Chat Widget para Portal Legacy Translations
============================================================
API e Widget para integrar chat no portal.legacytranslations.com
Separado do WhatsApp para seguranca e flexibilidade
============================================================
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from datetime import datetime
from typing import Optional, Dict, List
from pydantic import BaseModel
import os
import logging
import traceback
import uuid

from openai import OpenAI
from admin_training_routes import get_database

# ============================================================
# CONFIGURACAO
# ============================================================
router = APIRouter(prefix="/webchat", tags=["webchat"])
logger = logging.getLogger(__name__)

# Cliente OpenAI
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Database
db = get_database()

# Dominios permitidos (CORS)
ALLOWED_ORIGINS = [
    "https://portal.legacytranslations.com",
    "http://localhost:3000",  # Desenvolvimento
    "http://localhost:5000",
    "http://127.0.0.1:5000"
]


# ============================================================
# MODELOS PYDANTIC
# ============================================================
class WebChatMessage(BaseModel):
    session_id: str
    message: str
    visitor_name: Optional[str] = None
    visitor_email: Optional[str] = None


class WebChatResponse(BaseModel):
    success: bool
    message: str
    session_id: str
    timestamp: str


# ============================================================
# FUNCOES AUXILIARES
# ============================================================
async def get_webchat_training() -> str:
    """Busca treinamento dinamico do bot para WebChat"""
    try:
        bot = await db.bots.find_one({"name": "Mia"})

        if not bot:
            return """Voce e a Mia, assistente virtual da Legacy Translations.

Especialidades:
- Traducoes certificadas
- Cotacoes de documentos
- Prazos de entrega
- Formas de pagamento

Responda de forma profissional, educada e objetiva."""

        # Extrair dados do bot
        personality = bot.get("personality", {})
        knowledge_base = bot.get("knowledge_base", [])
        faqs = bot.get("faqs", [])

        # Montar prompt dinamico
        prompt_parts = []

        # Contexto especifico para WebChat
        prompt_parts.append("""CONTEXTO: Voce esta atendendo pelo chat do portal web.
O visitante pode estar em qualquer pagina do site.
Seja proativo em oferecer ajuda e coletar informacoes de contato.""")

        # Objetivos
        if personality.get("goals"):
            goals_text = "\n".join(personality["goals"]) if isinstance(personality["goals"], list) else personality["goals"]
            prompt_parts.append(f"**OBJETIVOS:**\n{goals_text}")

        # Tom de voz
        if personality.get("tone"):
            prompt_parts.append(f"**TOM DE VOZ:**\n{personality['tone']}")

        # Restricoes
        if personality.get("restrictions"):
            restrictions_text = "\n".join(personality["restrictions"]) if isinstance(personality["restrictions"], list) else personality["restrictions"]
            prompt_parts.append(f"**RESTRICOES:**\n{restrictions_text}")

        # Base de conhecimento
        if knowledge_base:
            kb_text = "\n\n".join([
                f"**{item.get('title', 'Info')}:**\n{item.get('content', '')}"
                for item in knowledge_base
            ])
            prompt_parts.append(f"**BASE DE CONHECIMENTO:**\n{kb_text}")

        # FAQs
        if faqs:
            faq_text = "\n\n".join([
                f"P: {item.get('question', '')}\nR: {item.get('answer', '')}"
                for item in faqs
            ])
            prompt_parts.append(f"**PERGUNTAS FREQUENTES:**\n{faq_text}")

        return "\n\n".join(prompt_parts)

    except Exception as e:
        logger.error(f"Erro ao buscar treinamento webchat: {e}")
        return "Voce e a Mia, assistente da Legacy Translations. Responda de forma profissional."


async def get_webchat_context(session_id: str, limit: int = 10) -> List[Dict]:
    """Busca ultimas mensagens da sessao de webchat"""
    try:
        messages = await db.webchat_conversas.find(
            {"session_id": session_id}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)

        messages.reverse()

        return [
            {"role": msg["role"], "content": msg["message"]}
            for msg in messages
        ]
    except Exception as e:
        logger.error(f"Erro ao buscar contexto webchat: {e}")
        return []


async def process_webchat_message(session_id: str, message: str, visitor_info: Dict = None) -> str:
    """Processa mensagem do webchat com GPT-4"""
    try:
        # Buscar treinamento
        system_prompt = await get_webchat_training()

        # Adicionar info do visitante se disponivel
        if visitor_info:
            visitor_context = f"\nINFO DO VISITANTE: Nome: {visitor_info.get('name', 'Desconhecido')}, Email: {visitor_info.get('email', 'Nao informado')}"
            system_prompt += visitor_context

        # Buscar contexto
        context = await get_webchat_context(session_id)

        # Montar mensagens
        messages = [
            {"role": "system", "content": system_prompt}
        ] + context + [
            {"role": "user", "content": message}
        ]

        # Chamar GPT-4
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )

        reply = response.choices[0].message.content

        # Salvar conversa
        await db.webchat_conversas.insert_one({
            "session_id": session_id,
            "message": message,
            "role": "user",
            "timestamp": datetime.now(),
            "visitor_info": visitor_info,
            "canal": "WebChat"
        })

        await db.webchat_conversas.insert_one({
            "session_id": session_id,
            "message": reply,
            "role": "assistant",
            "timestamp": datetime.now(),
            "canal": "WebChat"
        })

        # Analisar para aprendizado hibrido
        await analisar_incerteza_webchat(session_id, message, reply)

        return reply

    except Exception as e:
        logger.error(f"Erro ao processar webchat: {str(e)}")
        logger.error(traceback.format_exc())
        return "Desculpe, tive um problema. Pode tentar novamente?"


async def analisar_incerteza_webchat(session_id: str, user_message: str, bot_response: str):
    """Analisa se IA demonstrou incerteza e sugere novo conhecimento"""
    try:
        sinais_incerteza = [
            "nao tenho certeza", "nao sei", "nao posso",
            "nao consigo", "nao tenho essa informacao"
        ]

        response_lower = bot_response.lower()

        if any(sinal in response_lower for sinal in sinais_incerteza):
            # Gerar sugestao de conhecimento
            suggestion_prompt = f"""Analise esta conversa e sugira conhecimento para a base:

PERGUNTA: {user_message}
RESPOSTA: {bot_response}

Gere:
TITULO: [titulo curto]
CONTEUDO: [explicacao completa]"""

            suggestion_response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Voce ajuda a criar base de conhecimento."},
                    {"role": "user", "content": suggestion_prompt}
                ],
                max_tokens=400
            )

            suggestion_text = suggestion_response.choices[0].message.content

            # Extrair titulo e conteudo
            lines = suggestion_text.split('\n')
            title = ""
            content = ""

            for line in lines:
                if line.startswith("TITULO:"):
                    title = line.replace("TITULO:", "").strip()
                elif line.startswith("CONTEUDO:"):
                    content = line.replace("CONTEUDO:", "").strip()
                elif content:
                    content += "\n" + line

            if title and content:
                await db.knowledge_suggestions.insert_one({
                    "title": title,
                    "content": content.strip(),
                    "user_question": user_message,
                    "bot_response": bot_response,
                    "session_id": session_id,
                    "source": "webchat",
                    "status": "pending",
                    "created_at": datetime.now()
                })

                logger.info(f"Sugestao de conhecimento salva: {title}")

    except Exception as e:
        logger.error(f"Erro ao analisar incerteza: {e}")


# ============================================================
# ENDPOINTS API
# ============================================================
@router.post("/send")
async def send_message(request: Request, chat_message: WebChatMessage):
    """Recebe mensagem do widget e retorna resposta da IA"""
    try:
        # Verificar origem (CORS basico)
        origin = request.headers.get("origin", "")
        # Em producao, descomentar:
        # if origin not in ALLOWED_ORIGINS:
        #     raise HTTPException(status_code=403, detail="Origem nao permitida")

        # Processar mensagem
        visitor_info = {
            "name": chat_message.visitor_name,
            "email": chat_message.visitor_email
        }

        reply = await process_webchat_message(
            session_id=chat_message.session_id,
            message=chat_message.message,
            visitor_info=visitor_info
        )

        return JSONResponse({
            "success": True,
            "message": reply,
            "session_id": chat_message.session_id,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Erro no webchat/send: {e}")
        return JSONResponse({
            "success": False,
            "message": "Erro ao processar mensagem",
            "error": str(e)
        }, status_code=500)


@router.get("/session/new")
async def new_session():
    """Cria nova sessao de chat"""
    session_id = str(uuid.uuid4())

    # Registrar sessao
    await db.webchat_sessions.insert_one({
        "session_id": session_id,
        "created_at": datetime.now(),
        "status": "active"
    })

    return JSONResponse({
        "session_id": session_id,
        "welcome_message": "Ola! Sou a Mia, assistente virtual da Legacy Translations. Como posso ajudar voce hoje?"
    })


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    """Retorna historico da sessao"""
    try:
        messages = await db.webchat_conversas.find(
            {"session_id": session_id}
        ).sort("timestamp", 1).to_list(length=100)

        history = [
            {
                "role": msg["role"],
                "message": msg["message"],
                "timestamp": msg["timestamp"].isoformat()
            }
            for msg in messages
        ]

        return JSONResponse({
            "session_id": session_id,
            "messages": history,
            "count": len(history)
        })

    except Exception as e:
        logger.error(f"Erro ao buscar historico: {e}")
        return JSONResponse({"messages": [], "error": str(e)})


@router.post("/lead/capture")
async def capture_lead(request: Request):
    """Captura lead do webchat"""
    try:
        data = await request.json()

        lead = {
            "nome": data.get("name"),
            "email": data.get("email"),
            "telefone": data.get("phone"),
            "session_id": data.get("session_id"),
            "origem": "WebChat Portal",
            "canal": "WebChat",
            "estagio": "novo",
            "temperatura": "morno",
            "created_at": datetime.now(),
            "source_url": data.get("source_url", "portal.legacytranslations.com")
        }

        await db.leads.insert_one(lead)

        logger.info(f"Lead capturado do webchat: {lead['email']}")

        return JSONResponse({
            "success": True,
            "message": "Obrigado! Entraremos em contato em breve."
        })

    except Exception as e:
        logger.error(f"Erro ao capturar lead: {e}")
        return JSONResponse({"success": False, "error": str(e)})


# ============================================================
# WIDGET JAVASCRIPT (EMBEDDABLE)
# ============================================================
@router.get("/widget.js", response_class=HTMLResponse)
async def get_widget_js():
    """Retorna o widget JavaScript para embed"""

    # URL do backend (ajustar para producao)
    backend_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:10000")

    widget_js = f"""
// ============================================================
// MIA WEBCHAT WIDGET - Legacy Translations
// Copie este script para seu site
// ============================================================
(function() {{
    'use strict';

    const BACKEND_URL = '{backend_url}';
    let sessionId = null;
    let isOpen = false;
    let visitorInfo = {{ name: null, email: null }};

    // Estilos do widget
    const styles = `
        #mia-chat-container {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 99999;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}

        #mia-chat-button {{
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: linear-gradient(135deg, #1e3a5f 0%, #2c5282 100%);
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(30, 58, 95, 0.4);
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}

        #mia-chat-button:hover {{
            transform: scale(1.1);
            box-shadow: 0 6px 20px rgba(30, 58, 95, 0.5);
        }}

        #mia-chat-button svg {{
            width: 28px;
            height: 28px;
            fill: white;
        }}

        #mia-chat-window {{
            display: none;
            position: absolute;
            bottom: 80px;
            right: 0;
            width: 380px;
            height: 520px;
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
            flex-direction: column;
        }}

        #mia-chat-window.open {{
            display: flex;
            animation: slideUp 0.3s ease;
        }}

        @keyframes slideUp {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        #mia-chat-header {{
            background: linear-gradient(135deg, #1e3a5f 0%, #2c5282 100%);
            color: white;
            padding: 16px 20px;
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        #mia-chat-header img {{
            width: 40px;
            height: 40px;
            border-radius: 50%;
            border: 2px solid rgba(255,255,255,0.3);
        }}

        #mia-chat-header-info h3 {{
            margin: 0;
            font-size: 16px;
            font-weight: 600;
        }}

        #mia-chat-header-info span {{
            font-size: 12px;
            opacity: 0.8;
        }}

        #mia-chat-close {{
            margin-left: auto;
            background: none;
            border: none;
            color: white;
            cursor: pointer;
            font-size: 24px;
            opacity: 0.7;
            transition: opacity 0.2s;
        }}

        #mia-chat-close:hover {{
            opacity: 1;
        }}

        #mia-chat-messages {{
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            background: #f8fafc;
        }}

        .mia-message {{
            margin-bottom: 12px;
            display: flex;
            flex-direction: column;
        }}

        .mia-message.user {{
            align-items: flex-end;
        }}

        .mia-message.assistant {{
            align-items: flex-start;
        }}

        .mia-message-bubble {{
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 16px;
            font-size: 14px;
            line-height: 1.4;
        }}

        .mia-message.user .mia-message-bubble {{
            background: linear-gradient(135deg, #1e3a5f 0%, #2c5282 100%);
            color: white;
            border-bottom-right-radius: 4px;
        }}

        .mia-message.assistant .mia-message-bubble {{
            background: white;
            color: #333;
            border: 1px solid #e2e8f0;
            border-bottom-left-radius: 4px;
        }}

        #mia-chat-input-area {{
            padding: 12px 16px;
            background: white;
            border-top: 1px solid #e2e8f0;
            display: flex;
            gap: 8px;
        }}

        #mia-chat-input {{
            flex: 1;
            border: 1px solid #e2e8f0;
            border-radius: 24px;
            padding: 10px 16px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }}

        #mia-chat-input:focus {{
            border-color: #1e3a5f;
        }}

        #mia-chat-send {{
            width: 44px;
            height: 44px;
            border-radius: 50%;
            background: linear-gradient(135deg, #1e3a5f 0%, #2c5282 100%);
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.2s;
        }}

        #mia-chat-send:hover {{
            transform: scale(1.05);
        }}

        #mia-chat-send svg {{
            width: 20px;
            height: 20px;
            fill: white;
        }}

        .mia-typing {{
            display: flex;
            gap: 4px;
            padding: 12px 16px;
        }}

        .mia-typing-dot {{
            width: 8px;
            height: 8px;
            background: #1e3a5f;
            border-radius: 50%;
            animation: typing 1.4s infinite;
        }}

        .mia-typing-dot:nth-child(2) {{ animation-delay: 0.2s; }}
        .mia-typing-dot:nth-child(3) {{ animation-delay: 0.4s; }}

        @keyframes typing {{
            0%, 60%, 100% {{ transform: translateY(0); opacity: 0.4; }}
            30% {{ transform: translateY(-4px); opacity: 1; }}
        }}

        @media (max-width: 480px) {{
            #mia-chat-window {{
                width: calc(100vw - 40px);
                height: 70vh;
                bottom: 70px;
                right: -10px;
            }}
        }}
    `;

    // HTML do widget
    const html = `
        <div id="mia-chat-container">
            <button id="mia-chat-button" aria-label="Abrir chat">
                <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>
            </button>

            <div id="mia-chat-window">
                <div id="mia-chat-header">
                    <img src="{backend_url}/static/images/logo_legacy.jpeg" alt="Mia" onerror="this.style.display='none'">
                    <div id="mia-chat-header-info">
                        <h3>Mia - Legacy Translations</h3>
                        <span>Online agora</span>
                    </div>
                    <button id="mia-chat-close">&times;</button>
                </div>

                <div id="mia-chat-messages"></div>

                <div id="mia-chat-input-area">
                    <input type="text" id="mia-chat-input" placeholder="Digite sua mensagem..." autocomplete="off">
                    <button id="mia-chat-send">
                        <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                    </button>
                </div>
            </div>
        </div>
    `;

    // Inicializar widget
    function init() {{
        // Injetar estilos
        const styleEl = document.createElement('style');
        styleEl.textContent = styles;
        document.head.appendChild(styleEl);

        // Injetar HTML
        const container = document.createElement('div');
        container.innerHTML = html;
        document.body.appendChild(container.firstElementChild);

        // Elementos
        const chatButton = document.getElementById('mia-chat-button');
        const chatWindow = document.getElementById('mia-chat-window');
        const chatClose = document.getElementById('mia-chat-close');
        const chatInput = document.getElementById('mia-chat-input');
        const chatSend = document.getElementById('mia-chat-send');
        const messagesContainer = document.getElementById('mia-chat-messages');

        // Event listeners
        chatButton.addEventListener('click', toggleChat);
        chatClose.addEventListener('click', toggleChat);
        chatSend.addEventListener('click', sendMessage);
        chatInput.addEventListener('keypress', function(e) {{
            if (e.key === 'Enter') sendMessage();
        }});

        // Funcoes
        async function toggleChat() {{
            isOpen = !isOpen;
            chatWindow.classList.toggle('open', isOpen);

            if (isOpen && !sessionId) {{
                await startSession();
            }}
        }}

        async function startSession() {{
            try {{
                const response = await fetch(BACKEND_URL + '/webchat/session/new');
                const data = await response.json();
                sessionId = data.session_id;

                // Mensagem de boas-vindas
                addMessage('assistant', data.welcome_message);
            }} catch (error) {{
                console.error('Erro ao iniciar sessao:', error);
                addMessage('assistant', 'Ola! Como posso ajudar?');
            }}
        }}

        async function sendMessage() {{
            const message = chatInput.value.trim();
            if (!message) return;

            // Adicionar mensagem do usuario
            addMessage('user', message);
            chatInput.value = '';

            // Mostrar typing
            showTyping();

            try {{
                const response = await fetch(BACKEND_URL + '/webchat/send', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{
                        session_id: sessionId,
                        message: message,
                        visitor_name: visitorInfo.name,
                        visitor_email: visitorInfo.email
                    }})
                }});

                const data = await response.json();
                hideTyping();

                if (data.success) {{
                    addMessage('assistant', data.message);
                }} else {{
                    addMessage('assistant', 'Desculpe, ocorreu um erro. Tente novamente.');
                }}
            }} catch (error) {{
                hideTyping();
                console.error('Erro ao enviar mensagem:', error);
                addMessage('assistant', 'Desculpe, nao consegui processar sua mensagem.');
            }}
        }}

        function addMessage(role, text) {{
            const messageDiv = document.createElement('div');
            messageDiv.className = 'mia-message ' + role;
            messageDiv.innerHTML = '<div class="mia-message-bubble">' + escapeHtml(text) + '</div>';
            messagesContainer.appendChild(messageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }}

        function showTyping() {{
            const typingDiv = document.createElement('div');
            typingDiv.id = 'mia-typing';
            typingDiv.className = 'mia-message assistant';
            typingDiv.innerHTML = '<div class="mia-typing"><div class="mia-typing-dot"></div><div class="mia-typing-dot"></div><div class="mia-typing-dot"></div></div>';
            messagesContainer.appendChild(typingDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }}

        function hideTyping() {{
            const typing = document.getElementById('mia-typing');
            if (typing) typing.remove();
        }}

        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}
    }}

    // Inicializar quando DOM estiver pronto
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', init);
    }} else {{
        init();
    }}

    // API publica
    window.MiaChat = {{
        open: function() {{
            document.getElementById('mia-chat-button').click();
        }},
        setVisitor: function(name, email) {{
            visitorInfo.name = name;
            visitorInfo.email = email;
        }}
    }};
}})();
"""

    return HTMLResponse(
        content=widget_js,
        media_type="application/javascript"
    )


# ============================================================
# PAGINA DE TESTE DO WIDGET
# ============================================================
@router.get("/test", response_class=HTMLResponse)
async def test_page():
    """Pagina de teste do widget"""
    backend_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:10000")

    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Teste Widget MIA - Legacy Translations</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 40px;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #1e3a5f;
            margin-bottom: 10px;
        }}
        .subtitle {{
            color: #666;
            margin-bottom: 30px;
        }}
        .code-block {{
            background: #1e3a5f;
            color: #fff;
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            margin: 20px 0;
        }}
        .instructions {{
            background: #f8fafc;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #1e3a5f;
        }}
        .instructions h3 {{
            margin-top: 0;
            color: #1e3a5f;
        }}
        .instructions ol {{
            margin-bottom: 0;
        }}
        .test-button {{
            display: inline-block;
            padding: 12px 24px;
            background: #1e3a5f;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            margin-top: 20px;
        }}
        .test-button:hover {{
            background: #2c5282;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Widget de Chat MIA</h1>
        <p class="subtitle">Teste e integre o chat no portal.legacytranslations.com</p>

        <div class="instructions">
            <h3>Como integrar no seu site:</h3>
            <ol>
                <li>Copie o codigo abaixo</li>
                <li>Cole antes do fechamento da tag <code>&lt;/body&gt;</code></li>
                <li>O widget aparecera automaticamente no canto inferior direito</li>
            </ol>
        </div>

        <div class="code-block">
&lt;script src="{backend_url}/webchat/widget.js"&gt;&lt;/script&gt;
        </div>

        <h3>Funcoes JavaScript disponiveis:</h3>
        <div class="code-block">
// Abrir chat programaticamente
MiaChat.open();

// Definir informacoes do visitante
MiaChat.setVisitor('Nome do Cliente', 'email@exemplo.com');
        </div>

        <button class="test-button" onclick="MiaChat.open()">
            Testar Widget Agora
        </button>

        <p style="margin-top: 30px; color: #666;">
            O widget ja esta carregado nesta pagina. Clique no botao acima ou no icone de chat no canto inferior direito.
        </p>
    </div>

    <!-- Widget carregado para teste -->
    <script src="{backend_url}/webchat/widget.js"></script>
</body>
</html>
"""
