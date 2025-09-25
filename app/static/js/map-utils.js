/**
 * 地図関連のユーティリティ関数
 */

// 地図を初期化する関数
function initMap(elementId, options = {}) {
    const defaultOptions = {
        zoomControl: false,
        center: [36.5748, 139.2394],
        zoom: 5,
        minZoom: 3
    };
    
    const mapOptions = { ...defaultOptions, ...options };
    
    const map = L.map(elementId, {
        zoomControl: mapOptions.zoomControl,
        minZoom: mapOptions.minZoom
    }).setView(mapOptions.center, mapOptions.zoom);
    
    // OpenStreetMapのタイルレイヤーを追加
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);
    
    return map;
}

// マーカーを追加する関数
function addMarker(map, lat, lng, options = {}) {
    console.log('addMarker関数が呼ばれました:', { map, lat, lng, options });
    
    if (!map) {
        console.error('マップオブジェクトがnullです');
        return null;
    }
    
    const markerOptions = {
        icon: L.divIcon({
            className: 'custom-marker',
            html: '<div class="marker-pin"></div>',
            iconSize: [30, 30],
            iconAnchor: [15, 30]
        }),
        ...options
    };
    
    console.log('作成するマーカーのオプション:', markerOptions);
    
    try {
        const marker = L.marker([lat, lng], markerOptions).addTo(map);
        console.log('マーカー作成成功:', marker);
        return marker;
    } catch (error) {
        console.error('マーカー作成中にエラーが発生しました:', error);
        return null;
    }
}

// マーカーを表示し、地図の表示範囲を調整する関数
function showMarkersAndFitBounds(map, markers) {
    if (markers.length === 0) return;
    
    // マーカーの位置を取得
    const bounds = L.latLngBounds(markers.map(marker => marker.getLatLng()));
    
    // 地図の表示範囲を調整（パディングを追加、最小ズームレベルを設定）
    map.fitBounds(bounds, {
        padding: [50, 50],
        minZoom: 3 // 最小ズームレベルを3（大陸レベル）に制限
    });
}

// スポット詳細をモーダルに表示する関数
function renderSpotDetail(spot) {
    const container = document.getElementById('modal-content-container');
    
    // スポットの写真を取得
    const photos = spot.photos || [];
    
    // モーダルコンテンツを生成
    const content = `
        <div class="spot-detail">
            ${photos.length > 0 ? `
            <div class="spot-photos">
                <img src="${photos[0].photo_url}" alt="${spot.name}" class="w-full h-48 object-cover">
            </div>
            ` : ''}
            <div class="spot-info p-4">
                <h2 class="text-xl font-bold mb-2">${spot.name}</h2>
                <p class="text-gray-600 mb-4">${spot.location || ''}</p>
                <div class="spot-description text-gray-700">
                    ${spot.description || '説明はありません。'}
                </div>
            </div>
        </div>
    `;
    
    container.innerHTML = content;
}

// カスタムマーカーのスタイルを追加
const style = document.createElement('style');
style.textContent = `
    .custom-marker {
        background: transparent;
        border: none;
    }
    .marker-pin {
        width: 30px;
        height: 30px;
        border-radius: 50% 50% 50% 0;
        background: #3b82f6;
        position: absolute;
        transform: rotate(-45deg);
        left: 50%;
        top: 50%;
        margin: -15px 0 0 -15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    .marker-pin::after {
        content: '';
        width: 24px;
        height: 24px;
        margin: 3px 0 0 3px;
        background: #fff;
        position: absolute;
        border-radius: 50%;
    }
`;
document.head.appendChild(style);

