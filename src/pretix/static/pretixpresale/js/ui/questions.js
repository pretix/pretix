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
    var profiles_element = document.getElementById("profiles_json");
    if (!profiles_element || !profiles_element.textContent) return;
    var profiles = JSON.parse(profiles_element.textContent);
    function matchProfiles(profiles, scope) {
        var filtered = [];
        var data;
        var matched_field;
        for (var p of profiles) {
            data = {};
            for (var key of Object.keys(p)) {
                matched_field = getMatchingInput(key, p[key], scope);
                if (matched_field) {
                    // TODO: only add if no other field matches same fields?
                    data[key] = {
                        "answer": p[key],
                        "field": matched_field
                    };
                }
            }
            var equalMatchAvailable = filtered.findIndex(function(element) {
                return matchesAreEqual(element, data);
            });
            console.log("equalMatchAvailable", equalMatchAvailable);
            if (Object.keys(data).length) {
                filtered.push(data);
            }
        };
        return filtered;
    }
    function matchesAreEqual(object1, object2) {
        var keys1 = Object.keys(object1);
        var keys2 = Object.keys(object2);

        if (keys1.length !== keys2.length) {
            return false;
        }
        // TODO: recursive match on answer-value(s)

        return false;
    }

    function getInputForLabel(label) {
        if (label && label.getAttribute("for")) {
            var input = document.getElementById(label.getAttribute("for"));
            return input;
        }
        return null;
    }
    function getMatchingInput(key, answer, scope) {
        var $label;
        var $fields = $('[name$="' + key + '"], [name$="' + key + '_0"], [name$="' + key + '_1"]', scope);
        if ($fields.length) return $fields;

        if (answer.identifier) {
            $label = $('[data-identifier="' + answer.identifier + '"]', scope);
            var input = getInputForLabel($label.get(0));
            if (input) return $(input);
        }
        for (var label of scope.getElementsByTagName("label")) {
            if (label.textContent == answer.label) {
                var input = getInputForLabel(label);
                if (input) return $(input);
                break;
            }
        }
        return null;
    }
    function labelForProfile(p) {
            // TODO: create a „better“ label
            // - use name_cached if available
            // - add as few info as possible to make a distinction between available profiles
            // - add fields in the order of questions?
            var label = "";
            for (var key of Object.keys(p)) {
                console.log(key, p[key]);
                if (label.length > 32) break;
                var answer = p[key].answer.value || p[key].answer
                if (answer && typeof answer !== 'string') {
                    for (var a of Object.keys(answer)) {
                        label += answer[a] + ", ";
                    }
                }
                else {
                    label += answer + ", ";
                }
            }
            label += " …";
            return label;
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
        var matched_profiles = matchProfiles(profiles, this);
        if (!matched_profiles.length) return;

        var $formpart = $(this);
        var $select = $formpart.find(".profile-select");
        var $button = $formpart.find(".profile-apply");
        var $desc = $formpart.find(".profile-desc");

        var i = 0;
        for (p of matched_profiles) {
            $select.append("<option>" + (++i) + ". " + labelForProfile(p) + "</option>");
        }
        $select.change(function() {
            // TODO: human readable description for matched_profiles[this.selectedIndex]
            $desc.html("Show description for matched profile " + this.selectedIndex);
        }).trigger("change");
        $button.click(function() {
            var p = matched_profiles[$select.get(0).selectedIndex];
            Object.keys(p).forEach(function(key) {
                var answer = p[key].answer;
                var $field = p[key].field;

                if (answer && typeof answer !== 'string') {
                    answer = answer.value;
                }
                console.log(key, $field, answer);                
                if ($field.attr("type") === "checkbox") {
                    if (answer && typeof answer !== 'string') {
                        answer = Object.keys(answer);
                        $field.each(function() {
                            var checked = answer.indexOf(this.value) > -1;
                            if (checked != this.checked) {
                                this.checked = checked;
                                $(this).trigger("change");
                            }
                        });
                    }
                    else {
                        $field.prop("checked", answer).trigger("change");
                    }
                } else if ($field.attr("type") === "radio") {
                    $field.filter('[value="' + answer + '"]').prop("checked", true).trigger("change");
                } else if ($field.length > 1) {
                    // multiple matching fields, could be phone number or datetime
                    var $field_0 = $field.filter('[name$="_0"]');
                    var $field_1 = $field.filter('[name$="_1"]');
                    if (answer.substr(0, 1) == "+") {
                        // phone number
                        var prefix = !$field_0.is("select") ? answer.substr(0,2) : $field_0.get(0).options.find(function(o) {
                            return answer.startsWith(o.value);
                        });
                        var number = answer.substr(prefix.length);
                        $field_0.val(prefix).trigger("change");
                        $field_1.val(number).trigger("change");
                    }
                    else if ($field_0.hasClass("datepickerfield")) {
                        $field_0.data('DateTimePicker').date(moment(answer));
                        $field_1.data('DateTimePicker').date(moment(answer));
                    }
                } else if ($field.is("select")) {
                    if (answer && typeof answer !== 'string') {
                        answer = Object.keys(answer);
                    }
                    // save answer as data-attribute so if external event changes select-element/options it can select correct entries
                    // currently used when country => state changes
                    $field.prop("data-selected-value", answer);
                    $field.find("option").each(function() {
                        this.selected = this.value == answer || (answer && answer.indexOf && answer.indexOf(this.value) > -1);
                    });
                    $field.trigger("change");
                } else if (answer) {
                    if ($field.hasClass("datepickerfield")) {
                        $field.data('DateTimePicker').date(moment(answer));
                    }
                    else {
                        $field.val(answer).trigger("change");
                    }
                }
            });
        })

        $formpart.addClass("profile-select-initialized");
    });
}
