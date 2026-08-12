import { serialize } from "node:v8";
import { i18nstringLocalize } from "./helpers.js";
import { createStore } from "./lib/store.ts";
import { toRaw, type InjectionKey } from "vue";

export type WidgetStore = ReturnType<typeof createWalletStore>;
export const StoreKey: InjectionKey<WidgetStore> = Symbol("WidgetStore");

function getDefaultFieldgroupState(
	fieldgroup: FieldGroupDefinition,
): FieldGroupConfig {
	if (fieldgroup.type == "predefined") {
		return { active: fieldgroup.required };
	} else if (fieldgroup.type == "placeholder") {
		return {
			overflow: null,
			entries: JSON.parse(JSON.stringify(fieldgroup.default_entries)),
		};
	}
}

function parseExistingFieldgroupState(
	fieldgroup: FieldGroupDefinition,
	existing?: FieldGroupConfig,
): FieldGroupConfig {
	if (!existing) {
		return getDefaultFieldgroupState(fieldgroup);
	}
	if (fieldgroup.type == "predefined") {
		return {
			active: "active" in existing ? existing.active : fieldgroup.required,
		};
	} else if (fieldgroup.type == "placeholder") {
		return {
			overflow: "overflow" in existing ? existing.overflow : null,
			// TODO: check that placeholders are possible
			entries: structuredClone(
				toRaw(
					"entries" in existing ? existing.entries : fieldgroup.default_entries,
				),
			),
		};
	}
}

