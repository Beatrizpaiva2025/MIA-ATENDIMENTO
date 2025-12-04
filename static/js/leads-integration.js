/**
 * MIA ADS INTEGRATION - Leads Dashboard
 * Integração com API de Facebook Ads e Google Ads
 * 
 * API Base URL: https://mia-ads-api.onrender.com
 */

// Configuração da API
const API_BASE_URL = 'https://mia-ads-api.onrender.com';
const DEFAULT_PERIOD_DAYS = 30;

// Utility: Formatar moeda
function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2
    }).format(value || 0);
}

// Utility: Formatar porcentagem
function formatPercentage(value) {
    return `${(value || 0).toFixed(2)}%`;
}

// Utility: Formatar número
function formatNumber(value) {
    return new Intl.NumberFormat('en-US').format(value || 0);
}

// Utility: Determinar classe de status
function getStatusClass(status) {
    const statusMap = {
        'good': 'status-good',
        'neutral': 'status-neutral',
        'warning': 'status-warning',
        'bad': 'status-bad'
    };
    return statusMap[status] || 'status-neutral';
}

/**
 * 1. CARREGAR RESUMO DE LEADS
 */
async function loadLeadsSummary() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/leads/summary?days=${DEFAULT_PERIOD_DAYS}`);
        const result = await response.json();
        
        if (result.success && result.data) {
            const data = result.data;
            
            // Atualizar cards principais
            document.getElementById('total-revenue').textContent = formatCurrency(data.total_spend);
            document.getElementById('total-leads').textContent = formatNumber(data.total_leads);
            document.getElementById('conversion-rate').textContent = formatPercentage(data.ctr);
            document.getElementById('average-ticket').textContent = formatCurrency(data.cpl);
            
            // Atualizar período
            const periodText = `${data.date_start} to ${data.date_end}`;
            document.querySelectorAll('.period-text').forEach(el => {
                el.textContent = periodText;
            });
        }
    } catch (error) {
        console.error('Error loading leads summary:', error);
        showError('Failed to load leads summary');
    }
}

/**
 * 2. CARREGAR LEADS POR ORIGEM
 */
async function loadLeadsByOrigin() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/leads/by-origin?days=${DEFAULT_PERIOD_DAYS}`);
        const result = await response.json();
        
        if (result.success && result.data) {
            const data = result.data;
            
            // Preparar dados para o gráfico
            const chartData = {
                labels: [],
                values: [],
                colors: ['#1877F2', '#4285F4', '#34A853']
            };
            
            if (data.facebook && data.facebook.count > 0) {
                chartData.labels.push('Facebook Ads');
                chartData.values.push(data.facebook.count);
            }
            
            if (data.google && data.google.count > 0) {
                chartData.labels.push('Google Ads');
                chartData.values.push(data.google.count);
            }
            
            // Se não houver dados, mostrar mensagem
            if (chartData.labels.length === 0) {
                chartData.labels.push('No Data');
                chartData.values.push(1);
                chartData.colors = ['#95a5a6'];
            }
            
            renderPieChart('leads-origin-chart', chartData);
            updateOriginLegend(data);
        }
    } catch (error) {
        console.error('Error loading leads by origin:', error);
        showError('Failed to load leads by origin');
    }
}

/**
 * 3. CARREGAR INVESTIMENTO DIÁRIO
 */
async function loadMarketingInvestment() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/marketing/investment?days=${DEFAULT_PERIOD_DAYS}`);
        const result = await response.json();
        
        if (result.success && result.data) {
            const data = result.data;
            
            // Verificar se os dados existem e são arrays
            if (!data.facebook || !Array.isArray(data.facebook) || 
                !data.google || !Array.isArray(data.google)) {
                console.warn('Investment data format incorrect:', data);
                return;
            }
            
            // Se não houver dados, criar array vazio
            const facebookData = data.facebook.length > 0 ? data.facebook : [{ date: 'No data', spend: 0 }];
            const googleData = data.google.length > 0 ? data.google : [{ date: 'No data', spend: 0 }];
            
            const chartData = {
                labels: facebookData.map(item => item.date || item.day || 'N/A'),
                datasets: [
                    {
                        label: 'Facebook Ads',
                        data: facebookData.map(item => item.spend || 0),
                        borderColor: '#1877F2',
                        backgroundColor: 'rgba(24, 119, 242, 0.1)',
                        tension: 0.4
                    },
                    {
                        label: 'Google Ads',
                        data: googleData.map(item => item.spend || 0),
                        borderColor: '#4285F4',
                        backgroundColor: 'rgba(66, 133, 244, 0.1)',
                        tension: 0.4
                    }
                ]
            };
            
            renderLineChart('investment-chart', chartData);
        }
    } catch (error) {
        console.error('Error loading marketing investment:', error);
        showError('Failed to load marketing investment');
    }
}

/**
 * 4. CARREGAR CONVERSÕES DIÁRIAS
 */
async function loadDailyConversions() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/analytics/conversions?days=${DEFAULT_PERIOD_DAYS}`);
        const result = await response.json();
        
        if (result.success && result.data) {
            const data = result.data;
            
            // Verificar se os dados existem e são arrays
            if (!data.facebook || !Array.isArray(data.facebook) || 
                !data.google || !Array.isArray(data.google)) {
                console.warn('Conversions data format incorrect:', data);
                return;
            }
            
            // Se não houver dados, criar array vazio
            const facebookData = data.facebook.length > 0 ? data.facebook : [{ date: 'No data', conversions: 0 }];
            const googleData = data.google.length > 0 ? data.google : [{ date: 'No data', conversions: 0 }];
            
            const chartData = {
                labels: facebookData.map(item => item.date || item.day || 'N/A'),
                datasets: [
                    {
                        label: 'Facebook Ads',
                        data: facebookData.map(item => item.conversions || 0),
                        backgroundColor: '#1877F2'
                    },
                    {
                        label: 'Google Ads',
                        data: googleData.map(item => item.conversions || 0),
                        backgroundColor: '#4285F4'
                    }
                ]
            };
            
            renderBarChart('conversions-chart', chartData);
        }
    } catch (error) {
        console.error('Error loading daily conversions:', error);
        showError('Failed to load daily conversions');
    }
}

