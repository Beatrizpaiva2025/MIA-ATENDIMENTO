// ============================================
// LEADS INTEGRATION V2 - DASHBOARD COMPLETO
// Arquivo: leads-integration-v2.js
// ============================================

// Configuração da API
const API_CONFIG = {
    baseURL: 'https://mia-ads-api.onrender.com',
    refreshInterval: 300000, // 5 minutos
    timeout: 15000
};

// Estado Global
let dashboardState = {
    lastUpdate: null,
    isLoading: false,
    chartInstances: {},
    rawData: null
};

// ============================================
// INICIALIZAÇÃO
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Iniciando Dashboard MIA Leads v2...');
    
    // Configurar eventos
    setupEventListeners();
    
    // Carregar dados iniciais
    loadDashboardData();
    
    // Auto-refresh a cada 5 minutos
    setInterval(loadDashboardData, API_CONFIG.refreshInterval);
});

// ============================================
// EVENT LISTENERS
// ============================================
function setupEventListeners() {
    // Botão Refresh
    const refreshBtn = document.getElementById('refreshData');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            loadDashboardData(true);
        });
    }
    
    // Botão Export Excel
    const exportBtn = document.getElementById('exportExcel');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportToExcel);
    }
}

// ============================================
// CARREGAR DADOS DA API
// ============================================
async function loadDashboardData(showLoading = false) {
    if (dashboardState.isLoading) return;
    
    dashboardState.isLoading = true;
    
    if (showLoading) {
        showLoadingState();
    }
    
    try {
        console.log('📡 Buscando dados da API...');
        
        // Buscar dados de múltiplos endpoints
        const [kpisData, leadsData] = await Promise.all([
            fetchWithTimeout(`${API_CONFIG.baseURL}/api/kpis`),
            fetchWithTimeout(`${API_CONFIG.baseURL}/api/leads/summary`)
        ]);
        
        console.log('✅ Dados recebidos:', { kpisData, leadsData });
        
        // Armazenar dados brutos
        dashboardState.rawData = { kpisData, leadsData };
        dashboardState.lastUpdate = new Date();
        
        // Processar e exibir dados
        updateDashboard(kpisData, leadsData);
        
        // Atualizar timestamp
        updateLastRefreshTime();
        
    } catch (error) {
        console.error('❌ Erro ao carregar dados:', error);
        showErrorState(error.message);
    } finally {
        dashboardState.isLoading = false;
        hideLoadingState();
    }
}

// ============================================
// FETCH COM TIMEOUT
// ============================================
async function fetchWithTimeout(url, timeout = API_CONFIG.timeout) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
        const response = await fetch(url, {
            signal: controller.signal,
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return await response.json();
    } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
            throw new Error('Timeout: A API não respondeu em tempo hábil');
        }
        throw error;
    }
}

// ============================================
// ATUALIZAR DASHBOARD
// ============================================
function updateDashboard(kpisData, leadsData) {
    console.log('🔄 Atualizando dashboard...');
    
    // Extrair métricas
    const metrics = extractMetrics(kpisData, leadsData);
    
    // Atualizar cards
    updateStatCards(metrics);
    
    // Atualizar gráficos
    updateCharts(leadsData);
    
    // Atualizar tabela KPIs
    updateKPIsTable(kpisData);
    
    console.log('✅ Dashboard atualizado com sucesso!');
}

// ============================================
// EXTRAIR MÉTRICAS
// ============================================
function extractMetrics(kpisData, leadsData) {
    // Converter valores removendo símbolos
    const parseValue = (value) => {
        if (!value) return 0;
        const str = String(value).replace(/[$R\s,]/g, '').replace('%', '');
        return parseFloat(str) || 0;
    };
    
    return {
        totalInvestment: parseValue(kpisData.google_ads?.total_cost || 0) + 
                        parseValue(kpisData.facebook_ads?.total_cost || 0),
        totalLeads: parseValue(leadsData.total_leads || 0),
        totalClicks: parseValue(kpisData.google_ads?.total_clicks || 0) + 
                    parseValue(kpisData.facebook_ads?.total_clicks || 0),
        totalImpressions: parseValue(kpisData.google_ads?.total_impressions || 0) + 
                         parseValue(kpisData.facebook_ads?.total_impressions || 0),
        ctr: parseValue(kpisData.average_ctr || 0),
        cpl: 0 // Será calculado
    };
}

