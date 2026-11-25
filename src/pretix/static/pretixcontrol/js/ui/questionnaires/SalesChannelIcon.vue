<script setup lang="ts">

import {SalesChannel} from "./model";
import {localize_string} from "@/pretix/static/pretixbase/js/i18n";

const props = defineProps<{ salesChannel: SalesChannel, tooltip?: boolean }>();
</script>

<template>
  <template v-if="salesChannel.icon_url">
    <img :src="salesChannel.icon_url" class="fa-like-image" :alt="localize_string(salesChannel.label)" :data-toggle="tooltip ? 'tooltip' : ''" :title="tooltip ? localize_string(salesChannel.label) : ''">
  </template>
  <template v-else>
    <span :class="`fa fa-${salesChannel.icon} fa-fw text-muted`" :data-toggle="tooltip ? 'tooltip' : ''" :title="tooltip ? localize_string(salesChannel.label) : ''"></span>
  </template>
</template>
