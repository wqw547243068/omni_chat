// Qwen-Omni-Realtime Web 客户端
// 支持：心跳保活、自动重连、连接状态监控

const state = {
    ws: null,
    isConnected: false,
    isConnecting: false,
    connectionState: 'disconnected', // disconnected, connecting, connected, reconnecting
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    reconnectDelay: 3000,
    heartbeatInterval: null,
    lastPongTime: 0,
    heartbeatTimeout: 30000, // 30秒超时
    
    audioEnabled: true,
    videoEnabled: false,
    screenShareEnabled: false,
    searchEnabled: true,
    captionEnabled: true,
    micMuted: false,
    
    // 媒体流
    localStream: null,
    audioContext: null,
    audioInput: null,
    audioWorklet: null,
    videoInterval: null,
    
    // 统计
    frameCount: 0,
    lastFpsTime: Date.now(),
    audioBytesSent: 0,
    lastAudioTime: Date.now(),
    
    // 会话
    conversationId: null,
    messageQueue: [],
};

// ==================== DOM 元素 ====================
const elements = {
    wsUrl: document.getElementById('wsUrl'),
    apiKey: document.getElementById('apiKey'),
    model: document.getElementById('model'),
    voice: document.getElementById('voice'),
    connectBtn: document.getElementById('connectBtn'),
    
    localVideo: document.getElementById('localVideo'),
    videoCanvas: document.getElementById('videoCanvas'),
    localPlaceholder: document.getElementById('localPlaceholder'),
    localInfo: document.getElementById('localInfo'),
    localStatus: document.getElementById('localStatus'),
    
    remoteStatus: document.getElementById('remoteStatus'),
    remoteInfo: document.getElementById('remoteInfo'),
    
    chatMessages: document.getElementById('chatMessages'),
    textInput: document.getElementById('textInput'),
    sendBtn: document.getElementById('sendBtn'),
    
    wsStatus: document.getElementById('wsStatus'),
    fpsValue: document.getElementById('fpsValue'),
    audioRate: document.getElementById('audioRate'),
    
    micBtn: document.getElementById('micBtn'),
    micIcon: document.getElementById('micIcon'),
    micText: document.getElementById('micText'),
    cameraBtn: document.getElementById('cameraBtn'),
    cameraIcon: document.getElementById('cameraIcon'),
    cameraText: document.getElementById('cameraText'),
    
    logsContent: document.getElementById('logsContent'),
    logCount: document.getElementById('logCount'),
};

// ==================== 日志系统 ====================
let logs = [];
const MAX_LOGS = 100;

function addLog(type, message, data = null) {
    const timestamp = new Date().toLocaleTimeString();
    const log = { time: timestamp, type, message, data };
    logs.push(log);
    if (logs.length > MAX_LOGS) logs.shift();

    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';
    const typeClass = `log-type-${type}`;
    logEntry.innerHTML = `
        <span class="log-time">[${timestamp}]</span>
        <span class="log-type ${typeClass}">${type.toUpperCase()}</span>
        <span class="log-message">${message}</span>
        ${data ? `<pre class="log-data">${JSON.stringify(data, null, 2)}</pre>` : ''}
    `;
    elements.logsContent.appendChild(logEntry);
    elements.logsContent.scrollTop = elements.logsContent.scrollHeight;
    elements.logCount.textContent = `${logs.length} 条记录`;
}

// ==================== WebSocket 连接管理 ====================

async function connectWebSocket() {
    const url = elements.wsUrl.value || 'ws://localhost:8081';
    const apiKey = elements.apiKey.value;
    
    if (state.ws && (state.ws.readyState === WebSocket.CONNECTING || state.ws.readyState === WebSocket.OPEN)) {
        addLog('warn', 'WebSocket 已在连接中');
        return;
    }
    
    state.connectionState = 'connecting';
    state.isConnecting = true;
    elements.connectBtn.textContent = '连接中...';
    elements.connectBtn.disabled = true;
    updateConnectionStatus('connecting', '连接中...');
    
    try {
        addLog('info', '正在连接服务器...', { url, attempt: state.reconnectAttempts + 1 });
        
        state.ws = new WebSocket(url);
        
        state.ws.onopen = onWsOpen;
        state.ws.onmessage = onWsMessage;
        state.ws.onerror = onWsError;
        state.ws.onclose = onWsClose;
        
    } catch (error) {
        addLog('error', '连接创建失败', error.message);
        handleConnectionFailure();
    }
}

