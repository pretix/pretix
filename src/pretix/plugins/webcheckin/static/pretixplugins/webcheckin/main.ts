import { createApp } from 'vue'

// import './scss/main.scss'

import App from './components/app.vue'

const mountEl = document.querySelector<HTMLElement>('#app')!

const app = createApp(App, mountEl.dataset)
app.mount('#app')

app.config.errorHandler = (error, _vm, info) => {
	// vue fatals on errors by default, which is a weird choice
	// https://github.com/vuejs/core/issues/3525
	// https://github.com/vuejs/router/discussions/2435
	console.error('[VUE]', info, error)
}
