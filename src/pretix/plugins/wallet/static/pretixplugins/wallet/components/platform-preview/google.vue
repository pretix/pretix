<script setup lang="ts">
import { computed, inject } from "vue";
import { StoreKey } from "../../walletStore";
import { dateTimeFormat, i18nstringLocalize } from "../../helpers";

const store = inject(StoreKey)!;

const props = defineProps<{ data: any }>();

function isActive(fieldgroup: string) {
	return store.layout.fieldgroups[fieldgroup]?.active;
}

const qrcode = computed(() => store.renderedFieldGroups["code"]?.[0]);
</script>

<template lang="pug">
    div.pass-preview-google(style="")
        div.f-column
            .pass-container.f-row
                img.logo(:src="store.getSettingValue('logo')?.url")
                div
                    .bold {{ data.event }}
                    div(v-if="isActive('date')") {{ dateTimeFormat(data.date_from, {"dateStyle": "medium"}) }}
                    div(v-else) {{  data.organizer }}

            .pass-container.google-main(:data-background-color="store.getSettingValue('bg_color')")
                .pass-inner
                    .f-row
                        img.logo(:src="store.getSettingValue('logo')?.url")
                        div.logo-text {{  data.organizer }}

                    .top-row
                        div(v-if="isActive('venue')") {{ i18nstringLocalize(data.venue?.[0]) }}
                        .event-name {{ data.event }}

                    .f-column
                        slot(name="card-rows")

                    .qrcode-inner(v-for="qrcode in store.renderedFieldGroups['code']") {{ qrcode.label }}

                    .f-column
                        img.hero(:src="store.getSettingValue('hero')?.url")

        .pass-container.google-pass-details
            .pass-inner
                slot(name="details")

</template>

<style lang="css">
.pass-preview-google {
	display: grid;
	gap: 1em;
	grid-template-columns: repeat(auto-fit, minmax(auto, 360px));
	align-items: start;

	.google-main {
		--background-color: attr(data-background-color type(<color>));
		color: contrast-color(var(--background-color));
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

	.top-row > .event-name {
		font-size: 1.75em;
	}

	.card-row {
		display: flex;
		flex-direction: row;
		gap: inherit;

		> div {
			flex: 0 1 100%;
		}

		&:has(> :first-child:nth-last-child(2)) {
			/* twoItems */
			> :nth-child(2) {
				text-align: end;
			}
		}
		&:has(> :first-child:nth-last-child(3)) {
			/* threeItems */
			> :nth-child(2) {
				text-align: center;
			}
			> :nth-child(3) {
				text-align: end;
			}
		}
	}

	.card-row {
		.pass-label {
			font-size: 0.9em;
		}
	}

	.hero {
		align-self: center;
		max-width: 100%;
	}

	.google-pass-details {
		.pass-label {
			font-weight: bold;
		}
		.pass-content {
			font-size: 0.9em;
			white-space: pre-wrap;
		}
	}

	.pass-details-link {
		color: black;
	}
}
</style>
