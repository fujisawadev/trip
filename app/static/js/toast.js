/**
 * Spacey共通トースト通知システム
 * 画面中央に通知メッセージを表示する
 */

// グローバルスコープで使えるように
window.SpaceyToast = {
  /**
   * トーストメッセージを表示する
   * @param {string} message - 表示するメッセージ
   * @param {string} type - メッセージタイプ: 'success', 'error', 'warning', 'info'
   * @param {number} duration - 表示時間（ミリ秒）、デフォルトは3000ms
   */
  show: function(message, type = 'info', duration = 3000) {
    // 既存のメッセージがあれば削除
    const existingMessage = document.querySelector('.spacey-toast-message');
    if (existingMessage) {
      existingMessage.remove();
    }
    
    // メッセージ要素を作成
    const messageElement = document.createElement('div');
    
    // タイプに応じたスタイルを適用
    let backgroundColor, textColor, borderColor;
    switch (type) {
      case 'success':
        backgroundColor = 'bg-green-100';
        textColor = 'text-green-700';
        borderColor = 'border-green-200';
        break;
      case 'error':
        backgroundColor = 'bg-red-100';
        textColor = 'text-red-700';
        borderColor = 'border-red-200';
        break;
      case 'warning':
        backgroundColor = 'bg-yellow-100';
        textColor = 'text-yellow-700';
        borderColor = 'border-yellow-200';
        break;
      case 'info':
      default:
        backgroundColor = 'bg-blue-100';
        textColor = 'text-blue-700';
        borderColor = 'border-blue-200';
        break;
    }
    
    // クラスを設定
    messageElement.className = `spacey-toast-message fixed inset-x-0 top-4 mx-auto w-4/5 max-w-sm p-4 rounded-lg shadow-lg z-50 transition-opacity duration-300 text-center ${backgroundColor} ${textColor} border ${borderColor}`;
    messageElement.textContent = message;
    
    // bodyに追加
    document.body.appendChild(messageElement);
    
    // 指定時間後に消える
    setTimeout(() => {
      messageElement.classList.add('opacity-0');
      setTimeout(() => {
        messageElement.remove();
      }, 300);
    }, duration);
  },
  
  /**
   * サクセスメッセージを表示する
   * @param {string} message - 表示するメッセージ
   * @param {number} duration - 表示時間（ミリ秒）
   */
  success: function(message, duration = 3000) {
    this.show(message, 'success', duration);
  },
  
  /**
   * エラーメッセージを表示する
   * @param {string} message - 表示するメッセージ
   * @param {number} duration - 表示時間（ミリ秒）
   */
  error: function(message, duration = 3000) {
    this.show(message, 'error', duration);
  },
  
  /**
   * 警告メッセージを表示する
   * @param {string} message - 表示するメッセージ
   * @param {number} duration - 表示時間（ミリ秒）
   */
  warning: function(message, duration = 3000) {
    this.show(message, 'warning', duration);
  },
  
  /**
   * 情報メッセージを表示する
   * @param {string} message - 表示するメッセージ
   * @param {number} duration - 表示時間（ミリ秒）
   */
  info: function(message, duration = 3000) {
    this.show(message, 'info', duration);
  },
  
  /**
   * ページ読み込み時にFlaskのフラッシュメッセージを処理する
   * Jinja2の{% with messages = get_flashed_messages(with_categories=true) %}ブロックの代わりに使用
   * この関数はベースレイアウトに配置して自動的に実行されるべき
   */
  processFlashMessages: function() {
    const flashMessages = document.querySelectorAll('.flask-flash-message');
    
    if (flashMessages.length > 0) {
      flashMessages.forEach((element) => {
        const message = element.textContent.trim();
        const category = element.getAttribute('data-category') || 'info';
        
        if (message) {
          // メッセージが存在する場合は表示
          this.show(message, category);
          
          // 処理したメッセージを削除
          element.remove();
        }
      });
    }
  }
};

// DOMが読み込まれたら自動的にフラッシュメッセージを処理
document.addEventListener('DOMContentLoaded', function() {
  // Flaskのフラッシュメッセージがあれば処理
  SpaceyToast.processFlashMessages();
}); 