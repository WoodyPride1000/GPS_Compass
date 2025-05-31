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
      const error = data.error;

      document.getElementById("coords").textContent = `Lat: ${lat.toFixed(6)}, Lon: ${lon.toFixed(6)}`;
      document.getElementById("heading").textContent = `Heading: ${heading.toFixed(1)}°`;
      document.getElementById("error").textContent = `Error: ${error.toFixed(2)} m`;

      if (!map) {
        map = L.map("map").setView([lat, lon], 19);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: "© OpenStreetMap contributors"
        }).addTo(map);
        marker = L.marker([lat, lon]).addTo(map);
      } else {
        marker.setLatLng([lat, lon]);
      }

      if (headingLine) {
        map.removeLayer(headingLine);
      }

      const length = 0.0002; // 約20m相当の線
      const lat2 = lat + length * Math.cos((heading * Math.PI) / 180);
      const lon2 = lon + length * Math.sin((heading * Math.PI) / 180);

      headingLine = L.polyline([[lat, lon], [lat2, lon2]], {
        color: "red",
        weight: 2
      }).addTo(map);
    });
}

setInterval(updateMap, 1000);  // 1秒ごとに更新
