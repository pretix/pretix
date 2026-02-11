import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
	plugins: [
		vue()
	],
	resolve: {
		alias: {
			'~': import.meta.dirname + '/src',
		},
	},
	build: {
		manifest: true,
		outDir: import.meta.dirname + '/../../../../../static.dist/vite/widget',
		rollupOptions: {
			input: {
				main: import.meta.dirname + '/src/main.ts',
			},
			output: {
				format: 'iife',
				entryFileNames: 'widget.js',
				assetFileNames: 'widget.[ext]',
			},
		},
	},
	optimizeDeps: {
		exclude: ['moment', 'jquery']
	},
	define: {
		LANG: JSON.stringify(process.env.PRETIX_WIDGET_LANG || 'en')
	}
})
