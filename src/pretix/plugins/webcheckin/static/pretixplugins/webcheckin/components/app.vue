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
          <a class="pull-right" @click.prevent="clear" href="#" tabindex="-1">
            <span class="fa fa-close"></span>
          </a>
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
        <div class="panel-body" v-if="checkResult.position">
          <div class="details">
            <h4>{{ checkResult.position.order }}-{{ checkResult.position.positionid }} {{ checkResult.position.attendee_name }}</h4>
            <strong v-if="checkResult.reason_explanation">{{ checkResult.reason_explanation }}<br></strong>
            <span>{{ checkResultItemvar }}</span><br>
            <span v-if="checkResultSubevent">{{ checkResultSubevent }}<br></span>
            <span class="secret">{{ checkResult.position.secret }}</span>
            <span v-if="checkResult.position.seat"><br>{{ checkResult.position.seat.name }}</span>
          </div>
        </div>
        <div class="attention" v-if="checkResult && checkResult.require_attention">
          <span class="fa fa-warning"></span>
          {{ $root.strings['check.attention'] }}
        </div>
      </div>

      <div v-else-if="searchResults !== null" class="panel panel-primary search-results">
        <div class="panel-heading">
          <a class="pull-right" @click.prevent="clear" href="#" tabindex="-1">
            <span class="fa fa-close"></span>
          </a>
          <h3 class="panel-title">
            {{ $root.strings['results.headline'] }}
          </h3>
        </div>
        <ul class="list-group">
          <searchresult-item ref="result" v-if="searchResults" v-for="p in searchResults" :position="p" :key="p.id" @selected="selectResult($event)"></searchresult-item>
          <li v-if="!searchResults.length && !searchLoading" class="list-group-item text-center">
            {{ $root.strings['results.none'] }}
          </li>
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

      <div v-else-if="checkinlist">
        <div class="panel panel-default">
          <div class="panel-body meta">
            <div class="row settings">
              <div class="col-sm-6">
                <div>
                  <span :class="'fa fa-sign-' + (type === 'exit' ? 'out' : 'in')"></span>
                  {{ $root.strings['scantype.' + type] }}<br>
                  <button @click="switchType" class="btn btn-default"><span class="fa fa-refresh"></span> {{ $root.strings['scantype.switch'] }}</button>
                </div>
              </div>
              <div class="col-sm-6">
                <div v-if="checkinlist">
                  {{ checkinlist.name }}<br>
                  {{ subevent }}<br v-if="subevent">
                  <button @click="switchList" type="button" class="btn btn-default">{{ $root.strings['checkinlist.switch'] }}</button>
                </div>
              </div>
            </div>
            <div v-if="status" class="row status">
              <div class="col-sm-4">
                <span class="statistic">{{ status.checkin_count }}</span>
                {{ $root.strings['status.checkin'] }}
              </div>
              <div class="col-sm-4">
                <span class="statistic">{{ status.position_count }}</span>
                {{ $root.strings['status.position'] }}
              </div>
              <div class="col-sm-4">
                <div class="pull-right">
                  <button @click="fetchStatus" class="btn btn-default"><span :class="'fa fa-refresh' + (statusLoading ? ' fa-spin': '')"></span></button>
                </div>
                <span class="statistic">{{ status.inside_count }}</span>
                {{ $root.strings['status.inside'] }}
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>

    <div :class="'modal modal-unpaid fade' + (showUnpaidModal ? ' in' : '')" tabindex="-1" role="dialog">
      <div class="modal-dialog" role="document">
        <div class="modal-content" v-if="checkResult && checkResult.position">
          <div class="modal-header">
            <button type="button" class="close" @click="showUnpaidModal = false">
              <span class="fa fa-close"></span>
            </button>
            <h4 class="modal-title">
              {{ $root.strings['modal.unpaid.head'] }}
            </h4>
          </div>
          <div class="modal-body">
            <p>
              {{ $root.strings['modal.unpaid.text'] }}
            </p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-primary pull-right" @click="check(checkResult.position.secret, true, false, false, true)">
              {{ $root.strings['modal.continue'] }}
            </button>
            <button type="button" class="btn btn-default" @click="showUnpaidModal = false">
              {{ $root.strings['modal.cancel'] }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <form :class="'modal modal-questions fade' + (showQuestionsModal ? ' in' : '')" tabindex="-1" role="dialog" ref="questionsModal">
      <div class="modal-dialog" role="document">
        <div class="modal-content" v-if="checkResult && checkResult.questions">
          <div class="modal-header">
            <button type="button" class="close" @click="showQuestionsModal = false">
                <span class="fa fa-close"></span>
            </button>
            <h4 class="modal-title">
              {{ $root.strings['modal.questions'] }}
            </h4>
          </div>
          <div class="modal-body">
            <div :class="q.type === 'M' ? '' : (q.type === 'B' ? 'checkbox' : 'form-group')" v-for="q in checkResult.questions">
              <label :for="'q_' + q.id" v-if="q.type !== 'B'">
                {{ q.question }}
                {{ q.required ? ' *' : '' }}
              </label>

              <textarea v-if="q.type === 'T'" v-model="answers[q.id.toString()]" :id="'q_' + q.id" class="form-control" :required="q.required"></textarea>
              <input v-else-if="q.type === 'N'" type="number" v-model="answers[q.id.toString()]" :id="'q_' + q.id" class="form-control" :required="q.required">
              <datefield v-else-if="q.type === 'D'" v-model="answers[q.id.toString()]" :id="'q_' + q.id" :required="q.required"></datefield>
              <timefield v-else-if="q.type === 'H'" v-model="answers[q.id.toString()]" :id="'q_' + q.id" :required="q.required"></timefield>
              <datetimefield v-else-if="q.type === 'W'" v-model="answers[q.id.toString()]" :id="'q_' + q.id" :required="q.required"></datetimefield>
              <select v-else-if="q.type === 'C'" v-model="answers[q.id.toString()]" :id="'q_' + q.id" class="form-control" :required="q.required">
                <option v-if="!q.required"></option>
                <option v-for="op in q.options" :value="op.id.toString()">{{ op.answer }}</option>
              </select>
              <div v-else-if="q.type === 'F'"><em>file input not supported</em></div>
              <div v-else-if="q.type === 'M'">
                <div class="checkbox" v-for="op in q.options">
                  <label>
                    <input type="checkbox" :checked="answers[q.id.toString()] && answers[q.id.toString()].split(',').includes(op.id.toString)" @input="answerSetM(q.id.toString(), op.id.toString(), $event.target.checked)">
                    {{ op.answer }}
                  </label>
                </div>
              </div>
              <label v-else-if="q.type === 'B'">
                <input type="checkbox" :checked="answers[q.id.toString()] === 'true'" @input="answers[q.id.toString()] = $event.target.checked.toString()" :required="q.required">
                {{ q.question }}
                {{ q.required ? ' *' : '' }}
              </label>
              <select v-else-if="q.type === 'CC'" v-model="answers[q.id.toString()]" :id="'q_' + q.id" class="form-control" :required="q.required">
                <option v-if="!q.required"></option>
                <option v-for="op in countries" :value="op.key">{{ op.value }}</option>
              </select>
              <input v-else v-model="answers[q.id.toString()]" :id="'q_' + q.id" class="form-control" :required="q.required">
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-primary pull-right" @click="check(checkResult.position.secret, true, true, true)">
              {{ $root.strings['modal.continue'] }}
            </button>
            <button type="button" class="btn btn-default" @click="showQuestionsModal = false">
              {{ $root.strings['modal.cancel'] }}
            </button>
          </div>
        </div>
      </div>
    </form>

  </div>
</template>
<script>
export default {
  components: {
    CheckinlistSelect: CheckinlistSelect.default,
    SearchresultItem: SearchresultItem.default,
    Datetimefield: Datetimefield.default,
    Timefield: Timefield.default,
    Datefield: Datefield.default,
  },
  data() {
    return {
      type: 'entry',
      query: '',
      searchLoading: false,
      searchResults: null,
      searchNextUrl: null,
      searchError: null,
      status: null,
      statusLoading: 0,
      statusInterval: null,
      checkLoading: false,
      checkError: null,
      checkResult: null,
      checkinlist: null,
      clearTimeout: null,
      showUnpaidModal: false,
      showQuestionsModal: false,
      answers: {},
    }
  },
  mounted() {
    window.addEventListener('focus', this.globalKeydown)
    document.addEventListener("visibilitychange", this.globalKeydown)
    document.addEventListener('keydown', this.globalKeydown)
    this.statusInterval = window.setInterval(this.fetchStatus, 120 * 1000)
  },
  destroyed() {
    window.removeEventListener('focus', this.globalKeydown)
    document.removeEventListener("visibilitychange", this.globalKeydown)
    document.removeEventListener('keydown', this.globalKeydown)
    window.clearInterval(this.statusInterval)
    window.clearInterval(this.clearTimeout)
  },
  computed: {
    countries() {
      return JSON.parse(document.querySelector("#countries").innerHTML);
    },
    subevent() {
      if (!this.checkinlist) return ''
      if (!this.checkinlist.subevent) return ''
      const name = i18nstring_localize(this.checkinlist.subevent.name)
      const date = moment.utc(this.checkinlist.subevent.date_from).tz(this.$root.timezone).format(this.$root.datetime_format)
      return `${name} · ${date}`
    },
    checkResultSubevent() {
      if (!this.checkResult) return ''
      if (!this.checkResult.position.subevent) return ''
      const name = i18nstring_localize(this.checkResult.position.subevent.name)
      const date = moment.utc(this.checkResult.position.subevent.date_from).tz(this.$root.timezone).format(this.$root.datetime_format)
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
        if (this.type === "exit") {
          return this.$root.strings['result.exit']
        }
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
      this.check(res.id, false, false, false, false)
    },
    answerSetM(qid, opid, checked) {
      let arr = this.answers[qid] ? this.answers[qid].split(',') : [];
      if (checked && !arr.includes(opid)) {
        arr.push(opid)
      } else if (!checked) {
        arr = arr.filter(o => opid !== o)
      }
      this.answers[qid] = arr.join(',')
    },
    clear() {
      this.query = ''
      this.searchLoading = false
      this.searchResults = null
      this.searchNextUrl = null
      this.searchError = null
      this.checkLoading = false
      this.checkError = null
      this.checkResult = null
      this.showUnpaidModal = false
      this.showQuestionsModal = false
      this.answers = {}
    },
    check(id, ignoreUnpaid, keepAnswers, fallbackToSearch, untrusted) {
      if (!keepAnswers) {
        this.answers = {}
      } else if (this.showQuestionsModal) {
        if (!this.$refs.questionsModal.reportValidity()) {
          return
        }
      }
      this.showUnpaidModal = false
      this.showQuestionsModal = false
      this.checkLoading = true
      this.checkError = null
      this.checkResult = {}
      window.clearInterval(this.clearTimeout)

      this.$nextTick(() => {
        this.$refs.input.blur()
      })

      let url = this.$root.api.lists + this.checkinlist.id + '/positions/' + encodeURIComponent(id) + '/redeem/?expand=item&expand=subevent&expand=variation'
      if (untrusted)  {
        url += '&untrusted_input=true'
      }
      fetch(url, {
        method: 'POST',
        headers: {
          'X-CSRFToken': document.querySelector("input[name=csrfmiddlewaretoken]").value,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          questions_supported: true,
          canceled_supported: true,
          ignore_unpaid: ignoreUnpaid || false,
          type: this.type,
          answers: this.answers,
        })
      })
          .then(response => {
            if (response.status === 404) {
              return {
                status: 'error',
                reason: 'invalid',
              }
            }
            if (!response.ok && [401, 403].includes(response.status)) {
              window.location.href = '/control/login?next=' + encodeURIComponent(window.location.pathname + window.location.search + window.location.hash);
            }
            if (!response.ok && response.status != 400) {
              throw new Error("HTTP status " + response.status);
            }
            return response.json()
          })
          .then(data => {
            this.checkLoading = false
            this.checkResult = data
            if (this.checkinlist.include_pending && data.status === 'error' && data.reason === 'unpaid') {
              this.showUnpaidModal = true
              this.$nextTick(() => {
                document.querySelector(".modal-unpaid .btn-primary").focus()
              })
            } else if (data.status === 'incomplete') {
              this.showQuestionsModal = true
              for (const q of this.checkResult.questions) {
                if (!this.answers[q.id.toString()]) {
                  this.answers[q.id.toString()] = ""
                }
                q.question = i18nstring_localize(q.question)
                for (const o of q.options) {
                  o.answer = i18nstring_localize(o.answer)
                }
              }
              this.$nextTick(() => {
                document.querySelector(".modal-questions input, .modal-questions select, .modal-questions textarea").focus()
              })
            } else if (data.status === 'error' && data.reason === 'invalid' && fallbackToSearch) {
              this.startSearch(false)
            } else {
              this.clearTimeout = window.setTimeout(this.clear, 1000 * 20)
              this.fetchStatus()
            }
          })
          .catch(reason => {
            this.checkLoading = false
            this.checkResult = {}
            this.checkError = reason.toString()
            this.clearTimeout = window.setTimeout(this.clear, 1000 * 20)
          })
    },
    globalKeydown(e) {
      if (document.activeElement.classList.contains('searchresult') && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        if (e.key === 'ArrowDown') {
          document.activeElement.nextElementSibling.focus()
          e.preventDefault()
          return true
        }
        if (e.key === 'ArrowUp') {
          document.activeElement.previousElementSibling.focus()
          e.preventDefault()
          return true
        }
      }
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
        this.startSearch(true)
      } else if (this.query === '') {
        this.clear()
      }
    },
    startSearch(fallbackToScan) {
      if (this.query.length >= 32 && fallbackToScan) {
        // likely a secret, not a search result
        this.check(this.query, false, false, true, true)
        return
      }

      this.checkResult = null
      this.searchLoading = true
      this.searchError = null
      this.searchResults = []
      this.answers = {}

      window.clearInterval(this.clearTimeout)
      fetch(this.$root.api.lists + this.checkinlist.id + '/positions/?ignore_status=true&expand=subevent&expand=item&expand=variation&check_rules=true&search=' + encodeURIComponent(this.query))
          .then(response => {
            if (!response.ok && [401, 403].includes(response.status)) {
              window.location.href = '/control/login?next=' + encodeURIComponent(window.location.pathname + window.location.search + window.location.hash);
            }
            return response.json()
          })
          .then(data => {
            this.searchLoading = false
            if (data.results) {
              this.searchResults = data.results
              this.searchNextUrl = data.next
              if (data.results.length) {
                if (data.results[0].secret === this.query) {
                  this.$nextTick(() => {
                    this.$refs.input.blur()
                    this.$refs.result[0].$refs.a.click()
                  })
                } else {
                  this.$nextTick(() => {
                    this.$refs.result[0].$refs.a.focus()
                  })
                }
              } else {
                this.$nextTick(() => {
                  this.$refs.input.blur()
                })
              }
            } else {
              this.searchError = data
            }
            this.clearTimeout = window.setTimeout(this.clear, 1000 * 20)
          })
          .catch(reason => {
            this.searchLoading = false
            this.searchResults = []
            this.searchError = reason
            this.clearTimeout = window.setTimeout(this.clear, 1000 * 20)
          })
    },
    searchNext() {
      this.searchLoading = true
      this.searchError = null
      window.clearInterval(this.clearTimeout)
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
            this.clearTimeout = window.setTimeout(this.clear, 1000 * 20)
          })
          .catch(reason => {
            this.searchLoading = false
            this.searchError = reason
            this.clearTimeout = window.setTimeout(this.clear, 1000 * 20)
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
    fetchStatus() {
      this.statusLoading++
      fetch(this.$root.api.lists + this.checkinlist.id + '/status/')
              .then(response => response.json())
              .then(data => {
                this.statusLoading--
                this.status = data
              })
              .catch(reason => {
                this.statusLoading--
              })
    },
    selectList(list) {
      this.checkinlist = list
      location.hash = '#' + list.id
      this.refocus()
      this.fetchStatus()
    }
  }
}
</script>
