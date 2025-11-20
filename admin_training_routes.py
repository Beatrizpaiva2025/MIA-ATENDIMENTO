admin_training_routes.py - VERSÃO CORRIGIDA COM VARIÁVEIS EM PORTUGUÊS
Rotas para gerenciamento de treinamento da IA
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
from datetime import datetime
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ CORREÇÃO: Usar caminho relativo igual ao main.py
templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/admin/treinamento", tags=["Admin Training"])

# ============================================================
# CONEXÃO MONGODB
# ============================================================

def get_database():
    """Obter database MongoDB com fallback"""
    try:
        # Tentar MONGODB_URI primeiro
        mongo_uri = os.getenv("MONGODB_URI")
        if not mongo_uri:
            # Fallback para MONGODB_URL
            mongo_uri = os.getenv("MONGODB_URL")
        
        if not mongo_uri:
            logger.error("❌ Nenhuma URI MongoDB configurada!")
            raise ValueError("MongoDB URI não configurada")
        
        logger.info("🔗 Conectando MongoDB Atlas")
        client = AsyncIOMotorClient(mongo_uri)
        db = client.get_database()
        logger.info("✅ Database fallback criado")
        return db
    except Exception as e:
        logger.error(f"❌ Erro ao conectar MongoDB: {e}")
        raise

# Inicializar database
db = get_database()

# ============================================================
# HELPER FUNCTIONS
# ============================================================

async def get_or_create_bot():
    """Buscar ou criar bot Mia"""
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            logger.warning("⚠️ Bot Mia não encontrado, criando...")
            bot_data = {
                "name": "Mia",
                "personality": {
                    "tone": "Profissional e acolhedor",
                    "goals": [
                        "Qualificar leads de tradução",
                        "Agendar reuniões",
                        "Fornecer informações sobre serviços"
                    ],
                    "restrictions": [
                        "Não fornecer orçamentos sem análise",
                        "Sempre transferir casos complexos para humano"
                    ]
                },
                "knowledge_base": [],
                "faqs": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            result = await db.bots.insert_one(bot_data)
            bot = await db.bots.find_one({"_id": result.inserted_id})
            logger.info(f"✅ Bot Mia criado: {result.inserted_id}")
        else:
            logger.info(f"✅ Bot Mia encontrado: {bot['_id']}")
        
        return bot
    except Exception as e:
        logger.error(f"❌ Erro ao buscar/criar bot: {e}")
        raise

# ============================================================
# ROTAS DE VISUALIZAÇÃO
# ============================================================

@router.get("/", response_class=HTMLResponse, name="admin_training")
async def training_page(request: Request):
    """Página principal de treinamento da IA"""