async function onWsOpen() {
    addLog('success', 'WebSocket 连接已建立');
    state.isConnected = true;
    state.isConnecting = false;
    state.connectionState = 'connected';
    state.reconnectAttempts = 0; // 重置重连计数
    state.lastPongTime = Date.now();
    
    elements.connectBtn.textContent = '断开';
    elements.connectBtn.className = 'btn btn-danger';
    elements.connectBtn.disabled = false;
    updateConnectionStatus('connected', '已连接');
    
    elements.textInput.disabled = false;
    elements.sendBtn.disabled = false;
    elements.remoteStatus.classList.add('active');
    elements.remoteInfo.textContent = '已连接';
    
    addMessage('system', '✓ 已连接到服务器，正在初始化...');
    
    // 发送初始化消息
    const initMessage = {
        type: 'init',
        api_key: elements.apiKey.value,
        model: elements.model.value
    };
    sendWsMessage(initMessage);
    
    // 启动心跳保活
    startHeartbeat();
    
    // 初始化会话
    await initializeSession();
    
    // 启用麦克风
    if (state.audioEnabled) {
        await startAudioInput();
    }
    
    // 启用摄像头
    if (state.videoEnabled) {
        await startVideoInput();
    }
}

function onWsMessage(event) {
    try {
        const data = JSON.parse(event.data);
        
        // 处理心跳响应
        if (data.type === 'ping') {
            state.lastPongTime = Date.now();
            // 回应pong
            sendWsMessage({ type: 'pong', timestamp: Date.now() });
            return;
        }
        
        // 只记录非频繁消息
        if (data.type !== 'response.audio.delta') {
            addLog('recv', data.type, data);
        }
        
        handleServerEvent(data);
    } catch (error) {
        addLog('error', '解析消息失败', error.message);
    }
}

function onWsError(error) {
    addLog('error', 'WebSocket 错误', error);
    updateConnectionStatus('error', '连接错误');
}

function onWsClose(event) {
    addLog('info', 'WebSocket 连接已关闭', { 
        code: event.code, 
        reason: event.reason,
        wasClean: event.wasClean 
    });
    
    // 停止心跳
    stopHeartbeat();
    
    // 清理状态
    state.isConnected = false;
    state.isConnecting = false;
    state.ws = null;
    
    // 停止媒体流
    stopAudioInput();
    stopVideoInput();
    
    // 更新UI
    elements.connectBtn.textContent = '连接';
    elements.connectBtn.className = 'btn btn-primary';
    elements.connectBtn.disabled = false;
    updateConnectionStatus('disconnected', '已断开');
    elements.remoteStatus.classList.remove('active');
    elements.remoteInfo.textContent = '未连接';
    
    // 非正常关闭时自动重连
    if (!event.wasClean && state.connectionState !== 'disconnected') {
        handleConnectionFailure();
    }
}

function handleConnectionFailure() {
    state.connectionState = 'reconnecting';
    
    if (state.reconnectAttempts >= state.maxReconnectAttempts) {
        addLog('error', '重连次数超限，请手动刷新页面重试');
        updateConnectionStatus('error', '连接失败');
        elements.connectBtn.textContent = '重试';
        elements.connectBtn.disabled = false;
        return;
    }
    
    state.reconnectAttempts++;
    const delay = state.reconnectDelay * Math.min(state.reconnectAttempts, 3);
    
    addLog('warn', `连接中断，${delay/1000}秒后重试 (第${state.reconnectAttempts}/${state.maxReconnectAttempts}次)`);
    updateConnectionStatus('reconnecting', `重连中...${state.reconnectAttempts}`);
    
    setTimeout(() => {
        if (state.connectionState === 'reconnecting') {
            connectWebSocket();
        }
    }, delay);
}

