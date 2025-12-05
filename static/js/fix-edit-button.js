// FIX BOTÕES EDIT - Página de Treinamento
console.log('🔧 Corrigindo botões Edit da página de treinamento...');

document.addEventListener('DOMContentLoaded', function() {
    setTimeout(initEditButtons, 500);
});

function initEditButtons() {
    console.log('🎯 Inicializando botões Edit...');
    
    // Buscar TODOS os botões e filtrar os que contêm "Edit"
    const allButtons = document.querySelectorAll('button');
    const editButtons = Array.from(allButtons).filter(btn => 
        btn.textContent.trim().includes('Edit') || 
        btn.classList.contains('btn-primary')
    );
    
    console.log(`📊 Encontrados ${editButtons.length} botões Edit`);
    
    editButtons.forEach((btn) => {
        const btnText = btn.textContent.trim();
        console.log(`🔘 Configurando botão: ${btnText}`);
        
        // Clonar para remover event listeners antigos
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);
        
        newBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            console.log('✏️ Botão Edit clicado!');
            
            // Subir até encontrar o card/container pai
            const card = this.closest('.border, [class*="card"], [class*="knowledge"], .bg-white, .rounded-lg');
            
            if (!card) {
                console.error('❌ Card não encontrado');
                alert('Erro: Não foi possível localizar o item');
                return;
            }
            
            // Buscar título e conteúdo com seletores mais específicos
            const titleEl = card.querySelector('h3, h4, h5, strong, .font-semibold, .font-bold');
            const contentEl = card.querySelector('p:not(:empty), .text-gray-600, .text-gray-500');
            
            const title = titleEl ? titleEl.textContent.trim() : '';
            const content = contentEl ? contentEl.textContent.trim() : '';
            
            console.log('📝 Dados:', { title, content });
            
            openEditModal(title, content, card);
        });
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
    
    // Guardar referência ao card
    modal._cardElement = cardElement;
    modal.style.display = 'flex';
    
    // Focar no primeiro input
    setTimeout(() => document.getElementById('editTitle').focus(), 100);
    
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
                <button id="btnCancelEdit" style="
                    padding: 12px 24px;
                    background: #e2e8f0;
                    color: #334155;
                    border: none;
                    border-radius: 8px;
                    font-size: 15px;
                    font-weight: 600;
                    cursor: pointer;
                ">❌ Cancelar</button>
                <button id="btnSaveEdit" style="
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
    
    // Event listeners
    modal.addEventListener('click', function(e) {
        if (e.target === modal) closeEditModal();
    });
    
    // Usar setTimeout para garantir que elementos existem
    setTimeout(() => {
        document.getElementById('btnCancelEdit').addEventListener('click', closeEditModal);
        document.getElementById('btnSaveEdit').addEventListener('click', saveEdit);
    }, 0);
    
    // Fechar com ESC
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeEditModal();
    });
    
    return modal;
}

function closeEditModal() {
    const modal = document.getElementById('editModal');
    if (modal) {
        modal.style.display = 'none';
        modal._cardElement = null;
    }
}

function saveEdit() {
    const title = document.getElementById('editTitle').value.trim();
    const content = document.getElementById('editContent').value.trim();
    
    if (!title || !content) {
        alert('⚠️ Preencha título e conteúdo!');
        return;
    }
    
    console.log('💾 Salvando:', { title, content });
    
    // Desabilitar botão enquanto salva
    const btnSave = document.getElementById('btnSaveEdit');
    btnSave.disabled = true;
    btnSave.textContent = '⏳ Salvando...';
    
    fetch('/api/knowledge/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content })
    })
    .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    })
    .then(data => {
        console.log('✅ Salvo:', data);
        alert('✅ Salvo com sucesso!');
        closeEditModal();
        setTimeout(() => window.location.reload(), 500);
    })
    .catch(error => {
        console.error('❌ Erro:', error);
        alert('❌ Erro ao salvar: ' + error.message);
    })
    .finally(() => {
        btnSave.disabled = false;
        btnSave.textContent = '✅ Salvar';
    });
}

// Expor funções globalmente (para compatibilidade)
window.closeEditModal = closeEditModal;
window.saveEdit = saveEdit;
window.initEditButtons = initEditButtons;

console.log('✅ Script carregado!');
