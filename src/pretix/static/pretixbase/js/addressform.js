$(function () {
    "use strict";

    // Responses are expected to only depend on the GET parameters passed, so we can have a little client-side cache
    // to prevent fetching the same thing many times.
    var responseCache = {};

    const cleanName = (name) => {
        // Remove form prefix
        name = name.split("-").pop();
        // Remove settings prefix
        name = name.replace(/^invoice_address_from_/, "");
        return name
    }

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
            dependents[cleanName($(this).attr("name"))] = $(this)
        })

        if (!Object.values(dependents).some((el) => el.length)) {
            // No address fields found, do not create request
            return;
        }

        const update_form = function (data) {
            var selected_state = dependents.state.prop("data-selected-value");
            if (selected_state) dependents.state.prop("data-selected-value", "");
            dependents.state.find("option:not([value=''])").remove();
            $.each(data.data, function (k, s) {
                var o = $("<option>").attr("value", s.code).text(s.name);
                if (selected_state === s.code) o.prop("selected", true);
                dependents.state.append(o);
            });

            if (dependents.transmission_type) {
                var selected_transmission_type = dependents.transmission_type.prop("data-selected-value");
                if (selected_transmission_type) dependents.transmission_type.prop("data-selected-value", "");
                dependents.transmission_type.find("option:not([value='']):not([value='-'])").remove();

                if (!data.transmission_type.visible) {
                    selected_transmission_type = "email";
                }

                $.each(data.transmission_types, function (k, s) {
                    var o = $("<option>").attr("value", s.code).text(s.name);
                    if (selected_transmission_type === s.code) {
                        o.prop("selected", true);
                    }
                    dependents.transmission_type.append(o);
                });

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
                if ('helptext_visible' in options) {
                    dependent.closest(".form-group").find(".help-block").toggle(options.helptext_visible);
                }

                const required = 'required' in options && visible && (
                    (options.required === 'if_any' && isAnyRequired) ||
                    (options.required === true)
                );
                dependent.closest(".form-group").toggle(visible).toggleClass('required', required);
                dependent.prop("required", required);

                const label = dependent.closest(".form-group").find("label");
                const labelRequired = label.find(".label-required");
                if (!required) {
                    labelRequired.remove();
                } else if (!labelRequired.length) {
                    label.append('<i class="label-required">' + gettext('required') + '</i>')
                }
            }
            for (var k in dependents) dependents[k].prop("disabled", false);
            loader.hide();
        }

        const update = function (ev) {
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
                url.searchParams.append(cleanName($(this).attr("name")), $(this).val());
            })
            if (dependents.transmission_type) {
                url.searchParams.append("transmission_type_required", !dependents.transmission_type.find("option[value='-']").length);
            }

            if (xhr && url in responseCache) {
                if (responseCache[url] == xhr) {
                    // already requested this, but XHR is still running and will resolve promise
                    // only re-resolve promise for JSON-data in responseCache[url]
                    return;
                } else {
                    // abort current xhr as it is not the one we want
                    // aborting deletes responseCache[url] but async
                    xhr.abort();
                }
            }

            if (!(url in responseCache)) {
                responseCache[url] = xhr = $.ajax({
                    dataType: "json",
                    url: url,
                    timeout: 3000,
                });
            }

            Promise.resolve(responseCache[url]).then(function (data) {
                responseCache[url] = data;
                update_form(data);
            }).catch(function () {
                delete responseCache[url];
                // In case of errors, show everything and require nothing, we can still handle errors in backend
                for (var k in dependents) {
                    const dependent = dependents[k],
                        visible = true,
                        required = false;

                    dependent.closest(".form-group").toggle(visible).toggleClass('required', required);
                    dependent.prop("required", required).prop("disabled", false);
                }
            }).finally(function () {
                loader.hide();
            });
        };
        update();
        dependencies.on("change", update);

        if (dependents.vat_id && dependents.transmission_type && dependents.transmission_peppol_participant_id) {
            // In Belgium, the VAT ID is built from "BE" + the company ID. The Peppol ID also needs to be built
            // from the company ID with ID scheme 0208. We can save users some knowing and typing by filling this in!
            if (!dependents.transmission_peppol_participant_id.val()) {
                const fill_peppol_id = function () {
                    const vatId = dependents.vat_id.val();
                    if (vatId && vatId.startsWith("BE") && dependents.transmission_type.val() === "peppol" && autofill_peppol_id) {
                        dependents.transmission_peppol_participant_id.val("0201:" + vatId.substring(2))
                    }
                }
                dependents.vat_id.add(dependents.transmission_type).on("change", fill_peppol_id);
                dependents.transmission_peppol_participant_id.one("change", () => {
                    dependents.vat_id.add(dependents.transmission_type).unbind("change", fill_peppol_id)
                });
            }
        }
    });

});
