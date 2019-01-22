/*global django*/
var roundTo = function (n, digits) {
    if (digits === undefined) {
        digits = 0;
    }

    var multiplicator = Math.pow(10, digits);
    n = parseFloat((n * multiplicator).toFixed(11));
    return Math.round(n) / multiplicator;
};


var floatformat = function (val, places) {
    "use strict";
    if (places === undefined) {
        places = 2;
    }
    if (typeof val === "string") {
        val = parseFloat(val);
    }
    var parts = roundTo(val, places).toFixed(places).split(".");
    if (places === 0) {
        return parts[0];
    }
    parts[0] = parts[0].replace(new RegExp("\\B(?=(\\d{" + django.get_format("NUMBER_GROUPING") + "})+(?!\\d))", "g"), django.get_format("THOUSAND_SEPARATOR"));
    return parts[0] + django.get_format("DECIMAL_SEPARATOR") + parts[1];
};


var autofloatformat = function (val, places) {
    "use strict";
    if (val == roundTo(val, 0)) {
        places = 0;
    }
    return floatformat(val, places);
};
