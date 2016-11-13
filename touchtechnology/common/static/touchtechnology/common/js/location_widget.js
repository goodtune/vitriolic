var maps;


function initialize() {
  maps = forEach(
    document.getElementsByClassName('mapwidget'),
    location_widget);
}


var forEach = function forEach(a, f) {
  var r = new Array(a.length);
  for (var i=0; i<a.length; i++) {
    var e = a[i];
    r[i] = f(e, i, a);
  }
  return r;
}


var location_widget = function location_widget(elem) {
  var fields = elem.getElementsByTagName('input');

  // inject a div into the DOM which will contain the map
  var div = document.createElement("div");
  div.setAttribute("class", "map form-control");
  elem.insertBefore(div, fields[0]);

  // store values for easier substitution
  var latitude = parseFloat(fields[0].getAttribute('value')) || 0;
  var longitude = parseFloat(fields[1].getAttribute('value')) || 0;
  var zoom = parseInt(fields[2].getAttribute('value'), 10) || 0;

  var initial = true;

  if (!latitude && !longitude) {
    initial = false;
    if (google.loader && google.loader.ClientLocation) {
      latitude = google.loader.ClientLocation.latitude;
      longitude = google.loader.ClientLocation.longitude;
    }
    else {
      // Sydney Harbour Bridge
      latitude = -33.85241918266747;
      longitude = 151.2106704711914;
      // Zoom quite a long way out, only want to indicate "Sydney"
      zoom = 8;
    }
  }

  if (!zoom) {
    zoom = 10;
  }

  // Set the values back to the input fields since we may not have
  // actually obtained them from the user.
  fields[0].setAttribute('value', latitude);
  fields[1].setAttribute('value', longitude);
  fields[2].setAttribute('value', zoom);

  // create a point to centre and drop a marker on a map
  var latlng = new google.maps.LatLng(latitude, longitude);

  // options for the map creation
  var options = {
    center: latlng,
    zoom: zoom,
    mapTypeId: google.maps.MapTypeId.ROADMAP,
    mapTypeControl: true,
    mapTypeControlOptions: {
      style: google.maps.MapTypeControlStyle.DROPDOWN_MENU
    }
  };

  // create the map and add the marker
  var map = new google.maps.Map(div, options);
  var marker = new google.maps.Marker({
    position: latlng,
    draggable: true,
    map: map
  });

  var markerMoved = function markerMoved(position) {
    fields[0].value = position.latLng.lat();
    fields[1].value = position.latLng.lng();
    map.panTo(position.latLng);
  };

  if (!initial && navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      function(position) {
        latlng = new google.maps.LatLng(
          position.coords.latitude,
          position.coords.longitude);
        marker.setPosition(latlng);
        marker.map.setCenter(latlng);
        marker.map.setZoom(13);
        markerMoved({
          latLng: latlng
        });
      },
      function(error) {
        // do nothing
      },
      {
        enableHighAccuracy: true
      }
    );
  }

  // bind events to update the fields
  google.maps.event.addListener(marker, 'dragend', markerMoved);

  google.maps.event.addListener(map, 'zoom_changed', function() {
    fields[2].value = map.getZoom();
  });

  return map;
}


google.maps.event.addDomListener(window, 'load', initialize);
