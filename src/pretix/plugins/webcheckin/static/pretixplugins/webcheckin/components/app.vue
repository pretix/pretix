<template>
  <div id="app">
    <div class="container">
      <h1>
        {{ $root.event_name }}
      </h1>

      <checkinlist-select v-if="!checkinlist" @selected="selectList($event)"></checkinlist-select>

      <input v-if="checkinlist" ref="input" :placeholder="$root.strings['input.placeholder']" class="form-control">

      <div v-if="checkinlist" class="scantype text-center">
        <span :class="'fa fa-sign-' + (type === 'exit' ? 'out' : 'in')"></span>
        {{ $root.strings['scantype.' + type] }}<br>
        <button @click="switchType" class="btn btn-default"><span class="fa fa-refresh"></span> {{ $root.strings['scantype.switch'] }}</button>
      </div>
      <div v-if="checkinlist" class="meta text-center">
        {{ checkinlist.name }}<br>
        {{ subevent }}<br>
        <button @click="switchList" type="button" class="btn btn-default">{{ $root.strings['checkinlist.switch'] }}</button>
      </div>
    </div>
  </div>
</template>
<script>
export default {
  components: {
    CheckinlistSelect: CheckinlistSelect.default,
  },
  data() {
    return {
      type: 'entry',
      checkinlist: null,
    }
  },
  mounted () {
    window.addEventListener('focus', this.refocus)
    document.addEventListener('keydown', this.globalKeydown)
  },
  destroyed () {
    window.removeEventListener('focus', this.refocus)
    document.removeEventListener('keydown', this.globalKeydown)
  },
  computed: {
    subevent() {
      if (!this.checkinlist) return ''
      if (!this.checkinlist.subevent) return ''
      const name = i18nstring_localize(this.checkinlist.subevent.name)
      const date = moment.utc(this.checkinlist.subevent.date_from).tz(this.$root.timezone).format(this.$root.datetime_format)
      return `${name} · ${date}`
    }
  },
  methods: {
    globalKeydown(e) {
      if (document.activeElement.nodeName.toLowerCase() !== 'input' && document.activeElement.nodeName.toLowerCase() !== 'textarea') {
        if (e.key.match(/^[a-z0-9A-Z+/=<>#]$/)) {
          this.refocus()
        }
      }
    },
    refocus() {
      this.$nextTick(() => {
        this.$refs.input.focus()
      })
    },
    switchType() {
      this.type = this.type === 'exit' ? 'entry' : 'exit'
      this.refocus()
    },
    switchList() {
      location.hash = ''
      this.checkinlist = null
    },
    selectList(list) {
      this.checkinlist = list
      location.hash = '#' + list.id
      this.refocus()
    }
  }
}
</script>
