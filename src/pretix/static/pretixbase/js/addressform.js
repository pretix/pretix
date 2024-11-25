$(function () {
    "use strict";

    $("select[name$=state]:not([data-static])").each(function () {
        var dependent = $(this),
            counter = 0,
            dependency = $(this).closest(".panel-body, form").find('select[name$=country]'),
            update = function (ev) {
                counter++;
                var curCounter = counter;
                dependent.prop("disabled", true);
                dependency.closest(".form-group").find("label").prepend("<span class='fa fa-cog fa-spin'></span> ");
                $.getJSON('/js_helpers/states/?country=' + dependency.val(), function (data) {
                    if (counter > curCounter) {
                        return;  // Lost race
                    }
                    var selected_value = dependent.prop("data-selected-value");
                    dependent.find("option").filter(function (t) {return !!$(this).attr("value")}).remove();
                    if (data.data.length > 0) {
                        $.each(data.data, function (k, s) {
                            var o = $("<option>").attr("value", s.code).text(s.name);
                            if (s.code == selected_value || (selected_value && selected_value.indexOf && selected_value.indexOf(s.code) > -1)) {
                                o.prop("selected", true);
                            }
                            dependent.append(o);
                        });
                        dependent.closest(".form-group").show();
                        dependent.prop('required', dependency.prop("required"));
                    } else {
                        dependent.closest(".form-group").hide();
                        dependent.prop("required", false);
                    }
                    dependent.prop("disabled", false);
                    dependency.closest(".form-group").find("label .fa-spin").remove();
                });
            };
        if (dependent.find("option").length === 1) {
            dependent.closest(".form-group").hide();
        } else {
            dependent.prop('required', dependency.prop("required"));
        }
        dependency.on("change", update);
    });
});
