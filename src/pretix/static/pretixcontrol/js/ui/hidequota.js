$(document).ready(function() {
  hideDeselected();
});

function hideDeselected() {
  var v = $("#id_quota_option").val();

  if (v === "existing") {
    hideAll();
    $("#existing-quota-group").children().show();
  } else if (v === "new") {
    hideAll();
    $("#new-quota-group").children().show();
  } else {
    hideAll();
  }
};

function hideAll() {
  $("#new-quota-group").children().hide();
  $("#existing-quota-group").children().hide();
};

$(function () {
  $('#id_quota_option').on('change',
    function(e) {
      hideDeselected();
    }
  );
});
