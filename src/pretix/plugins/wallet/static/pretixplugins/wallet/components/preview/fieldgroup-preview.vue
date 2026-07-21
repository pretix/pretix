<script setup lang="ts">
import { computed, inject, reactive, watchEffect } from "vue";
import { StoreKey } from "../../walletStore";
import PlaceholderFieldgroupPreview from "./placeholder-fieldgroup-preview.vue";

const store = inject(StoreKey)!

const props = defineProps<{
    config: PreviewFieldgroup;
}>();

const style_def = Object.fromEntries(store.currentPlatformStyles[store.currentPlatformLayout.style].fieldgroups.map(x => [x.identifier, x]))[props.config.fieldgroup]

</script>

<template lang="pug">
    PlaceholderFieldgroupPreview(v-if="style_def && style_def.type == 'placeholder'" :config="config" :style_def="style_def")
    PlaceholderFieldgroupPreview(v-else-if="style_def && style_def.type == 'predefined'" :config="config" :style_def="style_def")
    //- // TODO: support predefined group
    //- div(:style="{'flex-grow': config.relSize}")
    //-     div(style="background-color: gray; display: flex; flex-direction: row;")
    //-         div(v-for="entry in layout.entries.slice(0,style_def.max_entries)")
    //-             div(v-if="style_def.labels") {{ i18nstringLocalize(entry.label) }}
    //-             div(v-if="entry.type == 'custom'") {{ i18nstringLocalize(entry.content) }}
    //-             div(v-if="entry.type == 'placeholder'") {{ store.variables[style_def.content_type][entry.content] }}
    //- pre
    //-     //- code {{ config }}
    //-     code {{ style_def }}
    //-     code {{ layout }}
        //- div(style="position: absolute; background-color: red; top: 0.5cm; left: 0cm; height: 1cm; width: 2cm;") Logo
        //- div(style="position: absolute; background-color: red; top: 0.5cm; left: 2.25cm; height: 1cm; width: 5.5cm;") Logo Text
        //- div(style="position: absolute; background-color: red; top: 0.5cm; left: 8cm; height: 1cm; width: 2cm;") Header
        //- div(style="position: absolute; background-color: red; top: 2.5cm; left: 0cm; height: 2cm; width: 10cm;") Primary
        //- div(style="position: absolute; background-color: red; top: 4.75cm; left: 0cm; height: 1cm; width: 10cm;") Secondary
        //- div(style="position: absolute; background-color: red; top: 7cm; left: 0cm; height: 1cm; width: 10cm;") Auxiliary
        //- div(style="position: absolute; background-color: red; top: 10cm; left: 3cm; height: 4cm; width: 4cm;")
</template>
