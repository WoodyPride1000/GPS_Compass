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

      document.getElementById("coords").textContent = `Lat: ${base.lat.toFixed(6)}, Lon: ${base.lon.toFixed(6)}`;
      document.getElementById("heading").textContent = `Heading: ${heading.toFixed(1)}°`;
      document.getElementById("error").textContent = `Error: ${error.toFixed(2)} m`;

      if (!map) {
        map = L.map("map").setView([base.lat, base.lon], 19);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: "© OpenStreetMap contributors"
        }).addTo(map);

        baseMarker = L.marker([base.lat, base.lon]).addTo(map).bindPopup("Base").openPopup();
        roverMarker = L.marker([rover.lat, rover.lon]).addTo(map).bindPopup("Rover");
      } else {
        baseMarker.setLatLng([base.lat, base.lon]);
        roverMarker.setLatLng([rover.lat, rover.lon]);
      }

      if (headingLine) {
        map.removeLayer(headingLine);
      }

      // 方位線（base → rover）
      headingLine = L.polyline([[base.lat, base.lon], [rover.lat, rover.lon]], {
        color: "red",
        weight: 2
      }).addTo(map);
    });
}

setInterval(updateMap, 1000);









