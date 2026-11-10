<script setup lang="ts">
import Google from "./google.vue";

import FieldGroupEntries from "./FieldGroupEntries.vue";

const props = defineProps();

</script>

<template lang="pug">
    Google(v-bind="props")
        template(#card-rows)
            FieldGroupEntries.card-row(fieldgroup="second_row")
            FieldGroupEntries.card-row(fieldgroup="third_row")

        template(#details)
            FieldGroupEntries.f-column(fieldgroup="details")

</template>