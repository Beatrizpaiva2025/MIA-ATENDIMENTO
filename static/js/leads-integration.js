// ============================================
// DASHBOARD MIA - VERSAO STANDALONE COMPLETA
// FUNCIONA 100% OFFLINE COM DADOS REAIS
// Versao: 5.0.0-STANDALONE
// ============================================

console.log('DASHBOARD STANDALONE - Carregando...');

// ============================================
// DADOS DAS CAMPANHAS - ATUALIZADO FEV 2026
// Conta Google Ads: 409-094-0790 (beatriz.tradutora@gmail.com)
// ============================================
const CAMPAIGN_DATA = {
    // Campanha ativa: Pesquisa 01 (Google Ads - Rede de Pesquisa)
    // Campaign ID: 22639135145
    // Orcamento diario: $15.00 | Estrategia: Maximizar Cliques (CPC max $1.50)
    // Locais: Massachusetts, New York
    //
    // Campanhas removidas do tracking:
    //   - [VENDAS] - Traducao: PAUSADA (historico: $544.46 investidos, 532 cliques, 16.000 impressoes)
    //   - Vendas de traducoes: campanha anterior/teste, substituida pela Pesquisa 01
    totalInvestment: 0,
    totalClicks: 0,
    totalImpressions: 0,
    totalLeads: 16, // Leads acumulados (historico)
    ctr: 0,

    campaigns: [
        {
            name: 'Pesquisa 01',
            campaignId: '22639135145',
            platform: 'Google Ads',
            type: 'Rede de Pesquisa',
            dailyBudget: 15.00,
            bidStrategy: 'Maximizar Cliques (CPC max $1.50)',
            locations: 'Massachusetts, New York',
            investment: 0,
            clicks: 0,
            impressions: 0,
            ctr: 0,
            conversions: 0,
            status: 'ACTIVE'
        }
    ],

    // Distribuicao de leads por origem (historico acumulado)
    leadsByOrigin: {
        'Google Ads': 11,
        'Organico': 3,
        'WhatsApp': 2
    },

    // Investimento por plataforma (apenas campanhas ativas)
    investmentByPlatform: {
        'Google Ads': 0
    },

    // Conversoes diarias (aguardando dados da nova campanha Pesquisa 01)
    dailyConversions: [
        { date: '27/01', leads: 0, clicks: 0 },
        { date: '28/01', leads: 0, clicks: 0 },
        { date: '29/01', leads: 0, clicks: 0 },
        { date: '30/01', leads: 0, clicks: 0 },
        { date: '31/01', leads: 0, clicks: 0 },
        { date: '01/02', leads: 0, clicks: 0 },
        { date: '02/02', leads: 0, clicks: 0 }
    ]
};

// Estado Global
let charts = {};

// ============================================
// INICIALIZACAO
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Ready - Iniciando dashboard...');

    // Verificar Chart.js
    if (typeof Chart === 'undefined') {
        console.error('Chart.js nao encontrado! Tentando carregar...');
        loadChartJS().then(init).catch(err => {
            console.error('Falha ao carregar Chart.js:', err);
            alert('ERRO: Nao foi possivel carregar os graficos. Verifique sua conexao com a internet.');
        });
    } else {
        console.log('Chart.js disponivel:', Chart.version);
        init();
    }
});

// ============================================
// CARREGAR CHART.JS
// ============================================
function loadChartJS() {
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js';
        script.onload = () => {
            console.log('Chart.js carregado com sucesso!');
            resolve();
        };
        script.onerror = reject;
        document.head.appendChild(script);
    });
}

// ============================================
// INICIALIZAR DASHBOARD
// ============================================
function init() {
    console.log('Inicializando dashboard com dados reais...');

    // Atualizar cards
    updateCards();

    // Criar graficos
    createCharts();

    // Atualizar tabela
    updateTable();

    // Event listeners
    setupEventListeners();

    // Timestamp
    updateTimestamp();

    console.log('Dashboard carregado com sucesso!');

    // Mensagem de aviso
    showWarning('Dashboard atualizado - Campanha ativa: Pesquisa 01 (Google Ads)');
}

