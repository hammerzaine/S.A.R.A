"""S.A.R.A Web UI — Built-in web interface for chatting with your agent.

This module provides a simple web interface that can be accessed from any browser.
It uses FastAPI and serves a single-page application.
"""

from __future__ import annotations

import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Add the parent directory to the path so we can import hermes modules
sys.path.insert(0, str(Path(__file__).parent.parent))


# Update checker
import subprocess
import time
import threading

_update_available = False
_update_info = ""
_update_check_interval = 120  # 2 minutes

def check_for_updates():
    """Check if a new version is available on the remote."""
    global _update_available, _update_info
    try:
        # Fetch latest from remote
        subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True,
            timeout=30,
            cwd=SARA_ROOT
        )
        
        # Compare local and remote
        local = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=SARA_ROOT
        ).stdout.strip()
        
        remote = subprocess.run(
            ["git", "rev-parse", "origin/master"],
            capture_output=True,
            text=True,
            cwd=SARA_ROOT
        ).stdout.strip()
        
        if local != remote:
            _update_available = True
            _update_info = "New version available!"
        else:
            _update_available = False
            _update_info = ""
    except Exception as e:
        _update_available = False
        _update_info = ""

def update_checker_loop():
    """Background thread that checks for updates periodically."""
    while True:
        check_for_updates()
        time.sleep(_update_check_interval)

# Start the update checker thread
update_thread = threading.Thread(target=update_checker_loop, daemon=True)
update_thread.start()


