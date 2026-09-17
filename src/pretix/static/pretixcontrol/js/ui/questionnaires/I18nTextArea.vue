<script setup lang="ts">
import {getEventLocales} from "./api"

const locales = getEventLocales();

const props = defineProps<{ value: any, id?: string }>();
</script>

<template>
<div class="i18n-form-group" :id="id">
	<textarea v-for="locale in locales" cols="40" rows="2" :lang="locale" dir="ltr" class="form-control" title="Englisch" :id="`${id}_${locale}`" :placeholder="locale" v-model="value[locale]"></textarea>
</div>
</template>
