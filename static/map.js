let map;
let marker;
let headingLine;

function updateMap() {
  fetch("/api/position")
    .then((res) => res.json())
    .then((data) => {
      const lat = data.lat;
      const lon = data.lon;
      const heading = data.heading;

      if (!map) {
        map = L.map("map").setView([lat, lon], 18);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: "© OpenStreetMap contributors",
        }).addTo(map);
        marker = L.marker([lat, lon]).addTo(map);
      } else {
        map.setView([lat, lon]);
        marker.setLatLng([lat, lon]);
      }

      // 方位線の更新
      if (headingLine) {
        map.removeLayer(headingLine);
      }
      const length = 0.0009; // 約100m程度、地図上の表示バランスに応じて調整
      const lat2 = lat + length * Math.cos((heading * Math.PI) / 180);
      const lon2 = lon + length * Math.sin((heading * Math.PI) / 180);
      headingLine = L.polyline([[lat, lon], [lat2, lon2]], {
        color: "red",
        weight: 2,
      }).addTo(map);
    });
}

setInterval(updateMap, 2000); // 2秒ごとに更新
