['DOMContentLoaded', 'pretix:async-task-error'].forEach(function (ev) {
  document.addEventListener(ev, function () {
    document.querySelectorAll('#goback, #reload').forEach(function (element) {
      const regularLoad = ev === 'DOMContentLoaded' && element.id === 'goback';
      element.addEventListener('click', regularLoad
        ? () => window.history.back()
        : () => window.location.reload()
      );
    });
  });
});
