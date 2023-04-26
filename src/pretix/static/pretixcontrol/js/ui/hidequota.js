$(function () {
  hideDeselected(false);

  function hideDeselected(animate) {
    var v = $("input[name='quota_option']:checked").val(),
      fn = animate ? 'slideDown' : 'show';
    if (v === "existing") {
      hideAll(animate);
      $("#existing-quota-group").children()[fn]();
    } else if (v === "new") {
      hideAll(animate);
      if ($("#id_quota_add_new_name").val() === "") {
          $("#id_quota_add_new_name").val($("input[name^=name_]").first().val());
      }
      $("#new-quota-group").children()[fn]();
    } else {
      hideAll(animate);
    }
  }

  function hideAll(animate) {
    var fn = animate ? 'slideUp' : 'hide';
    $("#new-quota-group").children()[fn]();
    $("#existing-quota-group").children()[fn]();
  }

  $("input[name='quota_option']").on('change',
    function () {
      hideDeselected(true);
    }
  );

  function toggleblock() {
    $("#new-quota-group").closest('fieldset').toggle(!$("[name=has_variations][value=on]").prop('checked'));
  }

  $("[name=has_variations]").change(toggleblock);
  toggleblock();
});
