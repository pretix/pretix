/*globals $*/

$(function () {
  var j = 0;
  $(".geodata-section").each(function () {
    var $sec = $(this);
    var $inp = $(this).find("textarea[lang=en], input[lang=en]").first();
    if ($inp.length === 0) {
      $inp = $(this).find("textarea, input").first();
    }
    var timer;
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
        }
        $sec.find(".col-md-1").html("");
      })
    }
    $sec.find("input[name$=geo_lat], input[name$=geo_lon]").change(function () {
      touched = $sec.find("input[name$=geo_lat]").val() !== "";
    });

    $inp.change(load);
    $inp.keyup(function () {
      if (timer) {
        window.clearTimeout(timer);
      }
      timer = window.setTimeout(load, 1000);
    });

  });
});
