<script setup lang="ts">
import { ref, useId, defineProps } from 'vue';

defineProps(['value', 'id'])

</script>

<template>
<div class="i18n-form-group" :id="id">
<textarea cols="40" rows="2" lang="en" dir="ltr" class="form-control" title="Englisch" :id="`${id}_0`" placeholder="Englisch" v-model="value.en"></textarea>
<textarea cols="40" rows="2" lang="de" dir="ltr" class="form-control" title="Deutsch" :id="`${id}_1`" placeholder="Deutsch" v-model="value.de"></textarea>
</div>
</template>
