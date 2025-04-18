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