function startHeartbeat() {
    if (state.heartbeatInterval) {
        clearInterval(state.heartbeatInterval);
    }
    
    state.lastPongTime = Date.now();
    
    state.heartbeatInterval = setInterval(() => {
        if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
            return;
        }
        
        // 检查超时
        const timeSinceLastPong = Date.now() - state.lastPongTime;
        if (timeSinceLastPong > state.heartbeatTimeout) {
            addLog('warn', '心跳超时，准备重连...');
            state.ws.close(4001, 'Heartbeat timeout');
            return;
        }
        
        // 发送pong保活
        try {
            sendWsMessage({ type: 'pong', timestamp: Date.now() });
        } catch (e) {
            addLog('error', '心跳发送失败', e.message);
        }
    }, 10000); // 每10秒发送一次
}

function stopHeartbeat() {
    if (state.heartbeatInterval) {
        clearInterval(state.heartbeatInterval);
        state.heartbeatInterval = null;
    }
}

function updateConnectionStatus(status, message) {
    const statusEl = elements.wsStatus;
    if (!statusEl) return;
    
    const statusColors = {
        disconnected: '#ff4444',
        connecting: '#ffaa00',
        connected: '#00ff88',
        reconnecting: '#ffaa00',
        error: '#ff4444'
    };
    
    statusEl.style.color = statusColors[status] || '#ffffff';
    statusEl.textContent = message || status;
}

function disconnect() {
    state.connectionState = 'disconnected';
    state.reconnectAttempts = 0;
    stopHeartbeat();
    stopAudioInput();
    stopVideoInput();
    
    if (state.ws) {
        state.ws.close(1000, 'User disconnect');
        state.ws = null;
    }
    
    state.isConnected = false;
    state.isConnecting = false;
    
    elements.connectBtn.textContent = '连接';
    elements.connectBtn.className = 'btn btn-primary';
    elements.connectBtn.disabled = false;
    updateConnectionStatus('disconnected', '已断开');
    elements.remoteStatus.classList.remove('active');
    elements.remoteInfo.textContent = '未连接';
    elements.textInput.disabled = true;
    elements.sendBtn.disabled = true;
}

function sendWsMessage(message) {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
        addLog('error', 'WebSocket 未连接');
        return false;
    }
    
    try {
        state.ws.send(JSON.stringify(message));
        return true;
    } catch (error) {
        addLog('error', '发送消息失败', error.message);
        return false;
    }
}

// ==================== 会话管理 ====================

async function initializeSession() {
    const sessionConfig = {
        type: 'session.update',
        session: {
            model: elements.model.value,
            voice: elements.voice.value,
            modalities: ['text', 'audio'],
            instructions: '你是一个有帮助的AI助手。请用简洁、友好的方式回答。',
            input_audio_format: 'pcm16',
            output_audio_format: 'pcm16',
            input_audio_transcription: {
                model: 'whisper-1',
                language: 'zh'
            },
            turn_detection: {
                type: 'server_vad',
                threshold: 0.5,
                prefix_padding_ms: 300,
                silence_duration_ms: 500
            },
            tools: state.searchEnabled ? [
                { type: 'function', function: { name: 'search', description: '搜索信息' } }
            ] : []
        }
    };
    
    addLog('info', '初始化会话', sessionConfig);
    sendWsMessage(sessionConfig);
}

function handleServerEvent(data) {
    switch (data.type) {
        case 'connection.open':
            addMessage('system', '✓ ' + (data.message || '连接成功'));
            break;
            
        case 'session.created':
        case 'session.updated':
            addLog('info', '会话已创建');
            addMessage('system', '✓ 会话已就绪，可以开始对话');
            break;
            
        case 'conversation.item.input_audio_transcription.completed':
            if (data.transcript) {
                addMessage('user', data.transcript);
            }
            break;
            
        case 'response.audio_transcript.done':
            if (data.transcript) {
                addMessage('assistant', data.transcript);
            }
            break;
            
        case 'response.audio.delta':
            playAudioData(data.delta);
            break;
            
        case 'error':
            addLog('error', '服务器错误', data.error);
            addMessage('error', '错误: ' + (data.error?.message || 'Unknown error'));
            break;
            
        case 'response.done':
            if (data.response?.usage) {
                addLog('info', '使用统计', data.response.usage);
            }
            break;
    }
}

