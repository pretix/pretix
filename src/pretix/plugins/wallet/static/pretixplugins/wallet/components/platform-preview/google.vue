<script setup lang="ts">
import { computed, inject } from "vue";
import { StoreKey } from "../../walletStore";
import { i18nstringLocalize } from "../../helpers";

const store = inject(StoreKey)!;

const props = defineProps<{ data: any }>();

function isActive(fieldgroup: string) {
	return store.layout.fieldgroups[fieldgroup]?.active;
}

const qrcode = computed(() => store.renderedFieldGroups["code"]?.[0]);
</script>

<template lang="pug">
    div(style="display: grid; gap: 1em; grid-template-columns: repeat(auto-fit, minmax(auto, 360px));")
        .google-pass-container.f-row
            img.logo(:src="store.getSettingValue('logo')?.url")
            div
                .bold {{ data.event }}
                div(v-if="isActive('date')") {{ data.date_from }}
                div(v-else) {{  data.organizer }}

        .google-pass-container(:style="{'--background-color': store.getSettingValue('bg_color')}")
            .f-row
                img.logo(:src="store.getSettingValue('logo')?.url")
                div.logo-text {{  data.organizer }}
            div
                div(v-if="isActive('venue')") {{ i18nstringLocalize(data.venue?.[0]) }}
                div.large {{ data.event }}
            // TODO: front card
            .qrcode-inner(v-if="qrcode") {{ qrcode.label }}
            .f-column
                img.hero(:src="store.getSettingValue('hero')?.url")

        .google-pass-container
            div(v-for="entry in store.renderedFieldGroups['details']")
                div.pass-details-label {{ entry.label }}
                div.pass-details-content {{ entry.content }}
</template>

<style lang="css" scoped>
.google-pass-container {
	min-width: 0;
	width: 100%;
	vertical-align: top;
	display: flex;
	flex-direction: column;
	border: solid 1px #949494;
	border-radius: 1em;
	padding: 1em;

	background-image: var(--background-image);
	background-color: var(--background-color);
	color: contrast-color(var(--background-color));
	background-size: cover;
	background-position: center;

	gap: 1em;
}

.f-row {
	display: flex;
	flex-direction: row;
	gap: inherit;
}
.f-column {
	display: flex;
	flex-direction: column;
	gap: inherit;
}
.bold {
	font-weight: bold;
}
.logo {
	height: 2lh;
	aspect-ratio: 1;
	border-radius: 50%;
	background-color: white;
	object-fit: fill;
}
.logo-text {
	align-self: center;
	font-size: 1.5em;
}
.large {
	font-size: 2em;
}
.qrcode-inner {
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
.hero {
    align-self: center;
}
.pass-details-label {
    font-weight: bold;
}
.pass-details-content {
    font-size: 0.9em;
}
</style>
