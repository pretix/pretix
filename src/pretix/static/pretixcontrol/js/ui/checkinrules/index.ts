import { createApp } from 'vue'
import App from './App.vue'

const app = createApp(App)
app.mount('#rules-editor')

app.config.errorHandler = (error, _vm, info) => {
	// vue fatals on errors by default, which is a weird choice
	// https://github.com/vuejs/core/issues/3525
	// https://github.com/vuejs/router/discussions/2435
	console.error('[VUE]', info, error)
}