// ==================== 音频处理 ====================

async function startAudioInput() {
    try {
        addLog('info', '正在启动音频输入...');
        
        const stream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true
            }
        });
        
        state.localStream = stream;
        
        state.audioContext = new AudioContext({ sampleRate: 16000 });
        state.audioInput = state.audioContext.createMediaStreamSource(stream);
        
        // 创建音频处理节点
        await state.audioContext.audioWorklet.addModule(URL.createObjectURL(new Blob([`
            class AudioProcessor extends AudioWorkletProcessor {
                process(inputs, outputs, parameters) {
                    const input = inputs[0];
                    if (input && input[0]) {
                        const samples = input[0];
                        // 转换为16位PCM
                        const pcmData = new Int16Array(samples.length);
                        for (let i = 0; i < samples.length; i++) {
                            pcmData[i] = Math.max(-1, Math.min(1, samples[i])) * 0x7FFF;
                        }
                        this.port.postMessage(pcmData.buffer, [pcmData.buffer]);
                    }
                    return true;
                }
            }
            registerProcessor('audio-processor', AudioProcessor);
        `], { type: 'application/javascript' })));
        
        state.audioWorklet = new AudioWorkletNode(state.audioContext, 'audio-processor');
        state.audioWorklet.port.onmessage = (e) => {
            if (state.micMuted || !state.isConnected) return;
            
            const pcmData = new Int16Array(e.data);
            const base64Audio = arrayBufferToBase64(pcmData.buffer);
            
            sendWsMessage({
                type: 'input_audio_buffer.append',
                audio: base64Audio
            });
            
            state.audioBytesSent += pcmData.length * 2;
        };
        
        state.audioInput.connect(state.audioWorklet);
        
        elements.localStatus.classList.add('active');
        elements.localInfo.textContent = '麦克风已启用';
        addLog('success', '音频输入已启动');
        
    } catch (error) {
        addLog('error', '启动音频失败', error.message);
    }
}

function stopAudioInput() {
    if (state.audioWorklet) {
        state.audioWorklet.disconnect();
        state.audioWorklet = null;
    }
    if (state.audioInput) {
        state.audioInput.disconnect();
        state.audioInput = null;
    }
    if (state.audioContext) {
        state.audioContext.close();
        state.audioContext = null;
    }
    if (state.localStream) {
        state.localStream.getAudioTracks().forEach(track => track.stop());
    }
    elements.localStatus.classList.remove('active');
}

// ==================== 视频处理 ====================

async function startVideoInput() {
    try {
        addLog('info', '正在启动视频输入...');
        
        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 640 },
                height: { ideal: 480 },
                frameRate: { ideal: 5 }
            },
            audio: false
        });
        
        if (!state.localStream) {
            state.localStream = stream;
        } else {
            stream.getVideoTracks().forEach(track => {
                state.localStream.addTrack(track);
            });
        }
        
        elements.localVideo.srcObject = state.localStream;
        elements.localVideo.classList.remove('hidden');
        elements.localPlaceholder.classList.add('hidden');
        elements.localStatus.classList.add('active');
        
        // 开始视频帧发送
        state.videoInterval = setInterval(captureAndSendFrame, 200); // 5fps
        
        addLog('success', '视频输入已启动');
        
    } catch (error) {
        addLog('error', '启动视频失败', error.message);
    }
}

function stopVideoInput() {
    if (state.videoInterval) {
        clearInterval(state.videoInterval);
        state.videoInterval = null;
    }
    if (state.localStream) {
        state.localStream.getVideoTracks().forEach(track => track.stop());
    }
    elements.localVideo.classList.add('hidden');
    elements.localPlaceholder.classList.remove('hidden');
}

