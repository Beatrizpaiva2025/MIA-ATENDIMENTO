<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard MIA - Marketing Intelligence Analytics</title>

    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

    <!-- SheetJS para exportar Excel -->
    <script src="https://cdn.sheetjs.com/xlsx-0.20.0/package/dist/xlsx.full.min.js"></script>

    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">

    <style>
        :root {
            --primary-color: #4285F4;
            --secondary-color: #1877F2;
            --success-color: #4CAF50;
            --warning-color: #FF9800;
            --danger-color: #FF6B6B;
            --dark-color: #2c3e50;
            --light-bg: #f8f9fa;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .dashboard-container {
            max-width: 1400px;
            margin: 0 auto;
        }

        .dashboard-header {
            background: white;
            border-radius: 16px;
            padding: 24px 32px;
            margin-bottom: 24px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }

        .dashboard-title {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .dashboard-title h1 {
            font-size: 28px;
            font-weight: 700;
            color: var(--dark-color);
            margin: 0;
        }

        .dashboard-title .badge {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }

        .header-actions {
            display: flex;
            gap: 12px;
            align-items: center;
        }

        .btn-refresh, .btn-export {
            padding: 10px 20px;
            border-radius: 10px;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .btn-refresh {
            background: var(--primary-color);
            color: white;
        }

        .btn-refresh:hover {
            background: #3367d6;
            transform: translateY(-2px);
        }

        .btn-export {
            background: var(--success-color);
            color: white;
        }

        .btn-export:hover {
            background: #43a047;
            transform: translateY(-2px);
        }

        #lastUpdate {
            color: #666;
            font-size: 13px;
        }

        .cards-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }

        .metric-card {
            background: white;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }

        .metric-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.15);
        }

        .metric-card .icon {
            width: 50px;
            height: 50px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            margin-bottom: 16px;
        }

        .metric-card.investment .icon { background: rgba(66, 133, 244, 0.1); }
        .metric-card.leads .icon { background: rgba(76, 175, 80, 0.1); }
        .metric-card.ctr .icon { background: rgba(255, 152, 0, 0.1); }
        .metric-card.cpl .icon { background: rgba(156, 39, 176, 0.1); }

        .metric-card .label {
            font-size: 13px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }

        .metric-card .value {
            font-size: 32px;
            font-weight: 700;
            color: var(--dark-color);
        }

        .metric-card .value.updated {
            animation: pulse 0.5s ease;
        }

        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }

        .charts-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 24px;
            margin-bottom: 24px;
        }

        .chart-card {
            background: white;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }

        .chart-card h3 {
            font-size: 18px;
            font-weight: 600;
            color: var(--dark-color);
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid #f0f0f0;
        }

        .chart-container {
            position: relative;
            height: 300px;
            width: 100%;
        }

        .chart-full-width {
            grid-column: 1 / -1;
        }

        .table-card {
            background: white;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            margin-bottom: 24px;
            overflow-x: auto;
        }

        .table-card h3 {
            font-size: 18px;
            font-weight: 600;
            color: var(--dark-color);
            margin-bottom: 20px;
        }

        .kpis-table {
            width: 100%;
            border-collapse: collapse;
        }

        .kpis-table th {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 14px 16px;
            text-align: left;
            font-weight: 600;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .kpis-table th:first-child { border-radius: 10px 0 0 0; }
        .kpis-table th:last-child { border-radius: 0 10px 0 0; }

        .kpis-table td {
            padding: 14px 16px;
            border-bottom: 1px solid #f0f0f0;
            font-size: 14px;
            color: #333;
        }

        .kpis-table tr:hover { background: #f8f9fa; }
        .kpis-table tr:last-child td { border-bottom: none; }

        .alert { border-radius: 12px; border: none; font-weight: 500; }

        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }

        @media (max-width: 768px) {
            .dashboard-header { flex-direction: column; text-align: center; }
            .charts-row { grid-template-columns: 1fr; }
            .metric-card .value { font-size: 26px; }
        }

        .results-summary {
            background: white;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            margin-bottom: 24px;
        }

        .results-summary h3 {
            font-size: 20px;
            font-weight: 700;
            color: var(--dark-color);
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
        }

        .summary-item {
            padding: 16px;
            background: #f8f9fa;
            border-radius: 12px;
            text-align: center;
        }

        .summary-item .label {
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            margin-bottom: 6px;
        }

        .summary-item .value {
            font-size: 24px;
            font-weight: 700;
            color: var(--primary-color);
        }
    </style>
</head>
<body>
    <div class="dashboard-container">
        <header class="dashboard-header">
            <div class="dashboard-title">
                <h1>Dashboard MIA</h1>
                <span class="badge">Marketing Intelligence</span>
            </div>
            <div class="header-actions">
                <span id="lastUpdate">Carregando...</span>
                <button class="btn-refresh" id="refreshData"><span>Atualizar</span></button>
                <button class="btn-export" id="exportExcel"><span>Exportar Excel</span></button>
            </div>
        </header>

        <div class="cards-row">
            <div class="metric-card investment">
                <div class="icon">$</div>
                <div class="label">Investimento Total</div>
                <div class="value" id="totalInvestment">$0.00</div>
            </div>
            <div class="metric-card leads">
                <div class="icon">@</div>
                <div class="label">Total de Leads</div>
                <div class="value" id="totalLeads">0</div>
            </div>
            <div class="metric-card ctr">
                <div class="icon">%</div>
                <div class="label">CTR Medio</div>
                <div class="value" id="ctr">0%</div>
            </div>
            <div class="metric-card cpl">
                <div class="icon">$</div>
                <div class="label">Custo por Lead</div>
                <div class="value" id="cpl">$0.00</div>
            </div>
        </div>

        <div class="charts-row">
            <div class="chart-card">
                <h3>Leads por Origem</h3>
                <div class="chart-container">
                    <canvas id="leadsByOriginChart"></canvas>
                </div>
            </div>
            <div class="chart-card">
                <h3>Investimento por Plataforma</h3>
                <div class="chart-container">
                    <canvas id="investmentChart"></canvas>
                </div>
            </div>
        </div>

        <div class="charts-row">
            <div class="chart-card chart-full-width">
                <h3>Conversoes Diarias (Ultimos 7 dias)</h3>
                <div class="chart-container">
                    <canvas id="dailyConversionsChart"></canvas>
                </div>
            </div>
        </div>

        <div class="results-summary">
            <h3>Resumo dos Resultados da Pesquisa de Marketing</h3>
            <div class="summary-grid">
                <div class="summary-item">
                    <div class="label">Total de Impressoes</div>
                    <div class="value" id="totalImpressions">0</div>
                </div>
                <div class="summary-item">
                    <div class="label">Total de Cliques</div>
                    <div class="value" id="totalClicks">0</div>
                </div>
                <div class="summary-item">
                    <div class="label">Campanhas Ativas</div>
                    <div class="value" id="activeCampaigns">0</div>
                </div>
                <div class="summary-item">
                    <div class="label">Taxa de Conversao</div>
                    <div class="value" id="conversionRate">0%</div>
                </div>
            </div>
        </div>

        <div class="table-card">
            <h3>Detalhes das Campanhas</h3>
            <table class="kpis-table">
                <thead>
                    <tr>
                        <th>Campanha</th>
                        <th>Investimento</th>
                        <th>Impressoes</th>
                        <th>Cliques</th>
                        <th>CTR</th>
                        <th>CPC Medio</th>
                        <th>Conversoes</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="kpisTableBody"></tbody>
            </table>
        </div>
    </div>

    <script>
    const CAMPAIGN_DATA = {
        totalInvestment: 560.54,
        totalClicks: 545,
        totalImpressions: 16700,
        totalLeads: 16,
        ctr: 3.26,
        campaigns: [
            { name: '[VENDAS] - Traducao', investment: 544.46, clicks: 532, impressions: 16000, ctr: 3.20, conversions: 11, status: 'PAUSAR' },
            { name: 'Vendas de traducoes', investment: 16.08, clicks: 13, impressions: 700, ctr: 13.13, conversions: 5, status: 'ESCALAR' }
        ],
        leadsByOrigin: { 'Google Ads': 11, 'Facebook Ads': 1, 'Organico': 3, 'WhatsApp': 2 },
        investmentByPlatform: { 'Google Ads': 544.46, 'Facebook Ads': 16.08 },
        dailyConversions: [
            { date: '28/11', leads: 1, clicks: 75 },
            { date: '29/11', leads: 2, clicks: 78 },
            { date: '30/11', leads: 1, clicks: 80 },
            { date: '01/12', leads: 3, clicks: 82 },
            { date: '02/12', leads: 2, clicks: 76 },
            { date: '03/12', leads: 0, clicks: 74 },
            { date: '04/12', leads: 1, clicks: 80 }
        ]
    };

    let charts = {};

    document.addEventListener('DOMContentLoaded', function() {
        if (typeof Chart === 'undefined') {
            loadChartJS().then(init).catch(err => alert('ERRO: Nao foi possivel carregar os graficos.'));
        } else {
            init();
        }
    });

    function loadChartJS() {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    function init() {
        updateCards();
        updateSummary();
        createCharts();
        updateTable();
        setupEventListeners();
        updateTimestamp();
    }

    function updateCards() {
        const { totalInvestment, totalLeads, ctr } = CAMPAIGN_DATA;
        setCard('totalInvestment', `$${totalInvestment.toFixed(2)}`);
        setCard('totalLeads', totalLeads);
        setCard('ctr', `${ctr.toFixed(2)}%`);
        const cpl = totalLeads > 0 ? totalInvestment / totalLeads : 0;
        setCard('cpl', `$${cpl.toFixed(2)}`);
    }

    function setCard(id, value) {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = value;
            el.classList.add('updated');
            setTimeout(() => el.classList.remove('updated'), 500);
        }
    }

    function updateSummary() {
        const { totalImpressions, totalClicks, totalLeads, campaigns } = CAMPAIGN_DATA;
        document.getElementById('totalImpressions').textContent = totalImpressions.toLocaleString('pt-BR');
        document.getElementById('totalClicks').textContent = totalClicks.toLocaleString('pt-BR');
        document.getElementById('activeCampaigns').textContent = campaigns.length;
        const conversionRate = totalClicks > 0 ? ((totalLeads / totalClicks) * 100).toFixed(2) : 0;
        document.getElementById('conversionRate').textContent = `${conversionRate}%`;
    }

    function createCharts() {
        createLeadsByOriginChart();
        createInvestmentChart();
        createDailyConversionsChart();
    }

    function createLeadsByOriginChart() {
        const canvas = document.getElementById('leadsByOriginChart');
        if (!canvas) return;
        const data = CAMPAIGN_DATA.leadsByOrigin;
        if (charts.leadsByOrigin) charts.leadsByOrigin.destroy();
        charts.leadsByOrigin = new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: Object.keys(data),
                datasets: [{
                    data: Object.values(data),
                    backgroundColor: ['#4285F4', '#1877F2', '#25D366', '#FF6B6B'],
                    borderWidth: 3,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom', labels: { padding: 15, font: { size: 14, weight: '600' }, usePointStyle: true } },
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        padding: 12,
                        callbacks: {
                            label: function(context) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((context.parsed / total) * 100).toFixed(1);
                                return `${context.label}: ${context.parsed} leads (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    function createInvestmentChart() {
        const canvas = document.getElementById('investmentChart');
        if (!canvas) return;
        const data = CAMPAIGN_DATA.investmentByPlatform;
        if (charts.investment) charts.investment.destroy();
        charts.investment = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: Object.keys(data),
                datasets: [{
                    label: 'Investimento (USD)',
                    data: Object.values(data),
                    backgroundColor: ['#4285F4', '#1877F2'],
                    borderRadius: 12
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (ctx) => `Investido: $${ctx.parsed.y.toFixed(2)}` } }
                },
                scales: {
                    y: { beginAtZero: true, ticks: { callback: (v) => `$${v}` }, grid: { color: 'rgba(0,0,0,0.05)' } },
                    x: { grid: { display: false } }
                }
            }
        });
    }

    function createDailyConversionsChart() {
        const canvas = document.getElementById('dailyConversionsChart');
        if (!canvas) return;
        const data = CAMPAIGN_DATA.dailyConversions;
        if (charts.daily) charts.daily.destroy();
        charts.daily = new Chart(canvas, {
            type: 'line',
            data: {
                labels: data.map(d => d.date),
                datasets: [
                    {
                        label: 'Leads por dia',
                        data: data.map(d => d.leads),
                        borderColor: '#4CAF50',
                        backgroundColor: 'rgba(76, 175, 80, 0.1)',
                        borderWidth: 3,
                        tension: 0.4,
                        fill: true,
                        pointRadius: 6,
                        pointBackgroundColor: '#4CAF50',
                        yAxisID: 'y'
                    },
                    {
                        label: 'Cliques por dia',
                        data: data.map(d => d.clicks),
                        borderColor: '#2196F3',
                        borderWidth: 2,
                        tension: 0.4,
                        pointRadius: 4,
                        pointBackgroundColor: '#2196F3',
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top', labels: { usePointStyle: true, padding: 20 } },
                    tooltip: { mode: 'index', intersect: false }
                },
                scales: {
                    y: { type: 'linear', position: 'left', beginAtZero: true, title: { display: true, text: 'Leads' }, ticks: { stepSize: 1 } },
                    y1: { type: 'linear', position: 'right', beginAtZero: true, title: { display: true, text: 'Cliques' }, grid: { drawOnChartArea: false } },
                    x: { grid: { display: false } }
                },
                interaction: { intersect: false, mode: 'index' }
            }
        });
    }

    function updateTable() {
        const tbody = document.getElementById('kpisTableBody');
        if (!tbody) return;
        tbody.innerHTML = '';
        CAMPAIGN_DATA.campaigns.forEach(campaign => {
            const avgCpc = campaign.clicks > 0 ? campaign.investment / campaign.clicks : 0;
            const statusColor = campaign.status === 'ESCALAR' ? 'color: #4CAF50;' : 'color: #f44336;';
            const statusIcon = campaign.status === 'ESCALAR' ? 'V' : 'X';
            const row = tbody.insertRow();
            row.innerHTML = `
                <td><strong>${campaign.name}</strong></td>
                <td>$${campaign.investment.toFixed(2)}</td>
                <td>${campaign.impressions.toLocaleString('pt-BR')}</td>
                <td>${campaign.clicks}</td>
                <td>${campaign.ctr.toFixed(2)}%</td>
                <td>$${avgCpc.toFixed(2)}</td>
                <td>${campaign.conversions}</td>
                <td><span style="font-weight: bold; ${statusColor}">${statusIcon} ${campaign.status}</span></td>
            `;
        });
    }

    function setupEventListeners() {
        document.getElementById('refreshData')?.addEventListener('click', function() {
            updateTimestamp();
            alert('Dashboard atualizado!');
        });
        document.getElementById('exportExcel')?.addEventListener('click', exportToExcel);
    }

    function exportToExcel() {
        if (typeof XLSX === 'undefined') { alert('Biblioteca de exportacao nao carregada.'); return; }
        const wb = XLSX.utils.book_new();
        const resumo = [
            ['DASHBOARD MIA - RELATORIO DE CAMPANHAS'],
            ['Periodo: Novembro 2025'], [''],
            ['RESUMO GERAL'],
            ['Investimento Total', `$${CAMPAIGN_DATA.totalInvestment}`],
            ['Total de Cliques', CAMPAIGN_DATA.totalClicks],
            ['Total de Impressoes', CAMPAIGN_DATA.totalImpressions],
            ['CTR Medio', `${CAMPAIGN_DATA.ctr}%`],
            ['Total de Leads', CAMPAIGN_DATA.totalLeads], [''],
            ['CAMPANHAS'],
            ['Nome', 'Investimento', 'Cliques', 'Impressoes', 'CTR', 'Status'],
        ];
        CAMPAIGN_DATA.campaigns.forEach(c => resumo.push([c.name, `$${c.investment}`, c.clicks, c.impressions, `${c.ctr}%`, c.status]));
        XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(resumo), 'Resumo');
        XLSX.writeFile(wb, `MIA_Dashboard_${new Date().toISOString().split('T')[0]}.xlsx`);
        alert('Excel exportado com sucesso!');
    }

    function updateTimestamp() {
        const el = document.getElementById('lastUpdate');
        if (el) el.textContent = `Ultima atualizacao: ${new Date().toLocaleTimeString('pt-BR')}`;
    }

    window.MIADashboard = { version: '4.0.0', data: CAMPAIGN_DATA, charts: charts };
    </script>
</body>
</html>
