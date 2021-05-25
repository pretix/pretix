/*globals $*/

$(document).on("pretix:bind-forms", function () {
    function cleanup(l) {
        return $.trim(l.replace(/\n/g, ", "));
    }
    $(".geodata-section").each(function () {
        // Geocoding
        // detach notifications and append them to first label (should be from location)
        var $notifications = $(".geodata-autoupdate", this).detach().appendTo($("label", this).first());
        var $lat = $("input[name$=geo_lat]", this).first();
        var $lon = $("input[name$=geo_lon]", this).first();
        var lat;
        var lon;
        var $updateButton = $("[data-action=update]", this);
        var $location = $("textarea[lang=en], input[lang=en]", this).first();
        if (!$location.length) $location = $("textarea, input[type=text]", this).first();

        if (!$lat.length || !$lon.length || !$location.length) {
            return;
        }

        var debounceLoad, debounceLatLonChange, delayUpdateDismissal;
        var touched = $lat.val() !== "";
        var xhr;
        var lastLocation = cleanup($location.val());

        function load() {
            window.clearTimeout(debounceLoad);
            if (xhr) {
                xhr.abort();
                xhr = null;
            }

            var q = cleanup($location.val());
            if (q === "" || q === lastLocation) return;

            lastLocation = q;
            $notifications.attr("data-notify", "loading");

            xhr = $.getJSON('/control/geocode/?q=' + encodeURIComponent(q), function (res) {
                if (!res.results || !res.results.length) {
                    $notifications.attr("data-notify", "error");
                    return;
                }

                lat = res.results[0].lat;
                lon = res.results[0].lon;
                if ($lat.val() == lat && $lon.val() == lon) {
                    $notifications.attr("data-notify", "");
                }
                else if (touched) {
                    $notifications.attr("data-notify", "confirm");
                }
                else {
                    $notifications.attr("data-notify", "");
                    $lat.val(lat);
                    $lon.val(lon);
                    center(13);
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
            window.clearTimeout(debounceLoad);
            debounceLoad = window.setTimeout(load, 1000);
            if ($notifications.attr("data-notify") == "confirm" && lastLocation !== cleanup(this.value)) $notifications.attr("data-notify", "");
        });

        $updateButton.click(function() {
            $lat.val(lat);
            $lon.val(lon).trigger("change");// change-event is needed by bulk-edit
            touched = false;
            center(13);
            $notifications.attr("data-notify", "updated");
            delayUpdateDismissal = window.setTimeout(function() {
                if ($notifications.attr("data-notify") == "updated") $notifications.attr("data-notify", "");
            }, 2500);
        });

        // Map
        var $grp = $(".geodata-group", this);
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
