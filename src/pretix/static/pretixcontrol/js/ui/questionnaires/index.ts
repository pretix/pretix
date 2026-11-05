import { createApp } from 'vue'
import App from './App.vue'
import { plugin as slicksortPlugin } from 'vue-slicksort'

createApp(App)
    .use(slicksortPlugin)
    .mount('#questionnaires-editor')
