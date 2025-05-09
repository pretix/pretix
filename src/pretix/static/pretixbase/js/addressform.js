$(function () {
    "use strict";

    $("[data-address-information-url]").each(function () {
        let xhr;
        const form = $(this);
        const dependencies = $(this).find("[data-trigger-address-info]");
        const loader = $("<span class='fa fa-cog fa-spin'></span>").hide().prependTo(dependencies.closest(".form-group").find("label").first())
        const baseUrl = this.getAttribute('data-address-information-url')
        const isAnyRequired = dependencies.toArray().some(function (e) { return $(e).closest(".form-group").is(".required") });

        const dependents =  {
            'city': form.find("input[name$=city]"),
            'zipcode': form.find("input[name$=zipcode]"),
            'street': form.find("textarea[name$=street]"),
            'state': form.find("select[name$=state]"),
            'vat_id': form.find("input[name$=vat_id]"),
        };

        form.find("select[name*=transmission_], textarea[name*=transmission_], input[name*=transmission_]").each(function () {
            dependents[$(this).attr("name").split("-").pop()] = $(this)
        })

        const update = function (ev) {
            if (xhr) {
                xhr.abort();
            }

            dependents.state.prop("data-selected-value", dependents.state.val());
            if (dependents.transmission_type) {
                dependents.transmission_type.prop("data-selected-value", dependents.transmission_type.val());
            }

            for (var k in dependents) dependents[k].prop("disabled", true);
            loader.show();
            var url = new URL(baseUrl, location.href);
            // Address depends on all annotated fields
            form.find("[data-trigger-address-info]").each(function () {
                // Remove prefix of the form to get actual field name
                if (($(this).attr("type") === "radio" || $(this).attr("type") === "checkbox") && !$(this).prop("checked")) {
                    return
                }
                url.searchParams.append($(this).attr("name").split("-").pop(), $(this).val());
            })
            xhr = $.getJSON(url, function (data) {
                var selected_state = dependents.state.prop("data-selected-value");
                if (selected_state) dependents.state.prop("data-selected-value", "");
                dependents.state.find("option:not([value=''])").remove();
                if (data.data.length > 0) {
                    $.each(data.data, function (k, s) {
                        var o = $("<option>").attr("value", s.code).text(s.name);
                        if (selected_state === s.code) o.prop("selected", true);
                        dependents.state.append(o);
                    });
                }

                if (dependents.transmission_type) {
                    var selected_transmission_type = dependents.transmission_type.prop("data-selected-value");
                    if (selected_transmission_type) dependents.transmission_type.prop("data-selected-value", "");
                    dependents.transmission_type.find("option:not([value=''])").remove();
                    if (data.transmission_types.length > 0) {
                        $.each(data.transmission_types, function (k, s) {
                            var o = $("<option>").attr("value", s.code).text(s.name);
                            if (selected_transmission_type === s.code) {
                                o.prop("selected", true);
                            }
                            dependents.transmission_type.append(o);
                        });
                    }
                }

                for (var k in dependents) {
                    const options = data[k],
                        dependent = dependents[k];
                    let visible = 'visible' in options ? options.visible : true;

                    if (dependent.is("[data-display-dependency]")) {
                        const dependency = $(dependent.attr("data-display-dependency"));
                        visible = visible && (
                            (dependency.attr("type") === 'checkbox' || dependency.attr("type") === 'radio') ? dependency.prop('checked') : !!dependency.val()
                        );
                    }

                    if ('label' in options) {
                        dependent.closest(".form-group").find(".control-label").text(options.label);
                    }

                    const required = 'required' in options && options.required && isAnyRequired && visible;
                    dependent.closest(".form-group").toggle(visible).toggleClass('required', required);
                    dependent.prop("required", required);
                }
                for (var k in dependents) dependents[k].prop("disabled", false);
            }).always(function() {
                loader.hide();
            }).fail(function(){
                // In case of errors, show everything and require nothing, we can still handle errors in backend
                for(var k in dependents) {
                    const dependent = dependents[k],
                        visible = true,
                        required = false;

                    dependent.closest(".form-group").toggle(visible).toggleClass('required', required);
                    dependent.prop("required", required);
                }
            });
        };
        update();
        dependencies.on("change", update);
    });

});