// ============================================
// ATUALIZAR CARDS ESTATÍSTICOS
// ============================================
function updateStatCards(metrics) {
    // Total Investment
    updateCard('totalInvestment', metrics.totalInvestment, 'currency');
    
    // Total Leads
    updateCard('totalLeads', metrics.totalLeads, 'number');
    
    // CTR
    updateCard('ctr', metrics.ctr, 'percentage');
    
    // CPL (Cost Per Lead)
    const cpl = metrics.totalLeads > 0 ? 
                metrics.totalInvestment / metrics.totalLeads : 0;
    updateCard('cpl', cpl, 'currency');
}

function updateCard(cardId, value, format) {
    const element = document.getElementById(cardId);
    if (!element) return;
    
    let formattedValue;
    
    switch(format) {
        case 'currency':
            formattedValue = `R$ ${value.toFixed(2).replace('.', ',')}`;
            break;
        case 'percentage':
            formattedValue = `${value.toFixed(2)}%`;
            break;
        case 'number':
            formattedValue = value.toLocaleString('pt-BR');
            break;
        default:
            formattedValue = value;
    }
    
    element.textContent = formattedValue;
    
    // Animação de atualização
    element.classList.add('updated');
    setTimeout(() => element.classList.remove('updated'), 500);
}

// ============================================
// ATUALIZAR GRÁFICOS
// ============================================
function updateCharts(leadsData) {
    // Gráfico de Leads por Origem
    updateLeadsByOriginChart(leadsData);
    
    // Gráfico de Investimento
    updateInvestmentChart(leadsData);
    
    // Gráfico de Conversões Diárias
    updateDailyConversionsChart(leadsData);
}

function updateLeadsByOriginChart(data) {
    const ctx = document.getElementById('leadsByOriginChart');
    if (!ctx) return;
    
    // Destruir gráfico anterior
    if (dashboardState.chartInstances.leadsByOrigin) {
        dashboardState.chartInstances.leadsByOrigin.destroy();
    }
    
    // Dados
    const origins = data.by_origin || {};
    const labels = Object.keys(origins);
    const values = Object.values(origins);
    
    // Criar novo gráfico
    dashboardState.chartInstances.leadsByOrigin = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: [
                    '#4285F4', // Google Blue
                    '#1877F2', // Facebook Blue
                    '#25D366', // WhatsApp Green
                    '#FF6B6B', // Red
                    '#FFD93D'  // Yellow
                ],
                borderWidth: 2,
                borderColor: '#fff'
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
                        font: { size: 12 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

function updateInvestmentChart(data) {
    const ctx = document.getElementById('investmentChart');
    if (!ctx) return;
    
    if (dashboardState.chartInstances.investment) {
        dashboardState.chartInstances.investment.destroy();
    }
    
    // Dados de investimento por plataforma
    const googleAds = parseFloat(data.google_ads_cost || 0);
    const facebookAds = parseFloat(data.facebook_ads_cost || 0);
    
    dashboardState.chartInstances.investment = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Google Ads', 'Facebook Ads'],
            datasets: [{
                label: 'Investimento (R$)',
                data: [googleAds, facebookAds],
                backgroundColor: ['#4285F4', '#1877F2'],
                borderWidth: 0,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => `R$ ${context.parsed.y.toFixed(2)}`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: (value) => `R$ ${value}`
                    }
                }
            }
        }
    });
}

function updateDailyConversionsChart(data) {
    const ctx = document.getElementById('dailyConversionsChart');
    if (!ctx) return;
    
    if (dashboardState.chartInstances.dailyConversions) {
        dashboardState.chartInstances.dailyConversions.destroy();
    }
    
    // Dados diários (últimos 7 dias)
    const dailyData = data.daily_leads || [];
    const labels = dailyData.map(d => d.date);
    const values = dailyData.map(d => d.leads);
    
    dashboardState.chartInstances.dailyConversions = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Leads',
                data: values,
                borderColor: '#4CAF50',
                backgroundColor: 'rgba(76, 175, 80, 0.1)',
                borderWidth: 3,
                tension: 0.4,
                fill: true,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                }
            }
        }
    });
}

