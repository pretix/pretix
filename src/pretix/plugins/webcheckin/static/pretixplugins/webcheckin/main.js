/*global gettext, Vue, App*/

moment.locale(document.body.attributes['data-datetimelocale'].value)
window.vapp = new Vue({
    components: {
        App: App.default
    },
    render: function (h) {
        return h('App')
    },
    data: {
        api: {
            lists: document.querySelector('#app').attributes['data-api-lists'].value,
        },
        strings: {
            'checkinlist.select': gettext('Select a check-in list'),
            'checkinlist.none': gettext('No active check-in lists found.'),
            'pagination.next': gettext('Load more'),
        },
        event_name: document.querySelector('#app').attributes['data-event-name'].value,
        timezone: document.body.attributes['data-timezone'].value,
        datetime_format: document.body.attributes['data-datetimeformat'].value,
    },
    el: '#app'
})
