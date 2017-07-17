$(document).ready(function() {
  hideDeselected();
});

function hideDeselected() {
  var index = $("select[name='quota_option'] option:selected").index();
  if (index == 1) {
    hideAll();
    $('label[for="id_quota_add_existing"]').show();
    $('#id_quota_add_existing').show();
  } else if (index == 2) {
    hideAll();
    $('#id_quota_add_new_name').show();
    $('label[for="id_quota_add_new_name"]').show();
    $('#id_quota_add_new_size').show();
    $('label[for="id_quota_add_new_size"]').show();
  } else {
    hideAll();
  }
};

function hideAll() {
  $('#id_quota_add_new_name').hide();
  $('label[for="id_quota_add_new_name"]').hide();

  $('#id_quota_add_new_size').hide();
  $('label[for="id_quota_add_new_size"]').hide();

  $('#id_quota_add_existing').hide();
  $('label[for="id_quota_add_existing"]').hide();
};

$(function () {
  $('#id_quota_option').on('change',
    function(e) {
      hideDeselected();
    }
  );
});
