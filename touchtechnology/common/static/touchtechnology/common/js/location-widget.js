document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".location-widget").forEach(function (elem) {
    var inputs = elem.querySelectorAll(".location-widget-inputs input");
    var latitude = inputs[0];
    var longitude = inputs[1];
    var zoom = inputs[2];
    var toggle = elem.querySelector(".location-widget-toggle");
    var canvas = elem.querySelector(".location-widget-map");
    var defaultZoom = parseInt(canvas.getAttribute("data-zoom"), 10);
    var marker = null;

    var map = L.map(canvas);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    function position() {
      var lat = parseFloat(latitude.value);
      var lng = parseFloat(longitude.value);
      if (isFinite(lat) && isFinite(lng)) {
        return L.latLng(lat, lng);
      }
      return null;
    }

    function storedZoom() {
      var value = parseInt(zoom.value, 10);
      return isFinite(value) ? value : defaultZoom;
    }

    function record(latlng) {
      latitude.value = latlng.lat.toFixed(6);
      longitude.value = latlng.lng.toFixed(6);
      zoom.value = map.getZoom();
    }

    function place(latlng) {
      if (marker) {
        marker.setLatLng(latlng);
        return;
      }
      marker = L.marker(latlng, { draggable: true }).addTo(map);
      marker.on("dragend", function () {
        record(marker.getLatLng());
      });
    }

    var initial = position();
    if (initial) {
      map.setView(initial, storedZoom());
      place(initial);
    } else {
      map.setView([0, 0], 1);
    }

    map.on("click", function (e) {
      place(e.latlng);
      record(e.latlng);
    });

    map.on("zoomend", function () {
      if (marker) {
        zoom.value = map.getZoom();
      }
    });

    [latitude, longitude, zoom].forEach(function (input) {
      input.addEventListener("change", function () {
        var latlng = position();
        if (latlng) {
          place(latlng);
          map.setView(latlng, storedZoom());
        }
      });
    });

    // The inputs are locked by default so the map is the way to pick a
    // location; the toggle unlocks them for typing exact coordinates.
    function setLocked(locked) {
      [latitude, longitude, zoom].forEach(function (input) {
        input.readOnly = locked;
      });
      toggle.textContent = locked ? "Edit" : "Lock";
      toggle.setAttribute("aria-pressed", locked ? "false" : "true");
    }

    toggle.addEventListener("click", function () {
      setLocked(!latitude.readOnly);
    });
    toggle.hidden = false;
    setLocked(true);

    // The map may start inside a hidden tab; redraw once it becomes visible.
    if (window.ResizeObserver) {
      new ResizeObserver(function () {
        map.invalidateSize();
      }).observe(canvas);
    }
  });
});
