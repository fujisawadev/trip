(function(){
  function uuidv4(){
    if (crypto && crypto.randomUUID) return crypto.randomUUID();
    const bytes = new Uint8Array(16);
    if (crypto && crypto.getRandomValues) crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes).map(b => b.toString(16).padStart(2,'0')).join('');
    return `${hex.substr(0,8)}-${hex.substr(8,4)}-${hex.substr(12,4)}-${hex.substr(16,4)}-${hex.substr(20)}`;
  }

  function setCookie(name, value, maxAgeSec){
    try{
      const attrs = [`Max-Age=${Math.floor(maxAgeSec)}`, 'Path=/', 'SameSite=Lax'];
      if (location.protocol === 'https:') attrs.push('Secure');
      document.cookie = `${encodeURIComponent(name)}=${encodeURIComponent(value)}; ${attrs.join('; ')}`;
    }catch(_e){}
  }

  function getCookie(name){
    try{
      const n = encodeURIComponent(name) + '=';
      const parts = document.cookie.split(';');
      for (let p of parts){
        p = p.trim();
        if (p.indexOf(n) === 0) return decodeURIComponent(p.substring(n.length));
      }
    }catch(_e){}
    return null;
  }

  function ensureClientId(){
    let cid = getCookie('ml_cid');
    if (!cid){
      cid = uuidv4();
      // 400日 ≒ 34560000秒
      setCookie('ml_cid', cid, 400*24*60*60);
    }
    return cid;
  }

  function ensureSessionId(){
    // 30分スライディング: 1800秒
    let sid = getCookie('ml_sid');
    if (!sid) sid = uuidv4();
    setCookie('ml_sid', sid, 30*60);
    return sid;
  }

  function refreshSessionOnActivity(){
    let throttle = false;
    const refresh = ()=>{ if (throttle) return; throttle = true; setTimeout(()=>{ throttle=false; ensureSessionId(); }, 1000); };
    ['visibilitychange','focus','click','scroll','keydown','beforeunload'].forEach(ev=>{
      window.addEventListener(ev, refresh, { passive: true });
    });
  }

  function getIds(){
    const spotMeta = document.querySelector('meta[name="spot-id"]');
    const userMeta = document.querySelector('meta[name="user-id"]');
    const pageId = spotMeta ? spotMeta.getAttribute('content') : null;
    const userId = userMeta ? userMeta.getAttribute('content') : null;
    const cid = ensureClientId();
    const sid = ensureSessionId();
    return { userId, pageId, cid, sid };
  }

  function buildRedirectUrl(ota, destUrl){
    const ids = getIds();
    if (!ota || !destUrl || !ids.userId || !ids.pageId) return destUrl;
    const params = new URLSearchParams();
    params.set('user_id', ids.userId);
    params.set('page_id', ids.pageId);
    params.set('sid', ids.sid);
    params.set('cid', ids.cid);
    params.set('url', destUrl);
    return `/api/wallet/r/${encodeURIComponent(String(ota).toLowerCase())}?${params.toString()}`;
  }

  function sendViewAfterDelay(){
    const ids = getIds();
    if (!ids.userId || !ids.pageId) return;
    const startedAt = Date.now();
    setTimeout(()=>{
      const dwell = Date.now() - startedAt;
      if (dwell < 3000) return; // 念のため
      fetch('/api/wallet/ingest/view',{
        method:'POST',
        headers:{ 'Content-Type':'application/json' },
        body: JSON.stringify({
          user_id: Number(ids.userId),
          page_id: Number(ids.pageId),
          client_id: ids.cid,
          session_id: ids.sid,
          dwell_ms: dwell,
          price_median: null
        })
      }).catch(()=>{});
    }, 3000);
  }

  // init
  try{
    ensureClientId();
    ensureSessionId();
    refreshSessionOnActivity();
    if (document.readyState === 'complete' || document.readyState === 'interactive') sendViewAfterDelay();
    else window.addEventListener('DOMContentLoaded', sendViewAfterDelay);
  }catch(_e){}

  window.walletAnalytics = { getIds, buildRedirectUrl };
})();