/**
 * 5. CARREGAR KPIs
 */
async function loadKPIs() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/kpis?days=${DEFAULT_PERIOD_DAYS}`);
        const result = await response.json();
        
        if (result.success && result.data) {
            const kpis = result.data;
            const kpiTableBody = document.getElementById('kpi-table-body');
            
            if (kpiTableBody) {
                kpiTableBody.innerHTML = '';
                
                kpis.forEach(kpi => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td><strong>${kpi.name}</strong></td>
                        <td class="text-center"><span class="kpi-value">${kpi.value}</span></td>
                        <td class="text-center">
                            <span class="status-badge ${getStatusClass(kpi.status)}">
                                ${kpi.status.toUpperCase()}
                            </span>
                        </td>
                        <td>${kpi.description}</td>
                    `;
                    kpiTableBody.appendChild(row);
                });
            }
        }
    } catch (error) {
        console.error('Error loading KPIs:', error);
        showError('Failed to load KPIs');
    }
}

/**
 * RENDERIZAR GRÁFICO DE PIZZA
 */
function renderPieChart(canvasId, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    if (window.chartsInstances && window.chartsInstances[canvasId]) {
        window.chartsInstances[canvasId].destroy();
    }
    
    const ctx = canvas.getContext('2d');
    const chart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: data.labels,
            datasets: [{
                data: data.values,
                backgroundColor: data.colors,
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
                            const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
    
    if (!window.chartsInstances) window.chartsInstances = {};
    window.chartsInstances[canvasId] = chart;
}

/**
 * RENDERIZAR GRÁFICO DE LINHA
 */
function renderLineChart(canvasId, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    if (window.chartsInstances && window.chartsInstances[canvasId]) {
        window.chartsInstances[canvasId].destroy();
    }
    
    const ctx = canvas.getContext('2d');
    const chart = new Chart(ctx, {
        type: 'line',
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${formatCurrency(context.parsed.y)}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return formatCurrency(value);
                        }
                    }
                }
            }
        }
    });
    
    if (!window.chartsInstances) window.chartsInstances = {};
    window.chartsInstances[canvasId] = chart;
}

/**
 * RENDERIZAR GRÁFICO DE BARRAS
 */
function renderBarChart(canvasId, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    if (window.chartsInstances && window.chartsInstances[canvasId]) {
        window.chartsInstances[canvasId].destroy();
    }
    
    const ctx = canvas.getContext('2d');
    const chart = new Chart(ctx, {
        type: 'bar',
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { stepSize: 1 }
                }
            }
        }
    });
    
    if (!window.chartsInstances) window.chartsInstances = {};
    window.chartsInstances[canvasId] = chart;
}

/**
 * ATUALIZAR LEGENDA DE ORIGEM
 */
function updateOriginLegend(data) {
    const legendContainer = document.getElementById('origin-legend');
    if (!legendContainer) return;
    
    legendContainer.innerHTML = `
        <div class="origin-item">
            <span class="origin-color" style="background: #1877F2;"></span>
            <span class="origin-label">Facebook Ads</span>
            <span class="origin-value">${data.facebook ? formatNumber(data.facebook.count) : 0} (${data.facebook ? formatPercentage(data.facebook.percentage) : '0%'})</span>
        </div>
        <div class="origin-item">
            <span class="origin-color" style="background: #4285F4;"></span>
            <span class="origin-label">Google Ads</span>
            <span class="origin-value">${data.google ? formatNumber(data.google.count) : 0} (${data.google ? formatPercentage(data.google.percentage) : '0%'})</span>
        </div>
    `;
}

/**
 * MOSTRAR ERRO
 */
function showError(message) {
    console.error('MIA Ads Integration Error:', message);
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'alert alert-error';
    errorDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #f44336; color: white; padding: 15px; border-radius: 5px; z-index: 9999;';
    errorDiv.textContent = message;
    document.body.appendChild(errorDiv);
    
    setTimeout(() => {
        errorDiv.remove();
    }, 5000);
}

/**
 * ATUALIZAR TODOS OS DADOS
 */
async function refreshAllData() {
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.textContent = 'Atualizando...';
    }
    
    try {
        await Promise.all([
            loadLeadsSummary(),
            loadLeadsByOrigin(),
            loadMarketingInvestment(),
            loadDailyConversions(),
            loadKPIs()
        ]);
    } catch (error) {
        console.error('Error refreshing data:', error);
        showError('Failed to refresh data');
    } finally {
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.textContent = '🔄 Refresh';
        }
    }
}

/**
 * INICIALIZAR
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('MIA Ads Integration - Initializing...');
    refreshAllData();
    
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', refreshAllData);
    }
    
    setInterval(refreshAllData, 5 * 60 * 1000);
    console.log('MIA Ads Integration - Ready!');
});

window.MIAAdsIntegration = {
    refreshAllData,
    loadLeadsSummary,
    loadLeadsByOrigin,
    loadMarketingInvestment,
    loadDailyConversions,
    loadKPIs
};
