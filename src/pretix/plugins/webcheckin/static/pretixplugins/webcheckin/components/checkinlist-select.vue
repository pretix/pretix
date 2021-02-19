<template>
  <div class="panel panel-primary checkinlist-select">
    <div class="panel-heading">
      <h3 class="panel-title">
        {{ $root.strings['checkinlist.select'] }}
      </h3>
    </div>
    <ul class="list-group">
      <checkinlist-item v-if="lists" v-for="l in lists" :list="l" :key="l.id" @selected="$emit('selected', l)"></checkinlist-item>
      <li v-if="loading" class="list-group-item text-center">
        <span class="fa fa-4x fa-cog fa-spin loading-icon"></span>
      </li>
      <li v-else-if="error" class="list-group-item text-center">
        {{ error }}
      </li>
      <a v-else-if="next_url" class="list-group-item text-center" href="#" @click.prevent="loadNext">
        {{ $root.strings['pagination.next'] }}
      </a>
    </ul>
  </div>
</template>
<script>
export default {
  components: {
    CheckinlistItem: CheckinlistItem.default,
  },
  data() {
    return {
      loading: false,
      error: null,
      lists: null,
      next_url: null,
    }
  },
  // TODO: pagination
  mounted() {
    this.load()
  },
  methods: {
    load() {
      this.loading = true
      const cutoff = moment().subtract(8, 'hours').toISOString()
      if (location.hash) {
        fetch(this.$root.api.lists + location.hash.substr(1) + '/' + '?expand=subevent')
            .then(response => response.json())
            .then(data => {
              this.loading = false
              if (data.id) {
                this.$emit('selected', data)
              } else {
                location.hash = ''
                this.load()
              }
            })
            .catch(reason => {
              location.hash = ''
              this.load()
            })
        return
      }
      fetch(this.$root.api.lists + '?exclude=checkin_count&exclude=position_count&expand=subevent&ends_after=' + cutoff)
          .then(response => response.json())
          .then(data => {
            this.loading = false
            if (data.results) {
              this.lists = data.results
              this.next_url = data.next
            } else if (data.results === 0) {
              this.error = this.$root.strings['checkinlist.none']
            } else {
              this.error = data
            }
          })
          .catch(reason => {
            this.loading = false
            this.error = reason
          })
    },
    loadNext() {
      this.loading = true
      fetch(this.next_url)
          .then(response => response.json())
          .then(data => {
            this.loading = false
            if (data.results) {
              this.lists.push(...data.results)
              this.next_url = data.next
            } else if (data.results === 0) {
              this.error = this.$root.strings['checkinlist.none']
            } else {
              this.error = data
            }
          })
          .catch(reason => {
            this.loading = false
            this.error = reason
          })
    },
  },
}
</script>