export function createWalletStore(config: {
	platforms: Platforms;
	variables: VariableConfig;
	locales: Record<string, string>;
	csrfToken: string;
	layoutId: string;
}) {
	return createStore({
		state: () => ({
			...config,
			loaded: false,
			activePlatform: config.platforms[0].identifier,
			name: null as string | null,
			platformLayouts: {} as Record<string, NewPlatformLayout>,
		}),
		getters: {
			platform() {
				return this.getPlatform(this.activePlatform);
			},
			layout() {
				if (!this.loaded) {
					return;
				}
				return this.platformLayouts[this.activePlatform] || null;
			},
			style(): Style {
				if (this.layout) {
					return this.platform.styles[this.layout.style];
				} else {
					return null;
				}
			},
			styles() {
				return this.platform.styles;
			},
			settings() {
				const settings = {};
				for (const setting of this.style.settings) {
					if (setting.type == "text") {
						settings[setting.identifier] =
							this.layout.settings[setting.identifier];
					} else if (setting.type == "image") {
						settings[setting.identifier] =
							this.layout.file_settings[setting.identifier];
					}
				}
				return settings;
			},
			renderedFieldGroups() {
				const content = {};
				const group_defs = this.style.fieldgroups;
				for (const fieldgroup of group_defs) {
					if (fieldgroup.type == "placeholder") {
						content[fieldgroup.identifier] = [];
						const layout_group = this.layout.fieldgroups[
							fieldgroup.identifier
						] as any as PlaceholderFieldGroupConfig;
						for (const entry of layout_group.entries) {
							const placeholder =
								entry.type === "placeholder"
									? this.variables[fieldgroup.content_type][entry.content]
									: null;

							let label = i18nstringLocalize(entry.label);
							if (placeholder && !label) {
								label = i18nstringLocalize(placeholder.label);
							}

							let value = null;
							if (entry.type == "custom") {
								value = i18nstringLocalize(entry.content);
							} else if (entry.type == "placeholder") {
								value =
									placeholder?.sample ||
									`(unknown placeholder: ${entry.content})`;
							}
							content[fieldgroup.identifier].push({
								entry,
								label,
								content: value,
							});
						}
					}
				}
				for (const fieldgroup of group_defs) {
					if (fieldgroup.type == "placeholder") {
						const layout_group: PlaceholderFieldGroupConfig =
							this.layout.fieldgroups[
								fieldgroup.identifier
							];
						if (
							fieldgroup.max_entries &&
							content[fieldgroup.identifier].length > fieldgroup.max_entries
						) {
							const overflow = content[fieldgroup.identifier].slice(
								fieldgroup.max_entries,
							);
							content[fieldgroup.identifier] = content[
								fieldgroup.identifier
							].slice(0, fieldgroup.max_entries);
							if (layout_group.overflow) {
								content[layout_group.overflow].splice(0, 0, ...overflow);
							}
						}
					}
				}

				return content;
			},
		},
		actions: {
			getPlatform(identifier: string): Platform {
				for (const platform of this.platforms) {
					if (platform.identifier === identifier) {
						return platform;
					}
				}
			},
			load() {
				// TODO: error handling / proper api client
				fetch(
					`/api/v1/organizers/demo/events/wallet/walletlayouts/${this.layoutId}/`,
				)
					.then((x) => x.json())
					.then((x) => {
						this.parseServerLayout(x);
						this.loaded = true;
					})
					.catch(alert);
			},
			parseServerLayout(serverLayout) {
				this.name = serverLayout.name;
				for (const layout of serverLayout.platform_layouts) {
					const clientLayout = {
						style: layout.style,
						fieldgroups: {},
						settings: layout.layout.settings,
						file_settings: layout.file_settings,
					};
					const styleDefinition = this.getPlatform(layout.platform).styles[
						layout.style
					];
					console.log(styleDefinition);
					for (const fieldgroup of styleDefinition.fieldgroups) {
						clientLayout.fieldgroups[fieldgroup.identifier] =
							parseExistingFieldgroupState(
								fieldgroup,
								layout.layout.fieldgroups[fieldgroup.identifier],
							);
					}
					this.platformLayouts[layout.platform] = clientLayout;
				}
			},
			setPlatform(platform: string) {
				this.activePlatform = platform;
			},
			setStyle(style: string | null) {
				if (style === null) {
					delete this.platformLayouts[this.activePlatform];
				} else if (Object.keys(this.platform.styles).includes(style)) {
					const newLayout = {
						style,
						fieldgroups: {},
						settings: {},
						file_settings: {},
					};
					for (const fieldgroup of this.platform.styles[style].fieldgroups) {
						newLayout.fieldgroups[fieldgroup.identifier] =
							getDefaultFieldgroupState(fieldgroup);
					}
					this.platformLayouts[this.activePlatform] = newLayout;
					// TODO: keep old fieldgroups & settings if matching
				}
			},
			getSetting(identifier: string): Setting {
				for (const setting of this.style.settings) {
					if (setting.identifier === identifier) {
						return setting;
					}
				}
			},
			setSetting(identifier: string, value: string | File) {
				const setting = this.getSetting(identifier);
				if (!setting) return;

				if (
					setting.type === "image" &&
					(value instanceof File || value === null)
				) {
					this.layout.file_settings[setting.identifier] = {
						file: value as File | null,
					};
				} else if (setting.type == "text" && typeof value == "string") {
					this.layout.settings[setting.identifier] = value;
				}
			},
			async uploadFile(file: ClientSideFile) {
				return await fetch("/api/v1/upload", {
					method: "POST",
					body: file.file,
					headers: {
						"content-disposition": `attachment; filename="${encodeURI(file.file.name)}"`,
						"content-type": file.file.type || "application/octet-stream",
						"X-CSRFToken": this.csrfToken,
					},
				})
					.then((x) => x.json())
					.then((x) => {
						file.identifier = x.id;
						return x.id;
					})
					.catch(alert);
			},
			async serializePlatformLayout(platform, layout: NewPlatformLayout) {
				const uploadedFiles = Object.fromEntries(
					(
						await Promise.all(
							Object.entries(layout.file_settings).map(async ([k, v]) => {
								if ("url" in v) {
									return;
								} else if ("identifier" in v) {
									return [k, v.identifier];
								} else if ("file" in v && v.file instanceof File) {
									return [k, await this.uploadFile(v)];
								} else if ("file" in v && v.file == null) {
									return [k, null];
								}
							}),
						)
					).filter((x) => !!x),
				);
				return {
					platform,
					style: layout.style,
					file_settings: uploadedFiles,
					layout: {
						fieldgroups: layout.fieldgroups,
						settings: layout.settings,
					},
				};
			},
			async serializeLayout() {
				const layoutPromises = Object.entries(this.platformLayouts).map(
					([platform, layout]) =>
						this.serializePlatformLayout(platform, layout),
				);
				return {
					name: this.name,
					platform_layouts: await Promise.all(layoutPromises),
				};
			},
			async save() {
				const serializedLayout = await this.serializeLayout();
				// TODO: error handling / proper api client
				fetch(
					`/api/v1/organizers/demo/events/wallet/walletlayouts/${this.layoutId}/`,
					{
						method: "PUT",
						headers: {
							"content-type": "application/json",
							"X-CSRFToken": this.csrfToken,
						},
						body: JSON.stringify(serializedLayout),
					},
				)
					.then((x) => x.json())
					.catch((x) => alert(x))
					.then((x) => {
						this.parseServerLayout(x);
					});
			},
		},
	});
}
