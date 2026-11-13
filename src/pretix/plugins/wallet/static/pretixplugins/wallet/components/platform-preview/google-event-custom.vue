<script setup lang="ts">
import type { PreviewProps } from 'src/pretix/static/pretixcontrol/wallet/index.d.ts'

import Google from './google.vue'
import FieldGroupEntries from './FieldGroupEntries.vue'

const props = defineProps<PreviewProps>()

</script>

<template lang="pug">
    Google(v-bind="props")
        template(#card-rows)
            FieldGroupEntries.card-row(fieldgroup="second_row" :fieldgroup_contents="fieldgroup_contents")
            FieldGroupEntries.card-row(fieldgroup="third_row" :fieldgroup_contents="fieldgroup_contents")

        template(#details)
            FieldGroupEntries.f-column(fieldgroup="details" :fieldgroup_contents="fieldgroup_contents")

</template>
