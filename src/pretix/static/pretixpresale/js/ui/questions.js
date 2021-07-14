/*global $ */

function questions_toggle_dependent(ev) {
    function q_should_be_shown($el) {
        if (!$el.attr('data-question-dependency')) {
            return true;
        }

        var dependency_name = $el.attr("name").split("_")[0] + "_" + $el.attr("data-question-dependency");
        var dependency_values = JSON.parse($el.attr("data-question-dependency-values"));
        var $dependency_el;

        if ($("select[name=" + dependency_name + "]").length) {
            // dependency is type C
            $dependency_el = $("select[name=" + dependency_name + "]");
            if (!$dependency_el.closest(".form-group").hasClass("dependency-hidden")) {  // do not show things that depend on hidden things
                return q_should_be_shown($dependency_el) && $.inArray($dependency_el.val(), dependency_values) > -1;
            }
        } else if ($("input[type=checkbox][name=" + dependency_name + "]").length) {
            // dependency type is B or M
            if ($.inArray("True", dependency_values) > -1 || $.inArray("False", dependency_values) > -1) {
                $dependency_el = $("input[name=" + dependency_name + "]");
                if (!$dependency_el.closest(".form-group").hasClass("dependency-hidden")) {  // do not show things that depend on hidden things
                    return q_should_be_shown($dependency_el) && (
                        ($.inArray("True", dependency_values) > -1 && $dependency_el.prop('checked'))
                        || ($.inArray("False", dependency_values) > -1 && !$dependency_el.prop('checked'))
                    );
                }
            } else {
                var filter = "";
                for (var i = 0; i < dependency_values.length; i++) {
                    if (filter) filter += ", ";
                    filter += "input[value=" + dependency_values[i] + "][name=" + dependency_name + "]:checked";
                }
                $dependency_el = $("input[value=" + dependency_values[0] + "][name=" + dependency_name + "]");
                if (!$dependency_el.closest(".form-group").hasClass("dependency-hidden")) {  // do not show things that depend on hidden things
                    return q_should_be_shown($dependency_el) && $(filter).length;
                }
            }
        }
    }

    $("[data-question-dependency]").each(function () {
        var $dependent = $(this).closest(".form-group");
        var is_shown = !$dependent.hasClass("dependency-hidden");
        var should_be_shown = q_should_be_shown($(this));

        if (should_be_shown && !is_shown) {
            $dependent.stop().removeClass("dependency-hidden");
            if (!ev) {
                $dependent.show();
            } else {
                $dependent.slideDown();
            }
            $dependent.find("input.required-hidden, select.required-hidden, textarea.required-hidden").each(function () {
                $(this).prop("required", true).removeClass("required-hidden");
            });
        } else if (!should_be_shown && is_shown) {
            if ($dependent.hasClass("has-error") || $dependent.find(".has-error").length) {
                // Do not hide things with invalid validation
                return;
            }
            $dependent.stop().addClass("dependency-hidden");
            if (!ev) {
                $dependent.hide();
            } else {
                $dependent.slideUp();
            }
            $dependent.find("input[required], select[required], textarea[required]").each(function () {
                $(this).prop("required", false).addClass("required-hidden");
            });
        }
    });
}

function questions_init_photos(el) {
    if (!FileReader) {
        // No browser support
        return
    }

    el.find("input[data-portrait-photo]").each(function () {
        var $inp = $(this)
        var $container = $inp.parent().parent()

        $container.find(".photo-input").addClass("hidden")
        $container.find(".photo-buttons").removeClass("hidden")

        $container.find("button[data-action=upload]").click(function () {
            $inp.click();
        })

        var cropper = new Cropper($container.find(".photo-preview img").get(0), {
            aspectRatio: 3 / 4,
            viewMode: 1,
            zoomable: false,
            crop: function (event) {
                $container.find("input[type=hidden]").val(JSON.stringify(cropper.getData(true)));
            },
        });
        /* This rule is very important, please don't ignore this */

        $inp.on("change", function () {
            if (!$inp.get(0).files[0]) return
            $container.find("button[data-action=upload]").append("<span class='fa fa-spin fa-cog'></span>")
            var fr = new FileReader()
            fr.onload = function () {
                cropper.replace(fr.result)
                $container.find(".photo-preview").removeClass("hidden")
                $container.find("button[data-action=upload] .fa-spin").remove()
            }
            fr.readAsDataURL($inp.get(0).files[0])
        })
    });
}

