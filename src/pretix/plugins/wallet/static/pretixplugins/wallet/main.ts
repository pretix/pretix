import Apple from './components/platform-preview/apple.vue'
import GoogleEventDefault from './components/platform-preview/google-event-default.vue'
import GoogleEventCustom from './components/platform-preview/google-event-custom.vue'

window.pretix_wallet_preview_renderers['apple_eventticket'] = Apple
window.pretix_wallet_preview_renderers['google_eventticket_default'] = GoogleEventDefault
window.pretix_wallet_preview_renderers['google_eventticket_custom'] = GoogleEventCustom
