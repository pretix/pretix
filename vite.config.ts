// vite build config for control UI
// widget has its own config, see src/pretix/static/pretixpresale/widget/vite.config.ts
import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { execSync } from 'child_process'
import { readFileSync } from 'fs'

// Shared dependencies exposed to plugins via import map.
// Adding a dep here auto-generates a _vendor/{name} entry and
// makes it available in the import map.
const SHARED_DEPS = ['vue']

const { entries: pretixPluginEntries } = discoverPretixPlugins()
const pluginDirs = [...new Set(Object.values(pretixPluginEntries).map(p => path.dirname(p)))]

export default defineConfig({
	plugins: [
		vue(),
		sharedDepsPlugin(),
		pretixPluginDevEntries(),
	],
	resolve: {
		// Pin shared deps to pretix's node_modules to prevent duplicate instances
		// across plugins whose node_modules live in sibling directories
		dedupe: [...SHARED_DEPS, '@vue/runtime-core', '@vue/reactivity', '@vue/shared'],
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
			preserveEntrySignatures: 'exports-only',
			input: {
				'webcheckin/main': path.resolve(__dirname, 'src/pretix/plugins/webcheckin/static/pretixplugins/webcheckin/main.ts'),
				'checkinrules/main': path.resolve(__dirname, 'src/pretix/static/pretixcontrol/js/ui/checkinrules/index.ts'),
				...Object.fromEntries(SHARED_DEPS.map(dep => [`_vendor/${dep}`, `virtual:vendor/${dep}`])),
				...pretixPluginEntries,
			},
		}
	},
	optimizeDeps: {
		exclude: ['moment', 'jquery']
	}
})

// Virtual module plugin: generates re-export entries for each shared dep
// In dev mode, serves /__pretix_importmap so the python template tag can build the import map without hardcoding dep names.
function sharedDepsPlugin (): Plugin {
	const PREFIX = 'virtual:vendor/'
	const RESOLVED = '\0virtual:vendor/'
	return {
		name: 'pretix-shared-deps',
		resolveId (id) {
			if (id.startsWith(PREFIX))
				return RESOLVED + id.slice(PREFIX.length)
		},
		load (id) {
			if (id.startsWith(RESOLVED)) {
				const pkg = id.slice(RESOLVED.length)
				return `export * from '${pkg}'`
			}
		},
		// Serve the import map data so the Python template tag can fetch it in dev mode
		configureServer (server) {
			server.middlewares.use((req, res, next) => {
				if (req.url === '/__pretix_importmap') {
					const imports = Object.fromEntries(
						SHARED_DEPS.map(dep => [
							dep,
							`/node_modules/.vite/deps/${dep.replace('/', '_')}.js`,
						])
					)
					res.setHeader('Content-Type', 'application/json')
					res.setHeader('Access-Control-Allow-Origin', '*')
					res.end(JSON.stringify(imports))
					return
				}
				next()
			})
		},
	}
}

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
        if not url_info.get('dir_info', {}).get('editable'):
            continue  # non-editable plugins build their own assets
        p = pathlib.Path(url_info['url'].replace('file://', '')) / 'pretixplugin.vite.json'
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
		const packageRoot = entriesFile.replace(/[/\\]pretixplugin\.vite\.json$/, '')
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
