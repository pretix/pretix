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
