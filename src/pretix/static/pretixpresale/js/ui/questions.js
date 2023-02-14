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

        $inp.prop("required", false)
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
    Auto-fill answers with profiles and addresses from customer account.

    There are two types of profiles:
    1. profiles for answers and 
    2. profiles for invoice addesses

    Both are handled the same way.

    Each form section/fieldset has its own auto-fill and save to profile 
    inputs. Each fieldset can define its own profiles by providing the 
    HTML-attribute data-profiles-id, which defaults to "profiles_json".
    Currently only the invoice address fieldset uses this to load a 
    different set of profiles.

    For each section each profile’s answers are matched to inputs inside
    this section. Only matching ones are shown for auto-fill. If multiple
    profiles only match the same inputs with the same values (e.g. name)
    then only the first one is shown as showing multiple profile with the
    same values is not helpful.

    Feature-Idea:
    – in the original profile description, strikethrough which answer
      will be overwritten, followed by the new answer
    – add new answers with a + in front
    – change <select> to a list of radio-buttons for multiline-display 
      of profiles?
    */
    var profilesById = {};
    function getProfilesById(id) {
        if (!(id in profilesById)) {
            var element = document.getElementById(id);
            profilesById[id] = (!element || !element.textContent) ? [] : JSON.parse(element.textContent);
        }
        return profilesById[id];
    }

    function matchProfilesToInputs(profiles, scope) {
        var filtered = [];
        var data;
        var matched_field;
        var addSpecialKey;
        // special fields are used for substition with human readable or pre-formatted values
        var addSpecialFieldMap = {
            "country": "_country_for_address",
            "state": "_state_for_address",
            "name_parts_0": "_name",
            "attendee_name_parts_0": "_attendee_name",
        }
        for (var p of profiles) {
            data = {};
            for (var key of Object.keys(p)) {
                if (key.startsWith("_")) {
                    continue;
                }
                matched_field = getMatchingInput(key, p[key], scope);
                if (matched_field) {
                    // TODO: only add if no other answer matches same fields?
                    data[key] = {
                        "value": (typeof p[key] == "string") ? p[key] : p[key]["value"],
                        "field": matched_field
                    };
                    if (p[key]["label"]) data[key]["label"] = p[key]["label"];
                    if (p[key]["type"]) data[key]["type"] = p[key]["type"];
                    if (addSpecialKey = addSpecialFieldMap[key]) {
                        data[addSpecialKey] = p[addSpecialKey];
                    }
                }
            }
            if (Object.keys(data).length) filtered.push(data);
        };
        return filtered;
    }
    // For auto-fill with few inputs it could happen that multiple profiles 
    // only match with the same fields that have the same values. It makes
    // no sense to show multiple profiles if all fill the same value(s).
    // Therefore filter profiles to unique ones.
    function uniqueProfiles(profiles) {
        var uniques = [];
        var matchIndex;
        for (var p of profiles) {
            matchIndex = uniques.findIndex(function(element, index, array) {
                return _profilesAreEqual(element, p);
            });
            if (matchIndex === -1) uniques.push(p);
        }
        return uniques;
    }
    function _profilesAreEqual(a, b) {
        var keysA = Object.keys(a);
        var keysB = Object.keys(b);
        if (keysA.length !== keysB.length) return false;
        keysA.sort();
        keysB.sort();
        if (!keysA.every((val, index) => val === keysB[index])) return false;
        if (!keysA.every((key, index) => a[key].value === b[key].value)) return false;
        return true;
    }

    function _getInputForLabel(label) {
        if (!label) return null;
        var input;
        if (label.getAttribute("for")) {
            input = document.getElementById(label.getAttribute("for"));
            if (input) return input;
        }
        // for grouped inputs like phone number the "label" is more a fieldset/legend
        return label.closest(".form-group").querySelectorAll("select, input, textarea");
    }
    function getMatchingInput(key, answer, scope) {
        var $label;
        // _0 and _1 are e.g. for phone-fields. name-fields have their parts/keys already split
        var $fields = $('[name$="' + key + '"], [name$="' + key + '_0"], [name$="' + key + '_1"]', scope).not(":disabled");
        if ($fields.length) return $fields;

        if (answer.identifier) {
            $label = $('[data-identifier="' + answer.identifier + '"]', scope);
            var input = _getInputForLabel($label.get(0));
            if (input) return $(input);
        }
        for (var label of scope.getElementsByTagName("label")) {
            if (label.textContent === answer.label) {
                var input = _getInputForLabel(label);
                if (input) return $(input);
                break;
            }
        }
        return null;
    }

    function formatAnswerHumanReadable(answer) {
        if (typeof answer == "string") return answer;
        if (typeof answer == "number") return answer.toString();
        if (!answer && answer !== false) return "";
        var value = answer.value;
        if ("type" in answer) {
            if (answer.type === "TEL") {
                // TODO: format phone number with locale or use pre-formatted like with names?
                return value;
            }
            if (answer.type === "W") {
                return moment(value).format(document.body.getAttribute("data-datetimeformat"));
            }
            if (answer.type === "D") {
                return moment(value).format(document.body.getAttribute("data-dateformat"));
            }
            if (answer.type === "H") {
                var format = document.body.getAttribute("data-timeformat");
                return moment(value, "HH:mm:ss").format(format);
            }
            if (answer.type === "B") {
                return value ? gettext("Yes") : gettext("No");
            }
        }
        if (typeof value == "string") return value;
        if (!value) return "";
        return Object.values(value).join(", ");
    }

    // TODO: add as few info as possible to make a distinction between available profiles?
    function labelForProfile(p, profiles, scope = null) {
        var parts = describeProfile(p);
        var label = parts.join(", ");
        if (label.length > 74) {
            var len = label.lastIndexOf(' ', 74);
            label = label.substr(0, Math.max(len, 48)) + " …";
        }
        return label;
    }
    function getAnswer(a) {
        if (typeof a == "string") return a;
        return a && "value" in a ? a["value"] : "";
    }
    function describeProfile(p) {
        if (!p) return [];
        var lines = [
            getAnswer(p["company"]),
            p["_name"],
            [p["_attendee_name"], getAnswer(p["attendee_email"])].filter(v => v).join(", "),
            [
                getAnswer(p["street"]),
                [getAnswer(p["zipcode"]), getAnswer(p["city"]), p["_state_for_address"]].filter(v => v).join(" "),
                p["_country_for_address"]
            ].filter(v => v).join(", ")
        ];
        lines = lines.filter(line => line && line.trim());

        var answer;
        var label;
        for (var key of Object.keys(p)) {
            if (!key.startsWith("question_")) continue;
            answer = p[key];
            label = answer["label"] || "";
            lines.push(label + ("!?.:".split("").indexOf(label.slice(-1)) > -1 ? " " : ": ") + formatAnswerHumanReadable(answer))
        }
        return lines;
    }
    function escapeHTML(t) {
        return $("<div>").text(t).get(0).innerHTML;
    }
    function describeProfileHTML(p) {
        return describeProfile(p).map(escapeHTML).join("<br>");
    }


    function _updateDescription(select, profile, $help) {
        // show additional description if different from option-text
        var label = select.options[select.selectedIndex].textContent;
        var lines = describeProfile(profile).map(escapeHTML);
        if (!lines.length || label === lines.join(", ")) {
            $help.slideUp(function() {
                $help.html("");
            });
        }
        else {
            $help.html(lines.join("<br>")).slideDown();
        }
    }

    function setupSaveToProfile(scope, profiles) {
        var $select = $('[name$="saved_id"]', scope);
        var $selectContainer = $select.closest(".form-group").addClass("profile-save-id");
        var $checkbox = $('[name$="save"]', scope);
        var $checkboxContainer = $checkbox.closest(".form-group").addClass("profile-save");
        var $help = $selectContainer.find(".help-block");

        var $container = $("<div class='profile-save-container js-do-not-copy-answers'></div>");
        $selectContainer.after($container);
        $container.append($checkboxContainer);
        $container.append($selectContainer);
        
        if (!profiles || !profiles.length) {
            $selectContainer.hide();
            return;
        }

        $checkbox.change(function() {
            if (this.checked) $selectContainer.slideDown();
            else $selectContainer.slideUp();
        });

        for (var p of profiles) {
            $select.append($('<option>').attr('value', p._pk).text(labelForProfile(p, profiles)));
        }
        $select.append('<option value="" disabled>–</option>');
        $select.append($select.find("option").first());
        $select.get(0).selectedIndex = 0;
        $select.change(function() {
            _updateDescription(this, profiles[this.selectedIndex], $help);
        }).trigger("change");
        $checkbox.trigger("change");
    }

    // setup auto-fill for each scope/fieldset
    // match profile’s answers to inputs in scope
    // if none match, do not show auto-fill
    // if one matches, only show button to auto-fill
    // else show select with profiles and button to auto-fill
    function setupAutoFill(scope, profiles) {
        var matchedProfiles = uniqueProfiles(matchProfilesToInputs(profiles, scope));
        if (!matchedProfiles.length) {
            $(scope).addClass("profile-none-matched");
            return;
        }

        var selectedProfile = matchedProfiles[0];
        var $select = $(".profile-select", scope);
        var $button = $(".profile-apply", scope);
        var $help = $(".profile-desc", scope);

        if (matchedProfiles.length === 1) {
            $(".profile-select-control", scope).hide().parent().addClass("form-control-text");
            $help.html(describeProfileHTML(selectedProfile)).addClass("single-profile-desc").after($button);
        }
        else {
            var i = 0;
            for (p of matchedProfiles) {
                $select.append($("<option>").text(labelForProfile(p, matchedProfiles, scope)).attr("value", i));
                i++;
            }
            $select.change(function() {
                selectedProfile = matchedProfiles[this.value];
                _updateDescription(this, selectedProfile, $help);
            }).trigger("change");
        }
        // Add-Ons sit on same level as their parent product scope
        // Therefore use .prevUntil("legend") as an Add-On is
        // offset by a <legend>
        // if no <legend> is present – e.g. on invoice-address – the 
        // containing <summary> would be selected, which is not what we want
        $(scope).prevUntil("legend").not("summary").addClass("profile-pre-select");

        $button.click(function() {
            Object.keys(selectedProfile).forEach(function(key) {
                var answer = selectedProfile[key].value;
                var $field = selectedProfile[key].field;
                if (!$field || !$field.length) return;
              
                if ($field.attr("type") === "checkbox") {
                    if (answer === true || answer === false) {
                        // boolean
                        $field.prop("checked", answer).trigger("change");
                    }
                    else if (typeof answer !== 'string') {
                        answer = Object.keys(answer);
                        $field.each(function() {
                            var checked = answer.indexOf(this.value) > -1;
                            if (checked !== this.checked) {
                                this.checked = checked;
                                $(this).trigger("change");
                            }
                        });
                    }
                } else if ($field.attr("type") === "radio") {
                    $field.filter('[value="' + answer + '"]').prop("checked", true).trigger("change");
                } else if ($field.length > 1) {
                    // multiple matching fields, could be phone number or datetime
                    var $field_0 = $field.filter('[name$="_0"]');
                    var $field_1 = $field.filter('[name$="_1"]');
                    if (answer.substr(0, 1) === "+") {
                        var prefix = "";
                        var options = $field_0.get(0).options;
                        for (var i = 0; i < options.length; i++) {
                            var v = options[i].value;
                            if (v && answer.substr(0, v.length) === v) {
                                prefix = v;
                                break;
                            }
                        }
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
                        this.selected = this.value === answer || (answer && answer.indexOf && answer.indexOf(this.value) > -1);
                    });
                    $field.trigger("change");
                } else {
                    if ($field.hasClass("datepickerfield")) {
                        $field.data('DateTimePicker').date(moment(answer));
                    }
                    else {
                        $field.val(answer).trigger("change");
                    }
                }
            });
        })
    }

    // each fieldset is its own scope for auto-fill and save
    el.find(".profile-scope").each(function () {
        var profiles = getProfilesById(this.getAttribute("data-profiles-id") || "profiles_json");

        setupSaveToProfile(this, profiles);
        setupAutoFill(this, profiles);

        this.classList.add("profile-select-initialized");
    });
}
