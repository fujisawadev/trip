/**
 * 地図関連のユーティリティ関数
 */

// 地図インスタンスを初期化する
function initMap(elementId, options = {}) {
  const defaultOptions = {
    center: [35.6812, 139.7671], // 東京をデフォルト中心に
    zoom: 13,
    scrollWheelZoom: true
  };
  
  const mapOptions = { ...defaultOptions, ...options };
  const map = L.map(elementId, mapOptions);
  
  // OpenStreetMapのタイルレイヤーを追加
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
  }).addTo(map);
  
  return map;
}

// マーカーを追加する
function addMarker(map, lat, lng, options = {}) {
  if (!lat || !lng) return null;
  
  const marker = L.marker([lat, lng], options);
  marker.addTo(map);
  return marker;
}

// 複数のマーカーを表示し、すべてが見えるようにビューを調整する
function showMarkersAndFitBounds(map, markers) {
  if (!markers || markers.length === 0) return;
  
  const group = L.featureGroup(markers);
  map.fitBounds(group.getBounds(), { padding: [30, 30] });
}

// 住所から緯度経度を取得する（ジオコーディング）
async function geocodeAddress(address) {
  if (!address) return null;
  
  try {
    const encodedAddress = encodeURIComponent(address);
    const response = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodedAddress}&limit=1`);
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
    const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`);
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