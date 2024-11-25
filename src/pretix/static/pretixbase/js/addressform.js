$(function () {
    "use strict";

    $("select[data-country-information-url]").each(function () {
        let counter = 0;
        const dependency = $(this),
            url = this.getAttribute('data-country-information-url'),
            form = $(this).closest(".panel-body, form"),
            isRequired = dependency.closest(".form-group").is(".required"),
            dependents =  {
                'city': form.find("input[name$=city]"),
                'zipcode': form.find("input[name$=zipcode]"),
                'street': form.find("textarea[name$=street]"),
                'state': form.find("select[name$=state]"),
                'vat_id': form.find("input[name$=vat_id]"),
            },
            update = function (ev) {
                counter++;
                const curCounter = counter;
                for (var k in dependents) dependents[k].prop("disabled", true);
                dependency.closest(".form-group").find("label").prepend("<span class='fa fa-cog fa-spin'></span> ");
                $.getJSON(url + '?country=' + dependency.val(), function (data) {
                    if (counter > curCounter) {
                        return;  // Lost race
                    }
                    var selected_value = dependents.state.prop("data-selected-value");
                    dependents.state.find("option").filter(function (t) {return !!$(this).attr("value")}).remove();
                    if (data.data.length > 0) {
                        $.each(data.data, function (k, s) {
                            var o = $("<option>").attr("value", s.code).text(s.name);
                            if (s.code == selected_value || (selected_value && selected_value.indexOf && selected_value.indexOf(s.code) > -1)) {
                                o.prop("selected", true);
                            }
                            dependents.state.append(o);
                        });
                    }
                    for(var k in dependents) {
                        const options = data[k], dependent = dependents[k]; console.log(options, dependent)
                        if ('visible' in options) {
                            if (options.visible) {
                                dependent.closest(".form-group").show().toggleClass('required', isRequired);
                                dependent.prop('required', isRequired);
                            } else {
                                dependent.closest(".form-group").hide();
                                dependent.prop("required", false);
                            }
                        }
                        if ('required' in options) {
                            dependent.closest(".form-group").toggleClass('required', options.required && isRequired);
                            dependent.prop('required', options.required && isRequired);
                        }
                    }
                    for (var k in dependents) dependents[k].prop("disabled", false);
                    dependency.closest(".form-group").find("label .fa-spin").remove();
                });
            };
        update();
        dependency.on("change", update);
    });

});
