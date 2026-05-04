class ChatApp {
    constructor() {
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.chatMessages = document.getElementById('chatMessages');
        this.isProcessing = false;

        this.init();
    }

    init() {
        this.sendButton.addEventListener('click', () => this.sendMessage());

        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.messageInput.addEventListener('input', () => {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = this.messageInput.scrollHeight + 'px';
        });

        this.messageInput.focus();
    }

    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || this.isProcessing) return;

        this.addUserMessage(message);
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';

        const loadingId = this.addLoadingMessage();
        this.setProcessing(true);

        try {
            const response = await fetch('/api/chat/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            this.removeMessage(loadingId);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const chunks = buffer.split('\n\n');
                buffer = chunks.pop() || '';

                for (const chunk of chunks) {
                    if (!chunk.trim() || chunk.startsWith(':')) continue;

                    const eventMatch = chunk.match(/^event: (.+)\ndata: (.+)$/s);
                    if (!eventMatch) continue;

                    const eventType = eventMatch[1];
                    const data = JSON.parse(eventMatch[2]);

                    if (eventType === 'done' && data.response) {
                        this.addBotMessage(data.response);
                    } else if (eventType === 'error') {
                        this.addBotMessage(`Error: ${data.error}`);
                    }
                }
            }
        } catch (error) {
            this.removeMessage(loadingId);
            this.addBotMessage(`Error: ${error.message}`);
        } finally {
            this.setProcessing(false);
        }
    }

    addUserMessage(text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        messageDiv.innerHTML = `<div class="message-content">${this.escapeHtml(text)}</div>`;
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    addBotMessage(text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot';
        messageDiv.innerHTML = `<div class="message-content">${this.escapeHtml(text)}</div>`;
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    addLoadingMessage() {
        const id = 'loading_' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot loading';
        messageDiv.id = id;
        messageDiv.innerHTML = `
            <div class="message-content">
                <div class="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        `;
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        return id;
    }

    removeMessage(id) {
        const element = document.getElementById(id);
        if (element) {
            element.remove();
        }
    }

    setProcessing(processing) {
        this.isProcessing = processing;
        this.sendButton.disabled = processing;
        this.messageInput.disabled = processing;
    }

    scrollToBottom() {
        requestAnimationFrame(() => {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new ChatApp();
});
