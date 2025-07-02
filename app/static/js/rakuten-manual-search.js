/**
 * 楽天ホテル手動検索機能
 * スポット登録・編集画面でユーザーが「ホテルを検索して選択」ボタンを
 * クリックした際の処理を担当
 */
class RakutenManualSearch {
    constructor() {
        this.modal = null;
        this.isSearching = false;
        this.initializeEventListeners();
        this.createModal();
    }

    /**
     * イベントリスナの初期化
     */
    initializeEventListeners() {
        // ボタンクリックイベント
        document.addEventListener('click', (e) => {
            if (e.target && e.target.id === 'search-rakuten-hotels') {
                e.preventDefault();
                this.handleSearchButtonClick();
            }
        });

        // モーダル外クリックで閉じる
        document.addEventListener('click', (e) => {
            if (e.target && e.target.classList.contains('rakuten-modal-overlay')) {
                this.closeModal();
            }
        });

        // ESCキーでモーダルを閉じる
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal && !this.modal.classList.contains('hidden')) {
                this.closeModal();
            }
        });
    }

    /**
     * モーダルHTML要素を作成
     */
    createModal() {
        const modalHTML = `
            <div id="rakuten-search-modal" class="rakuten-modal-overlay fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center hidden z-[10001]">
                <div class="bg-white rounded-xl p-6 max-w-md w-full mx-4 max-h-[80vh] overflow-y-auto">
                    <div class="flex justify-between items-center mb-4">
                        <h3 class="text-lg font-bold text-neutral-900">ホテルを選択</h3>
                        <button type="button" class="text-gray-400 hover:text-gray-600" onclick="rakutenSearch.closeModal()">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                    
                    <!-- ローディング表示 -->
                    <div id="rakuten-loading" class="text-center py-8 hidden">
                        <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                        <p class="mt-2 text-sm text-gray-600">ホテルを検索中...</p>
                    </div>
                    
                    <!-- エラー表示 -->
                    <div id="rakuten-error" class="hidden">
                        <div class="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
                            <div class="flex">
                                <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                                </svg>
                                <div class="ml-3">
                                    <p class="text-sm text-red-800" id="rakuten-error-message"></p>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- ホテル候補リスト -->
                    <div id="rakuten-hotels-list" class="space-y-3"></div>
                    
                    <!-- フッター -->
                    <div class="mt-6 flex justify-end">
                        <button type="button" class="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg" onclick="rakutenSearch.closeModal()">
                            キャンセル
                        </button>
                    </div>
                </div>
            </div>
        `;

        // モーダルをDOMに追加
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        this.modal = document.getElementById('rakuten-search-modal');
    }

    /**
     * 検索ボタンクリック時の処理
     */
    async handleSearchButtonClick() {
        if (this.isSearching) return;

        // スポット名を取得
        const spotNameInput = document.getElementById('spotName');
        if (!spotNameInput) {
            this.showError('スポット名の入力欄が見つかりません');
            return;
        }

        const spotName = spotNameInput.value.trim();
        if (!spotName) {
            this.showError('スポット名を入力してください');
            return;
        }

        try {
            await this.searchHotels(spotName);
        } catch (error) {
            console.error('検索処理エラー:', error);
            this.showError('検索中にエラーが発生しました');
        }
    }

    /**
     * ホテル検索API呼び出し
     */
    async searchHotels(spotName) {
        this.isSearching = true;
        this.showModal();
        this.showLoading();

        try {
            const response = await fetch('/api/rakuten/manual-search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    spot_name: spotName
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || 'APIエラーが発生しました');
            }

            if (data.success) {
                this.displayHotels(data.hotels || []);
            } else {
                throw new Error(data.message || '検索に失敗しました');
            }

        } catch (error) {
            console.error('API呼び出しエラー:', error);
            this.showError(error.message);
        } finally {
            this.hideLoading();
            this.isSearching = false;
        }
    }

    /**
     * ホテル候補を表示
     */
    displayHotels(hotels) {
        const listContainer = document.getElementById('rakuten-hotels-list');
        
        if (hotels.length === 0) {
            listContainer.innerHTML = `
                <div class="text-center py-8">
                    <p class="text-gray-500">該当するホテルが見つかりませんでした</p>
                </div>
            `;
            return;
        }

        listContainer.innerHTML = hotels.map((hotel, index) => `
            <div class="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 cursor-pointer transition-colors"
                 onclick="rakutenSearch.selectHotel(${index}, '${this.escapeHtml(hotel.affiliate_url)}')">
                <div class="flex">
                    ${hotel.image_url ? `
                        <img src="${this.escapeHtml(hotel.image_url)}" 
                             alt="${this.escapeHtml(hotel.name)}"
                             class="w-16 h-16 object-cover rounded-lg mr-3 flex-shrink-0">
                    ` : `
                        <div class="w-16 h-16 bg-gray-200 rounded-lg mr-3 flex-shrink-0 flex items-center justify-center">
                            <svg class="w-8 h-8 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clip-rule="evenodd" />
                            </svg>
                        </div>
                    `}
                    <div class="flex-1 min-w-0">
                        <h4 class="text-sm font-medium text-gray-900 truncate">${this.escapeHtml(hotel.name)}</h4>
                        <p class="text-sm text-gray-500 truncate mt-1">${this.escapeHtml(hotel.address)}</p>
                        <div class="mt-2">
                            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                選択する
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    }

    /**
     * ホテル選択時の処理
     */
    selectHotel(index, affiliateUrl) {
        // 楽天URLフィールドに設定
        const rakutenUrlInput = document.getElementById('rakuten_url');
        if (rakutenUrlInput) {
            rakutenUrlInput.value = affiliateUrl;
            
            // 視覚的フィードバック
            rakutenUrlInput.style.backgroundColor = '#f0f9ff';
            setTimeout(() => {
                rakutenUrlInput.style.backgroundColor = '';
            }, 1000);
        }

        this.closeModal();
        
        // 成功メッセージ（簡易版）
        this.showSuccessMessage('ホテルリンクを設定しました');
    }

    /**
     * モーダル表示
     */
    showModal() {
        if (this.modal) {
            this.modal.classList.remove('hidden');
            document.body.classList.add('modal-open');
        }
    }

    /**
     * モーダル非表示
     */
    closeModal() {
        if (this.modal) {
            this.modal.classList.add('hidden');
            document.body.classList.remove('modal-open');
            this.hideError();
            this.hideLoading();
        }
    }

    /**
     * ローディング表示
     */
    showLoading() {
        const loadingEl = document.getElementById('rakuten-loading');
        if (loadingEl) {
            loadingEl.classList.remove('hidden');
        }
        this.hideError();
    }

    /**
     * ローディング非表示
     */
    hideLoading() {
        const loadingEl = document.getElementById('rakuten-loading');
        if (loadingEl) {
            loadingEl.classList.add('hidden');
        }
    }

    /**
     * エラー表示
     */
    showError(message) {
        const errorEl = document.getElementById('rakuten-error');
        const errorMessageEl = document.getElementById('rakuten-error-message');
        
        if (errorEl && errorMessageEl) {
            errorMessageEl.textContent = message;
            errorEl.classList.remove('hidden');
        }
        
        this.hideLoading();
    }

    /**
     * エラー非表示
     */
    hideError() {
        const errorEl = document.getElementById('rakuten-error');
        if (errorEl) {
            errorEl.classList.add('hidden');
        }
    }

    /**
     * 成功メッセージ表示（簡易版）
     */
    showSuccessMessage(message) {
        // 既存のトースト機能があれば利用、なければ簡易表示
        if (typeof maplinkToast !== 'undefined' && maplinkToast.success) {
            maplinkToast.success(message);
        } else {
            console.log('Success:', message);
        }
    }

    /**
     * HTMLエスケープ
     */
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// グローバルインスタンス作成
let rakutenSearch;

// DOM読み込み後に初期化
document.addEventListener('DOMContentLoaded', function() {
    rakutenSearch = new RakutenManualSearch();
}); 