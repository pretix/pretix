$(document).ready(function() {
  hideDeselected();
});

function hideDeselected() {
  var v = $("input[name='quota_option']:checked").val();

  if (v === "existing") {
    hideAll();
    $("#existing-quota-group").children().slideDown();
  } else if (v === "new") {
    hideAll();
    $("#new-quota-group").children().slideDown();
  } else {
    hideAll();
  }
};

function hideAll() {
  $("#new-quota-group").children().slideUp();
  $("#existing-quota-group").children().slideUp();
};

$(function () {
  $("input[name='quota_option']").on('change',
    function() {
      hideDeselected();
    }
  );
});
