import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => ({
	server: {
		port: 5180
	},
	plugins: [
		vue()
	],
	resolve: {
		alias: {
			'~': import.meta.dirname + '/src',
		},
	},
	build: {
		minify: false, // django will do minification
		outDir: import.meta.dirname + '/../../../static.dist/vite/widget',
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
		...(mode === 'development' && {
			LANG: JSON.stringify(process.env.PRETIX_WIDGET_LANG || 'en'),
		}),
	},
}))
