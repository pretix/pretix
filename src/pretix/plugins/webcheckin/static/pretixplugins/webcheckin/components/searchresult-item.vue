<template>
  <a class="list-group-item searchresult" href="#" @click.prevent="$emit('selected', position)" ref="a">
    <div class="details">
      <h4>{{ position.order }}-{{ position.positionid }} {{ position.attendee_name }}</h4>
      <span>{{ itemvar }}<br></span>
      <span v-if="subevent">{{ subevent }}<br></span>
      <div class="secret">{{ position.secret }}</div>
    </div>
    <div :class="`status status-${status}`">
      <span v-if="position.require_attention"><span class="fa fa-warning"></span><br></span>
      {{ $root.strings[`status.${status}`] }}
    </div>
  </a>
</template>
<script>
export default {
  components: {},
  props: {
    position: Object
  },
  computed: {
    status() {
      if (this.position.checkins.length) return 'redeemed';
      return this.position.order__status
    },
    itemvar() {
      if (this.position.variation) {
        return `${i18nstring_localize(this.position.item.name)} – ${i18nstring_localize(this.position.variation.value)}`
      }
      return i18nstring_localize(this.position.item.name)
    },
    subevent() {
      if (!this.position.subevent) return ''
      const name = i18nstring_localize(this.position.subevent.name)
      const date = moment.utc(this.position.subevent.date_from).tz(this.$root.timezone).format(this.$root.datetime_format)
      return `${name} · ${date}`
    },
  },
}
// secret
// status
// order code
// name
// seat
// require attention
</script>