// ============================================
// ATUALIZAR CARDS
// ============================================
function updateCards() {
    console.log('Atualizando cards...');

    const { totalInvestment, totalClicks, totalImpressions, totalLeads, ctr } = CAMPAIGN_DATA;

    // Total Investment
    setCard('totalInvestment', `$${totalInvestment.toFixed(2)}`);

    // Total Leads
    setCard('totalLeads', totalLeads);

    // CTR
    setCard('ctr', `${ctr.toFixed(2)}%`);

    // CPL
    const cpl = totalLeads > 0 ? totalInvestment / totalLeads : 0;
    setCard('cpl', `$${cpl.toFixed(2)}`);

    console.log('Cards atualizados:', { totalInvestment, totalLeads, ctr, cpl });
}

function setCard(id, value) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = value;
        el.classList.add('updated');
        setTimeout(() => el.classList.remove('updated'), 500);
    } else {
        console.warn(`Card nao encontrado: ${id}`);
    }
}

// ============================================
// CRIAR TODOS OS GRAFICOS
// ============================================
function createCharts() {
    console.log('Criando graficos...');

    try {
        createLeadsByOriginChart();
        createInvestmentChart();
        createDailyConversionsChart();
        console.log('Todos os graficos criados com sucesso!');
    } catch (error) {
        console.error('Erro ao criar graficos:', error);
        alert('Erro ao criar graficos: ' + error.message);
    }
}

