console.log('Script loaded');

// Add Chart.js library
const chartScript = document.createElement('script');
chartScript.src = 'https://cdn.jsdelivr.net/npm/chart.js';
document.head.appendChild(chartScript);

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded');
    const chatLog = document.getElementById('chat-log');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');

    let chatHistory = []; // To maintain context for the backend
    
    // Store the last request for retry functionality
    let lastRequest = null;
    let currentChart = null; // Keep track of current chart

    // Hotwords for post-processing (still used for text input)
    const hotwords = ['deepseek-r1', 'gpt-4o'];
    function correctHotwords(text) {
        let corrected = text;
        hotwords.forEach(hotword => {
            const regex = new RegExp(hotword.replace(/[-]/g, '[- ]'), 'i');
            if (!regex.test(corrected)) {
                if (hotword === 'deepseek-r1') {
                    corrected = corrected.replace(/deep seek|deep sick|deep sea|滴锡|滴西|滴息|滴希|滴锡/g, 'deepseek-r1');
                }
                if (hotword === 'gpt-4o') {
                    corrected = corrected.replace(/gpt ?4o|gpt ?for o|gpt ?四 o|gpt ?四欧|gpt ?佛欧|gpt ?佛 o|gpt ?佛/g, 'gpt-4o');
                }
            }
        });
        return corrected;
    }

    // Function to determine if the data should be visualized
    function shouldVisualize(question, data) {
        const visualizationKeywords = ['trend', 'distribution', 'rpm', 'tpm', '分布', '趋势'];
        return visualizationKeywords.some(keyword => question.toLowerCase().includes(keyword)) && 
               data && data.includes('|');
    }

    // Function to create a chart from table data
    function createChart(tableData, question) {
        const lines = tableData.split('\n').filter(line => line.trim());
        if (lines.length < 2) return null;

        const headers = lines[0].split('|').map(h => h.trim());
        const data = lines.slice(1).map(line => 
            line.split('|').map(v => {
                const num = Number(v.trim());
                return isNaN(num) ? v.trim() : num;
            })
        );

        // Determine chart type based on the question and data
        let chartType = 'line';
        if (question.toLowerCase().includes('distribution') || question.toLowerCase().includes('分布')) {
            chartType = 'bar';
        }

        const chartData = {
            labels: data.map(row => row[0]),
            datasets: [{
                label: headers[1],
                data: data.map(row => row[1]),
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }]
        };

        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true
                }
            },
            plugins: {
                title: {
                    display: true,
                    text: question
                }
            }
        };

        return { type: chartType, data: chartData, options: chartOptions };
    }

    // Add column name translations
    const columnTranslations = {
        // Time related
        'created_at': '时间',
        'timestamp': '时间戳',
        'hour': '小时',
        'date': '日期',
        'time': '时间',
        
        // Model related
        'model_name': '模型名称',
        'model': '模型',
        'model_type': '模型类型',
        
        // Usage metrics
        'token_used': '消耗token数',
        'tokens': 'token数',
        'prompt_tokens': '输入token数',
        'completion_tokens': '输出token数',
        'total_tokens': '总token数',
        'count': '调用次数',
        'requests': '请求数',
        'rpm': '每分钟请求数',
        'tpm': '每分钟token数',
        
        // Cost related
        'quota': '配额消耗',
        'cost': '成本',
        'price': '价格',
        'amount': '金额',
        
        // Channel related
        'channel': '渠道',
        'channel_name': '渠道名称',
        'channel_id': '渠道ID',
        
        // User related
        'user': '用户',
        'username': '用户名',
        'user_id': '用户ID',
        'user_group': '用户组',
        
        // Performance metrics
        'latency': '延迟',
        'duration': '持续时间',
        'use_time': '使用时间',
        
        // Percentage metrics
        'percentage': '百分比',
        'ratio': '比率',
        'rate': '比率',
        
        // Status
        'status': '状态',
        'success': '成功',
        'failed': '失败',
        
        // Others
        'total': '总计',
        'average': '平均值',
        'max': '最大值',
        'min': '最小值'
    };

    function translateColumnName(columnName) {
        // Convert to lowercase and remove underscores for matching
        const normalizedName = columnName.toLowerCase().trim();
        
        // Try exact match first
        if (columnTranslations[normalizedName]) {
            return columnTranslations[normalizedName];
        }
        
        // Try partial matches
        for (const [key, value] of Object.entries(columnTranslations)) {
            if (normalizedName.includes(key)) {
                return value;
            }
        }
        
        // If no match found, return original
        return columnName;
    }

    function addMessageToLog(message, sender, isHtml = false) {
        console.log('Adding message:', { message, sender, isHtml });
        
        const messageElement = document.createElement('div');
        messageElement.className = `message ${sender}-message`;
        
        const contentContainer = document.createElement('div');
        contentContainer.style.display = 'flex';
        contentContainer.style.flexDirection = 'column';
        contentContainer.style.gap = '10px';
        contentContainer.style.width = '100%';
        
        const messageContent = document.createElement('div');
        messageContent.style.width = '100%';
        
        // Check if we should create a visualization
        if (sender === 'assistant' && shouldVisualize(lastRequest?.question || '', message)) {
            // Create a single table for both chart and data
            const tableDiv = document.createElement('div');
            tableDiv.className = 'table-wrapper';
            tableDiv.style.width = '100%';
            
            // Create separate tables for chart and data
            // Chart table
            const chartTable = document.createElement('table');
            chartTable.className = 'chart-table';
            const chartRow = document.createElement('tr');
            const chartCell = document.createElement('td');
            chartCell.className = 'chart-cell';
            
            const chartContainer = document.createElement('div');
            chartContainer.className = 'chart-container';
            
            const canvas = document.createElement('canvas');
            chartContainer.appendChild(canvas);
            
            const chartConfig = createChart(message, lastRequest?.question || '');
            if (chartConfig) {
                currentChart = new Chart(canvas, chartConfig);
                chartCell.appendChild(chartContainer);
                chartRow.appendChild(chartCell);
                chartTable.appendChild(chartRow);
            }
            
            // Add delimiter
            const delimiter = document.createElement('div');
            delimiter.className = 'table-delimiter';
            
            // Data table
            const dataTable = document.createElement('table');
            dataTable.className = 'sql-results-table';
            
            if (message.includes('|')) {
                const lines = message.split('\n').filter(line => line.trim());
                if (lines.length >= 2) {
                    // Create table header
                    const thead = document.createElement('thead');
                    const headerRow = document.createElement('tr');
                    const headers = lines[0].split('|').map(h => h.trim());
                    
                    // Determine column types by checking first data row
                    const firstDataRow = lines[1].split('|').map(v => v.trim());
                    const columnTypes = firstDataRow.map(value => !isNaN(value) && value.trim() !== '' ? 'numeric' : 'text');
                    
                    headers.forEach((header, idx) => {
                        const th = document.createElement('th');
                        const translatedHeader = translateColumnName(header);
                        
                        // Show both English and Chinese if translation exists and is different
                        if (translatedHeader !== header) {
                            th.innerHTML = `${translatedHeader}<br><span class="original-header">${header}</span>`;
                        } else {
                            th.textContent = header;
                        }
                        
                        th.className = columnTypes[idx] + '-col';
                        headerRow.appendChild(th);
                    });
                    thead.appendChild(headerRow);
                    dataTable.appendChild(thead);
                    
                    // Create table body
                    const tbody = document.createElement('tbody');
                    for (let i = 1; i < lines.length; i++) {
                        const tr = document.createElement('tr');
                        const values = lines[i].split('|').map(v => v.trim());
                        values.forEach((value, colIdx) => {
                            const td = document.createElement('td');
                            td.className = columnTypes[colIdx] + '-col';
                            if (!isNaN(value) && value.trim() !== '') {
                                if (value.includes('.')) {
                                    td.textContent = Number(value).toFixed(4);
                                } else {
                                    td.textContent = Number(value).toLocaleString();
                                }
                            } else {
                                td.textContent = value;
                            }
                            tr.appendChild(td);
                        });
                        tbody.appendChild(tr);
                    }
                    dataTable.appendChild(tbody);
                }
            }
            
            // Append everything in correct order
            tableDiv.appendChild(chartTable);
            tableDiv.appendChild(delimiter);
            tableDiv.appendChild(dataTable);
            messageContent.appendChild(tableDiv);
        } else if (message.includes('|')) {
            // Regular table handling for non-chart cases
            const tableDiv = document.createElement('div');
            tableDiv.className = 'table-wrapper';
            tableDiv.style.width = '100%';
            
            const lines = message.split('\n').filter(line => line.trim());
            if (lines.length >= 2) {
                const table = document.createElement('table');
                table.className = 'sql-results-table';
                
                // Create table header from first line
                const thead = document.createElement('thead');
                const headerRow = document.createElement('tr');
                const headers = lines[0].split('|').map(h => h.trim());
                headers.forEach(header => {
                    const th = document.createElement('th');
                    th.textContent = header;
                    headerRow.appendChild(th);
                });
                thead.appendChild(headerRow);
                table.appendChild(thead);
                
                // Identify columns for special formatting
                const usdColumns = headers.map(h => h.toLowerCase()).map((h, i) => (h.includes('usd') || h.includes('cost') || h.includes('quota')) ? i : -1).filter(i => i !== -1);
                const percentColumns = headers.map(h => h.toLowerCase()).map((h, i) => (h.includes('percent') || h.includes('percentage')) ? i : -1).filter(i => i !== -1);
                
                // Create table body from remaining lines
                const tbody = document.createElement('tbody');
                for (let i = 1; i < lines.length; i++) {
                    const tr = document.createElement('tr');
                    const values = lines[i].split('|').map(v => v.trim());
                    values.forEach((value, colIdx) => {
                        const td = document.createElement('td');
                        // Format USD columns
                        if (usdColumns.includes(colIdx) && !isNaN(value) && value.trim() !== '') {
                            td.textContent = `$${Number(value).toFixed(2)}`;
                        } else if (percentColumns.includes(colIdx) && !isNaN(value) && value.trim() !== '') {
                            td.textContent = `${Number(value).toFixed(2)}%`;
                        } else if (!isNaN(value) && value.trim() !== '') {
                            if (value.includes('.')) {
                                td.textContent = Number(value).toFixed(4);
                            } else {
                                td.textContent = Number(value).toLocaleString();
                            }
                        } else {
                            td.textContent = value;
                        }
                        tr.appendChild(td);
                    });
                    tbody.appendChild(tr);
                }
                table.appendChild(tbody);
                
                tableDiv.appendChild(table);
            }
            messageContent.appendChild(tableDiv);
        } else {
            if (isHtml) {
                messageContent.innerHTML = message;
            } else {
                // Enhanced formatting for single-value responses
                let formatted = message;
                const trimmed = message.trim();
                // USD formatting: e.g. '123.45 USD', '$123.45', 'cost: 123.45', 'quota: 123.45'
                if (/^(\$?\d+(\.\d+)?(\s*usd)?|cost: ?\d+(\.\d+)?|quota: ?\d+(\.\d+)?)/i.test(trimmed)) {
                    let num = trimmed.match(/\d+(\.\d+)?/);
                    if (num) {
                        formatted = `$${Number(num[0]).toFixed(2)}`;
                    }
                } else if (/^(\d+(\.\d+)?\s*%|percent|percentage)/i.test(trimmed) || /\d+(\.\d+)?\s*%$/.test(trimmed)) {
                    let num = trimmed.match(/\d+(\.\d+)?/);
                    if (num) {
                        formatted = `${Number(num[0]).toFixed(2)}%`;
                    }
                } else if (!isNaN(trimmed) && trimmed !== '') {
                    if (trimmed.includes('.')) {
                        formatted = Number(trimmed).toFixed(4);
                    } else {
                        formatted = Number(trimmed).toLocaleString();
                    }
                }
                messageContent.textContent = formatted;
            }
        }
                
        contentContainer.appendChild(messageContent);
        
        // Update retry button to use an icon
        if (sender === 'assistant') {
            const retryButton = document.createElement('button');
            retryButton.className = 'retry-button';
            retryButton.setAttribute('title', 'Retry'); // Add tooltip
            
            // Create retry icon using SVG
            retryButton.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
                    <path d="M21 3v5h-5"/>
                    <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
                    <path d="M8 16H3v5"/>
                </svg>
            `;
            
            retryButton.addEventListener('click', async function(e) {
                console.log('Retry button clicked');
                e.preventDefault();
                e.stopPropagation();
                if (lastRequest) {
                    console.log('Retrying request:', lastRequest);
                    this.disabled = true;
                    this.textContent = 'Retrying...';
                    try {
                        messageElement.remove();
                        const response = await fetch('/ask', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify(lastRequest)
                        });
                        const result = await response.json();
                        console.log('Retry response:', result);
                        if (result.error) {
                            addMessageToLog(result.error, 'assistant');
                        } else {
                            addMessageToLog(result.answer, 'assistant');
                            chatHistory.push({ role: 'assistant', content: result.answer });
                        }
                    } catch (error) {
                        console.error('Retry error:', error);
                        addMessageToLog(`Retry failed: ${error.message}`, 'assistant');
                    } finally {
                        this.disabled = false;
                        this.textContent = 'Retry';
                    }
                } else {
                    console.log('No lastRequest available');
                }
            });
            
            contentContainer.appendChild(retryButton);
        }
        
        messageElement.appendChild(contentContainer);
        chatLog.appendChild(messageElement);
        chatLog.scrollTop = chatLog.scrollHeight;
    }

    async function sendMessage() {
        const question = userInput.value.trim();
        if (!question) return;
        console.log('Sending message:', question);
        lastRequest = {
            question: question,
            chat_history: [...chatHistory]
        };
        console.log('Stored lastRequest:', lastRequest);
        addMessageToLog(question, 'user');
        userInput.value = '';
        chatHistory.push({ role: 'user', content: question });
        try {
            const response = await fetch('/ask', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    question: question,
                    chat_history: chatHistory
                })
            });
            const result = await response.json();
            console.log('Response received:', result);
            if (result.error) {
                addMessageToLog(result.error, 'assistant');
            } else {
                addMessageToLog(result.answer, 'assistant');
                chatHistory.push({ role: 'assistant', content: result.answer });
            }
        } catch (error) {
            console.error('Send message error:', error);
            addMessageToLog(`Error: ${error.message}`, 'assistant');
        }
    }

    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            sendMessage();
        }
    });
}); 