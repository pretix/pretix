// vite build config for control UI
// widget has its own config, see src/pretix/static/pretixpresale/widget/vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
	plugins: [
		vue()
	],
	build: {
		manifest: true,
		outDir: path.resolve(__dirname, 'src/pretix/static.dist/vite/control'),
		rollupOptions: {
			input: {
				'webcheckin/main': path.resolve(__dirname, 'src/pretix/plugins/webcheckin/static/pretixplugins/webcheckin/main.ts'),
				'checkinrules/main': path.resolve(__dirname, 'src/pretix/static/pretixcontrol/js/ui/checkinrules/index.ts')
			},
		}
	},
	optimizeDeps: {
		exclude: ['moment', 'jquery']
	}
})