// ============================================
// GRAFICO 1: LEADS POR ORIGEM
// ============================================
function createLeadsByOriginChart() {
    const canvas = document.getElementById('leadsByOriginChart');
    if (!canvas) {
        console.error('Canvas leadsByOriginChart nao encontrado no HTML!');
        return;
    }

    console.log('Criando: Leads por Origem');

    const data = CAMPAIGN_DATA.leadsByOrigin;
    const labels = Object.keys(data);
    const values = Object.values(data);

    if (charts.leadsByOrigin) {
        charts.leadsByOrigin.destroy();
    }

    charts.leadsByOrigin = new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: [
                    '#4285F4',  // Google Blue
                    '#25D366',  // WhatsApp Green
                    '#FF6B6B'   // Red
                ],
                borderWidth: 3,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 15,
                        font: { size: 14, weight: '600' },
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    padding: 12,
                    titleFont: { size: 14, weight: 'bold' },
                    bodyFont: { size: 13 },
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `${label}: ${value} leads (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });

    console.log('Grafico Leads por Origem criado');
}

// ============================================
// GRAFICO 2: INVESTIMENTO POR PLATAFORMA
// ============================================
function createInvestmentChart() {
    const canvas = document.getElementById('investmentChart');
    if (!canvas) {
        console.error('Canvas investmentChart nao encontrado no HTML!');
        return;
    }

    console.log('Criando: Investimento');

    const data = CAMPAIGN_DATA.investmentByPlatform;
    const labels = Object.keys(data);
    const values = Object.values(data);

    if (charts.investment) {
        charts.investment.destroy();
    }

    charts.investment = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Investimento (USD)',
                data: values,
                backgroundColor: ['#4285F4'],
                borderRadius: 12,
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    padding: 12,
                    titleFont: { size: 14, weight: 'bold' },
                    bodyFont: { size: 13 },
                    callbacks: {
                        label: (context) => `Investido: $${context.parsed.y.toFixed(2)}`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: (value) => `$${value}`,
                        font: { size: 12 }
                    },
                    grid: {
                        color: 'rgba(0,0,0,0.05)',
                        drawBorder: false
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        font: { size: 13, weight: '600' }
                    }
                }
            }
        }
    });

    console.log('Grafico Investimento criado');
}

// ============================================
// GRAFICO 3: CONVERSOES DIARIAS
// ============================================
function createDailyConversionsChart() {
    const canvas = document.getElementById('dailyConversionsChart');
    if (!canvas) {
        console.error('Canvas dailyConversionsChart nao encontrado no HTML!');
        return;
    }

    console.log('Criando: Conversoes Diarias');

    const data = CAMPAIGN_DATA.dailyConversions;
    const labels = data.map(d => d.date);
    const values = data.map(d => d.leads);

    if (charts.daily) {
        charts.daily.destroy();
    }

    charts.daily = new Chart(canvas, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Leads por dia',
                data: values,
                borderColor: '#4CAF50',
                backgroundColor: 'rgba(76, 175, 80, 0.1)',
                borderWidth: 3,
                tension: 0.4,
                fill: true,
                pointRadius: 6,
                pointHoverRadius: 8,
                pointBackgroundColor: '#4CAF50',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 2,
                pointHoverBackgroundColor: '#4CAF50',
                pointHoverBorderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    padding: 12,
                    titleFont: { size: 14, weight: 'bold' },
                    bodyFont: { size: 13 },
                    callbacks: {
                        label: (context) => `${context.parsed.y} leads`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1,
                        callback: (value) => Math.round(value),
                        font: { size: 12 }
                    },
                    grid: {
                        color: 'rgba(0,0,0,0.05)',
                        drawBorder: false
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        font: { size: 12 }
                    }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });

    console.log('Grafico Conversoes Diarias criado');
}

// ============================================
// ATUALIZAR TABELA DE KPIs
// ============================================
function updateTable() {
    const tbody = document.getElementById('kpisTableBody');
    if (!tbody) {
        console.warn('Tabela KPIs nao encontrada');
        return;
    }

    console.log('Atualizando tabela de KPIs...');

    tbody.innerHTML = '';

    CAMPAIGN_DATA.campaigns.forEach(campaign => {
        const avgCpc = campaign.clicks > 0 ? campaign.investment / campaign.clicks : 0;

        const row = tbody.insertRow();
        row.innerHTML = `
            <td><strong>${campaign.name}</strong><br><small style="color:#888">ID: ${campaign.campaignId || 'N/A'} | ${campaign.locations || ''}</small></td>
            <td>$${campaign.investment.toFixed(2)}</td>
            <td>${campaign.impressions.toLocaleString('pt-BR')}</td>
            <td>${campaign.clicks}</td>
            <td>${campaign.ctr.toFixed(2)}%</td>
            <td>$${avgCpc.toFixed(2)}</td>
            <td>${campaign.conversions}</td>
            <td><span style="font-size:0.9em;font-weight:bold;color:${campaign.status === 'ACTIVE' ? '#4CAF50' : '#f44336'}">${campaign.status}</span></td>
        `;
    });

    console.log('Tabela atualizada');
}

// ============================================
// EVENT LISTENERS
// ============================================
function setupEventListeners() {
    const refreshBtn = document.getElementById('refreshData');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            console.log('Refresh manual');
            showInfo('Dashboard atualizado - Campanha ativa: Pesquisa 01');
            updateTimestamp();
        });
    }

    const exportBtn = document.getElementById('exportExcel');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportToExcel);
    }
}

// ============================================
// EXPORTAR PARA EXCEL
// ============================================
function exportToExcel() {
    if (typeof XLSX === 'undefined') {
        alert('Biblioteca de exportacao nao esta carregada. Recarregue a pagina.');
        return;
    }

    console.log('Exportando para Excel...');

    try {
        const wb = XLSX.utils.book_new();

        // Sheet 1: Resumo
        const resumo = [
            ['DASHBOARD MIA - RELATORIO DE CAMPANHAS'],
            ['Periodo: Fevereiro 2026'],
            ['Conta Google Ads: 409-094-0790'],
            [''],
            ['RESUMO GERAL'],
            ['Investimento Total', `$${CAMPAIGN_DATA.totalInvestment}`],
            ['Total de Cliques', CAMPAIGN_DATA.totalClicks],
            ['Total de Impressoes', CAMPAIGN_DATA.totalImpressions],
            ['CTR Medio', `${CAMPAIGN_DATA.ctr}%`],
            ['Total de Leads', CAMPAIGN_DATA.totalLeads],
            [''],
            ['CAMPANHAS ATIVAS'],
            ['Nome', 'Campaign ID', 'Plataforma', 'Tipo', 'Orcamento Diario', 'Investimento', 'Cliques', 'Impressoes', 'CTR', 'Locais', 'Status'],
        ];

        CAMPAIGN_DATA.campaigns.forEach(c => {
            resumo.push([
                c.name,
                c.campaignId || 'N/A',
                c.platform || 'Google Ads',
                c.type || 'Pesquisa',
                c.dailyBudget ? `$${c.dailyBudget}` : 'N/A',
                `$${c.investment}`,
                c.clicks,
                c.impressions,
                `${c.ctr}%`,
                c.locations || 'N/A',
                c.status
            ]);
        });

        const ws1 = XLSX.utils.aoa_to_sheet(resumo);
        XLSX.utils.book_append_sheet(wb, ws1, 'Resumo');

        // Sheet 2: Leads por Origem
        const leadsData = [
            ['LEADS POR ORIGEM'],
            ['Origem', 'Quantidade'],
        ];
        Object.entries(CAMPAIGN_DATA.leadsByOrigin).forEach(([origem, qtd]) => {
            leadsData.push([origem, qtd]);
        });

        const ws2 = XLSX.utils.aoa_to_sheet(leadsData);
        XLSX.utils.book_append_sheet(wb, ws2, 'Leads por Origem');

        // Sheet 3: Conversoes Diarias
        const dailyData = [
            ['CONVERSOES DIARIAS'],
            ['Data', 'Leads', 'Cliques'],
        ];
        CAMPAIGN_DATA.dailyConversions.forEach(d => {
            dailyData.push([d.date, d.leads, d.clicks]);
        });

        const ws3 = XLSX.utils.aoa_to_sheet(dailyData);
        XLSX.utils.book_append_sheet(wb, ws3, 'Diario');

        // Salvar
        const filename = `MIA_Dashboard_${new Date().toISOString().split('T')[0]}.xlsx`;
        XLSX.writeFile(wb, filename);

        console.log('Excel exportado:', filename);
        showSuccess('Excel exportado com sucesso!');

    } catch (error) {
        console.error('Erro ao exportar:', error);
        alert('Erro ao exportar: ' + error.message);
    }
}

// ============================================
// UI HELPERS
// ============================================
function updateTimestamp() {
    const el = document.getElementById('lastUpdate');
    if (el) {
        const now = new Date();
        el.textContent = `Ultima atualizacao: ${now.toLocaleTimeString('pt-BR')}`;
    }
}

function showInfo(msg) {
    showAlert(msg, 'info', 'INFO');
}

function showSuccess(msg) {
    showAlert(msg, 'success', 'OK');
}

function showWarning(msg) {
    showAlert(msg, 'warning', '!');
}

function showAlert(msg, type, icon) {
    const alertEl = document.createElement('div');
    alertEl.className = `alert alert-${type}`;
    alertEl.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        z-index: 9999;
        max-width: 400px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        animation: slideIn 0.3s ease-out;
    `;
    alertEl.innerHTML = `
        <strong>${icon}</strong> ${msg}
        <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
    `;

    document.body.appendChild(alertEl);
    setTimeout(() => alertEl.remove(), 5000);
}

// ============================================
// GLOBAL API
// ============================================
window.MIADashboard = {
    version: '5.0.0-STANDALONE',
    data: CAMPAIGN_DATA,
    charts: charts,
    refresh: () => {
        updateCards();
        updateTimestamp();
        showInfo('Dashboard atualizado');
    },
    export: exportToExcel
};

console.log('DASHBOARD STANDALONE PRONTO!');
console.log('Dados disponiveis em: window.MIADashboard');
