import { localize_string } from '@/pretix/static/pretixbase/js/i18n'
import { createStore } from '@/pretix/static/pretixbase/js/store'
import { toRaw, type InjectionKey } from 'vue'

export type WidgetStore = ReturnType<typeof createWalletStore>
export const StoreKey: InjectionKey<WidgetStore> = Symbol('WidgetStore')

function getDefaultFieldgroupState (
	fieldgroup: FieldGroupDefinition,
): FieldGroupConfig {
	if (fieldgroup.type == 'predefined') {
		return { active: fieldgroup.required || fieldgroup.default_active }
	} else {
		return {
			overflow: fieldgroup.default_overflow,
			entries: JSON.parse(JSON.stringify(fieldgroup.default_entries)),
		}
	}
}

function parseExistingFieldgroupState (
	fieldgroup: FieldGroupDefinition,
	existing?: FieldGroupConfig,
): FieldGroupConfig {
	if (!existing) {
		return getDefaultFieldgroupState(fieldgroup)
	}
	if (fieldgroup.type == 'predefined') {
		return {
			active: 'active' in existing ? existing.active : fieldgroup.required,
		}
	} else {
		return {
			overflow: 'overflow' in existing ? existing.overflow : null,
			// TODO: check that placeholders are possible
			entries: structuredClone(
				toRaw(
					'entries' in existing ? existing.entries : fieldgroup.default_entries,
				),
			),
		}
	}
}

