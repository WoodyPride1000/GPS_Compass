let map;
let baseMarker;
let roverMarker;
let headingLine;

function updateMap() {
  fetch("/api/position")
    .then(res => res.json())
    .then(data => {
      const base = data.base;
      const rover = data.rover;
      const heading = data.heading;
      const error = data.error;

      // 画面上のテキスト更新
      document.getElementById("coords").textContent = `緯度: ${base.lat.toFixed(6)}, 経度: ${base.lon.toFixed(6)}`;
      document.getElementById("heading").textContent = `方位角: ${heading.toFixed(1)}°`;
      document.getElementById("error").textContent = `推定誤差: ${error.toFixed(2)} m`;

      // 地図初期化またはマーカー更新
      if (!map) {
        map = L.map("map").setView([base.lat, base.lon], 19);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: "© OpenStreetMap contributors"
        }).addTo(map);

        baseMarker = L.marker([base.lat, base.lon]).addTo(map).bindPopup("基準局(Base)").openPopup();
        roverMarker = L.marker([rover.lat, rover.lon]).addTo(map).bindPopup("移動局(Rover)");
      } else {
        baseMarker.setLatLng([base.lat, base.lon]);
        roverMarker.setLatLng([rover.lat, rover.lon]);
        map.setView([base.lat, base.lon]);
      }

      // 既存の方位線を削除
      if (headingLine) {
        map.removeLayer(headingLine);
      }

      // 方位線の終点計算（200m先）
      const R = 6378137; // 地球半径[m]
      const lat1 = base.lat * Math.PI / 180;
      const lon1 = base.lon * Math.PI / 180;
      const bearing = heading * Math.PI / 180;
      const distance = 200; // 表示したい線の長さ[m]

      const lat2 = Math.asin(Math.sin(lat1) * Math.cos(distance / R) +
                             Math.cos(lat1) * Math.sin(distance / R) * Math.cos(bearing));
      const lon2 = lon1 + Math.atan2(Math.sin(bearing) * Math.sin(distance / R) * Math.cos(lat1),
                                    Math.cos(distance / R) - Math.sin(lat1) * Math.sin(lat2));
      const endLat = lat2 * 180 / Math.PI;
      const endLon = lon2 * 180 / Math.PI;

      // 方位線をピンク色で描画
      headingLine = L.polyline([[base.lat, base.lon], [endLat, endLon]], {
        color: "pink",
        weight: 2
      }).addTo(map);
    })
    .catch(err => {
      console.error("位置情報取得エラー:", err);
    });
}

// 2秒ごとに更新
setInterval(updateMap, 2000);









