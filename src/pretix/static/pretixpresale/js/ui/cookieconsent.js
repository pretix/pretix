/*global $ */

window.__pretix_cookie_update_listeners = window.__pretix_cookie_update_listeners || []

$(function () {
  var storage_key = $("#cookie-consent-storage-key").text();
  if (!window.localStorage[storage_key]) {
    $("#cookie-consent-modal").show();
  }
  $("#cookie-consent-button-yes").on("click", function () {
    window.localStorage[storage_key] = JSON.stringify({
      'functionality': true,
      'ad': true,
      'analytics': true,
      'social': true,
    })
    for (var k of window.__pretix_cookie_update_listeners) {
      k.call(this, window.localStorage[storage_key])
    }
    $("#cookie-consent-modal").hide()
  })
  $("#cookie-consent-button-no").on("click", function () {
    window.localStorage[storage_key] = JSON.stringify({
      'functionality': true,
      'ad': false,
      'analytics': false,
      'social': false,
    })
    for (var k of window.__pretix_cookie_update_listeners) {
      k.call(this, window.localStorage[storage_key])
    }
    $("#cookie-consent-modal").hide()
  })
  $("#cookie-consent-reopen").on("click", function (e) {
    $("#cookie-consent-modal").show()
    e.preventDefault()
    return true
  })
});