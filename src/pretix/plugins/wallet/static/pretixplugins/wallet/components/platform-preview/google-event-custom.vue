<script setup lang="ts">
import { computed, inject } from "vue";
import { StoreKey } from "../../walletStore";
import { dateTimeFormat, i18nstringLocalize } from "../../helpers";
import Google from "./google.vue";
const store = inject(StoreKey)!;
const gettext = (window as any).gettext;

const props = defineProps<{ data: any }>();

</script>

<template lang="pug">
    Google(:data="data")
        template(#card-rows)
            div.card-row
                div(v-for="entry in store.renderedFieldGroups['second_row']")
                    div.card-rows-label {{ entry.label }}
                    div.card-rows-content {{ entry.content }}
            div.card-row
                div(v-for="entry in store.renderedFieldGroups['third_row']")
                    div.card-rows-label {{ entry.label }}
                    div.card-rows-content {{ entry.content }}

        template(#details)
            div(v-for="entry in store.renderedFieldGroups['details']")
                div.pass-details-label {{ entry.label }}
                div.pass-details-content {{ entry.content }}

</template>