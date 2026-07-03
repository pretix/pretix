document.addEventListener("DOMContentLoaded", () => {
  const COOKIE_NAME = "__Host-pretix_csrftoken";
  const RELOAD_FLAG = "csrfReloadPerformed";

  const hasCookie = document.cookie
    .split("; ")
    .some((c) => c.startsWith(COOKIE_NAME + "="));

  if (!hasCookie && !sessionStorage.getItem(RELOAD_FLAG)) {
    sessionStorage.setItem(RELOAD_FLAG, "1");
    location.reload();
  } else if (hasCookie && sessionStorage.getItem(RELOAD_FLAG)) {
      sessionStorage.removeItem(RELOAD_FLAG);
  }
});
