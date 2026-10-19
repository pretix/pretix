<script setup lang="ts">
import { computed, inject } from "vue";
import { StoreKey } from "../../walletStore";
import FieldGroupEntries from "./FieldGroupEntries.vue";
const store = inject(StoreKey)!;
const props = defineProps<{ data: any }>();

const theme = computed(() => {
	const theme = {
		bg_color: store.getSettingValue("bg_color"),
		fg_color: store.getSettingValue("fg_color"),
		label_color: store.getSettingValue("label_color"),
		bg_image: null,
	};
	const bg_image = store.getSettingValue("background");
	if (bg_image?.url) {
		theme.bg_image = `url(${encodeURI(store.getSettingValue("background").url)})`;
		theme.bg_color = "#000";
	}
	return theme;
});
</script>

<template lang="pug">
    div.apple-pass-preview
        .pass-container.blur-bg.apple-pass-front
            .pass-inner.f-column
                .f-row.head-row
                    img.logo(:src="store.getSettingValue('logo')?.url")
                    div.logo-text {{ store.renderedFieldGroups['logo_text']?.[0]?.content }}
                    FieldGroupEntries.header(fieldgroup="header")

                .f-column
                    FieldGroupEntries.primary(fieldgroup="primary")
                    FieldGroupEntries.f-row(fieldgroup="secondary")
                    FieldGroupEntries.f-row(fieldgroup="auxiliary")

                .qrcode-inner(v-for="qrcode in store.renderedFieldGroups['code']") {{ qrcode.label }}

        .pass-container.apple-pass-back
            FieldGroupEntries.pass-inner.f-column(fieldgroup="back")

</template>

<style lang="css">
.apple-pass-preview {
	display: grid;
	gap: 1em;
	grid-template-columns: repeat(auto-fit, minmax(auto, 360px));
	align-items: start;

	.apple-pass-front {
		background-image: v-bind("theme.bg_image");
		background-color: v-bind("theme.bg_color");
		color: v-bind("theme.fg_color");
		background-size: cover;
		background-position: center;

		padding-top: 0.25em;
	}

	.pass-content {
		text-overflow: ellipsis;
		overflow: hidden;
		text-wrap: nowrap;
	}

	.head-row {
		align-items: center;
		gap: 0.5rem;
	}

	.logo {
		max-height: 3lh;
		object-fit: contain;
		flex-grow: 0;
	}
	.logo-text {
		font-size: 1.5em;
		font-weight: bold;
		min-height: 2lh;
		flex: 1 1 3;
		align-content: center;
		text-wrap: nowrap;
	}
	.header {
		flex: 1 0 fit-content;
		text-align: end;
		line-height: 1.25;
		gap: 0.25rem;
		.pass-content {
			font-size: 1.25em;
		}
	}
	.primary {
		.pass-content {
			font-size: 1.5em;
		}
	}

	.hero {
		align-self: center;
		max-width: 100%;
	}

	.apple-pass-front .pass-label {
		font-weight: bold;
		font-size: 0.8em;
		text-overflow: ellipsis;
		overflow: hidden;
		text-wrap: nowrap;

		color: v-bind("theme.label_color");
	}

	.apple-pass-back .pass-label {
		font-weight: bold;
	}
}
</style>
