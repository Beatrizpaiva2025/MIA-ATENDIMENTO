# ADD THESE ROUTES TO YOUR main.py FILE
# Copy and paste this at the end of main.py, before "if __name__ == '__main__':"

# ============================================================
# ROTA: PIPELINE (COM CONTROLE DE ACESSO)
# ============================================================
@app.get("/admin/pipeline")
async def admin_pipeline(request: Request):
    """Sales Pipeline page"""
    username = get_current_user(request)
    
    return templates.TemplateResponse(
        "admin_pipeline.html",
        {
            "request": request,
            "session": request.session,
            "username": username
        }
    )

# ============================================================
# ROTA: LEADS (COM CONTROLE DE ACESSO)
# ============================================================
@app.get("/admin/leads")
async def admin_leads(request: Request):
    """Leads Management page"""
    username = get_current_user(request)
    
    return templates.TemplateResponse(
        "admin_leads.html",
        {
            "request": request,
            "session": request.session,
            "username": username
        }
    )

# ============================================================
# API: TRAINING - FIX SAVE FUNCTIONALITY
# ============================================================

@app.post("/admin/training/knowledge/add")
async def add_knowledge_item(
    request: Request,
    category: str = Form(...),
    title: str = Form(...),
    content: str = Form(...)
):
    """Add new knowledge item to bot training"""
    username = get_current_user(request)
    
    try:
        # Get Mia bot
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            # Create bot if doesn't exist
            bot = {
                "name": "Mia",
                "personality": {
                    "goals": [],
                    "tone": "",
                    "restrictions": []
                },
                "knowledge_base": [],
                "faqs": []
            }
            await db.bots.insert_one(bot)
        
        # Add to knowledge base
        new_item = {
            "category": category,
            "title": title,
            "content": content,
            "created_by": username,
            "created_at": datetime.now()
        }
        
        await db.bots.update_one(
            {"name": "Mia"},
            {"$push": {"knowledge_base": new_item}}
        )
        
        return RedirectResponse(url="/admin/training", status_code=303)
        
    except Exception as e:
        logger.error(f"Error adding knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/training/faq/add")
async def add_faq_item(
    request: Request,
    question: str = Form(...),
    answer: str = Form(...)
):
    """Add new FAQ item to bot training"""
    username = get_current_user(request)
    
    try:
        # Get Mia bot
        bot = await db.bots.find_one({"name": "Mia"})
        
        if not bot:
            # Create bot if doesn't exist
            bot = {
                "name": "Mia",
                "personality": {
                    "goals": [],
                    "tone": "",
                    "restrictions": []
                },
                "knowledge_base": [],
                "faqs": []
            }
            await db.bots.insert_one(bot)
        
        # Add to FAQs
        new_item = {
            "question": question,
            "answer": answer,
            "created_by": username,
            "created_at": datetime.now()
        }
        
        await db.bots.update_one(
            {"name": "Mia"},
            {"$push": {"faqs": new_item}}
        )
        
        return RedirectResponse(url="/admin/training", status_code=303)
        
    except Exception as e:
        logger.error(f"Error adding FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/admin/training/knowledge/delete/{index}")
async def delete_knowledge_item(index: int, request: Request):
    """Delete knowledge item by index"""
    username = check_admin_access(request)
    
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        
        if bot and "knowledge_base" in bot:
            knowledge_base = bot["knowledge_base"]
            
            if 0 <= index < len(knowledge_base):
                knowledge_base.pop(index)
                
                await db.bots.update_one(
                    {"name": "Mia"},
                    {"$set": {"knowledge_base": knowledge_base}}
                )
                
                return {"success": True}
        
        raise HTTPException(status_code=404, detail="Item not found")
        
    except Exception as e:
        logger.error(f"Error deleting knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/admin/training/faq/delete/{index}")
async def delete_faq_item(index: int, request: Request):
    """Delete FAQ item by index"""
    username = check_admin_access(request)
    
    try:
        bot = await db.bots.find_one({"name": "Mia"})
        
        if bot and "faqs" in bot:
            faqs = bot["faqs"]
            
            if 0 <= index < len(faqs):
                faqs.pop(index)
                
                await db.bots.update_one(
                    {"name": "Mia"},
                    {"$set": {"faqs": faqs}}
                )
                
                return {"success": True}
        
        raise HTTPException(status_code=404, detail="Item not found")
        
    except Exception as e:
        logger.error(f"Error deleting FAQ: {e}")
        raise HTTPException(status_code=500, detail=str(e))
