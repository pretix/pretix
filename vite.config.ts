// vite build config for control UI
// widget has its own config, see src/pretix/static/pretixpresale/widget/vite.config.ts
import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { execSync } from 'child_process'
import { readFileSync } from 'fs'

const { entries: pretixPluginEntries } = discoverPretixPlugins()
const pluginDirs = [...new Set(Object.values(pretixPluginEntries).map(p => path.dirname(p)))]

export default defineConfig({
	plugins: [
		vue(),
		pretixPluginDevEntries(),
	],
	resolve: {
		// Pin shared deps to pretix's node_modules to prevent duplicate instances
		// across plugins whose node_modules live in sibling directories
		dedupe: ['vue', '@vue/runtime-core', '@vue/reactivity', '@vue/shared'],
	},
	server: {
		fs: {
			// Allow serving source files from sibling plugin directories
			allow: ['src', ...pluginDirs],
		},
	},
	build: {
		manifest: true,
		outDir: path.resolve(__dirname, 'src/pretix/static.dist/vite/control'),
		rollupOptions: {
			input: {
				'webcheckin/main': path.resolve(__dirname, 'src/pretix/plugins/webcheckin/static/pretixplugins/webcheckin/main.ts'),
				'checkinrules/main': path.resolve(__dirname, 'src/pretix/static/pretixcontrol/js/ui/checkinrules/index.ts'),
				...pretixPluginEntries,
			},
		}
	},
	optimizeDeps: {
		exclude: ['moment', 'jquery']
	}
})

// TODO move to separate file?
function discoverPretixPlugins (): { entries: Record<string, string> } {
	let entryFiles: string[] = []
	try {
		const raw = execSync(`python -c "
import importlib_metadata as metadata, json, pathlib
result = []
for ep in metadata.entry_points(group='pretix.plugin'):
    dist = ep.dist
    if not dist: continue
    try:
        url_info = json.loads(dist.read_text('direct_url.json') or '{}')
        if url_info.get('dir_info', {}).get('editable'):
            p = pathlib.Path(url_info['url'].replace('file://', '')) / 'pretix-vite-entries.json'
        else:
            p = pathlib.Path(str(dist.locate_file('pretix-vite-entries.json')))
        if p.exists():
            result.append(str(p))
    except Exception:
        pass
print(json.dumps(result))
"`, { stdio: ['pipe', 'pipe', 'inherit'] }).toString().trim()
		entryFiles = JSON.parse(raw)
	} catch (error) {
		console.error('Failed to discover pretix plugins, skipping plugin entries:', error)
	}

	const entries: Record<string, string> = {}
	for (const entriesFile of entryFiles) {
		const packageRoot = entriesFile.replace(/[/\\]pretix-vite-entries\.json$/, '')
		const { entries: pluginEntries } = JSON.parse(readFileSync(entriesFile, 'utf8'))
		for (const [name, rel] of Object.entries<string>(pluginEntries)) {
			entries[name] = path.join(packageRoot, rel)
		}
	}
	return { entries }
}

// In dev mode, the browser requests /{entryName} from the Vite dev server.
// Vite can't find these files since they live outside the project root.
// This plugin rewrites those URLs to /@fs{absPath} so Vite serves them directly.
function pretixPluginDevEntries (): Plugin {
	return {
		name: 'pretix-plugin-dev-entries',
		configureServer (server) {
			server.middlewares.use((req, _res, next) => {
				const urlPath = req.url?.split('?')[0]
				if (urlPath) {
					const name = urlPath.slice(1) // strip leading /
					if (name in pretixPluginEntries)
						req.url = `/@fs${pretixPluginEntries[name]}`
				}
				next()
			})
		},
	}
}
