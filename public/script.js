document.addEventListener('DOMContentLoaded', () => {
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
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', sender === 'user' ? 'user-message' : 'assistant-message');
        
        if (isHtml) {
            // For assistant messages that might contain preformatted SQL/results
            const preElement = document.createElement('pre');
            preElement.textContent = message; // Use textContent to avoid XSS with raw HTML from server
            messageElement.appendChild(preElement);
        } else {
            const pElement = document.createElement('p');
            pElement.textContent = message;
            messageElement.appendChild(pElement);
        }
        
        chatLog.appendChild(messageElement);
        chatLog.scrollTop = chatLog.scrollHeight; // Scroll to bottom
    }

    async function sendMessage() {
        const question = userInput.value.trim();
        if (!question) return;

        addMessageToLog(question, 'user');
        chatHistory.push({ role: 'user', content: question });
        userInput.value = ''; // Clear input field

        // Create a placeholder for the assistant's response
        const assistantMessageContainer = document.createElement('div');
        assistantMessageContainer.classList.add('message', 'assistant-message');
        const assistantPreElement = document.createElement('pre');
        assistantMessageContainer.appendChild(assistantPreElement);
        chatLog.appendChild(assistantMessageContainer);
        chatLog.scrollTop = chatLog.scrollHeight;

        let fullResponse = '';

        try {
            const response = await fetch('/ask/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    question: question,
                    chat_history: chatHistory.slice(0, -1) // Send history *before* current question
                }),
            });

            if (!response.ok) {
                const errorText = await response.text();
                assistantPreElement.textContent = `Error: ${response.status} ${errorText || response.statusText}`;
                chatHistory.push({ role: 'assistant', content: `Error: ${response.status} ${errorText || response.statusText}` });
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let reading = true;

            while(reading) {
                const { done, value } = await reader.read();
                if (done) {
                    reading = false;
                    break;
                }
                const chunk = decoder.decode(value, { stream: true });
                fullResponse += chunk;
                assistantPreElement.textContent = fullResponse; // Update pre element with new chunk
                chatLog.scrollTop = chatLog.scrollHeight;
            }
            
        } catch (error) {
            console.error('Error sending message:', error);
            fullResponse = `Error: Could not connect to the server. ${error.message}`;
            assistantPreElement.textContent = fullResponse;
        }
        chatHistory.push({ role: 'assistant', content: fullResponse });
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