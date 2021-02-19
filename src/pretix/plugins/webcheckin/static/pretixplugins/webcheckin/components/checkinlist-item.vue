<template>
  <a class="list-group-item" href="#" @click.prevent="$emit('selected', list)">
    <div class="row">
      <div class="col-md-6">
        {{ list.name }}
      </div>
      <div class="col-md-6 text-muted">
        {{ subevent }}
      </div>
    </div>
  </a>
</template>
<script>
export default {
  components: {},
  props: {
    list: Object
  },
  computed: {
    subevent () {
      if (!this.list.subevent) return '';
      const name = i18nstring_localize(this.list.subevent.name)
      const date = moment.utc(this.list.subevent.date_from).tz(this.$root.timezone).format(this.$root.datetime_format)
      return `${name} · ${date}`
    }
  },
}
</script>