app = FastAPI(title="S.A.R.A Agent", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTML for the web UI
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>S.A.R.A — Smart AI Resource Assistant</title>
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-tertiary: #1a1a2e;
            --text-primary: #e0e0e0;
            --text-secondary: #a0a0a0;
            --accent-cyan: #38BDF8;
            --accent-blue: #4B9FFF;
            --accent-green: #4ADE80;
            --accent-red: #F87171;
            --accent-amber: #FBBF24;
            --accent-violet: #A78BFA;
            --accent-gold: #FCD34D;
            --border-color: #2a2a3e;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        

        .update-banner {
            display: none;
            background: var(--accent-red);
            color: white;
            padding: 0.5rem 1rem;
            text-align: center;
            font-size: 0.875rem;
            font-weight: 600;
            cursor: pointer;
            animation: pulse 2s infinite;
        }
        
        .update-banner.active {
            display: block;
        }
        
        .update-banner:hover {
            background: #dc2626;
        }
        
        .header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 1rem 1.5rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        
        .logo-icon {
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            color: white;
            font-size: 1.2rem;
        }
        
        .logo-text h1 {
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--accent-cyan);
        }
        
        .logo-text p {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }
        
        .provider-selector {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .provider-selector select {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 0.5rem 0.75rem;
            color: var(--text-primary);
            font-size: 0.875rem;
            cursor: pointer;
        }
        
        .provider-selector select:focus {
            border-color: var(--accent-cyan);
        }
        
        .status {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent-green);
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        
        .message {
            max-width: 80%;
            padding: 1rem;
            border-radius: 12px;
            line-height: 1.6;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message.user {
            align-self: flex-end;
            background: var(--accent-blue);
            color: white;
            border-bottom-right-radius: 4px;
        }
        
        .message.assistant {
            align-self: flex-start;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-bottom-left-radius: 4px;
        }
        
        .message.assistant .sender {
            color: var(--accent-cyan);
            font-weight: 600;
            margin-bottom: 0.5rem;
            font-size: 0.875rem;
        }
        
        .message.system {
            align-self: center;
            background: transparent;
            color: var(--text-secondary);
            font-size: 0.875rem;
            font-style: italic;
        }
        
        .input-container {
            background: var(--bg-secondary);
            border-top: 1px solid var(--border-color);
            padding: 1rem 1.5rem;
            display: flex;
            gap: 0.75rem;
        }
        
        .input-container input {
            flex: 1;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            color: var(--text-primary);
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s;
        }
        
        .input-container input:focus {
            border-color: var(--accent-cyan);
        }
        
        .input-container button {
            background: var(--accent-cyan);
            border: none;
            border-radius: 8px;
            padding: 0.75rem 1.5rem;
            color: white;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .input-container button:hover {
            background: var(--accent-blue);
        }
        
        .input-container button:disabled {
            background: var(--text-secondary);
            cursor: not-allowed;
        }
        
        .typing-indicator {
            display: none;
            align-self: flex-start;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1rem;
            border-bottom-left-radius: 4px;
        }
        
        .typing-indicator.active {
            display: block;
        }
        
        .typing-indicator span {
            display: inline-block;
            width: 8px;
            height: 8px;
            background: var(--accent-cyan);
            border-radius: 50%;
            margin: 0 2px;
            animation: typing 1.4s infinite;
        }
        
        .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
        .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
        
        @keyframes typing {
            0%, 60%, 100% { transform: translateY(0); }
            30% { transform: translateY(-10px); }
        }
        
        .welcome {
            text-align: center;
            padding: 2rem;
            color: var(--text-secondary);
        }
        
        .welcome h2 {
            color: var(--accent-cyan);
            margin-bottom: 0.5rem;
        }
        
        .welcome p {
            font-size: 0.875rem;
        }
        
        .credentials-panel {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }
        
        .credentials-panel.active {
            display: flex;
        }
        
        .credentials-modal {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }
        
        .credentials-modal h2 {
            color: var(--accent-cyan);
            margin-bottom: 1rem;
        }
        
        .credential-section {
            margin-bottom: 1.5rem;
        }
        
        .credential-section h3 {
            color: var(--text-primary);
            margin-bottom: 0.5rem;
            font-size: 1rem;
        }
        
        .credential-input {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 0.5rem;
        }
        
        .credential-input input {
            flex: 1;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 0.5rem 0.75rem;
            color: var(--text-primary);
            font-size: 0.875rem;
        }
        
        .credential-input button {
            background: var(--accent-cyan);
            border: none;
            border-radius: 6px;
            padding: 0.5rem 1rem;
            color: white;
            cursor: pointer;
            font-size: 0.875rem;
        }
        
        .credential-input button:hover {
            background: var(--accent-blue);
        }
        
        .credential-list {
            margin-top: 0.5rem;
        }
        
        .credential-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.5rem;
            background: var(--bg-tertiary);
            border-radius: 6px;
            margin-bottom: 0.25rem;
            font-size: 0.875rem;
        }
        
        .credential-item .label {
            flex: 1;
        }
        
        .credential-item .status {
            margin: 0 0.5rem;
        }
        
        .credential-item .status.active {
            color: var(--accent-green);
        }
        
        .credential-item .status.exhausted {
            color: var(--accent-amber);
        }
        
        .credential-item .status.dead {
            color: var(--accent-red);
        }
        
        .credential-item button {
            background: transparent;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 0.25rem 0.5rem;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 0.75rem;
        }
        
        .credential-item button:hover {
            border-color: var(--accent-red);
            color: var(--accent-red);
        }
        
        .close-modal {
            background: transparent;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 0.5rem 1rem;
            color: var(--text-secondary);
            cursor: pointer;
            margin-top: 1rem;
        }
        
        .close-modal:hover {
            border-color: var(--accent-cyan);
            color: var(--accent-cyan);
        }
        
        .settings-btn {
            background: transparent;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 0.5rem 0.75rem;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 0.875rem;
        }
        
        .settings-btn:hover {
            border-color: var(--accent-cyan);
            color: var(--accent-cyan);
        }
    </style>
</head>
<body>
    <div class="update-banner" id="updateBanner" onclick="checkUpdate()">
        <span id="updateMessage">New version available!</span>
    </div>
    
    <div class="header">
        <div class="logo">
            <div class="logo-icon">S</div>
            <div class="logo-text">
                <h1>S.A.R.A</h1>
                <p>Smart AI Resource Assistant</p>
            </div>
        </div>
        <div class="status">
            <div class="provider-selector">
                <select id="providerSelect" onchange="switchProvider()">
                    <option value="ollama">Ollama (Local)</option>
                    <option value="openai">OpenAI (ChatGPT)</option>
                    <option value="gemini">Google Gemini</option>
                    <option value="copilot">GitHub Copilot</option>
                    <option value="anthropic">Anthropic (Claude)</option>
                    <option value="openrouter">OpenRouter</option>
                    <option value="groq">Groq</option>
                    <option value="mistral">Mistral AI</option>
                    <option value="deepseek">DeepSeek</option>
                    <option value="xai">xAI (Grok)</option>
                    <option value="together">Together AI</option>
                    <option value="fireworks">Fireworks AI</option>
                    <option value="perplexity">Perplexity</option>
                    <option value="opencodezen">OpenCode Zen</option>
                    <option value="kimi">Kimi / Moonshot</option>
                    <option value="minimax">MiniMax</option>
                    <option value="zai">Z.AI / GLM</option>
                    <option value="nous">Nous Research (Hermes)</option>
                </select>
            </div>
            <button class="settings-btn" onclick="showSkills()">📚 Skills</button>
            <button class="settings-btn" onclick="showTools()">🔧 Tools</button>
            <button class="settings-btn" onclick="openCredentials()">⚙ Settings</button>
            <div class="status-dot"></div>
            <span>Online</span>
        </div>
    </div>
    
    <div class="chat-container" id="chat">
        <div class="welcome">
            <h2>Welcome to S.A.R.A</h2>
            <p>Your Smart AI Resource Assistant is ready to help.</p>
        </div>
    </div>
    
    <div class="typing-indicator" id="typing">
        <span></span>
        <span></span>
        <span></span>
    </div>
    
    <div class="input-container">
        <input type="text" id="messageInput" placeholder="Type your message..." autocomplete="off">
        <button id="sendBtn" onclick="sendMessage()">Send</button>
    </div>
    
    <div class="credentials-panel" id="credentialsPanel">
        <div class="credentials-modal">
            <h2>Credentials</h2>
            <div id="credentialsContent">
                <p>Loading...</p>
            </div>
            <button class="close-modal" onclick="closeCredentials()">Close</button>
        </div>
    </div>
    

    <div class="credentials-panel" id="skillsPanel">
        <div class="credentials-modal">
            <h2>Learned Skills</h2>
            <div id="skillsContent">
                <p>Loading...</p>
            </div>
            <button class="close-modal" onclick="closeSkills()">Close</button>
        </div>
    </div>
    
    <div class="credentials-panel" id="toolsPanel">
        <div class="credentials-modal">
            <h2>Available Tools</h2>
            <div id="toolsContent">
                <p>Loading...</p>
            </div>
            <button class="close-modal" onclick="closeTools()">Close</button>
        </div>
    </div>
    
    <script>
        const chat = document.getElementById('chat');
        const messageInput = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');
        const typing = document.getElementById('typing');
        
        let ws = null;
        let isConnected = false;
        
        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
            
            ws.onopen = () => {
                isConnected = true;
                console.log('Connected to S.A.R.A');
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'response') {
                    typing.classList.remove('active');
                    addMessage(data.message, 'assistant');
                    sendBtn.disabled = false;
                } else if (data.type === 'typing') {
                    typing.classList.add('active');
                } else if (data.type === 'system') {
                    addMessage(data.message, 'system');
                } else if (data.type === 'error') {
                    typing.classList.remove('active');
                    addMessage('Error: ' + data.message, 'system');
                    sendBtn.disabled = false;
                }
            };
            
            ws.onclose = () => {
                isConnected = false;
                console.log('Disconnected from S.A.R.A');
                setTimeout(connect, 3000);
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }
        
        function addMessage(text, sender) {
            const welcome = chat.querySelector('.welcome');
            if (welcome) welcome.remove();
            
            const div = document.createElement('div');
            div.className = `message ${sender}`;
            
            if (sender === 'assistant') {
                div.innerHTML = `<div class="sender">S.A.R.A</div>${escapeHtml(text)}`;
            } else {
                div.textContent = text;
            }
            
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function sendMessage() {
            const text = messageInput.value.trim();
            if (!text || !isConnected) return;
            
            addMessage(text, 'user');
            messageInput.value = '';
            typing.classList.add('active');
            sendBtn.disabled = true;
            
            ws.send(JSON.stringify({ message: text, provider: document.getElementById('providerSelect').value }));
        }
        
        function switchProvider() {
            const provider = document.getElementById('providerSelect').value;
            addMessage('Switched to ' + provider, 'system');
        }
        

        function showSkills() {
            document.getElementById('skillsPanel').classList.add('active');
            loadSkills();
        }
        
        function closeSkills() {
            document.getElementById('skillsPanel').classList.remove('active');
        }
        
        async function loadSkills() {
            const content = document.getElementById('skillsContent');
            try {
                const resp = await fetch('/api/skills');
                const data = await resp.json();
                
                let html = `<p>Total skills: ${data.count}</p>`;
                html += '<div class="credential-list">';
                
                for (const skill of data.skills || []) {
                    html += `<div class="credential-item">`;
                    html += `<span class="label">${skill.name}</span>`;
                    html += `<span style="color: var(--text-secondary); font-size: 0.75rem;">${skill.category || ''}</span>`;
                    html += `</div>`;
                }
                
                html += '</div>';
                content.innerHTML = html || '<p>No skills found.</p>';
            } catch (e) {
                content.innerHTML = `<p>Error loading skills: ${e.message}</p>`;
            }
        }
        
        function showTools() {
            document.getElementById('toolsPanel').classList.add('active');
            loadTools();
        }
        
        function closeTools() {
            document.getElementById('toolsPanel').classList.remove('active');
        }
        
        async function loadTools() {
            const content = document.getElementById('toolsContent');
            try {
                const resp = await fetch('/api/tools');
                const data = await resp.json();
                
                let html = `<p>Total tools: ${data.count}</p>`;
                html += '<div class="credential-list">';
                
                for (const tool of data.tools || []) {
                    html += `<div class="credential-item">`;
                    html += `<span class="label">${tool.emoji || '⚡'} ${tool.name}</span>`;
                    html += `<span style="color: var(--text-secondary); font-size: 0.75rem;">${tool.toolset || ''}</span>`;
                    html += `</div>`;
                }
                
                html += '</div>';
                content.innerHTML = html || '<p>No tools found.</p>';
            } catch (e) {
                content.innerHTML = `<p>Error loading tools: ${e.message}</p>`;
            }
        }
        

        function checkUpdate() {
            fetch('/api/update-status')
                .then(r => r.json())
                .then(data => {
                    const banner = document.getElementById('updateBanner');
                    const message = document.getElementById('updateMessage');
                    if (data.update_available) {
                        banner.classList.add('active');
                        message.textContent = data.message || 'New version available!';
                    } else {
                        banner.classList.remove('active');
                    }
                })
                .catch(() => {});
        }
        
        // Check for updates every 2 minutes
        setInterval(checkUpdate, 120000);
        // Initial check
        setTimeout(checkUpdate, 2000);
        
        function openCredentials() {
            document.getElementById('credentialsPanel').classList.add('active');
            loadCredentials();
        }
        
        function closeCredentials() {
            document.getElementById('credentialsPanel').classList.remove('active');
        }
        
        async function loadCredentials() {
            const content = document.getElementById('credentialsContent');
            try {
                // Fetch both available providers and configured credentials
                const [providersResp, credsResp] = await Promise.all([
                    fetch('/api/providers'),
                    fetch('/api/credentials')
                ]);
                const providersData = await providersResp.json();
                const credsData = await credsResp.json();
                
                let html = '';
                for (const [provider, info] of Object.entries(providersData.providers || {})) {
                    const status = credsData.providers?.[provider];
                    const entries = status?.entries || [];
                    const authType = info.auth_type;
                    
                    html += `<div class="credential-section">`;
                    html += `<h3>${info.name} (${provider})</h3>`;
                    html += `<p style="color: var(--text-secondary); font-size: 0.75rem; margin-bottom: 0.5rem;">${info.description}</p>`;
                    
                    if (authType === 'api_key') {
                        html += `<div class="credential-input">`;
                        html += `<input type="password" id="key-${provider}" placeholder="Enter API key...">`;
                        html += `<button onclick="addCredential('${provider}')">Add</button>`;
                        html += `</div>`;
                    } else {
                        html += `<p style="color: var(--text-secondary); font-size: 0.75rem;">No API key required.</p>`;
                    }
                    
                    html += `<div class="credential-list">`;
                    
                    for (const entry of entries) {
                        const statusClass = entry.status;
                        const statusIcon = entry.status === 'active' ? '✓' : '✗';
                        html += `<div class="credential-item">`;
                        html += `<span class="label">${entry.label}</span>`;
                        html += `<span class="status ${statusClass}">${statusIcon} ${entry.status}</span>`;
                        html += `<button onclick="removeCredential('${provider}', '${entry.id}')">Remove</button>`;
                        html += `</div>`;
                    }
                    
                    html += `</div></div>`;
                }
                
                content.innerHTML = html || '<p>No providers available.</p>';
            } catch (e) {
                content.innerHTML = `<p>Error loading credentials: ${e.message}</p>`;
            }
        }
        
        async function addCredential(provider) {
            const input = document.getElementById(`key-${provider}`);
            const apiKey = input.value.trim();
            if (!apiKey) return;
            
            try {
                const resp = await fetch(`/api/credentials/${provider}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: apiKey })
                });
                const data = await resp.json();
                if (data.success) {
                    input.value = '';
                    loadCredentials();
                } else {
                    alert(data.error || 'Failed to add credential');
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }
        
        async function removeCredential(provider, entryId) {
            if (!confirm('Remove this credential?')) return;
            
            try {
                const resp = await fetch(`/api/credentials/${provider}/${entryId}`, {
                    method: 'DELETE'
                });
                const data = await resp.json();
                if (data.success) {
                    loadCredentials();
                } else {
                    alert(data.error || 'Failed to remove credential');
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }
        
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
        
        connect();
    </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve the main web UI page."""
    return HTML_TEMPLATE


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time chat with S.A.R.A agent."""
    await websocket.accept()

    # Import the agent bridge
    from agent_bridge import get_agent

    # Get or initialize the agent
    agent = get_agent()

    # Send initialization status
    if not agent.is_ready():
        await websocket.send_json({
            "type": "system",
            "message": "Initializing S.A.R.A agent..."
        })

        # Initialize the agent
        success = agent.initialize()

        if not success:
            await websocket.send_json({
                "type": "error",
                "message": f"Failed to initialize agent: {agent._init_error}"
            })
            return

        await websocket.send_json({
            "type": "system",
            "message": "S.A.R.A agent ready!"
        })

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            user_message = message.get("message", "").strip()
            provider_name = message.get("provider", "ollama")
            if not user_message:
                continue

            # Switch provider if requested
            if provider_name != agent._active_provider:
                if not agent.set_provider(provider_name):
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Failed to switch to provider: {provider_name}"
                    })
                    continue

            # Send typing indicator
            await websocket.send_json({
                "type": "typing",
                "message": "S.A.R.A is thinking..."
            })

            # Process the message through the agent
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: agent.chat(user_message)
            )

            # Send the response
            await websocket.send_json({
                "type": "response",
                "message": response
            })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except Exception:
            pass


@app.get("/api/credentials")
async def get_credentials():
    """Get all configured credentials."""
    from sara_auth_store import list_credentials
    return list_credentials()


@app.post("/api/credentials/{provider}")
async def add_credential(provider: str, request: Request):
    """Add a credential for a provider."""
    from sara_auth_store import add_credential as store_add

    data = await request.json()
    api_key = data.get("api_key", "")
    label = data.get("label", "")

    if not api_key:
        return {"error": "API key is required"}

    try:
        entry = store_add(provider, api_key, label)
        return {"success": True, "id": entry.id, "label": entry.label}
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/credentials/{provider}/{entry_id}")
async def delete_credential(provider: str, entry_id: str):
    """Remove a credential."""
    from sara_auth_store import remove_credential as store_remove

    if store_remove(provider, entry_id):
        return {"success": True}
    return {"error": "Credential not found"}


@app.post("/api/credentials/test/{provider}")
async def test_credential(provider: str):
    """Test a provider connection."""
    from sara_auth_store import get_auth_store
    from agent_bridge import PROVIDERS as BRIDGE_PROVIDERS

    if provider not in BRIDGE_PROVIDERS:
        return {"error": "Unknown provider"}

    store = get_auth_store()
    cred = store.get_credential(provider)
    if not cred:
        return {"error": "No credential configured"}

    provider_class = BRIDGE_PROVIDERS[provider]
    config = {"api_key": cred.api_key}

    instance = provider_class(config)
    if instance.initialize():
        return {"success": True, "message": "Connection successful"}
    return {"error": instance._init_error}


@app.get("/api/providers")
async def get_providers():
    """Get all available providers."""
    from sara_auth_store import PROVIDERS
    return {
        "providers": {
            key: {
                "name": val["name"],
                "description": val["description"],
                "auth_type": val["auth_type"],
            }
            for key, val in PROVIDERS.items()
        }
    }



@app.get("/api/skills")
async def get_skills():
    """Get all learned skills."""
    try:
        from tools.skills_tool import _find_all_skills
        skills = _find_all_skills()
        return {
            "count": len(skills),
            "skills": [
                {
                    "name": s.get("name", ""),
                    "description": s.get("description", ""),
                    "category": s.get("category", ""),
                }
                for s in skills
            ]
        }
    except Exception as e:
        return {"error": str(e), "count": 0, "skills": []}


@app.get("/api/tools")
async def get_tools():
    """Get all available tools."""
    try:
        from tools.registry import registry
        tool_names = registry.get_all_tool_names()
        return {
            "count": len(tool_names),
            "tools": [
                {
                    "name": name,
                    "toolset": registry.get_toolset_for_tool(name) or "unknown",
                    "emoji": registry.get_emoji(name, "⚡"),
                }
                for name in tool_names
            ]
        }
    except Exception as e:
        return {"error": str(e), "count": 0, "tools": []}


@app.get("/api/update-status")
async def get_update_status():
    """Check if an update is available."""
    return {
        "update_available": _update_available,
        "message": _update_info,
        "check_interval": _update_check_interval
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "agent": "S.A.R.A", "version": "1.0.0"}


@app.get("/api/status")
async def get_status():
    """Get agent status."""
    return {
        "agent": "S.A.R.A",
        "status": "online",
        "model": "unknown",
        "version": "1.0.0"
    }


def start_web_server(host: str = "0.0.0.0", port: int = 8800):
    """Start the web server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_web_server()
