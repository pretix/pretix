/*global $ */

function questions_toggle_dependent(ev) {
    $("[data-question-dependency]").each(function () {
        var $dependent = $(this).closest(".form-group");
        var dependency_name = $(this).attr("name").split("_")[0] + "_" + $(this).attr("data-question-dependency");
        var dependency_value = $(this).attr("data-question-dependency-value");
        var should_be_shown = false;
        var is_shown = !$dependent.hasClass("dependency-hidden");
        if ($("select[name=" + dependency_name + "]").length) {
            // dependency is type C
            var $dependency_el = $("select[name=" + dependency_name + "]");
            if (!$dependency_el.closest(".form-group").hasClass("dependency-hidden")) {  // do not show things that depend on hidden things
                should_be_shown = $dependency_el.val() === dependency_value;
            }
        } else if ($("input[type=checkbox][name=" + dependency_name + "]").length) {
            // dependency type is B or M
            if (dependency_value === "True" || dependency_value === "False") {
                var $dependency_el = $("input[name=" + dependency_name + "]");
                if (!$dependency_el.closest(".form-group").hasClass("dependency-hidden")) {  // do not show things that depend on hidden things
                    if (dependency_value === "True") {
                        should_be_shown = $dependency_el.prop('checked');
                    } else {
                        should_be_shown = !$dependency_el.prop('checked');
                    }
                }
            } else {
                var $dependency_el = $("input[value=" + dependency_value + "][name=" + dependency_name + "]");
                if (!$dependency_el.closest(".form-group").hasClass("dependency-hidden")) {  // do not show things that depend on hidden things
                    should_be_shown = $dependency_el.prop('checked');
                }
            }
        }
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
            if ($dependent.hasClass("has-error") || $dependent.find(".has-error")) {
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
