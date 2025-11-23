{% extends "admin_base.html" %}

{% block title %}Treinamento - MIA Admin{% endblock %}

{% block extra_style %}
<style>
    .section-card {
        background: white;
        border-radius: 12px;
        padding: 25px;
        margin-bottom: 25px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        border-left: 4px solid #ff9800;
    }

    .section-header {
        display: flex;
        align-items: center;
        margin-bottom: 20px;
        padding-bottom: 15px;
        border-bottom: 2px solid #f0f0f0;
    }

    .section-icon {
        font-size: 2em;
        margin-right: 15px;
    }

    .section-title {
        font-size: 1.5em;
        color: #1e3a5f;
        margin: 0;
    }

    .form-group {
        margin-bottom: 20px;
    }

    .form-label {
        display: block;
        font-weight: 600;
        color: #1e3a5f;
        margin-bottom: 8px;
        font-size: 1.05em;
    }

    .form-input, .form-textarea, .form-select {
        width: 100%;
        padding: 12px 15px;
        border: 2px solid #e0e0e0;
        border-radius: 8px;
        font-size: 1em;
        transition: all 0.3s;
        font-family: inherit;
    }

    .form-input:focus, .form-textarea:focus, .form-select:focus {
        outline: none;
        border-color: #5dade2;
        box-shadow: 0 0 0 3px rgba(93, 173, 226, 0.1);
    }

    .form-textarea {
        min-height: 120px;
        resize: vertical;
    }

    .btn-primary {
        background: linear-gradient(135deg, #ff9800 0%, #ff5722 100%);
        color: white;
        padding: 12px 30px;
        border: none;
        border-radius: 8px;
        font-size: 1.1em;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s;
        box-shadow: 0 4px 12px rgba(255, 152, 0, 0.3);
    }

    .btn-primary:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(255, 152, 0, 0.4);
    }

    .btn-secondary {
        background: #5dade2;
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 6px;
        font-size: 0.95em;
        cursor: pointer;
        margin-right: 10px;
        transition: all 0.3s;
    }

    .btn-secondary:hover {
        background: #4a9dd1;
    }

    .knowledge-item, .faq-item {
        background: #f8f9fa;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 12px;
        border-left: 3px solid #5dade2;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .item-content {
        flex: 1;
    }

    .item-title {
        font-weight: 600;
        color: #1e3a5f;
        margin-bottom: 5px;
    }

    .item-text {
        color: #666;
        font-size: 0.95em;
    }

    .item-actions {
        display: flex;
        gap: 8px;
    }

    .btn-edit, .btn-delete {
        padding: 6px 12px;
        border: none;
        border-radius: 5px;
        cursor: pointer;
        font-size: 0.9em;
        transition: all 0.2s;
    }

    .btn-edit {
        background: #5dade2;
        color: white;
    }

    .btn-edit:hover {
        background: #4a9dd1;
    }

    .btn-delete {
        background: #e74c3c;
        color: white;
    }

    .btn-delete:hover {
        background: #c0392b;
    }

    .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 15px;
        margin-bottom: 25px;
    }

    .stat-card {
        background: linear-gradient(135deg, #5dade2 0%, #4a9dd1 100%);
        color: white;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
    }

    .stat-number {
        font-size: 2.5em;
        font-weight: bold;
        margin-bottom: 5px;
    }

    .stat-label {
        font-size: 0.95em;
        opacity: 0.9;
    }
</style>
{% endblock %}

{% block content %}
<div class="page-header">
    <h1>🎓 Treinamento da IA</h1>
    <p>Configure o conhecimento e personalidade da MIA</p>
</div>

<!-- STATS -->
<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-number">{{ conhecimentos|length }}</div>
        <div class="stat-label">Base de Conhecimento</div>
    </div>
    <div class="stat-card" style="background: linear-gradient(135deg, #ff9800 0%, #ff5722 100%);">
        <div class="stat-number">{{ faqs|length }}</div>
        <div class="stat-label">FAQs Cadastradas</div>
    </div>
</div>

<!-- PERSONALIDADE -->
<div class="section-card">
    <div class="section-header">
        <span class="section-icon">🤖</span>
        <h2 class="section-title">Personalidade da IA</h2>
    </div>
    
    <form method="POST" action="/admin/treinamento/personalidade">
        <div class="form-group">
            <label class="form-label">Tom de Voz</label>
            <select name="tom_voz" class="form-select">
                <option value="amigavel" {% if personalidade.tom_voz == 'amigavel' %}selected{% endif %}>Amigável e Casual</option>
                <option value="profissional" {% if personalidade.tom_voz == 'profissional' %}selected{% endif %}>Profissional</option>
                <option value="formal" {% if personalidade.tom_voz == 'formal' %}selected{% endif %}>Formal</option>
            </select>
        </div>

        <div class="form-group">
            <label class="form-label">Descrição da Empresa</label>
            <textarea name="descricao" class="form-textarea" placeholder="Ex: Você é o assistente oficial da empresa Legacy Translations, especializada em..."required>{{ personalidade.descricao or '' }}</textarea>
        </div>

        <div class="form-group">
            <label class="form-label">Objetivos da IA</label>
            <textarea name="objetivos" class="form-textarea" placeholder="Siga as instruções abaixo para responder a clientes de forma educada..." required>{{ personalidade.objetivos or '' }}</textarea>
        </div>

        <div class="form-group">
            <label class="form-label">Restrições</label>
            <textarea name="restricoes" class="form-textarea" placeholder="Uma restrição por linha">{{ personalidade.restricoes or '' }}</textarea>
        </div>

        <button type="submit" class="btn-primary">💾 Salvar Personalidade</button>
    </form>
</div>

<!-- BASE DE CONHECIMENTO -->
<div class="section-card">
    <div class="section-header">
        <span class="section-icon">📚</span>
        <h2 class="section-title">Base de Conhecimento</h2>
    </div>

    <form method="POST" action="/admin/treinamento/conhecimento" style="margin-bottom: 25px;">
        <div class="form-group">
            <label class="form-label">Título</label>
            <input type="text" name="titulo" class="form-input" placeholder="Ex: Serviços de Tradução Jurídica" required>
        </div>

        <div class="form-group">
            <label class="form-label">Conteúdo</label>
            <textarea name="conteudo" class="form-textarea" placeholder="Descreva as informações que a IA deve saber sobre este tópico..." required></textarea>
        </div>

        <button type="submit" class="btn-primary">➕ Adicionar Conhecimento</button>
    </form>

    {% if conhecimentos %}
        {% for item in conhecimentos %}
        <div class="knowledge-item">
            <div class="item-content">
                <div class="item-title">{{ item.titulo }}</div>
                <div class="item-text">{{ item.conteudo[:100] }}...</div>
            </div>
            <div class="item-actions">
                <button class="btn-edit" onclick="editarConhecimento('{{ item._id }}')">✏️ Editar</button>
                <button class="btn-delete" onclick="deletarConhecimento('{{ item._id }}')">🗑️ Deletar</button>
            </div>
        </div>
        {% endfor %}
    {% else %}
        <p style="text-align: center; color: #999; padding: 30px;">Nenhum conhecimento cadastrado ainda.</p>
    {% endif %}
</div>

<!-- FAQs -->
<div class="section-card">
    <div class="section-header">
        <span class="section-icon">❓</span>
        <h2 class="section-title">FAQs Cadastradas</h2>
    </div>

    <form method="POST" action="/admin/treinamento/faq" style="margin-bottom: 25px;">
        <div class="form-group">
            <label class="form-label">Pergunta</label>
            <input type="text" name="pergunta" class="form-input" placeholder="Ex: Quanto custa uma tradução juramentada?" required>
        </div>

        <div class="form-group">
            <label class="form-label">Resposta</label>
            <textarea name="resposta" class="form-textarea" placeholder="Digite a resposta completa..." required></textarea>
        </div>

        <button type="submit" class="btn-primary">➕ Adicionar FAQ</button>
    </form>

    {% if faqs %}
        {% for faq in faqs %}
        <div class="faq-item">
            <div class="item-content">
                <div class="item-title">{{ faq.pergunta }}</div>
                <div class="item-text">{{ faq.resposta[:100] }}...</div>
            </div>
            <div class="item-actions">
                <button class="btn-edit" onclick="editarFAQ('{{ faq._id }}')">✏️ Editar</button>
                <button class="btn-delete" onclick="deletarFAQ('{{ faq._id }}')">🗑️ Deletar</button>
            </div>
        </div>
        {% endfor %}
    {% else %}
        <p style="text-align: center; color: #999; padding: 30px;">Nenhuma FAQ cadastrada ainda.</p>
    {% endif %}
</div>
{% endblock %}

{% block extra_scripts %}
<script>
    function editarConhecimento(id) {
        alert('Edição em desenvolvimento. ID: ' + id);
    }

    function deletarConhecimento(id) {
        if (confirm('Deletar este conhecimento?')) {
            fetch('/admin/treinamento/conhecimento/' + id, { method: 'DELETE' })
                .then(() => location.reload());
        }
    }

    function editarFAQ(id) {
        alert('Edição em desenvolvimento. ID: ' + id);
    }

    function deletarFAQ(id) {
        if (confirm('Deletar esta FAQ?')) {
            fetch('/admin/treinamento/faq/' + id, { method: 'DELETE' })
                .then(() => location.reload());
        }
    }
</script>
{% endblock %}
