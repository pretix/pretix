<script setup lang="ts">

import {SalesChannel} from "./model";
import {i18n_any} from "./helper";

const props = defineProps<{ salesChannel: SalesChannel, tooltip?: boolean }>();
</script>

<template>
  <template v-if="salesChannel.icon_url">
    <img :src="salesChannel.icon_url" class="fa-like-image" :alt="i18n_any(salesChannel.label)" :data-toggle="tooltip ? 'tooltip' : ''" :title="tooltip ? i18n_any(salesChannel.label) : ''">
  </template>
  <template v-else>
    <span :class="`fa fa-${salesChannel.icon} fa-fw text-muted`" :data-toggle="tooltip ? 'tooltip' : ''" :title="tooltip ? i18n_any(salesChannel.label) : ''"></span>
  </template>
</template>
