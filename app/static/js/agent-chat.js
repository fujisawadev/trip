/**
 * 新しいエージェントチャット機能
 * 
 * Step 0 & Step 1の機能を統合したフロントエンドです。
 * クイックプロンプト、安全なチャット、追い質問機能を提供します。
 */

class AgentChat {
    constructor(containerId, options = {}) {
        this.chatHistoryEl = document.getElementById(containerId);
        if (!this.chatHistoryEl) {
            console.error(`AgentChat: Container element '${containerId}' not found`);
            return;
        }
        
        this.options = {
            contextType: options.contextType || 'general',
            influencerId: options.influencerId || null,
            spotId: options.spotId || null,
            apiBaseUrl: '/api/agents',
            apiVersion: options.apiVersion || 'v1',
            ...options
        };
        
        this.sessionId = null;
        this.isLoading = false;
        this.messageHistory = [];
        
        // 既存のモーダル要素を取得
        this.modal = document.getElementById('ai-assistant-modal');
        this.modalOverlay = document.getElementById('ai-assistant-modal-overlay');
        this.footerInput = document.getElementById('footer-user-input');
        this.footerSendButton = document.getElementById('footer-send-message');
        this.modalInput = document.getElementById('modal-user-input');
        this.modalSendButton = document.getElementById('modal-send-message');
        
        this.init();
    }
    
    init() {
        this.loadQuickPrompts();
        this.bindEvents();
        this.setupModalTriggers();
    }
    
