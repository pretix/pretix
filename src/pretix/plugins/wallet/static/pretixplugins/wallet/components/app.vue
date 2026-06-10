<script setup lang="ts">
import { computed, ref, watchEffect } from "vue";
import StyleSettings from "./style-settings.vue";
import Select from "./input/select.vue";
import Input from "./input/input.vue";

const gettext = (window as any).gettext;

const isLoading = ref<boolean>(true);
const wallet_layout = ref<Layout | null>(null);

const PLATFORMS: Platforms = JSON.parse(
    document.querySelector("#platforms")?.textContent ?? "{}",
);
const VARIABLES: VariableConfig = JSON.parse(
    document.querySelector("#variables")?.textContent ?? "{}",
);
const LOCALES: Record<string, string> = JSON.parse(
    document.querySelector("#locales")?.textContent ?? "{}",
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
        .catch((x) => alert(x))
        .then((x) => {
            wallet_layout.value = x;
            isLoading.value = false;
        });
}

function openForm(url: string, data: Record<string, string>) {

    let form = document.createElement("form");
    form.target = "_blank";
    form.method = "POST";
    form.action = url;
    form.style.display = "none";

    for (var key in data) {
       var input = document.createElement("input");
       input.type = "hidden";
       input.name = key;
       input.value = data[key];
       form.appendChild(input);
    }
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
}


const currentPlatform = ref(PLATFORMS[0].identifier);
const currentLayout = computed(() => ({}));
const platformStyles = computed(() => {
    for (const platform of PLATFORMS) {
        if (platform.identifier === currentPlatform.value) {
            return platform.styles
        }
    }
});
const platformLayout = computed(() => {
    for (const layout of wallet_layout.value.platform_layouts) {
        if (layout.platform === currentPlatform.value) {
            return layout
        }
    }
    const newLayout = {platform: currentPlatform, style: null, layout: {}};
    wallet_layout.value.platform_layouts.push(newLayout);
    return newLayout
});
const platformChoices = computed(() => {
    return [[null, "Do not generate pass"], ...Object.values(platformStyles.value).map(x => [x.identifier, x.name])]
});

function openPreview(e: SubmitEvent) {
    e.preventDefault();
    openForm("../../preview/", {"csrfmiddlewaretoken": CSRF_TOKEN, "platform": currentPlatform.value, "style": platformLayout.value.style, "layout": JSON.stringify(platformLayout.value.layout)})
}
</script>

<template lang="pug">
    // TODO: add :key for all `v-for`s
    // TODO: i18n textfields
    // TODO: proper spinner
    template(v-if="isLoading") {{ gettext("Loading...") }}
    form(v-else @submit="saveLayout")
        .form-group
            Input(label="Name" v-model="wallet_layout.name")
        nav
            ul.nav.nav-tabs
                li(v-for="platform in PLATFORMS" :class="{'active': currentPlatform === platform.identifier}")
                    a(role="tab" @click="currentPlatform = platform.identifier") {{ platform.name }}
        .tabbed-form.tab-content
            .tab-pane.active.row
                .col-md-8
                    Select.form-group(label="Style" v-model="platformLayout.style" :choices="platformChoices")

                    StyleSettings(v-if="platformLayout.style" v-model="platformLayout.layout" :style="platformStyles[platformLayout.style]" :variables="VARIABLES" :locales="LOCALES")
                .col-md-4
                    .panel.panel-default
                        .panel-heading Preview
                        .panel-body
                            // TODO: Preview
                            pre
                                code {{ platformLayout }}
                            pre(v-if="wallet_layout.style")
                                code {{ platformStyles[wallet_layout.style] }}
                            pre
                                code {{ wallet_layout }}
        .form-group.submit-group
            button.btn.btn-lg.btn-default(type="button" @click="openPreview") Preview
            button.btn.btn-primary.btn-save(type="submit") Submit

</template>