function captureAndSendFrame() {
    if (!state.isConnected || !state.localStream) return;
    
    const video = elements.localVideo;
    const canvas = elements.videoCanvas;
    const ctx = canvas.getContext('2d');
    
    canvas.width = 640;
    canvas.height = 480;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    const frameData = canvas.toDataURL('image/jpeg', 0.7);
    const base64Frame = frameData.split(',')[1];
    
    sendWsMessage({
        type: 'input_video_frame.append',
        video_frame: base64Frame
    });
    
    state.frameCount++;
}

// ==================== 音频播放 ====================

const audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
let audioQueue = [];
let isPlaying = false;

function playAudioData(base64Data) {
    const arrayBuffer = base64ToArrayBuffer(base64Data);
    audioQueue.push(arrayBuffer);
    
    if (!isPlaying) {
        playNextAudio();
    }
}

async function playNextAudio() {
    if (audioQueue.length === 0) {
        isPlaying = false;
        return;
    }
    
    isPlaying = true;
    const buffer = audioQueue.shift();
    
    try {
        const audioBuffer = await audioContext.decodeAudioData(buffer);
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        source.onended = playNextAudio;
        source.start();
    } catch (error) {
        addLog('error', '音频播放失败', error.message);
        playNextAudio();
    }
}

// ==================== UI 交互 ====================

function addMessage(role, content) {
    const messageEl = document.createElement('div');
    messageEl.className = `message ${role}`;
    
    const roleLabels = {
        user: '👤 你',
        assistant: '🤖 AI',
        system: '⚙️ 系统',
        error: '❌ 错误'
    };
    
    messageEl.innerHTML = `
        <div class="message-role">${roleLabels[role] || role}</div>
        <div class="message-content">${escapeHtml(content)}</div>
    `;
    
    elements.chatMessages.appendChild(messageEl);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

function base64ToArrayBuffer(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
}

// ==================== 配置加载 ====================

async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const config = await response.json();
        
        if (config.api_key) {
            elements.apiKey.value = config.api_key;
            addLog('info', '已从配置文件加载 API Key');
        }
        
        if (config.model && elements.model) {
            elements.model.value = config.model;
        }
        
    } catch (error) {
        addLog('warn', '无法加载配置，请手动输入 API Key');
    }
}

// ==================== 事件绑定 ====================

elements.connectBtn.addEventListener('click', () => {
    if (state.isConnected) {
        disconnect();
    } else {
        connectWebSocket();
    }
});

elements.sendBtn.addEventListener('click', () => {
    const text = elements.textInput.value.trim();
    if (!text) return;
    
    sendWsMessage({
        type: 'conversation.item.create',
        item: {
            type: 'message',
            role: 'user',
            content: [{ type: 'input_text', text: text }]
        }
    });
    
    sendWsMessage({ type: 'response.create' });
    
    addMessage('user', text);
    elements.textInput.value = '';
});

elements.textInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        elements.sendBtn.click();
    }
});

elements.micBtn.addEventListener('click', () => {
    state.micMuted = !state.micMuted;
    elements.micIcon.textContent = state.micMuted ? '🔇' : '🎤';
    elements.micText.textContent = state.micMuted ? '已静音' : '麦克风';
    addLog('info', state.micMuted ? '麦克风已静音' : '麦克风已解除静音');
});

elements.cameraBtn.addEventListener('click', async () => {
    state.videoEnabled = !state.videoEnabled;
    
    if (state.videoEnabled) {
        await startVideoInput();
        elements.cameraIcon.textContent = '📹';
        elements.cameraText.textContent = '关闭摄像头';
    } else {
        stopVideoInput();
        elements.cameraIcon.textContent = '📹';
        elements.cameraText.textContent = '摄像头';
    }
});

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    addLog('info', '页面已加载，等待连接...');
    
    // 加载配置
    loadConfig();
    
    // 检查浏览器支持
    if (!navigator.mediaDevices) {
        addLog('error', '浏览器不支持 getUserMedia');
        alert('您的浏览器不支持音视频功能，请使用 Chrome 或 Edge 浏览器');
    }
});
