$(function () {
    "use strict";

    $("select[data-country-information-url]").each(function () {
        let xhr;
        const dependency = $(this),
            loader = $("<span class='fa fa-cog fa-spin'></span>").hide().prependTo(dependency.closest(".form-group").find("label")),
            url = this.getAttribute('data-country-information-url'),
            form = dependency.closest(".panel-body, form, .profile-scope"),
            isRequired = dependency.closest(".form-group").is(".required"),
            dependents =  {
                'city': form.find("input[name$=city]"),
                'zipcode': form.find("input[name$=zipcode]"),
                'street': form.find("textarea[name$=street]"),
                'state': form.find("select[name$=state]"),
                'vat_id': form.find("input[name$=vat_id]"),
            },
            update = function (ev) {
                if (xhr) {
                    xhr.abort();
                }
                for (var k in dependents) dependents[k].prop("disabled", true);
                loader.show();
                xhr = $.getJSON(url + '?country=' + dependency.val(), function (data) {
                    var selected_value = dependents.state.prop("data-selected-value");
                    if (selected_value) dependents.state.prop("data-selected-value", "");
                    dependents.state.find("option:not([value=''])").remove();
                    if (data.data.length > 0) {
                        $.each(data.data, function (k, s) {
                            var o = $("<option>").attr("value", s.code).text(s.name);
                            if (selected_value == s.code) o.prop("selected", true);
                            dependents.state.append(o);
                        });
                    }
                    for(var k in dependents) {
                        const options = data[k],
                            dependent = dependents[k];
                        let visible = 'visible' in options ? options.visible : true;

                        if (dependent.is("[data-display-dependency]")) {
                            const dependency = $(dependent.attr("data-display-dependency"));
                            visible = visible && (
                                (dependency.attr("type") === 'checkbox' || dependency.attr("type") === 'radio') ? dependency.prop('checked') : !!dependency.val()
                            );
                        }

                        const required = 'required' in options && options.required && isRequired && visible;
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
        dependents.state.prop("data-selected-value", dependents.state.val());
        update();
        dependency.on("change", update);
    });

});
