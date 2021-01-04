/*globals $*/

$(function () {
  var j = 0;
  $(".geodata-section").each(function () {
    // Geocoding
    var $sec = $(this);
    var $inp = $(this).find("textarea[lang=en], input[lang=en]").first();
    if ($inp.length === 0) {
      $inp = $(this).find("textarea, input").first();
    }
    var timer, timer2;
    var touched = $sec.find("input[name$=geo_lat]").val() !== "";

    function load() {
      window.clearTimeout(timer);
      var q = $.trim($inp.val().replace(/\n/g, ", "));
      if ((touched && $sec.find("input[name$=geo_lat]").val() !== "") || $.trim(q) === "") {
        return;
      }
      $sec.find(".col-md-1").html("<span class='fa fa-cog fa-spin'></span>");
      $.getJSON('/control/geocode/?q=' + escape(q), function (res) {
        var q2 = $.trim($inp.val().replace(/\n/g, ", "));
        if (q2 !== q) {
          return;  // lost race
        }
        if (res.results) {
          $sec.find("input[name$=geo_lat]").val(res.results[0].lat);
          $sec.find("input[name$=geo_lon]").val(res.results[0].lon);
          center(13);
        }
        $sec.find(".col-md-1").html("");
      })
    }

    $sec.find("input[name$=geo_lat], input[name$=geo_lon]").change(function () {
      touched = $sec.find("input[name$=geo_lat]").val() !== "";
      center(13);
    }).keyup(function () {
      if (timer2) {
        window.clearTimeout(timer2);
      }
      timer2 = window.setTimeout(center, 300);
    });

    $inp.change(load);
    $inp.keyup(function () {
      if (timer) {
        window.clearTimeout(timer);
      }
      timer = window.setTimeout(load, 1000);
    });

    // Map
    var $grp = $sec.find(".geodata-group");
    var tiles = $grp.attr("data-tiles");
    var attrib = $grp.attr("data-attrib");
    if (tiles) {
      var $map = $("<div>");
      $grp.append($("<div>").addClass("col-md-9 col-md-offset-3").append($map));
      var map = L.map($map.get(0));
      L.tileLayer(tiles, {
        attribution: attrib,
        maxZoom: 18,
      }).addTo(map);
      var $lat = $sec.find("input[name$=geo_lat]");
      var $lon = $sec.find("input[name$=geo_lon]");

      function getpoint() {
        if ($lat.val() !== "" && $lon.val() !== "") {
          var p = [parseFloat($lat.val().replace(",", ".")), parseFloat($lon.val().replace(",", "."))];
          // Clip to valid ranges. Very invalid lon/lat values can even lead to browser crashes in leaflet apparently
          if (p[0] < -90) p[0] = -90
          if (p[0] > 90) p[0] = 90
          if (p[1] < -180) p[1] = -180
          if (p[1] > 180) p[1] = 180
          return p
        } else {
          return [0.0, 0.0];
        }
      }

      var marker = L.marker(getpoint(), {
        draggable: 'true',
        icon: L.icon({
          iconUrl: $grp.attr("data-icon"),
          shadowUrl: $grp.attr("data-shadow"),
          iconSize: [25, 41],
          iconAnchor: [12, 41],
          popupAnchor: [1, -34],
          tooltipAnchor: [16, -28],
          shadowSize: [41, 41]
        })
      });
      marker.addTo(map);
      marker.on("dragend", function (event) {
        var position = marker.getLatLng();
        marker.setLatLng(position, {
          draggable: 'true'
        }).bindPopup(position).update();
        $lat.val(position.lat.toFixed(7));
        $lon.val(position.lng.toFixed(7));
        center(null);
      });

      function center(zoom) {
        if ($lat.val() !== "" && $lon.val() !== "") {
          if (zoom) {
            map.setView(getpoint(), zoom);
          } else {
            map.panTo(getpoint());
          }
          marker.setLatLng(getpoint(), {
            draggable: 'true'
          }).bindPopup(getpoint()).update();
        } else {
          map.fitWorld();
        }
      }

      center(13);
    } else {
      function center(zoom) {
      }
    }

  });
});
