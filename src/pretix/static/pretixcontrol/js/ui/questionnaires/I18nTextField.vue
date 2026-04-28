<script setup lang="ts">
import { ref, useId, defineProps } from 'vue';
import {get_event_locales} from "./api";

const locales = get_event_locales();

const props = defineProps(['value', 'id']);

if (!props.value) props.value = {};
</script>

<template>
<div class="i18n-form-group" :id="id">
	<textarea v-for="locale in locales" cols="40" rows="2" :lang="locale" dir="ltr" class="form-control" title="Englisch" :id="`${id}_${locale}`" :placeholder="locale" v-model="value[locale]"></textarea>
</div>
</template>
