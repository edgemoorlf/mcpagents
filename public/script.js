console.log('Script loaded');

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded');
    const chatLog = document.getElementById('chat-log');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');

    let chatHistory = []; // To maintain context for the backend
    
    // Store the last request for retry functionality
    let lastRequest = null;

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

    function addMessageToLog(message, sender, isHtml = false) {
        console.log('Adding message:', { message, sender, isHtml });
        
        const messageElement = document.createElement('div');
        messageElement.className = `message ${sender}-message`;
        
        // Create a container for the message content and button
        const contentContainer = document.createElement('div');
        contentContainer.style.display = 'flex';
        contentContainer.style.alignItems = 'center';
        contentContainer.style.gap = '10px';
        
        // Create message content
        const messageContent = document.createElement('div');
        
        // Check if the message contains SQL results (pipe-separated format)
        if (message.includes('|')) {
            // Split the message into lines
            const lines = message.split('\n').filter(line => line.trim());
            
            if (lines.length >= 2) {
                // Create table for SQL results
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
                
                messageContent.appendChild(table);
            } else {
                if (isHtml) {
                    messageContent.innerHTML = message;
                } else {
                    messageContent.textContent = message;
                }
            }
        } else {
            if (isHtml) {
                messageContent.innerHTML = message;
            } else {
                messageContent.textContent = message;
            }
        }
        
        contentContainer.appendChild(messageContent);
        
        // Add retry button for all assistant messages
        if (sender === 'assistant') {
            const retryButton = document.createElement('button');
            retryButton.textContent = 'Retry';
            retryButton.className = 'retry-button';
            retryButton.style.cssText = `
                margin-left: 10px;
                padding: 5px 10px;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
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