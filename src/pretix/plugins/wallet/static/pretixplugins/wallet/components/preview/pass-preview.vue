<script setup lang="ts">
import { computed, inject } from "vue";
import { StoreKey } from "../../walletStore.js";
import RowPreview from "./row-preview.vue";

const store = inject(StoreKey)!;

const { layout } = defineProps<{ layout: PreviewLayout }>();

function isPredefined(
	row: PreviewFieldgroup,
): row is PredefinedFieldgroupPreview {
	const fieldgroup = store.fieldgroups[row.fieldgroup];
	return fieldgroup.type == "predefined";
}

function getSettingPreview(setting: string) {
	const settingDef = store.styles[store.layout.style].settings.find(
		(x) => x.identifier == setting,
	);
	const val = store.settings[setting];

	if (settingDef.type == "image") {
		if (val && "url" in val && val.url) {
			return { content: val.url, content_type: "image" };
		} else if (settingDef.default) {
			return { content: settingDef.default, content_type: "image" };
		}
	} else if (val) {
		return { content: val, content_type: "text" };
	} else if (settingDef.default) {
		return { content: settingDef.default, content_type: "text" };
	}
}

function evaluateStyle(style: StyleConfig) {
	return Object.fromEntries(
		Object.entries(style)
			.map(([k, v]) => {
				if (typeof v !== "string" && v.setting) {
					const settingsVal = getSettingPreview(v.setting);
					if (!settingsVal) {
						v = null;
					} else if (settingsVal.content_type == "image") {
						v = `url(${encodeURI(settingsVal.content)})`;
					} else {
						v = settingsVal.content;
					}
				}
				return [k, v];
			})
			.filter(([_k, v]) => !!v),
	);
}

type EvaluatedPreviewItem = {
	label?: LocalizableString;
	content: LocalizableString;
	content_type?: "text" | "image";
};
type EvaluatedPreviewRow = (
	| EvaluatedPreviewItem
	| { children: EvaluatedPreviewRow[] }
) & {
	display?: string;
	display_class?: string | string[];
	style?: Record<string, string | number>;
};

function hasEntries(row) {
	if ("content" in row) {
		return true;
	} else if ("children" in row) {
		return row.children.some(hasEntries);
	}
}
function evaluateRow(row: PreviewRow): EvaluatedPreviewRow {
	if ("children" in row) {
		const style = {
			"flex-direction": row.direction || "row",
		};
		const children = row.children.map(evaluateRow).filter((x) => !!x);
		if (row.max_entries) {
			children.splice(row.max_entries);
		}
		return { children, display_class: row.display_class, style };
	} else if ("fieldgroup" in row) {
		// TODO: click
		const style = {
			"flex-grow": row.relSize,
			"flex-direction": row.direction || "row",
		};
		if (isPredefined(row)) {
			if (store.layout.fieldgroups[row.fieldgroup]?.active) {
				return { style: style, children: row.sample, display_class: row.display_class };
			}
		} else {
			return {
				style: style,
				children: store.renderedFieldGroups[row.fieldgroup],
				display_class: row.display_class
			};
		}
	} else if ("content" in row) {
		return { label: row.label, content: row.content, display_class: row.display_class };
	} else if ("setting" in row) {
		return { ...getSettingPreview(row.setting), display_class: row.display_class };
	}
}

const renderedLayout = computed(() => {
	return {
		style: evaluateStyle(layout.style || {}),
		rows: layout.rows.map(evaluateRow),
	};
});
</script>

<template lang="pug">
    div.pass-container(:style="renderedLayout.style")
        div.pass-content
            RowPreview(v-for="row of renderedLayout.rows" :config="row")
</template>

<style lang="css" scoped>
.pass-container {
	width: 100%;
	max-width: 360px;
	vertical-align: top;
	display: inline-block;

	border: solid 1px #949494;
	border-radius: 1em;
	padding: 1em;

	overflow: hidden;
	position: relative;

	background-image: var(--background-image);
	background-color: var(--background-color);
	background-size: cover;
	background-position: center;
}

.pass-container::before {
	content: "";
	position: absolute;
	top: 0;
	left: 0;
	width: 100%;
	height: 100%;
	backdrop-filter: blur(10px);
	pointer-events: none;
}

.pass-content {
	overflow: scroll;
	display: flex;
	flex-direction: column;
	gap: 1em;
	position: relative;
}
</style>

<style lang="css">
.pass-container {
	.fieldgroup-container {
		min-width: 0;
		display: flex;
		gap: 0.5em;
		min-height: 2lh;
	}
	.fieldgroup-label {
		font-weight: bold;
		font-size: 0.8em;
		color: var(--label-color);
	}
	.fieldgroup-item {
		flex: 0 1 100%;
		min-width: 0;
		display: flex;
		flex-direction: column;
		white-space: pre-wrap;
	}
	.fieldgroup-item-image {
		object-fit: contain;
	}
	.fieldgroup-item-qrcode {
		font-weight: bold;
		background-color: lightgray;
		color: black;
		width: 50%;
		aspect-ratio: 1;
		align-self: center;

		/* center content */
		display: flex;
		align-items: center;
		text-align: center;
		justify-content: center;
		padding: 1em;
		overflow-wrap: anywhere;
	}
	.nowrap {
		text-overflow: ellipsis;
		overflow: hidden;
		text-wrap: nowrap;
	}
	.bold {
		font-weight: bold;
	}
	.large {
		font-size: 1.5em;
	}
	.tight {
		line-height: 1;
		gap: 0.25rem;
	}
	.img-inline {
		max-height: 3lh;
	}
	.img-circle-sm {
		max-height: 2lh;
		aspect-ratio: 1;
		border-radius: 50%;
		background-color: white;
		object-fit: fill;
	}
}
</style>