function questions_init_profiles(el) {
    /*
    TODO:
    - add dropdown for saved_id to select which profile/address to save to
    – in the original profile, strikethrough which answer will be overwritten, followed by the new answer
    – add new answers with a + in front
    */
    var profiles = JSON.parse(document.getElementById("profiles_json").textContent);
    function matchProfiles(profiles, scope) {
        var filtered = [];
        var data;
        for (var p of profiles) {
            data = {};
            for (var key of Object.keys(p)) {
                if ($("[name$=" + key + "], [name$=" + key + "_0]", scope).length) {
                    data[key] = p[key];
                }
            }
            if (Object.keys(data).length) {
                filtered.push(data);
            }
        };
        return filtered;
    }
    function shallowEqual(object1, object2) {
        var keys1 = Object.keys(object1);
        var keys2 = Object.keys(object2);

        if (keys1.length !== keys2.length) {
            return false;
        }

        for (var key of keys1) {
            if (object1[key] !== object2[key]) {
                return false;
            }
        }

        return true;
    }
    function uniqueProfiles(profiles) {
        return profiles.filter(function(p, index, arr) {
            for (var o of arr) {
                if (o != p && shallowEqual(o, p)) return false;
            }
            return true;
        });
    }

    el.find(".profile-scope").each(function () {
        // setup profile-select for each scope
        // for each answer of each profile, find the matching input (name, identifier, label)
        // if none found, remove answer from description (except attendee_name_cached vs attendee_name_parts?)
        // filter profiles to unique profiles (could be)
        // TODO:
        // – show full auto-fill info in $desc when 
        // - better UI when only one profile is available (no select)
        // - add checkmark to button when filled in 
        // - listen to all matched form fields for changes and remove chechmark if changed
        var profiles_filtered = uniqueProfiles(matchProfiles(profiles, this));
        if (!profiles_filtered.length) return;

        var $formpart = $(this);
        var $select = $formpart.find(".profile-select");
        var $button = $formpart.find(".profile-apply");
        var $desc = $formpart.find(".profile-desc");

        var i = 0;
        for (p of profiles_filtered) {
            // TODO: create a „better“ label
            // use name_cached if available, add as few info as possible to make a distinction
            // between available profiles
            // add fields in the order of questions?
            var label = (++i) + ". ";
            for (var key of Object.keys(p)) {
                if (label.length > 32) continue;
                label += (p[key]["value"] || p[key]) + ", ";
            }
            label += " …";
            $select.append("<option>" + label + "</option>");
        }
        $select.change(function() {
            // TODO: human readable description for profiles_filtered[this.selectedIndex]
            $desc.html("Show description for " + this.selectedIndex);
        }).trigger("change");
        $button.click(function() {
            var p = profiles_filtered[$select.get(0).selectedIndex];
            Object.keys(p).forEach(function(key) {
                var value = p[key];
                if (value && typeof value !== 'string') {
                    value = value.value;
                }
                var $field = $formpart.find('[name$="' + key + '"]');
                if (!$field.length) {
                    // no matching fields found, try with _0 multi-field format as value might be a timestamp or phone-number
                    // TODO: also try matching with identifier or even label
                    var $field_0 = $formpart.find('[name$="' + key + '_0"]');
                    var $field_1 = $formpart.find('[name$="' + key + '_1"]');
                    if (value.substr(0, 1) == "+") {
                        // phone number
                        var prefix = !$field_0.is("select") ? value.substr(0,2) : $field_0.get(0).options.find(function(o) {
                            return value.startsWith(o.value);
                        });
                        var number = value.substr(prefix.length);
                        $field_0.val(prefix).trigger("change");
                        $field_1.val(number).trigger("change");
                    }
                    else if ($field_0.hasClass("datepickerfield")) {
                        $field_0.data('DateTimePicker').date(moment(value));
                        $field_1.data('DateTimePicker').date(moment(value));
                    }
                } else if ($field.attr("type") === "checkbox") {
                    if (value && typeof value !== 'string') {
                        value = Object.keys(value);
                        $field.each(function() {
                            var checked = value.indexOf(this.value) > -1;
                            if (checked != this.checked) {
                                this.checked = checked;
                                $(this).trigger("change");
                            }
                        });
                    }
                    else {
                        $field.prop("checked", value).trigger("change");
                    }
                } else if ($field.length > 1) {
                    // radio-buttons
                    $field.filter('[value="' + p[key] + '"]').prop("checked", true).trigger("change");
                } else if ($field.is("select")) {
                    if (value && typeof value !== 'string') {
                        value = Object.keys(value);
                    }
                    // save value as data-attribute so if external event changes select-element/options it can select correct entries
                    // currently used when country => state changes
                    $field.prop("data-selected-value", value);
                    $field.find("option").each(function() {
                        this.selected = this.value == value || (value && value.indexOf && value.indexOf(this.value) > -1);
                    });
                    $field.trigger("change");
                } else if (value) {
                    if ($field.hasClass("datepickerfield")) {
                        $field.data('DateTimePicker').date(moment(value));
                    }
                    else {
                        $field.val(value).trigger("change");
                    }
                }
            });
        })

        $formpart.addClass("profile-select-initialized");
    });
}
