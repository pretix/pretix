/*globals $*/

$(function () {
    $(".geodata-section").each(function () {
        // Geocoding
        var $sec = $(this);
        //var $notifications = $(".geodata-autoupdate", this);
        var $lat = $("input[name$=geo_lat]", this).first();
        var $lon = $("input[name$=geo_lon]", this).first();
        var lat;
        var lon;
        var $location = $("textarea[lang=en], input[lang=en]", this).first();
        var $updateButton = $("[data-action=update]", this);

        if (!$location.length) {
            $location = $("textarea, input[type=text]", this).first();
        }
        if (!$lat.length || !$lon.length || !$location.length) {
            return;
        }

        var debounceLocationChange, debounceLatLonChange, delayLoadingIndicator, delayUpdateDismissal;
        var touched = $lat.val() !== "";
        var xhr;
        var lastLocation;

        function load() {
            window.clearTimeout(debounceLocationChange);

            var q = $.trim($location.val().replace(/\n/g, ", "));
            if (q === "" || q === lastLocation) return;
            lastLocation = q;

            window.clearTimeout(delayLoadingIndicator);
            delayLoadingIndicator = window.setTimeout(function() {
                $sec.removeClass("notify-updated").addClass("notify-loading");
            }, 1000);

            if (xhr) xhr.abort();

            xhr = $.getJSON('/control/geocode/?q=' + encodeURIComponent(q), function (res) {
                var q2 = $.trim($location.val().replace(/\n/g, ", "));
                window.clearTimeout(delayLoadingIndicator);
                $sec.removeClass("notify-updated").removeClass("notify-loading");
                if (q2 !== q) {
                    return;  // lost race
                }
                if (res.results && res.results.length) {
                    if (touched) {
                        $sec.addClass("notify-triggered");
                        lat = res.results[0].lat;
                        lon = res.results[0].lon;
                    }
                    else {
                        $lat.val(res.results[0].lat);
                        $lon.val(res.results[0].lon);
                        center(13);
                    }
                }
                else {
                    $sec.addClass("notify-error");
                }
            })
        }

        $lat.add($lon).change(function () {
            if (this.value !== "") touched = true;
            center(13);
        }).keyup(function () {
            window.clearTimeout(debounceLatLonChange);
            debounceLatLonChange = window.setTimeout(center, 300);
        });

        $location.change(load);
        $location.keyup(function () {
            window.clearTimeout(debounceLocationChange);
            debounceLocationChange = window.setTimeout(load, 1000);
        });

        $updateButton.click(function() {
            $lat.val(lat);
            $lon.val(lon).trigger("change");
            touched = false;
            center(13);
            $sec.addClass("notify-updated").removeClass("notify-triggered");
            delayUpdateDismissal = window.setTimeout(function() {
                $sec.removeClass("notify-updated");
            }, 2500);
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
                touched = true;
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