    setupModalTriggers() {
        // フッターの入力フィールドとボタンにイベントを設定
        if (this.footerInput) {
            this.footerInput.addEventListener('focus', () => this.openModal());
            // フッターでのEnterキー処理を無効化（フォーカス時にモーダルが開くので不要）
            this.footerInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    // Enterキーでは何もしない（フォーカス時に既にモーダルが開いている）
                }
            });
        }
        
        if (this.footerSendButton) {
            this.footerSendButton.addEventListener('click', () => this.openModal());
        }
        
        // モーダルを閉じるイベント
        if (this.modalOverlay) {
            this.modalOverlay.addEventListener('click', () => this.closeModal());
        }
        
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => this.closeModal());
        });
        
        // クイックプロンプトのイベントは動的に設定（renderQuickPrompts内で）
    }
    
    openModal() {
        if (this.modal && this.modalOverlay) {
            this.modalOverlay.classList.remove('hidden');
            this.modal.classList.add('show');
            document.body.style.overflow = 'hidden';
            
            // 初回開いた時にデフォルトメッセージを表示
            this.showDefaultMessageIfEmpty();
        }
    }
    
    closeModal() {
        if (this.modal && this.modalOverlay) {
            this.modal.classList.remove('show');
            setTimeout(() => {
                this.modalOverlay.classList.add('hidden');
                document.body.style.overflow = '';
            }, 300);
        }
    }
    
    async loadQuickPrompts() {
        try {
            const response = await fetch(`/api/v3/agents/quick-prompts`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    context_type: this.options.contextType,
                    influencer_id: this.options.influencerId,
                    spot_id: this.options.spotId
                })
            });
            
            const data = await response.json();
            
            if (data.success && data.prompts) {
                this.renderQuickPrompts(data.prompts);
            } else {
                this.showPromptsError();
            }
        } catch (error) {
            console.error('Quick prompts loading error:', error);
            this.showPromptsError();
        }
    }
    
    renderQuickPrompts(prompts) {
        // フッター部分のクイックプロンプトを更新
        const footerContainer = document.getElementById('agent-quick-prompts');
        // モーダル内のクイックプロンプトを更新
        const modalContainer = document.getElementById('modal-agent-quick-prompts');
        
        if (prompts.length === 0) {
            const noPromptsHtml = '<div class="text-gray-500 text-sm">現在利用できる質問候補がありません</div>';
            if (footerContainer) footerContainer.innerHTML = noPromptsHtml;
            if (modalContainer) modalContainer.innerHTML = noPromptsHtml;
            return;
        }
        
        const promptsHtml = prompts.map(prompt => `
            <button class="quick-prompt-btn flex-shrink-0" data-prompt="${prompt.text}">
                ${prompt.text}
            </button>
        `).join('');
        
        if (footerContainer) {
            footerContainer.innerHTML = promptsHtml;
            // フッタークイックプロンプトのイベント設定
            footerContainer.querySelectorAll('.quick-prompt-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const prompt = btn.dataset.prompt;
                    this.openModal();
                    setTimeout(() => {
                        this.sendMessage(prompt);
                    }, 100);
                });
            });
        }
        
        if (modalContainer) {
            modalContainer.innerHTML = `<div class="agent-quick-prompts-container">${promptsHtml}</div>`;
            // モーダルクイックプロンプトのイベント設定
            modalContainer.querySelectorAll('.quick-prompt-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const prompt = btn.dataset.prompt;
                    this.sendMessage(prompt);
                });
            });
        }
    }
    
    showPromptsError() {
        const errorHtml = '<div class="text-red-500 text-sm">質問候補の読み込みに失敗しました</div>';
        const footerContainer = document.getElementById('agent-quick-prompts');
        const modalContainer = document.getElementById('modal-agent-quick-prompts');
        
        if (footerContainer) footerContainer.innerHTML = errorHtml;
        if (modalContainer) modalContainer.innerHTML = errorHtml;
    }
    
    bindEvents() {
        // モーダル内のメッセージ入力イベント
        if (this.modalInput && this.modalSendButton) {
            // Enterキーでの送信を無効化（改行のみ許可）
            this.modalInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    // Enterキーでは送信しない（改行を挿入）
                    const cursorPos = this.modalInput.selectionStart;
                    const textBefore = this.modalInput.value.substring(0, cursorPos);
                    const textAfter = this.modalInput.value.substring(this.modalInput.selectionEnd);
                    this.modalInput.value = textBefore + '\n' + textAfter;
                    this.modalInput.selectionStart = this.modalInput.selectionEnd = cursorPos + 1;
                }
            });
            
            // 送信ボタンクリック時のみ送信
            this.modalSendButton.addEventListener('click', () => {
                if (this.modalInput.value.trim() && !this.isLoading) {
                    this.sendMessage(this.modalInput.value.trim());
                }
            });
        }
    }
    
    async sendMessage(message) {
        if (this.isLoading) return;
        
        console.log('[AgentChat] sendMessage started with message:', message);
        
        this.isLoading = true;
        this.updateLoadingState(true);
        
        // デフォルトメッセージを削除
        this.removeDefaultMessage();
        
        // ユーザーメッセージを追加
        await this.addMessage('user', message);
        
        // 入力をクリア
        if (this.modalInput) {
            this.modalInput.value = '';
        }
        
        // ローディング表示
        this.showLoadingMessage();
        
        // 履歴に追加
        this.messageHistory.push({
            type: 'user',
            content: message,
            timestamp: new Date().toISOString()
        });
        
        try {
            // v3エンドポイントを使用
            const response = await fetch('/api/v3/agents/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    // 'X-CSRF-TOKEN': this.getCSRFToken()
                },
                body: JSON.stringify({
                    message: message,
                    context_type: this.options.contextType,
                    influencer_id: this.options.influencerId,
                    spot_id: this.options.spotId,
                    session_id: this.sessionId || this._generateSessionId(),
                    user_id: this.options.influencerId 
                })
            });
            
            this.hideLoadingMessage();
            const data = await response.json();
            console.log('[AgentChat] Received response from backend:', data);
            
            if (data.success && data.response) {
                this.messageHistory.push({ type: 'assistant', content: data.response, timestamp: new Date().toISOString() });
                await this.addMessage('assistant', data.response);
            } else {
                await this.addMessage('assistant', data.error || '予期せぬエラーが発生しました。', { isError: true });
            }
        } catch (error) {
            console.error('[AgentChat] Send message error:', error);
            this.hideLoadingMessage();
            await this.addMessage('assistant', '通信中にエラーが発生しました。', { isError: true });
        } finally {
            this.isLoading = false;
            this.updateLoadingState(false);
        }
    }
    
    _generateSessionId() {
        if (this.sessionId) return this.sessionId;
        this.sessionId = `session_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
        return this.sessionId;
    }
    
    async addMessage(type, content, options = {}) {
        console.log(`[AgentChat] addMessage called for type: ${type}`, { content, options });

        if (!this.chatHistoryEl) return;

        // メッセージコンテナを作成
        const messageElement = document.createElement('div');
        messageElement.className = `message ${type} ${options.isError ? 'error' : ''}`;

        // メッセージ内容のフォーマットと設定
        try {
            if (type === 'assistant' && !options.isError) {
                console.log('[AgentChat] Formatting assistant message...');
                const formattedContent = await this.formatMessage(content);
                console.log('[AgentChat] Successfully formatted message. HTML:', formattedContent);
                messageElement.innerHTML = formattedContent;
            } else {
                // ユーザーメッセージとエラーメッセージはテキストとして表示
                messageElement.textContent = content;
            }
        } catch (e) {
            console.error('[AgentChat] Error formatting message, falling back to text:', e);
            messageElement.textContent = content; // エラー時はフォールバック
        }
        
        this.chatHistoryEl.appendChild(messageElement);
        this.chatHistoryEl.scrollTop = this.chatHistoryEl.scrollHeight;
    }
    
    async formatMessage(content) {
        console.log('[AgentChat] formatMessage started with content:', content);

        // テキストをMarkdownとしてパース
        let htmlContent = marked.parse(content);
        
        // 相対パスを絶対パスのリンクに変換
        // 例: /username/spot_id -> <a href="/username/spot_id">/username/spot_id</a>
        // ただし、//で始まるプロトコル相対URLは除外
        htmlContent = htmlContent.replace(/(\s|>|^)(\/[a-zA-Z0-9_.\-\/]+)/g, (match, prefix, path) => {
            // すでにリンクの一部である場合は変換しない
            if (prefix.toLowerCase().endsWith('href="')) {
                return match;
            }
            return `${prefix}<a href="${path}">${path}</a>`;
        });
        
        console.log('[AgentChat] Finished message formatting. Final HTML:', htmlContent);
        return htmlContent;
    }
    
    updateLoadingState(isLoading) {
        const sendButton = this.modalSendButton;
        // 送信ボタンを非アクティブにする（テキストは変更しない）
        if (sendButton) {
            sendButton.disabled = isLoading;
            // ボタンの見た目を非アクティブに
            if (isLoading) {
                sendButton.style.opacity = '0.5';
                sendButton.style.cursor = 'not-allowed';
            } else {
                sendButton.style.opacity = '1';
                sendButton.style.cursor = 'pointer';
            }
        }
        
        // 入力フィールドも非アクティブに
        if (this.modalInput) {
            this.modalInput.disabled = isLoading;
        }
        
        // ローディング終了時のみローディングUIを非表示
        if (!isLoading) {
            this.hideLoadingMessage();
        }
    }
    
    showLoadingMessage() {
        // 既存のローディングメッセージがあれば削除
        this.hideLoadingMessage();
        
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'agent-loading';
        loadingDiv.id = 'agent-loading-message';
        
        loadingDiv.innerHTML = `
            <div class="agent-loading-content">
                <div class="loading-text">少々お待ちください...</div>
                <div class="skeleton-lines">
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line"></div>
                </div>
            </div>
        `;
        
        if (this.chatHistoryEl) {
            this.chatHistoryEl.appendChild(loadingDiv);
            // スクロールを最下部に
            this.chatHistoryEl.scrollTop = this.chatHistoryEl.scrollHeight;
        } else {
            console.error('Chat container not found for loading message');
        }
        
        // アニメーション効果
        loadingDiv.style.opacity = '0';
        loadingDiv.style.transform = 'translateY(10px)';
        setTimeout(() => {
            loadingDiv.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            loadingDiv.style.opacity = '1';
            loadingDiv.style.transform = 'translateY(0)';
        }, 50);
    }
    
    hideLoadingMessage() {
        const loadingMessage = document.getElementById('agent-loading-message');
        if (loadingMessage) {
            loadingMessage.remove();
        }
    }
    
    showDefaultMessageIfEmpty() {
        if (!this.chatHistoryEl) return;
        
        // 既にメッセージがある場合は何もしない
        if (this.chatHistoryEl.children.length > 0) return;
        
        // デフォルトメッセージを表示
        const defaultMessageDiv = document.createElement('div');
        defaultMessageDiv.className = 'flex justify-start mb-4';
        defaultMessageDiv.id = 'default-welcome-message';
        
        defaultMessageDiv.innerHTML = `
            <div class="max-w-[80%] px-4 py-3 rounded-2xl bg-gray-100 text-gray-800 rounded-bl-md">
                <div style="word-wrap: break-word; line-height: 1.5;">
                    どのようなご相談でしょうか？
                </div>
            </div>
        `;
        
        this.chatHistoryEl.appendChild(defaultMessageDiv);
        
        // アニメーション効果
        defaultMessageDiv.style.opacity = '0';
        defaultMessageDiv.style.transform = 'translateY(10px)';
        setTimeout(() => {
            defaultMessageDiv.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            defaultMessageDiv.style.opacity = '1';
            defaultMessageDiv.style.transform = 'translateY(0)';
        }, 100);
    }
    
    removeDefaultMessage() {
        const defaultMessage = document.getElementById('default-welcome-message');
        if (defaultMessage) {
            defaultMessage.remove();
        }
    }
    
    // 外部から呼び出し可能なメソッド
    clearHistory() {
        if (this.chatHistoryEl) {
            this.chatHistoryEl.innerHTML = '';
        }
        this.messageHistory = [];
        this.sessionId = null;
    }
    
    getHistory() {
        return this.messageHistory;
    }
}

// グローバルに公開
window.AgentChat = AgentChat; 