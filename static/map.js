let map = L.map('map').setView([35.681236, 139.767125], 18);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

let marker = null;
let arrow = null;

function updateMap(data) {
  const { lat, lon, heading, error, distance } = data;

  // 更新：自己位置マーカー
  if (marker) map.removeLayer(marker);
  marker = L.marker([lat, lon]).addTo(map);

  // 更新：方位矢印（画面で10%程度の長さ）
  const arrowLen = 0.0003;
  const lat2 = lat + arrowLen * Math.cos(heading * Math.PI / 180);
  const lon2 = lon + arrowLen * Math.sin(heading * Math.PI / 180);

  if (arrow) map.removeLayer(arrow);
  arrow = L.polyline([[lat, lon], [lat2, lon2]], {color: 'red'}).addTo(map);

  // 更新：情報表示
  document.getElementById("info").innerHTML = `
    <b>Lat:</b> ${lat.toFixed(6)}<br>
    <b>Lon:</b> ${lon.toFixed(6)}<br>
    <b>Heading:</b> ${heading.toFixed(2)}°<br>
    <b>Distance:</b> ${distance.toFixed(2)} m<br>
    <b>Error:</b> ${error.toFixed(2)} m
  `;
}

async function fetchPosition() {
  try {
    const res = await fetch('/api/position');
    const data = await res.json();
    updateMap(data);
  } catch (err) {
    console.error("Failed to fetch GPS data:", err);
  }
}

// 初回実行 & 10秒ごと更新
fetchPosition();
setInterval(fetchPosition, 10000);
