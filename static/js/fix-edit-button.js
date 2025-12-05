// FIX BOTÕES EDIT - Página de Treinamento
console.log('🔧 Corrigindo botões Edit da página de treinamento...');

document.addEventListener('DOMContentLoaded', function() {
    setTimeout(initEditButtons, 500);
});

function initEditButtons() {
    console.log('🎯 Inicializando botões Edit...');
    
    const editButtons = document.querySelectorAll('button.btn-primary, button:contains("Edit"), [class*="edit"]');
    
    console.log(`📊 Encontrados ${editButtons.length} botões`);
    
    editButtons.forEach((btn) => {
        const btnText = btn.textContent.trim();
        if (btnText.includes('Edit') || btn.classList.contains('btn-primary')) {
            console.log(`🔘 Configurando botão: ${btnText}`);
            
            const newBtn = btn.cloneNode(true);
            btn.parentNode.replaceChild(newBtn, btn);
            
            newBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                console.log('✏️ Botão Edit clicado!');
                
                const card = this.closest('[class*="card"], [class*="knowledge"], .border');
                
                if (!card) {
                    console.error('❌ Card não encontrado');
                    alert('Erro: Não foi possível localizar o item');
                    return;
                }
                
                const titleEl = card.querySelector('h3, h4, h5, strong, [class*="title"]');
                const contentEl = card.querySelector('p, [class*="content"], [class*="text"]');
                
                const title = titleEl ? titleEl.textContent.trim() : '';
                const content = contentEl ? contentEl.textContent.trim() : '';
                
                console.log('📝 Dados:', { title, content });
                
                openEditModal(title, content, card);
            });
        }
    });
    
    console.log('✅ Botões configurados!');
}

function openEditModal(title, content, cardElement) {
    console.log('📋 Abrindo modal...');
    
    let modal = document.getElementById('editModal');
    
    if (!modal) {
        modal = createEditModal();
        document.body.appendChild(modal);
    }
    
    document.getElementById('editTitle').value = title;
    document.getElementById('editContent').value = content;
    
    modal.dataset.cardId = cardElement.id || '';
    modal.style.display = 'flex';
    
    console.log('✅ Modal aberto');
}

function createEditModal() {
    const modal = document.createElement('div');
    modal.id = 'editModal';
    modal.style.cssText = `
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        z-index: 9999;
        align-items: center;
        justify-content: center;
    `;
    
    modal.innerHTML = `
        <div style="
            background: white;
            border-radius: 12px;
            padding: 30px;
            max-width: 600px;
            width: 90%;
            box-shadow: 0 8px 24px rgba(0,0,0,0.2);
        ">
            <h2 style="margin-top: 0; color: #1e3a8a;">✏️ Editar Knowledge</h2>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">Título:</label>
                <input type="text" id="editTitle" style="
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #e2e8f0;
                    border-radius: 8px;
                    font-size: 15px;
                    box-sizing: border-box;
                " placeholder="Digite o título..." />
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">Conteúdo:</label>
                <textarea id="editContent" rows="8" style="
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #e2e8f0;
                    border-radius: 8px;
                    font-size: 15px;
                    font-family: inherit;
                    resize: vertical;
                    box-sizing: border-box;
                " placeholder="Digite o conteúdo..."></textarea>
            </div>
            
            <div style="display: flex; gap: 12px; justify-content: flex-end;">
                <button onclick="closeEditModal()" style="
                    padding: 12px 24px;
                    background: #e2e8f0;
                    color: #334155;
                    border: none;
                    border-radius: 8px;
                    font-size: 15px;
                    font-weight: 600;
                    cursor: pointer;
                ">❌ Cancelar</button>
                <button onclick="saveEdit()" style="
                    padding: 12px 24px;
                    background: #3b82f6;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 15px;
                    font-weight: 600;
                    cursor: pointer;
                ">✅ Salvar</button>
            </div>
        </div>
    `;
    
    modal.addEventListener('click', function(e) {
        if (e.target === modal) closeEditModal();
    });
    
    return modal;
}

function closeEditModal() {
    const modal = document.getElementById('editModal');
    if (modal) modal.style.display = 'none';
}

function saveEdit() {
    const title = document.getElementById('editTitle').value.trim();
    const content = document.getElementById('editContent').value.trim();
    
    if (!title || !content) {
        alert('⚠️ Preencha título e conteúdo!');
        return;
    }
    
    console.log('💾 Salvando:', { title, content });
    
    fetch('/api/knowledge/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content })
    })
    .then(response => response.ok ? response.json() : Promise.reject(`HTTP ${response.status}`))
    .then(data => {
        console.log('✅ Salvo:', data);
        alert('✅ Salvo com sucesso!');
        closeEditModal();
        setTimeout(() => window.location.reload(), 500);
    })
    .catch(error => {
        console.error('❌ Erro:', error);
        alert('❌ Erro ao salvar: ' + error);
    });
}

window.closeEditModal = closeEditModal;
window.saveEdit = saveEdit;

console.log('✅ Script carregado!');
