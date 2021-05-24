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
    el.find(".profile-list").each(function () {
        var $profilelist = $(this);
        var $formpart = $(this).parent().parent();
        $profilelist.find("button").on("click", function () {
           var $btn = $(this);
           var values = JSON.parse($btn.attr("data-stored-values"));
           $formpart.find("input[name$=save]").prop("checked", false);
           $formpart.find("input[name$=saved_id]").val($btn.attr("data-id"));

           for (var key of Object.keys(values)) {
               var value = values[key];
               var $field = $formpart.find("input[name$=" + key + "], textarea[name$=" + key + "], select[name$=" + key + "]");

               console.log(key, $field, value)
               if (key === "is_business") {
                   $formpart.find("input[name=is_business][value=business]").prop("checked", value)
                   $formpart.find("input[name=is_business][value=individual]").prop("checked", !value)
                   $formpart.find("input[name=is_business][value=individual]").trigger("change")
               } else if ($field.length === 1 && $field.attr("type") === "checkbox") {
                   $field.prop("checked", value)
               } else if (!value) {
                   continue;
               } else {
                   $field.val(value);
                   $field.trigger("change")
               }

               // (invoice) address: state
               // multiplechoice
               // choice
               // date
               // time
               // datetime
           }
        });
    });
}
