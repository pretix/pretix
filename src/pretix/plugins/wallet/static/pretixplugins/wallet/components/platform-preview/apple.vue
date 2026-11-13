<script setup lang="ts">
import { computed } from 'vue'
import type { PreviewProps } from 'src/pretix/static/pretixcontrol/wallet/index.d.ts'

import FieldGroupEntries from './FieldGroupEntries.vue'

const props = defineProps<PreviewProps>()

const theme = computed(() => {
	const theme = {
		bg_color: props.settings['bg_color'],
		fg_color: props.settings['fg_color'],
		label_color: props.settings['label_color'],
		bg_image: null,
	}
	const bg_image = props.settings['background']
	if (bg_image?.url) {
		theme.bg_image = `url(${encodeURI(props.settings['background'].url)})`
		theme.bg_color = '#000'
		theme.fg_color = '#fff'
	}
	return theme
})
</script>

<template lang="pug">
    div.apple-pass-preview
        .pass-container.blur-bg.apple-pass-front
            .pass-inner.f-column
                .f-row.head-row
                    img.logo(:src="settings['logo']?.url")
                    div.logo-text {{ fieldgroup_contents['logo_text']?.[0]?.content }}
                    FieldGroupEntries.header.f-row(fieldgroup="header" :fieldgroup_contents="fieldgroup_contents")

                .f-column
                    FieldGroupEntries.primary(fieldgroup="primary" :fieldgroup_contents="fieldgroup_contents")
                    FieldGroupEntries.f-row(fieldgroup="secondary" :fieldgroup_contents="fieldgroup_contents")
                    FieldGroupEntries.f-row(fieldgroup="auxiliary" :fieldgroup_contents="fieldgroup_contents")

                .qrcode-inner(v-for="qrcode in fieldgroup_contents['code']") {{ qrcode.label }}

        .pass-container.apple-pass-back
            FieldGroupEntries.pass-inner.f-column(fieldgroup="back" :fieldgroup_contents="fieldgroup_contents")

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
		flex: 1 1;
		align-content: center;
		text-wrap: nowrap;
	}
	.header {
		flex: 1 0 fit-content;
		text-align: end;
		line-height: 1.25;
		gap: 0.25rem;
		justify-content: end;
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