// 公開スポット詳細ページのホテルオファー取得（最小実装）
try {
  window.addEventListener('DOMContentLoaded', function () {
    const searchBtn = document.getElementById('hotelSearchBtn');
    const checkInEl = document.getElementById('checkIn');
    const checkOutEl = document.getElementById('checkOut');
    const offersList = document.getElementById('offers-list');
    const offersNote = document.getElementById('offers-note');
    const spotIdMeta = document.querySelector('meta[name="spot-id"]');
    const spotId = spotIdMeta ? spotIdMeta.getAttribute('content') : null;

    // ローカルストレージキー
    const LS_KEY_CI = 'hotel_check_in';
    const LS_KEY_CO = 'hotel_check_out';
    const LS_KEY_ADULTS = 'hotel_adults_total';
    const LS_KEY_CHILDREN = 'hotel_children_total';

    // 日付デフォルトとminの設定（ストレージ優先）
    const today = new Date();
    const fmt = (d)=> `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    const ensureDateDefaults = () => {
      // 今日を00:00に正規化
      const today0 = new Date(today.getFullYear(), today.getMonth(), today.getDate());
      const defaultIn = new Date(today0.getFullYear(), today0.getMonth(), today0.getDate() + 7);
      const defaultOut = new Date(defaultIn.getFullYear(), defaultIn.getMonth(), defaultIn.getDate() + 1);

      if (checkInEl) {
        checkInEl.min = fmt(today0);
        const storedCi = localStorage.getItem(LS_KEY_CI);
        let ciStr = checkInEl.value || storedCi || '';
        let ci = ciStr ? new Date(ciStr) : null;
        if (!ci || isNaN(ci.getTime()) || ci < today0) {
          ci = defaultIn;
        }
        checkInEl.value = fmt(ci);
      }

      if (checkOutEl) {
        // 入力済みチェックインを前提に、最低チェックアウトは+1日
        let inDate = (checkInEl && checkInEl.value) ? new Date(checkInEl.value) : null;
        if (!inDate || isNaN(inDate.getTime()) || inDate < new Date(today0)) {
          inDate = defaultIn;
        }
        const outMin = new Date(inDate.getFullYear(), inDate.getMonth(), inDate.getDate() + 1);
        checkOutEl.min = fmt(outMin);

        const storedCo = localStorage.getItem(LS_KEY_CO);
        let coStr = checkOutEl.value || storedCo || '';
        let co = coStr ? new Date(coStr) : null;
        if (!co || isNaN(co.getTime()) || co <= inDate) {
          co = new Date(outMin);
        }
        checkOutEl.value = fmt(co);
      }
    };

    // コンテナタップでカレンダーを出す（左=チェックイン / 右=チェックアウト）
    const hookDateContainerClick = () => {
      const parent = checkInEl && checkInEl.parentElement ? checkInEl.parentElement : null; // 2入力を内包
      if (!parent) return;
      parent.addEventListener('click', (e) => {
        const rect = parent.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const targetInput = (x < rect.width / 2) ? checkInEl : checkOutEl;
        if (targetInput) {
          if (typeof targetInput.showPicker === 'function') targetInput.showPicker();
          else targetInput.focus();
        }
      });
    };

    const renderOffersLoading = () => {
      if (!offersList) return;
      offersList.innerHTML = '';
      const skeleton = document.createElement('div');
      skeleton.className = 'space-y-3';
      const item = () => `
        <div class="flex items-center p-4 border rounded-lg border-border animate-pulse gap-4">
          <div class="flex items-center gap-3 flex-1 min-w-0">
            <div class="h-4 w-24 bg-muted rounded"></div>
            <div class="h-4 w-12 bg-muted rounded"></div>
          </div>
          <div class="flex items-center gap-4 flex-1 min-w-0 justify-end">
            <div class="text-right flex-1 min-w-0">
              <div class="h-6 w-24 bg-muted rounded mb-2 ml-auto"></div>
              <div class="h-3 w-16 bg-muted rounded ml-auto"></div>
            </div>
            <div class="h-9 w-24 bg-muted rounded flex-shrink-0"></div>
          </div>
        </div>`;
      skeleton.innerHTML = item() + item() + item();
      offersList.appendChild(skeleton);
    };

    const renderError = (message) => {
      if (!offersList) return;
      offersList.innerHTML = '';
      const msg = document.createElement('div');
      msg.className = 'text-sm text-muted-foreground';
      msg.textContent = message || '取得できませんでした。少し時間をおいて再検索してみてください。';
      offersList.appendChild(msg);
    };

    const renderEmpty = () => {
      if (!offersList) return;
      offersList.innerHTML = '';
      const msg = document.createElement('div');
      msg.className = 'text-sm text-muted-foreground';
      msg.textContent = '空きが見つかりませんでした。日付や人数を変更して再検索してください。';
      offersList.appendChild(msg);
    };

    const renderOffers = (offers) => {
      if (!offersList) return;
      offersList.innerHTML = '';
      if (!offers || offers.length === 0) { renderEmpty(); return; }

      const VISIBLE_LIMIT = 3;

      const createItem = (o) => {
        const isMin = o.is_min_price === true;
        const badgeHtml = isMin ? '<span data-slot=badge class="inline-flex items-center justify-center rounded-md border px-2 py-0.5 text-xs font-medium w-fit whitespace-nowrap shrink-0 border-transparent bg-green-500 text-white">最安値</span>' : '';
        const hasPrice = o.price !== undefined && o.price !== null && o.price !== '';
        const priceHtml = hasPrice ? `<div class="text-xl font-bold">¥${Number(o.price).toLocaleString()}</div>` : '<div class="text-sm text-muted-foreground">価格はリンク先でご確認ください</div>';
        const btnDisabled = o.deeplink ? '' : 'disabled';
        const btnLabel = o.deeplink ? '予約する' : '詳細';
        const provider = o.provider || '提携サイト';
        const wrapper = document.createElement('div');
        wrapper.className = 'flex items-center justify-between p-4 border rounded-lg border-border' + (isMin ? ' border-green-500 bg-green-50' : '');
        const deeplink = o.deeplink ? (window.walletAnalytics ? window.walletAnalytics.buildRedirectUrl(provider, o.deeplink) : o.deeplink) : '#';
        wrapper.innerHTML = `
          <div class="flex items-center gap-3">
            <div>
              <div class=font-medium>${provider}</div>${badgeHtml}
            </div>
          </div>
          <div class="flex items-center gap-4">
            <div class=text-right>
              ${priceHtml}
              ${hasPrice ? '<div class="text-sm text-muted-foreground">1泊あたり</div>' : ''}
            </div>
            <a href="${deeplink}" target="_blank" rel="nofollow sponsored noopener" ${btnDisabled} data-slot=button class="justify-center whitespace-nowrap rounded-md text-sm font-medium transition-all disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-9 px-4 py-2 has-[>svg]:px-3 flex items-center gap-2">${btnLabel}
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-external-link w-4 h-4" aria-hidden="true">
                <path d="M15 3h6v6"></path>
                <path d="M10 14 21 3"></path>
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              </svg>
            </a>
          </div>
        `;
        return wrapper;
      };

      // 3件以下ならそのまま表示
      if (offers.length <= VISIBLE_LIMIT) {
        offers.forEach((o) => offersList.appendChild(createItem(o)));
        return;
      }

      // 先頭3件を表示
      offers.slice(0, VISIBLE_LIMIT).forEach((o) => offersList.appendChild(createItem(o)));

      // 残りをアコーディオン（初期は閉）
      const restCount = offers.length - VISIBLE_LIMIT;
      const moreList = document.createElement('div');
      moreList.className = 'space-y-3 hidden';
      moreList.setAttribute('data-more-list', '1');
      offers.slice(VISIBLE_LIMIT).forEach((o) => moreList.appendChild(createItem(o)));
      offersList.appendChild(moreList);

      // トグルボタン
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.setAttribute('aria-expanded', 'false');
      toggle.className = 'w-full mt-2 text-sm text-primary hover:underline';
      toggle.textContent = `他の${restCount}件を表示`;
      toggle.addEventListener('click', () => {
        const expanded = toggle.getAttribute('aria-expanded') === 'true';
        if (expanded) {
          toggle.setAttribute('aria-expanded', 'false');
          toggle.textContent = `他の${restCount}件を表示`;
          moreList.classList.add('hidden');
        } else {
          toggle.setAttribute('aria-expanded', 'true');
          toggle.textContent = '閉じる';
          moreList.classList.remove('hidden');
        }
      });
      offersList.appendChild(toggle);
    };

    const fetchOffers = async () => {
      if (!spotId || !offersList) return;
      const params = new URLSearchParams();
      ensureDateDefaults();
      const ci = checkInEl && checkInEl.value ? checkInEl.value : fmt(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 7));
      const co = checkOutEl && checkOutEl.value ? checkOutEl.value : fmt(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 8));
      params.set('checkIn', ci);
      params.set('checkOut', co);
      const adultsEl = document.getElementById('adults');
      const adultsVal = adultsEl && adultsEl.dataset.total ? adultsEl.dataset.total : (adultsEl && adultsEl.value ? adultsEl.value : (localStorage.getItem(LS_KEY_ADULTS) || '2'));
      params.set('adults', adultsVal);
      const childrenVal = adultsEl && adultsEl.dataset.children ? adultsEl.dataset.children : (localStorage.getItem(LS_KEY_CHILDREN) || '0');
      params.set('children', childrenVal);
      // 同期保存
      try{
        localStorage.setItem(LS_KEY_CI, ci);
        localStorage.setItem(LS_KEY_CO, co);
        localStorage.setItem(LS_KEY_ADULTS, String(adultsVal));
        localStorage.setItem(LS_KEY_CHILDREN, String(childrenVal));
      }catch(_e){}
      try {
        if (searchBtn) searchBtn.setAttribute('disabled', 'disabled');
        renderOffersLoading();
        const res = await fetch(`/public/api/spots/${spotId}/hotel_offers?${params.toString()}`);
        if (!res.ok) { renderError(); return; }
        let data = null;
        try { data = await res.json(); } catch(_jsonErr) { renderError(); return; }
        if (!data || !Array.isArray(data.offers)) { renderEmpty(); return; }
        renderOffers(data.offers || []);
      } catch (e) {
        renderError();
      } finally {
        if (searchBtn) searchBtn.removeAttribute('disabled');
      }
    };

    if (searchBtn && spotId) {
      searchBtn.removeAttribute('disabled');
      searchBtn.addEventListener('click', function(e){ e.preventDefault(); fetchOffers(); });
      // 日付変更時はminや既定値だけ調整し、自動検索はしない
      if (checkInEl) checkInEl.addEventListener('change', () => { ensureDateDefaults(); });
      if (checkOutEl) checkOutEl.addEventListener('change', () => { ensureDateDefaults(); });
      const adultsEl2 = document.getElementById('adults');
      if (adultsEl2) adultsEl2.addEventListener('change', () => {});
      fetchOffers();
    }

    ensureDateDefaults();
    hookDateContainerClick();

    // 人数ピッカー（大人/子供、合計表示）
    const adultsInput = document.getElementById('adults');
    if (adultsInput) {
      adultsInput.readOnly = true;
      // 初期は合計人数を表示（大人2 + 子供0）
      const initAdults = localStorage.getItem(LS_KEY_ADULTS) || '2';
      const initChildren = localStorage.getItem(LS_KEY_CHILDREN) || '0';
      adultsInput.value = `${parseInt(initAdults,10) + parseInt(initChildren,10)}名`;
      adultsInput.dataset.total = String(initAdults);
      adultsInput.dataset.children = String(initChildren);
      const picker = document.createElement('div');
      // 入力直下に表示するため absolute で配置
      picker.className = 'absolute w-72 bg-white border rounded-lg shadow-lg p-4 z-50 hidden';
      picker.innerHTML = `
        <div class="flex items-center justify-between mb-3">
          <span>大人</span>
          <div class="flex items-center gap-2">
            <button type="button" id="dec-adult" class="px-2 py-1 border rounded">-</button>
            <span id="num-adult">2</span>
            <button type="button" id="inc-adult" class="px-2 py-1 border rounded">+</button>
          </div>
        </div>
        <div class="flex items-center justify-between mb-4">
          <span>子供</span>
          <div class="flex items-center gap-2">
            <button type="button" id="dec-child" class="px-2 py-1 border rounded">-</button>
            <span id="num-child">0</span>
            <button type="button" id="inc-child" class="px-2 py-1 border rounded">+</button>
          </div>
        </div>
        <div class="flex items-center justify-end gap-4 text-blue-600">
          <button type="button" id="cancel-guests">キャンセル</button>
          <button type="button" id="apply-guests">完了</button>
        </div>
      `;
      document.body.appendChild(picker);

      const placePicker = () => {
        const rect = adultsInput.getBoundingClientRect();
        picker.style.top = `${rect.bottom + window.scrollY + 8}px`;
        picker.style.left = `${rect.left + window.scrollX}px`;
      };
      const showPicker = () => { placePicker(); picker.classList.remove('hidden'); };
      const hidePicker = () => { picker.classList.add('hidden'); };
      adultsInput.addEventListener('click', showPicker);
      window.addEventListener('resize', () => { if (!picker.classList.contains('hidden')) placePicker(); });
      window.addEventListener('scroll', () => { if (!picker.classList.contains('hidden')) placePicker(); }, { passive: true });

      const adultSpan = picker.querySelector('#num-adult');
      const childSpan = picker.querySelector('#num-child');
      const decAdult = picker.querySelector('#dec-adult');
      const incAdult = picker.querySelector('#inc-adult');
      const decChild = picker.querySelector('#dec-child');
      const incChild = picker.querySelector('#inc-child');
      const cancelBtn = picker.querySelector('#cancel-guests');
      const applyBtn = picker.querySelector('#apply-guests');

      const clamp = (v,min,max)=> Math.max(min, Math.min(max, v));
      const updateDisplay = ()=>{
        const a = parseInt(adultSpan.textContent||'2',10);
        const c = parseInt(childSpan.textContent||'0',10);
        adultsInput.dataset.total = String(a);
        adultsInput.dataset.children = String(c);
        // 入力欄には合計人数を表示
        adultsInput.value = `${a + c}名`;
        try{
          localStorage.setItem(LS_KEY_ADULTS, String(a));
          localStorage.setItem(LS_KEY_CHILDREN, String(c));
        }catch(_e){}
      };
      decAdult.addEventListener('click', ()=>{ adultSpan.textContent = String(clamp(parseInt(adultSpan.textContent||'2',10)-1,1,20)); });
      incAdult.addEventListener('click', ()=>{ adultSpan.textContent = String(clamp(parseInt(adultSpan.textContent||'2',10)+1,1,20)); });
      decChild.addEventListener('click', ()=>{ childSpan.textContent = String(clamp(parseInt(childSpan.textContent||'0',10)-1,0,20)); });
      incChild.addEventListener('click', ()=>{ childSpan.textContent = String(clamp(parseInt(childSpan.textContent||'0',10)+1,0,20)); });
      // 入力外クリックで閉じる
      document.addEventListener('click', (e)=>{
        if (picker.classList.contains('hidden')) return;
        if (e.target === adultsInput || picker.contains(e.target)) return;
        hidePicker();
      });
      cancelBtn.addEventListener('click', ()=>{ hidePicker(); });
      applyBtn.addEventListener('click', ()=>{ updateDisplay(); hidePicker(); fetchOffers(); });
    }
  });
} catch (e) {
  console.warn('hotel offers init skipped:', e);
}

// 住所から緯度経度を取得する（ジオコーディング）
async function geocodeAddress(address) {
  if (!address) return null;
  
  try {
    const encodedAddress = encodeURIComponent(address);
    const response = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodedAddress}&limit=1`, {
      headers: {
        'User-Agent': 'my-map.link App (https://my-map.link)'
      }
    });
    const data = await response.json();
    
    if (data && data.length > 0) {
      return {
        lat: parseFloat(data[0].lat),
        lng: parseFloat(data[0].lon),
        displayName: data[0].display_name
      };
    }
    return null;
  } catch (error) {
    console.error('Geocoding error:', error);
    return null;
  }
}

// 緯度経度から住所を取得する（逆ジオコーディング）
async function reverseGeocode(lat, lng) {
  if (!lat || !lng) return null;
  
  try {
    const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`, {
      headers: {
        'User-Agent': 'my-map.link App (https://my-map.link)'
      }
    });
    const data = await response.json();
    
    if (data && data.display_name) {
      // サマリーロケーションを構築
      const address = data.address;
      const summaryParts = [];
      
      if (address.country) summaryParts.push(address.country);
      if (address.state) summaryParts.push(address.state);
      if (address.city || address.town || address.village) {
        summaryParts.push(address.city || address.town || address.village);
      }
      
      return {
        address: data.display_name,
        details: data.address,
        summary_location: summaryParts.join('、')
      };
    }
    return null;
  } catch (error) {
    console.error('Reverse geocoding error:', error);
    return null;
  }
} 