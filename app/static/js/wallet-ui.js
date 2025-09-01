(function(){
  const fmtInt = (v)=> Number.isFinite(Number(v)) ? Number(v).toLocaleString() : '0';
  const fmtYen = (v)=> Number.isFinite(Number(v)) ? `¥${Math.round(Number(v)).toLocaleString()}` : '¥0';
  const setText = (id, val)=>{ const el = document.getElementById(id); if (el) el.textContent = val; };
  const setCircle = (id, percent)=>{
    const circle = document.getElementById(id);
    if (!circle) return;
    const C = 2*Math.PI*21; // r=21
    const p = Math.max(0, Math.min(100, Number(percent)||0));
    // 可視性のため0%でも僅かなスリバーを表示（ラベルは0%のまま）
    const pVisible = p === 0 ? 2 : p;
    const offset = C * (1 - pVisible/100);
    circle.setAttribute('stroke-dasharray', String(C));
    circle.setAttribute('stroke-dashoffset', String(offset));
  };

  async function getJSON(url){
    const res = await fetch(url, { credentials: 'same-origin' });
    if (!res.ok) return null;
    return await res.json();
  }

  async function init(){
    // 初期表示: 0%のスリバーを必ず描画（API失敗時でもグラフは見える）
    try {
      setText('wallet-pv-percent', '0%'); setCircle('wallet-pv-circle', 0);
      setText('wallet-clicks-percent', '0%'); setCircle('wallet-clicks-circle', 0);
      setText('wallet-revenue-percent', '0%'); setCircle('wallet-revenue-circle', 0);
    } catch(_e) {}
    // 1) 使えるお金（withdrawable_balance）
    const s = await getJSON('/api/wallet/summary');
    if (s && typeof s.withdrawable_balance !== 'undefined') {
      setText('wallet-withdrawable', fmtYen(s.withdrawable_balance));
    }

    // 2) 今月の実績（ビュー/クリック/収益）
    const c = await getJSON('/api/wallet/current');
    if (c) {
      const pv = Number(c.pv||0);
      const clicks = Number(c.clicks||0);
      const revenue = Number(c.estimated_revenue||0);
      setText('wallet-pv', fmtInt(pv));
      setText('wallet-clicks', fmtInt(clicks));
      setText('wallet-revenue', fmtYen(revenue));
      // パーセントの基準は単純に0-100に丸め（将来目標連動可）
      const pvPct = Math.min(100, Math.round(pv/Math.max(1,pv)*100));
      const clicksPct = Math.min(100, Math.round(clicks/Math.max(1,clicks)*100));
      const revPct = Math.min(100, Math.round(revenue/Math.max(1,revenue)*100));
      setText('wallet-pv-percent', `${pvPct}%`);
      setText('wallet-pv-diff', `${pvPct}%`);
      setCircle('wallet-pv-circle', pvPct);
      setText('wallet-clicks-percent', `${clicksPct}%`);
      setText('wallet-clicks-diff', `${clicksPct}%`);
      setCircle('wallet-clicks-circle', clicksPct);
      setText('wallet-revenue-percent', `${revPct}%`);
      setText('wallet-revenue-diff', `${revPct}%`);
      setCircle('wallet-revenue-circle', revPct);
    } else {
      // データなしフォールバック
      setText('wallet-pv', '0');
      setText('wallet-clicks', '0');
      setText('wallet-revenue', '¥0');
      setText('wallet-pv-percent', '0%'); setText('wallet-pv-diff', '0%'); setCircle('wallet-pv-circle', 0);
      setText('wallet-clicks-percent', '0%'); setText('wallet-clicks-diff', '0%'); setCircle('wallet-clicks-circle', 0);
      setText('wallet-revenue-percent', '0%'); setText('wallet-revenue-diff', '0%'); setCircle('wallet-revenue-circle', 0);
    }

    // 3) 過去の推移（データが無くても今月を含む過去3ヶ月を必ず表示）
    const t = await getJSON('/api/wallet/trends?months=3');
    renderTrends(t || {});
    // ドーナツ率: 直近3ヶ月の中で今月値/最大値
    try{
      const pvArr = normalize3((t && t.pv) || []);
      const clicksArr = normalize3((t && t.clicks) || []);
      const revArr = normalize3((t && t.revenue) || []);
      const pvMax = Math.max(0, ...pvArr);
      const clicksMax = Math.max(0, ...clicksArr);
      const revMax = Math.max(0, ...revArr);
      const pvPct = pvMax > 0 ? Math.round(pvArr[pvArr.length-1] / pvMax * 100) : 0;
      const clicksPct = clicksMax > 0 ? Math.round(clicksArr[clicksArr.length-1] / clicksMax * 100) : 0;
      const revPct = revMax > 0 ? Math.round(revArr[revArr.length-1] / revMax * 100) : 0;
      setText('wallet-pv-percent', `${pvPct}%`); setText('wallet-pv-diff', `${pvPct}%`); setCircle('wallet-pv-circle', pvPct);
      setText('wallet-clicks-percent', `${clicksPct}%`); setText('wallet-clicks-diff', `${clicksPct}%`); setCircle('wallet-clicks-circle', clicksPct);
      setText('wallet-revenue-percent', `${revPct}%`); setText('wallet-revenue-diff', `${revPct}%`); setCircle('wallet-revenue-circle', revPct);
      // growth badge: 3指標のうち2つ以上が前月比50%以上
      const growthSignals = [pvPct, clicksPct, revPct].filter(p=>p>=50).length;
      const badge = document.getElementById('wallet-growth-badge');
      if (badge) badge.style.display = growthSignals >= 2 ? '' : 'none';
    }catch(_e){
      setText('wallet-pv-percent', '0%'); setText('wallet-pv-diff', '0%'); setCircle('wallet-pv-circle', 0);
      setText('wallet-clicks-percent', '0%'); setText('wallet-clicks-diff', '0%'); setCircle('wallet-clicks-circle', 0);
      setText('wallet-revenue-percent', '0%'); setText('wallet-revenue-diff', '0%'); setCircle('wallet-revenue-circle', 0);
      const badge = document.getElementById('wallet-growth-badge');
      if (badge) badge.style.display = 'none';
    }

    // 4) 支払い履歴（空でもプレースホルダ表示）
    const p = await getJSON('/api/wallet/payouts');
    renderPayouts((p && Array.isArray(p.items)) ? p.items : []);

    // 5) 「お金をもらう」ボタン: 未実装案内
    try{
      const btn = document.querySelector('button[aria-haspopup="dialog"]');
      if (btn){
        btn.addEventListener('click', (e)=>{
          e.preventDefault();
          showComingSoonToast();
        }, { passive:false });
      }
    }catch(_e){}
  }

  function renderTrends(data){
    const root = document.getElementById('wallet-trends');
    if (!root) return;

    // 常に直近3ヶ月（今月含む）を生成
    const months = (data.months && data.months.length)
      ? data.months
      : (function(){
          const ans = [];
          const now = new Date();
          const thisMonth = new Date(now.getFullYear(), now.getMonth(), 1);
          for (let i=2;i>=0;i--){
            const d = new Date(thisMonth.getFullYear(), thisMonth.getMonth()-i, 1);
            ans.push(d.toISOString().slice(0,10));
          }
          return ans;
        })();
    const monthLabels = months.map(m=>{
      const d = new Date(m);
      return `${d.getMonth()+1}月`;
    });

    let pv = data.pv || [];
    let clicks = data.clicks || [];
    let revenue = data.revenue || [];

    // 長さを3に正規化（不足分は0で埋め、超過分は末尾3つに揃える）
    const normalize = (arr)=>{
      const a = Array.isArray(arr) ? arr.slice(-3) : [];
      while (a.length < 3) a.unshift(0);
      return a;
    };
    pv = normalize(pv);
    clicks = normalize(clicks);
    revenue = normalize(revenue);

    const pvMax = Math.max(1, ...pv);
    const clicksMax = Math.max(1, ...clicks);
    const revenueMax = Math.max(1, ...revenue);

    const section = (colorKey, title, values, max, fmtVal, barColors)=>{
      const rows = values.map((v, i)=>{
        const width = Math.round((Number(v)||0) / max * 100);
        const label = monthLabels[i] || '';
        const valueText = fmtVal(v);
        return `
        <div class="flex items-center gap-3">
          <div class="w-8 text-xs text-muted-foreground">${label}</div>
          <div class="flex-1 ${barColors.bg} rounded-full h-4 relative overflow-hidden">
            <div class="${barColors.fill} h-full rounded-full transition-all duration-700 ease-out" style="width:${width}%"></div>
          </div>
          <div class="text-xs font-medium ${barColors.text} w-16 text-right">${valueText}</div>
        </div>`;
      }).join('');
      return `
      <div>
        <div class="flex items-center gap-2 mb-3">
          <div class="w-3 h-3 ${colorKey} rounded-full"></div>
          <span class="text-sm font-medium">${title}</span>
        </div>
        <div class="space-y-2">${rows}</div>
      </div>`;
    };

    const html = [
      section('bg-blue-500', '👀 ビュー数', pv, pvMax, v=>fmtInt(v), { bg:'bg-blue-100', fill:'bg-gradient-to-r from-blue-400 to-blue-600', text:'text-blue-600' }),
      section('bg-amber-500', '🖱️ クリック数', clicks, clicksMax, v=>fmtInt(v), { bg:'bg-amber-100', fill:'bg-gradient-to-r from-amber-400 to-amber-600', text:'text-amber-600' }),
      section('bg-green-500', '💰 収益', revenue, revenueMax, v=>fmtYen(v), { bg:'bg-green-100', fill:'bg-gradient-to-r from-green-400 to-green-600', text:'text-green-600' })
    ].join('');

    root.innerHTML = html;
  }

  function renderPayouts(items){
    const root = document.getElementById('wallet-payouts');
    if (!root) return;
    const html = items.map(it=>{
      const paid = !!it.paid_at;
      const dateStr = it.paid_at ? new Date(it.paid_at).toISOString().slice(0,10) : '-';
      const amount = fmtYen(it.amount);
      const badge = paid ? 'bg-green-100 text-green-700 border-green-200' : 'bg-yellow-100 text-yellow-700 border-yellow-200';
      const badgeText = paid ? '✅' : '⏳';
      return `
      <div class="flex items-center gap-3 p-3 bg-gradient-to-r from-green-50 to-emerald-50 rounded-2xl">
        <div class="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center"><span class="text-lg">💰</span></div>
        <div class="flex-1">
          <p class="font-medium text-sm">${amount}</p>
          <p class="text-xs text-muted-foreground">${dateStr}</p>
        </div>
        <span data-slot=badge class="inline-flex items-center justify-center rounded-md border px-2 py-0.5 text-xs font-medium w-fit whitespace-nowrap shrink-0 ${badge}">${badgeText}</span>
      </div>`;
    }).join('');
    root.innerHTML = html || '<p class="text-xs text-muted-foreground">履歴はまだありません</p>';
  }

  

  function normalize3(arr){
    const a = Array.isArray(arr) ? arr.slice(-3) : [];
    while (a.length < 3) a.unshift(0);
    return a;
  }

  function showComingSoonToast(){
    const msg = 'この機能は近日リリース予定です。準備が整い次第ご案内します。\nいつもご利用ありがとうございます！';
    try{
      // 軽量トースト
      const toast = document.createElement('div');
      toast.textContent = msg;
      toast.style.position = 'fixed';
      toast.style.left = '50%';
      toast.style.bottom = '24px';
      toast.style.transform = 'translateX(-50%)';
      toast.style.background = '#111827';
      toast.style.color = '#fff';
      toast.style.padding = '12px 16px';
      toast.style.borderRadius = '12px';
      toast.style.boxShadow = '0 6px 20px rgba(0,0,0,.2)';
      toast.style.fontSize = '12px';
      toast.style.zIndex = '9999';
      toast.style.maxWidth = '90vw';
      toast.style.textAlign = 'center';
      document.body.appendChild(toast);
      setTimeout(()=>{ toast.style.opacity='0'; toast.style.transition='opacity .3s'; }, 2200);
      setTimeout(()=>{ toast.remove(); }, 2600);
    }catch(_e){
      alert(msg);
    }
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') init();
  else window.addEventListener('DOMContentLoaded', init);
})();


