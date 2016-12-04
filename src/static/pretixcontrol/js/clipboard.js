$(function() {
    $('.btn-clipboard').tooltip({
      trigger: 'click',
      placement: 'bottom'
    });

    function setTooltip(btn, message) {
      $(btn).tooltip('hide')
        .attr('data-original-title', message)
        .tooltip('show');
    }

    function hideTooltip(btn) {
      setTimeout(function() {
        $(btn).tooltip('hide');
      }, 1000);
    }

    var clipboard = new Clipboard('.btn-clipboard');

    clipboard.on('success', function(e) {
      if (e.text.length > 0) {
        setTooltip(e.trigger, gettext('Copied!'));
        hideTooltip(e.trigger);
      }
    });

    clipboard.on('error', function(e) {
      setTooltip(e.trigger, gettext('Press Ctrl-C to copy!'));
      hideTooltip(e.trigger);
    });
});

