const registerErrorLinkHandlers = (reloadAll = false) => {
  const backwards = document.getElementById('goback');
  if (backwards) {
    backwards.onclick = reloadAll
      ? () => window.location.reload(true)
      : () => window.history.back();
  }

  const reload = document.getElementById('reload');
  if (reload) {
    reload.onclick = () => window.location.reload(true);
  }
};

registerErrorLinkHandlers();

$(document).on("pretix:async_task_replace_page:on_error", () => registerErrorLinkHandlers(true));
