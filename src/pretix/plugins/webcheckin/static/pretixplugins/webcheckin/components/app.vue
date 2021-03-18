<template>
  <div id="app">
    <div class="container">
      <h1>
        {{ $root.event_name }}
      </h1>

      <checkinlist-select v-if="!checkinlist" @selected="selectList($event)"></checkinlist-select>

      <input v-if="checkinlist" v-model="query" ref="input" :placeholder="$root.strings['input.placeholder']" @keyup="inputKeyup" class="form-control scan-input">

      <div v-if="checkResult !== null" class="panel panel-primary check-result">
        <div class="panel-heading">
          <h3 class="panel-title">
            {{ $root.strings['check.headline'] }}
          </h3>
        </div>
        <div v-if="checkLoading" class="panel-body text-center">
          <span class="fa fa-4x fa-cog fa-spin loading-icon"></span>
        </div>
        <div v-else-if="checkError" class="panel-body text-center">
          {{ checkError }}
        </div>
        <div :class="'check-result-status check-result-' + checkResultColor">
          {{ checkResultText }}
        </div>
        <div class="panel-body">
          <div class="details">
            <h4>{{ checkResult.position.order }}-{{ checkResult.position.positionid }} {{ checkResult.position.attendee_name }}</h4>
            <span>{{ checkResultItemvar }}</span>
            <span v-if="checkResult.position.seat"><br>{{ checkResult.position.seat.name }}</span>
          </div>
        </div>
      </div>

      <div v-else-if="searchResults !== null" class="panel panel-primary search-results">
        <div class="panel-heading">
          <h3 class="panel-title">
            {{ $root.strings['results.headline'] }}
          </h3>
        </div>
        <ul class="list-group">
          <searchresult-item v-if="searchResults" v-for="p in searchResults" :position="p" :key="p.id" @selected="selectResult($event)"></searchresult-item>
          <li v-if="searchLoading" class="list-group-item text-center">
            <span class="fa fa-4x fa-cog fa-spin loading-icon"></span>
          </li>
          <li v-else-if="searchError" class="list-group-item text-center">
            {{ searchError }}
          </li>
          <a v-else-if="searchNextUrl" class="list-group-item text-center" href="#" @click.prevent="searchNext">
            {{ $root.strings['pagination.next'] }}
          </a>
        </ul>
      </div>

      <div v-else>
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
  </div>
</template>
<script>
export default {
  components: {
    CheckinlistSelect: CheckinlistSelect.default,
    SearchresultItem: SearchresultItem.default,
  },
  data() {
    return {
      type: 'entry',
      query: '',
      searchLoading: false,
      searchResults: null,
      searchNextUrl: null,
      searchError: null,
      checkLoading: false,
      checkError: null,
      checkResult: null,
      checkinlist: null,
    }
  },
  mounted() {
    window.addEventListener('focus', this.globalKeydown)
    document.addEventListener('keydown', this.globalKeydown)
  },
  destroyed() {
    window.removeEventListener('focus', this.globalKeydown)
    document.removeEventListener('keydown', this.globalKeydown)
  },
  computed: {
    subevent() {
      if (!this.checkinlist) return ''
      if (!this.checkinlist.subevent) return ''
      const name = i18nstring_localize(this.checkinlist.subevent.name)
      const date = moment.utc(this.checkinlist.subevent.date_from).tz(this.$root.timezone).format(this.$root.datetime_format)
      return `${name} · ${date}`
    },
    checkResultItemvar() {
      if (!this.checkResult) return ''
      if (this.checkResult.position.variation) {
        return `${i18nstring_localize(this.checkResult.position.item.name)} – ${i18nstring_localize(this.checkResult.position.variation.value)}`
      }
      return i18nstring_localize(this.checkResult.position.item.name)
    },
    checkResultText () {
      if (!this.checkResult) return ''
      if (this.checkResult.status === 'ok') {
        return this.$root.strings['result.ok']
      } else if (this.checkResult.status === 'incomplete') {
        return this.$root.strings['result.questions']
      } else {
        return this.$root.strings['result.' + this.checkResult.reason]
      }
    },
    checkResultColor () {
      if (!this.checkResult) return ''
      if (this.checkResult.status === 'ok') {
        return "green";
      } else if (this.checkResult.status === 'incomplete') {
        return "purple";
      } else {
        if (this.checkResult.reason === 'already_redeemed') return "orange";
        return "red";
      }
    },
  },
  methods: {
    selectResult(res) {
      this.check(res.id)
    },
    check(id) {
      this.checkLoading = true
      this.checkError = null
      this.checkResult = {}
      fetch(this.$root.api.lists + this.checkinlist.id + '/positions/' + encodeURIComponent(id) + '/redeem/?expand=item&expand=variation', {
        method: 'POST',
        headers: {
          'X-CSRFToken': document.querySelector("input[name=csrfmiddlewaretoken]").value,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          questions_supported: false,
          canceled_supported: true,
          type: this.type,
        })
      })
          .then(response => response.json())
          .then(data => {
            this.checkLoading = false
            this.checkResult = data
          })
          .catch(reason => {
            this.checkLoading = false
            this.checkResult = {}
            this.checkError = null
          })
    },
    globalKeydown(e) {
      if (document.activeElement.nodeName.toLowerCase() !== 'input' && document.activeElement.nodeName.toLowerCase() !== 'textarea') {
        if (e.key && e.key.match(/^[a-z0-9A-Z+/=<>#]$/)) {
          this.query = ''
          this.refocus()
        }
      }
    },
    refocus() {
      this.$nextTick(() => {
        this.$refs.input.focus()
      })
    },
    inputKeyup(e) {
      if (e.key === "Enter") {
        console.log("startsearch")
        this.startSearch()
      } else if (this.query === '') {
        this.cleanup()
      }
    },
    cleanup() {
      this.searchLoading = false
      this.searchResults = null
    },
    startSearch() {
      this.checkResult = null
      this.searchLoading = true
      this.searchError = null
      this.searchResults = []
      fetch(this.$root.api.lists + this.checkinlist.id + '/positions/?ignore_status=true&expand=subevent&expand=item&expand=variation&check_rules=true&search=' + encodeURIComponent(this.query))
          .then(response => response.json())
          .then(data => {
            this.searchLoading = false
            if (data.results) {
              this.searchResults = data.results
              this.searchNextUrl = data.next
            } else {
              this.searchError = data
            }
          })
          .catch(reason => {
            this.searchLoading = false
            this.searchResults = []
            this.searchError = reason
          })
    },
    searchNext() {
      this.searchLoading = true
      this.searchError = null
      fetch(this.searchNextUrl)
          .then(response => response.json())
          .then(data => {
            this.searchLoading = false
            if (data.results) {
              this.searchResults.push(...data.results)
              this.searchNextUrl = data.next
            } else {
              this.searchError = data
            }
          })
          .catch(reason => {
            this.searchLoading = false
            this.searchError = reason
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
