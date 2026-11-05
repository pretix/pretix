<script setup lang="ts">
import {getEventLocales} from "./api"
import {useId} from "vue";

const locales = getEventLocales();

const props = defineProps<{ value: any, id?: string }>();
const uniqueId = useId()

</script>

<template>
<div class="i18n-form-group" :id="id ?? uniqueId">
	<textarea v-for="locale in locales" cols="40" rows="2" :lang="locale" dir="ltr" class="form-control" title="Englisch" :id="`${id ?? uniqueId}_${locale}`" :placeholder="locale" v-model="value[locale]"></textarea>
</div>
</template>
