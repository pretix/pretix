<script setup lang="ts">
import { computed, inject } from "vue";
import { StoreKey } from "../../walletStore.js";
import RowPreview from "./row-preview.vue";

const store = inject(StoreKey)!;

const { layout } = defineProps<{ layout: Array<PreviewLayout> }>();

const layoutStyle = computed(() => {
	if (layout.style) {
		return Object.fromEntries(
			Object.entries(layout.style)
				.map(([k, v]) => {
					if (v.setting) {
						const settingDef = store.styles[store.layout.style].settings.find(
							(x) => x.identifier == v.setting,
						);
						const val = store.settings[v.setting];
						if (!settingDef) {
							v = null;
						} else if (
							settingDef.type == "image" &&
							val &&
							"file" in val &&
							val.file
						) {
							v = `url(${URL.createObjectURL(val.file)})`; // TODO: encode
						} else if (settingDef.type == "image" && val && val.url) {
							v = `url(${val.url})`;
						} else if (settingDef.type == "image" && settingDef.attrs.default) {
							v = `url(${settingDef.attrs.default})`;
						} else {
							v = val;
						}
					} else if (v.value) {
						v = v.value;
					}
					return [k, v];
				})
				.filter(([k, v]) => !!v),
		);
	}
});
console.log("layoutStyle", layoutStyle.value);
</script>

<template lang="pug">
    div(style="container-type: inline-size;")
        div.pass-container(:style="layoutStyle")
            div.pass-content
                RowPreview(v-for="row of layout.rows" :config="row")
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
		width: 100%;
		display: flex;
		flex-direction: column;
		justify-content: center;
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
		margin: auto;

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
	}
	.img-inline {
		max-height: 3lh;
	}
}
</style>
