import { i18nstringLocalize } from "./helpers.js";
import { createStore } from "./lib/store.ts";
import { toRaw, type InjectionKey } from "vue";

export type WidgetStore = ReturnType<typeof createWalletStore>;
export const StoreKey: InjectionKey<WidgetStore> = Symbol("WidgetStore");

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
			walletLayout: null as WalletLayout | null,
			currentPlatform: config.platforms[0].identifier,
			loaded: false,
            files: {} as Record<string, File>
		}),
		getters: {
			currentPlatformStyles() {
				for (const platform of this.platforms) {
					if (platform.identifier === this.currentPlatform) {
						return platform.styles;
					}
				}
				throw "Unknown platform";
			},
			currentPlatformLayout(): PlatformLayout {
				if (!this.walletLayout) {
					throw "currentPlatformLayout access before store was loaded";
				}
				for (const layout of this.walletLayout.platform_layouts) {
					if (layout.platform === this.currentPlatform) {
						if (!("fieldgroups" in layout.layout)) {
							layout.layout.fieldgroups = {};
						}
						if (!("settings" in layout.layout)) {
							layout.layout.settings = {};
						}
						return layout;
					}
				}
				const newLayout = {
					platform: this.currentPlatform,
					style: null,
					layout: { fieldgroups: {}, settings: {} },
				};
				this.walletLayout.platform_layouts.push(newLayout);
				return newLayout;
			},

			currentLayoutFieldContent() {
				const content = {};
				const group_defs =
					this.currentPlatformStyles[this.currentPlatformLayout.style]
						.fieldgroups;
				for (const fieldgroup of group_defs) {
					if (fieldgroup.type == "placeholder") {
						content[fieldgroup.identifier] = [];
						const layout_group = this.currentPlatformLayout.layout.fieldgroups[
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
							this.currentPlatformLayout.layout.fieldgroups[
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
			currentLayoutSettings() {
				return {...this.currentPlatformLayout.file_settings, ...this.currentPlatformLayout.layout.settings}
			},
		},
		actions: {
			load() {
				// TODO: error handling / proper api client
				fetch(
					`/api/v1/organizers/demo/events/wallet/walletlayouts/${this.layoutId}/`,
				)
					.then((x) => x.json())
					.then((x) => {
						this.walletLayout = x;
						this.loaded = true;
					});
			},
			async uploadFile(file: File) {
				return await fetch("/api/v1/upload", {
					method: "POST",
					body: file,
					headers: {
						"content-disposition": `attachment; filename="${encodeURI(file.name)}"`,
						"content-type": file.type || "application/octet-stream",
						"X-CSRFToken": this.csrfToken,
					},
				})
					.then((x) => x.json())
					.then((x) => x.id);
			},
			async saveLayout() {
                const layoutToSave = structuredClone(toRaw(this.walletLayout))
                // TODO: error handling, parallelization
				for (const platformLayout of layoutToSave.platform_layouts) {
					const platformStyle = this.platforms.filter(
						(x) => x.identifier == platformLayout.platform,
					)[0].styles[platformLayout.style];
					for (const setting of platformStyle.settings) {
                        console.log(setting, platformLayout.layout?.settings[setting.identifier])
						if (
							setting.type === "image" &&
							platformLayout.layout?.settings[setting.identifier] instanceof
								File
						) {
							platformLayout.layout.settings[setting.identifier] = await
								this.uploadFile(
									platformLayout.layout.settings[setting.identifier],
								);
						}
					}
				}
				// TODO: error handling / proper api client
				fetch(
					`/api/v1/organizers/demo/events/wallet/walletlayouts/${this.layoutId}/`,
					{
						method: "PUT",
						headers: {
							"content-type": "application/json",
							"X-CSRFToken": this.csrfToken,
						},
						body: JSON.stringify(layoutToSave),
					},
				)
					.then((x) => x.json())
					.catch((x) => alert(x))
					.then((x) => {
						this.walletLayout = x;
					});
			},
			setCurrentPlatformStyle(style: string | null) {
				if (style === null) {
					this.currentPlatformLayout.style = null;
					this.currentPlatformLayout.layout.fieldgroups = {};
				} else if (Object.keys(this.currentPlatformStyles).includes(style)) {
					const oldStyle =
						this.currentPlatformLayout.style !== null
							? this.currentPlatformStyles[this.currentPlatformLayout.style]
							: { fieldgroups: [] };
					const newStyle = this.currentPlatformStyles[style];

					const oldFieldGroups = Object.fromEntries(
						oldStyle.fieldgroups.map((x) => [x.identifier, x]),
					);
					const newFieldGroups = Object.fromEntries(
						newStyle.fieldgroups.map((x) => [x.identifier, x]),
					);
					const keysToKeep = new Set(
						Object.keys(this.currentPlatformLayout.layout.fieldgroups).filter(
							(x) =>
								oldFieldGroups[x]?.type === "placeholder" &&
								newFieldGroups[x]?.type === "placeholder" &&
								oldFieldGroups[x]?.content_type ===
									newFieldGroups[x]?.content_type,
						),
					);
					const keysToDefault = new Set(Object.keys(newFieldGroups)).difference(
						keysToKeep,
					);
					const keysToRemove = new Set(
						Object.keys(this.currentPlatformLayout.layout.fieldgroups),
					)
						.difference(keysToKeep)
						.difference(keysToDefault);

					for (const key of keysToRemove) {
						delete this.currentPlatformLayout.layout.fieldgroups[key];
					}

					for (const key of keysToDefault) {
						if (newFieldGroups[key].type == "placeholder") {
							this.currentPlatformLayout.layout.fieldgroups[key] = {
								overflow: null,
								entries: JSON.parse(
									JSON.stringify(newFieldGroups[key].default_entries),
								),
								active:
									newFieldGroups[key].required ||
									newFieldGroups[key].default_entries.length > 0,
							};
						} else {
							this.currentPlatformLayout.layout.fieldgroups[key] = {
								active: newFieldGroups[key].required,
							};
						}
					}

					this.currentPlatformLayout.style = style;
				}
			},
			setSetting(identifier: string, value: string | File | null) {
				this.currentPlatformLayout.layout.settings[identifier] = value;
			},
		},
	});
}
