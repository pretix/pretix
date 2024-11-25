$(function () {
    "use strict";

    $("select[name$=state]:not([data-static])").each(function () {
        var dependent = $(this),
            counter = 0,
            dependency = $(this).closest(".panel-body, form").find('select[name$=country]'),
            depRequired = dependency.closest(".form-group").is(".required"),
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
                        dependent.closest(".form-group").show().toggleClass('required', depRequired);
                        dependent.prop('required', depRequired);
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
            dependent.closest(".form-group").toggleClass('required', depRequired);
            dependent.prop('required', depRequired);
        }
        dependency.on("change", update);
    });

    $("input[name$=vat_id][data-countries-with-vat-id]").each(function () {
        var dependent = $(this),
            dependency_country = $(this).closest(".panel-body, form").find('select[name$=country]'),
            dependency_id_is_business_1 = $(this).closest(".panel-body, form").find('input[id$=id_is_business_1]'),
            update = function (ev) {
                if (dependency_id_is_business_1.length && !dependency_id_is_business_1.prop("checked")) {
                    dependent.closest(".form-group").hide();
                } else if (dependent.attr('data-countries-with-vat-id').split(',').includes(dependency_country.val())) {
                    dependent.closest(".form-group").show();
                } else {
                    dependent.closest(".form-group").hide();
                }
            };
        update();
        dependency_country.on("change", update);
        dependency_id_is_business_1.on("change", update);
    });

});
