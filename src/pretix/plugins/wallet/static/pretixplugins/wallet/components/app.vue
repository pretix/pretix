<script setup lang="ts">
import { computed, ref, watchEffect } from "vue";
import StyleSettings from "./style-settings.vue";
import Select from "./input/select.vue";
import Input from "./input/input.vue";

const gettext = (window as any).gettext;

const isLoading = ref<boolean>(true);
const wallet_layout = ref<Layout | null>(null);

const STYLES: Styles = JSON.parse(
	document.querySelector("#styles")?.textContent ?? "{}",
);
const VARIABLES: VariableConfig = JSON.parse(
	document.querySelector("#variables")?.textContent ?? "{}",
);
const CSRF_TOKEN =
	document.querySelector<HTMLInputElement>("input[name=csrfmiddlewaretoken]")
		?.value ?? "";

const props = defineProps<{
	layoutId: string;
}>();

watchEffect(() => {
	// TODO: error handling / proper api client
	isLoading.value = true;
	fetch(
		`/api/v1/organizers/demo/events/wallet/walletlayouts/${props.layoutId}/`,
	)
		.then((x) => x.json())
		.then((x) => {
			wallet_layout.value = x;
			isLoading.value = false;
		});
});

function saveLayout(e: SubmitEvent) {
	e.preventDefault();
	isLoading.value = true;
	// TODO: error handling / proper api client
	fetch(
		`/api/v1/organizers/demo/events/wallet/walletlayouts/${props.layoutId}/`,
		{
			method: "PUT",
			headers: {
				"content-type": "application/json",
				"X-CSRFToken": CSRF_TOKEN,
			},
			body: JSON.stringify(wallet_layout.value),
		},
	)
		.then((x) => x.json())
		.then((x) => {
			wallet_layout.value = x;
			isLoading.value = false;
		});
}
</script>

<template lang="pug">
    // TODO: add :key for all `v-for`s
    // TODO: i18n textfields
    // TODO: proper spinner
    template(v-if="isLoading") {{ gettext("Loading...") }}
    form(v-else @submit="saveLayout")
        .row
            .col-md-8
                .form-group()
                    Input(label="Name" v-model="wallet_layout.name")

                .form-group()
                    Select(label="Style" v-model="wallet_layout.style" :choices="Object.values(STYLES).map(x => [x.identifier, x.name])")

                StyleSettings(v-if="wallet_layout.style" v-model="wallet_layout.layout" :style="STYLES[wallet_layout.style]" :variables="VARIABLES")
            .col-md-4
                .panel.panel-default
                    .panel-heading Preview
                    .panel-body
                        // TODO: Preview
                        pre
                            code {{ wallet_layout }}
        .form-group.submit-group
            button.btn.btn-primary.btn-save(type="submit") Submit
</template>