export function createWalletStore (config: {
	platforms: Platforms;
	placeholders: PlaceholderConfig;
	locales: Record<string, string>;
	csrfToken: string;
	layoutId: string;
	baseUrl: string;
	previewUrl: string;
}) {
	return createStore({
		state: () => ({
			...config,
			loaded: false,
			activePlatform: config.platforms[0].identifier,
			name: '',
			platformLayouts: {} as Record<string, PlatformLayout>,
		}),
		getters: {
			platform (): Platform | undefined {
				return this.getPlatform(this.activePlatform)
			},
			layout () {
				if (!this.loaded) {
					return
				}
				return this.platformLayouts[this.activePlatform] || null
			},
			style (): Style | null {
				if (this.layout && this.platform) {
					return this.platform.styles[this.layout.style]
				} else {
					return null
				}
			},
			styles (): Styles {
				return this.platform?.styles || {}
			},
			settings (): Record<string, SettingValue | null> {
				const settings = {}
				if (!this.style) {
					return settings
				}
				for (const setting of this.style.settings) {
					if (
						setting.type == 'text'
						|| setting.type == 'color'
						|| setting.type == 'float'
						|| setting.type == 'bool'
					) {
						settings[setting.identifier]
							= this.layout?.settings?.[setting.identifier]
					} else if (setting.type == 'image') {
						const val = this.layout?.file_settings[setting.identifier]
						if (val) {
							settings[setting.identifier] = val
						} else {
							settings[setting.identifier] = null
						}
					}
				}
				return settings
			},
			settingsValues (): Record<string, SettingValue> {
				const settings: Record<string, SettingValue> = {}
				if (!this.style) {
					return settings
				}
				for (const setting of this.style.settings) {
					if (
						setting.type == 'text'
						|| setting.type == 'color'
						|| setting.type == 'float'
						|| setting.type == 'bool'
					) {
						settings[setting.identifier]
							= this.layout?.settings?.[setting.identifier] || setting.default
					} else if (setting.type == 'image') {
						const val = this.layout?.file_settings[setting.identifier]
						if (val && 'url' in val && val.url) {
							settings[setting.identifier] = val
						} else if (setting.default) {
							settings[setting.identifier] = { url: setting.default }
						}
					}
				}
				return settings
			},
			renderedFieldGroups () {
				const content = {}
				const placeholderFieldGroups = this.style?.fieldgroups.filter(
					(x) => x.type === 'placeholder',
				)
				if (!placeholderFieldGroups) {
					return content
				}
				for (const fieldgroup of placeholderFieldGroups) {
					content[fieldgroup.identifier] = []
					const layout_group = this.layout?.fieldgroups[fieldgroup.identifier] as any as PlaceholderFieldGroupConfig | undefined
					if (!layout_group) continue
					for (const entry of layout_group.entries) {
						let label = entry.label ? localize_string(entry.label) : null
						let value: string | null = null
						if (entry.type === 'placeholder') {
							const placeholder = entry.content ? this.placeholders[fieldgroup.content_type][entry.content] : null
							if (!placeholder) {
								continue
							}
							if (!label) {
								label = localize_string(placeholder.label)
							}
							value = placeholder?.sample
						} else if (entry.type == 'custom') {
							value = entry.content ? localize_string(entry.content) : null
						}
						content[fieldgroup.identifier].push({
							label,
							content: value,
						})
					}
				}
				for (const fieldgroup of placeholderFieldGroups) {
					const layout_group = this.layout?.fieldgroups[fieldgroup.identifier] as any as PlaceholderFieldGroupConfig | undefined
					if (!layout_group) continue

					if (
						fieldgroup.max_entries
						&& content[fieldgroup.identifier].length > fieldgroup.max_entries
					) {
						const overflow = content[fieldgroup.identifier].splice(
							fieldgroup.max_entries,
						)
						if (layout_group.overflow) {
							content[layout_group.overflow].unshift(...overflow)
						}
					}
				}

				return content
			},
			fieldgroups (): Record<string, FieldGroupDefinition> {
				if (this.style) {
					return Object.fromEntries(
						this.style.fieldgroups.map((x) => [x.identifier, x]),
					)
				} else {
					return {}
				}
			},
		},
		actions: {
			getPlatform (identifier: string): Platform | undefined {
				for (const platform of this.platforms) {
					if (platform.identifier === identifier) {
						return platform
					}
				}
			},
			load () {
				// TODO: error handling / proper api client
				fetch(`${this.baseUrl}${this.layoutId}/`)
					.then((x) => x.json())
					.then((x) => {
						this.parseServerLayout(x)
						this.loaded = true
					})
					.catch(alert)
			},
			parseServerLayout (serverLayout) {
				this.name = serverLayout.name
				for (const layout of serverLayout.platform_layouts) {
					const clientLayout = {
						style: layout.style,
						fieldgroups: {},
						settings: layout.layout.settings || {},
						file_settings: layout.file_settings,
					}
					const styleDefinition = this.getPlatform(layout.platform)?.styles[
						layout.style
					]
					if (!styleDefinition) continue
					for (const fieldgroup of styleDefinition.fieldgroups) {
						clientLayout.fieldgroups[fieldgroup.identifier]
							= parseExistingFieldgroupState(
								fieldgroup,
								layout.layout.fieldgroups[fieldgroup.identifier],
							)
					}
					this.platformLayouts[layout.platform] = clientLayout
				}
			},
			setPlatform (platform: string) {
				this.activePlatform = platform
			},
			setStyle (style: string | null) {
				if (style === null) {
					delete this.platformLayouts[this.activePlatform]
				} else if (Object.keys(this.styles).includes(style)) {
					const newLayout = {
						style,
						fieldgroups: {},
						settings: {},
						file_settings: {},
					}
					for (const fieldgroup of this.styles[style].fieldgroups) {
						newLayout.fieldgroups[fieldgroup.identifier]
							= getDefaultFieldgroupState(fieldgroup)
					}
					this.platformLayouts[this.activePlatform] = newLayout
					// TODO: keep old fieldgroups & settings if matching
				}
			},
			getSetting (identifier: string): Setting | undefined {
				if (!this.style) {
					throw Error('No style set')
				}

				for (const setting of this.style.settings) {
					if (setting.identifier === identifier) {
						return setting
					}
				}
			},
			getSettingValue (identifier: string): SettingValue | undefined {
				const setting = this.getSetting(identifier)
				if (!setting) return

				if (
					setting.type == 'text'
					|| setting.type == 'color'
					|| setting.type == 'float'
					|| setting.type == 'bool'
				) {
					return this.layout?.settings?.[setting.identifier] || setting.default
				} else if (setting.type == 'image') {
					const val = this.layout?.file_settings[setting.identifier]
					if (val && 'url' in val && val.url) {
						return val
					} else if (setting.default) {
						return { url: setting.default }
					}
				}
			},
			setSetting (identifier: string, value: string | File) {
				if (!this.layout) return

				const setting = this.getSetting(identifier)
				if (!setting) return

				if (setting.type === 'image') {
					const oldUrl = this.layout.file_settings[setting.identifier]?.['url']
					if (oldUrl) {
						URL.revokeObjectURL(oldUrl)
					}
					if (value instanceof File) {
						this.layout.file_settings[setting.identifier] = {
							file: value,
							url: URL.createObjectURL(value),
							name: value.name,
						}
					} else if (value === null) {
						this.layout.file_settings[setting.identifier] = {
							file: null,
						}
					}
				} else if (
					(setting.type == 'text' || setting.type == 'color')
					&& typeof value == 'string'
				) {
					this.layout.settings[setting.identifier] = value
				} else if (setting.type == 'float' && typeof value == 'string') {
					this.layout.settings[setting.identifier] = parseFloat(value)
				} else if (setting.type == 'float' && typeof value == 'number') {
					this.layout.settings[setting.identifier] = value
				} else if (setting.type == 'bool' && typeof value == 'boolean') {
					this.layout.settings[setting.identifier] = value
				}
			},
			async uploadFile (file: ClientSideFile): Promise<string> {
				return await fetch('/api/v1/upload', {
					method: 'POST',
					body: file.file,
					headers: {
						'content-disposition': `attachment; filename="${encodeURI(file.file.name)}"`,
						'content-type': file.file.type || 'application/octet-stream',
						'X-CSRFToken': this.csrfToken,
					},
				})
					.then((x) => x.json())
					.then((x) => {
						file.identifier = x.id
						return x.id
					})
					.catch(alert)
			},
			serializeFieldgroups (platform, layout: PlatformLayout): Record<string, FieldGroupConfig> {
				const styleDefinition = this.getPlatform(platform)!.styles[layout.style]

				return Object.fromEntries(
					Object.entries(layout.fieldgroups)
						.map(([k, v]): [string, FieldGroupConfig] | undefined => {
							const fieldgroupDefinition = styleDefinition.fieldgroups.find(
								(x) => x.identifier == k,
							)
							if (!fieldgroupDefinition) {
								return
							}
							if (fieldgroupDefinition.type == 'placeholder') {
								v = v as PlaceholderFieldGroupConfig
								v = {
									...v,
									entries: v.entries.filter(
										(x) => x.type != 'placeholder' || !!x.content,
									),
								}
							}
							return [k, v]
						})
						.filter((x) => !!x),
				)
			},
			async serializePlatformLayout (platform, layout: PlatformLayout): Promise<ServerPlatformLayout> {
				const uploadedFiles = Object.fromEntries(
					(
						await Promise.all(
							Object.entries(layout.file_settings).map(async ([k, v]) => {
								if ('identifier' in v) {
									return [k, v.identifier]
								} else if ('file' in v && v instanceof File) {
									return [k, await this.uploadFile(v as ClientSideFile)]
								} else if ('file' in v && v.file == null) {
									return [k, null]
								} else if ('url' in v) {
									return [k, 'file:keep']
								}
							}),
						)
					).filter((x) => !!x),
				)
				return {
					platform,
					style: layout.style,
					file_settings: uploadedFiles,
					layout: {
						fieldgroups: this.serializeFieldgroups(platform, layout),
						settings: layout.settings,
					},
				}
			},
			async serializeCurrentPlatformLayout (): Promise<ServerPlatformLayout | undefined> {
				if (!this.layout) return
				return this.serializePlatformLayout(this.activePlatform, this.layout)
			},
			async serializeLayout (): Promise<ServerWalletLayout> {
				const layoutPromises = Object.entries(this.platformLayouts).map(
					([platform, layout]) =>
						this.serializePlatformLayout(platform, layout),
				)
				return {
					name: this.name,
					platform_layouts: await Promise.all(layoutPromises),
				}
			},
			async save (): Promise<undefined> {
				const serializedLayout = await this.serializeLayout()
				// TODO: error handling / proper api client
				fetch(
					`/api/v1/organizers/demo/events/wallet/walletlayouts/${this.layoutId}/`,
					{
						method: 'PUT',
						headers: {
							'content-type': 'application/json',
							'X-CSRFToken': this.csrfToken,
						},
						body: JSON.stringify(serializedLayout),
					},
				)
					.then((x) => {
						if (!x.ok) {
							throw new Error(`Response status: ${x.status}`)
						}
						return x.json()
					})
					.then((x) => {
						this.parseServerLayout(x)
					})
					.catch((x) => alert(x))
			},
		},
	})
}
