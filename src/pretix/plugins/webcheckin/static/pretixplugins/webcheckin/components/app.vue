<template>
  <div id="app">
    <div class="container">
      <h1>
        {{ $root.event_name }}
        <small v-if="checkinlist">
          {{ listname }}
        </small>
      </h1>

      <checkinlist-select v-if="!checkinlist" @selected="checkinlist = $event"></checkinlist-select>

    </div>
  </div>
</template>
<script>
export default {
  components: {
    CheckinlistSelect: CheckinlistSelect.default,
  },
  data () {
    return {
      checkinlist: null,
    }
  },
  computed: {
    listname () {
      if (!this.checkinlist) return ''
      if(!this.checkinlist.subevent) return this.checkinlist.name
      const name = i18nstring_localize(this.checkinlist.subevent.name)
      const date = moment.utc(this.checkinlist.subevent.date_from).tz(this.$root.timezone).format(this.$root.datetime_format)
      return `${this.checkinlist.name} · ${name} · ${date}`
    }
  },
}
</script>