// ============================================
// ATUALIZAR TABELA DE KPIs
// ============================================
function updateKPIsTable(kpisData) {
    const tbody = document.getElementById('kpisTableBody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    // KPIs do Google Ads
    if (kpisData.google_ads) {
        addKPIRow(tbody, 'Google Ads', kpisData.google_ads);
    }
    
    // KPIs do Facebook Ads
    if (kpisData.facebook_ads) {
        addKPIRow(tbody, 'Facebook Ads', kpisData.facebook_ads);
    }
}

function addKPIRow(tbody, platform, data) {
    const row = tbody.insertRow();
    row.innerHTML = `
        <td>${platform}</td>
        <td>R$ ${parseFloat(data.total_cost || 0).toFixed(2)}</td>
        <td>${data.total_impressions || 0}</td>
        <td>${data.total_clicks || 0}</td>
        <td>${parseFloat(data.ctr || 0).toFixed(2)}%</td>
        <td>R$ ${parseFloat(data.avg_cpc || 0).toFixed(2)}</td>
        <td>${data.conversions || 0}</td>
    `;
}

// ============================================
// EXPORTAR PARA EXCEL
// ============================================
function exportToExcel() {
    if (!dashboardState.rawData) {
        alert('Nenhum dado para exportar. Carregue os dados primeiro.');
        return;
    }
    
    console.log('📊 Exportando para Excel...');
    
    try {
        // Criar workbook
        const wb = XLSX.utils.book_new();
        
        // Dados de KPIs
        const kpisWS = createKPIsWorksheet(dashboardState.rawData.kpisData);
        XLSX.utils.book_append_sheet(wb, kpisWS, 'KPIs');
        
        // Dados de Leads
        const leadsWS = createLeadsWorksheet(dashboardState.rawData.leadsData);
        XLSX.utils.book_append_sheet(wb, leadsWS, 'Leads');
        
        // Salvar arquivo
        const filename = `MIA_Leads_${new Date().toISOString().split('T')[0]}.xlsx`;
        XLSX.writeFile(wb, filename);
        
        console.log('✅ Excel exportado:', filename);
        
        // Feedback visual
        const btn = document.getElementById('exportExcel');
        if (btn) {
            const originalText = btn.innerHTML;
            btn.innerHTML = '✅ Exportado!';
            setTimeout(() => {
                btn.innerHTML = originalText;
            }, 2000);
        }
        
    } catch (error) {
        console.error('❌ Erro ao exportar:', error);
        alert('Erro ao exportar para Excel. Verifique o console.');
    }
}

function createKPIsWorksheet(data) {
    const rows = [
        ['Plataforma', 'Investimento', 'Impressões', 'Cliques', 'CTR', 'CPC Médio', 'Conversões']
    ];
    
    if (data.google_ads) {
        rows.push([
            'Google Ads',
            data.google_ads.total_cost,
            data.google_ads.total_impressions,
            data.google_ads.total_clicks,
            data.google_ads.ctr,
            data.google_ads.avg_cpc,
            data.google_ads.conversions || 0
        ]);
    }
    
    if (data.facebook_ads) {
        rows.push([
            'Facebook Ads',
            data.facebook_ads.total_cost,
            data.facebook_ads.total_impressions,
            data.facebook_ads.total_clicks,
            data.facebook_ads.ctr,
            data.facebook_ads.avg_cpc,
            data.facebook_ads.conversions || 0
        ]);
    }
    
    return XLSX.utils.aoa_to_sheet(rows);
}

function createLeadsWorksheet(data) {
    const rows = [
        ['Métrica', 'Valor']
    ];
    
    rows.push(['Total de Leads', data.total_leads || 0]);
    rows.push(['Custo Google Ads', data.google_ads_cost || 0]);
    rows.push(['Custo Facebook Ads', data.facebook_ads_cost || 0]);
    
    // Leads por origem
    if (data.by_origin) {
        rows.push(['', '']);
        rows.push(['Leads por Origem', '']);
        Object.entries(data.by_origin).forEach(([origin, count]) => {
            rows.push([origin, count]);
        });
    }
    
    return XLSX.utils.aoa_to_sheet(rows);
}

// ============================================
// UTILITÁRIOS DE UI
// ============================================
function showLoadingState() {
    document.body.classList.add('loading');
}

function hideLoadingState() {
    document.body.classList.remove('loading');
}

function showErrorState(message) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-danger';
    alert.textContent = `Erro: ${message}`;
    
    const container = document.querySelector('.dashboard-container');
    if (container) {
        container.insertBefore(alert, container.firstChild);
        
        setTimeout(() => alert.remove(), 5000);
    }
}

function updateLastRefreshTime() {
    const element = document.getElementById('lastUpdate');
    if (!element) return;
    
    const now = new Date();
    const timeStr = now.toLocaleTimeString('pt-BR');
    element.textContent = `Última atualização: ${timeStr}`;
}

// ============================================
// EXPORT GLOBAL
// ============================================
window.MIADashboard = {
    refresh: () => loadDashboardData(true),
    export: exportToExcel,
    getState: () => dashboardState
};

console.log('✅ MIA Leads Integration v2 carregado com sucesso!');
