import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
	plugins: [
		vue()
	],
	build: {
		manifest: true,
		outDir: path.resolve(__dirname, '../../static.dist/vite'),
		rollupOptions: {
			input: {
				// 'webcheckin/main': path.resolve(__dirname, '../plugins/webcheckin/static/pretixplugins/webcheckin/main.js'),
				'checkinrules/main': path.resolve(__dirname, '../pretixcontrol/js/ui/checkinrules/index.ts')
			},
		}
	},
	optimizeDeps: {
		exclude: ['moment', 'jquery']
	}
})
