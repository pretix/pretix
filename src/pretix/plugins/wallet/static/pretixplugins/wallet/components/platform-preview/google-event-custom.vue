<script setup lang="ts">
import { computed, inject } from "vue";
import { StoreKey } from "../../walletStore";
import { dateTimeFormat, i18nstringLocalize } from "../../helpers";
import Google from "./google.vue";
const store = inject(StoreKey)!;
const gettext = (window as any).gettext;
import FieldGroupEntries from "./FieldGroupEntries.vue";

const props = defineProps<{ data: any }>();

</script>

<template lang="pug">
    Google(:data="data")
        template(#card-rows)
            FieldGroupEntries.card-row(fieldgroup="second_row")
            FieldGroupEntries.card-row(fieldgroup="third_row")

        template(#details)
            FieldGroupEntries.f-column(fieldgroup="details")

</template>