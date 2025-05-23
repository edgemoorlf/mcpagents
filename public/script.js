console.log('Script loaded');

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded');
    const chatLog = document.getElementById('chat-log');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const recordButton = document.getElementById('record-button');

    let chatHistory = []; // To maintain context for the backend
    let isRecording = false;
    let recognitionMode = 'chinese'; // Default to Chinese mode, can toggle between 'english' and 'chinese'
    
    // Audio recording variables
    let mediaRecorder;
    let audioChunks = [];
    
    // Store the last request for retry functionality
    let lastRequest = null;
    
    // Check for supported MIME types
    function getSupportedMimeType() {
        const types = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/mp4',
            'audio/mpeg',
            'audio/wav'
        ];
        
        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) {
                console.log(`Browser supports recording with MIME type: ${type}`);
                return type;
            }
        }
        
        console.warn('None of the preferred MIME types are supported, using default');
        return '';  // Let the browser use default
    }
    
    // Hotwords for post-processing
    const hotwords = ['deepseek-r1', 'gpt-4o'];

    // Simple fuzzy match/correction for hotwords
    function correctHotwords(text) {
        // Lowercase for comparison
        let corrected = text;
        hotwords.forEach(hotword => {
            // If hotword is not in the text, try to correct similar sounding words
            // You can expand this with more advanced fuzzy matching if needed
            const regex = new RegExp(hotword.replace(/[-]/g, '[- ]'), 'i'); // allow for space or dash
            if (!regex.test(corrected)) {
                // Try to replace common misrecognitions (add more as needed)
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

    // Toggle between English and Chinese recognition modes
    function toggleRecognitionMode() {
        recognitionMode = recognitionMode === 'english' ? 'chinese' : 'english';
        console.log(`Recognition mode switched to: ${recognitionMode}`);
        // Update UI to indicate current mode (you can add a visual indicator)
    }
    
    // Web Speech API setup (for English recognition)
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let webSpeechRecognition;

    if (SpeechRecognition) {
        webSpeechRecognition = new SpeechRecognition();
        webSpeechRecognition.continuous = false;
        webSpeechRecognition.lang = 'en-US'; // English recognition
        webSpeechRecognition.interimResults = false;
        webSpeechRecognition.maxAlternatives = 1;

        webSpeechRecognition.onresult = (event) => {
            let speechResult = event.results[0][0].transcript;
            speechResult = correctHotwords(speechResult);
            userInput.value = speechResult;
            stopRecording(); // Automatically stop after getting a result
            sendMessage(); // Automatically send after successful recognition
        };

        webSpeechRecognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            addMessageToLog(`Speech recognition error: ${event.error}`, 'assistant');
            stopRecording();
        };

        webSpeechRecognition.onend = () => {
            if (isRecording && recognitionMode === 'english') { // If it ended unexpectedly while supposed to be recording
                stopRecording();
            }
        };
    } else {
        console.warn('Web Speech API not supported in this browser.');
    }
    
    // Setup for recording audio (for Chinese recognition using local API)
    async function setupAudioRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            
            // Get a supported MIME type
            const supportedType = getSupportedMimeType();
            const options = supportedType ? { mimeType: supportedType } : undefined;
            
            console.log(`Creating MediaRecorder with options:`, options);
            mediaRecorder = new MediaRecorder(stream, options);
            
            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };
            
            mediaRecorder.onstop = async () => {
                if (recognitionMode === 'chinese') {
                    const mimeType = mediaRecorder.mimeType || supportedType || 'audio/webm';
                    console.log(`Creating audio blob with type: ${mimeType}`);
                    const audioBlob = new Blob(audioChunks, { type: mimeType });
                    await sendAudioToLocalAPI(audioBlob);
                    audioChunks = []; // Clear chunks for next recording
                }
            };
            
            return true;
        } catch (error) {
            console.error('Error accessing microphone:', error);
            addMessageToLog(`Could not access microphone: ${error.message}`, 'assistant');
            return false;
        }
    }
    
    // Send audio to local API for Chinese recognition
    async function sendAudioToLocalAPI(audioBlob) {
        try {
            // Create FormData and append the audio file
            const formData = new FormData();
            
            // Determine extension from mime type
            const mimeType = audioBlob.type || 'audio/webm';
            let extension = '.webm';
            
            if (mimeType.includes('webm')) extension = '.webm';
            else if (mimeType.includes('mp4')) extension = '.mp4';
            else if (mimeType.includes('mpeg')) extension = '.mp3';
            else if (mimeType.includes('ogg')) extension = '.ogg';
            else if (mimeType.includes('wav')) extension = '.wav';
            
            const filename = `recording${extension}`;
            console.log(`Sending recording as ${filename} with mime type: ${mimeType}`);
            
            formData.append('file', audioBlob, filename);
            
            // Show indicator that processing is happening
            userInput.placeholder = "处理中...";
            userInput.disabled = true;
            
            // Add debugging info
            console.log(`Audio blob size: ${audioBlob.size} bytes`);
            
            // Send to our proxy endpoint instead of direct API access
            // This avoids CORS issues by having the server handle the cross-origin request
            const response = await fetch('/recognize', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`Server responded with status: ${response.status}`);
            }
            
            const result = await response.json();
            if (result.text) {
                // Apply hotword correction to the recognized text
                let recognizedText = correctHotwords(result.text);
                userInput.value = recognizedText;
                sendMessage(); // Automatically send after recognition
            } else {
                console.error('No recognized text returned from API');
                addMessageToLog('No speech detected', 'assistant');
            }
        } catch (error) {
            console.error('Error sending audio to API:', error);
            addMessageToLog(`Recognition error: ${error.message}`, 'assistant');
        } finally {
            // Reset UI
            userInput.placeholder = "Type your question or use the mic...";
            userInput.disabled = false;
        }
    }

    function toggleRecording() {
        if (isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    }

    async function startRecording() {
        if (isRecording) return;
        
        try {
            if (recognitionMode === 'english') {
                // Use Web Speech API for English
                if (webSpeechRecognition) {
                    webSpeechRecognition.start();
                } else {
                    throw new Error('Web Speech API not supported');
                }
            } else {
                // Use local API for Chinese - start recording audio
                if (!mediaRecorder) {
                    const success = await setupAudioRecording();
                    if (!success) {
                        throw new Error('Failed to setup audio recording');
                    }
                }
                
                audioChunks = []; // Clear any previous recording
                
                try {
                    // Check if mediaRecorder is in inactive state before starting
                    if (mediaRecorder.state === 'inactive') {
                        mediaRecorder.start();
                        console.log('MediaRecorder started successfully');
                    } else {
                        console.warn(`Cannot start mediaRecorder in state: ${mediaRecorder.state}`);
                        // Try to reset the mediaRecorder
                        mediaRecorder.stop();
                        await new Promise(resolve => setTimeout(resolve, 100));
                        mediaRecorder.start();
                    }
                } catch (recordError) {
                    console.error('Error starting MediaRecorder:', recordError);
                    
                    // Try to recreate the MediaRecorder with a different mime type
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    const supportedType = getSupportedMimeType();
                    console.log(`Trying again with mime type: ${supportedType || 'browser default'}`);
                    
                    // Create a new MediaRecorder with the supported mime type
                    const options = supportedType ? { mimeType: supportedType } : undefined;
                    mediaRecorder = new MediaRecorder(stream, options);
                    
                    // Re-attach event handlers
                    mediaRecorder.ondataavailable = (event) => {
                        if (event.data.size > 0) {
                            audioChunks.push(event.data);
                        }
                    };
                    
                    mediaRecorder.onstop = async () => {
                        if (recognitionMode === 'chinese') {
                            const audioBlob = new Blob(audioChunks, { type: supportedType || 'audio/webm' });
                            await sendAudioToLocalAPI(audioBlob);
                            audioChunks = []; // Clear chunks for next recording
                        }
                    };
                    
                    // Try to start the new MediaRecorder
                    mediaRecorder.start();
                }
            }
            
            isRecording = true;
            recordButton.classList.add('recording');
            recordButton.textContent = 'STOP';
        } catch (e) {
            console.error("Error starting speech recognition:", e);
            addMessageToLog(`Could not start recording: ${e.message}`, 'assistant');
        }
    }

    function stopRecording() {
        if (!isRecording) return;
        
        if (recognitionMode === 'english') {
            // Stop Web Speech API
            if (webSpeechRecognition) {
                webSpeechRecognition.stop();
            }
        } else {
            // Stop audio recording for local API
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                mediaRecorder.stop();
            }
        }
        
        isRecording = false;
        recordButton.classList.remove('recording');
        recordButton.textContent = '🎤';
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
                
                // Create table body from remaining lines
                const tbody = document.createElement('tbody');
                for (let i = 1; i < lines.length; i++) {
                    const tr = document.createElement('tr');
                    const values = lines[i].split('|').map(v => v.trim());
                    values.forEach(value => {
                        const td = document.createElement('td');
                        // Format numbers if they're numeric
                        if (!isNaN(value) && value.trim() !== '') {
                            // If it's a decimal number, format it to 4 decimal places
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
                // Not enough lines for a table, display as normal text
                if (isHtml) {
                    messageContent.innerHTML = message;
                } else {
                    messageContent.textContent = message;
                }
            }
        } else {
            // Not SQL results, display as normal text
            if (isHtml) {
                messageContent.innerHTML = message;
            } else {
                messageContent.textContent = message;
            }
        }
        
        contentContainer.appendChild(messageContent);
        
        // Add retry button for all assistant messages
        if (sender === 'assistant') {
            console.log('Creating retry button');
            
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
            
            // Add click handler
            retryButton.addEventListener('click', async function(e) {
                console.log('Retry button clicked');
                e.preventDefault();
                e.stopPropagation();
                
                if (lastRequest) {
                    console.log('Retrying request:', lastRequest);
                    
                    // Disable the retry button while retrying
                    this.disabled = true;
                    this.textContent = 'Retrying...';
                    
                    try {
                        // Remove the current message
                        messageElement.remove();
                        
                        // Retry the last request
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
                        // Re-enable the retry button
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
        
        console.log('Sending message:', question); // Debug log 11
        
        // Store the current request for potential retry
        lastRequest = {
            question: question,
            chat_history: [...chatHistory] // Create a copy of the chat history
        };
        
        console.log('Stored lastRequest:', lastRequest); // Debug log 12
        
        // Add user message to chat
        addMessageToLog(question, 'user');
        userInput.value = '';
        
        // Add user message to chat history
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
            console.log('Response received:', result); // Debug log 13
            
            if (result.error) {
                addMessageToLog(result.error, 'assistant');
            } else {
                addMessageToLog(result.answer, 'assistant');
                // Add assistant response to chat history
                chatHistory.push({ role: 'assistant', content: result.answer });
            }
        } catch (error) {
            console.error('Send message error:', error); // Debug log 14
            addMessageToLog(`Error: ${error.message}`, 'assistant');
        }
    }

    // Setup event listeners
    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            sendMessage();
        }
    });

    if (recordButton) {
        recordButton.addEventListener('click', toggleRecording);
        // Double-click to toggle between English and Chinese recognition modes
        recordButton.addEventListener('dblclick', (event) => {
            event.preventDefault(); // Prevent default double-click behavior
            toggleRecognitionMode();
            // Provide visual feedback
            addMessageToLog(`已切换到${recognitionMode === 'english' ? '英文' : '中文'}语音识别模式`, 'assistant');
        });
    }
    
    // Initial setup for audio recording
    setupAudioRecording();
}); 