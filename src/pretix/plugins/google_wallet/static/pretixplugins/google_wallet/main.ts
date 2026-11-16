import GoogleEventDefault from './components/platform-preview/google-event-default.vue'
import GoogleEventCustom from './components/platform-preview/google-event-custom.vue'

window.pretix_wallet_preview_renderers = window.pretix_wallet_preview_renderers || {}
window.pretix_wallet_preview_renderers['google_eventticket_default'] = GoogleEventDefault
window.pretix_wallet_preview_renderers['google_eventticket_custom'] = GoogleEventCustom
