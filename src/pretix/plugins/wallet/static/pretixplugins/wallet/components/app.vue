<script setup lang="ts">
import { computed, inject, ref, watchEffect } from "vue";
import StyleSettings from "./style-settings.vue";
import Select from "./input/select.vue";
import Input from "./input/input.vue";
import { StoreKey } from "../walletStore";
import GoogleEventDefault from "./platform-preview/google-event-default.vue";
import GoogleEventCustom from "./platform-preview/google-event-custom.vue";
import Apple from "./platform-preview/apple.vue";

const store = inject(StoreKey)!;
const gettext = (window as any).gettext;

function openForm(url: string, data: Record<string, string | object>) {
	let form = document.createElement("form");
	form.target = "_blank";
	form.method = "POST";
	form.action = url;
	form.style.display = "none";

	for (var key in data) {
		var input = document.createElement("input");
		input.type = "hidden";
		input.name = key;
		let value = data[key];
		if (value instanceof Object) {
			value = JSON.stringify(data[key]);
		}
		input.value = value;
		form.appendChild(input);
	}
	document.body.appendChild(form);
	form.submit();
	document.body.removeChild(form);
}

async function openPreview(e: Event) {
	e.preventDefault();
	openForm("../../preview/", {
		csrfmiddlewaretoken: store.csrfToken,
		id: store.layoutId,
		...(await store.serializeCurrentPlatformLayout()),
	});
}

const platformChoices = computed(() => {
	return [
		[null, "Do not generate pass"],
		...Object.values(store.platform.styles).map((x) => [x.identifier, x.name]),
	];
});

const previewRenderers = {
	google_eventticket_default: GoogleEventDefault,
	google_eventticket_custom: GoogleEventCustom,
	apple_eventticket: Apple,
};
</script>

<template lang="pug">
    // TODO: add :key for all `v-for`s
    // TODO: proper spinner

    template(v-if="!store.loaded") {{ gettext("Loading...") }}
    form(v-else @submit.prevent="store.save")
        .form-group
            Input(label="Name" v-model="store.name")
        nav
            ul.nav.nav-tabs
                li(v-for="platform in store.platforms" :class="{'active': store.platform.identifier === platform.identifier}")
                    a(role="tab" @click="store.setPlatform(platform.identifier)") {{ platform.name }}
        .tabbed-form.tab-content
            .tab-pane.active.row
                .col-md-6.col-lg-8
                    Select.form-group(label="Style" :modelValue="store.style?.identifier || null" @update:modelValue="store.setStyle" :choices="platformChoices")
                    button(type="button" @click="store.setStyle(store.style.identifier)") Reset style
                    StyleSettings(v-if="!!store.style")
                .col-md-6.col-lg-4(style="position: sticky; top: 10px;")
                    .panel.panel-default
                        .panel-heading Preview
                        .panel-body
                            div(v-if="!!store.style?.preview_renderer && store.style?.preview_renderer in previewRenderers")
                                p.text-muted {{ gettext("The preview below is only a rough representation of what the pass might look like. Please check the generated pass.") }}
                                component(:is="previewRenderers[store.style?.preview_renderer]" :data="store.style?.preview_data")
                            div(v-else) Preview not supported
        .form-group.submit-group
            button.btn.btn-lg.btn-default(type="button" @click="openPreview") Preview
            button.btn.btn-primary.btn-save(type="submit") Submit

</template>

<style lang="css">
.walletsettings-panel .panel-heading {
	.checkbox {
		padding: 0;
		margin: 0;
		display: inline-block;
		input[type="checkbox"] {
			margin-top: 0;
			margin-right: 5px;
			margin-left: 0px;
			position: relative;
			top: 1px;
		}
		label {
			padding-left: 0;
		}
	}
}
.walletsettings-panel .panel-body {
	> :is(h1, h2, h3, h4, h5, h6):first-child {
		margin-top: 0;
	}
}

.pass-container {
	min-width: 0;
	width: 100%;
	min-height: 0;

	border: solid 1px #949494;
	border-radius: 1em;
	padding: 1em;

	overflow: hidden;
	position: relative;

	background-image: var(--background-image);
	background-color: var(--background-color);
	color: var(--bg-color);
	background-size: cover;
	background-position: center;
}

.blur-bg::before {
	content: "";
	position: absolute;
	top: 0;
	left: 0;
	width: 100%;
	height: 100%;
	backdrop-filter: blur(10px);
	pointer-events: none;
}

.f-row {
	display: flex;
	flex-direction: row;
	gap: inherit;
	> div {
		min-width: 0;
	}
}
.f-column {
	display: flex;
	flex-direction: column;
	gap: inherit;
}

.pass-inner {
	position: relative;
	gap: 1em;

	display: flex;
	flex-direction: column;
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
</style>
