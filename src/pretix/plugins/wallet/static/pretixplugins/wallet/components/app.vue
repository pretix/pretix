<script setup lang="ts">
import { computed, inject, ref, watchEffect } from "vue";
import StyleSettings from "./style-settings.vue";
import Select from "./input/select.vue";
import Input from "./input/input.vue";
import { StoreKey } from "../walletStore";

const gettext = (window as any).gettext;

const store = inject(StoreKey)!


const platformChoices = computed(() => {
    return [[null, "Do not generate pass"], ...Object.values(store.currentPlatformStyles).map(x => [x.identifier, x.name])]
});

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

function openPreview(e: SubmitEvent) {
    e.preventDefault();
    openForm("../../preview/", {"csrfmiddlewaretoken": store.csrfToken, "platform": store.currentPlatform, "style": store.currentPlatformLayout.style, "layout": JSON.stringify(store.currentPlatformLayout.layout)})
}
</script>

<template lang="pug">
    // TODO: add :key for all `v-for`s
    // TODO: i18n textfields
    // TODO: proper spinner

    template(v-if="!store.loaded") {{ gettext("Loading...") }}
    form(v-else @submit.prevent="store.saveLayout")
        .form-group
            Input(label="Name" v-model="store.walletLayout.name")
        nav
            ul.nav.nav-tabs
                li(v-for="platform in store.platforms" :class="{'active': store.currentPlatform === platform.identifier}")
                    a(role="tab" @click="store.currentPlatform = platform.identifier") {{ platform.name }}
        .tabbed-form.tab-content
            .tab-pane.active.row
                .col-md-8
                    Select.form-group(label="Style" :modelValue="store.currentPlatformLayout.style" @update:modelValue="store.setCurrentPlatformStyle" :choices="platformChoices")

                    StyleSettings(v-if="store.currentPlatformLayout.style" v-model="store.currentPlatformLayout.layout" :style="store.currentPlatformStyles[store.currentPlatformLayout.style]")
                .col-md-4
                    .panel.panel-default
                        .panel-heading Preview
                        .panel-body
                            span.text-muted The preview below is only a rough representation of what the pass might look like. Please check the generated pass.
                            div(style="margin-top: 1em; width: 10cm; height: 15cm; position: relative; border: solid 1px gray; border-radius: 1em;")
                                div(style="position: absolute; background-color: red; top: 0.5cm; left: 0cm; height: 1cm; width: 2cm;") Logo
                                div(style="position: absolute; background-color: red; top: 0.5cm; left: 2.25cm; height: 1cm; width: 5.5cm;") Logo Text
                                div(style="position: absolute; background-color: red; top: 0.5cm; left: 8cm; height: 1cm; width: 2cm;") Header
                                div(style="position: absolute; background-color: red; top: 2.5cm; left: 0cm; height: 2cm; width: 10cm;") Primary
                                div(style="position: absolute; background-color: red; top: 4.75cm; left: 0cm; height: 1cm; width: 10cm;") Secondary
                                div(style="position: absolute; background-color: red; top: 7cm; left: 0cm; height: 1cm; width: 10cm;") Auxiliary
                                div(style="position: absolute; background-color: red; top: 10cm; left: 3cm; height: 4cm; width: 4cm;") Barcode
                            // TODO: Preview
                            pre
                                code {{ store.currentPlatformLayout }}
                            pre(v-if="store.currentPlatformLayout.style")
                                code {{ store.currentPlatformStyles[store.currentPlatformLayout.style] }}
                            pre
                                code {{ store.walletLayout }}
        .form-group.submit-group
            button.btn.btn-lg.btn-default(type="button" @click="openPreview") Preview
            button.btn.btn-primary.btn-save(type="submit") Submit

</template>
